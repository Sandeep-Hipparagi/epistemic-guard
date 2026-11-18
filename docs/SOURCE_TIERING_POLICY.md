# Source Tiering & Domain Governance Policy

This policy document governs how media organizations, research repositories, institutional portals, and platforms are categorized into deterministic accountability tiers within `config/source_tiers.yaml`.

---

## 1. Guiding Principles

`epistemic-guard` **does not evaluate political ideology, editorial slant, or subjective opinions**. 

Instead, the source tiering model evaluates a single structural question:
> **Is the publisher legally accountable for errors, bound by published corrections policies, and subject to pre-publication editorial review?**

Viral outrage thrives when anonymous, unverified social media claims are treated on equal epistemic footing with named, verified on-the-record journalism. Source tiering mathematically restores this distinction.

---

## 2. Source Tier Definitions

| Tier | Identifier | Trust Level | Description & Admission Criteria | Default Engine Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | `TIER_1_PRIMARY` | `HIGH` | **Primary Records & Global Wires:** Direct wire services (Reuters, AP), primary academic journals (`Nature`, `Science`), official government/judicial registries (`.gov`, `.mil`), supranational bodies (UN, WHO), and certified IFCN fact-checkers. | Eligible for standalone **`VERIFIED_PRIMARY`** status. |
| **Tier 2** | `TIER_2_ESTABLISHED_EDITORIAL` | `MEDIUM_HIGH` | **Accountable Newsrooms:** Major international/national newsrooms with transparent mastheads, named reporter bylines, documented institutional corrections policies, and legal accountability (e.g. NYT, BBC, WSJ, The Guardian). | Eligible for **`CORROBORATED_SECONDARY`** status. |
| **Tier 3** | `TIER_3_SECONDARY_ANALYSIS` | `MEDIUM` | **Specialized & Trade Press:** Industry trade publications, tech journalism, regional press, analytical newsletters, and commentary platforms (e.g. Wired, Axios, TechCrunch, Substack). | Informs context but requires secondary corroboration for hard factual claims. |
| **Tier 4** | `TIER_4_USER_GENERATED` | `LOW_UNVERIFIED` | **User-Generated Content & Social Media:** Open platforms where any individual can publish anonymously without pre-publication editorial review (X/Twitter, TikTok, Reddit, Telegram, YouTube). Also includes lookalike domains. | **`DO_NOT_SHARE_UNCONFIRMED`** if sole source. Citing multiple Tier 4 sources cannot escalate verification. |
| **Tier 5** | `TIER_5_SATIRE_PARODY` | `SATIRE` | **Satire & Humor:** Recognized satire publications (The Onion, Babylon Bee) whose fictional articles are frequently misconstrued by automated scrapers or viral posts. | Generates **`SATIRE_PARODY_ALERT`**; strictly blocked from news sharing. |
| **Unknown** | `TIER_UNKNOWN` | `UNKNOWN` | **Unregistered / New Domains:** Any domain not explicitly present in `config/source_tiers.yaml`. | Treated conservatively as unconfirmed pending primary wire corroboration. |

---

## 3. Top-Level Domain (TLD) Invariants

`epistemic-guard` applies deterministic TLD-level classification:
- `.gov` (US & Sovereign Government Portals) $\to$ **`TIER_1_PRIMARY`**
- `.mil` (Military Authorities) $\to$ **`TIER_1_PRIMARY`**
- `.edu` (Accredited Higher Education & Research) $\to$ **`TIER_1_PRIMARY`**

---

## 4. Adversarial Lookalike & Typosquatting Defense

Attackers often register typosquatted domains imitating reputable newsrooms (e.g., `reuters-breaking.com`, `bbc-news-alert.co`, `nytimes-live.org`) to bypass automated filters.

### Defense Mechanism
The engine runs `detect_lookalike_domain` before evaluating any registered domain:
1. Compares domain tokens against 22+ protected Tier 1/2 brands (`reuters`, `apnews`, `bbc`, `nytimes`, `wsj`, `cnn`, `c-span`, etc.).
2. Detects deceptive hyphenation, appended modifier keywords (`breaking`, `news`, `alert`, `wire`, `live`), and homograph tricks.
3. Automatically overrides any lookalike domain into **Tier 4 (UGC / Unverified)** with the audit flag:
   ```json
   "warning_flags": ["LOOKALIKE_DOMAIN_IMPERSONATION"]
   ```
4. Immediately revokes `is_shareable` and flags the claim as `DO_NOT_SHARE_UNCONFIRMED`.

---

## 5. Community Domain Proposal Workflow

We welcome community pull requests to expand domain coverage in `config/source_tiers.yaml`. To preserve deterministic integrity, all proposals must follow these guidelines:

### Proposal Criteria

#### For Tier 1 Primary:
- **Wire Services:** Must supply syndicated reporting to multiple external media clients and operate a formal bureau network.
- **Scientific Registries:** Must be an established open-access preprint server or peer-reviewed academic publisher indexed in PubMed/Scopus.
- **Fact-Checking Organizations:** Must be an active signatory of the International Fact-Checking Network (IFCN) Code of Principles.

#### For Tier 2 Established Editorial:
- Must have a publicly accessible masthead listing senior editors and journalists.
- Must maintain a clear, published **Corrections Policy** detailing how retractions and corrections are issued.
- Must have an established operating history ($\ge 3$ years) of investigative reporting with bylines.

#### For Tier 5 Satire:
- Must include a clear public disclaimer or widespread public consensus identifying the publication as parody or satire.

---

### Step-by-Step Pull Request Process

1. Use the **[Source Tier Proposal Template](https://github.com/Sandeep-Hipparagi/epistemic-guard/issues/new?template=source_tier_proposal.md)** to open an issue or PR.
2. Provide the apex registered domain (e.g., `example.com`).
3. Link to:
   - The publisher's Corrections Policy.
   - The official masthead.
   - IFCN certificate or indexing documentation (if proposing Tier 1).
4. Run the test suite to ensure no classification regressions:
   ```bash
   pytest tests/test_domain_auditor.py
   python benchmarks/evaluate.py
   ```
5. Maintainers will review the submission within 3–5 business days.
