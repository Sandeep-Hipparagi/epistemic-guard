from __future__ import annotations

from datetime import datetime, timezone
import pytest

from epistemic_guard.schemas import (
    ClaimAuditRequest,
    EvidenceType,
    ProvenanceVerdict,
    SourceRecord,
    SourceTier,
)
from epistemic_guard.tools.domain_auditor import DomainAuditor


@pytest.fixture
def auditor() -> DomainAuditor:
    return DomainAuditor()


class TestDomainAuditorClassification:
    def test_tier_1_primary_wire_and_institutions(self, auditor: DomainAuditor) -> None:
        reuters = auditor.audit_url("https://www.reuters.com/business/finance/article-1")
        assert reuters.tier == SourceTier.TIER_1_PRIMARY
        assert reuters.registered_domain == "reuters.com"
        assert reuters.is_primary_or_editorial is True
        assert reuters.is_social_media is False
        assert reuters.is_satire is False

        ap = auditor.audit_url("https://apnews.com/article/12345")
        assert ap.tier == SourceTier.TIER_1_PRIMARY

        bloomberg = auditor.audit_url("https://bloomberg.com/news/markets")
        assert bloomberg.tier == SourceTier.TIER_1_PRIMARY

        un = auditor.audit_url("https://un.org/press/en/statement")
        assert un.tier == SourceTier.TIER_1_PRIMARY

        snopes = auditor.audit_url("https://www.snopes.com/fact-check/claim-check")
        assert snopes.tier == SourceTier.TIER_1_PRIMARY

    def test_tier_1_tld_rules(self, auditor: DomainAuditor) -> None:
        # .gov overrides
        gov = auditor.audit_url("https://briefing.whitehouse.gov/statements")
        assert gov.tier == SourceTier.TIER_1_PRIMARY
        assert gov.suffix == "gov"

        defense = auditor.audit_url("https://www.defense.gov/News/Transcripts")
        assert defense.tier == SourceTier.TIER_1_PRIMARY

        # .edu overrides
        edu = auditor.audit_url("https://news.mit.edu/2026/quantum-computing")
        assert edu.tier == SourceTier.TIER_1_PRIMARY

        # .mil overrides
        mil = auditor.audit_url("https://www.navy.mil/Press-Office")
        assert mil.tier == SourceTier.TIER_1_PRIMARY

    def test_tier_2_established_editorial(self, auditor: DomainAuditor) -> None:
        nyt = auditor.audit_url("https://www.nytimes.com/2026/11/19/world/europe")
        assert nyt.tier == SourceTier.TIER_2_ESTABLISHED_EDITORIAL
        assert nyt.is_primary_or_editorial is True

        bbc_uk = auditor.audit_url("https://www.bbc.co.uk/news/world")
        assert bbc_uk.tier == SourceTier.TIER_2_ESTABLISHED_EDITORIAL

        bbc_com = auditor.audit_url("https://bbc.com/news")
        assert bbc_com.tier == SourceTier.TIER_2_ESTABLISHED_EDITORIAL

        guardian = auditor.audit_url("https://www.theguardian.com/us-news")
        assert guardian.tier == SourceTier.TIER_2_ESTABLISHED_EDITORIAL

        wsj = auditor.audit_url("https://wsj.com/articles/markets-today")
        assert wsj.tier == SourceTier.TIER_2_ESTABLISHED_EDITORIAL

    def test_tier_3_secondary_analysis(self, auditor: DomainAuditor) -> None:
        tc = auditor.audit_url("https://techcrunch.com/2026/startup-funding")
        assert tc.tier == SourceTier.TIER_3_SECONDARY_ANALYSIS

        verge = auditor.audit_url("https://theverge.com/tech-news")
        assert verge.tier == SourceTier.TIER_3_SECONDARY_ANALYSIS

        substack = auditor.audit_url("https://newsletter.substack.com/p/analysis")
        assert substack.tier == SourceTier.TIER_3_SECONDARY_ANALYSIS

    def test_tier_4_user_generated_social_media(self, auditor: DomainAuditor) -> None:
        x = auditor.audit_url("https://x.com/viral_user/status/987654321")
        assert x.tier == SourceTier.TIER_4_USER_GENERATED
        assert x.is_social_media is True

        twitter = auditor.audit_url("https://mobile.twitter.com/breaking/status/111")
        assert twitter.tier == SourceTier.TIER_4_USER_GENERATED
        assert twitter.is_social_media is True

        tiktok = auditor.audit_url("https://www.tiktok.com/@creator/video/123456")
        assert tiktok.tier == SourceTier.TIER_4_USER_GENERATED
        assert tiktok.is_social_media is True

        reddit = auditor.audit_url("https://old.reddit.com/r/all/comments/xyz")
        assert reddit.tier == SourceTier.TIER_4_USER_GENERATED
        assert reddit.is_social_media is True

        telegram = auditor.audit_url("https://t.me/breakingchannel/456")
        assert telegram.tier == SourceTier.TIER_4_USER_GENERATED
        assert telegram.is_social_media is True

    def test_tier_5_satire_parody(self, auditor: DomainAuditor) -> None:
        onion = auditor.audit_url("https://theonion.com/senate-passes-bill-humor")
        assert onion.tier == SourceTier.TIER_5_SATIRE_PARODY
        assert onion.is_satire is True

        bee = auditor.audit_url("https://babylonbee.com/news/satirical-headline")
        assert bee.tier == SourceTier.TIER_5_SATIRE_PARODY
        assert bee.is_satire is True

        clickhole = auditor.audit_url("https://clickhole.com/quiz-which-president")
        assert clickhole.tier == SourceTier.TIER_5_SATIRE_PARODY
        assert clickhole.is_satire is True

    def test_tier_unknown_and_malformed_urls(self, auditor: DomainAuditor) -> None:
        unknown = auditor.audit_url("https://some-unheard-of-blog-xyz999.io/post")
        assert unknown.tier == SourceTier.TIER_UNKNOWN
        assert unknown.is_primary_or_editorial is False

        empty = auditor.audit_url("   ")
        assert empty.tier == SourceTier.TIER_UNKNOWN

        bare_domain = auditor.audit_url("reuters.com/business")
        assert bare_domain.tier == SourceTier.TIER_1_PRIMARY

    def test_classify_domain_helper(self, auditor: DomainAuditor) -> None:
        assert auditor.classify_domain("apnews.com") == SourceTier.TIER_1_PRIMARY
        assert auditor.classify_domain("x.com") == SourceTier.TIER_4_USER_GENERATED
        assert auditor.classify_domain("theonion.com") == SourceTier.TIER_5_SATIRE_PARODY


class TestProvenanceEvaluationMethodology:
    """Rigorous tests verifying the core 3 provenance questions and DO_NOT_SHARE_UNCONFIRMED invariant."""

    def test_sole_source_unverified_social_media_flags_do_not_share(self, auditor: DomainAuditor) -> None:
        """RULE: If sole source is an unverified social media post -> DO_NOT_SHARE_UNCONFIRMED."""
        req = ClaimAuditRequest(
            claim_text="Major city announces complete blackout starting tomorrow morning.",
            alleged_venue="X / Twitter Post",
            alleged_date="2026-11-19",
            sources=[
                SourceRecord(
                    url="https://x.com/viral_anonymous/status/123456789",
                    author_or_account="@viral_anonymous",
                    evidence_type=EvidenceType.SOCIAL_MEDIA_POST,
                    has_primary_media=False,
                )
            ],
            emotional_intensity_score=0.92,
        )
        res = auditor.evaluate_claim(req)

        assert res.verdict == ProvenanceVerdict.DO_NOT_SHARE_UNCONFIRMED
        assert res.is_shareable is False
        assert res.is_safe_to_share() is False
        assert "SOLE_SOURCE_UNVERIFIED_UGC" in res.warning_flags
        assert "NO_PRIMARY_MEDIA_OR_NAMED_OUTLET" in res.warning_flags
        assert "DO NOT SHARE" in res.recommendation

    def test_satire_parody_alert(self, auditor: DomainAuditor) -> None:
        """RULE: Satire domains trigger SATIRE_PARODY_ALERT and do_not_share."""
        req = ClaimAuditRequest(
            claim_text="Congress passes bill replacing national currency with candy wrappers.",
            alleged_venue="The Onion",
            alleged_date="2026-11-19",
            sources=[
                SourceRecord(
                    url="https://theonion.com/congress-passes-bill-currency",
                    outlet="The Onion",
                )
            ],
        )
        res = auditor.evaluate_claim(req)

        assert res.verdict == ProvenanceVerdict.SATIRE_PARODY_ALERT
        assert res.is_shareable is False
        assert "SATIRE_PARODY_SOURCE" in res.warning_flags
        assert res.confidence_score >= 0.90

    def test_missing_timestamp_recycled_media_risk(self, auditor: DomainAuditor) -> None:
        """RULE: Missing publication timestamp triggers recycled quote risk and DO_NOT_SHARE_UNCONFIRMED."""
        req = ClaimAuditRequest(
            claim_text="President declares emergency during unexpected press conference.",
            alleged_venue="White House Press Room",
            alleged_date=None,  # No date provided
            sources=[
                SourceRecord(
                    url="https://www.reuters.com/archive-wire",
                    has_primary_media=False,
                    published_at=None,
                    date_str=None,  # No timestamp
                )
            ],
        )
        res = auditor.evaluate_claim(req)

        assert res.verdict == ProvenanceVerdict.DO_NOT_SHARE_UNCONFIRMED
        assert res.is_shareable is False
        assert res.when.is_recycled_media_risk is True
        assert "MISSING_TIMESTAMP_RECYCLED_RISK" in res.warning_flags

    def test_missing_where_provenance(self, auditor: DomainAuditor) -> None:
        """RULE: Missing Where (origin venue or root URL) flags DO_NOT_SHARE_UNCONFIRMED."""
        req = ClaimAuditRequest(
            claim_text="Secret summit agrees to restructure international monetary debt.",
            alleged_venue=None,
            alleged_date="2026-11-19",
            sources=[],  # No sources
        )
        res = auditor.evaluate_claim(req)

        assert res.verdict == ProvenanceVerdict.DO_NOT_SHARE_UNCONFIRMED
        assert res.is_shareable is False
        assert "MISSING_ROOT_WHERE_PROVENANCE" in res.warning_flags
        assert "NO_SOURCES_EVALUATED" in res.warning_flags

    def test_verified_primary_with_wire_and_video(self, auditor: DomainAuditor) -> None:
        """Full compliance: Where, When, and Video/Primary media from Tier 1 wire."""
        pub_time = datetime(2026, 11, 19, 14, 30, tzinfo=timezone.utc)
        req = ClaimAuditRequest(
            claim_text="Federal Reserve lowers benchmark interest rate by 25 basis points.",
            alleged_venue="Federal Reserve Press Briefing",
            alleged_date="2026-11-19",
            sources=[
                SourceRecord(
                    url="https://www.reuters.com/markets/us/fed-rate-cut-2026",
                    published_at=pub_time,
                    evidence_type=EvidenceType.VIDEO,
                    has_primary_media=True,
                    outlet="Reuters",
                    quote_excerpt="The Federal Open Market Committee decided to lower the target range...",
                )
            ],
        )
        res = auditor.evaluate_claim(req)

        assert res.verdict == ProvenanceVerdict.VERIFIED_PRIMARY
        assert res.is_shareable is True
        assert res.is_safe_to_share() is True
        assert res.where.is_identified is True
        assert res.where.is_primary_venue is True
        assert res.when.is_exact_timestamp is True
        assert res.when.is_recycled_media_risk is False
        assert res.evidence.has_primary_media is True
        assert res.confidence_score >= 0.85
        assert len(res.warning_flags) == 0

    def test_corroborated_secondary_established_editorial(self, auditor: DomainAuditor) -> None:
        """Compliant: Tier 2 major editorial newsroom with named reporting and verified timing."""
        pub_time = datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc)
        req = ClaimAuditRequest(
            claim_text="City Council approves new zoning plan after overnight debate.",
            alleged_venue="City Hall Council Chambers",
            alleged_date="2026-11-19",
            sources=[
                SourceRecord(
                    url="https://www.nytimes.com/2026/11/19/nyregion/zoning-vote",
                    published_at=pub_time,
                    evidence_type=EvidenceType.NAMED_OUTLET_REPORT,
                    has_primary_media=False,
                    outlet="The New York Times",
                )
            ],
        )
        res = auditor.evaluate_claim(req)

        assert res.verdict == ProvenanceVerdict.CORROBORATED_SECONDARY
        assert res.is_shareable is True
        assert res.is_safe_to_share() is True
        assert res.evidence.has_named_outlet is True
        assert res.confidence_score >= 0.75

    def test_raw_urls_automatic_ingestion_and_audit(self, auditor: DomainAuditor) -> None:
        """Test that raw_urls in ClaimAuditRequest are parsed, categorized, and audited."""
        req = ClaimAuditRequest(
            claim_text="Major diplomatic announcement at global summit.",
            alleged_date="2026-11-19",
            raw_urls=[
                "https://apnews.com/article/summit-treaty-signed",
                "https://x.com/reporter/status/999888",
            ],
        )
        res = auditor.evaluate_claim(req)

        assert len(res.evaluated_sources) == 2
        ap_src = next(s for s in res.evaluated_sources if "apnews.com" in (s.url or ""))
        assert ap_src.domain_audit is not None
        assert ap_src.domain_audit.tier == SourceTier.TIER_1_PRIMARY

        x_src = next(s for s in res.evaluated_sources if "x.com" in (s.url or ""))
        assert x_src.domain_audit is not None
        assert x_src.domain_audit.tier == SourceTier.TIER_4_USER_GENERATED

    def test_audit_sources_helper(self, auditor: DomainAuditor) -> None:
        sources = auditor.audit_sources([
            "https://www.bbc.com/news/123",
            "https://twitter.com/post/456",
        ])
        assert len(sources) == 2
        assert sources[0].domain_audit.tier == SourceTier.TIER_2_ESTABLISHED_EDITORIAL
        assert sources[0].evidence_type == EvidenceType.NAMED_OUTLET_REPORT
        assert sources[1].domain_audit.tier == SourceTier.TIER_4_USER_GENERATED
        assert sources[1].evidence_type == EvidenceType.SOCIAL_MEDIA_POST
