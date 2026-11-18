from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from epistemic_guard.extraction.extractor import ClaimExtractor
from epistemic_guard.graph.nodes import (
    create_audit_node,
    create_extract_node,
    create_synthesize_node,
)
from epistemic_guard.graph.state import EpistemicGraphState
from epistemic_guard.llm.client import StructuredLLMClient
from epistemic_guard.schemas import TwoSidedListeningReport
from epistemic_guard.tools.provenance_resolver import ProvenanceInvestigator

logger = logging.getLogger(__name__)


def build_epistemic_graph(
    extractor: Optional[ClaimExtractor] = None,
    investigator: Optional[ProvenanceInvestigator] = None,
    llm_client: Optional[StructuredLLMClient] = None,
) -> CompiledStateGraph:
    """Construct and compile the stateful LangGraph workflow for two-sided provenance listening."""
    active_extractor = extractor or ClaimExtractor()
    active_investigator = investigator or ProvenanceInvestigator()
    active_llm = llm_client or StructuredLLMClient()

    workflow = StateGraph(EpistemicGraphState)

    # Register workflow nodes
    workflow.add_node("extract", create_extract_node(active_extractor))
    workflow.add_node("audit", create_audit_node(active_investigator))
    workflow.add_node("synthesize", create_synthesize_node(active_llm))

    # Define execution graph topology
    workflow.set_entry_point("extract")
    workflow.add_edge("extract", "audit")
    workflow.add_edge("audit", "synthesize")
    workflow.add_edge("synthesize", END)

    return workflow.compile()


class EpistemicGuardPipeline:
    """High-level facade orchestrating end-to-end two-sided listening and provenance auditing."""

    def __init__(
        self,
        extractor: Optional[ClaimExtractor] = None,
        investigator: Optional[ProvenanceInvestigator] = None,
        llm_client: Optional[StructuredLLMClient] = None,
    ) -> None:
        self.extractor = extractor or ClaimExtractor()
        self.investigator = investigator or ProvenanceInvestigator()
        self.llm_client = llm_client or StructuredLLMClient()
        self.graph = build_epistemic_graph(
            extractor=self.extractor,
            investigator=self.investigator,
            llm_client=self.llm_client,
        )

    def analyze(
        self,
        texts: str | Sequence[str],
        reference_now: Optional[datetime] = None,
    ) -> TwoSidedListeningReport:
        """Execute end-to-end extraction, provenance auditing, and multi-perspective synthesis."""
        if isinstance(texts, str):
            raw_inputs = [texts]
        else:
            raw_inputs = list(texts)

        ref_dt = reference_now or datetime.now(timezone.utc)
        ref_iso = ref_dt.isoformat()

        initial_state: EpistemicGraphState = {
            "raw_inputs": raw_inputs,
            "reference_now_iso": ref_iso,
            "extracted_claims": [],
            "audited_claims": [],
            "report": None,
        }

        final_state = self.graph.invoke(initial_state)
        report = final_state.get("report")
        if report is None:
            raise RuntimeError("Pipeline failed to produce a TwoSidedListeningReport.")
        return report

    async def async_analyze(
        self,
        texts: str | Sequence[str],
        reference_now: Optional[datetime] = None,
    ) -> TwoSidedListeningReport:
        """Asynchronously execute end-to-end extraction, provenance auditing, and synthesis."""
        if isinstance(texts, str):
            raw_inputs = [texts]
        else:
            raw_inputs = list(texts)

        ref_dt = reference_now or datetime.now(timezone.utc)
        ref_iso = ref_dt.isoformat()

        initial_state: EpistemicGraphState = {
            "raw_inputs": raw_inputs,
            "reference_now_iso": ref_iso,
            "extracted_claims": [],
            "audited_claims": [],
            "report": None,
        }

        final_state = await self.graph.ainvoke(initial_state)
        report = final_state.get("report")
        if report is None:
            raise RuntimeError("Pipeline failed to produce a TwoSidedListeningReport.")
        return report
