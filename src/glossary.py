"""glossary.py — CLI for managing the personal technical glossary."""

import argparse
import sys
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from database import delete_glossary_term, get_all_glossary, init_db, update_glossary, upsert_glossary
from models import GlossaryItem

console = Console()


def cmd_add(args: argparse.Namespace) -> None:
    init_db()
    item = GlossaryItem(
        term=args.term,
        definition=args.definition,
        aliases=args.aliases or "",
        updated_at=datetime.now(timezone.utc),
    )
    upsert_glossary(item)
    console.print(f"[green]Saved:[/green] [bold]{item.term}[/bold] — {item.definition}")


def cmd_list(args: argparse.Namespace) -> None:
    init_db()
    items = get_all_glossary()
    if not items:
        console.print("[yellow]No glossary terms registered.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Term", style="bold cyan", no_wrap=True)
    table.add_column("Definition")
    table.add_column("Aliases", style="dim")
    table.add_column("Updated", style="dim", no_wrap=True)

    query = (args.query or "").lower()
    for item in items:
        if query and query not in item.term.lower() and query not in item.definition.lower():
            continue
        table.add_row(
            item.term,
            item.definition,
            item.aliases,
            item.updated_at.isoformat()[:10],
        )

    console.print(table)


def cmd_update(args: argparse.Namespace) -> None:
    init_db()
    fields = {}
    if args.definition:
        fields["definition"] = args.definition
    if args.aliases is not None:
        fields["aliases"] = args.aliases

    if not fields:
        console.print("[yellow]Nothing to update. Specify --def and/or --aliases.[/yellow]")
        return

    if update_glossary(args.term, **fields):
        console.print(f"[green]Updated:[/green] [bold]{args.term}[/bold]")
    else:
        console.print(f"[yellow]Term not found:[/yellow] {args.term}")


def cmd_delete(args: argparse.Namespace) -> None:
    init_db()
    if delete_glossary_term(args.term):
        console.print(f"[red]Deleted:[/red] {args.term}")
    else:
        console.print(f"[yellow]Term not found:[/yellow] {args.term}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage arXiv Explorer glossary")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add or update a term")
    p_add.add_argument("term", help="Technical term (e.g. SFT)")
    p_add.add_argument("--def", dest="definition", required=True, help="Definition")
    p_add.add_argument("--aliases", help="Comma-separated synonyms (e.g. 'fine-tuning,supervised ft')")

    p_list = sub.add_parser("list", help="List all terms")
    p_list.add_argument("query", nargs="?", help="Filter by term or definition")

    p_upd = sub.add_parser("update", help="Update definition or aliases of an existing term")
    p_upd.add_argument("term", help="Term to update (primary key)")
    p_upd.add_argument("--def", dest="definition", help="New definition")
    p_upd.add_argument("--aliases", help="New aliases (replaces existing)")

    p_del = sub.add_parser("delete", help="Remove a term")
    p_del.add_argument("term", help="Term to delete")

    args = parser.parse_args()
    {"add": cmd_add, "list": cmd_list, "update": cmd_update, "delete": cmd_delete}[args.command](args)


if __name__ == "__main__":
    main()
