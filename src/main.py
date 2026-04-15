import argparse
import logging
import sys

import database
import fetcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def run_fetch() -> None:
    database.init_db()

    expired = database.delete_expired()
    logger.info("Cleanup: removed %d expired records", expired)

    papers = fetcher.fetch_recent_cs_papers()
    inserted, skipped = database.insert_papers(papers)

    logger.info(
        "Done — fetched=%d, inserted=%d, skipped(dup)=%d, expired_removed=%d",
        len(papers), inserted, skipped, expired,
    )


def run_cleanup_only() -> None:
    database.init_db()
    expired = database.delete_expired()
    logger.info("Cleanup-only: removed %d expired records", expired)


def main() -> None:
    parser = argparse.ArgumentParser(description="arXiv Explorer fetcher")
    parser.add_argument(
        "--cleanup-only",
        action="store_true",
        help="Only run TTL cleanup, skip fetching",
    )
    args = parser.parse_args()

    if args.cleanup_only:
        run_cleanup_only()
    else:
        run_fetch()


if __name__ == "__main__":
    main()
