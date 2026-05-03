import logging
from jobspy import scrape_jobs

logger = logging.getLogger(__name__)


def _salary_str(row) -> str:
    min_a = row.get("min_amount")
    max_a = row.get("max_amount")
    if min_a and max_a:
        interval = row.get("interval") or ""
        return f"£{int(min_a):,}–£{int(max_a):,} {interval}".strip()
    return ""


def search(queries: list[str], location: str, min_salary: int) -> list[dict]:
    jobs = []
    for query in queries:
        try:
            df = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=query,
                location=location,
                distance=100,
                results_wanted=50,
                country_indeed="UK",
            )
            for _, row in df.iterrows():
                min_a = row.get("min_amount")
                if min_a and min_a < min_salary:
                    continue
                jobs.append({
                    "title": str(row.get("title") or ""),
                    "company": str(row.get("company") or ""),
                    "location": str(row.get("location") or ""),
                    "salary": _salary_str(row),
                    "description": str(row.get("description") or "")[:500],
                    "url": str(row.get("job_url") or ""),
                    "source": str(row.get("site") or "").capitalize(),
                })
        except Exception as exc:
            logger.warning("JobSpy search failed for query '%s': %s", query, exc)
    return jobs
