import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator
from . import jobspy_searcher, reed, nhs_jobs

logger = logging.getLogger(__name__)


def search_all_streaming(
    queries: list[str],
    location: str,
    min_salary: int,
    distance: int = 50,
    platforms: dict[str, bool] | None = None,
) -> Generator[tuple[str, list[dict], str | None], None, None]:
    """Yields (platform_name, jobs, error_msg) as each platform's search completes."""
    all_searchers = {
        "LinkedIn + Indeed": jobspy_searcher.search,
        "Reed": reed.search,
        "NHS Jobs": nhs_jobs.search,
    }
    searchers = {
        name: fn for name, fn in all_searchers.items()
        if platforms is None or name in platforms
    }
    with ThreadPoolExecutor(max_workers=len(searchers)) as executor:
        futures = {
            executor.submit(fn, queries, location, min_salary, distance): name
            for name, fn in searchers.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                yield name, future.result(), None
            except Exception as exc:
                logger.warning("Platform '%s' search failed: %s", name, exc, exc_info=True)
                yield name, [], str(exc)
