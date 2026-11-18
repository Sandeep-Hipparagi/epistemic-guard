from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest

from epistemic_guard.extraction.extractor import ClaimExtractor, extract_urls
from epistemic_guard.llm.client import StructuredLLMClient, clean_json_payload
from epistemic_guard.schemas import (
    ClaimAuditRequest,
    EmotionalFraming,
    EvidenceType,
    ExtractedClaim,
    ExtractionBatchResult,
    ProvenanceVerdict,
    SourceTier,
)
from epistemic_guard.tools.domain_auditor import DomainAuditor


class TestURLExtractor:
    def test_extract_urls_from_noisy_social_media(self) -> None:
        raw_text = (
            "BREAKING!!! Watch this insane clip: https://x.com/user/status/123456789. "
            "Also reported on (https://reuters.com/world/article-999), and www.bbc.com/news/live! "
            "Is this real??? Check http://apnews.com/article/111, or https://x.com/user/status/123456789"
        )
        urls = extract_urls(raw_text)

        assert "https://x.com/user/status/123456789" in urls
        assert "https://reuters.com/world/article-999" in urls
        assert "https://www.bbc.com/news/live" in urls
        assert "http://apnews.com/article/111" in urls
        # Check deduplication
        assert len(urls) == 4

    def test_extract_urls_empty_and_no_urls(self) -> None:
        assert extract_urls("") == []
        assert extract_urls("No urls mentioned anywhere in this sentence.") == []

    def test_extract_urls_punctuation_stripping(self) -> None:
        text = "Visit <https://apnews.com/wire>, or [https://nature.com/articles/123]! End."
        urls = extract_urls(text)
        assert urls == ["https://apnews.com/wire", "https://nature.com/articles/123"]


class TestStructuredLLMClientUtils:
    def test_clean_json_payload_markdown_fences(self) -> None:
        raw_md = "```json\n{\"foo\": \"bar\"}\n```"
        assert clean_json_payload(raw_md) == '{"foo": "bar"}'

        raw_fence_no_json = "```\n{\"foo\": \"bar\"}\n```"
        assert clean_json_payload(raw_fence_no_json) == '{"foo": "bar"}'

    def test_clean_json_payload_conversational_wrapping(self) -> None:
        raw_convo = "Sure! Here is the JSON output you requested:\n{\"status\": \"ok\", \"count\": 3}\nHope this helps!"
        cleaned = clean_json_payload(raw_convo)
        assert json.loads(cleaned) == {"status": "ok", "count": 3}

    def test_render_messages(self) -> None:
        client = StructuredLLMClient()
        messages = client.render_messages("claim_extraction", raw_text="Test statement text.")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert "ZERO-HALLUCINATION" in messages[0]["content"]
        assert messages[1]["role"] == "user"
        assert "Test statement text." in messages[1]["content"]


class TestExtractedClaimToAuditRequest:
    def test_to_audit_request_handoff(self) -> None:
        claim = ExtractedClaim(
            claim_id="claim-001",
            speaker="Official Spokesperson",
            verbatim_quote="Energy exports will resume by midnight.",
            normalized_claim="Energy exports resume by midnight.",
            alleged_venue="Ministry Press Room",
            alleged_date="2026-11-19",
            cited_urls=["https://apnews.com/article/energy-exports"],
            narrative_side="Side A",
            emotional_framing=EmotionalFraming(
                arousal_score=0.35,
                primary_emotion="relief",
                manipulation_cues=[],
            ),
        )

        req = claim.to_audit_request()
        assert isinstance(req, ClaimAuditRequest)
        assert req.claim_text == "Energy exports resume by midnight."
        assert req.speaker_or_subject == "Official Spokesperson"
        assert req.alleged_venue == "Ministry Press Room"
        assert req.alleged_date == "2026-11-19"
        assert req.emotional_intensity_score == 0.35
        assert len(req.sources) == 1
        assert req.sources[0].url == "https://apnews.com/article/energy-exports"
        assert req.sources[0].quote_excerpt == "Energy exports will resume by midnight."
        assert "Side A" in (req.context_notes or "")


class TestClaimExtractorEndToEnd:
    @pytest.fixture
    def mock_llm_client(self) -> StructuredLLMClient:
        client = StructuredLLMClient()
        client._client = MagicMock()
        return client

    def test_extract_empty_text(self, mock_llm_client: StructuredLLMClient) -> None:
        extractor = ClaimExtractor(llm_client=mock_llm_client)
        result = extractor.extract("   ")
        assert result.claims == []
        assert result.overall_emotional_intensity == 0.0
        assert len(result.raw_text_hash) == 64

    def test_viral_fake_quote_high_outrage_do_not_share(
        self,
        mock_llm_client: StructuredLLMClient,
    ) -> None:
        """Scenario: Viral outrage quote on social media with no date or primary media -> DO_NOT_SHARE_UNCONFIRMED."""
        raw_text = (
            "OUTRAGEOUS!! Leaked audio reveals Governor saying: 'We will cut power to opposition districts!' "
            "See the viral thread here: https://x.com/viral_anonymous/status/123456789"
        )

        fake_batch = ExtractionBatchResult(
            raw_text_hash="dummy_hash",
            overall_emotional_intensity=0.91,
            claims=[
                ExtractedClaim(
                    claim_id="claim-viral-001",
                    speaker="Governor",
                    verbatim_quote="We will cut power to opposition districts!",
                    normalized_claim="Governor stated intention to cut power to political opposition districts.",
                    alleged_venue="X / Twitter Post",
                    alleged_date=None,  # Zero-hallucination: date is absent in input
                    cited_urls=["https://x.com/viral_anonymous/status/123456789"],
                    narrative_side="Side A",
                    emotional_framing=EmotionalFraming(
                        arousal_score=0.91,
                        primary_emotion="outrage",
                        manipulation_cues=["all_caps_urgency", "unverified_screenshot_appeal"],
                    ),
                )
            ],
        )

        # Mock structured LLM response
        with patch.object(mock_llm_client, "generate_structured", return_value=fake_batch):
            extractor = ClaimExtractor(llm_client=mock_llm_client)
            audited_pairs = extractor.extract_and_audit(raw_text)

        assert len(audited_pairs) == 1
        claim, audit_result = audited_pairs[0]

        # Assertions bridging Phase 1 to Phase 0
        assert claim.speaker == "Governor"
        assert claim.alleged_date is None
        assert claim.emotional_framing.arousal_score == 0.91
        assert audit_result.verdict == ProvenanceVerdict.DO_NOT_SHARE_UNCONFIRMED
        assert audit_result.is_shareable is False
        assert audit_result.is_safe_to_share() is False
        assert "SOLE_SOURCE_UNVERIFIED_UGC" in audit_result.warning_flags
        assert "MISSING_TIMESTAMP_RECYCLED_RISK" in audit_result.warning_flags
        assert "DO NOT SHARE" in audit_result.recommendation

    def test_verified_primary_statement_reuters_and_briefing(
        self,
        mock_llm_client: StructuredLLMClient,
    ) -> None:
        """Scenario: Verified primary announcement at official briefing reported by Reuters wire."""
        raw_text = (
            "Federal Reserve Chairman announced: 'The committee decided to lower the policy rate by 25 basis points.' "
            "Delivered today at the Federal Reserve Press Briefing: https://www.reuters.com/markets/us/fed-rate-cut-2026"
        )

        verified_batch = ExtractionBatchResult(
            raw_text_hash="dummy_hash",
            overall_emotional_intensity=0.15,
            claims=[
                ExtractedClaim(
                    claim_id="claim-verified-001",
                    speaker="Federal Reserve Chairman",
                    verbatim_quote="The committee decided to lower the policy rate by 25 basis points.",
                    normalized_claim="Federal Reserve lowers benchmark interest rate by 25 basis points.",
                    alleged_venue="Federal Reserve Press Briefing",
                    alleged_date="2026-11-19",
                    cited_urls=["https://www.reuters.com/markets/us/fed-rate-cut-2026"],
                    narrative_side="Neutral",
                    emotional_framing=EmotionalFraming(
                        arousal_score=0.15,
                        primary_emotion="neutral",
                        manipulation_cues=[],
                    ),
                )
            ],
        )

        with patch.object(mock_llm_client, "generate_structured", return_value=verified_batch):
            extractor = ClaimExtractor(llm_client=mock_llm_client)
            audited_pairs = extractor.extract_and_audit(raw_text)

        assert len(audited_pairs) == 1
        claim, audit_result = audited_pairs[0]

        assert claim.speaker == "Federal Reserve Chairman"
        assert claim.alleged_venue == "Federal Reserve Press Briefing"
        assert claim.alleged_date == "2026-11-19"
        assert audit_result.verdict == ProvenanceVerdict.VERIFIED_PRIMARY
        assert audit_result.is_shareable is True
        assert audit_result.is_safe_to_share() is True
        assert audit_result.where.is_identified is True
        assert audit_result.where.is_primary_venue is True
        assert len(audit_result.warning_flags) == 0

    def test_url_reconciliation_injects_unmapped_regex_urls(
        self,
        mock_llm_client: StructuredLLMClient,
    ) -> None:
        """Test that URLs found in text by regex are deterministically preserved even if LLM missed them."""
        raw_text = "Statement without URL in LLM output https://apnews.com/article/123"

        batch_without_urls = ExtractionBatchResult(
            raw_text_hash="hash",
            overall_emotional_intensity=0.2,
            claims=[
                ExtractedClaim(
                    claim_id="c1",
                    speaker=None,
                    verbatim_quote=None,
                    normalized_claim="Test claim",
                    alleged_venue=None,
                    alleged_date=None,
                    cited_urls=[],  # LLM returned empty list
                    narrative_side="Neutral",
                    emotional_framing=EmotionalFraming(
                        arousal_score=0.2,
                        primary_emotion="neutral",
                        manipulation_cues=[],
                    ),
                )
            ],
        )

        with patch.object(mock_llm_client, "generate_structured", return_value=batch_without_urls):
            extractor = ClaimExtractor(llm_client=mock_llm_client)
            result = extractor.extract(raw_text)

        # Assert that regex detected URL was reconciled into the claim
        assert "https://apnews.com/article/123" in result.claims[0].cited_urls
