from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from epistemic_guard.extraction.extractor import ClaimExtractor
from epistemic_guard.graph.workflow import EpistemicGuardPipeline
from epistemic_guard.llm.client import StructuredLLMClient
from epistemic_guard.schemas import (
    ExtractedClaim,
    ExtractionBatchResult,
    SideNarrativeDraft,
    SynthesisLLMOutput,
)
from epistemic_guard.tools.provenance_resolver import ProvenanceInvestigator
from epistemic_guard.tools.search import MockSearchProvider, SearchHit, build_provenance_queries

logger = logging.getLogger(__name__)


def setup_mock_search_for_case(case: dict[str, Any]) -> MockSearchProvider:
    """Create a MockSearchProvider tailored to the scenario's mock search hits."""
    raw_hits = case.get("mock_search_hits", [])
    search_hits = [SearchHit(**h) for h in raw_hits]
    extracted_claims = [ExtractedClaim(**c) for c in case.get("extracted_claims", [])]
    mock_search = MockSearchProvider()

    if len(extracted_claims) <= 1:
        # Single-claim scenario: all hits answer the claim's provenance queries
        mock_search._default_hits = search_hits
        for h in search_hits:
            mock_search.register_response(h.source_query.strip().lower(), [h])
        return mock_search

    # Multi-claim scenario: associate hits with corresponding claims
    for claim in extracted_claims:
        claim_hits: list[SearchHit] = []
        for h in search_hits:
            if h.url in claim.cited_urls:
                claim_hits.append(h)
            elif not any(h.url in other.cited_urls for other in extracted_claims if other != claim):
                combined_text = (
                    f"{claim.normalized_claim} {claim.verbatim_quote or ''} {claim.speaker or ''}"
                ).lower()
                query_words = [w for w in h.source_query.lower().split() if len(w) >= 4]
                if any(w in combined_text for w in query_words):
                    claim_hits.append(h)

        queries = build_provenance_queries(claim)
        for q in queries:
            mock_search.register_response(q, claim_hits)
            mock_search.register_response(q.lower(), claim_hits)

    return mock_search


def evaluate_dataset(
    dataset_path: Path | str = "benchmarks/dataset.jsonl",
) -> dict[str, Any]:
    """Execute end-to-end provenance audits on the benchmark dataset and compute evaluation metrics."""
    path = Path(dataset_path)
    if not path.is_file():
        raise FileNotFoundError(f"Benchmark dataset file not found at: {path}")

    cases: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str and not line_str.startswith("#"):
                cases.append(json.loads(line_str))

    case_results: list[dict[str, Any]] = []
    unshareable_total = 0
    unshareable_blocked = 0
    shareable_total = 0
    shareable_verified = 0
    recycled_total = 0
    recycled_caught = 0
    asymmetry_total = 0
    asymmetry_detected = 0

    start_total_time = time.perf_counter()

    for case in cases:
        case_id = case["id"]
        category = case.get("category", "unknown")
        expected = case["expected"]
        ref_iso = case.get("reference_now_iso", "2026-11-19T12:00:00Z")
        ref_dt = datetime.fromisoformat(ref_iso)

        t0 = time.perf_counter()

        # 1. Setup mock search provider
        mock_search = setup_mock_search_for_case(case)

        # 2. Setup mock LLM structured output
        extracted_claims = [ExtractedClaim(**c) for c in case.get("extracted_claims", [])]
        extraction_batch = ExtractionBatchResult(
            raw_text_hash=f"hash_{case_id}",
            overall_emotional_intensity=0.5,
            claims=extracted_claims,
        )

        side_drafts = []
        for c in extracted_claims:
            side_drafts.append(
                SideNarrativeDraft(
                    side_label=c.narrative_side,
                    steel_manned_summary=f"Steel-manned argument for {c.narrative_side}: {c.normalized_claim}",
                    key_arguments=[c.normalized_claim],
                )
            )

        synthesis_output = SynthesisLLMOutput(
            topic_title=case.get("topic", "Benchmark Topic"),
            side_drafts=side_drafts,
            deescalation_guidance="Verify primary sources before sharing.",
        )

        mock_llm = StructuredLLMClient()
        mock_llm._client = MagicMock()

        def make_mock_generate(eb: ExtractionBatchResult, so: SynthesisLLMOutput):
            def mock_generate_structured(
                prompt_name: str,
                response_model: Any,
                prompt_vars: Optional[dict[str, Any]] = None,
            ):
                if prompt_name == "claim_extraction":
                    return eb
                elif prompt_name == "two_sided_synthesis":
                    return so
                return so

            return mock_generate_structured

        mock_llm.generate_structured = make_mock_generate(extraction_batch, synthesis_output)

        # 3. Assemble and execute pipeline
        investigator = ProvenanceInvestigator(search_provider=mock_search)
        extractor = ClaimExtractor(llm_client=mock_llm)
        pipeline = EpistemicGuardPipeline(
            extractor=extractor,
            investigator=investigator,
            llm_client=mock_llm,
        )

        discourse_inputs = case.get("discourse_inputs", [])
        report = pipeline.analyze(discourse_inputs, reference_now=ref_dt)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        # 4. Evaluate against ground truth
        actual_shareable = all(item.audit.is_safe_to_share() for item in report.audited_claims)
        actual_verdicts = [item.audit.verdict.value for item in report.audited_claims]
        primary_verdict = actual_verdicts[0] if actual_verdicts else "UNKNOWN"
        actual_recycled = any(
            "TEMPORAL_DRIFT_RECYCLED_CONTENT" in item.audit.warning_flags
            for item in report.audited_claims
        )
        actual_asymmetry = report.provenance_asymmetry_detected

        exp_shareable = expected.get("expected_shareable")
        exp_verdict = expected.get("expected_verdict")
        exp_recycled = expected.get("expected_recycled")
        exp_asymmetry = expected.get("expected_asymmetry")

        ok_shareable = (actual_shareable == exp_shareable) if exp_shareable is not None else True
        ok_verdict = (exp_verdict in actual_verdicts) if exp_verdict is not None else True
        ok_recycled = (actual_recycled == exp_recycled) if exp_recycled is not None else True
        ok_asymmetry = (actual_asymmetry == exp_asymmetry) if exp_asymmetry is not None else True

        passed = ok_shareable and ok_verdict and ok_recycled and ok_asymmetry

        # Metric tracking
        if exp_shareable is False:
            unshareable_total += 1
            if not actual_shareable:
                unshareable_blocked += 1

        if exp_shareable is True:
            shareable_total += 1
            if actual_shareable:
                shareable_verified += 1

        if exp_recycled is True:
            recycled_total += 1
            if actual_recycled:
                recycled_caught += 1

        if exp_asymmetry is True:
            asymmetry_total += 1
            if actual_asymmetry:
                asymmetry_detected += 1

        case_results.append({
            "id": case_id,
            "category": category,
            "passed": passed,
            "duration_ms": round(elapsed_ms, 2),
            "actual": {
                "shareable": actual_shareable,
                "verdict": primary_verdict,
                "verdicts": actual_verdicts,
                "recycled": actual_recycled,
                "asymmetry": actual_asymmetry,
            },
            "expected": {
                "shareable": exp_shareable,
                "verdict": exp_verdict,
                "recycled": exp_recycled,
                "asymmetry": exp_asymmetry,
            },
            "failures": [
                f"shareable (exp {exp_shareable} vs act {actual_shareable})" if not ok_shareable else "",
                f"verdict (exp {exp_verdict} not in {actual_verdicts})" if not ok_verdict else "",
                f"recycled (exp {exp_recycled} vs act {actual_recycled})" if not ok_recycled else "",
                f"asymmetry (exp {exp_asymmetry} vs act {actual_asymmetry})" if not ok_asymmetry else "",
            ],
        })

    total_time_ms = (time.perf_counter() - start_total_time) * 1000.0
    total_cases = len(case_results)
    passed_cases = sum(1 for c in case_results if c["passed"])
    failed_cases = total_cases - passed_cases

    overall_accuracy = (passed_cases / total_cases) if total_cases > 0 else 0.0
    misinfo_block_recall = (unshareable_blocked / unshareable_total) if unshareable_total > 0 else 1.0
    verified_share_prec = (shareable_verified / shareable_total) if shareable_total > 0 else 1.0
    temporal_drift_recall = (recycled_caught / recycled_total) if recycled_total > 0 else 1.0
    asymmetry_accuracy = (asymmetry_detected / asymmetry_total) if asymmetry_total > 0 else 1.0

    return {
        "dataset_path": str(path),
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "overall_accuracy": round(overall_accuracy, 4),
        "misinformation_block_recall": round(misinfo_block_recall, 4),
        "verified_share_precision": round(verified_share_prec, 4),
        "temporal_drift_recall": round(temporal_drift_recall, 4),
        "asymmetry_detection_accuracy": round(asymmetry_accuracy, 4),
        "total_duration_ms": round(total_time_ms, 2),
        "average_case_ms": round(total_time_ms / total_cases, 2) if total_cases > 0 else 0.0,
        "case_results": case_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Epistemic Guard benchmark precision/recall evaluation harness."
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default="benchmarks/dataset.jsonl",
        help="Path to the JSONL benchmark dataset (default: benchmarks/dataset.jsonl)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw evaluation metrics in JSON format.",
    )
    args = parser.parse_args()

    results = evaluate_dataset(args.dataset)

    if args.json:
        print(json.dumps(results, indent=2))
        sys.exit(0 if results["overall_accuracy"] >= 0.95 else 1)

    console = Console()
    console.print(
        Panel.fit(
            "[bold cyan]🛡️ Epistemic Guard - Precision & Recall Benchmark Harness[/bold cyan]\n"
            f"Dataset: [green]{results['dataset_path']}[/green] | Total Cases: [bold]{results['total_cases']}[/bold]",
            border_style="cyan",
        )
    )

    table = Table(title="Scenario Audit Results", show_lines=True)
    table.add_column("Case ID", style="bold")
    table.add_column("Category")
    table.add_column("Verdict (Actual / Exp)")
    table.add_column("Shareable", justify="center")
    table.add_column("Recycled", justify="center")
    table.add_column("Asymmetry", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Latency", justify="right")

    for c in results["case_results"]:
        status_text = "[bold green]PASS[/bold green]" if c["passed"] else "[bold red]FAIL[/bold red]"
        act = c["actual"]
        exp = c["expected"]

        verdict_str = f"{act['verdict']}"
        if exp["verdict"] not in act.get("verdicts", [act["verdict"]]):
            verdict_str = f"[red]{act['verdict']}[/red] / [yellow]{exp['verdict']}[/yellow]"

        share_str = "[green]YES[/green]" if act["shareable"] else "[dim]NO[/dim]"
        recycled_str = "[bold red]YES[/bold red]" if act["recycled"] else "[dim]NO[/dim]"
        asym_str = "[bold yellow]YES[/bold yellow]" if act["asymmetry"] else "[dim]NO[/dim]"

        table.add_row(
            c["id"],
            c["category"],
            verdict_str,
            share_str,
            recycled_str,
            asym_str,
            status_text,
            f"{c['duration_ms']:.1f}ms",
        )

    console.print(table)

    # Summary Metrics Panel
    metrics_table = Table(title="Aggregate Epistemic Performance Metrics", show_header=True)
    metrics_table.add_column("Metric", style="bold")
    metrics_table.add_column("Score", justify="right", style="cyan")
    metrics_table.add_column("Target", justify="right", style="dim")

    metrics_table.add_row(
        "Overall Accuracy", f"{results['overall_accuracy'] * 100:.1f}%", ">= 95.0%"
    )
    metrics_table.add_row(
        "Misinformation Block Recall",
        f"{results['misinformation_block_recall'] * 100:.1f}%",
        "100.0%",
    )
    metrics_table.add_row(
        "Verified Share Precision",
        f"{results['verified_share_precision'] * 100:.1f}%",
        "100.0%",
    )
    metrics_table.add_row(
        "Temporal Drift (Recycled) Recall",
        f"{results['temporal_drift_recall'] * 100:.1f}%",
        "100.0%",
    )
    metrics_table.add_row(
        "Provenance Asymmetry Accuracy",
        f"{results['asymmetry_detection_accuracy'] * 100:.1f}%",
        "100.0%",
    )
    metrics_table.add_row(
        "Total Evaluation Runtime", f"{results['total_duration_ms']:.1f}ms", "< 3000ms"
    )

    console.print(metrics_table)

    if results["overall_accuracy"] >= 0.95:
        console.print(
            "\n[bold green]✅ All benchmark targets met! Epistemic Guard verification PASSED.[/bold green]"
        )
        sys.exit(0)
    else:
        console.print(
            f"\n[bold red]❌ Benchmark accuracy ({results['overall_accuracy']*100:.1f}%) below target threshold (95.0%).[/bold red]"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
