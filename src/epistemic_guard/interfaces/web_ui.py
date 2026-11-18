from __future__ import annotations

import html
import json
from typing import Optional


def render_web_ui(prefill_claim: Optional[str] = None) -> str:
    """Render the self-contained HTML5/CSS/JS Pre-Share Web Friction Studio."""
    safe_prefill = html.escape(prefill_claim or "")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>🛡️ Epistemic Guard — Pre-Share Friction Studio</title>
  <style>
    :root {{
      --bg: #0f172a;
      --surface: #1e293b;
      --surface-border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --primary-hover: #0284c7;
      --danger: #ef4444;
      --danger-bg: rgba(239, 68, 68, 0.15);
      --warning: #f59e0b;
      --warning-bg: rgba(245, 158, 11, 0.15);
      --success: #10b981;
      --success-bg: rgba(16, 185, 129, 0.15);
      --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      --radius: 12px;
    }}

    @media (prefers-color-scheme: light) {{
      :root {{
        --bg: #f8fafc;
        --surface: #ffffff;
        --surface-border: #e2e8f0;
        --text: #0f172a;
        --text-muted: #64748b;
        --primary: #0284c7;
        --primary-hover: #0369a1;
        --danger-bg: #fee2e2;
        --warning-bg: #fef3c7;
        --success-bg: #d1fae5;
      }}
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 24px;
      min-height: 100vh;
    }}

    .container {{
      max-width: 960px;
      margin: 0 auto;
    }}

    header {{
      text-align: center;
      margin-bottom: 28px;
    }}

    header h1 {{
      font-size: 2rem;
      font-weight: 800;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 10px;
      color: var(--text);
    }}

    header p {{
      color: var(--text-muted);
      font-size: 0.95rem;
      margin-top: 6px;
    }}

    .badge-api {{
      display: inline-block;
      font-size: 0.75rem;
      padding: 2px 8px;
      border-radius: 999px;
      background: var(--success-bg);
      color: var(--success);
      font-weight: 600;
      margin-top: 8px;
    }}

    /* Tabs */
    .tabs {{
      display: flex;
      gap: 8px;
      border-bottom: 1px solid var(--surface-border);
      margin-bottom: 24px;
    }}

    .tab-btn {{
      padding: 10px 18px;
      border: none;
      background: none;
      color: var(--text-muted);
      font-size: 0.95rem;
      font-weight: 600;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      transition: all 0.2s ease;
    }}

    .tab-btn.active {{
      color: var(--primary);
      border-bottom-color: var(--primary);
    }}

    .tab-btn:hover:not(.active) {{
      color: var(--text);
    }}

    .tab-content {{
      display: none;
    }}

    .tab-content.active {{
      display: block;
    }}

    /* Cards & Inputs */
    .card {{
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: var(--radius);
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }}

    label {{
      display: block;
      font-weight: 600;
      margin-bottom: 8px;
      font-size: 0.9rem;
    }}

    textarea, input[type="text"] {{
      width: 100%;
      padding: 12px 14px;
      border-radius: 8px;
      border: 1px solid var(--surface-border);
      background: rgba(0, 0, 0, 0.05);
      color: var(--text);
      font-family: inherit;
      font-size: 0.95rem;
      resize: vertical;
      margin-bottom: 16px;
    }}

    textarea:focus, input:focus {{
      outline: none;
      border-color: var(--primary);
    }}

    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 12px 24px;
      font-size: 0.95rem;
      font-weight: 600;
      border-radius: 8px;
      border: none;
      cursor: pointer;
      background: var(--primary);
      color: #ffffff;
      transition: background 0.15s ease;
    }}

    .btn:hover {{ background: var(--primary-hover); }}
    .btn:disabled {{ opacity: 0.6; cursor: not-allowed; }}

    /* Friction Banners */
    .friction-banner {{
      border-radius: var(--radius);
      padding: 20px;
      margin-bottom: 24px;
      display: flex;
      align-items: flex-start;
      gap: 16px;
      border: 2px solid transparent;
      animation: fadeIn 0.3s ease;
    }}

    .banner-danger {{
      background: var(--danger-bg);
      border-color: var(--danger);
      color: var(--danger);
    }}

    .banner-warning {{
      background: var(--warning-bg);
      border-color: var(--warning);
      color: var(--warning);
    }}

    .banner-success {{
      background: var(--success-bg);
      border-color: var(--success);
      color: var(--success);
    }}

    .banner-title {{
      font-size: 1.25rem;
      font-weight: 800;
      margin-bottom: 6px;
    }}

    .banner-desc {{
      color: var(--text);
      font-size: 0.95rem;
    }}

    /* 3 Provenance Checks */
    .checks-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}

    .check-box {{
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 8px;
      padding: 16px;
    }}

    .check-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
      font-weight: 700;
    }}

    .status-pill {{
      font-size: 0.75rem;
      padding: 2px 8px;
      border-radius: 999px;
      font-weight: 700;
    }}

    .pill-pass {{ background: var(--success-bg); color: var(--success); }}
    .pill-fail {{ background: var(--danger-bg); color: var(--danger); }}
    .pill-warn {{ background: var(--warning-bg); color: var(--warning); }}

    /* Meter */
    .meter-container {{
      margin-top: 14px;
      margin-bottom: 20px;
    }}

    .meter-bar {{
      height: 10px;
      background: #334155;
      border-radius: 999px;
      overflow: hidden;
      margin-top: 6px;
    }}

    .meter-fill {{
      height: 100%;
      transition: width 0.4s ease;
    }}

    /* Badges */
    .tag-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}

    .tag {{
      font-size: 0.8rem;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 6px;
      font-family: var(--font-mono);
    }}

    .tag-danger {{ background: var(--danger-bg); color: var(--danger); }}
    .tag-warning {{ background: var(--warning-bg); color: var(--warning); }}
    .tag-neutral {{ background: rgba(148, 163, 184, 0.2); color: var(--text-muted); }}

    /* Two sided layout */
    .sides-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      margin-top: 20px;
    }}

    @media (max-width: 768px) {{
      .sides-grid {{ grid-template-columns: 1fr; }}
    }}

    /* Bookmarklet */
    .code-box {{
      background: rgba(0, 0, 0, 0.3);
      padding: 14px;
      border-radius: 8px;
      font-family: var(--font-mono);
      font-size: 0.85rem;
      word-break: break-all;
      border: 1px solid var(--surface-border);
      margin: 12px 0;
      color: var(--primary);
    }}

    .spinner {{
      display: inline-block;
      width: 16px;
      height: 16px;
      border: 2px solid rgba(255, 255, 255, 0.3);
      border-radius: 50%;
      border-top-color: #ffffff;
      animation: spin 0.8s linear infinite;
    }}

    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
    @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(-4px); }} to {{ opacity: 1; transform: translateY(0); }} }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>🛡️ Epistemic Guard</h1>
      <p>Model-Agnostic Provenance Auditing & Two-Sided Discourse Analysis</p>
      <span class="badge-api">● REST API v0.2.0 ACTIVE</span>
    </header>

    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab('single')">Single-Claim Quick Check</button>
      <button class="tab-btn" onclick="switchTab('twosided')">Two-Sided Listening Studio</button>
      <button class="tab-btn" onclick="switchTab('bookmarklet')">Browser Bookmarklet</button>
    </div>

    <!-- TAB 1: Single Claim Quick Check -->
    <div id="tab-single" class="tab-content active">
      <div class="card">
        <label for="singleInput">Discourse Input (Tweet, viral quote, claim text, or article URL):</label>
        <textarea id="singleInput" rows="3" placeholder="Example: Official Envoy announces: 'The bilateral trade accord has been ratified.' https://www.reuters.com/markets/trade-accord-2026">{safe_prefill}</textarea>
        <button id="singleBtn" class="btn" onclick="runSingleAudit()">
          <span>Audit Provenance & Verify</span>
        </button>
      </div>

      <div id="singleResults" style="display:none;"></div>
    </div>

    <!-- TAB 2: Two-Sided Listening Studio -->
    <div id="tab-twosided" class="tab-content">
      <div class="card">
        <div class="sides-grid" style="margin-top:0; margin-bottom:16px;">
          <div>
            <label for="sideAInput">Perspective A (Affirmative / Official Wire / Side A):</label>
            <textarea id="sideAInput" rows="4" placeholder="Enter Side A statement with source link..."></textarea>
          </div>
          <div>
            <label for="sideBInput">Perspective B (Opposition / Counterclaim / Side B):</label>
            <textarea id="sideBInput" rows="4" placeholder="Enter Side B statement with source link..."></textarea>
          </div>
        </div>
        <button id="twoSidedBtn" class="btn" onclick="runTwoSidedAudit()">
          <span>Analyze Both Perspectives</span>
        </button>
      </div>

      <div id="twoSidedResults" style="display:none;"></div>
    </div>

    <!-- TAB 3: Browser Bookmarklet -->
    <div id="tab-bookmarklet" class="tab-content">
      <div class="card">
        <h3 style="margin-bottom:8px;">Instant 1-Click Browser Pre-Share Bookmarklet</h3>
        <p style="color:var(--text-muted); font-size:0.95rem; margin-bottom:14px;">
          Highlight any viral tweet, unverified quote, or controversial paragraph on any website (X/Twitter, Reddit, news feeds) and click this bookmarklet to open the Epistemic Guard Friction Studio pre-filled and ready to audit.
        </p>

        <p><strong>Option 1: Drag to Bookmarks Bar</strong></p>
        <div style="margin: 12px 0;">
          <a class="btn" href="javascript:(function(){{var q=window.getSelection().toString().trim();if(!q){{q=prompt('Enter claim or quote to audit:');}}if(q){{var u='http://localhost:8000/?claim='+encodeURIComponent(q);window.open(u,'_blank');}}}})();" onclick="alert('Drag this button to your browser Bookmarks Bar!'); return false;">
            <span>🛡️ Epistemic Audit</span>
          </a>
        </div>

        <p style="margin-top:20px;"><strong>Option 2: Copy Code Snippet</strong></p>
        <div class="code-box" id="bmCode">javascript:(function(){{var q=window.getSelection().toString().trim();if(!q){{q=prompt('Enter claim or quote to audit:');}}if(q){{var u='http://localhost:8000/?claim='+encodeURIComponent(q);window.open(u,'_blank');}}}})();</div>
        <button class="btn" style="padding: 8px 16px; font-size: 0.85rem;" onclick="navigator.clipboard.writeText(document.getElementById('bmCode').innerText); alert('Bookmarklet code copied to clipboard!');">Copy Code</button>
      </div>
    </div>
  </div>

  <script>
    function switchTab(name) {{
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      if (name === 'single') {{
        document.querySelectorAll('.tab-btn')[0].classList.add('active');
        document.getElementById('tab-single').classList.add('active');
      }} else if (name === 'twosided') {{
        document.querySelectorAll('.tab-btn')[1].classList.add('active');
        document.getElementById('tab-twosided').classList.add('active');
      }} else {{
        document.querySelectorAll('.tab-btn')[2].classList.add('active');
        document.getElementById('tab-bookmarklet').classList.add('active');
      }}
    }}

    async function runSingleAudit() {{
      const text = document.getElementById('singleInput').value.trim();
      if (!text) {{ alert('Please enter claim or quote text to audit.'); return; }}

      const btn = document.getElementById('singleBtn');
      const resultsDiv = document.getElementById('singleResults');
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span> <span>Investigating Provenance...</span>';
      resultsDiv.style.display = 'none';

      try {{
        const resp = await fetch('/v1/analyze', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ texts: [text] }})
        }});

        if (!resp.ok) throw new Error('API returned error ' + resp.status);
        const report = await resp.json();
        renderSingleResults(report);
      }} catch (err) {{
        alert('Failed to audit claim: ' + err.message);
      }} finally {{
        btn.disabled = false;
        btn.innerHTML = '<span>Audit Provenance & Verify</span>';
      }}
    }}

    function renderSingleResults(report) {{
      const div = document.getElementById('singleResults');
      const audited = (report.audited_claims && report.audited_claims.length > 0) ? report.audited_claims[0] : null;
      if (!audited) {{ div.innerHTML = '<p>No claims extracted.</p>'; div.style.display = 'block'; return; }}

      const audit = audited.audit;
      const claim = audited.claim;
      const isSafe = audit.is_shareable;
      const isSatire = audit.verdict === 'SATIRE_PARODY_ALERT';

      let bannerClass = 'banner-danger';
      let bannerIcon = '🚨';
      let bannerTitle = 'DO NOT SHARE — UNCONFIRMED PROVENANCE';

      if (isSatire) {{
        bannerClass = 'banner-warning';
        bannerIcon = '⚠️';
        bannerTitle = 'SATIRE / PARODY ALERT — NOT REAL NEWS';
      }} else if (isSafe) {{
        bannerClass = 'banner-success';
        bannerIcon = '✅';
        bannerTitle = 'PROVENANCE CONFIRMED — SAFE TO REFERENCE';
      }}

      // Arousal percent & color
      const arousal = (claim.emotional_framing ? claim.emotional_framing.arousal_score : 0.5) * 100;
      let meterColor = '#10b981';
      if (arousal >= 75) meterColor = '#ef4444';
      else if (arousal >= 50) meterColor = '#f59e0b';

      // Checkboxes status
      const wherePass = audit.where && audit.where.is_identified;
      const whenPass = audit.when && (audit.when.is_exact_timestamp || (audit.when.date_str && !audit.when.is_recycled_media_risk));
      const evPass = audit.evidence && (audit.evidence.has_primary_media || audit.evidence.has_named_outlet);

      let flagsHtml = '';
      (audit.warning_flags || []).forEach(f => {{
        flagsHtml += `<span class="tag tag-danger">${{f}}</span>`;
      }});
      if (claim.emotional_framing && claim.emotional_framing.manipulation_cues) {{
        claim.emotional_framing.manipulation_cues.forEach(c => {{
          flagsHtml += `<span class="tag tag-warning">${{c}}</span>`;
        }});
      }}

      div.innerHTML = `
        <div class="friction-banner ${{bannerClass}}">
          <div style="font-size:2rem;">${{bannerIcon}}</div>
          <div>
            <div class="banner-title">${{bannerTitle}}</div>
            <div class="banner-desc">${{audit.recommendation}}</div>
          </div>
        </div>

        <div class="card">
          <h3 style="margin-bottom:14px;">The 3 Strict Provenance Questions</h3>
          <div class="checks-grid">
            <div class="check-box">
              <div class="check-header">
                <span>1. WHERE was it said?</span>
                <span class="status-pill ${{wherePass ? 'pill-pass' : 'pill-fail'}}">${{wherePass ? 'VERIFIED' : 'UNCONFIRMED'}}</span>
              </div>
              <p style="font-size:0.85rem; color:var(--text-muted);">${{audit.where.venue_or_platform || 'Missing venue/root platform'}}</p>
            </div>
            <div class="check-box">
              <div class="check-header">
                <span>2. WHEN was it said?</span>
                <span class="status-pill ${{whenPass ? 'pill-pass' : 'pill-fail'}}">${{whenPass ? 'CONTEMPORARY' : 'RECYCLED RISK'}}</span>
              </div>
              <p style="font-size:0.85rem; color:var(--text-muted);">${{audit.when.date_str || audit.when.temporal_notes || 'Timestamp unconfirmed'}}</p>
            </div>
            <div class="check-box">
              <div class="check-header">
                <span>3. PRIMARY MEDIA / OUTLET?</span>
                <span class="status-pill ${{evPass ? 'pill-pass' : 'pill-fail'}}">${{evPass ? 'ACCOUNTABLE' : 'UNVERIFIED'}}</span>
              </div>
              <p style="font-size:0.85rem; color:var(--text-muted);">${{audit.evidence.outlet_name || audit.evidence.evidence_type || 'No named outlet or video'}}</p>
            </div>
          </div>

          <div class="meter-container">
            <div style="display:flex; justify-content:space-between; font-size:0.85rem; font-weight:600;">
              <span>Emotional Contagion & Arousal</span>
              <span>${{arousal.toFixed(0)}}% (${{claim.emotional_framing.primary_emotion || 'neutral'}})</span>
            </div>
            <div class="meter-bar">
              <div class="meter-fill" style="width:${{arousal}}%; background:${{meterColor}};"></div>
            </div>
          </div>

          ${{flagsHtml ? `<div><strong>Warning Indicators & Signals:</strong><div class="tag-list">${{flagsHtml}}</div></div>` : ''}}
        </div>
      `;
      div.style.display = 'block';
    }}

    async function runTwoSidedAudit() {{
      const a = document.getElementById('sideAInput').value.trim();
      const b = document.getElementById('sideBInput').value.trim();
      if (!a || !b) {{ alert('Please enter text for both Perspective A and Perspective B.'); return; }}

      const btn = document.getElementById('twoSidedBtn');
      const resultsDiv = document.getElementById('twoSidedResults');
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span> <span>Synthesizing Perspectives...</span>';
      resultsDiv.style.display = 'none';

      try {{
        const resp = await fetch('/v1/analyze', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ texts: [a, b] }})
        }});

        if (!resp.ok) throw new Error('API returned error ' + resp.status);
        const report = await resp.json();
        renderTwoSidedResults(report);
      }} catch (err) {{
        alert('Failed to analyze perspectives: ' + err.message);
      }} finally {{
        btn.disabled = false;
        btn.innerHTML = '<span>Analyze Both Perspectives</span>';
      }}
    }}

    function renderTwoSidedResults(report) {{
      const div = document.getElementById('twoSidedResults');
      const isAsymmetric = report.provenance_asymmetry_detected;

      let asymHtml = '';
      if (isAsymmetric) {{
        asymHtml = `
          <div class="friction-banner banner-warning">
            <div style="font-size:2rem;">⚖️</div>
            <div>
              <div class="banner-title">PROVENANCE ASYMMETRY DETECTED</div>
              <div class="banner-desc">One perspective is corroborated by accountable primary or wire sources, while the opposing narrative relies exclusively on unverified social media viral claims.</div>
            </div>
          </div>
        `;
      }}

      let perspHtml = '';
      (report.perspectives || []).forEach(p => {{
        perspHtml += `
          <div class="card" style="margin-bottom:0;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
              <h3 style="color:var(--primary);">${{p.side_label}}</h3>
              <span class="status-pill ${{p.verified_shareable_count > 0 ? 'pill-pass' : 'pill-fail'}}">
                ${{p.verified_shareable_count}} Verified / ${{p.unconfirmed_blocked_count}} Blocked
              </span>
            </div>
            <p style="font-size:0.95rem; margin-bottom:12px;"><strong>Steel-Manned Summary:</strong> ${{p.steel_manned_summary}}</p>
            <div style="font-size:0.85rem; color:var(--text-muted);">
              Avg Arousal: <strong>${{(p.average_emotional_arousal * 100).toFixed(0)}}%</strong> | Recycled Media: <strong>${{p.recycled_content_count}}</strong>
            </div>
          </div>
        `;
      }});

      div.innerHTML = `
        ${{asymHtml}}
        <div class="sides-grid" style="margin-bottom:24px;">
          ${{perspHtml}}
        </div>
        <div class="card">
          <h3>De-Escalation Guidance & Synthesis</h3>
          <p style="margin-top:8px; font-size:0.95rem;">${{report.deescalation_guidance || 'Verify claims against primary documentation before sharing.'}}</p>
        </div>
      `;
      div.style.display = 'block';
    }}

    // Auto-prefill claim if query param ?claim= is present
    window.addEventListener('DOMContentLoaded', () => {{
      const params = new URLSearchParams(window.location.search);
      const c = params.get('claim');
      if (c && c.trim()) {{
        document.getElementById('singleInput').value = c.trim();
        runSingleAudit();
      }}
    }});
  </script>
</body>
</html>
"""
