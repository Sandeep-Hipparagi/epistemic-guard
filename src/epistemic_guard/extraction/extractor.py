from __future__ import annotations

import hashlib
import re
from typing import Optional

from epistemic_guard.llm.client import StructuredLLMClient
from epistemic_guard.schemas import (
    ClaimAuditRequest,
    ExtractedClaim,
    ExtractionBatchResult,
    ProvenanceAuditResult,
)
from epistemic_guard.tools.domain_auditor import DomainAuditor

# Robust URL extraction pattern for unstructured text (with or without scheme)
URL_PATTERN = re.compile(
    r"""(?xi)
    \b
    (?:
      https?://[^\s<>"'{}|\\^`]+
      |
      (?:www\.)[^\s<>"'{}|\\^`]+
    )
    """
)

TRAILING_PUNCTUATION = ".,;:?!)\"']}>"


def extract_urls(text: str) -> list[str]:
    """Deterministically extract and clean all URLs from noisy or informal raw text."""
    if not text:
        return []

    matches = URL_PATTERN.findall(text)
    cleaned_urls: list[str] = []

    for match in matches:
        cleaned = match.strip()
        # Strip trailing punctuation common in prose
        cleaned = cleaned.rstrip(TRAILING_PUNCTUATION)

        # Normalize www. to https://www
        if cleaned.lower().startswith("www."):
            cleaned = f"https://{cleaned}"

        if cleaned and cleaned not in cleaned_urls:
            cleaned_urls.append(cleaned)

    return cleaned_urls


class ClaimExtractor:
    """Model-agnostic structured claim and emotional framing extractor.

    Deconstructs raw viral text, articles, or transcripts into discrete, auditable
    ExtractedClaim objects and evaluates emotional arousal indicators.
    Bridges Phase 1 directly into Phase 0 via DomainAuditor.
    """

    def __init__(
        self,
        llm_client: Optional[StructuredLLMClient] = None,
        auditor: Optional[DomainAuditor] = None,
    ) -> None:
        self._llm_client = llm_client or StructuredLLMClient()
        self._auditor = auditor or DomainAuditor()

    @staticmethod
    def extract_urls(text: str) -> list[str]:
        """Expose URL extraction as a static utility method."""
        return extract_urls(text)

    def extract(self, raw_text: str) -> ExtractionBatchResult:
        """Extract claims, quotes, and emotional framing profiles from raw text."""
        cleaned_text = raw_text.strip() if raw_text else ""
        text_hash = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()

        if not cleaned_text:
            return ExtractionBatchResult(
                raw_text_hash=text_hash,
                overall_emotional_intensity=0.0,
                claims=[],
            )

        # 1. Deterministic regex URL extraction (never rely solely on LLM to copy links)
        detected_urls = self.extract_urls(cleaned_text)

        # 2. Invoke structured extraction via LLM
        batch_result = self._llm_client.generate_structured(
            prompt_name="claim_extraction",
            response_model=ExtractionBatchResult,
            prompt_vars={"raw_text": cleaned_text},
        )

        # 3. Deterministic reconciliation: ensure text hash and detected URLs are preserved
        reconciled_claims: list[ExtractedClaim] = []
        for claim in batch_result.claims:
            claim_urls = list(claim.cited_urls)
            # If the claim has no cited URLs but the raw input contained URLs, attach them
            if not claim_urls and detected_urls:
                claim_urls = list(detected_urls)
            else:
                # Merge any detected URLs not yet present
                for u in detected_urls:
                    if u not in claim_urls:
                        claim_urls.append(u)

            updated_claim = ExtractedClaim(
                claim_id=claim.claim_id,
                speaker=claim.speaker,
                verbatim_quote=claim.verbatim_quote,
                normalized_claim=claim.normalized_claim,
                alleged_venue=claim.alleged_venue,
                alleged_date=claim.alleged_date,
                cited_urls=claim_urls,
                narrative_side=claim.narrative_side,
                emotional_framing=claim.emotional_framing,
            )
            reconciled_claims.append(updated_claim)

        return ExtractionBatchResult(
            raw_text_hash=text_hash,
            overall_emotional_intensity=batch_result.overall_emotional_intensity,
            claims=reconciled_claims,
        )

    async def async_extract(self, raw_text: str) -> ExtractionBatchResult:
        """Asynchronously extract claims, quotes, and emotional framing profiles."""
        cleaned_text = raw_text.strip() if raw_text else ""
        text_hash = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()

        if not cleaned_text:
            return ExtractionBatchResult(
                raw_text_hash=text_hash,
                overall_emotional_intensity=0.0,
                claims=[],
            )

        detected_urls = self.extract_urls(cleaned_text)

        batch_result = await self._llm_client.async_generate_structured(
            prompt_name="claim_extraction",
            response_model=ExtractionBatchResult,
            prompt_vars={"raw_text": cleaned_text},
        )

        reconciled_claims: list[ExtractedClaim] = []
        for claim in batch_result.claims:
            claim_urls = list(claim.cited_urls)
            if not claim_urls and detected_urls:
                claim_urls = list(detected_urls)
            else:
                for u in detected_urls:
                    if u not in claim_urls:
                        claim_urls.append(u)

            updated_claim = ExtractedClaim(
                claim_id=claim.claim_id,
                speaker=claim.speaker,
                verbatim_quote=claim.verbatim_quote,
                normalized_claim=claim.normalized_claim,
                alleged_venue=claim.alleged_venue,
                alleged_date=claim.alleged_date,
                cited_urls=claim_urls,
                narrative_side=claim.narrative_side,
                emotional_framing=claim.emotional_framing,
            )
            reconciled_claims.append(updated_claim)

        return ExtractionBatchResult(
            raw_text_hash=text_hash,
            overall_emotional_intensity=batch_result.overall_emotional_intensity,
            claims=reconciled_claims,
        )

    def extract_and_audit(
        self,
        raw_text: str,
        auditor: Optional[DomainAuditor] = None,
    ) -> list[tuple[ExtractedClaim, ProvenanceAuditResult]]:
        """Bridge Phase 1 into Phase 0: Extract all claims and execute deterministic provenance audits."""
        batch = self.extract(raw_text)
        active_auditor = auditor or self._auditor

        audit_results: list[tuple[ExtractedClaim, ProvenanceAuditResult]] = []
        for claim in batch.claims:
            request = claim.to_audit_request()
            provenance_result = active_auditor.evaluate_claim(request)
            audit_results.append((claim, provenance_result))

        return audit_results

    async def async_extract_and_audit(
        self,
        raw_text: str,
        auditor: Optional[DomainAuditor] = None,
    ) -> list[tuple[ExtractedClaim, ProvenanceAuditResult]]:
        """Asynchronously extract all claims and execute deterministic provenance audits."""
        batch = await self.async_extract(raw_text)
        active_auditor = auditor or self._auditor

        audit_results: list[tuple[ExtractedClaim, ProvenanceAuditResult]] = []
        for claim in batch.claims:
            request = claim.to_audit_request()
            provenance_result = active_auditor.evaluate_claim(request)
            audit_results.append((claim, provenance_result))

        return audit_results
