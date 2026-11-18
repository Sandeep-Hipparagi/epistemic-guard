from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from epistemic_guard.extraction.extractor import ClaimExtractor
from epistemic_guard.graph.workflow import EpistemicGuardPipeline
from epistemic_guard.interfaces.api import create_app
from epistemic_guard.interfaces.cli import app as cli_app, set_dependencies
from epistemic_guard.interfaces.mcp_server import create_mcp_server
from epistemic_guard.llm.client import StructuredLLMClient
from epistemic_guard.schemas import (
    EmotionalFraming,
    ExtractedClaim,
    ExtractionBatchResult,
    SideNarrativeDraft,
    SynthesisLLMOutput,
    TwoSidedListeningReport,
)
from epistemic_guard.tools.domain_auditor import DomainAuditor
from epistemic_guard.tools.provenance_resolver import ProvenanceInvestigator
from epistemic_guard.tools.search import MockSearchProvider, SearchHit

runner = CliRunner()


@pytest.fixture
def mock_pipeline() -> EpistemicGuardPipeline:
    """Construct an offline, mocked EpistemicGuardPipeline for interface testing."""
    mock_llm = StructuredLLMClient()
    mock_llm._client = MagicMock()

    claim_a = ExtractedClaim(
        claim_id="mcp-test-claim-1",
        speaker="Spokesperson",
        verbatim_quote="Economic growth exceeded forecast by 3 percent.",
        normalized_claim="Economic growth exceeded forecast by 3 percent.",
        alleged_venue="Treasury Press Room",
        alleged_date="2026-11-19",
        cited_urls=["https://www.reuters.com/markets/economic-growth-2026"],
        narrative_side="Side A",
        emotional_framing=EmotionalFraming(
            arousal_score=0.2,
            primary_emotion="relief",
            manipulation_cues=[],
        ),
    )

    batch = ExtractionBatchResult(
        raw_text_hash="test_interface_hash",
        overall_emotional_intensity=0.2,
        claims=[claim_a],
    )

    synthesis = SynthesisLLMOutput(
        topic_title="Treasury Economic Forecast",
        side_drafts=[
            SideNarrativeDraft(
                side_label="Side A",
                steel_manned_summary="Official economic expansion data confirmed by Treasury records.",
                key_arguments=["Validated by wire reporting."],
            )
        ],
        deescalation_guidance="Official statement confirmed by wire reporting.",
    )

    def mock_gen(prompt_name, response_model, prompt_vars=None):
        if prompt_name == "claim_extraction":
            return batch
        elif prompt_name == "two_sided_synthesis":
            return synthesis
        raise ValueError(f"Unexpected prompt {prompt_name}")

    mock_llm.generate_structured = MagicMock(side_effect=mock_gen)  # type: ignore

    mock_search = MockSearchProvider(
        default_hits=[
            SearchHit(
                title="Reuters - Economic Growth",
                url="https://www.reuters.com/markets/economic-growth-2026",
                snippet="Official economic forecast results published today.",
                published_date="2026-11-19",
                source_query="growth",
            )
        ]
    )

    extractor = ClaimExtractor(llm_client=mock_llm)
    investigator = ProvenanceInvestigator(search_provider=mock_search)

    return EpistemicGuardPipeline(
        extractor=extractor,
        investigator=investigator,
        llm_client=mock_llm,
    )


class TestCLIInterface:
    def test_cli_audit_url_primary(self) -> None:
        result = runner.invoke(cli_app, ["audit-url", "https://www.reuters.com/markets"])
        assert result.exit_code == 0
        assert "TIER_1_PRIMARY" in result.stdout
        assert "reuters.com" in result.stdout
        assert "Yes (Accountable)" in result.stdout

    def test_cli_audit_url_social(self) -> None:
        result = runner.invoke(cli_app, ["audit-url", "https://x.com/viral_account/status/123"])
        assert result.exit_code == 0
        assert "TIER_4_USER_GENERATED" in result.stdout
        assert "Unmoderated UGC" in result.stdout

    def test_cli_analyze_terminal_output(self, mock_pipeline: EpistemicGuardPipeline) -> None:
        set_dependencies(pipeline=mock_pipeline)
        try:
            result = runner.invoke(
                cli_app,
                [
                    "analyze",
                    "Treasury announces growth: https://www.reuters.com/markets/economic-growth-2026",
                ],
            )
            assert result.exit_code == 0
            assert "PRE-SHARE CHECK: SAFE TO SHARE" in result.stdout
            assert "Treasury Economic Forecast" in result.stdout
            assert "Side A" in result.stdout
        finally:
            set_dependencies(pipeline=None)

    def test_cli_analyze_json_output(self, mock_pipeline: EpistemicGuardPipeline) -> None:
        set_dependencies(pipeline=mock_pipeline)
        try:
            result = runner.invoke(
                cli_app,
                [
                    "analyze",
                    "Treasury announces growth: https://www.reuters.com/markets/economic-growth-2026",
                    "--json",
                ],
            )
            assert result.exit_code == 0
            data = json.loads(result.stdout)
            assert data["topic"] == "Treasury Economic Forecast"
            assert "perspectives" in data
            assert len(data["perspectives"]) >= 1
            assert data["perspectives"][0]["verified_shareable_count"] == 1
        finally:
            set_dependencies(pipeline=None)


class TestFastAPIInterface:
    def test_health_endpoint(self) -> None:
        client = TestClient(create_app())
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "version": "0.2.0"}

    def test_audit_url_endpoint(self) -> None:
        client = TestClient(create_app())
        resp = client.post("/v1/audit/url", json={"url": "https://apnews.com/article/test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["registered_domain"] == "apnews.com"
        assert data["tier"] == "TIER_1_PRIMARY"
        assert data["is_primary_or_editorial"] is True

    def test_analyze_endpoint(self, mock_pipeline: EpistemicGuardPipeline) -> None:
        app = create_app(pipeline=mock_pipeline)
        client = TestClient(app)

        resp = client.post(
            "/v1/analyze",
            json={
                "texts": ["Treasury announces growth: https://www.reuters.com/markets/economic-growth-2026"],
                "reference_now_iso": "2026-11-19T12:00:00Z",
            },
        )
        assert resp.status_code == 200
        report = TwoSidedListeningReport.model_validate(resp.json())
        assert report.topic == "Treasury Economic Forecast"
        assert len(report.perspectives) == 1
        assert report.perspectives[0].verified_shareable_count == 1


class TestMCPInterface:
    def test_mcp_audit_source_url(self) -> None:
        mcp = create_mcp_server()
        audit_func = getattr(mcp, "audit_source_url_func")
        result = audit_func("https://theonion.com/article-parody")

        assert isinstance(result, dict)
        assert result["tier"] == "TIER_5_SATIRE_PARODY"
        assert result["is_satire"] is True

    def test_mcp_check_viral_claim_unconfirmed(self) -> None:
        # Mock search provider returning nothing (unconfirmed claim)
        mock_search = MockSearchProvider(default_hits=[])
        mock_investigator = ProvenanceInvestigator(search_provider=mock_search)
        mock_pipeline = EpistemicGuardPipeline(investigator=mock_investigator)

        mcp = create_mcp_server(pipeline=mock_pipeline)
        check_func = getattr(mcp, "check_viral_claim_func")
        res = check_func("Leaked claim with no links and no sources")

        assert isinstance(res, dict)
        assert res["verdict"] == "DO_NOT_SHARE_UNCONFIRMED"
        assert res["is_shareable"] is False
        assert "NO_PRIMARY_MEDIA_OR_NAMED_OUTLET" in res["warning_flags"] or "MISSING_TIMESTAMP_RECYCLED_RISK" in res["warning_flags"]

    def test_mcp_listen_two_sides(self, mock_pipeline: EpistemicGuardPipeline) -> None:
        mcp = create_mcp_server(pipeline=mock_pipeline)
        listen_func = getattr(mcp, "listen_two_sides_func")
        report = listen_func(["Treasury statement https://www.reuters.com/markets/economic-growth-2026"])

        assert isinstance(report, dict)
        assert report["topic"] == "Treasury Economic Forecast"
        assert len(report["perspectives"]) >= 1
        assert "deescalation_guidance" in report
