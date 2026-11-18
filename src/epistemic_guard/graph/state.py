from __future__ import annotations

from typing import Optional, TypedDict

from epistemic_guard.schemas import (
    ClaimWithAudit,
    ExtractedClaim,
    TwoSidedListeningReport,
)


class EpistemicGraphState(TypedDict, total=False):
    """Shared state container for the LangGraph epistemic listening workflow."""

    raw_inputs: list[str]
    reference_now_iso: Optional[str]
    extracted_claims: list[ExtractedClaim]
    audited_claims: list[ClaimWithAudit]
    report: Optional[TwoSidedListeningReport]
