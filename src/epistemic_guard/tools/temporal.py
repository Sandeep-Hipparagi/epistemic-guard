from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional, Sequence
from dateutil import parser
from pydantic import BaseModel, ConfigDict, Field

from epistemic_guard.tools.search import SearchHit

logger = logging.getLogger(__name__)

# Regular expressions to detect dates embedded in URLs (e.g. /2021/03/15/ or -2021-03-15-)
DATE_URL_REGEX = re.compile(r"[-/](20\d{2})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])(?:/|[._\-])")
YEAR_MONTH_URL_REGEX = re.compile(r"[-/](20\d{2})[-/](0[1-9]|1[0-2])(?:/|[._\-])")


def parse_flexible_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse arbitrary date or timestamp strings into a timezone-aware UTC datetime."""
    if not date_str:
        return None

    cleaned = date_str.strip()
    if not cleaned or len(cleaned) < 4:
        return None

    try:
        dt = parser.parse(cleaned, fuzzy=True)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception as e:
        logger.debug("Failed to parse date string '%s': %s", date_str, e)
        return None


def extract_date_from_url(url: str) -> Optional[datetime]:
    """Extract publication date from URL path structure if present."""
    if not url:
        return None

    # Try YYYY/MM/DD
    match = DATE_URL_REGEX.search(url)
    if match:
        year, month, day = match.groups()
        try:
            return datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
        except ValueError:
            pass

    # Try YYYY/MM
    match_ym = YEAR_MONTH_URL_REGEX.search(url)
    if match_ym:
        year, month = match_ym.groups()
        try:
            return datetime(int(year), int(month), 1, tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


class TemporalAuditResult(BaseModel):
    """Result of temporal consistency and recycled quote auditing."""

    model_config = ConfigDict(frozen=True)

    claimed_date_iso: Optional[str] = Field(
        default=None,
        description="ISO-8601 formatted string of the alleged publication or speech date.",
    )
    earliest_found_date_iso: Optional[str] = Field(
        default=None,
        description="ISO-8601 formatted string of the earliest discovered primary or editorial report.",
    )
    drift_days: Optional[int] = Field(
        default=None,
        description="Difference in days between claimed/current date and earliest verified occurrence.",
    )
    is_recycled_old_content: bool = Field(
        default=False,
        description="True if content originated significantly prior to claimed or breaking timeframe.",
    )
    temporal_note: str = Field(
        description="Human-readable explanation of temporal evaluation and recency confidence.",
    )


def evaluate_temporal_consistency(
    alleged_date: Optional[str],
    hits: Sequence[SearchHit],
    reference_now: Optional[datetime] = None,
    drift_threshold_days: int = 30,
) -> TemporalAuditResult:
    """Evaluate whether a claim is recycled from past events or aligns with verified dates.

    Args:
        alleged_date: Date string alleged in the claim (or None if breaking/unstated).
        hits: Retrieved SearchHit results from provenance queries.
        reference_now: Reference datetime for 'now' (defaults to current UTC time).
        drift_threshold_days: Days difference required to flag content as recycled.
    """
    now = reference_now or datetime.now(timezone.utc)
    claimed_dt = parse_flexible_date(alleged_date)
    claimed_iso = claimed_dt.isoformat() if claimed_dt else None

    # Discover dates across search hits
    candidate_dates: list[datetime] = []
    for hit in hits:
        # 1. From published_date field
        if hit.published_date:
            parsed_hit_date = parse_flexible_date(hit.published_date)
            if parsed_hit_date:
                candidate_dates.append(parsed_hit_date)

        # 2. From URL structure
        url_date = extract_date_from_url(hit.url)
        if url_date:
            candidate_dates.append(url_date)

    if not candidate_dates:
        return TemporalAuditResult(
            claimed_date_iso=claimed_iso,
            earliest_found_date_iso=None,
            drift_days=None,
            is_recycled_old_content=False,
            temporal_note="No verifiable publication dates discovered in search results.",
        )

    # Sort to find earliest verified reporting
    candidate_dates.sort()
    earliest_dt = candidate_dates[0]
    earliest_iso = earliest_dt.isoformat()

    # Case 1: Specific claimed date was alleged
    if claimed_dt:
        drift = (claimed_dt - earliest_dt).days
        if drift > drift_threshold_days:
            return TemporalAuditResult(
                claimed_date_iso=claimed_iso,
                earliest_found_date_iso=earliest_iso,
                drift_days=drift,
                is_recycled_old_content=True,
                temporal_note=(
                    f"Recycled Content Warning: Claim was alleged for {alleged_date}, "
                    f"but earliest matching report was published {drift} days earlier on {earliest_iso}."
                ),
            )
        else:
            return TemporalAuditResult(
                claimed_date_iso=claimed_iso,
                earliest_found_date_iso=earliest_iso,
                drift_days=abs(drift),
                is_recycled_old_content=False,
                temporal_note="Temporal consistency verified: Earliest reporting matches alleged date.",
            )

    # Case 2: No date was alleged (presented as current/breaking viral claim)
    drift_from_now = (now - earliest_dt).days
    if drift_from_now > drift_threshold_days:
        return TemporalAuditResult(
            claimed_date_iso=None,
            earliest_found_date_iso=earliest_iso,
            drift_days=drift_from_now,
            is_recycled_old_content=True,
            temporal_note=(
                f"Recycled Content Warning: Claim presented without date or as breaking, "
                f"but earliest report dates back {drift_from_now} days to {earliest_iso}."
            ),
        )

    return TemporalAuditResult(
        claimed_date_iso=None,
        earliest_found_date_iso=earliest_iso,
        drift_days=drift_from_now,
        is_recycled_old_content=False,
        temporal_note="Temporal consistency verified: Content is contemporary.",
    )
