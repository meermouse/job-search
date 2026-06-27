# Sponsor Filter Design

**Date:** 2026-06-27
**Feature:** FE-005 — Approved Sponsor List Filter
**Status:** Approved

## Overview

Filter jobs against the UK Government's approved sponsor register (`assets/sponsor_cache.csv`). Jobs from companies not on the list are rejected. NHS-source jobs auto-pass. Jobs where the company cannot be matched due to missing or ambiguous data are flagged but passed.

---

## Architecture

A new module `src/job_search_email/sponsor_filter.py` owns all sponsor logic (CSV loading, normalization, set construction). [filter.py](../../../../job-search-email/src/job_search_email/filter.py) gains a `_check_sponsor` function that uses the pre-built set. [main.py](../../../../job-search-email/src/job_search_email/main.py) loads the sponsor set once at startup.

No new dependencies are introduced.

---

## Sponsor Set Construction

### `load_sponsor_set(csv_path: Path) -> frozenset[str]`

Reads `assets/sponsor_cache.csv` (141,920 entries, one per non-blank row). For each `Organisation Name` value:

1. Strip leading/trailing whitespace
2. Normalize:
   - Lowercase
   - Remove `T/A …` and `t/a …` trading-as clauses (everything from `t/a` to end of string)
   - Strip legal suffixes at the end of the string: `ltd`, `limited`, `plc`, `llp`, `llc`, `co`, `corp`, `corporation`, `inc` (whole-word, allowing a trailing `.`)
   - Remove all punctuation (except hyphens within words)
   - Collapse whitespace
3. Add the full normalized name to the accumulator set
4. Add every **word-boundary prefix of 2+ words AND 8+ characters** — so `"bossmans retail abergavenny"` also contributes `"bossmans retail"` to the set

The result is a single `frozenset[str]`, constructed once at startup and reused for every job.

### Example

| CSV name | Normalized | Also adds prefix |
|---|---|---|
| `" Bossmans Retail Abergavenny Ltd"` | `"bossmans retail abergavenny"` | `"bossmans retail"` |
| `" F-Secure (UK) Limited"` | `"fsecure uk"` | — (2 words, 8 chars — qualifies, adds `"fsecure"` only if ≥8 chars) |
| `" NHS Foundation Trust"` | `"nhs foundation trust"` | `"nhs foundation"` |

---

## Per-Job Check

### `_check_sponsor(job: JobListing, sponsor_set: frozenset[str]) -> FilteredResult | None`

Added to [filter.py](../../../../job-search-email/src/job_search_email/filter.py) after `_check_nhs_band_salary`.

| Condition | Result |
|---|---|
| `job.source == "nhs"` | `None` — pass (auto-approve, no check needed) |
| `job.company` is empty or None | `FilteredResult(flags=["sponsor_unknown_company"], rejected=False)` — flag and pass |
| Normalized company < 8 chars or < 2 words | `FilteredResult(flags=["sponsor_unknown_company"], rejected=False)` — too short to match reliably |
| Normalized company in `sponsor_set` | `None` — pass |
| Normalized company NOT in `sponsor_set` | `FilteredResult(rejected=True, reject_reason="company not on approved sponsor list")` |

The `"sponsor_unknown_company"` flag surfaces in the filtered results output so these jobs can be manually reviewed if needed.

---

## Integration Changes

### `filter.py`

- Import `is_approved` (or inline `_check_sponsor`) from `sponsor_filter`
- Add `_check_sponsor(job, sponsor_set)` function
- Update `filter_jobs` signature: `filter_jobs(jobs, plan, profile, sponsor_set: frozenset[str])`
- Insert sponsor check after NHS-band check in the pipeline

### `main.py`

- Add `SPONSOR_CACHE_PATH = ROOT / "assets" / "sponsor_cache.csv"`
- Load once before the filter step: `sponsor_set = load_sponsor_set(SPONSOR_CACHE_PATH)`
- Pass to `filter_jobs`

### Filter pipeline order (within `filter_jobs`)

1. Employment type check
2. Role suitability check
3. NHS band salary check
4. **Sponsor check** ← new

---

## Data Notes

- The CSV uses blank lines between entries; the CSV reader handles this naturally (blank rows produce empty `Organisation Name` values, which are skipped)
- Leading spaces on company names in the CSV are stripped during normalization
- The `Route` column is not used — all routes (Skilled Worker, Ministers of Religion, etc.) are treated equally
- The CSV is read-only; no writes or caching of the parsed set is needed (load time is negligible for ~141K rows)

---

## Edge Cases

| Case | Handling |
|---|---|
| Recruitment agency listed as company | Likely won't match; flagged `sponsor_unknown_company` and passed for manual review |
| NHS trust posting on LinkedIn/Indeed | Expected to be in sponsor list; goes through normal check |
| Company name is `None` | Flagged and passed |
| Very short company name (< 8 chars normalized) | Flagged and passed (avoid false rejects on bad data) |
| Company has multiple `T/A` clauses | First `t/a` onwards is stripped, covers all cases |
