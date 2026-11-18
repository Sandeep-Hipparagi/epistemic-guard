from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional, Sequence
from pydantic import BaseModel, ConfigDict, Field

from epistemic_guard.schemas import SourceTier
from epistemic_guard.tools.domain_auditor import DomainAuditor
from epistemic_guard.tools.search import SearchHit


class QuoteIntegrityResult(BaseModel):
    """Result of quote-mutation and misattribution verification."""

    model_config = ConfigDict(frozen=True)

    has_verbatim_quote: bool = Field(
        description="True if an explicit verbatim quote was extracted from the input discourse.",
    )
    best_match_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Highest similarity score (0.0 to 1.0) between the alleged quote and retrieved reporting.",
    )
    matched_source_url: Optional[str] = Field(
        default=None,
        description="URL of the retrieved source that provided the closest quote match.",
    )
    is_suspected_mutation: bool = Field(
        default=False,
        description="True when authoritative Tier 1/2 reporting covers the event, but the quote differs significantly (< 0.55).",
    )
    integrity_note: str = Field(
        description="Human-readable assessment of quote fidelity and misattribution risk.",
    )


def compute_quote_similarity(quote: str, text: str) -> float:
    """Compute normalized token-overlap and sequence similarity between a quote and a candidate text block."""
    if not quote or not text:
        return 0.0

    # Strip punctuation and normalize case
    q_clean = re.sub(r"[^\w\s]", "", quote).lower().strip()
    t_clean = re.sub(r"[^\w\s]", "", text).lower().strip()

    if not q_clean or not t_clean:
        return 0.0

    # Exact substring match
    if q_clean in t_clean:
        return 1.0

    q_words = q_clean.split()
    t_words = t_clean.split()

    if not q_words or not t_words:
        return 0.0

    # Token overlap (containment)
    q_set = set(q_words)
    t_set = set(t_words)
    containment = len(q_set & t_set) / len(q_set) if q_set else 0.0

    # Sliding window SequenceMatcher ratio matching quote length
    w_len = len(q_words)
    best_ratio = 0.0
    min_w = max(1, w_len - 2)
    max_w = min(len(t_words) + 1, w_len + 3)

    for size in range(min_w, max_w):
        for i in range(len(t_words) - size + 1):
            window = " ".join(t_words[i : i + size])
            ratio = SequenceMatcher(None, q_clean, window).ratio()
            if ratio > best_ratio:
                best_ratio = ratio

    # Composite metric combining sequence alignment and token containment
    composite_score = max(best_ratio, 0.5 * (best_ratio + containment))
    return round(min(1.0, composite_score), 4)


def verify_quote_integrity(
    verbatim_quote: Optional[str],
    hits: Sequence[SearchHit],
    domain_auditor: Optional[DomainAuditor] = None,
) -> QuoteIntegrityResult:
    """Verify whether an alleged verbatim quote matches credible reporting or is mutated/fabricated."""
    if not verbatim_quote or not verbatim_quote.strip():
        return QuoteIntegrityResult(
            has_verbatim_quote=False,
            best_match_score=0.0,
            matched_source_url=None,
            is_suspected_mutation=False,
            integrity_note="No verbatim quote alleged in claim.",
        )

    clean_quote = verbatim_quote.strip().strip("\"'")
    if len(clean_quote) < 5:
        return QuoteIntegrityResult(
            has_verbatim_quote=True,
            best_match_score=1.0,
            matched_source_url=None,
            is_suspected_mutation=False,
            integrity_note="Verbatim quote too brief for mutation analysis.",
        )

    auditor = domain_auditor or DomainAuditor()

    best_score = 0.0
    best_url: Optional[str] = None
    has_tier1_or_tier2_coverage = False

    for hit in hits:
        d_audit = auditor.audit_url(hit.url)
        is_authoritative = d_audit.tier in (
            SourceTier.TIER_1_PRIMARY,
            SourceTier.TIER_2_ESTABLISHED_EDITORIAL,
        )

        if is_authoritative:
            has_tier1_or_tier2_coverage = True

        combined_text = f"{hit.title} {hit.snippet}"
        sim = compute_quote_similarity(clean_quote, combined_text)

        if sim > best_score:
            best_score = sim
            best_url = hit.url

    # Suspected mutation condition:
    # Credible Tier 1/2 reporting exists covering the event/speaker, but the alleged quote scored < 0.55
    if has_tier1_or_tier2_coverage and best_score < 0.55:
        return QuoteIntegrityResult(
            has_verbatim_quote=True,
            best_match_score=best_score,
            matched_source_url=best_url,
            is_suspected_mutation=True,
            integrity_note=(
                f"Suspected quote mutation or misattribution: Credible Tier 1/2 reporting covers this event, "
                f"but the alleged quote achieved only {best_score:.2f} text alignment (< 0.55). "
                "The quote appears altered, doctored, or falsely attributed."
            ),
        )

    if best_score >= 0.55:
        return QuoteIntegrityResult(
            has_verbatim_quote=True,
            best_match_score=best_score,
            matched_source_url=best_url,
            is_suspected_mutation=False,
            integrity_note=(
                f"Quote integrity verified: Verbatim quote matches authoritative reporting "
                f"({best_score:.2f} alignment) from {best_url}."
            ),
        )

    return QuoteIntegrityResult(
        has_verbatim_quote=True,
        best_match_score=best_score,
        matched_source_url=best_url,
        is_suspected_mutation=False,
        integrity_note="No authoritative Tier 1/2 reporting discovered to cross-examine quote fidelity.",
    )
