# NHS Band Salary Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject NHS-banded job listings whose band salary (with London weighting) falls below `profile.min_salary`.

**Architecture:** A new private function `_check_nhs_band_salary` is added to `filter.py`. It detects the NHS band via regex on the job title and description, translates it to a salary using the existing `band_salary_map`, applies a 20% London uplift when the job location contains "London", and rejects if the result is below `profile.min_salary`. The function is slotted into `filter_jobs` as the third check.

**Tech Stack:** Python 3.11+, pytest, existing `filter.py` / `models.py` / `nhs_rules.py`

## Global Constraints

- No new modules — all changes go into `src/job_search_email/filter.py` and `tests/test_filter.py`
- `nhs_rules.py` is not modified — `band_salary_map` is already correct
- London weighting is a flat 1.20 multiplier (hardcoded)
- Out-of-map bands (e.g. Band 1–6) produce an estimated salary of £0, guaranteeing rejection
- Reject reason format: `"nhs band salary below threshold: Band 7 (~£43,742)"` (non-London) or `"nhs band salary below threshold: Band 7 London (~£52,490)"` (London)
- Detection: regex `Band\s*\d+[a-dA-D]?` (case-insensitive) on `job.title` + first 500 chars of `job.description`, OR `job.source == "nhs_jobs"` (but salary check still requires a band string — if none found, no-op)
- Run tests with: `pytest tests/test_filter.py -v`

---

### Task 1: Implement `_check_nhs_band_salary`

**Files:**
- Modify: `src/job_search_email/filter.py`
- Modify: `tests/test_filter.py`

**Interfaces:**
- Produces: `_check_nhs_band_salary(job: JobListing, nhs_rules: dict[str, Any], min_salary: int) -> FilteredResult | None`
  - Returns `None` if no band is detected or band salary meets threshold
  - Returns `FilteredResult(job=job, flags=[], rejected=True, reject_reason=...)` if below threshold

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_filter.py`:

```python
from job_search_email.filter import _check_nhs_band_salary

_NHS_RULES = {
    "band_salary_map": {
        "Band 7":  43742,
        "Band 8a": 53755,
        "Band 8b": 62215,
        "Band 8c": 72293,
        "Band 8d": 83571,
        "Band 9":  96376,
    }
}


def test_nhs_band_non_nhs_source_no_band_returns_none():
    job = make_job(source="reed", title="Business Manager", description="Great senior role.")
    assert _check_nhs_band_salary(job, _NHS_RULES, 60000) is None


def test_nhs_band_7_below_threshold_rejected():
    job = make_job(title="Transformation Manager Band 7", source="nhs_jobs", location="Bristol")
    result = _check_nhs_band_salary(job, _NHS_RULES, 60000)
    assert result is not None
    assert result.rejected is True
    assert "Band 7" in result.reject_reason
    assert "43,742" in result.reject_reason


def test_nhs_band_8b_above_threshold_returns_none():
    job = make_job(title="Digital Lead Band 8b", source="nhs_jobs", location="Bristol")
    assert _check_nhs_band_salary(job, _NHS_RULES, 60000) is None


def test_nhs_band_7_london_below_threshold_rejected():
    # 43742 * 1.20 = 52490 < 60000 — still rejected
    job = make_job(title="Manager Band 7", source="nhs_jobs", location="London")
    result = _check_nhs_band_salary(job, _NHS_RULES, 60000)
    assert result is not None
    assert result.rejected is True
    assert "London" in result.reject_reason
    assert "52,490" in result.reject_reason


def test_nhs_band_8a_london_above_threshold_returns_none():
    # 53755 * 1.20 = 64506 >= 60000 — passes
    job = make_job(title="Manager Band 8a", source="nhs_jobs", location="Greater London")
    assert _check_nhs_band_salary(job, _NHS_RULES, 60000) is None


def test_nhs_band_5_out_of_map_rejected():
    job = make_job(title="Admin Band 5", source="nhs_jobs", location="Bristol")
    result = _check_nhs_band_salary(job, _NHS_RULES, 60000)
    assert result is not None
    assert result.rejected is True


def test_nhs_band_detected_in_description():
    job = make_job(source="reed", title="NHS Digital Manager", description="AfC Band 7 post in Bristol.")
    result = _check_nhs_band_salary(job, _NHS_RULES, 60000)
    assert result is not None
    assert result.rejected is True


def test_nhs_band_beyond_500_chars_not_detected():
    job = make_job(source="reed", title="Digital Manager", description=("A" * 500) + " Band 7 post.")
    assert _check_nhs_band_salary(job, _NHS_RULES, 60000) is None


def test_nhs_jobs_source_no_band_in_text_returns_none():
    job = make_job(source="nhs_jobs", title="Digital Transformation Lead", description="No pay grade stated.")
    assert _check_nhs_band_salary(job, _NHS_RULES, 60000) is None


def test_nhs_london_location_case_insensitive():
    # 53755 * 1.20 = 64506 >= 60000
    job = make_job(title="Manager Band 8a", source="nhs_jobs", location="LONDON")
    assert _check_nhs_band_salary(job, _NHS_RULES, 60000) is None


def test_nhs_band_reject_reason_non_london_format():
    job = make_job(title="Manager Band 7", source="nhs_jobs", location="Bristol")
    result = _check_nhs_band_salary(job, _NHS_RULES, 60000)
    assert result.reject_reason == "nhs band salary below threshold: Band 7 (~£43,742)"


def test_nhs_band_reject_reason_london_format():
    job = make_job(title="Manager Band 7", source="nhs_jobs", location="London")
    result = _check_nhs_band_salary(job, _NHS_RULES, 60000)
    assert result.reject_reason == "nhs band salary below threshold: Band 7 London (~£52,490)"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_filter.py -v -k "nhs_band"
```

Expected: All 12 new tests FAIL with `ImportError: cannot import name '_check_nhs_band_salary'`

- [ ] **Step 3: Implement `_check_nhs_band_salary` in filter.py**

Add after the existing imports at the top of `src/job_search_email/filter.py`:

```python
from typing import Any

_NHS_BAND_RE = re.compile(r"Band\s*(\d+[a-dA-D]?)", re.IGNORECASE)
_LONDON_WEIGHTING = 1.20
```

Add the function after `_check_role_suitability`:

```python
def _check_nhs_band_salary(
    job: JobListing,
    nhs_rules: dict[str, Any],
    min_salary: int,
) -> FilteredResult | None:
    search_text = f"{job.title} {(job.description or '')[:500]}"
    match = _NHS_BAND_RE.search(search_text)

    if match is None:
        return None

    band_key = f"Band {match.group(1).lower()}"  # normalise e.g. "8A" → "8a"
    band_map: dict[str, int] = nhs_rules.get("band_salary_map", {})
    base_salary = band_map.get(band_key, 0)

    is_london = "london" in (job.location or "").lower()
    if is_london:
        estimated = int(base_salary * _LONDON_WEIGHTING)
        label = f"{band_key} London (~£{estimated:,})"
    else:
        estimated = base_salary
        label = f"{band_key} (~£{estimated:,})"

    if estimated < min_salary:
        return FilteredResult(
            job=job,
            flags=[],
            rejected=True,
            reject_reason=f"nhs band salary below threshold: {label}",
        )

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_filter.py -v -k "nhs_band"
```

Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/job_search_email/filter.py tests/test_filter.py
git commit -m "feat: add _check_nhs_band_salary with London weighting"
```

---

### Task 2: Wire `_check_nhs_band_salary` into `filter_jobs`

**Files:**
- Modify: `src/job_search_email/filter.py` (update `filter_jobs`)
- Modify: `tests/test_filter.py` (add integration tests)

**Interfaces:**
- Consumes: `_check_nhs_band_salary(job, plan.nhs_rules, profile.min_salary)` from Task 1
- The existing `make_plan()` helper in tests needs to accept an optional `nhs_rules` dict

- [ ] **Step 1: Write the failing integration tests**

In `tests/test_filter.py`, update `make_plan` to accept `nhs_rules`:

```python
def make_plan(roles: list[str] | None = None, nhs_rules: dict | None = None) -> SearchPlan:
    return SearchPlan(
        profile_fingerprint="abc123",
        queries=["test query"],
        exclusions={"roles": roles or [], "employment_types": []},
        nhs_rules=nhs_rules or {},
        evaluator_notes=[],
    )
```

Then append these integration tests:

```python
def test_filter_jobs_rejects_nhs_band_below_threshold():
    jobs = [make_job(title="Manager Band 7", source="nhs_jobs", employment_type="full-time", location="Bristol")]
    results = filter_jobs(jobs, make_plan(nhs_rules=_NHS_RULES), make_profile_stub())
    assert results[0].rejected is True
    assert "Band 7" in results[0].reject_reason


def test_filter_jobs_keeps_nhs_band_above_threshold():
    jobs = [make_job(title="Manager Band 8b", source="nhs_jobs", employment_type="full-time", location="Bristol")]
    results = filter_jobs(jobs, make_plan(nhs_rules=_NHS_RULES), make_profile_stub())
    assert results[0].rejected is False


def test_filter_jobs_employment_type_checked_before_nhs_band():
    # contract should be rejected for employment type, not band salary
    jobs = [make_job(title="Manager Band 7", source="nhs_jobs", employment_type="contract")]
    results = filter_jobs(jobs, make_plan(nhs_rules=_NHS_RULES), make_profile_stub())
    assert results[0].reject_reason == "employment type: contract"


def test_filter_jobs_role_check_before_nhs_band():
    # clinical role title should be rejected for role suitability, not band salary
    jobs = [make_job(title="Staff Nurse Band 7", source="nhs_jobs", employment_type="full-time")]
    results = filter_jobs(jobs, make_plan(roles=["staff nurse"], nhs_rules=_NHS_RULES), make_profile_stub())
    assert "staff nurse" in results[0].reject_reason
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_filter.py -v -k "filter_jobs_rejects_nhs or filter_jobs_keeps_nhs or filter_jobs_employment_type_checked_before_nhs or filter_jobs_role_check_before"
```

Expected: The two new `filter_jobs` NHS tests FAIL (band check not wired up yet); the ordering tests may pass or fail depending on current state.

- [ ] **Step 3: Wire the check into `filter_jobs`**

In `src/job_search_email/filter.py`, replace the `filter_jobs` function body:

```python
def filter_jobs(jobs: list[JobListing], plan: SearchPlan, profile: Profile) -> list[FilteredResult]:
    exclusion_roles = plan.exclusions.get("roles", [])
    results: list[FilteredResult] = []

    for job in jobs:
        et_result = _check_employment_type(job)
        if et_result.rejected:
            results.append(et_result)
            continue

        role_result = _check_role_suitability(job, exclusion_roles)
        if role_result is not None:
            results.append(role_result)
            continue

        nhs_result = _check_nhs_band_salary(job, plan.nhs_rules, profile.min_salary)
        if nhs_result is not None:
            results.append(nhs_result)
            continue

        results.append(FilteredResult(
            job=job,
            flags=et_result.flags,
            rejected=False,
            reject_reason=None,
        ))

    return results
```

- [ ] **Step 4: Run the full test suite**

```
pytest tests/test_filter.py -v
```

Expected: All tests PASS (existing tests unaffected, 4 new integration tests PASS)

- [ ] **Step 5: Commit**

```bash
git add src/job_search_email/filter.py tests/test_filter.py
git commit -m "feat: wire NHS band salary filter into filter_jobs pipeline"
```
