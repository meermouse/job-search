import logging
import re
from jobspy import scrape_jobs

logger = logging.getLogger(__name__)

# Matches £60,000 or £60,000–£80,000 or £60k–£80k style salary mentions
_SALARY_RE = re.compile(r'£([\d,]+)k?\s*(?:[-–]\s*£([\d,]+)k?)?', re.IGNORECASE)


def _parse_amount(raw: str, has_k: bool) -> int | None:
    try:
        val = int(raw.replace(',', ''))
        return val * 1000 if has_k else val
    except (ValueError, TypeError):
        return None


def _find_salary_in_text(text: str) -> tuple[int | None, int | None]:
    """Return (min, max) salary extracted from free text; both None if not found."""
    for m in _SALARY_RE.finditer(text):
        full = m.group(0)
        has_k1 = full[len(m.group(1)) + 1:].lower().startswith('k')
        min_val = _parse_amount(m.group(1), has_k1)
        if min_val and min_val < 1000:
            continue  # skip obviously-wrong matches like £30
        max_val = None
        if m.group(2):
            rest = full[m.start(2) - m.start():]
            has_k2 = rest.lower().rstrip().endswith('k')
            max_val = _parse_amount(m.group(2), has_k2)
        return min_val, max_val
    return None, None


def _salary_info(row) -> tuple[str, int | None]:
    """Return (display string, effective min salary or None)."""
    min_a = row.get("min_amount")
    max_a = row.get("max_amount")
    if min_a and max_a:
        interval = row.get("interval") or ""
        return f"£{int(min_a):,}–£{int(max_a):,} {interval}".strip(), int(min_a)
    if min_a:
        interval = row.get("interval") or ""
        return f"From £{int(min_a):,} {interval}".strip(), int(min_a)
    # Fallback: try to extract from description
    desc = str(row.get("description") or "")
    min_d, max_d = _find_salary_in_text(desc)
    if min_d:
        if max_d and max_d != min_d:
            return f"£{min_d:,}–£{max_d:,}", min_d
        return f"£{min_d:,}", min_d
    return "Not stated", None


def search(queries: list[str], location: str, min_salary: int, distance: int = 50) -> list[dict]:
    jobs = []
    for query in queries:
        try:
            df = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=query,
                location=location,
                distance=distance,
                results_wanted=50,
                country_indeed="UK",
            )
            for _, row in df.iterrows():
                min_a = row.get("min_amount")
                if min_a and min_a < min_salary:
                    continue
                salary_display, effective_min = _salary_info(row)
                # Filter on description-extracted salary when structured data is absent
                if not min_a and effective_min is not None and effective_min < min_salary:
                    continue
                jobs.append({
                    "title": str(row.get("title") or ""),
                    "company": str(row.get("company") or ""),
                    "location": str(row.get("location") or ""),
                    "salary": salary_display,
                    "description": str(row.get("description") or "")[:500],
                    "url": str(row.get("job_url") or ""),
                    "source": str(row.get("site") or "").capitalize(),
                })
        except Exception as exc:
            logger.warning("JobSpy search failed for query '%s': %s", query, exc)
    return jobs
