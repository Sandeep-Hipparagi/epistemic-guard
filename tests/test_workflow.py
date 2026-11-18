from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from epistemic_guard.extraction.extractor import ClaimExtractor
from epistemic_guard.graph.workflow import EpistemicGuardPipeline, build_epistemic_graph
from epistemic_guard.llm.client import StructuredLLMClient
from epistemic_guard.schemas import (
    EmotionalFraming,
    ExtractedClaim,
    ExtractionBatchResult,
    SideNarrativeDraft,
    SynthesisLLMOutput,
    TwoSidedListeningReport,
)
from epistemic_guard.tools.provenance_resolver import ProvenanceInvestigator
from epistemic_guard.tools.search import MockSearchProvider, SearchHit


class TestEpistemicGuardPipeline:
    @pytest.fixture
    def mock_llm_client(self) -> StructuredLLMClient:
        client = StructuredLLMClient()
        client._client = MagicMock()
        return client

    def test_asymmetric_viral_controversy(self, mock_llm_client: StructuredLLMClient) -> None:
        """TEST 1: Asymmetric Viral Controversy.

        Side A cites a verifiable reuters.com statement (is_shareable=True).
        Side B pushes a high-outrage (0.93) viral x.com quote with no date (DO_NOT_SHARE_UNCONFIRMED).
        Verifies:
          - provenance_asymmetry_detected is True
          - Side A verified_shareable_count == 1
          - Side B unconfirmed_blocked_count == 1
          - Fair steel-manned perspectives generated for both
        """
        side_a_claim = ExtractedClaim(
            claim_id="claim-side-a",
            speaker="Official Envoy",
            verbatim_quote="The bilateral trade accord has been ratified.",
            normalized_claim="Bilateral trade accord officially ratified.",
            alleged_venue="Geneva Summit",
            alleged_date="2026-11-19",
            cited_urls=["https://www.reuters.com/markets/trade-accord-2026"],
            narrative_side="Side A",
            emotional_framing=EmotionalFraming(
                arousal_score=0.25,
                primary_emotion="relief",
                manipulation_cues=[],
            ),
        )

        side_b_claim = ExtractedClaim(
            claim_id="claim-side-b",
            speaker="Opposition Activist",
            verbatim_quote="They secretly surrendered all domestic manufacturing rights!",
            normalized_claim="Accord secretly surrenders domestic manufacturing rights.",
            alleged_venue="X / Twitter Post",
            alleged_date=None,  # Missing date
            cited_urls=["https://x.com/viral_critic/status/987654321"],
            narrative_side="Side B",
            emotional_framing=EmotionalFraming(
                arousal_score=0.93,
                primary_emotion="outrage",
                manipulation_cues=["all_caps_urgency", "unverified_screenshot_appeal"],
            ),
        )

        extraction_batch = ExtractionBatchResult(
            raw_text_hash="hash_asymmetry",
            overall_emotional_intensity=0.59,
            claims=[side_a_claim, side_b_claim],
        )

        synthesis_output = SynthesisLLMOutput(
            topic_title="Bilateral Trade Accord Controversy",
            side_drafts=[
                SideNarrativeDraft(
                    side_label="Side A",
                    steel_manned_summary="Advocates argue the treaty secures critical market stability and economic growth.",
                    key_arguments=["Formal ratification documented in Geneva.", "Secures international trade access."],
                ),
                SideNarrativeDraft(
                    side_label="Side B",
                    steel_manned_summary="Critics raise concerns regarding long-term risks to domestic manufacturing competitiveness.",
                    key_arguments=["Sovereignty over manufacturing regulations.", "Lack of public review."],
                ),
            ],
            deescalation_guidance=(
                "Provenance asymmetry detected: Side A's ratification is confirmed by wire reporting, "
                "while viral claims of secret manufacturing surrender remain unconfirmed on social media. "
                "Verify primary documents before sharing."
            ),
        )

        # Mock Search: Side A finds Reuters wire; Side B finds only social media posts
        mock_search = MockSearchProvider()
        mock_search.register_response(
            "ratified",
            [
                SearchHit(
                    title="Reuters Trade Accord Ratified",
                    url="https://www.reuters.com/markets/trade-accord-2026",
                    snippet="Official ratification verified in Geneva today.",
                    published_date="2026-11-19",
                    source_query="trade accord ratified",
                )
            ],
        )
        mock_search.register_response(
            "surrender",
            [
                SearchHit(
                    title="Viral critique on X",
                    url="https://x.com/viral_critic/status/987654321",
                    snippet="Secret surrender allegations circulating on social media.",
                    published_date=None,
                    source_query="secret surrender",
                )
            ],
        )

        def mock_generate_structured(prompt_name, response_model, prompt_vars=None):
            if prompt_name == "claim_extraction":
                return extraction_batch
            elif prompt_name == "two_sided_synthesis":
                return synthesis_output
            raise ValueError(f"Unexpected prompt {prompt_name}")

        with patch.object(mock_llm_client, "generate_structured", side_effect=mock_generate_structured):
            extractor = ClaimExtractor(llm_client=mock_llm_client)
            investigator = ProvenanceInvestigator(search_provider=mock_search)
            pipeline = EpistemicGuardPipeline(
                extractor=extractor,
                investigator=investigator,
                llm_client=mock_llm_client,
            )

            ref_now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
            report = pipeline.analyze(
                texts=[
                    "Envoy announces trade accord: https://www.reuters.com/markets/trade-accord-2026",
                    "OUTRAGE!! Secret surrender leaked: https://x.com/viral_critic/status/987654321",
                ],
                reference_now=ref_now,
            )

        assert isinstance(report, TwoSidedListeningReport)
        assert report.topic == "Bilateral Trade Accord Controversy"
        assert report.provenance_asymmetry_detected is True
        assert len(report.perspectives) == 2

        side_a_summary = next(p for p in report.perspectives if p.side_label == "Side A")
        assert side_a_summary.verified_shareable_count == 1
        assert side_a_summary.unconfirmed_blocked_count == 0
        assert side_a_summary.total_claims == 1
        assert "Advocates argue" in side_a_summary.steel_manned_summary

        side_b_summary = next(p for p in report.perspectives if p.side_label == "Side B")
        assert side_b_summary.verified_shareable_count == 0
        assert side_b_summary.unconfirmed_blocked_count == 1
        assert side_b_summary.total_claims == 1
        assert side_b_summary.average_emotional_arousal == 0.93
        assert "Critics raise concerns" in side_b_summary.steel_manned_summary

    def test_both_sides_unconfirmed_outrage_spiral(self, mock_llm_client: StructuredLLMClient) -> None:
        """TEST 2: Both Sides Unconfirmed Outrage Spiral.

        Both Side A and Side B rely exclusively on unverified social screenshots and rumors.
        Verifies:
          - Both sides have verified_shareable_count == 0
          - provenance_asymmetry_detected is False (symmetric epistemic deficiency)
          - has_high_emotional_contagion is True
          - Zero claims are marked shareable
        """
        claim_a = ExtractedClaim(
            claim_id="claim-a-rumor",
            speaker="User Alpha",
            verbatim_quote="Opposing faction is planning a violent riot tonight!",
            normalized_claim="Opposing faction planning violent riot tonight.",
            alleged_venue="Telegram Channel",
            alleged_date=None,
            cited_urls=["https://t.me/channel_alpha/123"],
            narrative_side="Side A",
            emotional_framing=EmotionalFraming(
                arousal_score=0.95,
                primary_emotion="fear",
                manipulation_cues=["all_caps_urgency"],
            ),
        )

        claim_b = ExtractedClaim(
            claim_id="claim-b-rumor",
            speaker="User Beta",
            verbatim_quote="The other side has already poisoned the municipal reservoir!",
            normalized_claim="Opposing side poisoned municipal reservoir.",
            alleged_venue="X / Twitter",
            alleged_date=None,
            cited_urls=["https://x.com/user_beta/status/456"],
            narrative_side="Side B",
            emotional_framing=EmotionalFraming(
                arousal_score=0.98,
                primary_emotion="moral_disgust",
                manipulation_cues=["catastrophic_hyperbole"],
            ),
        )

        extraction_batch = ExtractionBatchResult(
            raw_text_hash="hash_outrage_spiral",
            overall_emotional_intensity=0.965,
            claims=[claim_a, claim_b],
        )

        synthesis_output = SynthesisLLMOutput(
            topic_title="Viral Polarization and Escalating Rumors",
            side_drafts=[
                SideNarrativeDraft(
                    side_label="Side A",
                    steel_manned_summary="Fears of impending public unrest and violence.",
                    key_arguments=["Public safety concerns."],
                ),
                SideNarrativeDraft(
                    side_label="Side B",
                    steel_manned_summary="Severe alarms regarding critical municipal infrastructure sabotage.",
                    key_arguments=["Water security."],
                ),
            ],
            deescalation_guidance=(
                "CRITICAL WARNING: High emotional contagion detected across both sides. "
                "Neither assertion is substantiated by primary media, local law enforcement, or accountable journalism. "
                "DO NOT SHARE unconfirmed crisis rumors."
            ),
        )

        # Mock search returns only Tier 4 social links
        mock_search = MockSearchProvider(
            default_hits=[
                SearchHit(
                    title="Telegram post rumor",
                    url="https://t.me/channel_alpha/123",
                    snippet="Riot rumors on Telegram.",
                    published_date=None,
                    source_query="riot",
                ),
                SearchHit(
                    title="X post rumor",
                    url="https://x.com/user_beta/status/456",
                    snippet="Reservoir rumors on X.",
                    published_date=None,
                    source_query="reservoir",
                ),
            ]
        )

        def mock_generate_structured(prompt_name, response_model, prompt_vars=None):
            if prompt_name == "claim_extraction":
                return extraction_batch
            elif prompt_name == "two_sided_synthesis":
                return synthesis_output
            raise ValueError(f"Unexpected prompt {prompt_name}")

        with patch.object(mock_llm_client, "generate_structured", side_effect=mock_generate_structured):
            extractor = ClaimExtractor(llm_client=mock_llm_client)
            investigator = ProvenanceInvestigator(search_provider=mock_search)
            pipeline = EpistemicGuardPipeline(
                extractor=extractor,
                investigator=investigator,
                llm_client=mock_llm_client,
            )

            report = pipeline.analyze(
                texts=["Viral thread alpha https://t.me/channel_alpha/123", "Viral thread beta https://x.com/user_beta/status/456"]
            )

        assert report.provenance_asymmetry_detected is False
        assert report.has_high_emotional_contagion is True
        assert report.overall_emotional_temperature >= 0.90
        assert all(p.verified_shareable_count == 0 for p in report.perspectives)
        assert all(not it.audit.is_safe_to_share() for it in report.audited_claims)

    def test_single_post_input_convenience(self, mock_llm_client: StructuredLLMClient) -> None:
        """TEST 3: Single-Post Input Convenience.

        Passing a single string instead of list[str] runs cleanly end-to-end.
        """
        claim = ExtractedClaim(
            claim_id="claim-single",
            speaker="City Official",
            verbatim_quote="Transit repairs will complete by 5 PM.",
            normalized_claim="Transit repairs will complete by 5 PM.",
            alleged_venue="Official City Podium",
            alleged_date="2026-11-19",
            cited_urls=["https://apnews.com/article/transit-update"],
            narrative_side="Neutral",
            emotional_framing=EmotionalFraming(
                arousal_score=0.2,
                primary_emotion="neutral",
                manipulation_cues=[],
            ),
        )
        batch = ExtractionBatchResult(
            raw_text_hash="single_hash",
            overall_emotional_intensity=0.2,
            claims=[claim],
        )
        synthesis = SynthesisLLMOutput(
            topic_title="City Transit Update",
            side_drafts=[
                SideNarrativeDraft(
                    side_label="Neutral",
                    steel_manned_summary="Routine municipal infrastructure announcement.",
                    key_arguments=["Repairs timeline confirmed."],
                )
            ],
            deescalation_guidance="Verified city dispatch. Suitable to reference.",
        )

        mock_search = MockSearchProvider(
            default_hits=[
                SearchHit(
                    title="AP News - City Transit Update",
                    url="https://apnews.com/article/transit-update",
                    snippet="Official city transit announcement today.",
                    published_date="2026-11-19",
                    source_query="transit repairs",
                )
            ]
        )

        def mock_generate_structured(prompt_name, response_model, prompt_vars=None):
            if prompt_name == "claim_extraction":
                return batch
            elif prompt_name == "two_sided_synthesis":
                return synthesis
            raise ValueError(f"Unexpected prompt {prompt_name}")

        with patch.object(mock_llm_client, "generate_structured", side_effect=mock_generate_structured):
            extractor = ClaimExtractor(llm_client=mock_llm_client)
            investigator = ProvenanceInvestigator(search_provider=mock_search)
            pipeline = EpistemicGuardPipeline(
                extractor=extractor,
                investigator=investigator,
                llm_client=mock_llm_client,
            )

            # Passing single string directly!
            report = pipeline.analyze("City Official announces: Transit repairs complete by 5 PM. https://apnews.com/article/transit-update")

        assert isinstance(report, TwoSidedListeningReport)
        assert report.topic == "City Transit Update"
        assert len(report.perspectives) == 1
        assert report.perspectives[0].verified_shareable_count == 1
