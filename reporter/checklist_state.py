"""
checklist_state.py
Persists manual checklist state (optout_date, followup_notes) across scan runs.

Storage: SQLite table `checklist_state` in scan_history.db
Key: (profile_id, broker_name) — one row per broker per profile, upserted on save.

The checklist HTML:
  - On load: receives pre-populated values injected by ManualChecklistBuilder
  - On change: saves to localStorage immediately (session persistence)
  - "Save Progress" button: POSTs state as a JSON download the user saves to
    outputs/checklist_state_<profile_id>.json
  - On next build: ManualChecklistBuilder reads both the DB and any JSON save
    file, merging them (JSON file wins as it is most recent)
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS checklist_state (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id      TEXT    NOT NULL,
    broker_name     TEXT    NOT NULL,
    optout_done     INTEGER DEFAULT 0,
    optout_date     TEXT,
    followup_notes  TEXT,
    last_updated    TEXT,
    UNIQUE(profile_id, broker_name)
);
"""

CREATE_IDX = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_checklist_state
    ON checklist_state (profile_id, broker_name);
"""


class ChecklistStateStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(CREATE_TABLE)
            conn.execute(CREATE_IDX)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_profile_state(self, profile_id: str) -> dict[str, dict]:
        """
        Returns all saved state for a profile as:
          { broker_name: { optout_done, optout_date, followup_notes } }
        """
        sql = """
            SELECT broker_name, optout_done, optout_date, followup_notes
              FROM checklist_state
             WHERE profile_id = ?
        """
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, (profile_id,)).fetchall()
        return {
            r["broker_name"]: {
                "optout_done":    bool(r["optout_done"]),
                "optout_date":    r["optout_date"]    or "",
                "followup_notes": r["followup_notes"] or "",
            }
            for r in rows
        }

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert(
        self,
        profile_id:     str,
        broker_name:    str,
        optout_done:    bool,
        optout_date:    str,
        followup_notes: str,
    ) -> None:
        """Insert or update state for one broker."""
        sql = """
            INSERT INTO checklist_state
              (profile_id, broker_name, optout_done, optout_date,
               followup_notes, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_id, broker_name) DO UPDATE SET
              optout_done    = excluded.optout_done,
              optout_date    = excluded.optout_date,
              followup_notes = excluded.followup_notes,
              last_updated   = excluded.last_updated
        """
        with self._conn() as conn:
            conn.execute(sql, (
                profile_id, broker_name,
                1 if optout_done else 0,
                optout_date, followup_notes,
                datetime.now().isoformat(),
            ))
        log.debug(f"Checklist state saved: {profile_id}/{broker_name}")

    def import_from_json(self, profile_id: str, json_path: Path) -> int:
        """
        Import state from a JSON save file (exported by the browser).
        The JSON file wins over DB values for the same broker (it is more recent).
        Returns number of records imported.
        """
        if not json_path.exists():
            return 0
        with open(json_path) as f:
            data = json.load(f)

        count = 0
        for broker_name, state in data.items():
            self.upsert(
                profile_id     = profile_id,
                broker_name    = broker_name,
                optout_done    = state.get("optout_done", False),
                optout_date    = state.get("optout_date", ""),
                followup_notes = state.get("followup_notes", ""),
            )
            count += 1

        log.info(f"Imported {count} checklist state records from {json_path.name}")
        return count

    def load_json_saves(self, profile_id: str, outputs_dir: Path) -> None:
        """
        Auto-import any JSON save files found in outputs_dir for this profile.
        Files are named: checklist_state_<profile_id>.json
        After import, the file is renamed to .imported so it is not re-processed.
        """
        save_file = outputs_dir / f"checklist_state_{profile_id}.json"
        if save_file.exists():
            count = self.import_from_json(profile_id, save_file)
            if count > 0:
                save_file.rename(save_file.with_suffix(".json.imported"))
                log.info(f"State file imported and renamed: {save_file.name}")
