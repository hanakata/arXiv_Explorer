# arXiv Explorer: Rolling-Window Fetcher & Knowledge Manager

## Project Overview
A robust, lightweight system to fetch recent CS research papers from arXiv, manage information lifecycle via TTL, and build a **personal technical glossary**. It features a Rich-based terminal UI for efficient scanning, read-tracking, and integrated glossary annotations.

## Tech Stack
- **Language**: Python 3.10+
- **Libraries**: `arxiv`, `pydantic`, `rich`, `PyYAML`
- **Database**: SQLite (WAL mode enabled)
- **Scheduling**: GitHub Actions or local cron

## Core Logic: Knowledge Lifecycle

- **Scanning**: Rolling 7-day window (`_SCAN_DAYS = 7`). Iterates newest-first; breaks loop when `published.date() < (today - 7 days)`.
- **Deduplication**: `INSERT OR IGNORE` using `entry_id`.
- **TTL (Retention)**:
    - Default: 7 days. Extended: 30 days based on keywords (`ebpf`, `kernel`, `zero-copy`, `distributed`, `performance`).
    - Records are deleted when `expire_at < CURRENT_TIMESTAMP`.
- **Glossary & Annotation**:
    - Users register technical terms to the `glossary` table via `glossary.py`.
    - `viewer.py` scans summaries for registered terms/aliases (case-insensitive) and displays their definitions as footnoted annotations.
- **Read Tracking**: Papers move from `unread` to `read` upon display in `viewer.py`.

## Directory Structure
```text
.
├── src/
│   ├── main.py          # Entry point (orchestrates fetch & cleanup)
│   ├── database.py      # Schema, WAL init, CRUD (Papers & Glossary)
│   ├── fetcher.py       # arXiv client with date-sentinel logic
│   ├── models.py        # Pydantic models (Paper, GlossaryItem)
│   ├── viewer.py        # UI: unread papers + glossary annotations
│   └── glossary.py      # CLI: manage terms (add, update, list, delete)
├── data/
│   └── archive.db       # SQLite DB (gitignored)
├── configs/
│   └── keywords.yaml    # TTL-extension keywords
└── CLAUDE.md            # This file
```

## SQLite Schema
```sql
CREATE TABLE IF NOT EXISTS papers (
    entry_id     TEXT PRIMARY KEY,   -- Canonical arXiv abs URL
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL,
    authors      TEXT NOT NULL,      -- Comma-separated
    categories   TEXT NOT NULL,      -- Comma-separated
    pdf_url      TEXT NOT NULL,      -- Direct PDF link
    submitted_at TEXT NOT NULL,      -- ISO8601 UTC (from arXiv)
    fetched_at   TEXT NOT NULL,      -- ISO8601 UTC (insertion time)
    expire_at    TEXT NOT NULL,      -- ISO8601 UTC (fetched_at + TTL)
    status       TEXT NOT NULL DEFAULT 'unread'  -- 'unread' | 'read'
);

CREATE TABLE IF NOT EXISTS glossary (
    term          TEXT PRIMARY KEY,
    definition    TEXT NOT NULL,
    aliases       TEXT NOT NULL DEFAULT '',   -- Comma-separated synonyms
    first_seen_id TEXT,                       -- FK to papers.entry_id
    updated_at    TEXT NOT NULL,
    FOREIGN KEY (first_seen_id) REFERENCES papers (entry_id) ON DELETE SET NULL
);
```
*Auto-migration: `init_db()` applies `ALTER TABLE ADD COLUMN` for `pdf_url` and `status` if missing.*

## database.py: Public Functions

| Function | Signature | Description |
|---|---|---|
| `init_db()` | `() -> None` | Create tables + run migrations |
| `insert_papers(list[Paper])` | `-> tuple[int, int]` | Bulk INSERT OR IGNORE; returns `(inserted, skipped)` |
| `get_unread_papers(days, limit)` | `-> list[sqlite3.Row]` | Fetch unread papers within window |
| `get_unread_counts_by_date(days)` | `-> list[sqlite3.Row]` | Per-day unread counts, newest first |
| `mark_as_read(list[str])` | `-> None` | Batch UPDATE status → `'read'` |
| `delete_expired()` | `() -> int` | DELETE where `expire_at` is past; returns count |
| `upsert_glossary(GlossaryItem)` | `-> None` | INSERT or full UPDATE; **preserves** existing `first_seen_id` |
| `update_glossary(term, **fields)` | `-> bool` | Partial UPDATE (`definition`, `aliases`); fails if term missing |
| `get_all_glossary()` | `() -> list[GlossaryItem]` | SELECT all glossary rows ordered by term |
| `delete_glossary_term(str)` | `-> bool` | DELETE by term; returns success |

## viewer.py: Subcommands

| Subcommand | Args | Description |
|---|---|---|
| `show` (default) | `[--days 7] [--limit 10] [--all]` | Display papers; marks displayed unread papers as read |
| `unread` | `[--days 7]` | Per-day bar chart of unread paper counts |

### show: UI Elements
| UI Element | Rich Style | Note |
|---|---|---|
| **Title** | `bold blue` | |
| **Categories** | `bold green` | |
| **TTL Keywords** | `bold yellow` | Triggers 30-day TTL |
| **Glossary Term** | `bold reverse` | Highlighted in summary text (case-insensitive) |
| **Annotations** | `italic dim` | `* TERM: definition` shown as footnotes |

- **Filtering**: Default shows `unread` only. `--all` shows both `read`/`unread`.
- **Glossary Priority**: Match **longest terms first** to avoid partial matching.

### unread: Output Format
```
──────── Unread papers — last 7 days (total: 47) ────────
  2026-03-30    18  ██████████████████
  2026-03-29    15  ███████████████
  2026-03-28    14  ██████████████
─────────────────────────────────────────────────────────
```
Bar length is proportional to count. Does **not** mark papers as read.

## glossary.py: Subcommands

| Command | Required | Optional | Behavior |
|---|---|---|---|
| **`add <term>`** | `--def` | `--aliases` | `upsert_glossary`: Insert or full replace (preserves `first_seen_id`) |
| **`update <term>`** | - | `--def`, `--aliases` | `update_glossary`: Partial update; fails if term doesn't exist |
| **`list [query]`** | - | - | Partial match on `term` or `definition` |
| **`delete <term>`** | - | - | `delete_glossary_term`: Remove entry |

## Implementation Guidelines (Strict)
1. **API Politeness**: 3-second delay between arXiv API requests (`delay_seconds=3`).
2. **Timezone**: Use `datetime.now(timezone.utc)` for all local timestamps.
3. **Database Performance**: `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=NORMAL`.
4. **Data Integrity**: Pydantic validation for all models before DB insertion.

## Commands
- **Setup**: `pip install arxiv pydantic rich pyyaml`
- **Ingest**: `python src/main.py`
- **Read**: `python src/viewer.py show [--days 7] [--limit 10] [--all]`
- **Unread summary**: `python src/viewer.py unread [--days 7]`
- **Maintenance**: `python src/main.py --cleanup-only`
- **Glossary Add**: `python src/glossary.py add "VLA" --def "Vision-Language-Action model"`
- **Glossary Update**: `python src/glossary.py update "VLA" --aliases "VLA model, Vision-Language-Action"`
- **Glossary List**: `python src/glossary.py list`
- **Glossary Delete**: `python src/glossary.py delete "VLA"`