from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
import yaml
import tldextract

from epistemic_guard.config import get_settings
from epistemic_guard.schemas import (
    ClaimAuditRequest,
    DomainAuditResult,
    EvidenceProvenance,
    EvidenceType,
    ProvenanceAuditResult,
    ProvenanceVerdict,
    SourceRecord,
    SourceTier,
    WhenProvenance,
    WhereProvenance,
)


class DomainAuditor:
    """Deterministic domain auditor and source tiering engine.

    Implements zero-hallucination provenance evaluation. Classifies sources into strict
    accountability tiers and verifies viral claims against the three fundamental provenance questions:
      1. Where was it said?
      2. When was it said?
      3. Is there video, audio, or a named outlet behind it?
    """

    def __init__(self, config_path: Optional[Path | str] = None) -> None:
        if config_path is not None:
            self._config_path = Path(config_path)
        else:
            self._config_path = get_settings().resolve_source_tiers_path()

        self._tier_domains: dict[SourceTier, set[str]] = {tier: set() for tier in SourceTier}
        self._tld_rules: dict[str, SourceTier] = {}
        self._tier_metadata: dict[SourceTier, dict[str, str]] = {}
        self._default_tier: SourceTier = SourceTier.TIER_UNKNOWN

        # Pre-configure tldextract extractor (cache locally)
        self._extractor = tldextract.TLDExtract(
            cache_dir=str(Path.home() / ".cache" / "epistemic_guard_tldextract"),
            include_psl_private_domains=True,
        )

        self._load_config()

    def _load_config(self) -> None:
        """Load source tier definitions and TLD rules from YAML."""
        if not self._config_path.exists():
            # Fallback to defaults if file missing
            self._load_built_in_defaults()
            return

        with open(self._config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # Parse TLD rules
        tld_rules = data.get("tld_rules", {})
        for tld, tier_str in tld_rules.items():
            tld_clean = tld.lstrip(".").lower()
            try:
                self._tld_rules[tld_clean] = SourceTier(tier_str)
            except ValueError:
                continue

        # Parse default tier
        default_tier_str = data.get("default_tier", "TIER_UNKNOWN")
        try:
            self._default_tier = SourceTier(default_tier_str)
        except ValueError:
            self._default_tier = SourceTier.TIER_UNKNOWN

        # Parse tiers
        tiers_data = data.get("tiers", {})
        for tier_key, tier_info in tiers_data.items():
            try:
                tier_enum = SourceTier(tier_key)
            except ValueError:
                continue

            self._tier_metadata[tier_enum] = {
                "name": tier_info.get("name", tier_key),
                "description": tier_info.get("description", ""),
                "trust_level": tier_info.get("trust_level", "UNKNOWN"),
            }

            domains = tier_info.get("domains", [])
            for domain in domains:
                cleaned = domain.strip().lower()
                if cleaned:
                    self._tier_domains[tier_enum].add(cleaned)

    def _load_built_in_defaults(self) -> None:
        """Hardcoded fallback defaults if YAML file cannot be loaded."""
        self._tld_rules = {
            "gov": SourceTier.TIER_1_PRIMARY,
            "mil": SourceTier.TIER_1_PRIMARY,
            "edu": SourceTier.TIER_1_PRIMARY,
        }
        self._tier_domains[SourceTier.TIER_1_PRIMARY] = {
            "reuters.com", "apnews.com", "afp.com", "bloomberg.com", "un.org", "who.int",
            "factcheck.org", "politifact.com", "snopes.com", "nature.com", "science.org"
        }
        self._tier_domains[SourceTier.TIER_2_ESTABLISHED_EDITORIAL] = {
            "nytimes.com", "washingtonpost.com", "wsj.com", "ft.com", "theguardian.com",
            "bbc.com", "bbc.co.uk", "npr.org", "pbs.org", "economist.com"
        }
        self._tier_domains[SourceTier.TIER_3_SECONDARY_ANALYSIS] = {
            "techcrunch.com", "theverge.com", "arstechnica.com", "wired.com", "axios.com",
            "forbes.com", "politico.com", "vox.com", "substack.com"
        }
        self._tier_domains[SourceTier.TIER_4_USER_GENERATED] = {
            "x.com", "twitter.com", "t.co", "facebook.com", "instagram.com", "tiktok.com",
            "reddit.com", "telegram.org", "t.me", "threads.net", "youtube.com", "youtu.be"
        }
        self._tier_domains[SourceTier.TIER_5_SATIRE_PARODY] = {
            "theonion.com", "babylonbee.com", "clickhole.com", "newsthump.com"
        }

    def get_tier_name(self, tier: SourceTier) -> str:
        """Return the human-readable name of a tier."""
        if tier in self._tier_metadata:
            return self._tier_metadata[tier].get("name", tier.value)
        return tier.value.replace("_", " ").title()

    def audit_url(self, url: str) -> DomainAuditResult:
        """Audit a URL string and return deterministic domain classification."""
        cleaned_url = url.strip()
        if not cleaned_url:
            return DomainAuditResult(
                url="",
                raw_domain="",
                registered_domain="",
                subdomain=None,
                suffix=None,
                tier=SourceTier.TIER_UNKNOWN,
                tier_name="Unknown / Invalid Domain",
                is_social_media=False,
                is_satire=False,
                is_primary_or_editorial=False,
                notes="Empty URL provided.",
            )

        extracted = self._extractor(cleaned_url)
        subdomain = extracted.subdomain.lower() if extracted.subdomain else None
        domain = extracted.domain.lower() if extracted.domain else ""
        suffix = extracted.suffix.lower() if extracted.suffix else ""

        if domain and suffix:
            registered_domain = f"{domain}.{suffix}"
        elif domain:
            registered_domain = domain
        else:
            registered_domain = ""

        raw_domain = extracted.fqdn.lower() if extracted.fqdn else registered_domain

        # Classify tier
        tier = self._classify_extracted(registered_domain=registered_domain, suffix=suffix, raw_domain=raw_domain)
        tier_name = self.get_tier_name(tier)

        is_social = tier == SourceTier.TIER_4_USER_GENERATED
        is_satire = tier == SourceTier.TIER_5_SATIRE_PARODY
        is_primary_or_editorial = tier in (
            SourceTier.TIER_1_PRIMARY,
            SourceTier.TIER_2_ESTABLISHED_EDITORIAL,
        )

        notes: list[str] = []
        if is_satire:
            notes.append("Identified satire/parody outlet. High risk of comedic misinterpretation.")
        elif is_social:
            notes.append("User-generated social media platform without editorial oversight.")
        elif tier == SourceTier.TIER_1_PRIMARY:
            notes.append("Primary institutional, wire service, or peer-reviewed domain.")
        elif tier == SourceTier.TIER_2_ESTABLISHED_EDITORIAL:
            notes.append("Established newsroom with verified bylines and correction standards.")
        elif tier == SourceTier.TIER_UNKNOWN:
            notes.append("Unlisted or unrecognized domain. Defaulting to Tier Unknown.")

        return DomainAuditResult(
            url=cleaned_url,
            raw_domain=raw_domain,
            registered_domain=registered_domain,
            subdomain=subdomain,
            suffix=suffix,
            tier=tier,
            tier_name=tier_name,
            is_social_media=is_social,
            is_satire=is_satire,
            is_primary_or_editorial=is_primary_or_editorial,
            notes="; ".join(notes) if notes else None,
        )

    def _classify_extracted(self, registered_domain: str, suffix: str, raw_domain: str) -> SourceTier:
        """Internal classification matching hierarchy."""
        # 1. Satire check takes top priority (even if satire claims another TLD)
        if registered_domain in self._tier_domains[SourceTier.TIER_5_SATIRE_PARODY]:
            return SourceTier.TIER_5_SATIRE_PARODY
        if raw_domain in self._tier_domains[SourceTier.TIER_5_SATIRE_PARODY]:
            return SourceTier.TIER_5_SATIRE_PARODY

        # 2. Top-level domain (TLD) overrides (e.g. .gov, .mil, .edu)
        if suffix:
            suffix_parts = suffix.split(".")
            for part in suffix_parts:
                if part in self._tld_rules:
                    return self._tld_rules[part]
            if suffix in self._tld_rules:
                return self._tld_rules[suffix]

        # 3. Direct domain lookup across tiers in order of precedence
        for tier in (
            SourceTier.TIER_1_PRIMARY,
            SourceTier.TIER_2_ESTABLISHED_EDITORIAL,
            SourceTier.TIER_3_SECONDARY_ANALYSIS,
            SourceTier.TIER_4_USER_GENERATED,
        ):
            if registered_domain in self._tier_domains[tier] or raw_domain in self._tier_domains[tier]:
                return tier

        return self._default_tier

    def classify_domain(self, domain_or_url: str) -> SourceTier:
        """Classify a domain or URL directly into a SourceTier."""
        return self.audit_url(domain_or_url).tier

    def audit_sources(self, sources: list[str | SourceRecord]) -> list[SourceRecord]:
        """Audit a list of URLs or SourceRecord objects and attach domain audit metadata."""
        audited_records: list[SourceRecord] = []
        for item in sources:
            if isinstance(item, str):
                audit = self.audit_url(item)
                # Infer evidence type if possible
                evidence_type = EvidenceType.UNVERIFIED_CLAIM
                has_primary = False
                if audit.is_social_media:
                    evidence_type = EvidenceType.SOCIAL_MEDIA_POST
                elif audit.is_primary_or_editorial:
                    evidence_type = EvidenceType.NAMED_OUTLET_REPORT

                record = SourceRecord(
                    url=item,
                    domain_audit=audit,
                    outlet=audit.registered_domain if audit.registered_domain else None,
                    evidence_type=evidence_type,
                    has_primary_media=has_primary,
                )
                audited_records.append(record)
            elif isinstance(item, SourceRecord):
                # Update domain audit if missing
                if item.domain_audit is None and item.url:
                    item_dict = item.model_dump()
                    item_dict["domain_audit"] = self.audit_url(item.url)
                    audited_records.append(SourceRecord(**item_dict))
                else:
                    audited_records.append(item)
        return audited_records

    def evaluate_claim(self, request: ClaimAuditRequest) -> ProvenanceAuditResult:
        """Execute deterministic provenance auditing on a claim.

        Evaluates the three core questions:
          1. Where was it said? (Venue/platform/root URL)
          2. When was it said? (Timestamp/date to catch recycled quotes)
          3. Is there video, audio, or a named outlet behind it?

        Enforces the zero-hallucination invariant:
        If criteria are not met, or if the sole source is an unverified social media post,
        the claim is flagged as DO_NOT_SHARE_UNCONFIRMED.
        """
        # Step 1: Consolidate all sources
        all_sources: list[SourceRecord] = []

        # Convert raw URLs
        for raw_url in request.raw_urls:
            all_sources.extend(self.audit_sources([raw_url]))

        # Include structured sources (auditing domains if needed)
        all_sources.extend(self.audit_sources(request.sources))

        warning_flags: list[str] = []

        # Step 2: Evaluate Question 1 - WHERE was it said?
        where_identified = False
        is_primary_venue = False
        venue_name = request.alleged_venue
        root_url = None
        best_domain_audit: Optional[DomainAuditResult] = None

        if all_sources:
            # Find the highest quality source for root URL
            sorted_sources = sorted(
                all_sources,
                key=lambda s: (
                    s.domain_audit.tier == SourceTier.TIER_1_PRIMARY if s.domain_audit else False,
                    s.domain_audit.tier == SourceTier.TIER_2_ESTABLISHED_EDITORIAL if s.domain_audit else False,
                    s.has_primary_media,
                ),
                reverse=True,
            )
            top_source = sorted_sources[0]
            root_url = top_source.url
            best_domain_audit = top_source.domain_audit

            if best_domain_audit and best_domain_audit.registered_domain:
                where_identified = True
                if not venue_name:
                    venue_name = best_domain_audit.registered_domain

        if request.alleged_venue and request.alleged_venue.strip():
            where_identified = True
            venue_name = request.alleged_venue.strip()

        # Check if venue is primary (e.g. official podium, wire source, gov site)
        if best_domain_audit and best_domain_audit.tier == SourceTier.TIER_1_PRIMARY:
            is_primary_venue = True

        if not where_identified:
            warning_flags.append("MISSING_ROOT_WHERE_PROVENANCE")

        where_provenance = WhereProvenance(
            venue_or_platform=venue_name,
            root_url=root_url,
            domain_audit=best_domain_audit,
            is_identified=where_identified,
            is_primary_venue=is_primary_venue,
            notes="Origin venue or platform verified." if where_identified else "Origin venue or root platform is unconfirmed.",
        )

        # Step 3: Evaluate Question 2 - WHEN was it said?
        when_timestamp: Optional[datetime] = None
        when_date_str: Optional[str] = request.alleged_date
        is_exact_timestamp = False
        is_recycled_media_risk = False

        for source in all_sources:
            if source.published_at is not None:
                when_timestamp = source.published_at
                is_exact_timestamp = True
                break
            if source.date_str and not when_date_str:
                when_date_str = source.date_str

        when_identified = is_exact_timestamp or (when_date_str is not None and len(when_date_str.strip()) >= 4)

        if not when_identified:
            is_recycled_media_risk = True
            warning_flags.append("MISSING_TIMESTAMP_RECYCLED_RISK")

        when_provenance = WhenProvenance(
            timestamp=when_timestamp,
            date_str=when_date_str,
            is_exact_timestamp=is_exact_timestamp,
            is_recycled_media_risk=is_recycled_media_risk,
            temporal_notes=(
                "Exact publication timestamp verified."
                if is_exact_timestamp
                else (
                    "Date provided but exact timestamp unconfirmed."
                    if when_identified
                    else "Missing publication timestamp. High risk of recycled historical quote or out-of-context replay."
                )
            ),
        )

        # Step 4: Evaluate Question 3 - Is there video, audio, or a named outlet behind it?
        has_primary_media = False
        has_named_outlet = False
        primary_media_types = {EvidenceType.VIDEO, EvidenceType.AUDIO, EvidenceType.PRIMARY_DOCUMENT, EvidenceType.TRANSCRIPT}
        best_evidence_type = EvidenceType.UNVERIFIED_CLAIM
        media_url = None
        outlet_name = None

        for source in all_sources:
            if source.has_primary_media or source.evidence_type in primary_media_types:
                has_primary_media = True
                best_evidence_type = source.evidence_type
                if source.url:
                    media_url = source.url

            if source.domain_audit and source.domain_audit.is_primary_or_editorial:
                has_named_outlet = True
                outlet_name = source.outlet or source.domain_audit.registered_domain
                if best_evidence_type == EvidenceType.UNVERIFIED_CLAIM:
                    best_evidence_type = EvidenceType.NAMED_OUTLET_REPORT

        evidence_provenance = EvidenceProvenance(
            evidence_type=best_evidence_type,
            has_primary_media=has_primary_media,
            has_named_outlet=has_named_outlet,
            outlet_name=outlet_name,
            media_url=media_url,
            evidence_summary=(
                "Backed by primary media (video/audio/document)."
                if has_primary_media
                else (
                    f"Reported by accountable editorial outlet ({outlet_name})."
                    if has_named_outlet
                    else "No video, audio, or accountable named outlet found."
                )
            ),
        )

        if not has_primary_media and not has_named_outlet:
            warning_flags.append("NO_PRIMARY_MEDIA_OR_NAMED_OUTLET")

        # Step 5: Detect Satire, Sole Source UGC, and Decision Branching
        has_satire = any(s.domain_audit and s.domain_audit.is_satire for s in all_sources)
        if has_satire:
            warning_flags.append("SATIRE_PARODY_SOURCE")

        has_tier1 = any(s.domain_audit and s.domain_audit.tier == SourceTier.TIER_1_PRIMARY for s in all_sources)
        has_tier2 = any(s.domain_audit and s.domain_audit.tier == SourceTier.TIER_2_ESTABLISHED_EDITORIAL for s in all_sources)
        all_ugc = bool(all_sources) and all(
            s.domain_audit and s.domain_audit.tier == SourceTier.TIER_4_USER_GENERATED for s in all_sources
        )

        is_sole_source_ugc = (len(all_sources) == 1 and all_ugc and not has_primary_media) or (
            all_ugc and not has_primary_media and not has_named_outlet
        )

        if is_sole_source_ugc:
            warning_flags.append("SOLE_SOURCE_UNVERIFIED_UGC")

        if not all_sources:
            warning_flags.append("NO_SOURCES_EVALUATED")

        # Compute Verdict
        verdict: ProvenanceVerdict
        is_shareable: bool
        recommendation: str
        confidence: float

        if has_satire:
            verdict = ProvenanceVerdict.SATIRE_PARODY_ALERT
            is_shareable = False
            confidence = 0.95
            recommendation = (
                "DO NOT SHARE. The originating source is a recognized satire or parody outlet. "
                "This claim was written as humor or satire and is not a factual event."
            )
        elif not all_sources:
            verdict = ProvenanceVerdict.DO_NOT_SHARE_UNCONFIRMED
            is_shareable = False
            confidence = 0.10
            recommendation = (
                "DO NOT SHARE (UNCONFIRMED). No verifiable source links or evidence were provided. "
                "Pause until primary video/audio or an accountable reporting outlet verifies the claim."
            )
        elif is_sole_source_ugc:
            verdict = ProvenanceVerdict.DO_NOT_SHARE_UNCONFIRMED
            is_shareable = False
            confidence = 0.25
            recommendation = (
                "DO NOT SHARE (UNCONFIRMED). The sole source is an unverified social media post with no "
                "underlying video, audio, or named journalism. Viral claims on social platforms are highly "
                "susceptible to manipulation, satire detachment, and emotional distortion."
            )
        elif not where_identified or not when_identified or (not has_primary_media and not has_named_outlet):
            verdict = ProvenanceVerdict.DO_NOT_SHARE_UNCONFIRMED
            is_shareable = False
            confidence = 0.35
            missing: list[str] = []
            if not where_identified:
                missing.append("origin venue/platform (Where)")
            if not when_identified:
                missing.append("verified timestamp (When)")
            if not has_primary_media and not has_named_outlet:
                missing.append("primary media or accountable newsroom (Evidence)")
            missing_str = ", ".join(missing)
            recommendation = (
                f"DO NOT SHARE (UNCONFIRMED). The claim failed critical provenance checks: missing {missing_str}. "
                "Hold off until independent corroboration is established."
            )
        elif has_tier1 and (has_primary_media or has_tier1):
            verdict = ProvenanceVerdict.VERIFIED_PRIMARY
            is_shareable = True
            confidence = 0.95 if has_primary_media and is_exact_timestamp else 0.88
            recommendation = (
                "VERIFIED. Backed by Tier 1 primary sources / wire reporting with confirmed origin and timestamp. "
                "Clear to reference with direct citation to the primary record."
            )
        elif has_tier2:
            verdict = ProvenanceVerdict.CORROBORATED_SECONDARY
            is_shareable = True
            confidence = 0.85 if has_primary_media else 0.78
            recommendation = (
                "CORROBORATED. Backed by established editorial newsrooms with named bylines and confirmed timing. "
                "Suitable for sharing with attribution."
            )
        else:
            verdict = ProvenanceVerdict.UNVERIFIED_SINGLE_SOURCE
            is_shareable = False
            confidence = 0.45
            recommendation = (
                "HOLD - UNVERIFIED SINGLE SOURCE. The claim has limited secondary reporting without primary media "
                "or Tier 1/2 editorial backing. Recommend awaiting independent confirmation before sharing."
            )

        # Build final deterministic result
        return ProvenanceAuditResult(
            claim_text=request.claim_text,
            verdict=verdict,
            is_shareable=is_shareable,
            where=where_provenance,
            when=when_provenance,
            evidence=evidence_provenance,
            evaluated_sources=all_sources,
            warning_flags=list(dict.fromkeys(warning_flags)),  # preserve order & unique
            recommendation=recommendation,
            confidence_score=round(confidence, 2),
            audited_at=datetime.now(timezone.utc),
        )
