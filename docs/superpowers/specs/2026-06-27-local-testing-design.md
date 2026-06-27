# Local Testing Mode Design

**Date:** 2026-06-27
**Status:** Approved

## Problem

The workflow runs entirely on GitHub Actions and calls three external services:
- Anthropic Claude API (query generation, job scoring)
- Job board APIs (Reed, NHS Jobs, LinkedIn/Indeed via jobspy)
- SMTP (email delivery)

When diagnosing deployment issues locally, there is no way to run the pipeline without incurring API calls, rate limits, and costs. This makes local iteration slow and error-prone.

## Goal

Add a local test mode that runs the full pipeline end-to-end without calling any external APIs, writing the email output to a local HTML file instead of sending it.

## Design

### Approach: Separate entry point, zero production code contamination

Production modules (`main.py`, `queries.py`, `scorer.py`, `search_api/fetcher.py`, `email.py`) are **not modified**. All test wiring lives in two new files:

```
src/job_search_email/
  main.py          ← unchanged
  local_run.py     ← NEW: local test orchestrator
  fixtures.py      ← NEW: hardcoded test data
```

A second script entry point is registered in `pyproject.toml`:

```toml
[project.scripts]
job-search-email       = "job_search_email.main:main"
job-search-email-local = "job_search_email.local_run:main"
```

Invocation: `job-search-email-local`

### Pipeline substitution

`local_run.py` re-uses all pure-logic production functions and replaces only the API-calling steps:

| Step | Production code | Local substitute |
|------|----------------|-----------------|
| Load profile | `load_profile()` | same — no API |
| Build search plan | `generate_queries()` → Claude | `fixture_queries()` |
| Fetch jobs | `fetch_all_jobs()` → Reed / NHS / jobspy | `fixture_jobs()` |
| Filter jobs | `filter_jobs()` | same — pure logic |
| Score jobs | `score_jobs()` → Claude | `fixture_scores(filtered)` |
| Email | `send_email()` → SMTP | writes `email_preview.html` |
| Write JSON artefacts | `write_search_plan()`, `write_filtered_results()`, `write_scored_results()` | same — useful for inspection |

### `fixtures.py`

Provides three functions:

**`fixture_queries() -> list[str]`**
Returns 8 hardcoded query strings in the same format that `queries.py` would produce (short keyword phrases).

**`fixture_jobs() -> list[JobListing]`**
Returns ~5 `JobListing` instances covering edge cases the pipeline must handle:
1. Strong match — senior software engineering role, good salary, known sponsor
2. Below salary threshold — otherwise suitable but salary below `min_salary`
3. Wrong employment type — contract role (should be filtered)
4. NHS job — no description (scorer sees title/salary only)
5. Non-sponsor company — should be rejected by sponsor filter

**`fixture_scores(results: list[FilteredResult]) -> list[ScoredResult]`**
Wraps already-filtered results with hardcoded `JobAnalysis` objects (score 1–10, verdict, matched skills, missing essentials). Does not call Claude.

### Email output

Instead of `send_email()`, `local_run.py` calls `build_email_html()` and writes the result to `email_preview.html` in the working directory. This file can be opened in any browser to inspect the rendered output.

## What is not in scope

- A GitHub Actions workflow for local testing (act, etc.)
- Pytest unit tests (separate concern)
- Partial stubs (e.g. real job fetch + fake scoring) — all-or-nothing test mode only
- Persisting fixture data to disk as JSON files
