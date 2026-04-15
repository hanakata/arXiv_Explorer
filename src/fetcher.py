import logging
import time
from datetime import datetime, timedelta, timezone

import arxiv

from models import Paper

logger = logging.getLogger(__name__)

# arXiv API politeness rule
_REQUEST_INTERVAL_SEC = 3

# TTL settings
_DEFAULT_TTL_DAYS = 7
_EXTENDED_TTL_DAYS = 30
_EXTENDED_KEYWORDS = {"performance", "kernel", "ebpf", "zero-copy", "distributed"}

_MAX_RESULTS_PER_QUERY = 2000  # generous upper bound; loop exits early via date sentinel


def _ttl_days(paper_text: str) -> int:
    lower = paper_text.lower()
    if any(kw in lower for kw in _EXTENDED_KEYWORDS):
        return _EXTENDED_TTL_DAYS
    return _DEFAULT_TTL_DAYS


_SCAN_DAYS = 7  # rolling window to catch delayed arXiv indexing


def fetch_recent_cs_papers() -> list[Paper]:
    """Fetch cs.* papers published within the last SCAN_DAYS days (UTC).

    Iterates newest-first and stops as soon as a result falls outside the
    window.  INSERT OR IGNORE in the DB layer handles deduplication, so
    re-scanning already-stored papers is safe.

    Respects the 3-second inter-request delay required by arXiv ToC.
    """
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    cutoff = today - timedelta(days=_SCAN_DAYS)  # stop when published < cutoff

    query = "cat:cs.OS OR cat:cs.CR OR cat:cs.DC"
    logger.info("Query: %s  |  window=%s..%s", query, cutoff, today)

    client = arxiv.Client(
        page_size=500,
        delay_seconds=_REQUEST_INTERVAL_SEC,
        num_retries=3,
    )
    search = arxiv.Search(
        query=query,
        max_results=_MAX_RESULTS_PER_QUERY,
        sort_by=arxiv.SortCriterion.SubmittedDate,
        sort_order=arxiv.SortOrder.Descending,
    )

    papers: list[Paper] = []
    fetched_at = datetime.now(timezone.utc)

    for result in client.results(search):
        pub_date = result.published.astimezone(timezone.utc).date()

        if pub_date < cutoff:
            logger.info("Reached cutoff date (%s), stopping early.", pub_date)
            break

        combined_text = result.title + " " + result.summary
        ttl = _ttl_days(combined_text)
        expire_at = fetched_at + timedelta(days=ttl)

        papers.append(Paper(
            entry_id=result.entry_id,
            title=result.title,
            summary=result.summary,
            authors=", ".join(a.name for a in result.authors),
            categories=", ".join(result.categories),
            pdf_url=result.pdf_url,
            submitted_at=result.published.astimezone(timezone.utc),
            fetched_at=fetched_at,
            expire_at=expire_at,
        ))

    logger.info("Scanned %d papers in window [%s, %s]", len(papers), cutoff, today)
    return papers
