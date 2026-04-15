import sqlite3
import logging
from pathlib import Path
from typing import Iterable

from models import GlossaryItem, Paper

DB_PATH = Path(__file__).parent.parent / "data" / "archive.db"

logger = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS papers (
    entry_id     TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    authors      TEXT NOT NULL,
    categories   TEXT NOT NULL,
    pdf_url      TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    fetched_at   TEXT NOT NULL,
    expire_at    TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'unread'
);

CREATE TABLE IF NOT EXISTS glossary (
    term          TEXT PRIMARY KEY,
    definition    TEXT NOT NULL,
    aliases       TEXT NOT NULL DEFAULT '',
    first_seen_id TEXT,
    updated_at    TEXT NOT NULL,
    FOREIGN KEY (first_seen_id) REFERENCES papers (entry_id) ON DELETE SET NULL
);
"""

_MIGRATIONS = [
    ("pdf_url", "ALTER TABLE papers ADD COLUMN pdf_url TEXT NOT NULL DEFAULT ''"),
    ("status",  "ALTER TABLE papers ADD COLUMN status  TEXT NOT NULL DEFAULT 'unread'"),
]


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(DDL)
        for column, sql in _MIGRATIONS:
            if not _column_exists(conn, "papers", column):
                conn.execute(sql)
                logger.info("Migration: added '%s' column to papers table", column)
    logger.info("DB initialized: %s", DB_PATH)


def insert_papers(papers: Iterable[Paper]) -> tuple[int, int]:
    """Insert papers using INSERT OR IGNORE (dedup by entry_id).

    Returns (inserted, skipped) counts.
    """
    rows = [
        (
            p.entry_id,
            p.title,
            p.summary,
            p.authors,
            p.categories,
            p.pdf_url,
            p.submitted_at.isoformat(),
            p.fetched_at.isoformat(),
            p.expire_at.isoformat(),
        )
        for p in papers
    ]

    sql = """
        INSERT OR IGNORE INTO papers
            (entry_id, title, summary, authors, categories, pdf_url,
             submitted_at, fetched_at, expire_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    inserted = 0
    skipped = 0
    with get_connection() as conn:
        for row in rows:
            cur = conn.execute(sql, row)
            if cur.rowcount:
                inserted += 1
            else:
                skipped += 1

    logger.info("insert_papers: inserted=%d, skipped=%d", inserted, skipped)
    return inserted, skipped


def get_unread_papers(days: int, limit: int) -> list[sqlite3.Row]:
    """Fetch unread papers submitted within the last `days` days."""
    sql = """
        SELECT entry_id, title, categories, pdf_url, submitted_at, summary, status
        FROM papers
        WHERE status = 'unread'
          AND submitted_at >= datetime('now', ? || ' days')
        ORDER BY submitted_at DESC
        LIMIT ?
    """
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, (f"-{days}", limit)).fetchall()


def get_unread_counts_by_date(days: int) -> list[sqlite3.Row]:
    """Return per-day unread counts within the last `days` days, newest first."""
    sql = """
        SELECT date(submitted_at) AS date, COUNT(*) AS count
        FROM papers
        WHERE status = 'unread'
          AND submitted_at >= datetime('now', ? || ' days')
        GROUP BY date(submitted_at)
        ORDER BY date DESC
    """
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, (f"-{days}",)).fetchall()


def mark_as_read(entry_ids: list[str]) -> None:
    """Set status = 'read' for the given entry_ids."""
    if not entry_ids:
        return
    placeholders = ",".join("?" * len(entry_ids))
    sql = f"UPDATE papers SET status = 'read' WHERE entry_id IN ({placeholders})"
    with get_connection() as conn:
        conn.execute(sql, entry_ids)


def upsert_glossary(item: GlossaryItem) -> None:
    """Insert or replace a glossary term."""
    sql = """
        INSERT INTO glossary (term, definition, aliases, first_seen_id, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(term) DO UPDATE SET
            definition    = excluded.definition,
            aliases       = excluded.aliases,
            first_seen_id = COALESCE(glossary.first_seen_id, excluded.first_seen_id),
            updated_at    = excluded.updated_at
    """
    with get_connection() as conn:
        conn.execute(sql, (
            item.term,
            item.definition,
            item.aliases,
            item.first_seen_id or None,
            item.updated_at.isoformat(),
        ))


def get_all_glossary() -> list[GlossaryItem]:
    """Return all glossary entries."""
    sql = "SELECT term, definition, aliases, first_seen_id, updated_at FROM glossary ORDER BY term"
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql).fetchall()
    return [
        GlossaryItem(
            term=r["term"],
            definition=r["definition"],
            aliases=r["aliases"] or "",
            first_seen_id=r["first_seen_id"] or "",
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


def update_glossary(term: str, **fields: str) -> bool:
    """Partially update a glossary entry by term. Returns True if the row existed.

    Only keys present in `fields` are updated (definition, aliases).
    updated_at is always refreshed.
    """
    if not fields:
        return False
    allowed = {"definition", "aliases"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return False

    from datetime import datetime, timezone
    sets["updated_at"] = datetime.now(timezone.utc).isoformat()

    assignments = ", ".join(f"{k} = ?" for k in sets)
    values = list(sets.values()) + [term]
    with get_connection() as conn:
        cur = conn.execute(
            f"UPDATE glossary SET {assignments} WHERE term = ?", values
        )
        return cur.rowcount > 0


def delete_glossary_term(term: str) -> bool:
    """Delete a glossary term. Returns True if a row was deleted."""
    with get_connection() as conn:
        cur = conn.execute("DELETE FROM glossary WHERE term = ?", (term,))
        return cur.rowcount > 0


def delete_expired() -> int:
    """Delete rows whose expire_at is in the past. Returns deleted count."""
    #sql = "DELETE FROM papers WHERE expire_at < datetime('now')"
    sql = "DELETE FROM papers"
    with get_connection() as conn:
        cur = conn.execute(sql)
        count = cur.rowcount
    logger.info("delete_expired: removed=%d", count)
    return count
