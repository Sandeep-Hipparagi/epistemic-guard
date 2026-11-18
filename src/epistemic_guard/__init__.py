from __future__ import annotations

from epistemic_guard.config import Settings, get_settings
from epistemic_guard.extraction import ClaimExtractor, extract_urls
from epistemic_guard.llm import StructuredLLMClient, clean_json_payload
from epistemic_guard.schemas import (
    ClaimAuditRequest,
    DomainAuditResult,
    EmotionalFraming,
    EvidenceProvenance,
    EvidenceType,
    ExtractedClaim,
    ExtractionBatchResult,
    ProvenanceAuditResult,
    ProvenanceVerdict,
    SourceRecord,
    SourceTier,
    WhenProvenance,
    WhereProvenance,
)
from epistemic_guard.tools.domain_auditor import DomainAuditor

__version__ = "0.1.0"

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
    "StructuredLLMClient",
    "clean_json_payload",
    "ClaimExtractor",
    "extract_urls",
]
