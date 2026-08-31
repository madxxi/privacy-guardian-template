"""
public_records.py
Florida-specific public record sources with legal advisor integration.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

import requests
from requests.exceptions import RequestException

from scanner.legal_advisor import LegalAdvisor

log = logging.getLogger(__name__)

STATUS_FOUND   = "FOUND"
STATUS_BLOCKED = "BLOCKED"
STATUS_ERROR   = "ERROR"
STATUS_SKIPPED = "SKIPPED"


@dataclass
class PublicRecordResult:
    source_name:       str
    profile_id:        str
    status:            str
    search_url:        str
    legal_basis:       str
    masking_available: bool
    masking_notes:     str
    optout_url:        str
    optout_method:     str
    compliant:         bool
    general_notes:     str
    legal_advisory:    str       = ""
    http_code:         int | None = None
    error_detail:      str       = ""


class PublicRecordsScanner:
    def __init__(self, profile: dict, brokers: list[dict], verbose: bool = False):
        self.profile  = profile
        self.brokers  = brokers
        self.verbose  = verbose
        self.advisor  = LegalAdvisor(profile)
        self.session  = self._make_session()

    def _make_session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        })
        return s

    def _check_url(self, url: str) -> tuple[int | None, str]:
        try:
            time.sleep(random.uniform(1.0, 2.5))
            resp = self.session.head(url, timeout=10, allow_redirects=True)
            return resp.status_code, ""
        except RequestException as exc:
            return None, str(exc)

    def _masking_notes(self, broker: dict) -> tuple[bool, str]:
        basis = broker.get("legal_basis", "NONE")
        laws  = self.advisor.applicable_laws_summary()

        if basis == "FL_PRA":
            fl_pra = next((l for l in laws if l["code"] == "FL_PRA"), None)
            if fl_pra:
                classes = (fl_pra.get("public_suppression_eligibility") or {}).get(
                    "protected_classes", []
                )
                classes_text = "\n".join(f"  • {c}" for c in classes)
                return False, (
                    f"[{fl_pra['jurisdiction']}] {fl_pra['name']} ({fl_pra['statute']})\n"
                    f"Address suppression only available for:\n{classes_text}\n"
                    f"General public suppression is NOT available under Florida law."
                )
            return False, "Florida Public Records Act: suppression for protected occupations only."

        if basis == "FL_DPPA":
            return True, (
                "Your driver record is protected under the DPPA and Fla. Stat. § 322.142. "
                "If this data appears on a commercial site for marketing, that is a federal "
                "violation. Document the URL and date and forward to your attorney immediately."
            )

        return False, "No masking mechanism identified for this source."

    def scan_all(self) -> list[PublicRecordResult]:
        public_bases = {"FL_PRA", "FL_DPPA"}
        pub_brokers  = [
            b for b in self.brokers
            if b.get("legal_basis", "NONE") in public_bases
        ]

        log.info(f"  Checking {len(pub_brokers)} public record sources...")
        results: list[PublicRecordResult] = []

        for broker in pub_brokers:
            name = broker["name"]
            url  = broker.get("url") or broker.get("optout_url", "")

            masking_available, masking_notes = self._masking_notes(broker)

            http_code, error = self._check_url(url) if url else (None, "No URL configured")
            status = (
                STATUS_SKIPPED if not url else
                STATUS_FOUND   if http_code == 200 else
                STATUS_BLOCKED if http_code in (403, 429) else
                STATUS_ERROR
            )

            results.append(PublicRecordResult(
                source_name       = name,
                profile_id        = self.profile["id"],
                status            = status,
                search_url        = url,
                legal_basis       = broker.get("legal_basis", "NONE"),
                masking_available = masking_available,
                masking_notes     = masking_notes,
                optout_url        = broker.get("optout_url", ""),
                optout_method     = broker.get("optout_method", "unknown"),
                compliant         = broker.get("compliant", False),
                general_notes     = broker.get("notes", ""),
                legal_advisory    = self.advisor.advisory_for_broker(
                    name,
                    broker.get("legal_basis", "NONE"),
                    broker.get("compliant", False),
                ),
                http_code         = http_code,
                error_detail      = error,
            ))
            log.info(f"  [pub-record] {name} — {status}")

        return results
