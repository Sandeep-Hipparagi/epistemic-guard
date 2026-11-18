# Security Policy

The `epistemic-guard` maintainers take the integrity and security of our provenance auditing and two-sided listening engine seriously. As an epistemic security tool defending against viral disinformation, adversarial manipulation of the engine is considered a security issue.

---

## Supported Versions

| Version | Supported |
| :--- | :---: |
| 0.2.x | :white_check_mark: |
| < 0.2.0 | :x: |

---

## In-Scope Security Vulnerabilities

We actively encourage responsible disclosure of:
1. **Adversarial Domain Bypass:** Heuristics or homograph attacks that fool `detect_lookalike_domain` or `DomainAuditor` into assigning Tier 1 or Tier 2 status to deceptive or malicious domains.
2. **Prompt Injection / Jailbreaks:** Crafted discourse text or quotes that hijack `ClaimExtractor` or `StructuredLLMClient` into hallucinating corroborating evidence or overriding deterministic invariants (`is_shareable = False`).
3. **Circular Reporting Exploits:** Retrieval techniques that trick `ProvenanceInvestigator` into treating coordinated social media bot networks or syndicated unverified blogs as independent Tier 1/2 corroboration.
4. **Denial of Service (DoS):** ReDoS (regular expression denial of service) in date/domain parsers, or runaway recursive loops in the state graph.

---

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, report vulnerabilities via:
- **GitHub Private Vulnerability Reporting:** Navigate to the **Security** tab of [https://github.com/Sandeep-Hipparagi/epistemic-guard/security](https://github.com/Sandeep-Hipparagi/epistemic-guard/security) and click **"Report a vulnerability"**.
- **Email:** If you cannot use GitHub Security Advisories, contact the lead maintainer directly at `security@epistemicguard.org`.

### What to Include
- Detailed description of the vulnerability and attack vector.
- Minimal reproducible example (discourse input string, URL, or mock payload).
- Analysis of potential impact (e.g. bypassing `DO_NOT_SHARE_UNCONFIRMED` or corrupting synthesis metrics).

### Response Timeline
- **Initial Acknowledgement:** Within 48 hours.
- **Triage & Reproduction:** Within 5 business days.
- **Fix & Advisory Release:** We will coordinate a patched release and publish a CVE / GitHub Security Advisory crediting the finder.
