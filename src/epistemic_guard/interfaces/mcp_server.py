from __future__ import annotations

import logging
from typing import Any, Optional

try:
    from mcp.server.fastmcp import FastMCP
except (ImportError, ModuleNotFoundError):
    from mcp.server.mcpserver import MCPServer as FastMCP

from epistemic_guard.graph.workflow import EpistemicGuardPipeline
from epistemic_guard.schemas import (
    ClaimAuditRequest,
    DomainAuditResult,
    EmotionalFraming,
    ExtractedClaim,
    TwoSidedListeningReport,
)
from epistemic_guard.tools.domain_auditor import DomainAuditor

logger = logging.getLogger(__name__)


def create_mcp_server(
    pipeline: Optional[EpistemicGuardPipeline] = None,
    auditor: Optional[DomainAuditor] = None,
) -> FastMCP:
    """Create and configure the Model Context Protocol (MCP) server for Epistemic Guard."""
    active_pipeline = pipeline or EpistemicGuardPipeline()
    active_auditor = auditor or DomainAuditor()

    mcp = FastMCP(
        "epistemic-guard",
        description="Epistemic Guard: Provenance Auditing & Two-Sided Listening Engine for AI Agents",
    )

    @mcp.tool()
    def audit_source_url(url: str) -> dict[str, Any]:
        """Classify a URL or domain into deterministic accountability tiers (Tier 1 Primary to Tier 5 Satire) before citing or sharing it."""
        res: DomainAuditResult = active_auditor.audit_url(url)
        return res.model_dump()

    @mcp.tool()
    def check_viral_claim(claim_text: str) -> dict[str, Any]:
        """Audit a single viral quote or claim against the 3 provenance criteria: Where was it said, When was it said, and is there video, audio, or a named outlet behind it."""
        # Use pipeline's investigator directly
        claim = ExtractedClaim(
            claim_id="mcp-claim",
            speaker=None,
            verbatim_quote=None,
            normalized_claim=claim_text.strip(),
            alleged_venue=None,
            alleged_date=None,
            cited_urls=active_pipeline.extractor.extract_urls(claim_text),
            narrative_side="Neutral",
            emotional_framing=EmotionalFraming(
                arousal_score=0.5,
                primary_emotion="neutral",
                manipulation_cues=[],
            ),
        )
        audit_result = active_pipeline.investigator.investigate_claim(claim)
        return audit_result.model_dump()

    @mcp.tool()
    def listen_two_sides(texts: list[str]) -> dict[str, Any]:
        """Execute multi-perspective listening and steel-manned synthesis across opposing posts, threads, or articles to identify provenance asymmetry and de-escalate controversy."""
        report: TwoSidedListeningReport = active_pipeline.analyze(texts)
        return report.model_dump()

    # Attach raw tool functions as attributes on mcp for convenient testing and inspection
    mcp.audit_source_url_func = audit_source_url  # type: ignore[attr-defined]
    mcp.check_viral_claim_func = check_viral_claim  # type: ignore[attr-defined]
    mcp.listen_two_sides_func = listen_two_sides  # type: ignore[attr-defined]

    return mcp


# Module-level instance for server execution
mcp_server = create_mcp_server()


def main() -> None:
    """Entry point for epistemic-guard-mcp console script."""
    mcp_server.run()


if __name__ == "__main__":
    main()
