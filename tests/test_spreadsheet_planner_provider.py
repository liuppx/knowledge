from __future__ import annotations

import json

import httpx

from knowledge.core.settings import Settings
from knowledge.services.spreadsheet_planner_provider import SpreadsheetPlanningProvider


def test_router_planner_requests_strict_json_without_sample_values():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-plan-1",
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "group_by": ["region"],
                                    "aggregations": [{"column": "amount", "op": "sum", "alias": "total"}],
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    settings = Settings(
        model_provider_mode="openai_compatible",
        model_gateway_base_url="https://router.example/v1",
        model_gateway_api_key="router-secret",
        analysis_planner_model="planner-model",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = SpreadsheetPlanningProvider(settings=settings, client=client).generate(
            "按地区汇总金额",
            {
                "format": "csv",
                "rowCount": 10,
                "columns": [
                    {"name": "region", "inferredType": "string", "nullCount": 0, "nonNullCount": 10, "samples": ["secret-east"]},
                    {"name": "amount", "inferredType": "number", "nullCount": 1, "nonNullCount": 9, "samples": ["999"]},
                ],
            },
        )
    finally:
        client.close()

    assert result.plan["group_by"] == ["region"]
    assert result.generated_by["model"] == "planner-model"
    assert captured["url"] == "https://router.example/v1/chat/completions"
    assert captured["authorization"] == "Bearer router-secret"
    assert captured["body"]["response_format"] == {"type": "json_object"}
    user_payload = captured["body"]["messages"][1]["content"]
    assert "secret-east" not in user_payload
    assert '"name":"region"' in user_payload


def test_router_planner_falls_back_when_response_is_not_json():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})

    settings = Settings(
        model_provider_mode="openai_compatible",
        model_gateway_base_url="https://router.example",
        analysis_planner_model="planner-model",
    )
    client = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        result = SpreadsheetPlanningProvider(settings=settings, client=client).generate(
            "分析",
            {"format": "csv", "rowCount": 1, "columns": []},
        )
    finally:
        client.close()

    assert result.plan is None
    assert result.generated_by["mode"] == "profile_only"
    assert result.fallback_reason


def test_router_planner_is_disabled_in_mock_mode():
    result = SpreadsheetPlanningProvider(settings=Settings(model_provider_mode="mock")).generate(
        "按地区汇总",
        {"format": "csv", "rowCount": 1, "columns": []},
    )
    assert result.plan is None
    assert result.generated_by["provider"] == "none"
    assert result.fallback_reason == "analysis planner is not configured"
