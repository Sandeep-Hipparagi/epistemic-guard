---
name: Benchmark Dataset Case Submission
about: Propose a new real-world viral misinformation or discourse case for benchmarks/dataset.jsonl
title: "[BENCHMARK] "
labels: ["benchmark", "dataset"]
assignees: ""
---

## Scenario Overview
- **Scenario Slug:** (e.g. `case-17-synthetic-audio-leak`)
- **Category:** `fake_viral_quote` | `recycled_old_media` | `circular_reporting` | `satire_misattribution` | `verified_primary` | `asymmetric_two_sided` | `quote_mutation` | `lookalike_impersonation`
- **Topic Summary:** 

## Context & Real-World Precedent
Briefly describe the viral incident, rumor, or controversy this test case models (links to news coverage or fact-checks appreciated).

## Proposed Dataset JSON Entry
Please format as a valid entry for `benchmarks/dataset.jsonl`:

```json
{
  "id": "case-XX-descriptive-slug",
  "category": "fake_viral_quote",
  "topic": "Concise summary of the scenario",
  "discourse_inputs": [
    "Raw viral post text or claim with URL: https://example.com/post/123"
  ],
  "extracted_claims": [
    {
      "claim_id": "c1",
      "speaker": "Speaker Name or null",
      "verbatim_quote": "Verbatim quote or null",
      "normalized_claim": "Clear factual assertion in indicative mood.",
      "alleged_venue": "Press Briefing or null",
      "alleged_date": "2026-11-19 or null",
      "cited_urls": ["https://example.com/post/123"],
      "narrative_side": "Neutral",
      "emotional_framing": {
        "arousal_score": 0.85,
        "primary_emotion": "outrage",
        "manipulation_cues": ["unverified_leak_claim"]
      }
    }
  ],
  "mock_search_hits": [
    {
      "title": "Authoritative Wire Coverage or Primary Record",
      "url": "https://www.reuters.com/world/example-coverage",
      "snippet": "Primary reporting text confirming or refuting the claim.",
      "published_date": "2026-11-19",
      "source_query": "search query"
    }
  ],
  "reference_now_iso": "2026-11-19T12:00:00Z",
  "expected": {
    "expected_shareable": false,
    "expected_verdict": "DO_NOT_SHARE_UNCONFIRMED",
    "expected_recycled": false,
    "expected_asymmetry": false,
    "expected_warning_flags": ["NO_PRIMARY_MEDIA_OR_NAMED_OUTLET"]
  }
}
```

## Validation Checklist
- [ ] Confirmed the proposed case reproduces reliably with `MockSearchProvider`.
- [ ] Tested locally: `python benchmarks/evaluate.py` passes with $\ge 95\%$ accuracy.
