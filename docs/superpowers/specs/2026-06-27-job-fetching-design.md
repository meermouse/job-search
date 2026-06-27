# Job Fetching Design

**Date:** 2026-06-27
**Branch:** feature/FE-002-job-fetching
**Repo:** job-search-email

## Goal

Take the 8 queries produced by step 2 (query generation), fan them out across three job sources, and return a single deduplicated flat list of `JobListing` objects ready for downstream scoring and filtering.

## Data Model

A `JobListing` dataclass is added to `models.py`:

| Field | Type | Notes |
|---|---|---|
| `title` | `str` | |
| `company` | `str` | |
| `location` | `str` | |
| `salary_min` | `int \| None` | Parsed from structured fields or regex; `None` if unknown |
| `description` | `str` | Empty string for NHS Jobs (no description available from scraper) |
| `url` | `str` | |
| `source` | `str` | `"linkedin"`, `"indeed"`, `"reed"`, `"nhs"` |
| `employment_type` | `str \| None` | e.g. `"full-time"`, `"contract"`; `None` for NHS Jobs |

## File Structure

```
src/job_search_email/search_api/
  __init__.py          (empty — marks package)
  jobspy_searcher.py   search(query, profile) -> list[JobListing]
  reed.py              search(query, profile) -> list[JobListing]
  nhs_jobs.py          search(query, profile) -> list[JobListing]
  dedup.py             deduplicate(jobs) -> list[JobListing]
  fetcher.py           fetch_all_jobs(plan, profile) -> list[JobListing]
```

Each searcher exposes a single `search(query: str, profile: Profile) -> list[JobListing]` function. All API-specific logic (auth, request shaping, response parsing, salary extraction) stays inside its file. No cross-file concerns.

## Sources

### 1. LinkedIn + Indeed — `jobspy_searcher.py`
Uses `python-jobspy`. Parameters: `search_term=query`, `location=profile.location`, `distance=50` (fixed constant — `Profile` has no distance field), `results_wanted=50`, `country_indeed="UK"`. Salary filtering is client-side: use `min_amount` from structured fields first, then regex fallback (`£60,000` / `£60k` patterns) on description text. Emits two `source` values — `"linkedin"` and `"indeed"` — depending on which platform each result came from.

### 2. Reed API — `reed.py`
REST call to `reed.co.uk/api/1.0/search`. Parameters: `keywords=query`, `locationName=profile.location`, `distancefromLocation=50`, `minimumSalary=profile.min_salary`, `resultsToTake=100`. Salary filtering is server-side via `minimumSalary`. API key read from `REED_API_KEY` env var.

### 3. NHS Jobs — `nhs_jobs.py`
Scrapes `jobs.nhs.uk/candidate/search/results` with no auth. Parameters: `keyword=query`, `location=profile.location`, `distance=50`, `language="en"`. Salary filtering is client-side by parsing the first `£` figure from the salary text on each result card. `description` is always returned as `""`.

## Orchestration — `fetcher.py`

`fetch_all_jobs(plan: SearchPlan, profile: Profile) -> list[JobListing]`:

1. Build 24 tasks: `(searcher.search, query)` for each of the 3 searchers × 8 queries.
2. Submit all tasks to `ThreadPoolExecutor`.
3. Collect results: catch exceptions per-task, log to stderr, treat failures as empty lists.
4. Concatenate all results into one flat list.
5. Pass to `deduplicate()` and return.

## Deduplication — `dedup.py`

`deduplicate(jobs: list[JobListing]) -> list[JobListing]`:

Keyed on `(title.lower().strip(), company.lower().strip())`. First occurrence wins; subsequent duplicates are discarded. URL-based dedup is not used since the same job has different URLs across sources.

## Integration with `main.py`

After the search plan is loaded or generated, `main.py` calls `fetch_all_jobs(plan, profile)` and writes the results to `job_results.json` in the working directory.

## Dependencies

New packages required:
- `python-jobspy` — LinkedIn + Indeed scraping
- `requests` — Reed API and NHS Jobs HTTP calls
- `beautifulsoup4` — NHS Jobs HTML parsing

Add to `pyproject.toml` `[project] dependencies`.

## Error Handling

- Per-task failures in `fetcher.py` are caught, logged to stderr, and treated as empty results — one bad source does not abort the run.
- Missing `REED_API_KEY` raises a clear `ValueError` at call time.
- Malformed API responses are caught in each searcher and raise with a descriptive message.
