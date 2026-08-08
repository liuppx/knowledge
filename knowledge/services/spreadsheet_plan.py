from __future__ import annotations

import csv
import io
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any


class SpreadsheetPlanService:
    FILTER_OPERATORS = {"eq", "ne", "gt", "gte", "lt", "lte", "contains", "in", "is_null", "not_null"}
    AGGREGATIONS = {"count", "sum", "avg", "min", "max"}
    SORT_DIRECTIONS = {"asc", "desc"}
    MAX_FILTERS = 20
    MAX_GROUP_COLUMNS = 5
    MAX_AGGREGATIONS = 20
    MAX_RESULT_ROWS = 10_000

    def build(self, intent: str, constraints: dict, columns: list[str]) -> dict:
        raw = constraints.get("analysis_plan") if isinstance(constraints, dict) else None
        raw = raw if isinstance(raw, dict) else {}
        known = set(columns)
        filters = self._filters(raw.get("filters"), known)
        group_by = self._columns(raw.get("group_by"), known, self.MAX_GROUP_COLUMNS, "group_by")
        aggregations = self._aggregations(raw.get("aggregations"), known)
        select = self._columns(raw.get("select"), known, len(columns), "select")
        sort = self._sort(raw.get("sort"), known | {item["alias"] for item in aggregations})
        limit = min(self.MAX_RESULT_ROWS, max(1, int(raw.get("limit") or 1000)))
        if group_by and not aggregations:
            aggregations = [{"column": "*", "op": "count", "alias": "row_count"}]
        if aggregations and not group_by and any(item["op"] != "count" for item in aggregations):
            mode = "aggregate"
        elif aggregations or group_by:
            mode = "group_aggregate"
        elif filters or select or sort:
            mode = "table"
        else:
            mode = "profile_only"
        return {
            "schema": "knowledge.spreadsheet-analysis-plan.v1",
            "intent": str(intent or "")[:2000],
            "mode": mode,
            "select": select,
            "filters": filters,
            "groupBy": group_by,
            "aggregations": aggregations,
            "sort": sort,
            "limit": limit,
        }

    def execute(self, rows: list[dict[str, str]], plan: dict) -> list[dict[str, Any]]:
        filtered = [row for row in rows if all(self._matches(row, item) for item in plan["filters"])]
        if plan["aggregations"] or plan["groupBy"]:
            result = self._aggregate(filtered, plan["groupBy"], plan["aggregations"])
        else:
            selected = plan["select"] or (list(rows[0]) if rows else [])
            result = [{column: row.get(column, "") for column in selected} for row in filtered]
        for item in reversed(plan["sort"]):
            result.sort(key=lambda row: self._sort_key(row.get(item["column"])), reverse=item["direction"] == "desc")
        return result[: plan["limit"]]

    @staticmethod
    def to_csv(rows: list[dict[str, Any]], fallback_columns: list[str]) -> bytes:
        output = io.StringIO(newline="")
        columns = list(rows[0]) if rows else fallback_columns
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: SpreadsheetPlanService._safe_csv_value(row.get(column, "")) for column in columns})
        return output.getvalue().encode("utf-8-sig")

    def _filters(self, value, known: set[str]) -> list[dict]:
        items = value if isinstance(value, list) else []
        if len(items) > self.MAX_FILTERS:
            raise ValueError(f"analysis_plan.filters supports at most {self.MAX_FILTERS} items")
        normalized = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"analysis_plan.filters[{index}] must be an object")
            column = str(item.get("column") or "")
            operator = str(item.get("operator") or "eq").lower()
            if column not in known:
                raise ValueError(f"analysis_plan.filters[{index}].column is unknown: {column}")
            if operator not in self.FILTER_OPERATORS:
                raise ValueError(f"analysis_plan.filters[{index}].operator is invalid")
            expected = item.get("value")
            if operator == "in" and not isinstance(expected, list):
                raise ValueError(f"analysis_plan.filters[{index}].value must be an array for in")
            normalized.append({"column": column, "operator": operator, "value": expected})
        return normalized

    @staticmethod
    def _columns(value, known: set[str], limit: int, label: str) -> list[str]:
        items = value if isinstance(value, list) else []
        if len(items) > limit:
            raise ValueError(f"analysis_plan.{label} has too many columns")
        result = []
        for item in items:
            column = str(item or "")
            if column not in known:
                raise ValueError(f"analysis_plan.{label} contains unknown column: {column}")
            if column not in result:
                result.append(column)
        return result

    def _aggregations(self, value, known: set[str]) -> list[dict]:
        items = value if isinstance(value, list) else []
        if len(items) > self.MAX_AGGREGATIONS:
            raise ValueError(f"analysis_plan.aggregations supports at most {self.MAX_AGGREGATIONS} items")
        result = []
        aliases = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"analysis_plan.aggregations[{index}] must be an object")
            op = str(item.get("op") or "").lower()
            column = str(item.get("column") or "")
            if op not in self.AGGREGATIONS:
                raise ValueError(f"analysis_plan.aggregations[{index}].op is invalid")
            if column != "*" and column not in known:
                raise ValueError(f"analysis_plan.aggregations[{index}].column is unknown: {column}")
            if column == "*" and op != "count":
                raise ValueError("only count supports column '*'")
            alias = str(item.get("alias") or f"{op}_{'rows' if column == '*' else column}")[:128]
            if not alias or alias in aliases or alias in known:
                raise ValueError(f"analysis_plan.aggregations[{index}].alias is invalid or duplicated")
            aliases.add(alias)
            result.append({"column": column, "op": op, "alias": alias})
        return result

    def _sort(self, value, known: set[str]) -> list[dict]:
        items = value if isinstance(value, list) else []
        result = []
        for index, item in enumerate(items[:10]):
            if not isinstance(item, dict):
                raise ValueError(f"analysis_plan.sort[{index}] must be an object")
            column = str(item.get("column") or "")
            direction = str(item.get("direction") or "asc").lower()
            if column not in known or direction not in self.SORT_DIRECTIONS:
                raise ValueError(f"analysis_plan.sort[{index}] is invalid")
            result.append({"column": column, "direction": direction})
        return result

    def _aggregate(self, rows: list[dict[str, str]], group_by: list[str], aggregations: list[dict]) -> list[dict[str, Any]]:
        groups: dict[tuple, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            groups[tuple(row.get(column, "") for column in group_by)].append(row)
        if not group_by and not groups:
            groups[()] = []
        result = []
        for key, members in groups.items():
            output = {column: key[index] for index, column in enumerate(group_by)}
            for aggregation in aggregations:
                output[aggregation["alias"]] = self._aggregate_value(members, aggregation["column"], aggregation["op"])
            result.append(output)
        return result

    @staticmethod
    def _aggregate_value(rows: list[dict[str, str]], column: str, op: str):
        values = [row.get(column, "") for row in rows] if column != "*" else []
        non_empty = [value for value in values if str(value).strip()]
        if op == "count":
            return len(rows) if column == "*" else len(non_empty)
        decimals = []
        for value in non_empty:
            try:
                decimals.append(Decimal(str(value).replace(",", "")))
            except InvalidOperation as exc:
                raise ValueError(f"aggregation {op} requires numeric values in column {column}") from exc
        if not decimals:
            return ""
        if op == "sum":
            value = sum(decimals, Decimal(0))
        elif op == "avg":
            value = sum(decimals, Decimal(0)) / len(decimals)
        elif op == "min":
            value = min(decimals)
        else:
            value = max(decimals)
        return format(value.normalize(), "f")

    @staticmethod
    def _matches(row: dict[str, str], item: dict) -> bool:
        actual = str(row.get(item["column"], ""))
        expected = item.get("value")
        operator = item["operator"]
        if operator == "is_null":
            return not actual.strip()
        if operator == "not_null":
            return bool(actual.strip())
        if operator == "contains":
            return str(expected or "").lower() in actual.lower()
        if operator == "in":
            return actual in {str(value) for value in expected}
        if operator in {"eq", "ne"}:
            matched = actual == str(expected if expected is not None else "")
            return matched if operator == "eq" else not matched
        left, right = SpreadsheetPlanService._comparable(actual), SpreadsheetPlanService._comparable(expected)
        return {"gt": left > right, "gte": left >= right, "lt": left < right, "lte": left <= right}[operator]

    @staticmethod
    def _comparable(value):
        try:
            return (0, Decimal(str(value).replace(",", "")))
        except InvalidOperation:
            return (1, str(value))

    @staticmethod
    def _sort_key(value):
        return SpreadsheetPlanService._comparable(value)

    @staticmethod
    def _safe_csv_value(value):
        text = str(value if value is not None else "")
        return "'" + text if text.startswith(("=", "+", "-", "@")) else text
