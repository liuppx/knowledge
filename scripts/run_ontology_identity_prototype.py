#!/usr/bin/env python3
"""Run a synthetic, in-memory identity-review walkthrough."""

from __future__ import annotations

import json

from knowledge.ontology.identity_prototype import (
    EvidenceReference,
    IdentityPrototype,
    IdentityRole,
    IdentityStatus,
)


def evidence(record: str) -> EvidenceReference:
    return EvidenceReference(
        uri=f"https://example.test/registry/{record}",
        source_version="synthetic-2026-10",
        locator=f"record/{record}",
        checksum="0" * 64,
    )


def main() -> int:
    prototype = IdentityPrototype(
        {
            "reviewer-a": IdentityRole.REVIEWER,
            "reviewer-b": IdentityRole.REVIEWER,
        }
    )
    identifier_owner = prototype.create_object(
        "organization", "Example Authority Ltd", created_by="reviewer-a", evidence=evidence("org-1")
    )
    prototype.add_identifier(
        identifier_owner.id,
        "TED:buyer",
        "buyer-001",
        evidence=evidence("ted-buyer-001"),
        registered_by="reviewer-a",
    )

    possible_duplicate = prototype.create_object(
        "organization", "Example Authority (regional office)", created_by="reviewer-a", evidence=evidence("org-2")
    )
    try:
        prototype.add_identifier(
            possible_duplicate.id,
            "TED:buyer",
            "buyer-001",
            evidence=evidence("ted-buyer-duplicate-claim"),
            registered_by="reviewer-a",
        )
    except ValueError as exc:
        if str(exc) != "external identifier is already assigned to another object":
            raise
        prototype.record_identifier_conflict(
            possible_duplicate.id,
            "TED:buyer",
            "buyer-001",
            evidence=evidence("conflict-001"),
            reported_by="reviewer-b",
        )

    confirmed = prototype.create_object(
        "organization", "Confirmed Example Company", created_by="reviewer-a", evidence=evidence("org-3")
    )
    prototype.add_identifier(
        confirmed.id,
        "TED:buyer",
        "buyer-003",
        evidence=evidence("ted-buyer-003"),
        registered_by="reviewer-a",
    )
    prototype.confirm_crosswalk(
        confirmed.id,
        namespace="TED:buyer",
        source_value="buyer-003",
        authority="Example Public Registry",
        canonical_namespace="REGISTRY:company-id",
        canonical_value="company-003",
        evidence=evidence("crosswalk-003"),
        confirmed_by="reviewer-b",
    )

    ambiguous = prototype.create_object(
        "contract", "Example Services Agreement", created_by="reviewer-a", evidence=evidence("contract-1")
    )
    prototype.review_identity(
        ambiguous.id,
        IdentityStatus.AMBIGUOUS,
        rationale="Two registry records remain plausible.",
        evidence=evidence("ambiguity-002"),
        reviewed_by="reviewer-b",
    )

    insufficient = prototype.create_object(
        "product", "Sample Product", created_by="reviewer-a", evidence=evidence("product-1")
    )
    prototype.review_identity(
        insufficient.id,
        IdentityStatus.INSUFFICIENT_EVIDENCE,
        rationale="The source snapshot does not contain a stable product identifier.",
        evidence=evidence("product-1"),
        reviewed_by="reviewer-b",
    )
    prototype.create_object(
        "product", "Candidate Product", created_by="reviewer-a", evidence=evidence("product-2")
    )

    print(
        json.dumps(
            [
                {
                    "id": record.id,
                    "type": record.object_type.value,
                    "label": record.label,
                    "identity_status": record.identity_status.value,
                    "identifier_count": len(record.identifiers),
                    "crosswalk_count": len(record.crosswalks),
                    "review_count": len(record.reviews),
                }
                for record in prototype.list_objects()
            ],
            ensure_ascii=False,
            indent=2,
        )
    )
    print(
        json.dumps(
            [
                {
                    "id": conflict.id,
                    "existing_object_id": conflict.existing_object_id,
                    "claimant_object_id": conflict.claimant_object_id,
                    "identifier": f"{conflict.namespace}:{conflict.value}",
                    "status": conflict.status,
                    "evidence_uris": [item.uri for item in conflict.evidence],
                    "reported_by": list(conflict.reported_by),
                }
                for conflict in prototype.list_conflicts()
            ],
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
