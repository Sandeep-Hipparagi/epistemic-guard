from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence

from epistemic_guard.config import Settings, get_settings
from epistemic_guard.schemas import (
    ClaimAuditRequest,
    EvidenceType,
    ExtractedClaim,
    ProvenanceAuditResult,
    ProvenanceVerdict,
    SourceRecord,
    SourceTier,
)
from epistemic_guard.tools.domain_auditor import DomainAuditor
from epistemic_guard.tools.search import (
    DuckDuckGoSearchProvider,
    MockSearchProvider,
    SearchHit,
    SearchProvider,
    TavilySearchProvider,
    build_provenance_queries,
)
from epistemic_guard.tools.temporal import (
    TemporalAuditResult,
    evaluate_temporal_consistency,
    parse_flexible_date,
)

logger = logging.getLogger(__name__)


def infer_evidence_for_url(
    url: str,
    tier: SourceTier,
    snippet: Optional[str] = None,
) -> tuple[EvidenceType, bool]:
    """Deterministically infer evidence type and whether primary media is present."""
    url_lower = url.lower()
    snippet_lower = (snippet or "").lower()

    # Video platforms & official broadcasters
    if any(host in url_lower for host in ("youtube.com", "youtu.be", "vimeo.com")):
        return EvidenceType.VIDEO, True

    if "c-span.org" in url_lower:
        # C-SPAN video or transcripts are official primary records
        if "transcript" in url_lower or "transcript" in snippet_lower:
            return EvidenceType.TRANSCRIPT, True
        return EvidenceType.VIDEO, True

    # Government / Judicial official documents
    if any(url_lower.endswith(tld) or f"{tld}/" in url_lower for tld in (".gov", ".mil")):
        if any(term in url_lower or term in snippet_lower for term in ("press", "statement", "briefing", "pdf", "order")):
            return EvidenceType.PRIMARY_DOCUMENT, True

    # Audio wire or broadcast
    if any(term in url_lower or term in snippet_lower for term in ("audio", "podcast", "radio")):
        return EvidenceType.AUDIO, True

    # Tier 1 Wire Services & Tier 2 Editorial newsrooms
    if tier == SourceTier.TIER_1_PRIMARY:
        return EvidenceType.NAMED_OUTLET_REPORT, False

    if tier == SourceTier.TIER_2_ESTABLISHED_EDITORIAL:
        return EvidenceType.NAMED_OUTLET_REPORT, False

    # Social media platforms
    if tier == SourceTier.TIER_4_USER_GENERATED:
        return EvidenceType.SOCIAL_MEDIA_POST, False

    # Satire
    if tier == SourceTier.TIER_5_SATIRE_PARODY:
        return EvidenceType.UNVERIFIED_CLAIM, False

    return EvidenceType.UNVERIFIED_CLAIM, False


class ProvenanceInvestigator:
    """Active 3-criteria provenance retrieval, corroboration, and temporal drift engine.

    Orchestrates:
      1. Targeted query generation across Where, When, and Empirical Evidence.
      2. Multi-engine search retrieval (DuckDuckGo, Tavily, Mock).
      3. Circular reporting defense (refusing UGC echo chambers).
      4. Temporal drift analysis (catching recycled historical quotes/footage).
      5. Enriched evaluation handoff into DomainAuditor.
    """

    def __init__(
        self,
        search_provider: Optional[SearchProvider] = None,
        auditor: Optional[DomainAuditor] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.auditor = auditor or DomainAuditor()

        if search_provider is not None:
            self.search_provider = search_provider
        else:
            self.search_provider = self._init_default_search_provider()

    def _init_default_search_provider(self) -> SearchProvider:
        """Initialize provider based on application settings."""
        provider_name = (self.settings.search_provider or "duckduckgo").lower()
        if provider_name == "tavily":
            return TavilySearchProvider()
        elif provider_name == "mock":
            return MockSearchProvider()
        else:
            return DuckDuckGoSearchProvider()

    def investigate_claim(
        self,
        claim: ExtractedClaim,
        reference_now: Optional[datetime] = None,
    ) -> ProvenanceAuditResult:
        """Investigate an extracted claim via active search, temporal audit, and domain tiering."""
        now = reference_now or datetime.now(timezone.utc)

        # 1. Build provenance queries
        queries = build_provenance_queries(claim)

        # 2. Execute retrieval
        all_hits: list[SearchHit] = []
        seen_urls: set[str] = set()

        for q in queries:
            try:
                hits = self.search_provider.search(q, max_results=self.settings.max_search_results)
                for h in hits:
                    clean_u = h.url.strip()
                    if clean_u and clean_u not in seen_urls:
                        seen_urls.add(clean_u)
                        all_hits.append(h)
            except Exception as e:
                logger.warning("Search query '%s' encountered an exception: %s", q, e)

        # 3. Assemble all candidate URLs (input cited URLs + discovered hits)
        candidate_urls: list[str] = []
        hit_by_url: dict[str, SearchHit] = {}

        for h in all_hits:
            hit_by_url[h.url] = h
            if h.url not in candidate_urls:
                candidate_urls.append(h.url)

        for u in claim.cited_urls:
            clean_u = u.strip()
            if clean_u and clean_u not in candidate_urls:
                candidate_urls.append(clean_u)

        # 4. Audit candidate domains and construct enriched SourceRecords
        enriched_sources: list[SourceRecord] = []
        for url in candidate_urls:
            domain_audit = self.auditor.audit_url(url)
            hit = hit_by_url.get(url)

            # Infer evidence type
            ev_type, has_primary = infer_evidence_for_url(
                url=url,
                tier=domain_audit.tier,
                snippet=hit.snippet if hit else None,
            )

            # Discover published timestamp
            pub_dt: Optional[datetime] = None
            if hit and hit.published_date:
                pub_dt = parse_flexible_date(hit.published_date)

            source_record = SourceRecord(
                url=url,
                domain_audit=domain_audit,
                outlet=domain_audit.registered_domain,
                published_at=pub_dt,
                date_str=pub_dt.strftime("%Y-%m-%d") if pub_dt else (hit.published_date if hit else None),
                evidence_type=ev_type,
                has_primary_media=has_primary,
                quote_excerpt=claim.verbatim_quote,
                raw_content=hit.snippet if hit else None,
            )
            enriched_sources.append(source_record)

        # 5. Temporal consistency & recycled content audit
        temporal_audit = evaluate_temporal_consistency(
            alleged_date=claim.alleged_date,
            hits=all_hits,
            reference_now=now,
            drift_threshold_days=self.settings.temporal_drift_days_threshold,
        )

        # 6. Build enriched ClaimAuditRequest
        # Adopt earliest verified date if alleged_date is missing or confirmed
        resolved_date = claim.alleged_date or temporal_audit.earliest_found_date_iso

        # Build context notes
        notes_parts: list[str] = []
        if claim.verbatim_quote:
            notes_parts.append(f"Verbatim quote: '{claim.verbatim_quote}'")
        notes_parts.append(f"Narrative stance: {claim.narrative_side}")
        notes_parts.append(f"Temporal analysis: {temporal_audit.temporal_note}")

        audit_request = ClaimAuditRequest(
            claim_text=claim.normalized_claim,
            speaker_or_subject=claim.speaker,
            alleged_venue=claim.alleged_venue,
            alleged_date=resolved_date,
            sources=enriched_sources,
            raw_urls=candidate_urls,
            emotional_intensity_score=claim.emotional_framing.arousal_score,
            context_notes=" | ".join(notes_parts),
        )

        # 7. Execute deterministic provenance audit via DomainAuditor
        audit_result = self.auditor.evaluate_claim(audit_request)

        # 8. Defense Invariant: Recycled Content & Temporal Drift
        if temporal_audit.is_recycled_old_content:
            # Overwrite/enrich flags and recommendations to strictly block viral sharing
            updated_flags = list(audit_result.warning_flags)
            if "TEMPORAL_DRIFT_RECYCLED_CONTENT" not in updated_flags:
                updated_flags.insert(0, "TEMPORAL_DRIFT_RECYCLED_CONTENT")

            # Update when provenance
            updated_when = audit_result.when.model_copy(
                update={
                    "is_recycled_media_risk": True,
                    "temporal_notes": temporal_audit.temporal_note,
                }
            )

            recycled_recommendation = (
                f"DO NOT SHARE (RECYCLED HISTORICAL CONTENT). {temporal_audit.temporal_note} "
                "Recycled quotes or footage stripped of original temporal context are a common vector "
                "for manufactured viral outrage."
            )

            audit_result = audit_result.model_copy(
                update={
                    "verdict": (
                        ProvenanceVerdict.DO_NOT_SHARE_UNCONFIRMED
                        if audit_result.verdict != ProvenanceVerdict.SATIRE_PARODY_ALERT
                        else ProvenanceVerdict.SATIRE_PARODY_ALERT
                    ),
                    "is_shareable": False,
                    "when": updated_when,
                    "warning_flags": updated_flags,
                    "recommendation": recycled_recommendation,
                }
            )

        return audit_result
