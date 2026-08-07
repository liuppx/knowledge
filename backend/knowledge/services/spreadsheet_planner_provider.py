from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from knowledge.core.settings import Settings, get_settings


@dataclass
class SpreadsheetPlanningResult:
    plan: dict | None
    generated_by: dict[str, Any] = field(default_factory=dict)
    fallback_reason: str = ""


class SpreadsheetPlanningProvider:
    SYSTEM_PROMPT = """You create safe spreadsheet analysis plans.
Return exactly one JSON object and no markdown. Use only columns from the supplied schema.
Allowed fields: select, filters, group_by, aggregations, sort, limit.
Allowed filter operators: eq, ne, gt, gte, lt, lte, contains, in, is_null, not_null.
Allowed aggregations: count, sum, avg, min, max. Maximum result limit is 10000.
Do not emit Python, SQL, formulas, file paths, URLs, explanations, or additional keys.
If the intent cannot be represented safely, return an empty object."""

    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None) -> None:
        self.settings = settings or get_settings()
        self.client = client

    def generate(self, intent: str, profile: dict) -> SpreadsheetPlanningResult:
        normalized_intent = str(intent or "").strip()
        if not normalized_intent:
            return SpreadsheetPlanningResult(None, {"provider": "none", "mode": "profile_only"}, "intent is empty")
        if self.settings.model_provider_mode != "openai_compatible" or not self.settings.model_gateway_base_url:
            return SpreadsheetPlanningResult(
                None,
                {"provider": "none", "configuredMode": self.settings.model_provider_mode, "mode": "profile_only"},
                "analysis planner is not configured",
            )
        schema = {
            "format": profile.get("format"),
            "rowCount": profile.get("rowCount"),
            "columns": [
                {
                    "name": item.get("name"),
                    "inferredType": item.get("inferredType"),
                    "nullCount": item.get("nullCount"),
                    "nonNullCount": item.get("nonNullCount"),
                }
                for item in profile.get("columns", [])
            ],
        }
        payload = {
            "model": self.settings.analysis_planner_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps({"intent": normalized_intent, "dataset": schema}, ensure_ascii=False, separators=(",", ":")),
                },
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.settings.model_gateway_api_key:
            headers["Authorization"] = f"Bearer {self.settings.model_gateway_api_key}"
        client = self.client or httpx.Client(timeout=max(1, self.settings.analysis_planner_timeout_seconds))
        owns_client = self.client is None
        try:
            response = client.post(self._endpoint(), headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            plan = json.loads(content)
            if not isinstance(plan, dict):
                raise ValueError("planner response must be a JSON object")
            usage = body.get("usage") if isinstance(body, dict) else None
            return SpreadsheetPlanningResult(
                plan,
                {
                    "provider": "openai_compatible",
                    "model": self.settings.analysis_planner_model,
                    "responseId": str(body.get("id") or ""),
                    "usage": usage if isinstance(usage, dict) else {},
                    "promptVersion": "knowledge.spreadsheet-planner.v1",
                },
            )
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            return SpreadsheetPlanningResult(
                None,
                {
                    "provider": "openai_compatible",
                    "model": self.settings.analysis_planner_model,
                    "promptVersion": "knowledge.spreadsheet-planner.v1",
                    "mode": "profile_only",
                },
                self._error(exc),
            )
        finally:
            if owns_client:
                client.close()

    def _endpoint(self) -> str:
        base = self.settings.model_gateway_base_url.rstrip("/")
        return f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"

    @staticmethod
    def _error(exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        return message[:500]
