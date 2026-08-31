"""
tracker.py
SQLite-backed history of all scans — tracks when each broker was found,
when an opt-out was submitted, and when/if removal was confirmed.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)


CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS scan_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date     TEXT    NOT NULL,
    profile_id    TEXT    NOT NULL,
    broker_name   TEXT    NOT NULL,
    record_type   TEXT    NOT NULL DEFAULT 'commercial',  -- commercial | public_record
    status        TEXT    NOT NULL,
    search_url    TEXT,
    optout_url    TEXT,
    legal_basis   TEXT,
    compliant     INTEGER,
    match_signals TEXT,   -- JSON array
    notes         TEXT,
    optout_sent   INTEGER DEFAULT 0,   -- 0/1 flag
    optout_date   TEXT,
    resolved      INTEGER DEFAULT 0,   -- 0/1 flag
    resolved_date TEXT
);
"""

CREATE_IDX = """
CREATE INDEX IF NOT EXISTS idx_profile_broker
    ON scan_events (profile_id, broker_name);
"""


class ScanTracker:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(CREATE_TABLE)
            conn.execute(CREATE_IDX)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def record(self, profile_results: dict) -> None:
        """Persist a full profile scan result set to the DB."""
        profile   = profile_results["profile"]
        scan_time = profile_results["scan_time"]

        rows = []

        # Commercial broker results
        for r in profile_results.get("broker_results", []):
            rows.append((
                scan_time,
                r.profile_id,
                r.broker_name,
                "commercial",
                r.status,
                r.search_url,
                r.optout_url,
                r.legal_basis,
                1 if r.compliant else 0,
                json.dumps(r.match_signals),
                r.notes,
            ))

        # Public record results
        for r in profile_results.get("pub_results", []):
            rows.append((
                scan_time,
                r.profile_id,
                r.source_name,
                "public_record",
                r.status,
                r.search_url,
                r.optout_url,
                r.legal_basis,
                1 if r.compliant else 0,
                json.dumps([]),
                r.general_notes,
            ))

        sql = """
            INSERT INTO scan_events
              (scan_date, profile_id, broker_name, record_type, status,
               search_url, optout_url, legal_basis, compliant,
               match_signals, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """
        with self._conn() as conn:
            conn.executemany(sql, rows)

        log.debug(f"Tracker: recorded {len(rows)} events for profile {profile['id']}")

    def mark_optout_sent(self, profile_id: str, broker_name: str) -> None:
        sql = """
            UPDATE scan_events
               SET optout_sent = 1, optout_date = ?
             WHERE profile_id = ? AND broker_name = ?
               AND optout_sent = 0
        """
        with self._conn() as conn:
            conn.execute(sql, (datetime.now().isoformat(), profile_id, broker_name))

    def mark_resolved(self, profile_id: str, broker_name: str) -> None:
        sql = """
            UPDATE scan_events
               SET resolved = 1, resolved_date = ?
             WHERE profile_id = ? AND broker_name = ?
               AND resolved = 0
        """
        with self._conn() as conn:
            conn.execute(sql, (datetime.now().isoformat(), profile_id, broker_name))

    def get_history(self, profile_id: str) -> list[dict]:
        sql = """
            SELECT * FROM scan_events
             WHERE profile_id = ?
             ORDER BY scan_date DESC
        """
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, (profile_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_pending_optouts(self, profile_id: str) -> list[dict]:
        sql = """
            SELECT DISTINCT broker_name, optout_url, legal_basis, notes
              FROM scan_events
             WHERE profile_id = ? AND status = 'FOUND' AND optout_sent = 0
             ORDER BY broker_name
        """
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, (profile_id,)).fetchall()
        return [dict(r) for r in rows]
