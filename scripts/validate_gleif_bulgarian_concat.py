#!/usr/bin/env python3
"""Scan a downloaded GLEIF Concatenated LEI-CDF ZIP for Bulgarian UIC matches."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, BinaryIO
from xml.sax import ContentHandler, make_parser
from xml.sax.handler import feature_external_ges, feature_namespaces


ARCHIVE_SHA256 = "23c03705b3f93dd9869af2c9366f1bc191640ac1fd0759e615ff768fc2d09af6"
SOURCE_URL = "https://leidata.gleif.org/api/v1/concatenated-files/lei2/get/42569/zip"
EXTRACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "validation"
    / "ontology-v1"
    / "public-study"
    / "bulgarian_commercial_register_extract_v1.json"
)
def _normalize_name(value: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", str(value or "").casefold(), flags=re.UNICODE))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class _GLEIFScan(ContentHandler):
    def __init__(self, targets: dict[str, dict[str, str]]) -> None:
        super().__init__()
        self.targets = targets
        self.path: list[str] = []
        self.record: dict[str, Any] | None = None
        self.field: str | None = None
        self.value: list[str] = []
        self.content_date = ""
        self.record_count = 0
        self.records_scanned = 0
        self.bg_legal_address_records = 0
        self.ra000065_records = 0
        self.uic_hits: dict[str, list[dict[str, str]]] = {
            uic: [] for uic in targets
        }
        self.name_hits: dict[str, list[dict[str, str]]] = {
            uic: [] for uic in targets
        }

    @staticmethod
    def _local_name(name: str) -> str:
        return name.rsplit(":", 1)[-1]

    def startElement(self, name: str, attrs: Any) -> None:
        tag = self._local_name(name)
        self.path.append(tag)
        parent = self.path[-2] if len(self.path) > 1 else ""
        if tag == "LEIRecord":
            self.record = {}
            return

        if self.record is None:
            if parent == "LEIHeader" and tag in {"ContentDate", "RecordCount"}:
                self.field = tag
                self.value = []
            return

        entity_scope = "Entity" in self.path and "Registration" not in self.path
        capture = (
            (tag == "LEI" and parent == "LEIRecord")
            or (tag == "LegalName" and parent == "Entity")
            or (tag == "OtherEntityName" and parent == "OtherEntityNames")
            or (tag == "Country" and parent == "LegalAddress" and entity_scope)
            or (
                tag in {"RegistrationAuthorityID", "RegistrationAuthorityEntityID"}
                and parent == "RegistrationAuthority"
                and entity_scope
            )
        )
        if capture:
            self.field = tag
            self.value = []

    def characters(self, content: str) -> None:
        if self.field is not None:
            self.value.append(content)

    def endElement(self, name: str) -> None:
        tag = self._local_name(name)
        if self.field == tag:
            text = "".join(self.value).strip()
            if self.record is None:
                if tag == "ContentDate":
                    self.content_date = text
                elif tag == "RecordCount":
                    self.record_count = int(text)
            else:
                if tag == "OtherEntityName":
                    self.record.setdefault(tag, []).append(text)
                else:
                    self.record[tag] = text
            self.field = None
            self.value = []

        if tag == "LEIRecord" and self.record is not None:
            self._accept_record(self.record)
            self.record = None
        self.path.pop()

    def _accept_record(self, record: dict[str, Any]) -> None:
        self.records_scanned += 1
        country = record.get("Country", "")
        authority_id = record.get("RegistrationAuthorityID", "")
        registry_id = record.get("RegistrationAuthorityEntityID", "")
        legal_name = record.get("LegalName", "")
        if country == "BG":
            self.bg_legal_address_records += 1
        if authority_id == "RA000065":
            self.ra000065_records += 1
        evidence = {
            "lei": record.get("LEI", ""),
            "legal_name": legal_name,
            "other_entity_names": sorted(set(record.get("OtherEntityName", []))),
            "registry_authority_id": authority_id,
            "registry_entity_id": registry_id,
        }
        if registry_id in self.targets:
            self.uic_hits[registry_id].append(evidence)
        record_names = [legal_name, *record.get("OtherEntityName", [])]
        for uic, target in self.targets.items():
            if _normalize_name(target["ted_name"]) in {
                _normalize_name(name) for name in record_names
            }:
                self.name_hits[uic].append(evidence)


def scan_xml_stream(
    stream: BinaryIO, targets: dict[str, dict[str, str]]
) -> dict[str, Any]:
    handler = _GLEIFScan(targets)
    parser = make_parser()
    parser.setFeature(feature_namespaces, False)
    parser.setFeature(feature_external_ges, False)
    parser.setContentHandler(handler)
    parser.parse(stream)
    if handler.record_count != handler.records_scanned:
        raise ValueError(
            "LEI-CDF record count mismatch: header says "
            f"{handler.record_count}, scanned {handler.records_scanned}"
        )
    return {
        "xml_content_date": handler.content_date,
        "xml_record_count": handler.record_count,
        "records_scanned": handler.records_scanned,
        "bg_legal_address_records": handler.bg_legal_address_records,
        "ra000065_records": handler.ra000065_records,
        "target_uic_hits": handler.uic_hits,
        "target_exact_name_or_alias_hits": handler.name_hits,
    }


def scan_archive(archive: Path, expected_sha256: str = ARCHIVE_SHA256) -> dict[str, Any]:
    archive_hash = _sha256_file(archive)
    if expected_sha256 and archive_hash != expected_sha256:
        raise ValueError(
            f"archive SHA-256 mismatch: expected {expected_sha256}, got {archive_hash}"
        )
    source = json.loads(EXTRACT_PATH.read_text(encoding="utf-8"))
    targets = {item["uic"]: item for item in source["records"]}
    with zipfile.ZipFile(archive) as zipped:
        members = [item for item in zipped.infolist() if item.filename.endswith(".xml")]
        if len(members) != 1:
            raise ValueError(f"expected one XML member in archive, found {len(members)}")
        with zipped.open(members[0]) as stream:
            parsed = scan_xml_stream(stream, targets)
    summary = {
        "source_url": SOURCE_URL,
        "archive_sha256": archive_hash,
        "archive_member": members[0].filename,
        "targets": targets,
        **parsed,
    }
    summary["summary_sha256"] = _canonical_sha256(summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        summary = scan_archive(args.archive)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"GLEIF scan failed: {exc}", file=sys.stderr)
        return 1
    output = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
