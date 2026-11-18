from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from epistemic_guard.extraction.extractor import ClaimExtractor
from epistemic_guard.graph.workflow import EpistemicGuardPipeline
from epistemic_guard.interfaces.api import create_app
from epistemic_guard.interfaces.web_ui import render_web_ui
from epistemic_guard.llm.client import StructuredLLMClient
from epistemic_guard.schemas import (
    ClaimAuditRequest,
    EmotionalFraming,
    ExtractedClaim,
    ExtractionBatchResult,
    ProvenanceVerdict,
    SideNarrativeDraft,
    SourceRecord,
    SourceTier,
    SynthesisLLMOutput,
)
from epistemic_guard.tools.domain_auditor import DomainAuditor, detect_lookalike_domain
from epistemic_guard.tools.provenance_resolver import ProvenanceInvestigator
from epistemic_guard.tools.quote_matcher import (
    compute_quote_similarity,
    verify_quote_integrity,
)
from epistemic_guard.tools.search import MockSearchProvider, SearchHit


class TestQuoteIntegrityAuditor:
    def test_compute_quote_similarity_exact_and_variations(self) -> None:
        """Verify similarity scores for exact, minor variation, and doctored quotes."""
        quote = "The committee decided to lower the policy rate by 25 basis points."

        # Exact match
        exact_text = "Official release: The committee decided to lower the policy rate by 25 basis points today."
        assert compute_quote_similarity(quote, exact_text) == 1.0

        # Minor punctuation or capitalization difference
        minor_text = "The committee decided to lower the policy rate by 25 basis points!"
        assert compute_quote_similarity(quote, minor_text) >= 0.95

        # Subtly doctored quote (liquidating gold reserves vs lowering rate)
        doctored_quote = "We are actively considering liquidating national gold reserves."
        reuters_text = "Prime Minister affirmed that national reserves remain fully secured at Geneva summit."
        assert compute_quote_similarity(doctored_quote, reuters_text) < 0.55

        # Empty inputs
        assert compute_quote_similarity("", exact_text) == 0.0
        assert compute_quote_similarity(quote, "") == 0.0

    def test_verify_quote_integrity_doctored_quote(self) -> None:
        """Verify that a doctored quote attributed to a real wire report is flagged as suspected mutation."""
        auditor = DomainAuditor()
        doctored_quote = "We are actively considering liquidating national gold reserves."

        # Real summit reporting covers the speech, but quote is absent / altered
        hits = [
            SearchHit(
                title="Reuters: Economic Summit Briefing",
                url="https://www.reuters.com/markets/summit-briefing-2026",
                snippet="Prime Minister affirmed that national reserves remain fully secured at Geneva summit and dismissed speculative currency rumors.",
                published_date="2026-11-19",
                source_query="prime minister gold reserves",
            )
        ]

        result = verify_quote_integrity(doctored_quote, hits, domain_auditor=auditor)

        assert result.has_verbatim_quote is True
        assert result.is_suspected_mutation is True
        assert result.best_match_score < 0.55
        assert "Suspected quote mutation" in result.integrity_note

    def test_verify_quote_integrity_exact_match(self) -> None:
        """Verify that an authentic quote matching C-SPAN or wire reporting scores >= 0.85 without mutation warning."""
        auditor = DomainAuditor()
        authentic_quote = "We must safeguard algorithmic transparency in civil infrastructure."

        hits = [
            SearchHit(
                title="C-SPAN: Algorithmic Oversight Hearing Transcript",
                url="https://www.c-span.org/video/?543210/hearing-transcript",
                snippet="Senator Jane Doe stated: 'We must safeguard algorithmic transparency in civil infrastructure' during morning testimony.",
                published_date="2026-11-19",
                source_query="algorithmic transparency civil infrastructure",
            )
        ]

        result = verify_quote_integrity(authentic_quote, hits, domain_auditor=auditor)

        assert result.has_verbatim_quote is True
        assert result.is_suspected_mutation is False
        assert result.best_match_score >= 0.85
        assert "Quote integrity verified" in result.integrity_note

    def test_verify_quote_integrity_no_quote(self) -> None:
        """Verify behavior when no verbatim quote was claimed."""
        result = verify_quote_integrity(None, [])
        assert result.has_verbatim_quote is False
        assert result.is_suspected_mutation is False
        assert result.best_match_score == 0.0


class TestLookalikeDomainDefense:
    def test_detect_lookalike_domain_patterns(self) -> None:
        """Verify that deceptive lookalike/typosquatted domains are detected across major protected brands."""
        assert detect_lookalike_domain("reuters-breaking-alert.com") == "reuters"
        assert detect_lookalike_domain("reuters-live.com") == "reuters"
        assert detect_lookalike_domain("reutersbreaking.com") == "reuters"
        assert detect_lookalike_domain("bbc-news-alert.co") == "bbc"
        assert detect_lookalike_domain("bbclive.com") == "bbc"
        assert detect_lookalike_domain("nytimes-online.org") == "nytimes"
        assert detect_lookalike_domain("nature-reports.net") == "nature"
        assert detect_lookalike_domain("bloomberg-feed.com") == "bloomberg"
        assert detect_lookalike_domain("thehindu-daily.com") == "thehindu"
        assert detect_lookalike_domain("c-span-news.org") == "c-span"

    def test_canonical_and_unrelated_domains_not_flagged(self) -> None:
        """Ensure canonical outlets and legitimate unrelated domains are never falsely flagged as lookalikes."""
        # Canonical outlets
        assert detect_lookalike_domain("reuters.com") is None
        assert detect_lookalike_domain("bbc.com") is None
        assert detect_lookalike_domain("bbc.co.uk") is None
        assert detect_lookalike_domain("nytimes.com") is None
        assert detect_lookalike_domain("nature.com") is None

        # Unrelated domains containing sub-tokens
        assert detect_lookalike_domain("signature.com") is None
        assert detect_lookalike_domain("google.com") is None
        assert detect_lookalike_domain("github.com") is None
        assert detect_lookalike_domain("x.com") is None
        assert detect_lookalike_domain("substack.com") is None

    def test_domain_auditor_lookalike_classification(self) -> None:
        """Verify that DomainAuditor classifies lookalike domains into Tier 4 with warning flag."""
        auditor = DomainAuditor()
        audit = auditor.audit_url("https://reuters-breaking-alert.com/markets/story/101")

        assert audit.tier == SourceTier.TIER_4_USER_GENERATED
        assert audit.is_lookalike is True
        assert audit.impersonated_brand == "reuters"
        assert "LOOKALIKE_DOMAIN_IMPERSONATION" in audit.warning_flags
        assert "reuters" in audit.notes.lower()

    def test_domain_auditor_evaluate_claim_blocks_lookalike(self) -> None:
        """Verify that evaluate_claim enforces DO_NOT_SHARE_UNCONFIRMED for lookalike sources."""
        auditor = DomainAuditor()
        audit_res = auditor.audit_url("https://reuters-breaking-alert.com/post/999")

        req = ClaimAuditRequest(
            claim_text="Central bank enacts emergency freeze on all outbound wire transfers.",
            sources=[
                SourceRecord(
                    url="https://reuters-breaking-alert.com/post/999",
                    domain_audit=audit_res,
                )
            ],
            alleged_venue="Wire Alert",
            alleged_date="2026-11-19",
        )

        audit = auditor.evaluate_claim(req)
        assert audit.verdict == ProvenanceVerdict.DO_NOT_SHARE_UNCONFIRMED
        assert audit.is_shareable is False
        assert "LOOKALIKE_DOMAIN_IMPERSONATION" in audit.warning_flags
        assert "LOOKALIKE DOMAIN IMPERSONATION" in audit.recommendation


class TestEndToEndPhase6Pipeline:
    def test_pipeline_catches_doctored_quote(self) -> None:
        """End-to-end verification: Pipeline flags doctored quote with QUOTE_MUTATION_DISTORTION."""
        claim = ExtractedClaim(
            claim_id="c-doctored",
            speaker="Prime Minister",
            verbatim_quote="We are actively considering liquidating national gold reserves.",
            normalized_claim="Prime Minister considers liquidating national gold reserves.",
            alleged_venue="Geneva Economic Summit",
            alleged_date="2026-11-19",
            cited_urls=["https://www.reuters.com/markets/summit-briefing-2026"],
            narrative_side="Side A",
            emotional_framing=EmotionalFraming(
                arousal_score=0.92,
                primary_emotion="fear",
                manipulation_cues=["attributed_quote_distortion"],
            ),
        )

        mock_search = MockSearchProvider(
            default_hits=[
                SearchHit(
                    title="Reuters: Economic Summit Briefing",
                    url="https://www.reuters.com/markets/summit-briefing-2026",
                    snippet="Prime Minister affirmed that national reserves remain fully secured at Geneva summit and dismissed speculative currency rumors.",
                    published_date="2026-11-19",
                    source_query="gold reserves",
                )
            ]
        )

        investigator = ProvenanceInvestigator(search_provider=mock_search)
        audit_res = investigator.investigate_claim(claim)

        assert audit_res.verdict == ProvenanceVerdict.DO_NOT_SHARE_UNCONFIRMED
        assert audit_res.is_shareable is False
        assert "QUOTE_MUTATION_DISTORTION" in audit_res.warning_flags
        assert "DOCTORED / MUTATED QUOTE" in audit_res.recommendation

    def test_pipeline_catches_lookalike_domain(self) -> None:
        """End-to-end verification: Pipeline flags lookalike domain with LOOKALIKE_DOMAIN_IMPERSONATION."""
        claim = ExtractedClaim(
            claim_id="c-lookalike",
            speaker="Viral Alert",
            verbatim_quote=None,
            normalized_claim="Emergency wire transfer freeze enacted.",
            alleged_venue="Breaking Feed",
            alleged_date="2026-11-19",
            cited_urls=["https://reuters-breaking-alert.com/post/999"],
            narrative_side="Side A",
            emotional_framing=EmotionalFraming(
                arousal_score=0.95,
                primary_emotion="panic",
                manipulation_cues=["lookalike_domain_spoofing"],
            ),
        )

        mock_search = MockSearchProvider(
            default_hits=[
                SearchHit(
                    title="Reuters Breaking Alert",
                    url="https://reuters-breaking-alert.com/post/999",
                    snippet="Unverified wire freeze claims published on lookalike domain.",
                    published_date="2026-11-19",
                    source_query="wire freeze",
                )
            ]
        )

        investigator = ProvenanceInvestigator(search_provider=mock_search)
        audit_res = investigator.investigate_claim(claim)

        assert audit_res.verdict == ProvenanceVerdict.DO_NOT_SHARE_UNCONFIRMED
        assert audit_res.is_shareable is False
        assert "LOOKALIKE_DOMAIN_IMPERSONATION" in audit_res.warning_flags


class TestPreShareWebUI:
    def test_render_web_ui_html_structure(self) -> None:
        """Verify that render_web_ui generates self-contained HTML with required controls and bookmarklet."""
        html_content = render_web_ui(prefill_claim="Breaking tech alert")

        assert "<!DOCTYPE html>" in html_content
        assert "Epistemic Guard" in html_content
        assert "Single-Claim Quick Check" in html_content
        assert "Two-Sided Listening Studio" in html_content
        assert "Browser Bookmarklet" in html_content
        assert "javascript:(function()" in html_content
        assert "Breaking tech alert" in html_content

    def test_fastapi_web_ui_endpoint(self) -> None:
        """Verify GET / on FastAPI serves 200 OK text/html with Pre-Share Friction Studio."""
        client = TestClient(create_app())
        response = client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Epistemic Guard" in response.text
        assert "Audit Provenance" in response.text

    def test_fastapi_web_ui_prefill_query_param(self) -> None:
        """Verify GET /?claim=... properly injects the pre-filled quote."""
        client = TestClient(create_app())
        response = client.get("/?claim=Test%20Viral%20Rumor")

        assert response.status_code == 200
        assert "Test Viral Rumor" in response.text
