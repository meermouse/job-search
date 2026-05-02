from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator
from . import jobspy_searcher, reed, nhs_jobs


def search_all_streaming(
    queries: list[str],
    location: str,
    min_salary: int,
) -> Generator[tuple[str, list[dict], str | None], None, None]:
    """Yields (platform_name, jobs, error_msg) as each platform's search completes."""
    searchers = {
        "LinkedIn + Indeed": jobspy_searcher.search,
        "Reed": reed.search,
        "NHS Jobs": nhs_jobs.search,
    }
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(fn, queries, location, min_salary): name
            for name, fn in searchers.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                yield name, future.result(), None
            except Exception as exc:
                yield name, [], str(exc)
