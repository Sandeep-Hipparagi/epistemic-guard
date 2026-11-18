from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from epistemic_guard.extraction.extractor import ClaimExtractor
from epistemic_guard.graph.state import EpistemicGraphState
from epistemic_guard.llm.client import StructuredLLMClient
from epistemic_guard.schemas import (
    ClaimWithAudit,
    ExtractedClaim,
    NarrativeSideSummary,
    SynthesisLLMOutput,
    TwoSidedListeningReport,
)
from epistemic_guard.tools.provenance_resolver import ProvenanceInvestigator
from epistemic_guard.tools.temporal import parse_flexible_date

logger = logging.getLogger(__name__)


def create_extract_node(extractor: ClaimExtractor):
    """Factory creating the extraction node for the LangGraph workflow."""

    def extract_node(state: EpistemicGraphState) -> dict:
        raw_inputs = state.get("raw_inputs", [])
        extracted: list[ExtractedClaim] = []
        seen_normalized: set[str] = set()

        for raw_text in raw_inputs:
            if not raw_text or not raw_text.strip():
                continue
            batch = extractor.extract(raw_text)
            for claim in batch.claims:
                norm_key = claim.normalized_claim.strip().lower()
                if norm_key not in seen_normalized:
                    seen_normalized.add(norm_key)
                    extracted.append(claim)

        return {"extracted_claims": extracted}

    return extract_node


def create_audit_node(investigator: ProvenanceInvestigator):
    """Factory creating the provenance audit node for the LangGraph workflow."""

    def audit_node(state: EpistemicGraphState) -> dict:
        claims = state.get("extracted_claims", [])
        ref_iso = state.get("reference_now_iso")
        ref_now = parse_flexible_date(ref_iso) or datetime.now(timezone.utc)

        audited_pairs: list[ClaimWithAudit] = []
        for claim in claims:
            audit_result = investigator.investigate_claim(claim, reference_now=ref_now)
            audited_pairs.append(ClaimWithAudit(claim=claim, audit=audit_result))

        return {"audited_claims": audited_pairs}

    return audit_node


def create_synthesize_node(llm_client: StructuredLLMClient):
    """Factory creating the multi-perspective synthesis and metrics node."""

    def synthesize_node(state: EpistemicGraphState) -> dict:
        audited_pairs = state.get("audited_claims", [])
        raw_inputs = state.get("raw_inputs", [])
        ref_iso = state.get("reference_now_iso")
        generated_at = parse_flexible_date(ref_iso) or datetime.now(timezone.utc)

        if not audited_pairs:
            empty_report = TwoSidedListeningReport(
                topic="No verifiable claims detected in input text",
                generated_at=generated_at,
                overall_emotional_temperature=0.0,
                has_high_emotional_contagion=False,
                provenance_asymmetry_detected=False,
                perspectives=[],
                audited_claims=[],
                deescalation_guidance=(
                    "No testable empirical assertions were detected. "
                    "Pause and request primary source links before sharing."
                ),
            )
            return {"report": empty_report}

        # Step 1: Compute deterministic per-side provenance metrics
        claims_by_side: dict[str, list[ClaimWithAudit]] = {}
        for item in audited_pairs:
            side = item.claim.narrative_side or "Neutral"
            claims_by_side.setdefault(side, []).append(item)

        side_metric_drafts: dict[str, dict] = {}
        all_arousal_scores: list[float] = []

        for side_label, side_items in claims_by_side.items():
            tot = len(side_items)
            ver = sum(1 for it in side_items if it.audit.is_safe_to_share())
            unconf = sum(1 for it in side_items if not it.audit.is_safe_to_share())
            rec = sum(
                1
                for it in side_items
                if (
                    it.audit.when.is_recycled_media_risk
                    or "TEMPORAL_DRIFT_RECYCLED_CONTENT" in it.audit.warning_flags
                )
            )
            arousals = [it.claim.emotional_framing.arousal_score for it in side_items]
            all_arousal_scores.extend(arousals)
            avg_arousal = round(sum(arousals) / tot, 2) if tot > 0 else 0.0

            side_metric_drafts[side_label] = {
                "total_claims": tot,
                "verified_shareable_count": ver,
                "unconfirmed_blocked_count": unconf,
                "recycled_content_count": rec,
                "average_emotional_arousal": avg_arousal,
            }

        # Step 2: Global metrics
        tot_all = len(all_arousal_scores)
        overall_temp = round(sum(all_arousal_scores) / tot_all, 2) if tot_all > 0 else 0.0

        # Provenance Asymmetry: True when at least one side is verified shareable while another has zero verified and >=1 blocked
        has_verified_side = any(m["verified_shareable_count"] > 0 for m in side_metric_drafts.values())
        has_blocked_zero_side = any(
            m["verified_shareable_count"] == 0 and m["unconfirmed_blocked_count"] >= 1
            for m in side_metric_drafts.values()
        )
        provenance_asymmetry = has_verified_side and has_blocked_zero_side

        # Emotional contagion threshold
        has_contagion = overall_temp >= 0.70 or any(
            m["unconfirmed_blocked_count"] > 0 and m["average_emotional_arousal"] >= 0.75
            for m in side_metric_drafts.values()
        )

        # Step 3: Format inputs for LLM synthesis
        topic_preview = "\n---\n".join(raw_inputs)[:1500] if raw_inputs else "Viral discourse topic"

        metrics_lines = []
        for side, m in side_metric_drafts.items():
            metrics_lines.append(
                f"- {side}: Total Claims={m['total_claims']}, "
                f"Verified Shareable={m['verified_shareable_count']}, "
                f"Unconfirmed Blocked={m['unconfirmed_blocked_count']}, "
                f"Recycled Content={m['recycled_content_count']}, "
                f"Avg Arousal={m['average_emotional_arousal']}"
            )
        metrics_summary = "\n".join(metrics_lines)

        claims_lines = []
        for idx, it in enumerate(audited_pairs, 1):
            quote_info = f" [Quote: '{it.claim.verbatim_quote}']" if it.claim.verbatim_quote else ""
            claims_lines.append(
                f"{idx}. [{it.claim.narrative_side}] '{it.claim.normalized_claim}'{quote_info} -> "
                f"Verdict: {it.audit.verdict.value} (Shareable: {it.audit.is_shareable}), "
                f"Flags: {it.audit.warning_flags}"
            )
        claims_summary = "\n".join(claims_lines)

        # Step 4: Invoke LLM for charitable steel-manning and de-escalation guidance
        try:
            llm_output = llm_client.generate_structured(
                prompt_name="two_sided_synthesis",
                response_model=SynthesisLLMOutput,
                prompt_vars={
                    "topic_context": topic_preview,
                    "per_side_metrics": metrics_summary,
                    "audited_claims_summary": claims_summary,
                },
            )
        except Exception as e:
            logger.warning("LLM synthesis generation failed (%s); constructing fallback synthesis.", e)
            llm_output = SynthesisLLMOutput(
                topic_title="Discourse Analysis",
                side_drafts=[],
                deescalation_guidance=(
                    "Provenance audit complete. Please verify primary media and named outlets "
                    "before sharing claims with high emotional arousal."
                ),
            )

        # Step 5: Merge deterministic metrics with steel-manned narratives
        draft_lookup = {d.side_label.strip(): d for d in llm_output.side_drafts}
        perspectives: list[NarrativeSideSummary] = []

        for side_label, metrics in side_metric_drafts.items():
            draft = draft_lookup.get(side_label)
            if draft:
                steel_summary = draft.steel_manned_summary
                key_args = draft.key_arguments
            else:
                # Fallback steel-man from claims
                side_claim_texts = [it.claim.normalized_claim for it in claims_by_side[side_label]]
                steel_summary = f"Perspective centering on: {'; '.join(side_claim_texts[:2])}."
                key_args = side_claim_texts[:3]

            perspectives.append(
                NarrativeSideSummary(
                    side_label=side_label,
                    steel_manned_summary=steel_summary,
                    key_arguments=key_args,
                    total_claims=metrics["total_claims"],
                    verified_shareable_count=metrics["verified_shareable_count"],
                    unconfirmed_blocked_count=metrics["unconfirmed_blocked_count"],
                    recycled_content_count=metrics["recycled_content_count"],
                    average_emotional_arousal=metrics["average_emotional_arousal"],
                )
            )

        report = TwoSidedListeningReport(
            topic=llm_output.topic_title or "Discourse Provenance Report",
            generated_at=generated_at,
            overall_emotional_temperature=overall_temp,
            has_high_emotional_contagion=has_contagion,
            provenance_asymmetry_detected=provenance_asymmetry,
            perspectives=perspectives,
            audited_claims=audited_pairs,
            deescalation_guidance=llm_output.deescalation_guidance,
        )

        return {"report": report}

    return synthesize_node
