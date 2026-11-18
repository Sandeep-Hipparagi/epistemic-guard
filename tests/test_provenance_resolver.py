from __future__ import annotations

from datetime import datetime, timezone
import pytest

from epistemic_guard.schemas import (
    EmotionalFraming,
    EvidenceType,
    ExtractedClaim,
    ProvenanceVerdict,
    SourceTier,
)
from epistemic_guard.tools.domain_auditor import DomainAuditor
from epistemic_guard.tools.provenance_resolver import (
    ProvenanceInvestigator,
    infer_evidence_for_url,
)
from epistemic_guard.tools.search import (
    MockSearchProvider,
    SearchHit,
    build_provenance_queries,
)
from epistemic_guard.tools.temporal import (
    evaluate_temporal_consistency,
    extract_date_from_url,
    parse_flexible_date,
)


class TestSearchQueryConstruction:
    def test_build_provenance_queries_with_quote_and_speaker(self) -> None:
        claim = ExtractedClaim(
            claim_id="c1",
            speaker="Senator Davis",
            verbatim_quote="The new economic sanctions will take effect next Monday.",
            normalized_claim="New economic sanctions take effect next Monday.",
            alleged_venue="Senate Chamber",
            alleged_date="2026-11-19",
            cited_urls=[],
            narrative_side="Side A",
            emotional_framing=EmotionalFraming(
                arousal_score=0.4,
                primary_emotion="neutral",
                manipulation_cues=[],
            ),
        )
        queries = build_provenance_queries(claim)

        # 3 queries expected: exact quote, primary media, named outlet
        assert len(queries) == 3
        assert '"The new economic sanctions will take effect next Monday." Senator Davis' in queries[0]
        assert "Senator Davis New economic sanctions take effect next Monday. (video OR transcript OR" in queries[1]
        assert "Senator Davis New economic sanctions take effect next Monday. (reuters OR apnews OR" in queries[2]

    def test_build_provenance_queries_without_verbatim_quote(self) -> None:
        claim = ExtractedClaim(
            claim_id="c2",
            speaker=None,
            verbatim_quote=None,
            normalized_claim="City subway line closed indefinitely due to flooding.",
            alleged_venue=None,
            alleged_date=None,
            cited_urls=[],
            narrative_side="Neutral",
            emotional_framing=EmotionalFraming(
                arousal_score=0.7,
                primary_emotion="fear",
                manipulation_cues=[],
            ),
        )
        queries = build_provenance_queries(claim)
        # Only primary media and named outlet queries
        assert len(queries) == 2
        assert "City subway line closed indefinitely due to flooding. (video OR" in queries[0]
        assert "City subway line closed indefinitely due to flooding. (reuters OR" in queries[1]


class TestTemporalDriftAnalysis:
    def test_parse_flexible_date(self) -> None:
        dt1 = parse_flexible_date("2026-11-19T14:30:00Z")
        assert dt1 is not None
        assert dt1.year == 2026
        assert dt1.month == 11
        assert dt1.day == 19
        assert dt1.tzinfo == timezone.utc

        dt2 = parse_flexible_date("March 15, 2021")
        assert dt2 is not None
        assert dt2.year == 2021
        assert dt2.month == 3
        assert dt2.day == 15

        assert parse_flexible_date("") is None
        assert parse_flexible_date(None) is None

    def test_extract_date_from_url(self) -> None:
        url1 = "https://www.bbc.com/news/world-2021-03-15-56400000"
        dt1 = extract_date_from_url(url1)
        assert dt1 is not None
        assert dt1.year == 2021
        assert dt1.month == 3
        assert dt1.day == 15

        url2 = "https://www.nytimes.com/2026/11/19/us/politics/election.html"
        dt2 = extract_date_from_url(url2)
        assert dt2 is not None
        assert dt2.year == 2026
        assert dt2.month == 11
        assert dt2.day == 19

    def test_evaluate_temporal_consistency_recycled_old_news(self) -> None:
        ref_now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
        hits = [
            SearchHit(
                title="Historic Accord Signed",
                url="https://www.reuters.com/world/accord-2021-03-10",
                snippet="World leaders signed the accord today.",
                published_date="2021-03-10",
                source_query="test query",
            )
        ]
        # Claim alleged date is 2026-11-19, but hit was published in March 2021 (~2080 days earlier)
        result = evaluate_temporal_consistency(
            alleged_date="2026-11-19",
            hits=hits,
            reference_now=ref_now,
            drift_threshold_days=30,
        )
        assert result.is_recycled_old_content is True
        assert result.drift_days is not None
        assert result.drift_days > 1000
        assert "Recycled Content Warning" in result.temporal_note

    def test_evaluate_temporal_consistency_contemporary(self) -> None:
        ref_now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
        hits = [
            SearchHit(
                title="Current Event",
                url="https://apnews.com/article/today-event",
                snippet="Event happening today.",
                published_date="2026-11-19",
                source_query="test",
            )
        ]
        result = evaluate_temporal_consistency(
            alleged_date="2026-11-19",
            hits=hits,
            reference_now=ref_now,
            drift_threshold_days=30,
        )
        assert result.is_recycled_old_content is False
        assert result.drift_days == 0
        assert "Temporal consistency verified" in result.temporal_note


class TestEvidenceInference:
    def test_infer_evidence_youtube_and_cspan(self) -> None:
        ev_yt, is_prim_yt = infer_evidence_for_url("https://www.youtube.com/watch?v=123", SourceTier.TIER_4_USER_GENERATED)
        assert ev_yt == EvidenceType.VIDEO
        assert is_prim_yt is True

        ev_cs, is_prim_cs = infer_evidence_for_url("https://www.c-span.org/video/?54321/hearing-transcript", SourceTier.TIER_2_ESTABLISHED_EDITORIAL)
        assert ev_cs in (EvidenceType.VIDEO, EvidenceType.TRANSCRIPT)
        assert is_prim_cs is True


class TestProvenanceInvestigatorScenarios:
    """Rigorous end-to-end tests for Phase 2 retrieval, corroboration, and defense invariants."""

    def test_circular_reporting_trap_remains_do_not_share(self) -> None:
        """TEST 1: Circular Reporting Defense.

        A viral unlinked claim returns multiple social media (x.com) posts and unknown unverified
        blogs. It MUST NOT count circular UGC repetition as corroboration and must remain DO_NOT_SHARE_UNCONFIRMED.
        """
        claim = ExtractedClaim(
            claim_id="claim-viral-circular-01",
            speaker="Unknown Source",
            verbatim_quote="Major city announces sudden complete blackout!",
            normalized_claim="Major city announces sudden complete blackout.",
            alleged_venue="X / Twitter Post",
            alleged_date=None,
            cited_urls=["https://x.com/viral_account_1/status/111"],
            narrative_side="Side A",
            emotional_framing=EmotionalFraming(
                arousal_score=0.95,
                primary_emotion="panic",
                manipulation_cues=["all_caps_urgency"],
            ),
        )

        # Mock search returns ONLY social media echo chambers and unknown blogs
        mock_provider = MockSearchProvider(
            default_hits=[
                SearchHit(
                    title="Viral Blackout Rumor",
                    url="https://x.com/viral_account_2/status/222",
                    snippet="Did you hear about the blackout?",
                    published_date=None,
                    source_query="blackout",
                ),
                SearchHit(
                    title="Blackout post on Reddit",
                    url="https://www.reddit.com/r/conspiracy/comments/333",
                    snippet="Everyone is talking about the blackout.",
                    published_date=None,
                    source_query="blackout",
                ),
                SearchHit(
                    title="Random Blog Post",
                    url="https://random-unverified-blog-xyz999.io/post/444",
                    snippet="Unconfirmed rumors of blackout.",
                    published_date=None,
                    source_query="blackout",
                ),
            ]
        )

        investigator = ProvenanceInvestigator(search_provider=mock_provider)
        result = investigator.investigate_claim(claim)

        # Circular reporting defense invariant:
        assert result.verdict == ProvenanceVerdict.DO_NOT_SHARE_UNCONFIRMED
        assert result.is_shareable is False
        assert result.is_safe_to_share() is False
        assert any("NO_PRIMARY_MEDIA_OR_NAMED_OUTLET" in flag or "SOLE_SOURCE_UNVERIFIED_UGC" in flag for flag in result.warning_flags)

    def test_corroborated_upgrade_primary_wire_and_cspan(self) -> None:
        """TEST 2: Corroborated Upgrade.

        An unlinked viral quote is actively investigated via search and corroborated
        by Reuters wire reporting and a C-SPAN hearing transcript. Upgrades to VERIFIED_PRIMARY.
        """
        claim = ExtractedClaim(
            claim_id="claim-upgrade-01",
            speaker="Federal Reserve Chairman",
            verbatim_quote="The committee decided to lower the policy rate by 25 basis points.",
            normalized_claim="Federal Reserve lowers benchmark interest rate by 25 basis points.",
            alleged_venue="Federal Reserve Press Briefing",
            alleged_date="2026-11-19",
            cited_urls=[],  # Initially unlinked!
            narrative_side="Neutral",
            emotional_framing=EmotionalFraming(
                arousal_score=0.2,
                primary_emotion="neutral",
                manipulation_cues=[],
            ),
        )

        # Mock search finds Reuters reporting and C-SPAN transcript with contemporary date
        mock_provider = MockSearchProvider(
            default_hits=[
                SearchHit(
                    title="Fed Lowers Rate - Reuters",
                    url="https://www.reuters.com/markets/us/fed-rate-cut-2026",
                    snippet="The Federal Reserve cut rates today during the official press briefing: 'The committee decided to lower the policy rate by 25 basis points.'",
                    published_date="2026-11-19",
                    source_query="fed rate cut",
                ),
                SearchHit(
                    title="C-SPAN Fed Briefing Transcript",
                    url="https://www.c-span.org/video/?59999/federal-reserve-briefing-transcript",
                    snippet="Full official transcript of the Federal Reserve press conference.",
                    published_date="2026-11-19",
                    source_query="fed rate cut",
                ),
            ]
        )

        ref_now = datetime(2026, 11, 19, 16, 0, tzinfo=timezone.utc)
        investigator = ProvenanceInvestigator(search_provider=mock_provider)
        result = investigator.investigate_claim(claim, reference_now=ref_now)

        assert result.verdict == ProvenanceVerdict.VERIFIED_PRIMARY
        assert result.is_shareable is True
        assert result.is_safe_to_share() is True
        assert result.where.is_identified is True
        assert result.when.is_exact_timestamp is True or result.when.date_str is not None
        assert result.evidence.has_primary_media is True or result.evidence.has_named_outlet is True
        assert len(result.warning_flags) == 0

    def test_recycled_old_quote_trap_blocks_sharing(self) -> None:
        """TEST 3: Recycled Old Content Defense.

        A claim presented as breaking news in November 2026 matches a genuine BBC article
        published in March 2021. Flags TEMPORAL_DRIFT_RECYCLED_CONTENT and blocks sharing.
        """
        claim = ExtractedClaim(
            claim_id="claim-recycled-01",
            speaker="Prime Minister",
            verbatim_quote="Border closures will be instituted immediately across all ports.",
            normalized_claim="Prime Minister institutes immediate border closures across all ports.",
            alleged_venue="National Address",
            alleged_date=None,  # Presented as current/breaking viral claim without historical date
            cited_urls=[],
            narrative_side="Side A",
            emotional_framing=EmotionalFraming(
                arousal_score=0.88,
                primary_emotion="fear",
                manipulation_cues=["catastrophic_hyperbole"],
            ),
        )

        # Discovered report is genuine BBC, but from 2021!
        mock_provider = MockSearchProvider(
            default_hits=[
                SearchHit(
                    title="BBC News - Historic Border Closures",
                    url="https://www.bbc.com/news/world-2021-03-15-56400000",
                    snippet="Prime Minister institutes immediate border closures amid pandemic.",
                    published_date="2021-03-15",
                    source_query="border closures",
                )
            ]
        )

        ref_now = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
        investigator = ProvenanceInvestigator(search_provider=mock_provider)
        result = investigator.investigate_claim(claim, reference_now=ref_now)

        # Recycled content defense invariant:
        assert result.is_shareable is False
        assert result.is_safe_to_share() is False
        assert "TEMPORAL_DRIFT_RECYCLED_CONTENT" in result.warning_flags
        assert result.when.is_recycled_media_risk is True
        assert "DO NOT SHARE (RECYCLED HISTORICAL CONTENT)" in result.recommendation

    def test_satire_origin_discovery(self) -> None:
        """TEST 4: Satire Origin Discovery.

        An unattributed viral screenshot quote is searched and traced directly to The Onion.
        Triggers SATIRE_PARODY_ALERT and blocks sharing.
        """
        claim = ExtractedClaim(
            claim_id="claim-satire-01",
            speaker="Department of Transportation",
            verbatim_quote="Highways to be replaced with lazy rivers by summer.",
            normalized_claim="Highways will be replaced with lazy rivers.",
            alleged_venue=None,
            alleged_date=None,
            cited_urls=[],
            narrative_side="Neutral",
            emotional_framing=EmotionalFraming(
                arousal_score=0.5,
                primary_emotion="neutral",
                manipulation_cues=[],
            ),
        )

        mock_provider = MockSearchProvider(
            default_hits=[
                SearchHit(
                    title="DOT Unveils Lazy River Highway System - The Onion",
                    url="https://theonion.com/dot-unveils-lazy-river-highways",
                    snippet="Officials confirmed all interstates will be filled with water.",
                    published_date="2026-06-01",
                    source_query="highways lazy rivers",
                )
            ]
        )

        investigator = ProvenanceInvestigator(search_provider=mock_provider)
        result = investigator.investigate_claim(claim)

        assert result.verdict == ProvenanceVerdict.SATIRE_PARODY_ALERT
        assert result.is_shareable is False
        assert "SATIRE_PARODY_SOURCE" in result.warning_flags
        assert result.confidence_score >= 0.90
