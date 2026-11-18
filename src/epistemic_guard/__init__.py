from __future__ import annotations

from epistemic_guard.config import Settings, get_settings
from epistemic_guard.extraction import ClaimExtractor, extract_urls
from epistemic_guard.llm import StructuredLLMClient, clean_json_payload
from epistemic_guard.graph import (
    EpistemicGraphState,
    EpistemicGuardPipeline,
    build_epistemic_graph,
)
from epistemic_guard.interfaces import (
    cli_app,
    create_app,
    create_mcp_server,
)
from epistemic_guard.interfaces.web_ui import render_web_ui
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
from epistemic_guard.tools.domain_auditor import DomainAuditor, detect_lookalike_domain
from epistemic_guard.tools.provenance_resolver import ProvenanceInvestigator
from epistemic_guard.tools.quote_matcher import (
    QuoteIntegrityResult,
    compute_quote_similarity,
    verify_quote_integrity,
)
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

__version__ = "0.2.0"

__all__ = [
    "__version__",
    "Settings",
    "get_settings",
    "SourceTier",
    "EvidenceType",
    "ProvenanceVerdict",
    "DomainAuditResult",
    "WhereProvenance",
    "WhenProvenance",
    "EvidenceProvenance",
    "SourceRecord",
    "ClaimAuditRequest",
    "ProvenanceAuditResult",
    "EmotionalFraming",
    "ExtractedClaim",
    "ExtractionBatchResult",
    "DomainAuditor",
    "detect_lookalike_domain",
    "QuoteIntegrityResult",
    "compute_quote_similarity",
    "verify_quote_integrity",
    "StructuredLLMClient",
    "clean_json_payload",
    "ClaimExtractor",
    "extract_urls",
    "SearchHit",
    "SearchProvider",
    "MockSearchProvider",
    "DuckDuckGoSearchProvider",
    "TavilySearchProvider",
    "build_provenance_queries",
    "TemporalAuditResult",
    "evaluate_temporal_consistency",
    "parse_flexible_date",
    "ProvenanceInvestigator",
    "ClaimWithAudit",
    "NarrativeSideSummary",
    "SideNarrativeDraft",
    "SynthesisLLMOutput",
    "TwoSidedListeningReport",
    "EpistemicGraphState",
    "build_epistemic_graph",
    "EpistemicGuardPipeline",
    "cli_app",
    "create_app",
    "create_mcp_server",
    "render_web_ui",
]
