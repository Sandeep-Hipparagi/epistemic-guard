---
name: Source Tier Domain Proposal
about: Propose adding, recategorizing, or flagging a domain in config/source_tiers.yaml
title: "[DOMAIN] "
labels: ["source-tiers", "governance"]
assignees: ""
---

## Domain Details
- **Registered Apex Domain:** (e.g. `lemonde.fr`, `example-news.org`)
- **Proposed Tier:** 
  - [ ] `TIER_1_PRIMARY` (Primary wire, academic registry, sovereign government, IFCN signatory)
  - [ ] `TIER_2_ESTABLISHED_EDITORIAL` (Accountable newsroom with masthead and corrections policy)
  - [ ] `TIER_3_SECONDARY_ANALYSIS` (Trade publication, tech press, curated newsletter)
  - [ ] `TIER_4_USER_GENERATED` (UGC platform or lookalike domain)
  - [ ] `TIER_5_SATIRE_PARODY` (Satire / parody publication)

## Evidence & Justification
Please provide documentation meeting the criteria in `docs/SOURCE_TIERING_POLICY.md`:
1. **Official Masthead / Editorial Board URL:** 
2. **Published Corrections / Retractions Policy URL:** 
3. **IFCN Signatory or Academic Indexing Record (if Tier 1):** 
4. **Is this domain imitating a known brand (Lookalike)?** 

## Test Verification
- [ ] Confirmed `pytest tests/test_domain_auditor.py` passes with the proposed domain.
- [ ] Confirmed `python benchmarks/evaluate.py` remains at 100% accuracy.
