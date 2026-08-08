from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THIRD_PARTY = ROOT / "knowledge" / "third_party"


def test_vendored_sources_are_tracked() -> None:
    sources = THIRD_PARTY / "SOURCES.md"

    assert sources.exists()
    text = sources.read_text(encoding="utf-8")
    assert "https://github.com/infiniflow/ragflow.git" in text
    assert "2d63ad654dd8a44e5aaf17ca6fc819bd7720027a" in text
    assert "5200dade0709f926f15309dbe48b1e43e680c202" in text
    assert (THIRD_PARTY / "ragflow" / "LICENSE").exists()
    assert (THIRD_PARTY / "connectors" / "LICENSE").exists()


def test_enterprise_connector_code_is_not_vendored() -> None:
    forbidden = [path for path in THIRD_PARTY.rglob("*") if "ee" in path.parts]

    assert forbidden == []
