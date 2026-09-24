"""SQLite initialization and claim persistence for TruthLens."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import sqlite3

from flask import current_app, g


TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    claim_text TEXT NOT NULL CHECK (length(trim(claim_text)) > 0),
    source_platform TEXT NOT NULL CHECK (source_platform IN ('WhatsApp', 'X', 'Instagram', 'Other')),
    source_url TEXT,
    category TEXT NOT NULL CHECK (category IN ('Politics', 'Health', 'Finance', 'Other')),
    risk_flags TEXT NOT NULL,
    risk_score INTEGER NOT NULL CHECK (risk_score BETWEEN 0 AND 3),
    status TEXT NOT NULL DEFAULT 'unverified'
        CHECK (status IN ('unverified', 'verified_true', 'verified_false', 'misleading')),
    reviewer_note TEXT,
    created_at TEXT NOT NULL
)
"""

INDEX_SCHEMA = "CREATE INDEX IF NOT EXISTS idx_claims_created_at ON claims(created_at DESC)"


def _migrate_legacy_statuses(connection: sqlite3.Connection) -> None:
    """Convert Milestone 1 title-case status values while preserving claim data."""
    table = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'claims'"
    ).fetchone()
    if table is None or "'Verified True'" not in (table[0] or ""):
        return

    connection.execute("DROP INDEX IF EXISTS idx_claims_created_at")
    connection.execute("ALTER TABLE claims RENAME TO claims_legacy")
    connection.execute(TABLE_SCHEMA)
    connection.execute(
        """INSERT INTO claims
           (id, claim_text, source_platform, source_url, category, risk_flags,
            risk_score, status, reviewer_note, created_at)
           SELECT id, claim_text, source_platform, source_url, category, risk_flags,
                  risk_score,
                  CASE status
                    WHEN 'Unverified' THEN 'unverified'
                    WHEN 'Verified True' THEN 'verified_true'
                    WHEN 'Verified False' THEN 'verified_false'
                    WHEN 'Misleading' THEN 'misleading'
                    ELSE status
                  END,
                  reviewer_note, created_at
           FROM claims_legacy"""
    )
    connection.execute("DROP TABLE claims_legacy")


def init_db(database_path: str) -> None:
    """Create the database directory, migrate old statuses, and initialize schema."""
    database_path = os.fspath(database_path)
    if database_path != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(database_path)), exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=5)
    try:
        connection.execute("BEGIN IMMEDIATE")
        _migrate_legacy_statuses(connection)
        connection.execute(TABLE_SCHEMA)
        connection.execute(INDEX_SCHEMA)
        connection.commit()
    finally:
        connection.close()


def get_db() -> sqlite3.Connection:
    """Get the request-scoped SQLite connection."""
    if "db" not in g:
        connection = sqlite3.connect(current_app.config["DATABASE"], timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


def close_db(_error: BaseException | None = None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def _serialize(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    claim = dict(row)
    claim["risk_flags"] = json.loads(claim["risk_flags"])
    claim["high_risk"] = claim["risk_score"] >= 2
    return claim


def insert_claim(
    *,
    claim_text: str,
    source_platform: str,
    source_url: str | None,
    category: str,
    risk_flags: list[str],
    risk_score: int,
) -> dict:
    """Insert a new, immutable claim with its server-calculated risk data."""
    created_at = datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    connection = get_db()
    cursor = connection.execute(
        """INSERT INTO claims
           (claim_text, source_platform, source_url, category, risk_flags,
            risk_score, status, reviewer_note, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'unverified', NULL, ?)""",
        (
            claim_text,
            source_platform,
            source_url,
            category,
            json.dumps(risk_flags),
            risk_score,
            created_at,
        ),
    )
    connection.commit()
    return get_claim(cursor.lastrowid)  # type: ignore[return-value]


def get_claim(claim_id: int) -> dict | None:
    row = get_db().execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
    return _serialize(row)


def list_claims(*, category: str | None = None, status: str | None = None) -> list[dict]:
    clauses: list[str] = []
    parameters: list[str] = []
    if category is not None:
        clauses.append("category = ?")
        parameters.append(category)
    if status is not None:
        clauses.append("status = ?")
        parameters.append(status)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = get_db().execute(
        f"""SELECT * FROM claims {where}
            ORDER BY
              CASE
                WHEN risk_score >= 2 AND status = 'unverified' THEN 0
                WHEN risk_score >= 2 THEN 1
                WHEN status = 'unverified' THEN 2
                ELSE 3
              END ASC,
              created_at DESC,
              id DESC""",
        parameters,
    ).fetchall()
    return [_serialize(row) for row in rows]  # type: ignore[misc]


def update_claim_review(
    claim_id: int,
    *,
    status: str,
    reviewer_note: str | None = None,
    update_note: bool,
) -> dict | None:
    """Update only the review fields; the original claim fields are never writable here."""
    connection = get_db()
    if update_note:
        cursor = connection.execute(
            "UPDATE claims SET status = ?, reviewer_note = ? WHERE id = ?",
            (status, reviewer_note, claim_id),
        )
    else:
        cursor = connection.execute(
            "UPDATE claims SET status = ? WHERE id = ?",
            (status, claim_id),
        )
    connection.commit()
    if cursor.rowcount == 0:
        return None
    return get_claim(claim_id)


def get_summary() -> dict[str, int]:
    row = get_db().execute(
        """SELECT COUNT(*) AS total_claims,
                  COALESCE(SUM(CASE WHEN risk_score >= 2 THEN 1 ELSE 0 END), 0) AS high_risk,
                  COALESCE(SUM(CASE WHEN status = 'unverified' THEN 1 ELSE 0 END), 0) AS unverified
           FROM claims"""
    ).fetchone()
    return dict(row)
