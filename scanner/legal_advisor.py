"""
legal_advisor.py
Geography-aware legal advisory engine.

For each profile, loads applicable legal frameworks based on:
  - Country (international law)
  - US state (state law, when country=US)
  - US federal (always applied for US residents)

Produces:
  - Applicable framework list with citation templates
  - Per-broker advisory text tailored to that profile's jurisdictions
  - Escalation flags for non-compliant brokers
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

FRAMEWORKS_DIR = Path(__file__).parent.parent / "config" / "legal_frameworks"

COUNTRY_FRAMEWORK_MAP = {
    "US":   None,
    "GB":   "GB.yaml",
    "CA":   "CA.yaml",
    "AU":   "AU.yaml",
    "BR":   "BR.yaml",
    "MX":   "MX.yaml",
    "SG":   "SG.yaml",
    "DE": "EU_GDPR.yaml", "FR": "EU_GDPR.yaml", "ES": "EU_GDPR.yaml",
    "IT": "EU_GDPR.yaml", "NL": "EU_GDPR.yaml", "BE": "EU_GDPR.yaml",
    "SE": "EU_GDPR.yaml", "PL": "EU_GDPR.yaml", "PT": "EU_GDPR.yaml",
    "AT": "EU_GDPR.yaml", "DK": "EU_GDPR.yaml", "FI": "EU_GDPR.yaml",
    "IE": "EU_GDPR.yaml", "CZ": "EU_GDPR.yaml", "RO": "EU_GDPR.yaml",
    "HU": "EU_GDPR.yaml", "GR": "EU_GDPR.yaml", "HR": "EU_GDPR.yaml",
    "SK": "EU_GDPR.yaml", "BG": "EU_GDPR.yaml", "LT": "EU_GDPR.yaml",
    "LV": "EU_GDPR.yaml", "EE": "EU_GDPR.yaml", "CY": "EU_GDPR.yaml",
    "LU": "EU_GDPR.yaml", "MT": "EU_GDPR.yaml", "SI": "EU_GDPR.yaml",
    "IS": "EU_GDPR.yaml", "LI": "EU_GDPR.yaml", "NO": "EU_GDPR.yaml",
}

US_STATE_FRAMEWORK_MAP = {
    "FL": "FL.yaml",
    "CA": "CA.yaml",
    "NY": "NY.yaml",
    "TX": "TX.yaml",
    "IL": "IL.yaml",
    "VA": "VA.yaml",
}


def _load_yaml(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path) as f:
        return yaml.safe_load(f)


def _load_framework_file(filename: str, base_dir: Path) -> dict | None:
    return _load_yaml(base_dir / filename)


class LegalAdvisor:
    def __init__(self, profile: dict):
        self.profile    = profile
        self.profile_id = profile["id"]
        self.frameworks: list[dict] = []
        self._load_all()

    def _load_all(self) -> None:
        seen_files: set[str] = set()

        for jur in self.profile.get("jurisdictions", []):
            country_code = jur.get("country_code", "").upper()
            region_code  = jur.get("region_code",  "").upper()

            if country_code == "US":
                fed_path = FRAMEWORKS_DIR / "us_federal.yaml"
                if "us_federal.yaml" not in seen_files and fed_path.exists():
                    fw = _load_yaml(fed_path)
                    if fw:
                        fw["_source_file"]       = "us_federal.yaml"
                        fw["_jurisdiction_label"] = "US Federal"
                        self.frameworks.append(fw)
                    seen_files.add("us_federal.yaml")

                state_file = US_STATE_FRAMEWORK_MAP.get(region_code)
                if state_file and state_file not in seen_files:
                    state_path = FRAMEWORKS_DIR / "us_states" / state_file
                    if state_path.exists():
                        fw = _load_yaml(state_path)
                        if fw:
                            fw["_source_file"]       = state_file
                            fw["_jurisdiction_label"] = fw.get("label", region_code)
                            self.frameworks.append(fw)
                    seen_files.add(state_file)
            else:
                country_file = COUNTRY_FRAMEWORK_MAP.get(country_code)
                if country_file and country_file not in seen_files:
                    country_path = FRAMEWORKS_DIR / "countries" / country_file
                    if country_path.exists():
                        fw = _load_yaml(country_path)
                        if fw:
                            fw["_source_file"]       = country_file
                            fw["_jurisdiction_label"] = fw.get("label", country_code)
                            self.frameworks.append(fw)
                    seen_files.add(country_file)
                elif not country_file:
                    log.warning(f"No legal framework for country code: {country_code}")

        log.debug(
            f"Profile {self.profile_id}: loaded "
            f"{len(self.frameworks)} framework(s): "
            f"{[f['_source_file'] for f in self.frameworks]}"
        )

    def applicable_laws_summary(self) -> list[dict]:
        laws = []
        for fw in self.frameworks:
            jur_label = fw.get("_jurisdiction_label", "Unknown")
            for f in fw.get("frameworks", []):
                laws.append({
                    "jurisdiction":            jur_label,
                    "code":                    f.get("code", ""),
                    "name":                    f.get("name", ""),
                    "statute":                 f.get("statute", ""),
                    "applies_to":              f.get("applies_to", ""),
                    "rights":                  f.get("rights", []),
                    "damages":                 f.get("damages", ""),
                    "private_right_of_action": f.get("private_right_of_action", False),
                    "enforcement":             f.get("enforcement", []),
                    "citation_template":       f.get("citation_template", ""),
                    "notes":                   f.get("notes", ""),
                })
        return laws

    def advisory_for_broker(self, broker_name: str, legal_basis: str, compliant: bool) -> str:
        laws  = self.applicable_laws_summary()
        lines: list[str] = []

        basis_to_codes = {
            "CCPA":    ["CCPA_CPRA"],
            "FCRA":    ["FCRA"],
            "GLBA":    ["GLBA"],
            "FL_DPPA": ["FL_DPPA", "DPPA"],
            "FL_PRA":  ["FL_PRA"],
            "NONE":    [],
        }
        deletion_codes = {
            "CCPA_CPRA", "GDPR_ERASURE", "UK_GDPR", "PIPEDA",
            "AU_PRIVACY_ACT", "LGPD", "MX_LFPDPPP", "SG_PDPA",
            "TX_TDPSA", "VA_CDPA", "NY_SHIELD", "FL_FIPA",
        }
        relevant_codes = set(basis_to_codes.get(legal_basis, [])) | deletion_codes

        cited = [law for law in laws if law["code"] in relevant_codes]

        if not cited:
            lines.append(
                f"No specific matching legal framework for '{broker_name}' "
                f"under your registered jurisdictions. Consult your attorney."
            )
        else:
            lines.append(f"Applicable legal frameworks for '{broker_name}':\n")
            for law in cited:
                pra = ("✅ Private right of action"
                       if law["private_right_of_action"]
                       else "❌ No private right of action (regulatory enforcement only)")
                lines.append(
                    f"  [{law['jurisdiction']}] {law['name']} ({law['statute']})\n"
                    f"  Damages: {law['damages'] or 'See enforcement agency'}\n"
                    f"  {pra}"
                )

        if not compliant:
            lines.append(
                "\n⚠️  This broker has NO accessible opt-out process. "
                "Forward to your attorney with the framework citations above."
            )

        agencies: list[str] = []
        for law in cited:
            for e in law.get("enforcement", []):
                entry = f"{e['agency']} — {e.get('url', '')}"
                if entry not in agencies:
                    agencies.append(entry)
        if agencies:
            lines.append("\nEnforcement contacts:")
            for a in agencies:
                lines.append(f"  • {a}")

        return "\n".join(lines)

    def citation_letter_for_broker(self, broker_name: str, legal_basis: str) -> str:
        laws    = self.applicable_laws_summary()
        profile = self.profile
        names   = profile.get("legal_names", {})
        name    = f"{names.get('first', '')} {names.get('last', '')}".strip()

        templates = [
            law["citation_template"]
            for law in laws
            if law.get("citation_template")
        ]

        if not templates:
            return (
                f"To Whom It May Concern,\n\n"
                f"I, {name}, request the immediate removal of my personal information "
                f"from your platform. I reserve all rights under applicable privacy law.\n\n"
                f"Sincerely,\n{name}"
            )

        paragraphs = "\n\n".join(t.strip() for t in templates)
        return (
            f"To Whom It May Concern,\n\n"
            f"I, {name}, am writing to formally demand the removal of my personal "
            f"information from your platform ({broker_name}).\n\n"
            f"{paragraphs}\n\n"
            f"I request written confirmation of compliance within the applicable "
            f"statutory timeframe. I reserve all rights to pursue the remedies "
            f"described above.\n\n"
            f"Sincerely,\n{name}"
        )

    def jurisdictions_label(self) -> str:
        parts = []
        for jur in self.profile.get("jurisdictions", []):
            region  = jur.get("region", "")
            country = jur.get("country", "")
            parts.append(f"{region}, {country}" if region else country)
        return " | ".join(parts) if parts else "Unknown"
