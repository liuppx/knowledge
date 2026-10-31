from __future__ import annotations

import pytest

from knowledge.ontology.identity_prototype import (
    IdentityPrototype,
    IdentityRole,
    IdentityStatus,
    ObjectType,
    EvidenceReference,
)


@pytest.fixture
def prototype() -> IdentityPrototype:
    return IdentityPrototype(
        {
            "a": IdentityRole.REVIEWER,
            "b": IdentityRole.REVIEWER,
            "reviewer-a": IdentityRole.REVIEWER,
            "reviewer-b": IdentityRole.REVIEWER,
            "reviewer-c": IdentityRole.REVIEWER,
            "reviewer-d": IdentityRole.REVIEWER,
            "adjudicator": IdentityRole.ADJUDICATOR,
            "adjudicator-2": IdentityRole.ADJUDICATOR,
            "adjudicator-3": IdentityRole.ADJUDICATOR,
        }
    )


def evidence(uri: str = "https://example.test/registry/1") -> EvidenceReference:
    return EvidenceReference(
        uri=uri,
        source_version="snapshot-2026-10",
        locator="record/1",
        checksum="a" * 64,
    )


def test_object_starts_as_candidate_and_keeps_evidence_audit(prototype: IdentityPrototype):
    record = prototype.create_object(
        ObjectType.ORGANIZATION,
        "Example Organization",
        created_by="reviewer-a",
        evidence=evidence(),
    )

    assert record.object_type is ObjectType.ORGANIZATION
    assert record.identity_status is IdentityStatus.CANDIDATE
    assert record.reviews[0].reviewed_by == "reviewer-a"
    assert record.reviews[0].evidence.source_version == "snapshot-2026-10"


def test_objects_cannot_be_created_without_evidence(prototype: IdentityPrototype):
    with pytest.raises(ValueError, match="evidence reference is required"):
        prototype.create_object(
            "organization",
            "Unsubstantiated Organization",
            created_by="reviewer-a",
            evidence=None,
        )


def test_confirmed_status_cannot_be_set_without_authoritative_crosswalk(prototype: IdentityPrototype):
    record = prototype.create_object(
        "organization",
        "Example Organization",
        created_by="reviewer-a",
        evidence=evidence(),
    )

    with pytest.raises(ValueError, match="authoritative crosswalk"):
        prototype.review_identity(
            record.id,
            "confirmed",
            rationale="Looks similar",
            evidence=evidence(),
            reviewed_by="reviewer-a",
        )

    assert prototype.get_object(record.id).identity_status is IdentityStatus.CANDIDATE


def test_authoritative_crosswalk_confirms_identity_and_records_provenance(prototype: IdentityPrototype):
    record = prototype.create_object(
        "organization",
        "Example Organization",
        created_by="reviewer-a",
        evidence=evidence(),
    )
    prototype.add_identifier(
        record.id,
        "TED:buyer",
        "buyer-17",
        evidence=evidence("https://example.test/ted/buyer-17"),
        registered_by="reviewer-a",
    )

    crosswalk = prototype.confirm_crosswalk(
        record.id,
        namespace="TED:buyer",
        source_value="buyer-17",
        authority="GLEIF",
        canonical_namespace="GLEIF:LEI",
        canonical_value="529900T8BM49AURSDO55",
        evidence=evidence("https://example.test/gleif/lei/1"),
        confirmed_by="reviewer-b",
    )
    saved = prototype.get_object(record.id)

    assert saved.identity_status is IdentityStatus.CONFIRMED
    assert saved.crosswalks == [crosswalk]
    assert saved.identifiers[0].registered_by == "reviewer-a"
    assert saved.identifiers[0].registered_at.tzinfo is not None
    assert saved.reviews[-1].reviewed_by == "reviewer-b"
    assert saved.reviews[-1].evidence.uri == "https://example.test/gleif/lei/1"


def test_identifier_collision_cannot_merge_two_objects(prototype: IdentityPrototype):
    first = prototype.create_object("organization", "First", created_by="a", evidence=evidence())
    second = prototype.create_object("organization", "Second", created_by="b", evidence=evidence())
    prototype.add_identifier(
        first.id, "TED:buyer", "buyer-17", evidence=evidence(), registered_by="a"
    )
    prototype.confirm_crosswalk(
        first.id,
        namespace="TED:buyer",
        source_value="buyer-17",
        authority="Public Registry",
        canonical_namespace="REGISTRY:company-id",
        canonical_value="company-17",
        evidence=evidence("https://example.test/crosswalk/17"),
        confirmed_by="reviewer-a",
    )

    with pytest.raises(ValueError, match="already assigned"):
        prototype.add_identifier(
            second.id, "TED:buyer", "buyer-17", evidence=evidence(), registered_by="b"
        )

    conflict = prototype.record_identifier_conflict(
        second.id,
        "TED:buyer",
        "buyer-17",
        evidence=evidence("https://example.test/conflict/1"),
        reported_by="reviewer-b",
    )
    saved_first = prototype.get_object(first.id)
    saved_second = prototype.get_object(second.id)

    assert conflict.existing_object_id == first.id
    assert conflict.claimant_object_id == second.id
    assert conflict.status == "open"
    assert saved_first.identity_status is IdentityStatus.AMBIGUOUS
    assert saved_second.identity_status is IdentityStatus.AMBIGUOUS
    assert saved_second.reviews[-1].evidence.uri == "https://example.test/conflict/1"
    assert prototype.list_conflicts() == [conflict]
    assert prototype.record_identifier_conflict(
        second.id,
        "TED:buyer",
        "buyer-17",
        evidence=evidence("https://example.test/conflict/1"),
        reported_by="reviewer-b",
    ) == conflict

    updated_conflict = prototype.record_identifier_conflict(
        second.id,
        "TED:buyer",
        "buyer-17",
        evidence=evidence("https://example.test/conflict/2"),
        reported_by="reviewer-c",
    )
    assert updated_conflict.id == conflict.id
    assert [item.uri for item in updated_conflict.evidence] == [
        "https://example.test/conflict/1",
        "https://example.test/conflict/2",
    ]
    assert updated_conflict.reported_by == ("reviewer-b", "reviewer-c")
    assert prototype.get_object(second.id).reviews[-1].reviewed_by == "reviewer-c"

    resolved = prototype.reject_identifier_claim(
        conflict.id,
        rationale="The registry evidence shows the claimant uses a different identifier.",
        evidence=evidence("https://example.test/adjudication/1"),
        adjudicated_by="adjudicator-2",
    )
    assert resolved.status == "claim_rejected"
    assert resolved.resolution is not None
    assert resolved.resolution.decision == "claim_rejected"
    assert prototype.get_object(first.id).identity_status is IdentityStatus.CONFIRMED
    assert prototype.get_object(second.id).identity_status is IdentityStatus.CANDIDATE
    assert prototype.get_object(first.id).identifiers[0].value == "buyer-17"
    assert prototype.get_object(second.id).identifiers == []
    assert prototype.reject_identifier_claim(
        conflict.id,
        rationale="The registry evidence shows the claimant uses a different identifier.",
        evidence=evidence("https://example.test/adjudication/1"),
        adjudicated_by="adjudicator-2",
    ) == resolved

    with pytest.raises(ValueError, match="already resolved"):
        prototype.reject_identifier_claim(
            conflict.id,
            rationale="Different decision.",
            evidence=evidence("https://example.test/adjudication/2"),
            adjudicated_by="adjudicator-3",
        )

    with pytest.raises(ValueError, match="identity conflict is already resolved"):
        prototype.record_identifier_conflict(
            second.id,
            "TED:buyer",
            "buyer-17",
            evidence=evidence("https://example.test/conflict/after-resolution"),
            reported_by="reviewer-d",
        )


def test_role_boundary_requires_explicit_actor_and_separates_review_from_adjudication():
    prototype = IdentityPrototype(
        {
            "contributor-a": IdentityRole.CONTRIBUTOR,
            "reviewer-a": IdentityRole.REVIEWER,
            "adjudicator-a": IdentityRole.ADJUDICATOR,
        }
    )
    owner = prototype.create_object(
        "organization", "Owner", created_by="contributor-a", evidence=evidence()
    )
    prototype.add_identifier(
        owner.id,
        "TED:buyer",
        "buyer-17",
        evidence=evidence("https://example.test/ted/buyer-17"),
        registered_by="contributor-a",
    )

    with pytest.raises(PermissionError, match="review_identity"):
        prototype.review_identity(
            owner.id,
            IdentityStatus.AMBIGUOUS,
            rationale="Contributor cannot perform identity review.",
            evidence=evidence("https://example.test/review/denied"),
            reviewed_by="contributor-a",
        )

    prototype.review_identity(
        owner.id,
        IdentityStatus.AMBIGUOUS,
        rationale="Reviewer marks the candidate as ambiguous.",
        evidence=evidence("https://example.test/review/accepted"),
        reviewed_by="reviewer-a",
    )
    claimant = prototype.create_object(
        "organization", "Claimant", created_by="contributor-a", evidence=evidence("https://example.test/claimant")
    )
    conflict = prototype.record_identifier_conflict(
        claimant.id,
        "TED:buyer",
        "buyer-17",
        evidence=evidence("https://example.test/conflict/17"),
        reported_by="reviewer-a",
    )

    with pytest.raises(PermissionError, match="reject_identifier_claim"):
        prototype.reject_identifier_claim(
            conflict.id,
            rationale="Reviewer cannot adjudicate a claim.",
            evidence=evidence("https://example.test/adjudication/denied"),
            adjudicated_by="reviewer-a",
        )
    resolved = prototype.reject_identifier_claim(
        conflict.id,
        rationale="Adjudicator rejects the competing claim.",
        evidence=evidence("https://example.test/adjudication/accepted"),
        adjudicated_by="adjudicator-a",
    )
    assert resolved.resolution is not None
    assert resolved.resolution.adjudicated_by == "adjudicator-a"

    with pytest.raises(PermissionError, match="create_object"):
        prototype.create_object(
            "product", "Unknown Actor Product", created_by="unknown", evidence=evidence()
        )


def test_open_conflict_blocks_crosswalk_confirmation_and_status_override(prototype: IdentityPrototype):
    owner = prototype.create_object("organization", "Owner", created_by="a", evidence=evidence())
    prototype.add_identifier(
        owner.id, "TED:buyer", "buyer-17", evidence=evidence(), registered_by="a"
    )
    prototype.add_identifier(
        owner.id, "REGISTRY:company", "company-17", evidence=evidence(), registered_by="a"
    )
    prototype.confirm_crosswalk(
        owner.id,
        namespace="TED:buyer",
        source_value="buyer-17",
        authority="Public Registry",
        canonical_namespace="REGISTRY:company",
        canonical_value="company-17",
        evidence=evidence("https://example.test/crosswalk/17"),
        confirmed_by="reviewer-a",
    )
    claimant = prototype.create_object("organization", "Claimant", created_by="b", evidence=evidence())
    prototype.record_identifier_conflict(
        claimant.id,
        "TED:buyer",
        "buyer-17",
        evidence=evidence("https://example.test/conflict/17"),
        reported_by="reviewer-b",
    )

    with pytest.raises(ValueError, match="unresolved identifier conflicts"):
        prototype.confirm_crosswalk(
            owner.id,
            namespace="REGISTRY:company",
            source_value="company-17",
            authority="Second Registry",
            canonical_namespace="REGISTRY:company",
            canonical_value="second-company-17",
            evidence=evidence("https://example.test/crosswalk/second"),
            confirmed_by="reviewer-c",
        )
    with pytest.raises(ValueError, match="governed by unresolved identifier conflicts"):
        prototype.review_identity(
            owner.id,
            IdentityStatus.CANDIDATE,
            rationale="Attempt to override the open conflict.",
            evidence=evidence("https://example.test/review/override"),
            reviewed_by="reviewer-c",
        )
    with pytest.raises(ValueError, match="governed by unresolved identifier conflicts"):
        prototype.review_identity(
            owner.id,
            IdentityStatus.AMBIGUOUS,
            rationale="Add a separate review while the conflict is still open.",
            evidence=evidence("https://example.test/review/ambiguous"),
            reviewed_by="reviewer-c",
        )

    saved_owner = prototype.get_object(owner.id)
    assert saved_owner.identity_status is IdentityStatus.AMBIGUOUS
    assert len(saved_owner.crosswalks) == 1


@pytest.mark.parametrize("resolution_order", [("first", "second"), ("second", "first")])
def test_multiple_open_conflicts_restore_status_only_after_last_resolution(
    prototype: IdentityPrototype,
    resolution_order: tuple[str, str],
):
    owner = prototype.create_object("organization", "Owner", created_by="a", evidence=evidence())
    prototype.add_identifier(
        owner.id, "TED:buyer", "buyer-17", evidence=evidence(), registered_by="a"
    )
    prototype.add_identifier(
        owner.id, "REGISTRY:company", "company-17", evidence=evidence(), registered_by="a"
    )
    prototype.confirm_crosswalk(
        owner.id,
        namespace="TED:buyer",
        source_value="buyer-17",
        authority="Public Registry",
        canonical_namespace="REGISTRY:company",
        canonical_value="company-17",
        evidence=evidence("https://example.test/crosswalk/17"),
        confirmed_by="reviewer-a",
    )

    claimants = {
        name: prototype.create_object("organization", f"Claimant {name}", created_by="b", evidence=evidence())
        for name in ("first", "second")
    }
    identifiers = {
        "first": ("TED:buyer", "buyer-17"),
        "second": ("REGISTRY:company", "company-17"),
    }
    conflicts = {
        name: prototype.record_identifier_conflict(
            claimants[name].id,
            namespace,
            value,
            evidence=evidence(f"https://example.test/conflict/{name}"),
            reported_by="reviewer-b",
        )
        for name, (namespace, value) in identifiers.items()
    }

    for index, name in enumerate(resolution_order):
        prototype.reject_identifier_claim(
            conflicts[name].id,
            rationale=f"Reject {name} claim based on registry evidence.",
            evidence=evidence(f"https://example.test/adjudication/{name}"),
            adjudicated_by="adjudicator-2",
        )
        expected_owner_status = (
            IdentityStatus.AMBIGUOUS if index == 0 else IdentityStatus.CONFIRMED
        )
        assert prototype.get_object(owner.id).identity_status is expected_owner_status
        assert prototype.get_object(claimants[name].id).identity_status is IdentityStatus.CANDIDATE


def test_crosswalk_requires_registered_source_identifier_and_authority(prototype: IdentityPrototype):
    record = prototype.create_object("organization", "Example", created_by="a", evidence=evidence())

    with pytest.raises(ValueError, match="source identifier must be registered"):
        prototype.confirm_crosswalk(
            record.id,
            namespace="TED:buyer",
            source_value="buyer-17",
            authority="GLEIF",
            canonical_namespace="GLEIF:LEI",
            canonical_value="529900T8BM49AURSDO55",
            evidence=evidence(),
            confirmed_by="reviewer-a",
        )

    prototype.add_identifier(
        record.id, "TED:buyer", "buyer-17", evidence=evidence(), registered_by="a"
    )
    with pytest.raises(ValueError, match="crosswalk requires: authority"):
        prototype.confirm_crosswalk(
            record.id,
            namespace="TED:buyer",
            source_value="buyer-17",
            authority="",
            canonical_namespace="GLEIF:LEI",
            canonical_value="529900T8BM49AURSDO55",
            evidence=evidence(),
            confirmed_by="reviewer-a",
        )


def test_returned_objects_cannot_mutate_prototype_state(prototype: IdentityPrototype):
    record = prototype.create_object("product", "Example Product", created_by="a", evidence=evidence())
    record.label = "Tampered"
    prototype.list_objects()[0].identity_status = IdentityStatus.CONFIRMED

    saved = prototype.get_object(record.id)
    assert saved.label == "Example Product"
    assert saved.identity_status is IdentityStatus.CANDIDATE
