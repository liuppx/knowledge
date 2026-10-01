"""Product acceptance run for docs/产品验证知识库.md §5/§6 using the 11 real documents.

Drives the real HTTP surface (in-process ASGI by default, or --base-url for a
running server) through the whole product loop with the mock Warehouse gateway
and mock model provider:

  login → warehouse credentials → KB → upload 11 docs → bind → import task →
  documents visible → source scan → evidence → candidates → accept → items with
  evidence links → publish → search-lab Q01–Q12 → service principal + grant →
  /service/search as a consumer → second-KB isolation check

Prints a Markdown report and writes it to .eval/acceptance_report.md. Exit code
is non-zero when a §6 pass condition fails.

Usage:
  .venv/bin/python scripts/product_acceptance.py            # in-process, knowledge_test DB
  .venv/bin/python scripts/product_acceptance.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CORPUS_DIR_NAME = "handbook"
CORPUS_FILES = [
    "README.md",
    "知识库架构V1.md",
    "社区产品关系与开发边界.md",
    "Agent运行与上下文资产设计.md",
    "API接入文档.md",
    "控制台操作手册.md",
    "控制面API文档.md",
    "Bot与Chat知识库重构PRD.md",
    "Warehouse鉴权与绑定重构说明.md",
    "Warehouse凭证使用说明.md",
    "Worker部署与扩缩容建议.md",
]
ACTIVE = {"pending", "running", "cancel_requested"}


def _configure_env(args: argparse.Namespace) -> None:
    if args.base_url:
        return
    os.environ["DATABASE_URL"] = args.database_url
    os.environ.setdefault("WAREHOUSE_GATEWAY_MODE", "mock")
    os.environ.setdefault("WAREHOUSE_MOCK_ROOT", str(Path("/tmp/knowledge_acceptance/mock_warehouse")))
    os.environ.setdefault("MODEL_PROVIDER_MODE", "mock")
    os.environ.setdefault("VECTOR_STORE_MODE", "db")
    os.environ.setdefault("APP_ENV", "development")


class Client:
    """Thin wrapper so the same steps run in-process or against a live server."""

    def __init__(self, base_url: str | None) -> None:
        if base_url:
            import httpx

            self._client = httpx.Client(base_url=base_url, timeout=120)
        else:
            from fastapi.testclient import TestClient

            from knowledge.main import app

            self._client = TestClient(app)
            self._client.__enter__()
        self.headers: dict[str, str] = {}

    def request(self, method: str, path: str, *, expect: int | tuple[int, ...] = 200, headers: dict | None = None, **kwargs):
        response = self._client.request(method, path, headers={**self.headers, **(headers or {})}, **kwargs)
        allowed = expect if isinstance(expect, tuple) else (expect,)
        if response.status_code not in allowed:
            raise RuntimeError(f"{method} {path} -> {response.status_code}: {response.text[:400]}")
        return response.json() if response.content else None

    def get(self, path: str, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.request("POST", path, **kwargs)


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.checks: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append((name, ok, detail))
        return ok

    def section(self, title: str) -> None:
        self.lines += ["", f"### {title}", ""]

    def line(self, text: str = "") -> None:
        self.lines.append(text)


def login(client: Client) -> str:
    from eth_account import Account
    from eth_account.messages import encode_defunct

    account = Account.create()
    challenge = client.post("/auth/challenge", json={"wallet_address": account.address})
    signed = Account.sign_message(encode_defunct(text=challenge["message"]), account.key)
    token = client.post("/auth/verify", json={"wallet_address": account.address, "signature": signed.signature.hex()})
    client.headers = {"Authorization": f"Bearer {token['access_token']}"}
    return account.address


def wait_task(client: Client, task_id: int, report: Report, attempts: int = 60) -> dict:
    task: dict = {}
    for _ in range(attempts):
        task = client.get(f"/tasks/{task_id}")
        if task["status"] not in ACTIVE:
            return task
        # No resident worker in the acceptance environment: drive the queue by hand.
        client.post("/tasks/process-pending")
        time.sleep(0.2)
    report.line(f"- task #{task_id} still {task.get('status')} after {attempts} rounds")
    return task


def run(args: argparse.Namespace) -> int:
    _configure_env(args)
    from knowledge.services.warehouse_scope import warehouse_app_path

    from tests.eval.dataset import DOCS, QUESTIONS

    report = Report()
    client = Client(args.base_url)
    started = time.time()

    report.section("环境")
    wallet = login(client)
    report.line(f"- 钱包：`{wallet}`")
    report.line(f"- 模式：{'live ' + args.base_url if args.base_url else 'in-process (TestClient)'} · warehouse={os.environ.get('WAREHOUSE_GATEWAY_MODE', 'env')} · model={os.environ.get('MODEL_PROVIDER_MODE', 'env')}")

    # Warehouse credentials (mock gateway accepts any key pair).
    root = warehouse_app_path("")
    write = client.post("/warehouse/credentials/write", json={"key_id": "ak_acceptance_write", "key_secret": "sk_w", "root_path": root})
    read = client.post("/warehouse/credentials/read", json={"key_id": "ak_acceptance_read", "key_secret": "sk_r", "root_path": root})
    status = client.get("/warehouse/status")
    report.check("Warehouse 凭证就绪", bool(status["credentials_ready"]), f"write #{write['id']}, read #{read['id']}")

    # KB.
    kb = client.post("/kbs", json={"name": "Knowledge Product Handbook", "description": "产品验证知识库（验收运行）"})
    kb_id = kb["id"]
    report.line(f"- 知识库 #{kb_id} `{kb['name']}`")

    # Upload the 11 documents.
    report.section("§6.1/§6.2 导入与文档可见")
    target_dir = warehouse_app_path(CORPUS_DIR_NAME)
    uploaded = 0
    for name in CORPUS_FILES:
        content = (REPO_ROOT / "docs" / name).read_bytes()
        client.post("/warehouse/upload", data={"target_dir": target_dir}, files={"file": (name, content, "text/markdown")})
        uploaded += 1
    report.check("11 篇文档上传成功", uploaded == len(CORPUS_FILES), f"{uploaded}/{len(CORPUS_FILES)} → {target_dir}")

    binding = client.post(f"/kbs/{kb_id}/bindings", json={"source_path": target_dir, "scope_type": "directory", "credential_id": read["id"]})
    task = client.post(f"/kbs/{kb_id}/tasks/import-from-bindings", json={"binding_ids": [binding["id"]]})
    task = wait_task(client, task["id"], report)
    items = client.get(f"/tasks/{task['id']}/items")
    report.line(f"- 导入任务 #{task['id']} 状态 `{task['status']}`，文件明细 {len(items)} 条：" + ", ".join(sorted({str(item['status']) for item in items})))
    documents = client.get(f"/kbs/{kb_id}/documents")
    names = {doc["source_file_name"] for doc in documents}
    missing = [name for name in CORPUS_FILES if name not in names]
    report.check("11 篇文档全部导入，无静默跳过", task["status"] == "succeeded" and not missing, f"documents={len(documents)} missing={missing}")
    report.check("文档列表显示文件级状态与 chunk 数", all(doc["parse_status"] and doc["chunk_count"] > 0 for doc in documents) and bool(documents), f"chunks={sum(doc['chunk_count'] for doc in documents)}")
    bindings = client.get(f"/kbs/{kb_id}/bindings")
    report.line(f"- 绑定 sync_status `{bindings[0]['sync_status']}` · document_count {bindings[0]['document_count']}")

    # Evidence → candidates → items.
    report.section("知识生产：Evidence → 候选 → 正式知识项")
    source = client.post(f"/kbs/{kb_id}/sources", json={"source_type": "warehouse", "source_path": target_dir, "scope_type": "directory"})
    scan = client.post(f"/kbs/{kb_id}/sources/{source['id']}/scan")
    build = client.post(f"/kbs/{kb_id}/sources/{source['id']}/build-evidence")
    evidence = client.get(f"/kbs/{kb_id}/evidence", params={"source_id": source["id"]})
    report.line(f"- 扫描资产 {scan['stats']['total_assets']}，构建 Evidence {build['built_evidence_count']}（处理 {build['processed_asset_count']} 资产），Evidence 总数 {len(evidence)}")
    report.check("Evidence 构建成功", len(evidence) > 0 and not build.get("failed_asset_ids"))
    generated = client.post(f"/kbs/{kb_id}/sources/{source['id']}/generate-candidates")
    candidates = [candidate for candidate in client.get(f"/kbs/{kb_id}/candidates") if candidate["review_status"] == "pending_review"]
    report.line(f"- 生成候选 {generated['created_count']}（复用 {generated['reused_count']}），待审核 {len(candidates)}")
    accepted = 0
    for candidate in candidates[: args.max_accept]:
        client.post(f"/kbs/{kb_id}/candidates/{candidate['id']}/accept", json={})
        accepted += 1
    items_list = client.get(f"/kbs/{kb_id}/items")
    report.line(f"- 接受候选 {accepted} 条 → 正式知识项 {len(items_list)}")
    report.check("候选可接受为正式知识项", accepted > 0 and len(items_list) >= accepted)
    without_evidence = [item["id"] for item in items_list if not item.get("evidence_count")]
    report.check("§6.5 每个正式知识项可回查至少一个 Evidence", bool(items_list) and not without_evidence, f"缺证据链的知识项: {without_evidence[:10]}")
    if items_list:
        detail = client.get(f"/kbs/{kb_id}/items/{items_list[0]['id']}")
        links = detail["current_revision"]["evidence_links"] if detail.get("current_revision") else []
        report.line(f"- 抽查知识项 #{items_list[0]['id']}「{items_list[0].get('title')}」：修订 #{items_list[0].get('revision_no')}，evidence_links {len(links)}")

    # Publish.
    report.section("发布")
    release = client.post(f"/kbs/{kb_id}/releases", json={"version": time.strftime("%Y.%m.%d-acceptance"), "release_note": "产品验收运行"})
    current = client.get(f"/kbs/{kb_id}/releases/current")
    report.check("发布成功且成为当前版本", current["release"]["id"] == release["release"]["id"], f"{release['release']['version']} · {len(release['items'])} 个知识项")

    # Search lab Q01–Q12.
    report.section("§6.3 Q01–Q12 检索（search-lab，top_k=6）")
    report.line("| ID | 类型 | formal_first 命中 | 预期来源命中 | Top1 |")
    report.line("| --- | --- | --- | --- | --- |")
    hits_on_expected = 0
    scored = 0
    for question in QUESTIONS:
        expected_files = {DOCS[key]["file"] for key in question["expected"] if DOCS[key]["file"] in CORPUS_FILES}
        compare = client.post(f"/kbs/{kb_id}/search-lab/compare", json={"query": question["query"], "top_k": 6, "result_view": "audit", "availability_mode": "allow_all"})
        hits = compare["formal_first"]["hits"]
        files_hit: list[str] = []
        for hit in hits:
            for ref in hit.get("source_refs") or []:
                files_hit.append(Path(ref).name)
            for summary in hit.get("evidence_summaries") or []:
                files_hit.append(Path(summary.get("source_ref", "")).name)
        matched = sorted(expected_files & set(files_hit))
        top = hits[0] if hits else None
        top_label = (top.get("title") or (top.get("text") or "")[:40]) if top else "—"
        if question["expected"]:
            scored += 1
            if matched:
                hits_on_expected += 1
            cell = f"✅ {', '.join(matched)}" if matched else f"❌ 期望 {', '.join(sorted(expected_files)) or '—'}"
        else:
            cell = f"ℹ️ 无金标；命中 {', '.join(sorted(set(files_hit))[:3]) or '∅'}"
        report.line(f"| {question['id']} | {question['kind']} | {len(hits)} | {cell} | {top_label} |")
    report.check("Q01–Q11 至少 9 题命中预期来源（检索层）", hits_on_expected >= 9, f"{hits_on_expected}/{scored}")
    logs = client.get(f"/kbs/{kb_id}/retrieval-logs", params={"limit": 5})
    trace = logs[0]["trace_json"] if logs else {}
    report.line(f"- 检索日志 {len(logs)} 条（最近一条 trace keys: {sorted(trace.keys())[:8]}）")

    # Consumer path: principal + grant + /service/search.
    report.section("消费方契约：Service Principal → Grant → /service/search")
    principal = client.post("/service-principals", json={"service_id": "acceptance.chat", "display_name": "Acceptance Chat", "identity_type": "api_key"})
    grant = client.post(f"/kbs/{kb_id}/grants", json={"service_principal_id": principal["principal"]["id"], "release_selection_mode": "latest_published", "default_result_mode": "referenced"})
    service_headers = {"X-Service-Api-Key": principal["api_key"]}
    service = client.request("POST", "/service/search", headers=service_headers, json={"kb_id": kb_id, "query": QUESTIONS[0]["query"], "top_k": 5}, expect=(200, 401, 403))
    ok = isinstance(service, dict) and "hits" in service
    report.check("消费方可用 API Key 经授权检索", ok, f"grant #{grant['id']} · hits={len(service['hits']) if ok else service}")

    # KB isolation.
    report.section("§6.6 知识库切换不串库")
    other = client.post("/kbs", json={"name": "Acceptance Empty KB", "description": ""})
    other_docs = client.get(f"/kbs/{other['id']}/documents")
    other_items = client.get(f"/kbs/{other['id']}/items")
    other_search = client.post(f"/kbs/{other['id']}/search-lab/compare", json={"query": QUESTIONS[0]["query"], "top_k": 6, "result_view": "compact", "availability_mode": "allow_all"})
    isolated = not other_docs and not other_items and not other_search["formal_first"]["hits"]
    report.check("空知识库看不到另一个知识库的数据", isolated, f"docs={len(other_docs)} items={len(other_items)} hits={len(other_search['formal_first']['hits'])}")
    client.request("DELETE", f"/kbs/{other['id']}")
    if not args.keep:
        client.request("DELETE", f"/kbs/{kb_id}")

    # Summary.
    passed = sum(1 for _, ok, _ in report.checks if ok)
    header = [
        "## 产品验收运行报告",
        "",
        f"- 时间：{time.strftime('%Y-%m-%d %H:%M:%S')} · 耗时 {time.time() - started:.1f}s",
        f"- 结果：**{passed}/{len(report.checks)} 项通过**",
        "",
        "| 检查 | 结果 | 说明 |",
        "| --- | --- | --- |",
    ] + [f"| {name} | {'✅' if ok else '❌'} | {detail} |" for name, ok, detail in report.checks]
    text = "\n".join(header + report.lines) + "\n"
    out = REPO_ROOT / ".eval" / "acceptance_report.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"written: {out}")
    return 0 if passed == len(report.checks) else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="", help="run against a live server instead of in-process")
    parser.add_argument("--database-url", default=os.environ.get("TEST_DATABASE_URL", "postgresql://knowledge:knowledge@127.0.0.1:5432/knowledge_test?gssencmode=disable"))
    parser.add_argument("--max-accept", type=int, default=200, help="cap on candidates accepted")
    parser.add_argument("--keep", action="store_true", help="keep the acceptance KB instead of deleting it")
    sys.exit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
