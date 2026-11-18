# Contributing to Epistemic Guard

Thank you for your interest in contributing to `epistemic-guard`! 

`epistemic-guard` is an open-source, model-agnostic provenance auditing and two-sided listening engine designed to slow down viral contagion and analyze asymmetric discourse with mathematical determinism and zero hallucinations.

---

## Code of Conduct

We are committed to maintaining a calm, welcoming, and scientifically rigorous community. Discourse in issues and pull requests should adhere to the same principles we encode in the system: steel-manning opposing viewpoints, grounding claims in primary evidence, and de-escalating emotive friction.

---

## Architectural Principles & Constraints

When submitting code to `epistemic-guard`, please respect the core invariants:

1. **Zero Hallucination Quantitative Invariants:**
   - All counts (`total_claims`, `verified_shareable_count`, `unconfirmed_blocked_count`, `recycled_content_count`, `average_emotional_arousal`) MUST be computed deterministically in Python. The LLM must never invent or guess metrics.
2. **Model Agnostic Inference:**
   - Always route LLM completions through `StructuredLLMClient` (configured via OpenAI-compatible `Settings`) to ensure compatibility with local servers (`Ollama`, `vLLM`, `llama.cpp`) and cloud providers.
3. **Deterministic Domain Tiering:**
   - Domain classification relies on deterministic suffix/registered-domain matching from `config/source_tiers.yaml`. Never classify domains via LLM inference.
4. **100% Offline Testing:**
   - Every unit test in `tests/` and benchmark evaluation in `benchmarks/` must execute completely offline without live network dependencies, using `MockSearchProvider` and mocked LLM fixtures.

---

## Development Setup

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/your-org/epistemic-guard.git
cd epistemic-guard

# Create and activate virtual environment
python -m venv .venv

# On Linux/macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Install editable package with dev dependencies
pip install -e ".[dev]"
```

### 2. Verify Installation

```bash
# Run full unit test suite
pytest -v

# Run reproducible offline benchmark harness
python benchmarks/evaluate.py
```

---

## Adding New Domains to `config/source_tiers.yaml`

To expand domain coverage:

1. Open `config/source_tiers.yaml`.
2. Locate the appropriate tier:
   - `tier_1_primary`: Official wire services (Reuters, AP), primary scientific registries, official government portals (`.gov`, `.mil`).
   - `tier_2_established_editorial`: Newsrooms with published editorial correction policies, mastheads, and investigative reporting standards.
   - `tier_3_specialized_advocacy`: Think tanks, policy institutes, industry trade publications, or advocacy groups.
   - `tier_4_user_generated`: Social media platforms (X/Twitter, TikTok, Reddit, Telegram) lacking pre-publication editorial review.
   - `tier_5_satire_parody`: Humorous or satirical outlets (The Onion, Babylon Bee) prone to literal misinterpretation.
3. Add the apex registered domain (e.g. `example.com` or specific FQDN).
4. Run `pytest tests/test_domain_auditor.py` to ensure the classification works as expected.

---

## Contributing Benchmark Scenarios to `benchmarks/dataset.jsonl`

We welcome new evaluation cases representing emerging vectors of viral misinformation, satirical confusion, or two-sided discourse:

1. Open `benchmarks/dataset.jsonl`.
2. Append a single-line JSON object adhering to the schema:
   ```json
   {
     "id": "case-XX-descriptive-slug",
     "category": "fake_viral_quote | recycled_old_media | circular_reporting | satire_misattribution | verified_primary | asymmetric_two_sided",
     "topic": "Concise summary of scenario",
     "discourse_inputs": ["Post text with URL..."],
     "extracted_claims": [...],
     "mock_search_hits": [...],
     "reference_now_iso": "2026-11-19T12:00:00Z",
     "expected": {
       "expected_shareable": false,
       "expected_verdict": "DO_NOT_SHARE_UNCONFIRMED",
       "expected_recycled": false,
       "expected_asymmetry": false
     }
   }
   ```
3. Run `python benchmarks/evaluate.py` to confirm the evaluation harness passes at $\ge 95\%$ accuracy.

---

## Submitting a Pull Request

Before opening a PR:
- [ ] Ensure all unit tests pass: `pytest -q`
- [ ] Ensure benchmark evaluation passes: `python benchmarks/evaluate.py`
- [ ] Format code cleanly: `ruff format` and `ruff check` (or flake8/black)
- [ ] Keep commits clean, descriptive, and atomic (`feat: ...`, `fix: ...`, `docs: ...`)
