"""
report_builder.py
Generates one self-contained HTML report PER PROFILE.
No cross-profile data leaks — each file contains only one person's findings.
Naming: report_<profile_id>_<YYYYMMDD_HHMMSS>.html
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Privacy Guardian — {label} — {date}</title>
<style>
  body  {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           background: #f4f6f9; color: #2c3e50; margin: 0; padding: 2rem; }}
  h1    {{ color: #2c3e50; border-bottom: 3px solid #e74c3c; padding-bottom: .5rem; }}
  h2    {{ color: #34495e; margin-top: 2.5rem; }}
  h3    {{ color: #555; margin-top: 1.5rem; }}
  .card {{ background: white; border-radius: 8px; padding: 1.5rem;
           margin-bottom: 2rem; box-shadow: 0 2px 8px rgba(0,0,0,.08); }}
  .meta {{ background: #ecf0f1; border-radius: 6px; padding: .8rem 1rem;
           font-size: .85rem; margin-bottom: 1rem; }}
  .meta span {{ margin-right: 1.5rem; }}
  .badge {{ padding: .3rem .7rem; border-radius: 4px; color: white;
            font-weight: bold; font-size: .82rem; margin-right: .4rem; }}
  .summary-row {{ display: flex; gap: .5rem; flex-wrap: wrap; margin-bottom: 1rem; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .88rem; margin-bottom: 1rem; }}
  th    {{ background: #2c3e50; color: white; padding: .6rem 1rem; text-align: left; }}
  td    {{ padding: .55rem 1rem; border-bottom: 1px solid #ecf0f1; vertical-align: top; }}
  tr:hover td {{ background: #fdfefe; }}
  .FOUND     {{ color: #c0392b; font-weight: bold; }}
  .NOT_FOUND {{ color: #27ae60; }}
  .BLOCKED   {{ color: #e67e22; }}
  .ERROR     {{ color: #95a5a6; }}
  .SKIPPED   {{ color: #bdc3c7; }}
  .advisory  {{ background: #fef9e7; border-left: 4px solid #f39c12; padding: .7rem 1rem;
                font-size: .8rem; white-space: pre-wrap; border-radius: 0 4px 4px 0;
                margin-top: .3rem; }}
  .citation  {{ background: #eaf4fb; border-left: 4px solid #2980b9; padding: .7rem 1rem;
                font-size: .78rem; white-space: pre-wrap; border-radius: 0 4px 4px 0;
                margin-top: .3rem; font-family: 'Courier New', monospace; }}
  .attn      {{ color: #c0392b; font-weight: bold; font-size: .78rem;
                display: block; margin-top: .4rem; }}
  .jur-tag   {{ background: #2980b9; color: white; font-size: .72rem;
                padding: .2rem .5rem; border-radius: 3px; margin-right: .3rem; }}
  details summary {{ cursor: pointer; color: #2980b9; font-size: .82rem;
                     margin-top: .4rem; }}
  a {{ color: #2980b9; }}
  footer {{ margin-top: 3rem; font-size: .78rem; color: #95a5a6; }}
</style>
</head>
<body>
<h1>🛡️ Privacy Guardian — Personal Scan Report</h1>
<p>
  <strong>For:</strong> {label} &nbsp;|&nbsp;
  <strong>Generated:</strong> {date}
</p>
{body}
<footer>
  privacy-guardian &middot; This report is intended solely for {label}. &middot;
  Legal advisories and citation templates are informational.
  Consult a licensed attorney for case-specific legal action.
</footer>
</body>
</html>
"""


class ReportBuilder:
    def __init__(self, reports_dir: Path):
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def build(self, all_results: list[dict]) -> dict[str, Path]:
        """
        Build one HTML report per profile.
        Returns dict mapping profile_id → Path of generated report.
        """
        datestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_paths: dict[str, Path] = {}

        for pr in all_results:
            path = self._build_single(pr, datestamp)
            report_paths[pr["profile"]["id"]] = path

        return report_paths

    def write_optout_queue(self, all_results: list[dict], queue_dir: Path) -> None:
        """Write one opt-out text file per profile (no cross-profile data)."""
        for pr in all_results:
            self._write_single_queue(pr, queue_dir)

    # ── Per-profile report ────────────────────────────────────────────────────

    def _build_single(self, pr: dict, datestamp: str) -> Path:
        profile  = pr["profile"]
        pid      = profile["id"]
        label    = self._label(profile)
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        body = self._profile_body(pr, label)
        html = HTML_TEMPLATE.format(
            label = label,
            date  = date_str,
            body  = body,
        )

        filename = f"report_{pid}_{datestamp}.html"
        out_path = self.reports_dir / filename
        out_path.write_text(html, encoding="utf-8")
        log.info(f"  Report written: {out_path.name}")
        return out_path

    def _label(self, profile: dict) -> str:
        names = profile.get("legal_names", {})
        return (
            profile.get("display_name") or
            f"{names.get('first','')} {names.get('last','')}".strip() or
            profile["id"]
        )

    def _profile_body(self, pr: dict, label: str) -> str:
        profile     = pr["profile"]
        broker_rows = pr.get("broker_results", [])
        pub_rows    = pr.get("pub_results", [])

        jurs     = profile.get("jurisdictions", [])
        jur_tags = "".join(
            f'<span class="jur-tag">{j.get("region_code") or j.get("country_code","?")}</span>'
            for j in jurs
        )

        addrs    = profile.get("addresses", [])
        addr_str = "; ".join(
            f"{a.get('type','').title()}: {a.get('city','')}, "
            f"{a.get('region','')} {a.get('zip','')} {a.get('country','')}"
            for a in addrs if a.get("city")
        )

        found   = sum(1 for r in broker_rows if r.status == "FOUND")
        blocked = sum(1 for r in broker_rows if r.status == "BLOCKED")
        clear   = sum(1 for r in broker_rows if r.status == "NOT_FOUND")
        intl    = sum(1 for r in broker_rows
                      if r.status == "FOUND" and r.legal_basis not in
                      {"CCPA","FCRA","GLBA","FL_DPPA","FL_PRA","NONE"})

        return f"""
        <div class="card">
          <h2>👤 {label} {jur_tags}</h2>
          <div class="meta">
            <span>🏠 {addr_str or 'Addresses not configured'}</span>
          </div>
          <div class="summary-row">
            <span class="badge" style="background:#c0392b">{found} Found</span>
            <span class="badge" style="background:#27ae60">{clear} Clear</span>
            <span class="badge" style="background:#e67e22">{blocked} Blocked/Recheck</span>
            {"<span class='badge' style='background:#8e44ad'>" + str(intl) + " Intl Found</span>" if intl else ""}
          </div>
          <h3>Commercial &amp; International Data Brokers</h3>
          {self._broker_table(broker_rows)}
          <h3>Public Record Sources</h3>
          {self._pub_table(pub_rows)}
        </div>
        """

    def _broker_table(self, rows: list) -> str:
        if not rows:
            return "<p>No broker results.</p>"

        html_rows = []
        for r in sorted(rows, key=lambda x: (x.status != "FOUND", x.broker_name)):
            optout  = (
                f'<a href="{r.optout_url}" target="_blank">Opt-out ↗</a>'
                if r.optout_url else "—"
            )
            signals = ", ".join(r.match_signals) if r.match_signals else "—"

            extra = ""
            if r.status == "FOUND":
                adv = ""
                if r.legal_advisory:
                    flag = ""
                    if not r.compliant:
                        flag = '<span class="attn">⚠️ NO OPT-OUT PROCESS — Forward to attorney</span>'
                    adv = f'<div class="advisory">{r.legal_advisory}{flag}</div>'
                cit = ""
                if r.citation_letter:
                    cit = (
                        f'<details><summary>📄 Show demand letter citation</summary>'
                        f'<div class="citation">{r.citation_letter}</div></details>'
                    )
                if adv or cit:
                    extra = f'<tr><td colspan="6">{adv}{cit}</td></tr>'

            html_rows.append(f"""
            <tr>
              <td><strong>{r.broker_name}</strong></td>
              <td class="{r.status}">{r.status}</td>
              <td>{signals}</td>
              <td><code style="font-size:.78rem">{r.legal_basis}</code></td>
              <td>{optout}</td>
              <td style="font-size:.78rem">{r.notes or "—"}</td>
            </tr>
            {extra}
            """)

        return f"""
        <table>
          <thead>
            <tr>
              <th>Broker</th><th>Status</th><th>Match Signals</th>
              <th>Legal Basis</th><th>Opt-Out</th><th>Notes</th>
            </tr>
          </thead>
          <tbody>{"".join(html_rows)}</tbody>
        </table>
        """

    def _pub_table(self, rows: list) -> str:
        if not rows:
            return "<p>No public record sources checked.</p>"

        html_rows = []
        for r in rows:
            masking = "✅ See notes" if r.masking_available else "❌ Not available (general public)"
            optout  = (
                f'<a href="{r.optout_url}" target="_blank">Link ↗</a>'
                if r.optout_url else "—"
            )
            notes_block = (
                f'<div class="advisory" style="font-size:.77rem">{r.masking_notes}</div>'
                if r.masking_notes else ""
            )
            legal_block = (
                f'<div class="advisory" style="font-size:.77rem">{r.legal_advisory}</div>'
                if r.legal_advisory else ""
            )
            extra = (
                f'<tr><td colspan="5">{notes_block}{legal_block}</td></tr>'
                if notes_block or legal_block else ""
            )

            html_rows.append(f"""
            <tr>
              <td><strong>{r.source_name}</strong></td>
              <td><code style="font-size:.78rem">{r.legal_basis}</code></td>
              <td>{masking}</td>
              <td>{optout}</td>
              <td style="font-size:.78rem">{r.general_notes or "—"}</td>
            </tr>
            {extra}
            """)

        return f"""
        <table>
          <thead>
            <tr>
              <th>Source</th><th>Legal Basis</th><th>Masking?</th>
              <th>Link</th><th>Notes</th>
            </tr>
          </thead>
          <tbody>{"".join(html_rows)}</tbody>
        </table>
        """

    # ── Per-profile opt-out queue ─────────────────────────────────────────────

    def _write_single_queue(self, pr: dict, queue_dir: Path) -> None:
        profile = pr["profile"]
        pid     = profile["id"]
        found   = [r for r in pr.get("broker_results", []) if r.status == "FOUND"]

        if not found:
            return

        names      = profile.get("legal_names", {})
        name       = f"{names.get('first','')} {names.get('last','')}".strip()
        jur_labels = ", ".join(
            f"{j.get('region_code','?')}, {j.get('country_code','?')}"
            for j in profile.get("jurisdictions", [])
        )

        lines = [
            f"# Opt-Out & Citation Queue",
            f"# Profile      : {name} (ID: {pid})",
            f"# Jurisdictions: {jur_labels}",
            f"# Generated    : {datetime.now():%Y-%m-%d %H:%M:%S}",
            f"# Items        : {len(found)}",
            "",
        ]

        for r in sorted(found, key=lambda x: x.broker_name):
            flag = " ⚠️  NO OPT-OUT — ATTORNEY REFERRAL" if not r.compliant else ""
            lines += [
                f"{'='*70}",
                f"## {r.broker_name}{flag}",
                f"   Match signals : {', '.join(r.match_signals)}",
                f"   Legal basis   : {r.legal_basis}",
                f"   Opt-out URL   : {r.optout_url or 'None'}",
                f"   Method        : {r.optout_method}",
                f"   Notes         : {r.notes or 'None'}",
                "",
            ]
            if r.legal_advisory:
                lines += ["-- Legal Advisory --", r.legal_advisory, ""]
            if r.citation_letter:
                lines += ["-- Demand Letter Citation --", r.citation_letter, ""]

        queue_path = queue_dir / f"optout_{pid}.txt"
        queue_path.write_text("\n".join(lines), encoding="utf-8")
        log.info(f"  Queue: {queue_path}")
