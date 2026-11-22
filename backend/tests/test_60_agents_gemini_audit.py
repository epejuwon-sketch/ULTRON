"""Comprehensive 60-agent & 5-tier NEON Gemini integration audit regression suite (local mocked HTTP transport)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

from app.core.config import Settings
from app.core.permissions import Principal
from app.db.models import AgentRecord
from app.db.session import get_session_factory, init_database, reset_engine
from app.services.agent_catalog import AGENT_CATALOG_60
from app.services.agent_service import build_agent_manifest
from app.services.neon_providers import GeminiLLMProvider
from app.services.neon_router import get_reasoning_tiers, invoke_agent_reasoning
from app.services.platform_modules_service import analyze_visual_frame


def test_all_60_agents_unique_contracts_and_live_gemini_routing_across_all_5_tiers(
    tmp_path: Path,
) -> None:
    """Verify all 60 agents keep unique roles/instructions/schemas and route live through NEON -> Gemini across T1-T5."""
    db_file = tmp_path / "audit_60_agents.db"
    live_cfg = Settings(
        ULTRON_ENV="test",
        ULTRON_SQLITE_PATH=str(db_file),
        ULTRON_DATABASE_URL="",
        GEMINI_API_KEY="AIzaSyTestLiveRoutingAll60Agents000001",
    )
    reset_engine()
    init_database(live_cfg)

    seen_system_instructions: set[str] = set()
    seen_agent_ids: set[str] = set()
    seen_names: set[str] = set()
    tiers_tested: set[int] = set()

    def gemini_mock_transport(req: httpx.Request) -> httpx.Response:
        model_id = req.url.path.split("/models/")[-1].split(":")[0]
        payload = json.loads(req.content.decode("utf-8"))
        sys_text = payload.get("systemInstruction", {}).get("parts", [{}])[0].get("text", "")
        assert sys_text, "Every agent MUST send its unique systemInstruction to Gemini"
        assert req.headers.get("x-goog-api-key") == "AIzaSyTestLiveRoutingAll60Agents000001"
        if model_id != "gemini-2.5-flash":
            return httpx.Response(
                404,
                json={"error": {"code": 404, "status": "NOT_FOUND", "message": f"Model {model_id} not eligible"}},
            )
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": f"LIVE_OK:{model_id}"}]}}],
                "usageMetadata": {"promptTokenCount": 14, "candidatesTokenCount": 5, "totalTokenCount": 19},
            },
        )

    provider = GeminiLLMProvider(live_cfg, http_client=httpx.Client(transport=httpx.MockTransport(gemini_mock_transport)))

    try:
        with get_session_factory(live_cfg)() as db:
            assert len(AGENT_CATALOG_60) == 60
            for aid, expected_name, _grp, expected_domain, expected_desc, expected_tools, expected_perm, expected_tier in AGENT_CATALOG_60:
                rec = db.get(AgentRecord, aid)
                assert rec is not None, f"{aid} missing from DB"
                manifest = build_agent_manifest(rec, live_cfg)
                assert manifest["name"] == expected_name
                assert manifest["domain"] == expected_domain
                assert manifest["role_description"] == expected_desc
                assert manifest["tools"] == expected_tools
                assert manifest["permission_scope"] == expected_perm
                assert manifest["default_reasoning_tier"] == expected_tier
                assert manifest["contract"]["input_schema"]["required"] == ["prompt"]
                assert manifest["contract"]["output_schema"]["properties"]["agent_id"]["const"] == aid
                assert len(manifest["contract"]["execution_workflow"]) == 4

                seen_agent_ids.add(aid)
                seen_names.add(expected_name)
                seen_system_instructions.add(rec.system_instruction)

                res = invoke_agent_reasoning(
                    db,
                    agent_id=aid,
                    prompt=f"Safe non-destructive readiness check for {aid}.",
                    settings=live_cfg,
                    providers=[provider],
                )
                assert res["agent_id"] == aid
                assert res["provider"] == "gemini"
                assert res["execution_mode"] == "gemini_live"
                assert res["model"] == "gemini-2.5-flash"
                assert res["fallback_used"] is True
                assert res["output"] == "LIVE_OK:gemini-2.5-flash"
                assert res["reasoning_tier"] == expected_tier
                assert rec.tasks_completed >= 1
                tiers_tested.add(expected_tier)

            # Explicitly test each reasoning tier T1..T5 directly on AGT-01 (primary model, zero fallback)
            direct_cfg = Settings(
                ULTRON_ENV="test",
                ULTRON_SQLITE_PATH=str(db_file),
                ULTRON_DATABASE_URL="",
                GEMINI_API_KEY="AIzaSyTestDirectPrimary000002",
                GEMINI_MODEL_FAST="gemini-2.5-flash",
                GEMINI_MODEL_STANDARD="gemini-2.5-flash",
                GEMINI_MODEL_REASONING="gemini-2.5-flash",
            )
            direct_provider = GeminiLLMProvider(
                direct_cfg,
                http_client=httpx.Client(
                    transport=httpx.MockTransport(
                        lambda _req: httpx.Response(
                            200,
                            json={
                                "candidates": [{"content": {"parts": [{"text": "DIRECT_PRIMARY_OK"}]}}],
                                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 4, "totalTokenCount": 14},
                            },
                        )
                    )
                ),
            )
            for tier_num in (1, 2, 3, 4, 5):
                r = invoke_agent_reasoning(
                    db,
                    agent_id="AGT-01",
                    prompt=f"Tier {tier_num} verification check",
                    settings=direct_cfg,
                    reasoning_tier=tier_num,
                    providers=[direct_provider],
                )
                assert r["reasoning_tier"] == tier_num
                assert r["execution_mode"] == "gemini_live"
                assert r["model"] == "gemini-2.5-flash"
                assert r["fallback_used"] is False
                assert r["failover_errors"] == []
    finally:
        reset_engine()

    assert len(seen_agent_ids) == 60
    assert len(seen_names) == 60
    assert len(seen_system_instructions) == 60
    assert tiers_tested == {1, 2, 3, 4, 5}
    assert set(get_reasoning_tiers(live_cfg).keys()) == {1, 2, 3, 4, 5}


def test_analyze_visual_frame_uses_valid_multimodal_parts_schema(
    tmp_path: Path, monkeypatch
) -> None:
    """Ensure analyze_visual_frame calls GeminiClient.generate_content with valid multimodal_parts (not invalid inline_data)."""
    captured: dict = {}

    def fake_generate(self, **kwargs):
        captured.update(kwargs)
        return {"text": "Visual frame verified.", "usage": {"total_tokens": 25}}

    monkeypatch.setattr("app.integrations.gemini.GeminiClient.generate_content", fake_generate)

    live_cfg = Settings(
        ULTRON_ENV="test",
        ULTRON_SQLITE_PATH=str(tmp_path / "visual_test.db"),
        ULTRON_DATABASE_URL="",
        GEMINI_API_KEY="AIzaSyVisualTestKey000003",
        GEMINI_MODEL_STANDARD="gemini-2.5-flash",
    )
    reset_engine()
    init_database(live_cfg)
    principal = Principal(
        user_id="usr_test",
        username="owner",
        role="OWNER",
        tenant_id=live_cfg.default_tenant_id,
        jti="jti_test",
    )
    pixel_b64 = base64.b64encode(b"fake-image-bytes").decode("ascii")
    try:
        with get_session_factory(live_cfg)() as db:
            out = analyze_visual_frame(
                db,
                principal=principal,
                settings=live_cfg,
                prompt="Inspect visual frame",
                image_base64=pixel_b64,
                mime_type="image/png",
            )
    finally:
        reset_engine()

    assert out["status"] == "ANALYZED_LIVE"
    assert out["analysis"] == "Visual frame verified."
    assert "multimodal_parts" in captured
    assert captured["multimodal_parts"][0]["inlineData"]["mimeType"] == "image/png"
