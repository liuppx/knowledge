from __future__ import annotations

import csv
import io

import pytest

from knowledge.services.spreadsheet_plan import SpreadsheetPlanService


def test_plan_filters_selects_sorts_and_limits_rows():
    service = SpreadsheetPlanService()
    plan = service.build(
        "筛选大额订单",
        {
            "analysis_plan": {
                "select": ["order_id", "amount"],
                "filters": [{"column": "amount", "operator": "gte", "value": 20}],
                "sort": [{"column": "amount", "direction": "desc"}],
                "limit": 2,
            }
        },
        ["order_id", "amount", "note"],
    )
    result = service.execute(
        [
            {"order_id": "A", "amount": "10", "note": "small"},
            {"order_id": "B", "amount": "30", "note": "large"},
            {"order_id": "C", "amount": "20", "note": "medium"},
        ],
        plan,
    )
    assert plan["mode"] == "table"
    assert result == [{"order_id": "B", "amount": "30"}, {"order_id": "C", "amount": "20"}]


def test_plan_rejects_unknown_columns_and_non_numeric_aggregation():
    service = SpreadsheetPlanService()
    with pytest.raises(ValueError, match="unknown column"):
        service.build("", {"analysis_plan": {"group_by": ["missing"]}}, ["region", "amount"])

    plan = service.build(
        "",
        {"analysis_plan": {"aggregations": [{"column": "amount", "op": "sum", "alias": "total"}]}},
        ["amount"],
    )
    with pytest.raises(ValueError, match="requires numeric values"):
        service.execute([{"amount": "not-a-number"}], plan)


def test_result_csv_escapes_spreadsheet_formulas():
    content = SpreadsheetPlanService.to_csv([{"name": "=HYPERLINK(\"bad\")", "amount": "-10"}], ["name", "amount"])
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    assert rows == [["name", "amount"], ["'=HYPERLINK(\"bad\")", "'-10"]]
