"""
manual_checklist.py
Generates one browser-ready HTML checklist PER PROFILE for blocked brokers.

Features:
  - Checkbox + opt-out date (auto-fills today, follow-up flag at 35 days)
  - Notes textarea for follow-up actions (BBB complaint, call logs, etc.)
  - Phone number button for brokers that have one
  - Progress bar and counter
  - State persists in localStorage immediately
  - "Save Progress" button exports a JSON file the user drops into outputs/
  - Next scan auto-imports that JSON and pre-populates the new checklist
  - Pre-populated values come from checklist_state.py (SQLite)

File naming: manual_checklist_<profile_id>_<YYYYMMDD_HHMMSS>.html
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from reporter.checklist_state import ChecklistStateStore

log = logging.getLogger(__name__)

# ── HTML shell ────────────────────────────────────────────────────────────────

CHECKLIST_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Privacy Guardian — Manual Checklist — {label} — {date}</title>
<style>
  body  {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #f4f6f9; color: #2c3e50; margin: 0; padding: 2rem; }}
  h1    {{ color: #2c3e50; border-bottom: 3px solid #e67e22; padding-bottom: .5rem; }}
  .intro {{ background: #fef9e7; border-left: 4px solid #f39c12; padding: 1rem 1.2rem;
            border-radius: 0 6px 6px 0; margin-bottom: 1.5rem; font-size: .92rem; }}
  .toolbar {{ display:flex; gap:.8rem; align-items:center; margin-bottom:1.2rem; flex-wrap:wrap; }}
  .save-btn {{ background:#2c3e50; color:white; border:none; padding:.45rem 1.1rem;
               border-radius:4px; cursor:pointer; font-size:.88rem; font-weight:bold; }}
  .save-btn:hover {{ background:#34495e; }}
  .save-hint {{ font-size:.78rem; color:#7f8c8d; }}
  .profile-block {{ background: white; border-radius: 8px; padding: 1.5rem;
                    margin-bottom: 2rem; box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
  .stats  {{ font-size: .85rem; color: #7f8c8d; margin-bottom: .4rem; }}
  .counter {{ font-size: .85rem; color: #27ae60; font-weight: bold; margin-bottom: .8rem; }}
  .progress {{ height: 8px; background: #ecf0f1; border-radius: 4px; margin-bottom: .8rem; }}
  .progress-bar {{ height: 100%; background: #27ae60; border-radius: 4px; transition: width .3s; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .86rem; }}
  th    {{ background: #e67e22; color: white; padding: .6rem .7rem; text-align: left;
           white-space: nowrap; }}
  td    {{ padding: .55rem .7rem; border-bottom: 1px solid #ecf0f1; vertical-align: top; }}
  tr.done td {{ background: #eafaf1; }}
  tr.done td.broker-name {{ text-decoration: line-through; color: #95a5a6; }}
  tr:hover:not(.done) td {{ background: #fdfefe; }}
  input[type=checkbox] {{ width: 18px; height: 18px; cursor: pointer;
                           accent-color: #27ae60; vertical-align: middle; }}
  .date-cell {{ white-space: nowrap; min-width: 160px; }}
  input[type=date] {{ font-size: .82rem; border: 1px solid #bdc3c7; border-radius: 4px;
                      padding: .2rem .4rem; color: #2c3e50; background: white; cursor: pointer; }}
  input[type=date]:disabled {{ background: #ecf0f1; color: #95a5a6; cursor: default; }}
  .date-label {{ font-size: .73rem; color: #7f8c8d; display: block; margin-top: 2px; }}
  .followup-flag {{ font-size: .73rem; font-weight: bold; display: inline-block; margin-top: 2px; }}
  .notes-cell {{ min-width: 200px; }}
  textarea.notes-input {{
    width: 100%; min-height: 52px; font-size: .8rem; border: 1px solid #bdc3c7;
    border-radius: 4px; padding: .3rem .4rem; resize: vertical; color: #2c3e50;
    background: white; font-family: inherit; box-sizing: border-box;
  }}
  textarea.notes-input:disabled {{ background: #f4f6f9; color: #95a5a6; cursor: default; }}
  textarea.notes-input::placeholder {{ color: #bdc3c7; font-style: italic; }}
  .btn {{ display: inline-block; padding: .32rem .75rem; border-radius: 4px; color: white;
          text-decoration: none; font-size: .78rem; font-weight: bold; white-space: nowrap; }}
  .btn-search {{ background: #2980b9; }}
  .btn-optout {{ background: #27ae60; margin-left: .3rem; }}
  .btn-phone  {{ background: #8e44ad; margin-top: .3rem; display: inline-block; }}
  .badge {{ font-size: .71rem; padding: .18rem .42rem; border-radius: 3px;
            color: white; margin-left: .3rem; vertical-align: middle; }}
  .badge-blocked  {{ background: #e67e22; }}
  .badge-error    {{ background: #95a5a6; }}
  .badge-nooptout {{ background: #c0392b; }}
  .legal {{ font-size: .74rem; color: #7f8c8d; }}
  .legend {{ font-size: .8rem; background: #ecf0f1; border-radius: 6px;
             padding: .6rem 1rem; margin-bottom: 1.2rem; }}
  footer {{ margin-top: 3rem; font-size: .78rem; color: #95a5a6; }}
  @media print {{
    .btn, input[type=date], textarea.notes-input, .save-btn, .toolbar {{ display: none; }}
    input[type=checkbox] {{ display: none; }}
  }}
</style>
</head>
<body>

<h1>🖥️ Privacy Guardian — Manual Browser Checklist</h1>
<p>
  <strong>For:</strong> {label} &nbsp;|&nbsp;
  <strong>Generated:</strong> {date}
</p>

<div class="intro">
  <strong>How to use this checklist:</strong><br>
  Click <strong>Search</strong> to find your listing, then <strong>Opt-out</strong>
  to request removal. If the form fails, use the <strong>📞 phone</strong> button
  to call directly. Check the box when done and set the date. Use the
  <strong>Notes</strong> column to log follow-up actions — BBB complaints, call
  reference numbers, escalation steps, etc.<br><br>
  The follow-up reminder fires 35 days after the opt-out date.<br><br>
  <strong>💾 Save Progress</strong> exports your notes and dates to a file. Drop that
  file into your <code>outputs/</code> folder — the next weekly scan will
  automatically carry your notes forward into the new checklist.
</div>

<div class="toolbar">
  <button class="save-btn" onclick="exportState()">💾 Save Progress</button>
  <span class="save-hint">
    Drop the downloaded file into <code>outputs/</code> to carry notes to the next scan.
  </span>
</div>

<div class="legend">
  <span><span class="badge badge-blocked">BLOCKED</span> Must visit manually</span>
  <span><span class="badge badge-error">UNREACHABLE</span> Connection failed</span>
  <span><span class="badge badge-nooptout">NO OPT-OUT</span> Refer to attorney</span>
</div>

{body}

<footer>
  privacy-guardian &middot; This checklist is intended solely for {label}. &middot; {date}<br>
  Legal advisories are informational — consult a licensed attorney for case-specific guidance.
</footer>

<script>
const PROFILE_ID  = '{profile_id}';
const STORAGE_KEY = 'pg_checklist_{profile_id}_{datestamp}';
const FOLLOWUP_DAYS = 35;

// Pre-populated state from previous runs (injected by Python at build time)
const PRELOADED = {preloaded_json};

// ── Persistence ───────────────────────────────────────────────────────────────
function collectState() {{
  const state = {{}};
  document.querySelectorAll('tr[data-row-id]').forEach(row => {{
    const id  = row.dataset.rowId;
    const cb  = row.querySelector('input[type=checkbox]');
    const dt  = row.querySelector('input[type=date]');
    const ta  = row.querySelector('textarea.notes-input');
    const bname = row.dataset.brokerName;
    state[id] = {{
      broker_name:    bname  || id,
      optout_done:    cb     ? cb.checked  : false,
      optout_date:    dt     ? dt.value    : '',
      followup_notes: ta     ? ta.value    : '',
    }};
  }});
  return state;
}}

function saveState() {{
  try {{ localStorage.setItem(STORAGE_KEY, JSON.stringify(collectState())); }} catch(e) {{}}
}}

function loadState() {{
  // Merge: PRELOADED (from DB) then localStorage (most recent browser session)
  const merged = Object.assign({{}}, PRELOADED);
  let raw;
  try {{ raw = localStorage.getItem(STORAGE_KEY); }} catch(e) {{}}
  if (raw) {{
    try {{ Object.assign(merged, JSON.parse(raw)); }} catch(e) {{}}
  }}

  Object.entries(merged).forEach(([id, val]) => {{
    const row = document.querySelector('tr[data-row-id="' + id + '"]');
    if (!row) return;
    const cb = row.querySelector('input[type=checkbox]');
    const dt = row.querySelector('input[type=date]');
    const ta = row.querySelector('textarea.notes-input');
    if (cb && val.optout_done)    {{ cb.checked = true; }}
    if (dt && val.optout_date)    {{ dt.value   = val.optout_date; }}
    if (ta && val.followup_notes) {{ ta.value   = val.followup_notes; }}
    applyRowState(row);
  }});
  updateCounter();
}}

// ── Export (Save Progress button) ─────────────────────────────────────────────
function exportState() {{
  const state = collectState();
  // Convert to broker_name-keyed dict for import by Python
  const byBroker = {{}};
  Object.values(state).forEach(v => {{
    byBroker[v.broker_name] = {{
      optout_done:    v.optout_done,
      optout_date:    v.optout_date,
      followup_notes: v.followup_notes,
    }};
  }});
  const blob = new Blob([JSON.stringify(byBroker, null, 2)],
                        {{type: 'application/json'}});
  const a    = document.createElement('a');
  a.href     = URL.createObjectURL(blob);
  a.download = 'checklist_state_{profile_id}.json';
  a.click();
  URL.revokeObjectURL(a.href);
}}

// ── Row state ─────────────────────────────────────────────────────────────────
function applyRowState(row) {{
  const cb      = row.querySelector('input[type=checkbox]');
  const dt      = row.querySelector('input[type=date]');
  const ta      = row.querySelector('textarea.notes-input');
  const flagEl  = row.querySelector('.followup-flag');
  const checked = cb && cb.checked;

  row.classList.toggle('done', checked);
  if (dt) dt.disabled = !checked;
  if (ta) ta.disabled = false;   // notes always editable

  if (flagEl) {{
    if (checked && dt && dt.value) {{
      const base     = new Date(dt.value);
      const followup = new Date(base);
      followup.setDate(followup.getDate() + FOLLOWUP_DAYS);
      const today    = new Date(); today.setHours(0,0,0,0);
      const fmt      = followup.toLocaleDateString(undefined,
                         {{month:'short', day:'numeric', year:'numeric'}});
      if (today >= followup) {{
        flagEl.textContent = '⚠️ Follow-up overdue! (was ' + fmt + ')';
        flagEl.style.color = '#c0392b';
      }} else {{
        flagEl.textContent = '📅 Follow-up by ' + fmt;
        flagEl.style.color = '#e67e22';
      }}
      flagEl.style.display = 'inline-block';
    }} else {{
      flagEl.style.display = 'none';
    }}
  }}
}}

function updateCounter() {{
  const total = document.querySelectorAll('tr[data-row-id]').length;
  const done  = document.querySelectorAll('tr[data-row-id].done').length;
  const pct   = total ? Math.round((done / total) * 100) : 0;
  const bar   = document.querySelector('.progress-bar');
  const ctr   = document.querySelector('.counter');
  if (bar) bar.style.width = pct + '%';
  if (ctr) ctr.textContent = done + ' / ' + total + ' completed (' + pct + '%)';
}}

// ── Event wiring ──────────────────────────────────────────────────────────────
document.querySelectorAll('tr[data-row-id]').forEach(row => {{
  const cb = row.querySelector('input[type=checkbox]');
  const dt = row.querySelector('input[type=date]');
  const ta = row.querySelector('textarea.notes-input');

  if (cb) {{
    cb.addEventListener('change', () => {{
      if (dt) {{
        if (cb.checked && !dt.value)
          dt.value = new Date().toISOString().split('T')[0];
        else if (!cb.checked)
          dt.value = '';
      }}
      applyRowState(row);
      saveState();
      updateCounter();
    }});
  }}
  if (dt) {{ dt.addEventListener('change', () => {{ applyRowState(row); saveState(); }}); }}
  if (ta) {{ ta.addEventListener('input',  () => {{ saveState(); }}); }}
}});

loadState();
</script>
</body>
</html>
"""

ROW_TEMPLATE = """
<tr data-row-id="{row_id}" data-broker-name="{broker_name_escaped}">
  <td style="text-align:center;width:44px">
    <input type="checkbox" id="cb_{row_id}" title="Mark as completed">
  </td>
  <td class="broker-name"><strong>{broker_name}</strong>{badges}</td>
  <td class="legal" style="width:70px"><code>{legal_basis}</code></td>
  <td class="date-cell">
    <input type="date" id="dt_{row_id}" disabled title="Date opt-out was submitted">
    <span class="date-label">Opt-out date</span>
    <span class="followup-flag" style="display:none"></span>
  </td>
  <td class="notes-cell">
    <textarea class="notes-input" id="ta_{row_id}"
      placeholder="Log follow-up actions here — call reference #, BBB complaint filed, attorney notified, escalation steps…"
      title="Notes for this broker"></textarea>
  </td>
  <td style="white-space:nowrap;width:190px">{search_btn}{optout_btn}{phone_btn}</td>
  <td class="legal">{notes}</td>
</tr>
"""


class ManualChecklistBuilder:
    def __init__(self, reports_dir: Path, db_path: Path | None = None):
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.db_path     = db_path
        self.store       = ChecklistStateStore(db_path) if db_path else None

    def build(self, all_results: list[dict]) -> dict[str, Path]:
        """
        Build one checklist per profile that has BLOCKED/ERROR brokers.
        Returns dict mapping profile_id → Path.
        """
        datestamp       = datetime.now().strftime("%Y%m%d_%H%M%S")
        checklist_paths: dict[str, Path] = {}

        for pr in all_results:
            # Auto-import any JSON save files before building
            if self.store:
                pid = pr["profile"]["id"]
                self.store.load_json_saves(pid, self.reports_dir.parent)

            path = self._build_single(pr, datestamp)
            if path:
                checklist_paths[pr["profile"]["id"]] = path

        return checklist_paths

    def _label(self, profile: dict) -> str:
        names = profile.get("legal_names", {})
        return (
            profile.get("display_name") or
            f"{names.get('first','')} {names.get('last','')}".strip() or
            profile["id"]
        )

    def _build_single(self, pr: dict, datestamp: str) -> Path | None:
        profile = pr["profile"]
        pid     = profile["id"]
        label   = self._label(profile)

        actionable = [
            r for r in pr.get("broker_results", [])
            if r.status in ("BLOCKED", "ERROR") and r.optout_url
        ]
        if not actionable:
            return None

        # Load previous state from DB for pre-population
        prev_state: dict[str, dict] = {}
        if self.store:
            prev_state = self.store.get_profile_state(pid)

        rows      = []
        preloaded = {}   # will be injected as JSON into the HTML

        for i, r in enumerate(sorted(actionable, key=lambda x: x.broker_name)):
            row_id = f"{pid}_{i}"

            badges = ""
            if r.status == "BLOCKED":
                badges += '<span class="badge badge-blocked">BLOCKED</span>'
            elif r.status == "ERROR":
                badges += '<span class="badge badge-error">UNREACHABLE</span>'
            if not r.compliant:
                badges += '<span class="badge badge-nooptout">NO OPT-OUT — ATTORNEY</span>'

            # Phone button
            phone     = getattr(r, "phone", "") or ""
            phone_btn = ""
            if phone:
                digits    = "".join(c for c in phone if c.isdigit())
                phone_btn = (
                    f'<br><a class="btn btn-phone" href="tel:{digits}">'
                    f'📞 {phone}</a>'
                )

            # Pre-populate from previous state
            saved = prev_state.get(r.broker_name, {})
            preloaded[row_id] = {
                "broker_name":    r.broker_name,
                "optout_done":    saved.get("optout_done", False),
                "optout_date":    saved.get("optout_date", ""),
                "followup_notes": saved.get("followup_notes", ""),
            }

            rows.append(ROW_TEMPLATE.format(
                row_id             = row_id,
                broker_name        = r.broker_name,
                broker_name_escaped = r.broker_name.replace('"', '&quot;'),
                badges             = badges,
                legal_basis        = r.legal_basis,
                search_btn         = (
                    f'<a class="btn btn-search" href="{r.search_url}"'
                    f' target="_blank">🔍 Search</a>' if r.search_url else ""
                ),
                optout_btn         = (
                    f'<a class="btn btn-optout" href="{r.optout_url}"'
                    f' target="_blank">✋ Opt-out</a>' if r.optout_url else ""
                ),
                phone_btn          = phone_btn,
                notes              = r.notes or "—",
            ))

        body = f"""
        <div class="profile-block profile-section">
          <div class="stats">{len(actionable)} brokers need manual review</div>
          <div class="progress"><div class="progress-bar" style="width:0%"></div></div>
          <div class="counter">0 / {len(actionable)} completed (0%)</div>
          <table>
            <thead>
              <tr>
                <th style="width:44px">Done</th>
                <th>Broker</th>
                <th style="width:70px">Law</th>
                <th style="width:175px">Opt-out Date / Follow-up</th>
                <th>Notes / Follow-up Actions</th>
                <th style="width:180px">Actions</th>
                <th>Broker Notes</th>
              </tr>
            </thead>
            <tbody>{"".join(rows)}</tbody>
          </table>
        </div>
        """

        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        html = CHECKLIST_HTML.format(
            label          = label,
            date           = date_str,
            profile_id     = pid,
            datestamp      = datestamp,
            body           = body,
            preloaded_json = json.dumps(preloaded, ensure_ascii=False),
        )

        filename = f"manual_checklist_{pid}_{datestamp}.html"
        out_path = self.reports_dir / filename
        out_path.write_text(html, encoding="utf-8")
        log.info(f"  Checklist written: {out_path.name}")
        return out_path
