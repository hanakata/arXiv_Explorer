"""viewer.py — Display papers from the local SQLite DB using Rich."""

import argparse
import re
import sqlite3
from pathlib import Path

from rich.console import Console
from rich.rule import Rule
from rich.text import Text

from database import DB_PATH, get_all_glossary, get_connection, get_unread_counts_by_date, get_unread_papers, mark_as_read
from fetcher import _EXTENDED_KEYWORDS  # reuse the same keyword set
from models import GlossaryItem

console = Console()

_KEYWORD_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(kw) for kw in sorted(_EXTENDED_KEYWORDS)) + r")\b",
    re.IGNORECASE,
)


def _build_glossary_pattern(glossary: list[GlossaryItem]) -> re.Pattern | None:
    """Build a combined regex for all terms and their aliases."""
    tokens: list[str] = []
    for item in glossary:
        tokens.append(item.term)
        if item.aliases:
            tokens.extend(a.strip() for a in item.aliases.split(",") if a.strip())
    if not tokens:
        return None
    return re.compile(
        r"\b(" + "|".join(re.escape(t) for t in sorted(tokens, key=len, reverse=True)) + r")\b",
        re.IGNORECASE,
    )


def _glossary_lookup(token: str, glossary: list[GlossaryItem]) -> str:
    """Return definition for a matched token (checks term and aliases)."""
    lower = token.lower()
    for item in glossary:
        if item.term.lower() == lower:
            return item.definition
        if item.aliases:
            for alias in item.aliases.split(","):
                if alias.strip().lower() == lower:
                    return item.definition
    return ""


def _render_summary(raw: str, glossary: list[GlossaryItem]) -> tuple[Text, list[str]]:
    """Render summary with keyword (yellow) and glossary term (bold reverse) highlights.

    Returns the rendered Text and a list of 'TERM: definition' annotation strings
    for terms found in this summary.
    """
    glossary_pattern = _build_glossary_pattern(glossary)

    # Collect all match spans with their styles, sorted by position.
    spans: list[tuple[int, int, str, str]] = []  # (start, end, matched_text, style)

    for m in _KEYWORD_PATTERN.finditer(raw):
        spans.append((m.start(), m.end(), m.group(), "bold yellow"))

    if glossary_pattern:
        for m in glossary_pattern.finditer(raw):
            # Glossary takes precedence; skip if already covered by keyword span.
            if not any(s <= m.start() < e for s, e, _, _ in spans):
                spans.append((m.start(), m.end(), m.group(), "bold reverse"))

    spans.sort(key=lambda x: x[0])

    text = Text()
    last = 0
    found_terms: dict[str, str] = {}  # term -> definition (deduped)
    for start, end, matched, style in spans:
        text.append(raw[last:start])
        text.append(matched, style=style)
        last = end
        if style == "bold reverse":
            defn = _glossary_lookup(matched, glossary)
            if defn:
                found_terms[matched.upper()] = defn
    text.append(raw[last:])

    annotations = [f"{term}: {defn}" for term, defn in found_terms.items()]
    return text, annotations


def _fetch_all_rows(days: int, limit: int) -> list[sqlite3.Row]:
    sql = """
        SELECT entry_id, title, categories, pdf_url, submitted_at, summary, status
        FROM papers
        WHERE submitted_at >= datetime('now', ? || ' days')
        ORDER BY submitted_at DESC
        LIMIT ?
    """
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, (f"-{days}", limit)).fetchall()


def show(days: int = 7, limit: int = 10, all_papers: bool = False) -> None:
    if not DB_PATH.exists():
        console.print("[red]DB not found:[/red]", DB_PATH)
        return

    rows = _fetch_all_rows(days, limit) if all_papers else get_unread_papers(days, limit)

    glossary = get_all_glossary()

    label = f"last {days} days" + ("" if all_papers else " / unread")
    if not rows:
        console.print(f"[yellow]No papers found ({label}).[/yellow]")
        return

    console.print(Rule(f"arXiv CS papers — {label} ({len(rows)} hits)"))

    displayed_ids: list[str] = []
    for row in rows:
        # --- Title (blue) ---
        console.print(Text(row["title"], style="bold blue"))

        # --- Categories (green) + date ---
        meta = Text()
        meta.append(row["categories"], style="bold green")
        meta.append(f"  |  {row['submitted_at'][:10]}", style="dim")
        console.print(meta)

        # --- PDF link ---
        if row["pdf_url"]:
            console.print(Text(row["pdf_url"], style="cyan underline"))

        # --- Summary with keyword + glossary highlights ---
        summary_text, annotations = _render_summary(row["summary"], glossary)
        console.print(summary_text)

        # --- Glossary annotations (italic dim) ---
        for note in annotations:
            console.print(Text(f"  * {note}", style="italic dim"))

        console.print(Rule(style="dim"))
        if row["status"] == "unread":
            displayed_ids.append(row["entry_id"])

    mark_as_read(displayed_ids)
    if displayed_ids:
        console.print(f"[dim]Marked {len(displayed_ids)} paper(s) as read.[/dim]")


def cmd_unread(args: argparse.Namespace) -> None:
    if not DB_PATH.exists():
        console.print("[red]DB not found:[/red]", DB_PATH)
        return

    rows = get_unread_counts_by_date(args.days)
    if not rows:
        console.print(f"[yellow]No unread papers in the last {args.days} days.[/yellow]")
        return

    total = sum(r["count"] for r in rows)
    console.print(Rule(f"Unread papers — last {args.days} days (total: {total})"))

    for row in rows:
        bar = "█" * row["count"]
        line = Text()
        line.append(f"  {row['date']}  ", style="dim")
        line.append(f"{row['count']:4d}  ", style="bold white")
        line.append(bar, style="bold cyan")
        console.print(line)

    console.print(Rule(style="dim"))


def main() -> None:
    parser = argparse.ArgumentParser(description="View arXiv papers from local DB")
    sub = parser.add_subparsers(dest="command")

    p_show = sub.add_parser("show", help="Display unread papers (default)")
    p_show.add_argument("--days",  type=int, default=7,  help="Papers from last N days (default: 7)")
    p_show.add_argument("--limit", type=int, default=10, help="Max papers to display (default: 10)")
    p_show.add_argument("--all",   action="store_true",  help="Include already-read papers")

    p_unread = sub.add_parser("unread", help="Show per-day unread paper counts")
    p_unread.add_argument("--days", type=int, default=7, help="Window in days (default: 7)")

    args = parser.parse_args()

    if args.command == "unread":
        cmd_unread(args)
    else:
        # default: show (handles both explicit 'show' and no subcommand)
        days  = getattr(args, "days",  7)
        limit = getattr(args, "limit", 10)
        all_p = getattr(args, "all",   False)
        show(days=days, limit=limit, all_papers=all_p)


if __name__ == "__main__":
    main()
