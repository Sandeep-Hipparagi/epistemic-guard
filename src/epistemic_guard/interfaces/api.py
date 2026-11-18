from __future__ import annotations

from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from epistemic_guard.graph.workflow import EpistemicGuardPipeline
from epistemic_guard.schemas import DomainAuditResult, TwoSidedListeningReport
from epistemic_guard.tools.domain_auditor import DomainAuditor
from epistemic_guard.tools.temporal import parse_flexible_date


class AuditUrlRequest(BaseModel):
    url: str = Field(min_length=1, description="The URL or domain to audit.")


class AnalyzeRequest(BaseModel):
    texts: list[str] = Field(
        min_length=1,
        description="One or more text statements, viral posts, or articles to analyze.",
    )
    reference_now_iso: Optional[str] = Field(
        default=None,
        description="Optional ISO datetime string representing 'now' for temporal drift evaluation.",
    )


def create_app(
    pipeline: Optional[EpistemicGuardPipeline] = None,
    auditor: Optional[DomainAuditor] = None,
) -> FastAPI:
    """Create and configure the FastAPI application with dependency injection."""
    app = FastAPI(
        title="Epistemic Guard API",
        version="0.1.0",
        description="Model-Agnostic Provenance Auditing and Two-Sided Listening Service",
    )

    active_pipeline = pipeline or EpistemicGuardPipeline()
    active_auditor = auditor or DomainAuditor()

    @app.get("/health")
    def health_check() -> dict[str, str]:
        """Health and liveness check endpoint."""
        return {"status": "ok", "version": "0.1.0"}

    @app.post("/v1/audit/url", response_model=DomainAuditResult)
    def audit_url_endpoint(req: AuditUrlRequest) -> DomainAuditResult:
        """Audit a domain URL and return its deterministic accountability tier."""
        url = req.url.strip()
        if not url:
            raise HTTPException(status_code=400, detail="URL cannot be empty.")
        return active_auditor.audit_url(url)

    @app.post("/v1/analyze", response_model=TwoSidedListeningReport)
    def analyze_endpoint(req: AnalyzeRequest) -> TwoSidedListeningReport:
        """Run the end-to-end two-sided listening and provenance auditing pipeline."""
        if not req.texts:
            raise HTTPException(status_code=400, detail="At least one text input is required.")

        ref_now = parse_flexible_date(req.reference_now_iso) if req.reference_now_iso else None
        try:
            return active_pipeline.analyze(req.texts, reference_now=ref_now)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Pipeline analysis failed: {e}")

    return app


# Default module-level instance for ASGI servers (uvicorn epistemic_guard.interfaces.api:app)
app = create_app()
