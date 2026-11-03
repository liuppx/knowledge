from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient
import pytest

from knowledge.db.session import SessionLocal
from knowledge.main import app
from knowledge.api import routes_ontology
from knowledge.services.ontology import OntologyConflictError, OntologyService


@pytest.fixture(autouse=True)
def enable_ontology_endpoints(monkeypatch):
    monkeypatch.setattr(routes_ontology.settings, "ontology_identity_enabled", True)


def _login(client: TestClient, account) -> dict[str, str]:
    challenge = client.post("/auth/challenge", json={"wallet_address": account.address})
    challenge.raise_for_status()
    signed = Account.sign_message(encode_defunct(text=challenge.json()["message"]), account.key)
    response = client.post(
        "/auth/verify",
        json={"wallet_address": account.address, "signature": signed.signature.hex()},
    )
    response.raise_for_status()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_kb(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post("/kbs", headers=headers, json={"name": name})
    response.raise_for_status()
    return response.json()["id"]


def _create_evidence(client: TestClient, headers: dict[str, str], kb_id: int, suffix: str = "1") -> dict:
    response = client.post(
        f"/kbs/{kb_id}/ontology/evidence",
        headers=headers,
        json={
            "uri": f"https://example.test/source/{suffix}",
            "source_version": f"v{suffix}",
            "locator": "section 1",
            "checksum": f"sha256:{suffix}",
        },
    )
    response.raise_for_status()
    return response.json()


def _create_object(client: TestClient, headers: dict[str, str], kb_id: int, evidence_id: int, label: str) -> dict:
    response = client.post(
        f"/kbs/{kb_id}/ontology/objects",
        headers=headers,
        json={"object_type": "organization", "label": label, "evidence_id": evidence_id},
    )
    response.raise_for_status()
    return response.json()


def test_ontology_identity_workflow_is_owner_scoped_auditable_and_non_merging():
    owner = Account.create()
    stranger = Account.create()
    with TestClient(app) as client:
        owner_headers = _login(client, owner)
        stranger_headers = _login(client, stranger)
        kb_id = _create_kb(client, owner_headers, "ontology identity workflow")
        evidence = _create_evidence(client, owner_headers, kb_id)
        followup_evidence = _create_evidence(client, owner_headers, kb_id, "2")

        first = _create_object(client, owner_headers, kb_id, evidence["id"], "Supplier A")
        second = _create_object(client, owner_headers, kb_id, evidence["id"], "Supplier B")
        assert first["identity_status"] == "candidate"
        assert first["created_by"] == owner.address.lower()
        assert len(first["reviews"]) == 1
        assert first["reviews"][0]["reviewed_by"] == owner.address.lower()

        identifier_payload = {
            "namespace": "registry:company",
            "value": "company-17",
            "evidence_id": evidence["id"],
            "registered_by": stranger.address,
        }
        registered = client.post(
            f"/kbs/{kb_id}/ontology/objects/{first['id']}/identifiers",
            headers=owner_headers,
            json=identifier_payload,
        )
        assert registered.status_code == 201
        registered_again = client.post(
            f"/kbs/{kb_id}/ontology/objects/{first['id']}/identifiers",
            headers=owner_headers,
            json=identifier_payload,
        )
        assert registered_again.status_code == 201
        assert registered_again.json()["id"] == registered.json()["id"]
        assert registered.json()["registered_by"] == owner.address.lower()

        different_evidence_claim = client.post(
            f"/kbs/{kb_id}/ontology/objects/{first['id']}/identifiers",
            headers=owner_headers,
            json={**identifier_payload, "evidence_id": followup_evidence["id"]},
        )
        assert different_evidence_claim.status_code == 409
        assert "different evidence" in different_evidence_claim.json()["detail"]

        duplicate_claim = client.post(
            f"/kbs/{kb_id}/ontology/objects/{second['id']}/identifiers",
            headers=owner_headers,
            json={**identifier_payload, "registered_by": owner.address},
        )
        assert duplicate_claim.status_code == 409

        conflict_payload = {
            "namespace": "registry:company",
            "value": "company-17",
            "evidence_id": followup_evidence["id"],
            "reported_by": stranger.address,
        }
        reported = client.post(
            f"/kbs/{kb_id}/ontology/objects/{second['id']}/conflicts",
            headers=owner_headers,
            json=conflict_payload,
        )
        assert reported.status_code == 201
        conflict = reported.json()
        assert conflict["status"] == "open"
        assert len(conflict["reports"]) == 1

        duplicate_report = client.post(
            f"/kbs/{kb_id}/ontology/objects/{second['id']}/conflicts",
            headers=owner_headers,
            json=conflict_payload,
        )
        assert duplicate_report.status_code == 201
        assert duplicate_report.json()["id"] == conflict["id"]
        assert len(duplicate_report.json()["reports"]) == 1

        blocked_confirmation = client.post(
            f"/kbs/{kb_id}/ontology/objects/{first['id']}/crosswalks",
            headers=owner_headers,
            json={
                "namespace": "registry:company",
                "source_value": "company-17",
                "authority": "Official register",
                "canonical_namespace": "gleif:lei",
                "canonical_value": "529900T8BM49AURSDO55",
                "evidence_id": evidence["id"],
            },
        )
        assert blocked_confirmation.status_code == 422
        assert "unresolved identifier conflicts" in blocked_confirmation.json()["detail"]

        adjudicated_payload = {
            "decision": "claim_rejected",
            "rationale": "The competing object has no supporting registry record.",
            "evidence_id": followup_evidence["id"],
            "adjudicated_by": stranger.address,
        }
        adjudicated = client.post(
            f"/kbs/{kb_id}/ontology/conflicts/{conflict['id']}/adjudications",
            headers=owner_headers,
            json=adjudicated_payload,
        )
        assert adjudicated.status_code == 200
        assert adjudicated.json()["status"] == "claim_rejected"
        assert adjudicated.json()["resolution"]["adjudicated_by"] == owner.address.lower()

        adjudicated_again = client.post(
            f"/kbs/{kb_id}/ontology/conflicts/{conflict['id']}/adjudications",
            headers=owner_headers,
            json=adjudicated_payload,
        )
        assert adjudicated_again.status_code == 200
        assert adjudicated_again.json()["resolution"] == adjudicated.json()["resolution"]

        resolved_duplicate_report = client.post(
            f"/kbs/{kb_id}/ontology/objects/{second['id']}/conflicts",
            headers=owner_headers,
            json=conflict_payload,
        )
        assert resolved_duplicate_report.status_code == 201
        assert resolved_duplicate_report.json()["id"] == conflict["id"]
        assert len(resolved_duplicate_report.json()["reports"]) == 1

        restored_first = client.get(
            f"/kbs/{kb_id}/ontology/objects/{first['id']}", headers=owner_headers
        ).json()
        restored_second = client.get(
            f"/kbs/{kb_id}/ontology/objects/{second['id']}", headers=owner_headers
        ).json()
        assert restored_first["identity_status"] == "candidate"
        assert restored_second["identity_status"] == "candidate"
        assert len(restored_first["identifiers"]) == 1
        assert len(restored_second["identifiers"]) == 0
        assert any(review["evidence_id"] == followup_evidence["id"] for review in restored_first["reviews"])
        assert any(review["evidence_id"] == followup_evidence["id"] for review in restored_second["reviews"])

        assert client.get(
            f"/kbs/{kb_id}/ontology/objects/{first['id']}", headers=stranger_headers
        ).status_code == 404
        assert client.get(
            f"/kbs/{kb_id}/ontology/conflicts/{conflict['id']}", headers=stranger_headers
        ).status_code == 404


def test_ontology_confirmation_requires_registered_identifier_and_authoritative_fields():
    account = Account.create()
    with TestClient(app) as client:
        headers = _login(client, account)
        kb_id = _create_kb(client, headers, "ontology confirmation guard")
        evidence = _create_evidence(client, headers, kb_id)
        record = _create_object(client, headers, kb_id, evidence["id"], "Supplier")

        missing_identifier = client.post(
            f"/kbs/{kb_id}/ontology/objects/{record['id']}/crosswalks",
            headers=headers,
            json={
                "namespace": "registry:company",
                "source_value": "company-17",
                "authority": "Official register",
                "canonical_namespace": "gleif:lei",
                "canonical_value": "529900T8BM49AURSDO55",
                "evidence_id": evidence["id"],
            },
        )
        assert missing_identifier.status_code == 422

        register = client.post(
            f"/kbs/{kb_id}/ontology/objects/{record['id']}/identifiers",
            headers=headers,
            json={"namespace": "registry:company", "value": "company-17", "evidence_id": evidence["id"]},
        )
        assert register.status_code == 201
        confirmed = client.post(
            f"/kbs/{kb_id}/ontology/objects/{record['id']}/crosswalks",
            headers=headers,
            json={
                "namespace": "registry:company",
                "source_value": "company-17",
                "authority": "Official register",
                "canonical_namespace": "gleif:lei",
                "canonical_value": "529900T8BM49AURSDO55",
                "evidence_id": evidence["id"],
                "created_by": "attacker",
            },
        )
        assert confirmed.status_code == 201
        assert confirmed.json()["created_by"] == account.address.lower()

        confirmed_again = client.post(
            f"/kbs/{kb_id}/ontology/objects/{record['id']}/crosswalks",
            headers=headers,
            json={
                "namespace": "registry:company",
                "source_value": "company-17",
                "authority": "Official register",
                "canonical_namespace": "gleif:lei",
                "canonical_value": "529900T8BM49AURSDO55",
                "evidence_id": evidence["id"],
            },
        )
        assert confirmed_again.status_code == 201
        assert confirmed_again.json()["id"] == confirmed.json()["id"]

        alias_identifier = client.post(
            f"/kbs/{kb_id}/ontology/objects/{record['id']}/identifiers",
            headers=headers,
            json={"namespace": "registry:alias", "value": "alias-17", "evidence_id": evidence["id"]},
        )
        assert alias_identifier.status_code == 201
        same_entity_alias = client.post(
            f"/kbs/{kb_id}/ontology/objects/{record['id']}/crosswalks",
            headers=headers,
            json={
                "namespace": "registry:alias",
                "source_value": "alias-17",
                "authority": "Official register",
                "canonical_namespace": "gleif:lei",
                "canonical_value": "529900T8BM49AURSDO55",
                "evidence_id": evidence["id"],
            },
        )
        assert same_entity_alias.status_code == 201

        another_object = _create_object(client, headers, kb_id, evidence["id"], "Other supplier")
        other_identifier = client.post(
            f"/kbs/{kb_id}/ontology/objects/{another_object['id']}/identifiers",
            headers=headers,
            json={"namespace": "registry:other", "value": "other-17", "evidence_id": evidence["id"]},
        )
        assert other_identifier.status_code == 201
        canonical_collision = client.post(
            f"/kbs/{kb_id}/ontology/objects/{another_object['id']}/crosswalks",
            headers=headers,
            json={
                "namespace": "registry:other",
                "source_value": "other-17",
                "authority": "Official register",
                "canonical_namespace": "gleif:lei",
                "canonical_value": "529900T8BM49AURSDO55",
                "evidence_id": evidence["id"],
            },
        )
        assert canonical_collision.status_code == 409


def test_ontology_identifier_claim_is_transactionally_unique_under_concurrency():
    account = Account.create()
    service = OntologyService()
    with TestClient(app) as client:
        headers = _login(client, account)
        kb_id = _create_kb(client, headers, "ontology concurrent identifiers")
        evidence = _create_evidence(client, headers, kb_id)
        objects = [
            _create_object(client, headers, kb_id, evidence["id"], "Supplier A"),
            _create_object(client, headers, kb_id, evidence["id"], "Supplier B"),
        ]

        barrier = Barrier(2)

        def claim(object_id: str) -> str:
            barrier.wait(timeout=5)
            with SessionLocal() as db:
                try:
                    result = service.register_identifier(
                        db,
                        account.address.lower(),
                        kb_id,
                        object_id,
                        namespace="registry:concurrent",
                        value="single-owner",
                        evidence_id=evidence["id"],
                    )
                    return f"registered:{result.object_id}"
                except OntologyConflictError:
                    return "conflict"

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(claim, (record["id"] for record in objects)))

        assert sum(outcome.startswith("registered:") for outcome in outcomes) == 1
        assert outcomes.count("conflict") == 1
        listed = client.get(f"/kbs/{kb_id}/ontology/objects", headers=headers)
        listed.raise_for_status()
        assert sum(len(record["identifiers"]) for record in listed.json()) == 1


def test_ontology_endpoints_are_hidden_until_explicitly_enabled(monkeypatch):
    account = Account.create()
    with TestClient(app) as client:
        headers = _login(client, account)
        kb_id = _create_kb(client, headers, "ontology disabled by default")
        monkeypatch.setattr(routes_ontology.settings, "ontology_identity_enabled", False)
        response = client.get(f"/kbs/{kb_id}/ontology/objects", headers=headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "ontology identity endpoints are disabled"
