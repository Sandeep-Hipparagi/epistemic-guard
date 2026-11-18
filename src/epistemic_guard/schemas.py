from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceTier(str, Enum):
    """Deterministic categorization of information sources based on accountability."""

    TIER_1_PRIMARY = "TIER_1_PRIMARY"
    """Direct primary sources, official government/regulatory releases, global wire services (Reuters, AP),
    primary academic journals, and certified non-partisan fact-checkers."""

    TIER_2_ESTABLISHED_EDITORIAL = "TIER_2_ESTABLISHED_EDITORIAL"
    """Major newsrooms with formal editorial oversight, named reporter bylines,
    transparent corrections policies, and legal accountability for reporting."""

    TIER_3_SECONDARY_ANALYSIS = "TIER_3_SECONDARY_ANALYSIS"
    """Specialized trade press, tech publications, opinion commentary, regional outlets,
    and curated analytical newsletters."""

    TIER_4_USER_GENERATED = "TIER_4_USER_GENERATED"
    """Social media platforms, microblogs, video-sharing forums, and unmoderated message boards
    where any user can publish without prior editorial verification or accountability."""

    TIER_5_SATIRE_PARODY = "TIER_5_SATIRE_PARODY"
    """Humorous, fictional, or satirical publications whose fictional headlines are frequently
    recycled or misconstrued as real breaking news."""

    TIER_UNKNOWN = "TIER_UNKNOWN"
    """Unclassified or unrecognized domain, treated with conservative suspicion."""


class EvidenceType(str, Enum):
    """Type of empirical evidence backing a claim."""

    VIDEO = "VIDEO"
    """Raw video footage, recorded live stream, or press briefing video."""

    AUDIO = "AUDIO"
    """Raw audio recording, press call audio, or wire broadcast."""

    PRIMARY_DOCUMENT = "PRIMARY_DOCUMENT"
    """Official court filing, executive order, legislation, or certified press release."""

    TRANSCRIPT = "TRANSCRIPT"
    """Verbatim official or verified hearing transcript."""

    NAMED_OUTLET_REPORT = "NAMED_OUTLET_REPORT"
    """Written investigative or bylined report from a Tier 1 or Tier 2 outlet."""

    SOCIAL_MEDIA_POST = "SOCIAL_MEDIA_POST"
    """Single tweet/post/comment from an unverified social media account."""

    UNVERIFIED_CLAIM = "UNVERIFIED_CLAIM"
    """Hearsay, uncited quote, unlinked screenshot, or second-hand rumor."""

    OTHER = "OTHER"
    """Other secondary media or unstructured reference."""


class ProvenanceVerdict(str, Enum):
    """Final decision regarding the provenance integrity of an audited claim."""

    VERIFIED_PRIMARY = "VERIFIED_PRIMARY"
    """Fully corroborated by primary media (video/audio/document) or Tier 1 wire service with verified Where and When."""

    CORROBORATED_SECONDARY = "CORROBORATED_SECONDARY"
    """Reported by accountable Tier 2 editorial outlets with named bylines and confirmed Where and When."""

    UNVERIFIED_SINGLE_SOURCE = "UNVERIFIED_SINGLE_SOURCE"
    """Reported by a single secondary outlet or domain with incomplete corroboration."""

    DO_NOT_SHARE_UNCONFIRMED = "DO_NOT_SHARE_UNCONFIRMED"
    """MANDATORY WARNING. The claim fails core provenance tests (missing Where/When, or sole source
    is an unverified social media post, or lacks primary media/named outlet). Sharing spreads contagion."""

    SATIRE_PARODY_ALERT = "SATIRE_PARODY_ALERT"
    """CRITICAL ALERT. The source is a known satire or parody publication misconstrued as real news."""


class DomainAuditResult(BaseModel):
    """Result of deterministic URL and domain tiering analysis."""

    model_config = ConfigDict(frozen=True)

    url: str = Field(description="The original URL or domain string audited.")
    raw_domain: str = Field(description="Extracted host/domain before suffix extraction.")
    registered_domain: str = Field(description="Top-level registered domain (e.g. 'reuters.com').")
    subdomain: Optional[str] = Field(default=None, description="Subdomain if present (e.g. 'news').")
    suffix: Optional[str] = Field(default=None, description="Public suffix / TLD (e.g. 'gov', 'com').")
    tier: SourceTier = Field(description="Assigned deterministic source tier.")
    tier_name: str = Field(description="Human-readable name of the tier.")
    is_social_media: bool = Field(default=False, description="True if domain is Tier 4 user-generated content.")
    is_satire: bool = Field(default=False, description="True if domain is Tier 5 satire/parody.")
    is_primary_or_editorial: bool = Field(
        default=False,
        description="True if domain is Tier 1 (Primary) or Tier 2 (Established Editorial).",
    )
    is_lookalike: bool = Field(
        default=False,
        description="True if domain is a deceptive lookalike/typosquatted impersonation of an established brand.",
    )
    impersonated_brand: Optional[str] = Field(
        default=None,
        description="Protected brand being impersonated if lookalike detected.",
    )
    warning_flags: list[str] = Field(
        default_factory=list,
        description="Specific domain risk warning flags.",
    )
    notes: Optional[str] = Field(default=None, description="Additional context or rule notes.")


class WhereProvenance(BaseModel):
    """Audit of provenance question 1: Where was it said?"""

    venue_or_platform: Optional[str] = Field(
        default=None,
        description="Identified platform, press room, official podium, or venue where the statement occurred.",
    )
    root_url: Optional[str] = Field(
        default=None,
        description="Original canonical URL where the claim or recording originated.",
    )
    domain_audit: Optional[DomainAuditResult] = Field(
        default=None,
        description="Deterministic audit of the hosting domain.",
    )
    is_identified: bool = Field(
        default=False,
        description="True if the physical or digital origin platform is reliably identified.",
    )
    is_primary_venue: bool = Field(
        default=False,
        description="True if the venue is an official or audited primary location rather than secondary commentary.",
    )
    notes: Optional[str] = Field(default=None, description="Evaluation notes for Where provenance.")


class WhenProvenance(BaseModel):
    """Audit of provenance question 2: When was it said?"""

    timestamp: Optional[datetime] = Field(
        default=None,
        description="Exact UTC timestamp or publication datetime.",
    )
    date_str: Optional[str] = Field(
        default=None,
        description="Normalized date string (e.g. '2024-11-19') if exact time is unavailable.",
    )
    is_exact_timestamp: bool = Field(
        default=False,
        description="True if an exact publication or broadcast timestamp was verified.",
    )
    is_recycled_media_risk: bool = Field(
        default=False,
        description="True if the quote/media appears to be recycled from an earlier historic event.",
    )
    temporal_notes: Optional[str] = Field(
        default=None,
        description="Temporal evaluation notes, recency warnings, or date discrepancies.",
    )


class EvidenceProvenance(BaseModel):
    """Audit of provenance question 3: Is there video, audio, or a named outlet behind it?"""

    evidence_type: EvidenceType = Field(
        default=EvidenceType.UNVERIFIED_CLAIM,
        description="Classification of empirical media backing the claim.",
    )
    has_primary_media: bool = Field(
        default=False,
        description="True if backed by direct video, audio recording, official filing, or transcript.",
    )
    has_named_outlet: bool = Field(
        default=False,
        description="True if backed by an accountable Tier 1 or Tier 2 newsroom.",
    )
    outlet_name: Optional[str] = Field(
        default=None,
        description="Name of the reporting outlet or wire service.",
    )
    media_url: Optional[str] = Field(
        default=None,
        description="Direct link to primary video/audio/document evidence.",
    )
    evidence_summary: Optional[str] = Field(
        default=None,
        description="Summary of media verification.",
    )


class SourceRecord(BaseModel):
    """Individual cited source attached to a claim."""

    url: Optional[str] = Field(default=None, description="URL of the cited source.")
    domain_audit: Optional[DomainAuditResult] = Field(
        default=None,
        description="Domain tiering analysis of the source URL.",
    )
    author_or_account: Optional[str] = Field(
        default=None,
        description="Author byline, social handle, or speaker name.",
    )
    outlet: Optional[str] = Field(default=None, description="Publishing outlet or platform.")
    published_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when this specific source was published.",
    )
    date_str: Optional[str] = Field(
        default=None,
        description="Published date string if exact datetime unavailable.",
    )
    evidence_type: EvidenceType = Field(
        default=EvidenceType.UNVERIFIED_CLAIM,
        description="Nature of evidence provided by this source.",
    )
    has_primary_media: bool = Field(
        default=False,
        description="True if source includes raw video/audio/filing.",
    )
    quote_excerpt: Optional[str] = Field(
        default=None,
        description="Specific quote or excerpt being audited.",
    )
    raw_content: Optional[str] = Field(
        default=None,
        description="Optional full text or transcript excerpt.",
    )
    notes: Optional[str] = Field(default=None, description="Source-level notes.")

    @field_validator("url")
    @classmethod
    def clean_url(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            return v if v else None
        return None


class ClaimAuditRequest(BaseModel):
    """Inbound request to audit the provenance of a viral quote or claim."""

    claim_text: str = Field(
        min_length=3,
        description="The statement, quote, or factual assertion to be audited.",
    )
    speaker_or_subject: Optional[str] = Field(
        default=None,
        description="The person or organization alleged to have made the statement.",
    )
    alleged_venue: Optional[str] = Field(
        default=None,
        description="The alleged venue or platform where it was purportedly said.",
    )
    alleged_date: Optional[str] = Field(
        default=None,
        description="The alleged date or timeframe when it was said.",
    )
    sources: list[SourceRecord] = Field(
        default_factory=list,
        description="List of cited source records supporting or carrying the claim.",
    )
    raw_urls: list[str] = Field(
        default_factory=list,
        description="Optional list of raw URLs to be automatically converted to sources.",
    )
    emotional_intensity_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Heuristic emotional volatility score (0.0=calm, 1.0=extreme viral outrage).",
    )
    context_notes: Optional[str] = Field(
        default=None,
        description="Any supplementary context or background information.",
    )

    @field_validator("claim_text")
    @classmethod
    def validate_claim_text(cls, v: str) -> str:
        cleaned = v.strip()
        if len(cleaned) < 3:
            raise ValueError("Claim text must contain at least 3 characters.")
        return cleaned


class ProvenanceAuditResult(BaseModel):
    """Deterministic audit outcome containing answers to the 3 provenance questions and sharing verdict."""

    claim_text: str = Field(description="The audited statement or quote.")
    verdict: ProvenanceVerdict = Field(description="The provenance integrity verdict.")
    is_shareable: bool = Field(
        description="Strict boolean: True ONLY if verified by primary media or corroborated editorial journalism.",
    )
    where: WhereProvenance = Field(
        description="Question 1 evaluation: Where was it said?",
    )
    when: WhenProvenance = Field(
        description="Question 2 evaluation: When was it said?",
    )
    evidence: EvidenceProvenance = Field(
        description="Question 3 evaluation: Is there video, audio, or a named outlet behind it?",
    )
    evaluated_sources: list[SourceRecord] = Field(
        default_factory=list,
        description="List of all sources audited during the evaluation.",
    )
    warning_flags: list[str] = Field(
        default_factory=list,
        description="Specific failure codes (e.g. 'SOLE_SOURCE_UNVERIFIED_UGC', 'MISSING_TIMESTAMP_RECYCLED_RISK').",
    )
    recommendation: str = Field(
        description="Actionable, de-escalating guidance on sharing, verification, or holding off.",
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Deterministic confidence score based on source tiering and evidence completeness.",
    )
    audited_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of when the audit was performed.",
    )

    def is_safe_to_share(self) -> bool:
        """Helper to check whether the claim is clear of viral unconfirmed risks."""
        return self.is_shareable and self.verdict in (
            ProvenanceVerdict.VERIFIED_PRIMARY,
            ProvenanceVerdict.CORROBORATED_SECONDARY,
        )


class EmotionalFraming(BaseModel):
    """Emotional arousal, tone, and rhetorical manipulation profile of a claim or text."""

    arousal_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Arousal intensity score from 0.0 (calm/neutral) to 1.0 (extreme viral panic/outrage).",
    )
    primary_emotion: str = Field(
        description="Dominant emotion detected (e.g. 'outrage', 'fear', 'vindication', 'moral_disgust', 'neutral').",
    )
    manipulation_cues: list[str] = Field(
        default_factory=list,
        description="List of detected rhetorical manipulation signals (e.g. 'all_caps_urgency', 'unverified_screenshot_appeal').",
    )


class ExtractedClaim(BaseModel):
    """An individual atomic claim or quote extracted from unstructured raw text."""

    claim_id: str = Field(description="Unique deterministic or sequential claim identifier.")
    speaker: Optional[str] = Field(
        default=None,
        description="Explicitly named speaker or entity making the statement, if mentioned in text.",
    )
    verbatim_quote: Optional[str] = Field(
        default=None,
        description="Exact quote enclosed in quotation marks or directly attributed in text, if any.",
    )
    normalized_claim: str = Field(
        description="Neutral, standardized assertion capturing the core testable claim.",
    )
    alleged_venue: Optional[str] = Field(
        default=None,
        description="Explicit platform, press room, podium, or event mentioned in text (Where). None if unstated.",
    )
    alleged_date: Optional[str] = Field(
        default=None,
        description="Explicit date or timestamp string mentioned in text (When). None if unstated.",
    )
    cited_urls: list[str] = Field(
        default_factory=list,
        description="List of URLs explicitly associated with or linked to this claim.",
    )
    narrative_side: str = Field(
        default="Neutral",
        description="Perspective or narrative stance in a controversy (e.g. 'Side A', 'Side B', 'Neutral').",
    )
    emotional_framing: EmotionalFraming = Field(
        description="Emotional arousal and manipulation signals for this claim.",
    )

    def to_audit_request(self) -> ClaimAuditRequest:
        """Bridge Phase 1 into Phase 0: Convert this extracted claim into a ClaimAuditRequest."""
        sources = [
            SourceRecord(
                url=url,
                quote_excerpt=self.verbatim_quote,
            )
            for url in self.cited_urls
            if url and url.strip()
        ]
        return ClaimAuditRequest(
            claim_text=self.normalized_claim,
            speaker_or_subject=self.speaker,
            alleged_venue=self.alleged_venue,
            alleged_date=self.alleged_date,
            sources=sources,
            raw_urls=list(self.cited_urls),
            emotional_intensity_score=self.emotional_framing.arousal_score,
            context_notes=(
                f"Verbatim quote: '{self.verbatim_quote}' | Narrative stance: {self.narrative_side}"
                if self.verbatim_quote
                else f"Narrative stance: {self.narrative_side}"
            ),
        )


class ExtractionBatchResult(BaseModel):
    """Aggregate result of extracting claims and emotional framing from a piece of raw text."""

    raw_text_hash: str = Field(description="SHA-256 or truncated hash of the source input text.")
    overall_emotional_intensity: float = Field(
        ge=0.0,
        le=1.0,
        description="Aggregate emotional volatility score across the entire input text.",
    )
    claims: list[ExtractedClaim] = Field(
        default_factory=list,
        description="List of discrete extracted claims.",
    )


class ClaimWithAudit(BaseModel):
    """Pairing of an extracted claim with its completed provenance audit result."""

    claim: ExtractedClaim = Field(description="The extracted claim.")
    audit: ProvenanceAuditResult = Field(description="The deterministic provenance audit result.")


class NarrativeSideSummary(BaseModel):
    """Summary of a specific narrative perspective with steel-manned arguments and deterministic metrics."""

    side_label: str = Field(description="Narrative perspective identifier (e.g. 'Side A', 'Side B', 'Neutral').")
    steel_manned_summary: str = Field(
        description="Charitable, non-ideological summary of the core argument from this perspective.",
    )
    key_arguments: list[str] = Field(
        default_factory=list,
        description="List of primary arguments or assertions advanced by this perspective.",
    )
    total_claims: int = Field(default=0, ge=0, description="Total number of claims attributed to this side.")
    verified_shareable_count: int = Field(
        default=0,
        ge=0,
        description="Number of claims verified by primary media or corroborated editorial journalism.",
    )
    unconfirmed_blocked_count: int = Field(
        default=0,
        ge=0,
        description="Number of claims failing provenance criteria or relying on unverified social media.",
    )
    recycled_content_count: int = Field(
        default=0,
        ge=0,
        description="Number of claims detected as recycled historic quotes or out-of-context footage.",
    )
    average_emotional_arousal: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Average emotional arousal score (0.0 to 1.0) of claims on this side.",
    )


class SideNarrativeDraft(BaseModel):
    """Draft narrative summary produced by the LLM during synthesis."""

    side_label: str = Field(description="Identifier matching 'Side A', 'Side B', or 'Neutral'.")
    steel_manned_summary: str = Field(description="Steel-manned explanation of this perspective.")
    key_arguments: list[str] = Field(default_factory=list, description="Core arguments.")


class SynthesisLLMOutput(BaseModel):
    """Structured LLM completion contract for multi-perspective synthesis."""

    topic_title: str = Field(description="Descriptive title of the overall topic or controversy.")
    side_drafts: list[SideNarrativeDraft] = Field(
        default_factory=list,
        description="Steel-manned summaries for each narrative side identified.",
    )
    deescalation_guidance: str = Field(
        description="Calm, non-preachy de-escalation guidance emphasizing the 3 provenance criteria.",
    )


class TwoSidedListeningReport(BaseModel):
    """Final comprehensive report synthesizing multi-perspective arguments and provenance asymmetry."""

    topic: str = Field(description="The primary topic or controversy examined.")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp when the report was generated.",
    )
    overall_emotional_temperature: float = Field(
        ge=0.0,
        le=1.0,
        description="Aggregate emotional arousal level across all analyzed claims (0.0=calm, 1.0=fever pitch).",
    )
    has_high_emotional_contagion: bool = Field(
        description="True if discourse exhibits viral outrage/panic markers warranting pause before sharing.",
    )
    provenance_asymmetry_detected: bool = Field(
        description="True if one perspective holds strong primary/editorial backing while the opposing perspective relies on unconfirmed social media or recycled claims.",
    )
    perspectives: list[NarrativeSideSummary] = Field(
        default_factory=list,
        description="Steel-manned perspectives with deterministic provenance scores.",
    )
    audited_claims: list[ClaimWithAudit] = Field(
        default_factory=list,
        description="All individual claims evaluated during synthesis.",
    )
    deescalation_guidance: str = Field(
        description="Actionable, pre-share friction guidance advising readers on verification.",
    )


