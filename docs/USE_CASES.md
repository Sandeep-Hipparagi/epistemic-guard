# Integration Recipes & Real-World Use Cases

This document provides concrete, end-to-end integration walkthroughs and recipes for integrating `epistemic-guard` into editorial pipelines, autonomous AI agents, social media moderation systems, and user browsers.

---

## Use Case 1: Catching Fake Attributed Outrage Quotes

### The Threat
A viral social media post attributes an inflammatory fabricated quote to a prominent corporate executive or political official to trigger market panic or public outrage:
> *"Tech Titan CEO announces immediate shutdown of European operations: 'We cannot comply with unreasonable regulatory directives.' https://x.com/tech_insider/status/987654"*

### Execution via CLI
```bash
epistemic-guard analyze "Tech Titan CEO announces immediate shutdown of European operations: 'We cannot comply with unreasonable regulatory directives.' https://x.com/tech_insider/status/987654"
```

### Engine Behavior
1. **Extraction:** Identifies `speaker = "Tech Titan CEO"` and `verbatim_quote = "We cannot comply with unreasonable regulatory directives."`.
2. **Provenance Audit:** Queries news wires and search index for the quote and speaker.
3. **Outcome:**
   - No Tier 1 wire services (Reuters, AP) or Tier 2 editorial publications report any such quote.
   - The cited URL is a Tier 4 unverified UGC post (`x.com`).
   - The quote matcher finds no matching transcript snippets.
4. **Deterministic Verdict:**
   - `verdict = "DO_NOT_SHARE_UNCONFIRMED"`
   - `is_shareable = false`
   - `warning_flags = ["NO_PRIMARY_MEDIA_OR_NAMED_OUTLET", "UNVERIFIED_UGC_SOLE_SOURCE"]`

---

## Use Case 2: Flagging Recycled Historical Footage

### The Threat
During an extreme weather warning, an account reshares dramatic footage from a 2021 winter storm blackout, claiming it is happening live:
> *"Disaster strikes right now! Complete regional power grid failure plunging millions into freezing dark! https://tiktok.com/@weather_watcher/video/404"*

### Execution via Python API
```python
from epistemic_guard.graph.workflow import EpistemicGuardPipeline
from datetime import datetime, timezone

pipeline = EpistemicGuardPipeline()
report = pipeline.analyze([
    "Disaster strikes right now! Complete regional power grid failure plunging millions into freezing dark! https://tiktok.com/@weather_watcher/video/404"
])

claim_audit = report.perspectives[0].claims[0].audit
print(f"Verdict: {claim_audit.verdict.value}")
print(f"Is Shareable: {claim_audit.is_shareable}")
print(f"When Recycled: {claim_audit.when.is_recycled}")
print(f"Original Date: {claim_audit.when.earliest_source_date}")
print(f"Warning Flags: {claim_audit.warning_flags}")
```

### Resulting Output
```json
{
  "verdict": "DO_NOT_SHARE_UNCONFIRMED",
  "is_shareable": false,
  "when": {
    "is_recycled": true,
    "days_drift": 1825,
    "earliest_source_date": "2021-02-16"
  },
  "warning_flags": [
    "TEMPORAL_DRIFT_RECYCLED_CONTENT",
    "UNVERIFIED_UGC_SOLE_SOURCE"
  ]
}
```
The engine exposes that the media is over 1,800 days old, arresting viral contagion before panic spreads.

---

## Use Case 3: Exposing Asymmetric Two-Sided Debates

### The Threat
A heated public debate emerges regarding a newly signed bilateral accord. One faction cites official treaty documentation and Tier 1 wire reports, while an opposing faction mobilizes emotional outrage based on rumors from unverified accounts.

### Execution via FastAPI
```bash
curl -X POST http://localhost:8000/v1/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "texts": [
      "Official Envoy: Trade accord ratified with tariff cuts across 14 sectors https://www.reuters.com/markets/trade-accord-2026",
      "OUTRAGE! Secret surrender leaked by anonymous patriot on Telegram! We gave away all sovereign rights! https://t.me/patriot_leaks/889"
    ]
  }'
```

### Output Synthesis
The response exposes the **epistemic asymmetry** without editorial bias:
```json
{
  "topic": "Bilateral Trade Accord Ratification",
  "provenance_asymmetry_detected": true,
  "asymmetry_rationale": "Side A is corroborated by Tier 1 wire services (Reuters), while Side B relies exclusively on unverified Tier 4 social media posts lacking documentary or primary media backing.",
  "perspectives": [
    {
      "side_label": "Side A",
      "total_claims": 1,
      "verified_shareable_count": 1,
      "unconfirmed_blocked_count": 0,
      "average_emotional_arousal": 0.22,
      "steelmanned_summary": "Proponents emphasize the formal economic provisions of the ratified accord, pointing to official tariff reductions across designated industrial sectors."
    },
    {
      "side_label": "Side B",
      "total_claims": 1,
      "verified_shareable_count": 0,
      "unconfirmed_blocked_count": 1,
      "average_emotional_arousal": 0.91,
      "steelmanned_summary": "Critics raise fears regarding loss of sovereignty and confidential concessions, though currently without primary documentation."
    }
  ],
  "deescalation_guidance": "Notice that primary evidence exists for the ratified terms, while allegations of secret concessions have not been corroborated by independent media or legal filings. Pause before sharing unverified leaks."
}
```

---

## Use Case 4: MCP Server for Autonomous AI Agents

AI research and coding agents frequently scrape or search the web and risk citing hallucinated or unreliable blog posts. Integrating `epistemic-guard` via the **Model Context Protocol (MCP)** gives any agent a deterministic fact-checking pre-flight check.

### Claude Desktop Configuration
Add to `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "epistemic-guard": {
      "command": "epistemic-guard-mcp",
      "env": {
        "LLM_BASE_URL": "http://localhost:11434/v1",
        "LLM_API_KEY": "ollama",
        "LLM_MODEL_NAME": "qwen2.5:7b"
      }
    }
  }
}
```

### Cursor & OpenCode Agent Configuration
Add to `.cursor/mcp.json` or agent settings:
```json
{
  "mcpServers": {
    "epistemic-guard": {
      "command": "python",
      "args": ["-m", "epistemic_guard.interfaces.mcp_server"]
    }
  }
}
```

### Agent Tool Usage Example
When the agent encounters a claim:
```python
# Tool: check_viral_claim
{
  "claim_text": "Federal Reserve unexpected 100bps rate hike announced on https://reuters-breaking-alert.com"
}
```

**MCP Tool Response to Agent:**
```json
{
  "verdict": "DO_NOT_SHARE_UNCONFIRMED",
  "is_shareable": false,
  "where": {
    "root_domain": "reuters-breaking-alert.com",
    "tier": "TIER_4_USER_GENERATED",
    "warning_flags": ["LOOKALIKE_DOMAIN_IMPERSONATION"]
  },
  "explanation": "Blocked: Domain 'reuters-breaking-alert.com' is an impersonation attempt targeting Reuters. No primary media or accountable outlet corroborates this claim."
}
```
The agent automatically aborts the citation and informs the user of the deceptive domain.

---

## Use Case 5: 1-Click Pre-Share Friction Bookmarklet

For journalists, fact-checkers, and everyday readers browsing social media:

1. Start the service:
   ```bash
   uvicorn epistemic_guard.interfaces.api:app --host 0.0.0.0 --port 8000
   ```
2. Navigate to `http://localhost:8000` in your web browser.
3. Drag the **🛡️ Epistemic Guard** bookmarklet to your bookmarks bar.
4. When browsing any breaking news story, highlight suspicious text and click the bookmarklet.
5. The Pre-Share Studio opens instantly, displaying the 3 Provenance Checkboxes (*Where*, *When*, *Evidence*) and an emotional arousal warning before you hit Retweet or Share.
