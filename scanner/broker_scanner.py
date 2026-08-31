"""
broker_scanner.py
Checks each known data broker for presence of a profile's personal information.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from urllib.parse import quote

import requests
from requests.exceptions import RequestException

from scanner.legal_advisor import LegalAdvisor

log = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

STATUS_FOUND     = "FOUND"
STATUS_NOT_FOUND = "NOT_FOUND"
STATUS_BLOCKED   = "BLOCKED"
STATUS_ERROR     = "ERROR"
STATUS_SKIPPED   = "SKIPPED"


@dataclass
class BrokerResult:
    broker_name:     str
    profile_id:      str
    status:          str
    search_url:      str
    optout_url:      str
    optout_method:   str
    legal_basis:     str
    compliant:       bool
    notes:           str
    phone:           str               = ""
    http_code:       int | None        = None
    match_signals:   list[str]         = field(default_factory=list)
    legal_advisory:  str               = ""
    citation_letter: str               = ""
    error_detail:    str               = ""


class BrokerScanner:
    def __init__(self, profile: dict, brokers: list[dict], verbose: bool = False):
        self.profile  = profile
        self.brokers  = brokers
        self.verbose  = verbose
        self.session  = self._make_session()
        self.advisor  = LegalAdvisor(profile)
        self._build_search_corpus()

    def _make_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9",
        })
        return s

    def _build_search_corpus(self) -> None:
        p     = self.profile
        names = p.get("legal_names", {})
        self.search_tokens = {
            "first":   names.get("first", "").lower(),
            "last":    names.get("last",  "").lower(),
            "full":    f"{names.get('first','')} {names.get('last','')}".lower().strip(),
            "aliases": [a.lower() for a in p.get("aliases", []) if a],
            "phones":  [ph.get("number", "").lower()
                        for ph in p.get("known_phones", []) if ph.get("number")],
            "emails":  [e.lower() for e in p.get("known_emails", []) if e],
            "cities":  list({addr.get("city", "").lower()
                             for addr in p.get("addresses", []) if addr.get("city")}),
            "zips":    list({addr.get("zip", "").lower()
                             for addr in p.get("addresses", []) if addr.get("zip")}),
            "streets": list({addr.get("street", "").lower()
                             for addr in p.get("addresses", []) if addr.get("street")}),
        }
        log.debug(
            f"Profile {self.profile['id']}: corpus — "
            f"phones={len(self.search_tokens['phones'])}, "
            f"emails={len(self.search_tokens['emails'])}, "
            f"cities={len(self.search_tokens['cities'])}"
        )

    def _primary_address(self) -> dict:
        for addr in self.profile.get("addresses", []):
            if addr.get("current") and addr.get("type") == "residential":
                return addr
        for addr in self.profile.get("addresses", []):
            if addr.get("city"):
                return addr
        return {}

    def _build_url(self, template: str) -> str:
        addr  = self._primary_address()
        names = self.profile.get("legal_names", {})
        for key, val in {
            "{first}": quote(names.get("first", ""), safe=""),
            "{last}":  quote(names.get("last",  ""), safe=""),
            "{city}":  quote(addr.get("city",   ""), safe=""),
            "{state}": quote(addr.get("region", ""), safe=""),
            "{zip}":   quote(addr.get("zip",    ""), safe=""),
        }.items():
            template = template.replace(key, val)
        return template

    def _detect_match(self, html: str) -> list[str]:
        signals: list[str] = []
        content = html.lower()
        tok     = self.search_tokens

        if tok["first"] and tok["last"] and tok["first"] in content and tok["last"] in content:
            signals.append(f"Name: {tok['full']}")
        for alias in tok["aliases"]:
            if alias and alias in content:
                signals.append(f"Alias: {alias}")
        for city in tok["cities"]:
            if city and city in content:
                signals.append(f"City: {city}")
        for phone in tok["phones"]:
            digits = "".join(c for c in phone if c.isdigit())
            content_digits = "".join(c for c in content if c.isdigit())
            if digits and len(digits) >= 7 and digits in content_digits:
                signals.append(f"Phone: {phone}")
        for email in tok["emails"]:
            if email and email in content:
                signals.append(f"Email: {email}")
        for street in tok["streets"]:
            if street:
                word = street.split()[0]
                if len(word) > 3 and word in content:
                    signals.append(f"Street: {street}")
        return signals

    def _scan_broker(self, broker: dict) -> BrokerResult:
        name      = broker["name"]
        url_tmpl  = broker.get("url", "")
        basis     = broker.get("legal_basis", "NONE")
        compliant = broker.get("compliant", False)

        base = BrokerResult(
            broker_name   = name,
            profile_id    = self.profile["id"],
            status        = STATUS_SKIPPED,
            search_url    = "",
            optout_url    = broker.get("optout_url", ""),
            optout_method = broker.get("optout_method", "unknown"),
            legal_basis   = basis,
            compliant     = compliant,
            notes         = broker.get("notes", ""),
            phone         = broker.get("phone", ""),
        )

        if not url_tmpl:
            base.status        = STATUS_SKIPPED
            base.legal_advisory = self.advisor.advisory_for_broker(name, basis, compliant)
            return base

        base.search_url = self._build_url(url_tmpl)

        try:
            time.sleep(random.uniform(1.0, 3.0))
            resp = self.session.get(base.search_url, timeout=15, allow_redirects=True)
            base.http_code = resp.status_code

            if resp.status_code == 200:
                signals = self._detect_match(resp.text)
                if signals:
                    base.status          = STATUS_FOUND
                    base.match_signals   = signals
                    base.legal_advisory  = self.advisor.advisory_for_broker(name, basis, compliant)
                    base.citation_letter = self.advisor.citation_letter_for_broker(name, basis)
                    log.info(f"  [FOUND]     {name} — {', '.join(signals)}")
                else:
                    base.status = STATUS_NOT_FOUND
                    if self.verbose:
                        log.debug(f"  [not found] {name}")
            elif resp.status_code in (403, 429, 503):
                base.status       = STATUS_BLOCKED
                base.error_detail = f"HTTP {resp.status_code}"
                log.warning(f"  [BLOCKED]   {name} (HTTP {resp.status_code})")
            else:
                base.status       = STATUS_ERROR
                base.error_detail = f"HTTP {resp.status_code}"
        except RequestException as exc:
            base.status       = STATUS_ERROR
            base.error_detail = str(exc)
            log.warning(f"  [ERROR]     {name} — {exc}")

        return base

    def _relevant_brokers(self) -> list[dict]:
        profile_countries = {
            jur.get("country_code", "").upper()
            for jur in self.profile.get("jurisdictions", [])
        }
        profile_regions = {
            jur.get("region_code", "").upper()
            for jur in self.profile.get("jurisdictions", [])
        }
        public_bases = {"FL_PRA", "FL_DPPA"}
        result: list[dict] = []
        for b in self.brokers:
            if b.get("legal_basis", "NONE") in public_bases:
                continue
            regions = b.get("regions", None)
            if regions is None:
                if "US" in profile_countries:
                    result.append(b)
            elif "GLOBAL" in regions:
                result.append(b)
            else:
                # Guard: skip any non-string entries (e.g. YAML booleans)
                region_set = {str(r).upper() for r in regions if isinstance(r, str)}
                if region_set & (profile_countries | profile_regions):
                    result.append(b)
        return result

    def scan_all(self) -> list[BrokerResult]:
        relevant = self._relevant_brokers()
        log.info(
            f"  Scanning {len(relevant)} brokers "
            f"({self.advisor.jurisdictions_label()})..."
        )
        results = [self._scan_broker(b) for b in relevant]
        found   = sum(1 for r in results if r.status == STATUS_FOUND)
        blocked = sum(1 for r in results if r.status == STATUS_BLOCKED)
        log.info(f"  → {found} found | {blocked} blocked | {len(results)} total")
        return results
