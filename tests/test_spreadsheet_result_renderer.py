from __future__ import annotations

import io

from openpyxl import load_workbook
from PIL import Image

from knowledge.services.spreadsheet_result_renderer import SpreadsheetResultRenderer


def test_result_xlsx_has_stable_table_and_formula_protection():
    renderer = SpreadsheetResultRenderer()
    content = renderer.to_xlsx(
        [
            {"region": "east", "total": "42", "note": '=HYPERLINK("bad")'},
            {"region": "west", "total": "18", "note": "ok"},
        ],
        [],
        {"aggregations": [{"column": "amount", "op": "sum", "alias": "total"}]},
    )
    workbook = load_workbook(io.BytesIO(content), data_only=False)
    sheet = workbook["Result"]
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref == "A1:C3"
    assert [cell.value for cell in sheet[1]] == ["region", "total", "note"]
    assert sheet["B2"].value == 42
    assert sheet["C2"].value == "'=HYPERLINK(\"bad\")"
    assert sheet["C2"].data_type != "f"


def test_result_chart_is_png_with_stable_dimensions_and_metadata():
    renderer = SpreadsheetResultRenderer()
    rendered = renderer.chart(
        [{"region": "east", "total": "42"}, {"region": "west", "total": "18"}],
        {
            "groupBy": ["region"],
            "aggregations": [{"column": "amount", "op": "sum", "alias": "total"}],
        },
    )
    assert rendered is not None
    content, metadata = rendered
    image = Image.open(io.BytesIO(content))
    assert image.format == "PNG"
    assert image.size == (1000, 600)
    assert metadata == {
        "chartType": "bar",
        "labelColumn": "region",
        "valueColumn": "total",
        "itemCount": 2,
        "truncated": False,
    }


def test_result_chart_is_not_created_for_plain_table():
    assert SpreadsheetResultRenderer().chart(
        [{"region": "east"}],
        {"groupBy": [], "aggregations": []},
    ) is None
