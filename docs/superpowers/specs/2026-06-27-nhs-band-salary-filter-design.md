# NHS Band Salary Filter — Design

**Date:** 2026-06-27
**Branch:** feature/FE-004-NHS-band-rules
**Project:** job-search-email

---

## Problem

NHS job listings advertise pay by Agenda for Change (AfC) band rather than a raw salary figure. The existing filter pipeline has no way to translate a band into a salary for comparison against the user's `min_salary` threshold. As a result, a Band 7 role (£43,742/yr nationally) passes the filter unchanged even when `min_salary` is £60,000.

---

## Goal

Reject NHS-banded job listings whose estimated salary — derived from the band and location — falls below `profile.min_salary`. London roles receive a 20% uplift before comparison.

---

## Detection: Is this an NHS-banded job?

A job is treated as NHS-banded if **either** of the following is true:

1. `job.source == "nhs_jobs"`
2. The job `title` or first 500 characters of `description` match the regex `Band\s*\d+[a-dA-D]?` (e.g. "Band 8a", "AfC Band 7", "Band 9")

If neither fires, this filter is a no-op for that job.

---

## Translation: Band → Salary

Band salaries are looked up from `nhs_rules["band_salary_map"]` (already defined in `nhs_rules.py`):

| Band   | Base salary |
|--------|-------------|
| Band 7 | £43,742     |
| Band 8a| £53,755     |
| Band 8b| £62,215     |
| Band 8c| £72,293     |
| Band 8d| £83,571     |
| Band 9 | £96,376     |

**Out-of-map bands** (Bands 1–6, or unrecognised values): estimated salary is treated as £0, guaranteeing rejection.

**London weighting:** if `job.location` contains `"London"` (case-insensitive), the estimated salary is multiplied by **1.20** (NHS High Cost Area Supplement). A single 20% figure is used for now; inner/outer London split can be added later.

**Threshold:** the estimated salary is compared against `profile.min_salary`. If below → reject.

---

## Rejection output

```
rejected=True
reject_reason="nhs band salary below threshold: Band 7 (~£43,742)"
```

For London-weighted jobs, the reason includes the boosted figure:

```
reject_reason="nhs band salary below threshold: Band 7 London (~£52,490)"
```

---

## Integration

New private function added to `src/job_search_email/filter.py`:

```python
def _check_nhs_band_salary(
    job: JobListing,
    nhs_rules: dict,
    min_salary: int,
) -> FilteredResult | None:
```

Returns `None` if the job is not NHS-banded (no-op). Returns a rejected `FilteredResult` if the band salary is below threshold. The `nhs_rules` dict and `min_salary` are already available in `filter_jobs` via `SearchPlan` and `Profile` respectively.

Filter order in `filter_jobs`:

1. `_check_employment_type` — reject if contract/temp
2. `_check_role_suitability` — reject if clinical title
3. `_check_nhs_band_salary` — reject if band salary < min_salary  ← new
4. Keep

---

## Out of scope

- Splitting London weighting into inner/outer/fringe zones
- Using the listing's advertised `salary_min` as an alternative to the band estimate
- Changing `nhs_rules["london_remote_floor"]` (still present in the plan but not used by this filter)
- Guarding against false-positive band detection in non-NHS job descriptions that mention NHS bands colloquially (e.g. "equivalent to Band 8a") — acceptable risk at this stage

---

## Files changed

| File | Change |
|------|--------|
| `src/job_search_email/filter.py` | Add `_check_nhs_band_salary`, call it in `filter_jobs` |
| `src/job_search_email/nhs_rules.py` | No change — `band_salary_map` already correct |
| `src/job_search_email/tests/test_nhs_band_filter.py` | New test file |
