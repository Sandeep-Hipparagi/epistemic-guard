from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional, Sequence
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from epistemic_guard.graph.workflow import EpistemicGuardPipeline
from epistemic_guard.schemas import ProvenanceVerdict, SourceTier, TwoSidedListeningReport
from epistemic_guard.tools.domain_auditor import DomainAuditor
from epistemic_guard.tools.temporal import parse_flexible_date

app = typer.Typer(
    name="epistemic-guard",
    help="Epistemic Guard: Provenance Auditing & Two-Sided Listening Engine",
    no_args_is_help=True,
)
console = Console()

# Dependency injection hooks for testing
_injected_auditor: Optional[DomainAuditor] = None
_injected_pipeline: Optional[EpistemicGuardPipeline] = None


def set_dependencies(
    auditor: Optional[DomainAuditor] = None,
    pipeline: Optional[EpistemicGuardPipeline] = None,
) -> None:
    """Inject auditor and pipeline instances (primarily for testing)."""
    global _injected_auditor, _injected_pipeline
    _injected_auditor = auditor
    _injected_pipeline = pipeline


def get_auditor() -> DomainAuditor:
    return _injected_auditor or DomainAuditor()


def get_pipeline() -> EpistemicGuardPipeline:
    return _injected_pipeline or EpistemicGuardPipeline()


@app.command("audit-url")
def audit_url_command(
    url: str = typer.Argument(..., help="URL or domain to audit for provenance tier and accountability"),
) -> None:
    """Audit a domain URL and display its deterministic accountability tier and viral risk."""
    auditor = get_auditor()
    res = auditor.audit_url(url)

    tier_color = "cyan"
    if res.tier == SourceTier.TIER_1_PRIMARY:
        tier_color = "bold green"
    elif res.tier == SourceTier.TIER_2_ESTABLISHED_EDITORIAL:
        tier_color = "green"
    elif res.tier == SourceTier.TIER_3_SECONDARY_ANALYSIS:
        tier_color = "yellow"
    elif res.tier == SourceTier.TIER_4_USER_GENERATED:
        tier_color = "bold red"
    elif res.tier == SourceTier.TIER_5_SATIRE_PARODY:
        tier_color = "magenta"

    table = Table(title="Domain Provenance Audit", show_header=True, header_style="bold magenta")
    table.add_column("Property", style="dim", width=22)
    table.add_column("Value")

    table.add_row("Input URL", res.url)
    table.add_row("Registered Domain", res.registered_domain)
    table.add_row("Assigned Tier", f"[{tier_color}]{res.tier.value}[/{tier_color}]")
    table.add_row("Tier Classification", res.tier_name)
    table.add_row("Primary / Editorial?", "Yes (Accountable)" if res.is_primary_or_editorial else "No")
    table.add_row("User-Generated Content?", "[red]Yes (Unmoderated UGC)[/red]" if res.is_social_media else "No")
    table.add_row("Satire / Parody?", "[magenta]Yes (Humor/Satire)[/magenta]" if res.is_satire else "No")
    if res.notes:
        table.add_row("Auditor Notes", res.notes)

    console.print(table)


@app.command("analyze")
def analyze_command(
    texts: list[str] = typer.Argument(..., help="One or more statements, viral posts, or articles to analyze"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON report"),
    reference_now: Optional[str] = typer.Option(
        None,
        "--reference-now",
        help="Optional ISO datetime string representing 'now' for temporal drift testing",
    ),
) -> None:
    """Execute end-to-end provenance auditing, temporal drift detection, and two-sided listening."""
    pipeline = get_pipeline()
    ref_dt = parse_flexible_date(reference_now) if reference_now else datetime.now(timezone.utc)

    report: TwoSidedListeningReport = pipeline.analyze(texts, reference_now=ref_dt)

    if json_output:
        typer.echo(report.model_dump_json(indent=2))
        return

    # 1. Pre-Share Friction Banner
    has_unconfirmed = any(not it.audit.is_safe_to_share() for it in report.audited_claims)
    has_recycled = any(
        it.audit.when.is_recycled_media_risk or "TEMPORAL_DRIFT_RECYCLED_CONTENT" in it.audit.warning_flags
        for it in report.audited_claims
    )

    if has_recycled:
        banner = Panel(
            "[bold white on red] 🚨 PRE-SHARE FRICTION: RECYCLED CONTENT ALERT [/bold white on red]\n\n"
            "[bold red]DO NOT SHARE AS CURRENT NEWS.[/bold red] One or more claims recycle historical quotes or media "
            "stripped of original temporal context.\n\n"
            f"[dim italic]{report.deescalation_guidance}[/dim italic]",
            title="[bold red]Epistemic Guard Friction Alert[/bold red]",
            border_style="red",
        )
    elif has_unconfirmed:
        banner = Panel(
            "[bold white on red] ⚠️ PRE-SHARE FRICTION: DO NOT SHARE — UNCONFIRMED [/bold white on red]\n\n"
            "[bold yellow]Pause before sharing.[/bold yellow] One or more claims fail core provenance criteria "
            "(missing origin podium, unverified date, or sole source is social media UGC).\n\n"
            f"[dim italic]{report.deescalation_guidance}[/dim italic]",
            title="[bold yellow]Epistemic Guard Friction Alert[/bold yellow]",
            border_style="yellow",
        )
    else:
        banner = Panel(
            "[bold white on green] ✅ PRE-SHARE CHECK: SAFE TO SHARE — VERIFIED PROVENANCE [/bold white on green]\n\n"
            "[bold green]Corroborated by primary media or accountable editorial outlets.[/bold green]\n\n"
            f"[dim italic]{report.deescalation_guidance}[/dim italic]",
            title="[bold green]Epistemic Guard Verified[/bold green]",
            border_style="green",
        )

    console.print()
    console.print(banner)
    console.print()

    # 2. Topic & Epistemic Diagnostics Header
    summary_panel = Panel(
        f"[bold]Topic:[/bold] {report.topic}\n"
        f"[bold]Emotional Temperature:[/bold] {report.overall_emotional_temperature:.2f} "
        f"({'[red]High Viral Contagion[/red]' if report.has_high_emotional_contagion else '[green]Calm / Measured[/green]'})\n"
        f"[bold]Provenance Asymmetry:[/bold] "
        f"({'[bold red]DETECTED (One side verified, opposing side unconfirmed)[/bold red]' if report.provenance_asymmetry_detected else '[green]None[/green]'})\n"
        f"[bold]Total Evaluated Claims:[/bold] {len(report.audited_claims)}",
        title="[bold]Discourse Epistemic Diagnostics[/bold]",
        border_style="blue",
    )
    console.print(summary_panel)
    console.print()

    # 3. 3-Criteria Provenance Table
    if report.audited_claims:
        table = Table(title="3-Criteria Provenance Audit Table", show_header=True, header_style="bold cyan")
        table.add_column("#", width=3)
        table.add_column("Claim / Verbatim Quote", style="white", min_width=25)
        table.add_column("1. Where (Origin)", style="cyan", min_width=15)
        table.add_column("2. When (Date)", style="yellow", min_width=12)
        table.add_column("3. Media / Outlet", style="magenta", min_width=18)
        table.add_column("Verdict", min_width=15)
        table.add_column("Flags", style="red", min_width=15)

        for idx, item in enumerate(report.audited_claims, 1):
            claim = item.claim
            audit = item.audit

            claim_display = claim.normalized_claim
            if claim.verbatim_quote:
                claim_display = f'"{claim.verbatim_quote}"\n[dim]{claim.normalized_claim}[/dim]'

            where_str = audit.where.venue_or_platform or "[red]Missing[/red]"
            when_str = audit.when.date_str or (audit.when.timestamp.strftime("%Y-%m-%d") if audit.when.timestamp else "[red]Missing[/red]")
            evidence_str = audit.evidence.evidence_summary or audit.evidence.evidence_type.value

            verdict_color = "green" if audit.is_safe_to_share() else "bold red"
            verdict_str = f"[{verdict_color}]{audit.verdict.value}[/{verdict_color}]"
            flags_str = "\n".join(audit.warning_flags) if audit.warning_flags else "[dim]None[/dim]"

            table.add_row(
                str(idx),
                claim_display,
                where_str,
                when_str,
                evidence_str,
                verdict_str,
                flags_str,
            )

        console.print(table)
        console.print()

    # 4. Two-Sided Listening Summary
    if report.perspectives:
        p_table = Table(title="Two-Sided Listening & Steel-Manned Perspectives", show_header=True, header_style="bold green")
        p_table.add_column("Perspective", style="bold", width=14)
        p_table.add_column("Verified", justify="center", style="green", width=10)
        p_table.add_column("Blocked", justify="center", style="red", width=10)
        p_table.add_column("Arousal", justify="center", width=10)
        p_table.add_column("Steel-Manned Argument Summary", style="dim white")

        for p in report.perspectives:
            p_table.add_row(
                p.side_label,
                f"{p.verified_shareable_count} / {p.total_claims}",
                str(p.unconfirmed_blocked_count),
                f"{p.average_emotional_arousal:.2f}",
                f"{p.steel_manned_summary}\n[dim]Key arguments: {'; '.join(p.key_arguments)}[/dim]",
            )

        console.print(p_table)
        console.print()


if __name__ == "__main__":
    app()
