# Job Filter Design

**Date:** 2026-06-27
**Branch:** feature/FE-003-clinical-job-type-filtering
**Step:** 3 of the Job Search Email Filter pipeline

## Overview

After jobs are fetched and deduplicated, a filter step removes unsuitable results before they reach the email. Two filters run in sequence: employment type and role suitability. Raw results are preserved; filtered results are written to a separate file.

---

## Data Model

A new `FilteredResult` dataclass wraps `JobListing` with filter metadata. `JobListing` is unchanged.

```python
@dataclass
class FilteredResult:
    job: JobListing
    flags: list[str]          # ["employment_type_unknown"]
    rejected: bool
    reject_reason: str | None  # "employment type: contract" / "unsuitable role: nurse"
```

Both kept and rejected jobs are represented as `FilteredResult`, making the output file uniform.

---

## Filter 1: Employment Type

Goal: reject contract/temporary/part-time roles; flag roles where type cannot be determined.

### Stage 1 — Structured field

Check `job.employment_type` (populated by Reed flags and jobspy enum):

| Value | Decision |
|-------|----------|
| `contract`, `fixed-term`, `temporary`, `locum`, `bank`, `agency`, `casual`, `zero-hours`, `part-time`, `internship` | Reject: `"employment type: {value}"` |
| `full-time`, `permanent` | Pass |
| `None` / empty / unrecognised | Go to Stage 2 |

### Stage 2 — Description text scan

Only runs when Stage 1 yields no decision. Scans the first 500 characters of title + description using multi-word phrases that unambiguously signal employment type. The word "contract" alone is **never** matched — only as part of an employment-relationship phrase.

Reject patterns (regex, case-insensitive):

```
fixed.?term contract
fixed.?term post
fixed.?term appointment
temporary contract
temporary post
temporary role
on a contract basis
contract basis
maternity cover
parental leave cover
\d+.month contract
\d+.month fixed
zero.hours
bank staff
locum post
```

- Match found → Reject: `"description contains contract indicators"`
- No match → **Keep with flag** `"employment_type_unknown"`

---

## Filter 2: Role Suitability

Goal: reject clinical and otherwise unsuitable roles using a profile-driven keyword list applied to job titles.

### Plan-time: exclusion list generation (`exclusions.py`)

`get_exclusions(profile)` is enhanced with a Claude Haiku API call that generates additional unsuitable role title terms beyond the hardcoded `STANDARD_CLINICAL_TERMS`.

Inputs to Claude:
- `target_roles`, `not_open_to`, `current_role`, `industry`, `skills`

Output: flat list of ~20–30 role title keywords/phrases clearly unsuitable for this candidate, with emphasis on NHS clinical titles that a non-clinical NHS manager's searches might surface (e.g. `"ward manager"`, `"clinical lead"`, `"staff nurse"`, `"consultant physician"`).

The final `exclusions["roles"]` list = `STANDARD_CLINICAL_TERMS` + `profile.not_open_to` + Claude-generated terms, deduplicated and sorted.

This call is protected by the existing plan cache — it only runs when the profile fingerprint changes.

### Filter-time: title matching (`filter.py`)

- Check job title (case-insensitive substring match) against `plan.exclusions["roles"]`
- Title only — description-level role scanning is too noisy
- Match found → Reject: `"unsuitable role: {matched_term}"`
- No match → Pass (no flag; an unmatched title is treated as suitable)

---

## File Output

| File | Contents |
|------|----------|
| `job_results.json` | Raw fetched jobs, unchanged |
| `job_results_filtered.json` | Structured output: summary + kept + rejected |

Shape of `job_results_filtered.json`:

```json
{
  "summary": {
    "total": 120,
    "kept": 45,
    "rejected": 60,
    "flagged": 15
  },
  "kept": [
    {
      "job": { "...JobListing fields..." },
      "flags": ["employment_type_unknown"],
      "rejected": false,
      "reject_reason": null
    }
  ],
  "rejected": [
    {
      "job": { "...JobListing fields..." },
      "flags": [],
      "rejected": true,
      "reject_reason": "employment type: contract"
    }
  ]
}
```

---

## Module Changes

### New: `src/job_search_email/filter.py`

```
filter_jobs(jobs, plan, profile) -> list[FilteredResult]
_check_employment_type(job) -> FilteredResult | None
_check_role_suitability(job, exclusion_roles) -> FilteredResult | None
```

Filters run in order: employment type first, then role suitability. A job rejected by the first filter is not passed to the second.

### Modified: `src/job_search_email/models.py`

Add `FilteredResult` dataclass.

### Modified: `src/job_search_email/exclusions.py`

Add `_generate_exclusion_roles(profile) -> list[str]` (Claude Haiku call). Merge result into `get_exclusions()` return value.

### Modified: `src/job_search_email/main.py`

After `fetch_all_jobs`:
1. Call `filter_jobs(jobs, plan, profile)`
2. Write `job_results.json` (raw, as before)
3. Write `job_results_filtered.json` (new structured output)
4. Print summary: `- filtered: 45 kept, 60 rejected (15 flagged unknown employment type)`

### Unchanged

`SearchPlan`, `queries.py`, `nhs_rules.py`, `evaluator_notes.py`, all three searchers, `dedup.py`.

---

## Notes

- The `employment_type` field on `JobListing` is never populated by NHS Jobs (title/salary only). NHS jobs will almost always reach Stage 2 of the employment type filter and be flagged `employment_type_unknown` unless contract phrases appear in the title.
- The profile's `employment_type: [full-time]` field informs the reject/pass split conceptually. If this field changes to include `["full-time", "part-time"]`, the `REJECT_TYPES` constant in `filter.py` should be updated accordingly.
- The Claude call in `exclusions.py` uses Haiku (same model as query generation) with a small token budget (~256 tokens output).
