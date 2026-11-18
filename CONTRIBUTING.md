# Contributing to Epistemic Guard

Thank you for your interest in contributing to **`epistemic-guard`**!

`epistemic-guard` is an open-source, model-agnostic provenance auditing and two-sided listening engine designed to slow down viral contagion and analyze asymmetric discourse with mathematical determinism and zero hallucinations.

---

## 🏛️ Code of Conduct & Community Values

We are committed to maintaining a calm, welcoming, and scientifically rigorous community. Discourse in issues and pull requests should adhere to the same principles we encode in the system:
- **Steel-Manning Opposing Viewpoints:** Seek the strongest, most charitable interpretation of others' arguments.
- **Grounding in Evidence:** Prioritize primary empirical records and accountable sources over viral hearsay.
- **De-escalation:** Minimize emotive friction and ad-hominem rhetoric.

Please review our [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

---

## 📚 Deep-Dive Technical Documentation

Before submitting complex architectural changes, please review our core technical guides:
- [System Architecture & Invariants](docs/ARCHITECTURE.md): Deep-dive into LangGraph state topology, deterministic invariants, quote similarity matching, and lookalike detection.
- [Real-World Use Cases & Recipes](docs/USE_CASES.md): End-to-end integration examples for CLI, FastAPI, MCP servers, and bookmarklets.
- [Source Tiering & Domain Policy](docs/SOURCE_TIERING_POLICY.md): Transparent criteria for categorizing domains into Tiers 1–5 in `config/source_tiers.yaml`.

---

## ⚙️ Architectural Invariants to Uphold

When submitting code to `epistemic-guard`, you MUST uphold these non-negotiable principles:

1. **Zero Hallucination Quantitative Invariants:**
   - All counts (`total_claims`, `verified_shareable_count`, `unconfirmed_blocked_count`, `recycled_content_count`, `average_emotional_arousal`) **must** be computed deterministically in Python. The LLM must never invent, guess, or aggregate counts.
2. **Model Agnostic Inference:**
   - Always route LLM completions through `StructuredLLMClient` (configured via OpenAI-compatible `Settings`) to ensure compatibility with local runtimes (`Ollama`, `vLLM`, `llama.cpp`) and hosted APIs.
3. **Deterministic Domain Tiering:**
   - Domain classification relies strictly on suffix/registered-domain matching from `config/source_tiers.yaml`. Never classify domains via LLM inference.
4. **100% Offline Testing:**
   - Every unit test in `tests/` and benchmark evaluation in `benchmarks/` must execute completely offline without live network dependencies, using `MockSearchProvider` and mocked LLM fixtures.

---

## 🛠️ Development Setup

### 1. Clone & Set Up Virtual Environment

```bash
git clone https://github.com/Sandeep-Hipparagi/epistemic-guard.git
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

### 2. Verify Test Suite & Benchmarks

```bash
# Run full unit test suite (89 offline tests)
pytest -v

# Run reproducible offline benchmark harness (16 cases, ~1.5s runtime)
python benchmarks/evaluate.py
```

---

## 📋 Ways to Contribute

### 1. Propose New Media Domains
To add or adjust domains in `config/source_tiers.yaml`:
- Follow the criteria outlined in [Source Tiering Policy](docs/SOURCE_TIERING_POLICY.md).
- Submit a proposal using the [Source Tier Proposal Template](.github/ISSUE_TEMPLATE/source_tier_proposal.md).
- Ensure `pytest tests/test_domain_auditor.py` passes.

### 2. Contribute Real-World Benchmark Cases
We actively welcome ground-truth cases modeling emerging vectors of viral disinformation, recycled media, or asymmetric discourse:
- Add your scenario to `benchmarks/dataset.jsonl`.
- Use the [Benchmark Case Template](.github/ISSUE_TEMPLATE/benchmark_case.md).
- Validate that `python benchmarks/evaluate.py` maintains $\ge 95\%$ accuracy.

### 3. Report Bugs & Adversarial Bypasses
- For regular bugs, submit via [Bug Report Template](.github/ISSUE_TEMPLATE/bug_report.md).
- For prompt injection, domain bypass, or security vulnerabilities, please consult [SECURITY.md](SECURITY.md) for private disclosure instructions.

---

## 🚀 Submitting a Pull Request

Before opening a PR:
- [ ] Verify all unit tests pass: `pytest -v` (89/89 passing)
- [ ] Verify benchmark evaluation passes: `python benchmarks/evaluate.py` (100% accuracy, $< 3.0\text{s}$)
- [ ] Ensure deterministic invariants are strictly preserved
- [ ] Check code style and formatting: `ruff check` / `ruff format`
- [ ] Fill out the [Pull Request Template](.github/PULL_REQUEST_TEMPLATE.md)
