from __future__ import annotations

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from epistemic_guard.config import Settings, get_settings
from epistemic_guard.schemas import (
    ClaimAuditRequest,
    ClaimWithAudit,
    DomainAuditResult,
    EmotionalFraming,
    EvidenceProvenance,
    EvidenceType,
    ExtractedClaim,
    ExtractionBatchResult,
    NarrativeSideSummary,
    ProvenanceAuditResult,
    ProvenanceVerdict,
    SideNarrativeDraft,
    SourceRecord,
    SourceTier,
    SynthesisLLMOutput,
    TwoSidedListeningReport,
    WhenProvenance,
    WhereProvenance,
)


class TestSourceTierEnums:
    def test_source_tier_values(self) -> None:
        expected = {
            "TIER_1_PRIMARY",
            "TIER_2_ESTABLISHED_EDITORIAL",
            "TIER_3_SECONDARY_ANALYSIS",
            "TIER_4_USER_GENERATED",
            "TIER_5_SATIRE_PARODY",
            "TIER_UNKNOWN",
        }
        actual = {tier.value for tier in SourceTier}
        assert actual == expected
        assert SourceTier.TIER_1_PRIMARY == "TIER_1_PRIMARY"

    def test_evidence_type_values(self) -> None:
        expected = {
            "VIDEO",
            "AUDIO",
            "PRIMARY_DOCUMENT",
            "TRANSCRIPT",
            "NAMED_OUTLET_REPORT",
            "SOCIAL_MEDIA_POST",
            "UNVERIFIED_CLAIM",
            "OTHER",
        }
        actual = {ev.value for ev in EvidenceType}
        assert actual == expected

    def test_provenance_verdict_values(self) -> None:
        expected = {
            "VERIFIED_PRIMARY",
            "CORROBORATED_SECONDARY",
            "UNVERIFIED_SINGLE_SOURCE",
            "DO_NOT_SHARE_UNCONFIRMED",
            "SATIRE_PARODY_ALERT",
        }
        actual = {v.value for v in ProvenanceVerdict}
        assert actual == expected


class TestDomainAuditResult:
    def test_domain_audit_result_immutability(self) -> None:
        res = DomainAuditResult(
            url="https://www.reuters.com/world",
            raw_domain="www.reuters.com",
            registered_domain="reuters.com",
            subdomain="www",
            suffix="com",
            tier=SourceTier.TIER_1_PRIMARY,
            tier_name="Tier 1: Primary Evidence & Wire Records",
            is_social_media=False,
            is_satire=False,
            is_primary_or_editorial=True,
            notes="Primary wire",
        )
        assert res.registered_domain == "reuters.com"
        assert res.is_primary_or_editorial is True

        # Frozen model test
        with pytest.raises(ValidationError):
            res.tier = SourceTier.TIER_4_USER_GENERATED  # type: ignore


class TestWhereWhenEvidenceProvenance:
    def test_where_provenance_defaults(self) -> None:
        where = WhereProvenance()
        assert where.is_identified is False
        assert where.venue_or_platform is None
        assert where.root_url is None

    def test_when_provenance_exact_and_recycled(self) -> None:
        now = datetime.now(timezone.utc)
        when = WhenProvenance(
            timestamp=now,
            date_str="2026-11-19",
            is_exact_timestamp=True,
            is_recycled_media_risk=False,
        )
        assert when.is_exact_timestamp is True
        assert when.is_recycled_media_risk is False
        assert when.timestamp == now

    def test_evidence_provenance_defaults(self) -> None:
        evidence = EvidenceProvenance()
        assert evidence.evidence_type == EvidenceType.UNVERIFIED_CLAIM
        assert evidence.has_primary_media is False
        assert evidence.has_named_outlet is False


class TestSourceRecord:
    def test_source_record_url_cleaning(self) -> None:
        rec = SourceRecord(url="   https://apnews.com/article/123   ")
        assert rec.url == "https://apnews.com/article/123"

        rec_empty = SourceRecord(url="   ")
        assert rec_empty.url is None

    def test_source_record_full_spec(self) -> None:
        rec = SourceRecord(
            url="https://apnews.com",
            author_or_account="John Doe",
            outlet="Associated Press",
            evidence_type=EvidenceType.NAMED_OUTLET_REPORT,
            has_primary_media=False,
            quote_excerpt="Official statement excerpt",
        )
        assert rec.outlet == "Associated Press"
        assert rec.evidence_type == EvidenceType.NAMED_OUTLET_REPORT


class TestClaimAuditRequest:
    def test_valid_request(self) -> None:
        req = ClaimAuditRequest(
            claim_text="World leaders reach historic climate accord in Geneva.",
            speaker_or_subject="UN Envoy",
            alleged_venue="Geneva Summit",
            alleged_date="2026-11-19",
            emotional_intensity_score=0.45,
        )
        assert req.claim_text == "World leaders reach historic climate accord in Geneva."
        assert req.emotional_intensity_score == 0.45
        assert req.sources == []
        assert req.raw_urls == []

    def test_short_claim_text_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ClaimAuditRequest(claim_text="ab")

        with pytest.raises(ValidationError):
            ClaimAuditRequest(claim_text="   ")

    def test_emotional_intensity_bounds(self) -> None:
        with pytest.raises(ValidationError):
            ClaimAuditRequest(claim_text="Test statement", emotional_intensity_score=1.5)

        with pytest.raises(ValidationError):
            ClaimAuditRequest(claim_text="Test statement", emotional_intensity_score=-0.1)


class TestProvenanceAuditResult:
    def test_is_safe_to_share_logic(self) -> None:
        where = WhereProvenance(is_identified=True)
        when = WhenProvenance(is_exact_timestamp=True)
        evidence = EvidenceProvenance(has_primary_media=True)

        # Verified Primary is shareable
        verified = ProvenanceAuditResult(
            claim_text="Official verified quote",
            verdict=ProvenanceVerdict.VERIFIED_PRIMARY,
            is_shareable=True,
            where=where,
            when=when,
            evidence=evidence,
            warning_flags=[],
            recommendation="Clear to share",
            confidence_score=0.95,
        )
        assert verified.is_safe_to_share() is True

        # Unconfirmed is NOT shareable
        unconfirmed = ProvenanceAuditResult(
            claim_text="Unverified rumor",
            verdict=ProvenanceVerdict.DO_NOT_SHARE_UNCONFIRMED,
            is_shareable=False,
            where=WhereProvenance(),
            when=WhenProvenance(),
            evidence=EvidenceProvenance(),
            warning_flags=["SOLE_SOURCE_UNVERIFIED_UGC"],
            recommendation="Do not share",
            confidence_score=0.2,
        )
        assert unconfirmed.is_safe_to_share() is False

    def test_json_roundtrip_serialization(self) -> None:
        where = WhereProvenance(venue_or_platform="UN Press Room", is_identified=True)
        when = WhenProvenance(date_str="2026-11-19", is_exact_timestamp=False)
        evidence = EvidenceProvenance(
            evidence_type=EvidenceType.NAMED_OUTLET_REPORT,
            has_named_outlet=True,
            outlet_name="Reuters",
        )
        original = ProvenanceAuditResult(
            claim_text="Breaking economic announcement",
            verdict=ProvenanceVerdict.CORROBORATED_SECONDARY,
            is_shareable=True,
            where=where,
            when=when,
            evidence=evidence,
            warning_flags=[],
            recommendation="Corroborated by Reuters",
            confidence_score=0.85,
        )
        json_str = original.model_dump_json()
        restored = ProvenanceAuditResult.model_validate_json(json_str)
        assert restored.claim_text == original.claim_text
        assert restored.verdict == original.verdict
        assert restored.is_shareable == original.is_shareable
        assert restored.evidence.outlet_name == "Reuters"


class TestConfigSettings:
    def test_default_settings(self) -> None:
        settings = Settings()
        assert settings.environment in ("development", "testing", "production")
        assert settings.temperature == 0.0
        assert settings.request_timeout >= 1.0
        assert settings.strict_timestamp_enforcement is True
        assert settings.require_primary_evidence_for_breaking is True

    def test_is_local_endpoint_detection(self) -> None:
        local_settings = Settings(openai_base_url="http://localhost:11434/v1")
        assert local_settings.is_local_endpoint is True

        cloud_settings = Settings(openai_base_url="https://api.openai.com/v1")
        assert cloud_settings.is_local_endpoint is False

    def test_get_settings_singleton(self) -> None:
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2


class TestPhase1ExtractionSchemas:
    def test_emotional_framing_valid(self) -> None:
        framing = EmotionalFraming(
            arousal_score=0.88,
            primary_emotion="moral_disgust",
            manipulation_cues=["all_caps_urgency", "unverified_screenshot_appeal"],
        )
        assert framing.arousal_score == 0.88
        assert framing.primary_emotion == "moral_disgust"
        assert len(framing.manipulation_cues) == 2

    def test_emotional_framing_bounds(self) -> None:
        with pytest.raises(ValidationError):
            EmotionalFraming(arousal_score=1.5, primary_emotion="outrage")

        with pytest.raises(ValidationError):
            EmotionalFraming(arousal_score=-0.2, primary_emotion="calm")

    def test_extracted_claim_and_batch_serialization(self) -> None:
        claim = ExtractedClaim(
            claim_id="test-claim-1",
            speaker="Senator Smith",
            verbatim_quote="Tax rates will double by next month.",
            normalized_claim="Tax rates will double next month.",
            alleged_venue="Senate Hearing",
            alleged_date="2026-11-19",
            cited_urls=["https://reuters.com/tax-hearing"],
            narrative_side="Side B",
            emotional_framing=EmotionalFraming(
                arousal_score=0.75,
                primary_emotion="fear",
                manipulation_cues=["catastrophic_hyperbole"],
            ),
        )
        batch = ExtractionBatchResult(
            raw_text_hash="abc123hash",
            overall_emotional_intensity=0.75,
            claims=[claim],
        )
        json_str = batch.model_dump_json()
        restored = ExtractionBatchResult.model_validate_json(json_str)

        assert restored.raw_text_hash == "abc123hash"
        assert len(restored.claims) == 1
        assert restored.claims[0].speaker == "Senator Smith"
        assert restored.claims[0].narrative_side == "Side B"


class TestPhase3SynthesisSchemas:
    def test_narrative_side_summary(self) -> None:
        summary = NarrativeSideSummary(
            side_label="Side A",
            steel_manned_summary="Strongest coherent version of the policy perspective.",
            key_arguments=["Key point 1", "Key point 2"],
            total_claims=3,
            verified_shareable_count=2,
            unconfirmed_blocked_count=1,
            recycled_content_count=0,
            average_emotional_arousal=0.35,
        )
        assert summary.side_label == "Side A"
        assert summary.verified_shareable_count == 2
        assert summary.unconfirmed_blocked_count == 1
        assert summary.average_emotional_arousal == 0.35

    def test_two_sided_listening_report_roundtrip(self) -> None:
        report = TwoSidedListeningReport(
            topic="Bilateral Treaty Debate",
            generated_at=datetime.now(timezone.utc),
            overall_emotional_temperature=0.62,
            has_high_emotional_contagion=False,
            provenance_asymmetry_detected=True,
            perspectives=[
                NarrativeSideSummary(
                    side_label="Side A",
                    steel_manned_summary="Summary A",
                    key_arguments=["Arg 1"],
                    total_claims=1,
                    verified_shareable_count=1,
                    unconfirmed_blocked_count=0,
                    recycled_content_count=0,
                    average_emotional_arousal=0.25,
                )
            ],
            audited_claims=[],
            deescalation_guidance="Take time to check wire reporting before sharing.",
        )
        json_str = report.model_dump_json()
        restored = TwoSidedListeningReport.model_validate_json(json_str)
        assert restored.topic == "Bilateral Treaty Debate"
        assert restored.provenance_asymmetry_detected is True
        assert restored.overall_emotional_temperature == 0.62


