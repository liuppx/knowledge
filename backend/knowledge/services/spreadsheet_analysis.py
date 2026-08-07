from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import PurePosixPath
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from knowledge.models import AgentRun, AgentRunInput, ServicePrincipal
from knowledge.services.agent_run_artifacts import AgentRunArtifactService
from knowledge.services.agent_run_manifests import AgentRunManifestService
from knowledge.services.agent_run_progress import AgentRunProgressService
from knowledge.services.agent_runs import AgentRunService
from knowledge.services.spreadsheet_plan import SpreadsheetPlanService
from knowledge.services.spreadsheet_planner_provider import SpreadsheetPlanningProvider
from knowledge.services.spreadsheet_result_renderer import SpreadsheetResultRenderer
from knowledge.services.warehouse_access import WarehouseAccessService
from knowledge.utils.time import utc_now


class SpreadsheetAnalysisQueue:
    @staticmethod
    def claim_next(db: Session) -> str | None:
        candidate = db.scalar(
            select(AgentRun.id)
            .where(AgentRun.run_type == "spreadsheet_analysis")
            .where(AgentRun.status == "queued")
            .order_by(AgentRun.created_at.asc(), AgentRun.id.asc())
        )
        if candidate is None:
            return None
        result = db.execute(
            update(AgentRun)
            .where(AgentRun.id == candidate)
            .where(AgentRun.status == "queued")
            .values(status="running", started_at=utc_now(), manifest_sync_status="pending")
        )
        if (result.rowcount or 0) != 1:
            db.rollback()
            return None
        db.commit()
        return candidate


class SpreadsheetAnalysisService:
    MAX_INPUT_BYTES = 50 * 1024 * 1024
    MAX_PROFILE_ROWS = 100_000
    MAX_PROFILE_COLUMNS = 256
    MAX_XLSX_EXPANDED_BYTES = 200 * 1024 * 1024
    SAMPLE_VALUES = 5

    def __init__(self, planning_provider: SpreadsheetPlanningProvider | None = None) -> None:
        self.run_service = AgentRunService()
        self.progress = AgentRunProgressService()
        self.access = WarehouseAccessService()
        self.artifacts = AgentRunArtifactService(run_service=self.run_service, warehouse_access_service=self.access)
        self.manifests = AgentRunManifestService(warehouse_access_service=self.access)
        self.plans = SpreadsheetPlanService()
        self.planning_provider = planning_provider or SpreadsheetPlanningProvider()
        self.result_renderer = SpreadsheetResultRenderer()

    def process(self, db: Session, run_id: str) -> AgentRun:
        run = db.get(AgentRun, run_id)
        if run is None or run.run_type != "spreadsheet_analysis":
            raise LookupError("spreadsheet analysis run not found")
        if run.status != "running":
            return run
        principal = db.get(ServicePrincipal, run.service_principal_id)
        if principal is None:
            raise ValueError("service principal not found")
        step = None
        try:
            self.progress.event(db, run.id, "run.started", stage="resolve", progress=5, message="开始读取分析文件")
            step = self.progress.start_step(db, run.id, "resolve")
            input_item = db.scalar(select(AgentRunInput).where(AgentRunInput.run_id == run.id).order_by(AgentRunInput.id.asc()))
            if input_item is None:
                raise ValueError("spreadsheet input is missing")
            content = self._read_input(db, run, input_item)
            self.progress.finish_step(db, step, metrics={"bytes": len(content), "sha256": input_item.sha256})

            self.progress.event(db, run.id, "run.progress", stage="profile", progress=30, message="正在识别表格结构")
            step = self.progress.start_step(db, run.id, "profile")
            profile = self._profile(input_item.warehouse_path, content)
            self.progress.finish_step(
                db,
                step,
                metrics={"format": profile["format"], "rows": profile["rowCount"], "columns": profile["columnCount"]},
            )

            self.progress.event(db, run.id, "run.progress", stage="plan", progress=55, message="正在校验分析计划")
            step = self.progress.start_step(db, run.id, "plan")
            constraints = (run.metadata_json or {}).get("constraints") or {}
            constraints = dict(constraints) if isinstance(constraints, dict) else {}
            intent = str((run.metadata_json or {}).get("intent") or "")
            explicit_plan = isinstance(constraints.get("analysis_plan"), dict)
            planning = None
            if explicit_plan:
                generated_by = {"provider": "caller", "promptVersion": "none"}
            else:
                planning = self.planning_provider.generate(intent, profile)
                generated_by = dict(planning.generated_by)
                if planning.plan is not None:
                    constraints["analysis_plan"] = planning.plan
            try:
                plan = self.plans.build(
                    intent,
                    constraints,
                    [item["name"] for item in profile.get("columns", [])],
                )
            except ValueError as exc:
                if explicit_plan:
                    raise
                constraints.pop("analysis_plan", None)
                plan = self.plans.build(intent, constraints, [item["name"] for item in profile.get("columns", [])])
                generated_by["mode"] = "profile_only"
                generated_by["fallbackReason"] = self._error(exc)
            if planning is not None and planning.fallback_reason:
                generated_by["fallbackReason"] = planning.fallback_reason
            plan["generatedBy"] = generated_by
            output_formats = self._output_formats(constraints)
            plan["outputFormats"] = sorted(output_formats)
            self.progress.finish_step(
                db,
                step,
                metrics={"mode": plan["mode"], "provider": generated_by.get("provider", "none")},
            )

            result_rows = None
            if plan["mode"] != "profile_only":
                self.progress.event(db, run.id, "run.progress", stage="execute", progress=65, message="正在执行表格分析")
                step = self.progress.start_step(db, run.id, "execute")
                rows = self._load_rows(input_item.warehouse_path, content)
                result_rows = self.plans.execute(rows, plan)
                self.progress.finish_step(db, step, metrics={"inputRows": len(rows), "resultRows": len(result_rows)})
                profile["analysis"] = {"mode": plan["mode"], "resultRowCount": len(result_rows)}

            self.progress.event(db, run.id, "run.progress", stage="publish", progress=75, message="正在生成分析产物")
            step = self.progress.start_step(db, run.id, "publish")
            artifact_count = 0
            self.artifacts.upload(
                db,
                principal,
                run.id,
                artifact_key="analysis-plan",
                artifact_type="data",
                role="analysis_plan",
                status="final",
                file_name="analysis-plan.json",
                content_type="application/json",
                content=json.dumps(plan, ensure_ascii=False, indent=2).encode("utf-8"),
                generated_by={"service": "knowledge", "tool": "spreadsheet-plan-validator", "version": "m1", **generated_by},
                metadata={"inputSha256": input_item.sha256},
            )
            artifact_count += 1
            self.artifacts.upload(
                db,
                principal,
                run.id,
                artifact_key="profile",
                artifact_type="data",
                role="profile",
                status="final",
                file_name="profile.json",
                content_type="application/json",
                content=json.dumps(profile, ensure_ascii=False, indent=2).encode("utf-8"),
                generated_by={"service": "knowledge", "tool": "spreadsheet-profiler", "version": "m1"},
                metadata={"inputSha256": input_item.sha256, "sampled": profile["sampled"]},
            )
            artifact_count += 1
            summary = self._summary(run, profile)
            self.artifacts.upload(
                db,
                principal,
                run.id,
                artifact_key="summary",
                artifact_type="report",
                role="summary",
                status="final",
                file_name="summary.md",
                content_type="text/markdown",
                content=summary.encode("utf-8"),
                generated_by={"service": "knowledge", "tool": "spreadsheet-profiler", "version": "m1"},
                metadata={"inputSha256": input_item.sha256},
            )
            artifact_count += 1
            if result_rows is not None:
                result_columns = plan["select"] or plan["groupBy"] or [item["alias"] for item in plan["aggregations"]]
                if "csv" in output_formats:
                    result_content = self.plans.to_csv(result_rows, result_columns)
                    self.artifacts.upload(
                        db,
                        principal,
                        run.id,
                        artifact_key="result",
                        artifact_type="data",
                        role="result",
                        status="final",
                        file_name="result.csv",
                        content_type="text/csv",
                        content=result_content,
                        generated_by={"service": "knowledge", "tool": "spreadsheet-plan-executor", "version": "m1"},
                        metadata={"inputSha256": input_item.sha256, "rowCount": len(result_rows), "planSchema": plan["schema"]},
                    )
                    artifact_count += 1
                if "xlsx" in output_formats:
                    xlsx_content = self.result_renderer.to_xlsx(result_rows, result_columns, plan)
                    self.artifacts.upload(
                        db,
                        principal,
                        run.id,
                        artifact_key="result-xlsx",
                        artifact_type="data",
                        role="result",
                        status="final",
                        file_name="result.xlsx",
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        content=xlsx_content,
                        generated_by={"service": "knowledge", "tool": "spreadsheet-result-renderer", "version": "m1"},
                        metadata={"inputSha256": input_item.sha256, "rowCount": len(result_rows), "planSchema": plan["schema"]},
                    )
                    artifact_count += 1
                chart = self.result_renderer.chart(result_rows, plan) if "png" in output_formats else None
                if chart is not None:
                    chart_content, chart_metadata = chart
                    self.artifacts.upload(
                        db,
                        principal,
                        run.id,
                        artifact_key="chart",
                        artifact_type="image",
                        role="visualization",
                        status="final",
                        file_name="chart.png",
                        content_type="image/png",
                        content=chart_content,
                        generated_by={"service": "knowledge", "tool": "spreadsheet-result-renderer", "version": "m1"},
                        metadata={"inputSha256": input_item.sha256, **chart_metadata},
                    )
                    artifact_count += 1
            self.progress.finish_step(db, step, metrics={"artifacts": artifact_count})
            run = self.run_service.finish_run(db, principal, run.id, "completed")
            self.progress.event(db, run.id, "run.completed", stage="completed", progress=100, message="表格分析已完成")
            return self.manifests.sync(db, run)
        except Exception as exc:  # noqa: BLE001 - worker turns failures into run state
            if step is not None and step.status == "running":
                self.progress.fail_step(db, step, exc)
            run = db.get(AgentRun, run_id) or run
            if run.status == "running":
                run.status = "failed"
                run.error_summary = self._error(exc)
                run.finished_at = utc_now()
                run.manifest_sync_status = "pending"
                db.commit()
            self.progress.event(
                db,
                run.id,
                "run.failed",
                stage="failed",
                progress=100,
                message=self._error(exc),
                retryable=isinstance(exc, (OSError, TimeoutError)),
            )
            self.manifests.sync(db, run)
            return run

    def _read_input(self, db: Session, run: AgentRun, item: AgentRunInput) -> bytes:
        resolved = self.access.resolve_write_access(db, run.owner_wallet_address, item.warehouse_path)
        content = self.access.warehouse_gateway.read_file(run.owner_wallet_address, item.warehouse_path, auth=resolved.auth)
        if len(content) > self.MAX_INPUT_BYTES:
            raise ValueError(f"spreadsheet exceeds M1 limit of {self.MAX_INPUT_BYTES} bytes")
        actual = hashlib.sha256(content).hexdigest()
        if item.sha256 and item.sha256 != actual:
            raise ValueError("spreadsheet checksum changed after run creation")
        item.sha256 = actual
        item.size = len(content)
        manifest_inputs = [dict(manifest_input) for manifest_input in (run.input_manifest_json or [])]
        for manifest_input in manifest_inputs:
            if manifest_input.get("inputKey") == item.input_key:
                manifest_input["sha256"] = actual
                manifest_input["size"] = len(content)
        run.input_manifest_json = manifest_inputs
        self.access.mark_access_success(resolved)
        db.commit()
        return content

    @staticmethod
    def _output_formats(constraints: dict) -> set[str]:
        requested = constraints.get("output_formats") if isinstance(constraints, dict) else None
        if not requested:
            return {"csv", "xlsx", "png"}
        allowed = {"csv", "xlsx", "png"}
        normalized = {str(item).strip().lower() for item in requested}
        unsupported = normalized - allowed - {"markdown"}
        if unsupported:
            raise ValueError(f"unsupported output formats: {', '.join(sorted(unsupported))}")
        return normalized & allowed

    def _profile(self, path: str, content: bytes) -> dict:
        suffix = PurePosixPath(path).suffix.lower()
        if suffix == ".csv":
            return self._profile_csv(content)
        if suffix == ".xlsx":
            return self._profile_xlsx(content)
        raise ValueError("only CSV and XLSX inputs are supported")

    def _load_rows(self, path: str, content: bytes) -> list[dict[str, str]]:
        suffix = PurePosixPath(path).suffix.lower()
        if suffix == ".csv":
            text, dialect, _ = self._decode_csv(content)
            reader = csv.reader(io.StringIO(text), dialect)
            try:
                headers = self._header_names(next(reader))
            except StopIteration:
                return []
            return [self._row_dict(headers, row) for row in reader]
        if suffix == ".xlsx":
            with ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                shared = self._shared_strings(archive) if "xl/sharedStrings.xml" in names else []
                sheet_path = "xl/worksheets/sheet1.xml"
                if sheet_path not in names:
                    return []
                rows = iter(self._xlsx_rows(archive.read(sheet_path), shared))
                try:
                    headers = self._header_names(next(rows))
                except StopIteration:
                    return []
                return [self._row_dict(headers, row) for row in rows]
        return []

    def _profile_csv(self, content: bytes) -> dict:
        text, dialect, encoding = self._decode_csv(content)
        reader = csv.reader(io.StringIO(text), dialect)
        try:
            headers = next(reader)
        except StopIteration as exc:
            raise ValueError("CSV is empty") from exc
        return self._profile_rows(
            reader,
            headers,
            format_name="csv",
            details={"encoding": encoding, "delimiter": dialect.delimiter},
        )

    @staticmethod
    def _decode_csv(content: bytes):
        encoding = "utf-8-sig"
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            encoding = "gb18030"
            try:
                text = content.decode(encoding)
            except UnicodeDecodeError as exc:
                raise ValueError("CSV encoding must be UTF-8 or GB18030 in M1") from exc
        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel
        return text, dialect, encoding

    def _profile_xlsx(self, content: bytes) -> dict:
        try:
            archive = ZipFile(io.BytesIO(content))
        except BadZipFile as exc:
            raise ValueError("XLSX file is invalid") from exc
        with archive:
            names = set(archive.namelist())
            expanded_size = sum(item.file_size for item in archive.infolist())
            if expanded_size > self.MAX_XLSX_EXPANDED_BYTES:
                raise ValueError("XLSX expanded content exceeds the M1 safety limit")
            if "xl/vbaProject.bin" in names:
                raise ValueError("macro-enabled workbooks are not supported")
            if "xl/workbook.xml" not in names:
                raise ValueError("XLSX workbook metadata is missing")
            shared = self._shared_strings(archive) if "xl/sharedStrings.xml" in names else []
            sheets = self._sheet_names(archive)
            profiles = []
            total_rows = 0
            max_columns = 0
            for index, sheet_name in enumerate(sheets, start=1):
                sheet_path = f"xl/worksheets/sheet{index}.xml"
                if sheet_path not in names:
                    continue
                rows = list(self._xlsx_rows(archive.read(sheet_path), shared))
                if not rows:
                    profiles.append({"name": sheet_name, "rowCount": 0, "columnCount": 0, "columns": []})
                    continue
                sheet_profile = self._profile_rows(iter(rows[1:]), rows[0], format_name="xlsx-sheet", details={})
                profiles.append({"name": sheet_name, **{key: sheet_profile[key] for key in ("rowCount", "columnCount", "columns", "sampled")}})
                total_rows += sheet_profile["rowCount"]
                max_columns = max(max_columns, sheet_profile["columnCount"])
            if not profiles:
                raise ValueError("XLSX contains no readable worksheets")
            return {
                "schema": "knowledge.spreadsheet-profile.v1",
                "format": "xlsx",
                "rowCount": total_rows,
                "columnCount": max_columns,
                "sheetCount": len(profiles),
                "sheets": profiles,
                "columns": profiles[0]["columns"],
                "sampled": any(item["sampled"] for item in profiles),
                "limitations": ["M1 reads cached cell values and does not recalculate formulas or execute macros."],
            }

    def _profile_rows(self, rows, headers: list, *, format_name: str, details: dict) -> dict:
        names = self._header_names(headers[: self.MAX_PROFILE_COLUMNS])
        stats = [{"nullCount": 0, "nonNullCount": 0, "samples": [], "types": Counter()} for _ in names]
        row_count = 0
        profiled_row_count = 0
        sampled = False
        for row in rows:
            row_count += 1
            if profiled_row_count >= self.MAX_PROFILE_ROWS:
                sampled = True
                continue
            profiled_row_count += 1
            values = list(row)
            for index, stat in enumerate(stats):
                value = values[index] if index < len(values) else ""
                text = str(value or "").strip()
                if not text:
                    stat["nullCount"] += 1
                    continue
                stat["nonNullCount"] += 1
                stat["types"][self._value_type(text)] += 1
                if len(stat["samples"]) < self.SAMPLE_VALUES and text not in stat["samples"]:
                    stat["samples"].append(text[:200])
        columns = []
        for name, stat in zip(names, stats, strict=True):
            inferred = stat["types"].most_common(1)[0][0] if stat["types"] else "empty"
            columns.append(
                {
                    "name": name,
                    "inferredType": inferred,
                    "nullCount": stat["nullCount"],
                    "nonNullCount": stat["nonNullCount"],
                    "samples": stat["samples"],
                }
            )
        return {
            "schema": "knowledge.spreadsheet-profile.v1",
            "format": format_name,
            "rowCount": row_count,
            "profiledRowCount": profiled_row_count,
            "columnCount": len(names),
            "columns": columns,
            "sampled": sampled,
            **details,
        }

    @staticmethod
    def _header_names(headers: list) -> list[str]:
        names = []
        counts = Counter()
        for index, value in enumerate(headers):
            base = str(value or "").strip() or f"column_{index + 1}"
            counts[base] += 1
            names.append(base if counts[base] == 1 else f"{base}_{counts[base]}")
        return names

    @staticmethod
    def _row_dict(headers: list[str], row) -> dict[str, str]:
        values = list(row)
        return {header: str(values[index] if index < len(values) else "") for index, header in enumerate(headers)}

    @staticmethod
    def _value_type(value: str) -> str:
        lowered = value.lower()
        if lowered in {"true", "false", "yes", "no"}:
            return "boolean"
        try:
            int(value)
            return "integer"
        except ValueError:
            pass
        try:
            float(value.replace(",", ""))
            return "number"
        except ValueError:
            return "string"

    @staticmethod
    def _shared_strings(archive: ZipFile) -> list[str]:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        return ["".join(node.itertext()) for node in root.findall("x:si", namespace)]

    @staticmethod
    def _sheet_names(archive: ZipFile) -> list[str]:
        root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        return [node.attrib.get("name", f"Sheet{index + 1}") for index, node in enumerate(root.findall("x:sheets/x:sheet", namespace))]

    @staticmethod
    def _xlsx_rows(payload: bytes, shared: list[str]):
        root = ElementTree.fromstring(payload)
        namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        for row in root.findall(".//x:sheetData/x:row", namespace):
            values = []
            for cell in row.findall("x:c", namespace):
                cell_type = cell.attrib.get("t", "")
                value = cell.findtext("x:v", default="", namespaces=namespace)
                if cell_type == "s" and value.isdigit() and int(value) < len(shared):
                    value = shared[int(value)]
                elif cell_type == "inlineStr":
                    inline = cell.find("x:is", namespace)
                    value = "".join(inline.itertext()) if inline is not None else ""
                values.append(value)
            yield values

    @staticmethod
    def _summary(run: AgentRun, profile: dict) -> str:
        intent = str((run.metadata_json or {}).get("intent") or "").strip()
        lines = [
            "# 表格分析摘要",
            "",
            f"- 格式：{profile['format']}",
            f"- 已读取行数：{profile['rowCount']}",
            f"- 列数：{profile['columnCount']}",
            f"- 是否截断采样：{'是' if profile['sampled'] else '否'}",
        ]
        if intent:
            lines.extend([f"- 用户目标：{intent}"])
        analysis = profile.get("analysis") or {}
        if analysis:
            lines.extend([f"- 分析模式：{analysis.get('mode')}", f"- 结果行数：{analysis.get('resultRowCount')}"])
        lines.extend(["", "## 字段概览", ""])
        for column in profile.get("columns", [])[:30]:
            lines.append(
                f"- `{column['name']}`：{column['inferredType']}，非空 {column['nonNullCount']}，空值 {column['nullCount']}"
            )
        lines.extend(["", "> M1 当前提供结构识别与数据质量概览；复杂聚合、图表和模型解释将在后续迭代扩展。", ""])
        return "\n".join(lines)

    @staticmethod
    def _error(exc: Exception) -> str:
        return (str(exc).strip() or exc.__class__.__name__)[:500]
