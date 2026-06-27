# Job Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Filter fetched job listings by employment type and role suitability, writing kept and rejected results to `job_results_filtered.json`.

**Architecture:** A new `filter.py` module applies two sequential filters (employment type, then role suitability) to each `JobListing`, returning `FilteredResult` objects. `exclusions.py` gains a Claude Haiku call at plan-time to expand the role exclusion list. `main.py` calls the filter after fetching and writes two output files.

**Tech Stack:** Python 3.11, anthropic SDK (already used in `queries.py`), pytest, `unittest.mock`.

## Global Constraints

- Python 3.11+ syntax (`X | Y` union types, `frozenset`, `match` expressions are fine)
- Model for all Claude calls: `claude-haiku-4-5-20251001`
- Tests live in `tests/` and run with `pytest` (configured in `pyproject.toml`)
- Never import `Profile` unnecessarily — prefer passing only what is needed
- `asdict` from `dataclasses` is used for JSON serialisation throughout the project — follow this pattern
- All file paths are resolved relative to `Path.cwd()` via the `ROOT` constant in `main.py`

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/job_search_email/models.py` | Add `FilteredResult` dataclass |
| Create | `src/job_search_email/filter.py` | Employment type + role suitability filters |
| Modify | `src/job_search_email/exclusions.py` | Add Claude call to expand role exclusion list |
| Modify | `src/job_search_email/main.py` | Wire filter, write `job_results_filtered.json` |
| Create | `tests/test_filter.py` | Tests for filter module |
| Modify | `tests/test_main.py` | Update existing `get_exclusions` tests to mock Claude call |

---

## Task 1: FilteredResult dataclass

**Files:**
- Modify: `src/job_search_email/models.py`
- Test: `tests/test_filter.py` (create)

**Interfaces:**
- Produces: `FilteredResult(job, flags, rejected, reject_reason)` used by Tasks 2, 3, 4, 6

- [ ] **Step 1: Write the failing test**

Create `tests/test_filter.py`:

```python
from dataclasses import asdict
from job_search_email.models import FilteredResult, JobListing


def make_job(**kwargs) -> JobListing:
    defaults = dict(
        title="Business Manager",
        company="NHS Trust",
        location="Bristol",
        salary_min=65000,
        description="",
        url="https://example.com/job/1",
        source="reed",
        employment_type=None,
    )
    defaults.update(kwargs)
    return JobListing(**defaults)


def test_filtered_result_rejected():
    job = make_job(employment_type="contract")
    result = FilteredResult(job=job, flags=[], rejected=True, reject_reason="employment type: contract")
    assert result.rejected is True
    assert result.reject_reason == "employment type: contract"
    assert result.flags == []


def test_filtered_result_kept_with_flag():
    job = make_job()
    result = FilteredResult(job=job, flags=["employment_type_unknown"], rejected=False, reject_reason=None)
    assert result.rejected is False
    assert result.reject_reason is None
    assert "employment_type_unknown" in result.flags


def test_filtered_result_serialises_with_asdict():
    job = make_job(employment_type="full-time")
    result = FilteredResult(job=job, flags=[], rejected=False, reject_reason=None)
    data = asdict(result)
    assert data["rejected"] is False
    assert data["job"]["title"] == "Business Manager"
    assert data["flags"] == []
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_filter.py -v
```

Expected: `ImportError` — `FilteredResult` does not exist yet.

- [ ] **Step 3: Add `FilteredResult` to `models.py`**

Open `src/job_search_email/models.py`. After the `JobListing` dataclass, add:

```python
@dataclass
class FilteredResult:
    job: JobListing
    flags: list[str]
    rejected: bool
    reject_reason: str | None
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_filter.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/job_search_email/models.py tests/test_filter.py
git commit -m "feat: add FilteredResult dataclass and test scaffold"
```

---

## Task 2: Employment type filter

**Files:**
- Create: `src/job_search_email/filter.py`
- Test: `tests/test_filter.py`

**Interfaces:**
- Consumes: `FilteredResult` from Task 1, `JobListing` from `models.py`
- Produces: `_check_employment_type(job: JobListing) -> FilteredResult` — always returns a result (never `None`)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_filter.py`:

```python
from job_search_email.filter import _check_employment_type


# --- Stage 1: structured employment_type field ---

def test_employment_type_contract_rejected():
    result = _check_employment_type(make_job(employment_type="contract"))
    assert result.rejected is True
    assert result.reject_reason == "employment type: contract"


def test_employment_type_fixed_term_rejected():
    result = _check_employment_type(make_job(employment_type="fixed-term"))
    assert result.rejected is True


def test_employment_type_part_time_rejected():
    result = _check_employment_type(make_job(employment_type="part-time"))
    assert result.rejected is True


def test_employment_type_full_time_passes():
    result = _check_employment_type(make_job(employment_type="full-time"))
    assert result.rejected is False
    assert result.flags == []


def test_employment_type_permanent_passes():
    result = _check_employment_type(make_job(employment_type="permanent"))
    assert result.rejected is False
    assert result.flags == []


# --- Stage 2: text scan ---

def test_employment_type_fixed_term_contract_in_description_rejected():
    job = make_job(description="This is a fixed-term contract post based in Bristol.")
    result = _check_employment_type(job)
    assert result.rejected is True
    assert result.reject_reason == "description contains contract indicators"


def test_employment_type_maternity_cover_rejected():
    job = make_job(description="This is a maternity cover position for 12 months.")
    result = _check_employment_type(job)
    assert result.rejected is True


def test_employment_type_month_contract_rejected():
    job = make_job(description="This is a 12-month contract with possible extension.")
    result = _check_employment_type(job)
    assert result.rejected is True


def test_employment_type_zero_hours_rejected():
    job = make_job(description="This zero-hours role requires flexibility.")
    result = _check_employment_type(job)
    assert result.rejected is True


def test_employment_type_contract_in_duties_not_rejected():
    # "contract" as a job duty term must not trigger rejection
    job = make_job(description="The role involves managing contracts with suppliers and reviewing procurement.")
    result = _check_employment_type(job)
    assert result.rejected is False


def test_employment_type_unknown_flagged():
    # No structured type, no contract phrases in description
    job = make_job(description="A great senior management opportunity at an NHS trust.")
    result = _check_employment_type(job)
    assert result.rejected is False
    assert "employment_type_unknown" in result.flags


def test_employment_type_none_with_clean_description_flagged():
    result = _check_employment_type(make_job(employment_type=None, description=""))
    assert result.rejected is False
    assert "employment_type_unknown" in result.flags


def test_employment_type_text_scan_limited_to_500_chars():
    # Contract phrase buried deep in description should NOT trigger rejection
    prefix = "A" * 500
    job = make_job(description=f"{prefix} This is a fixed-term contract post.")
    result = _check_employment_type(job)
    assert result.rejected is False
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_filter.py -k "employment_type" -v
```

Expected: `ImportError` — `filter` module does not exist yet.

- [ ] **Step 3: Create `src/job_search_email/filter.py`**

```python
import re
from .models import FilteredResult, JobListing, Profile, SearchPlan

_REJECT_TYPES = frozenset({
    "contract", "fixed-term", "temporary", "locum", "bank",
    "agency", "casual", "zero-hours", "part-time", "internship",
})

_PASS_TYPES = frozenset({"full-time", "permanent"})

_CONTRACT_PATTERNS = re.compile(
    r"fixed.?term (?:contract|post|appointment)"
    r"|temporary (?:contract|post|role)"
    r"|on a contract basis"
    r"|contract basis"
    r"|maternity cover"
    r"|parental leave cover"
    r"|\d+[\s\-]month (?:contract|fixed)"
    r"|zero.hours"
    r"|bank staff"
    r"|locum post",
    re.IGNORECASE,
)


def _check_employment_type(job: JobListing) -> FilteredResult:
    et = (job.employment_type or "").lower().strip()

    if et in _REJECT_TYPES:
        return FilteredResult(job=job, flags=[], rejected=True, reject_reason=f"employment type: {et}")

    if et in _PASS_TYPES:
        return FilteredResult(job=job, flags=[], rejected=False, reject_reason=None)

    text = f"{job.title} {job.description}"[:500]
    if _CONTRACT_PATTERNS.search(text):
        return FilteredResult(job=job, flags=[], rejected=True, reject_reason="description contains contract indicators")

    return FilteredResult(job=job, flags=["employment_type_unknown"], rejected=False, reject_reason=None)


def _check_role_suitability(job: JobListing, exclusion_roles: list[str]) -> FilteredResult | None:
    raise NotImplementedError


def filter_jobs(jobs: list[JobListing], plan: SearchPlan, profile: Profile) -> list[FilteredResult]:
    raise NotImplementedError
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_filter.py -k "employment_type" -v
```

Expected: all 13 employment_type tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/job_search_email/filter.py tests/test_filter.py
git commit -m "feat: add employment type filter with structured field and text scan"
```

---

## Task 3: Role suitability filter

**Files:**
- Modify: `src/job_search_email/filter.py`
- Test: `tests/test_filter.py`

**Interfaces:**
- Consumes: `JobListing`, `exclusion_roles: list[str]` (from `plan.exclusions["roles"]`)
- Produces: `_check_role_suitability(job, exclusion_roles) -> FilteredResult | None` — `None` means "no match, job passes"

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_filter.py`:

```python
from job_search_email.filter import _check_role_suitability


def test_role_suitability_rejects_matching_title():
    job = make_job(title="Staff Nurse Band 5")
    result = _check_role_suitability(job, ["staff nurse", "ward manager", "clinical lead"])
    assert result is not None
    assert result.rejected is True
    assert "staff nurse" in result.reject_reason


def test_role_suitability_rejects_case_insensitively():
    job = make_job(title="WARD MANAGER")
    result = _check_role_suitability(job, ["ward manager"])
    assert result is not None
    assert result.rejected is True


def test_role_suitability_rejects_on_partial_title_match():
    job = make_job(title="Senior Clinical Lead - Digital")
    result = _check_role_suitability(job, ["clinical lead"])
    assert result is not None
    assert result.rejected is True


def test_role_suitability_passes_non_matching_title():
    job = make_job(title="Business Manager Digital Transformation")
    result = _check_role_suitability(job, ["staff nurse", "ward manager", "clinical lead"])
    assert result is None


def test_role_suitability_passes_empty_exclusion_list():
    job = make_job(title="Staff Nurse")
    result = _check_role_suitability(job, [])
    assert result is None


def test_role_suitability_reject_reason_includes_matched_term():
    job = make_job(title="Consultant Physician")
    result = _check_role_suitability(job, ["consultant physician"])
    assert result is not None
    assert result.reject_reason == "unsuitable role: consultant physician"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_filter.py -k "role_suitability" -v
```

Expected: `NotImplementedError` from the stub.

- [ ] **Step 3: Implement `_check_role_suitability` in `filter.py`**

Replace the stub:

```python
def _check_role_suitability(job: JobListing, exclusion_roles: list[str]) -> FilteredResult | None:
    title_lower = job.title.lower()
    for term in exclusion_roles:
        if term.lower() in title_lower:
            return FilteredResult(job=job, flags=[], rejected=True, reject_reason=f"unsuitable role: {term}")
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_filter.py -k "role_suitability" -v
```

Expected: all 6 role_suitability tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/job_search_email/filter.py tests/test_filter.py
git commit -m "feat: add role suitability filter with title keyword matching"
```

---

## Task 4: `filter_jobs` orchestrator

**Files:**
- Modify: `src/job_search_email/filter.py`
- Test: `tests/test_filter.py`

**Interfaces:**
- Consumes: `list[JobListing]`, `SearchPlan` (for `plan.exclusions["roles"]`), `Profile`
- Produces: `filter_jobs(jobs, plan, profile) -> list[FilteredResult]` — flat list of all jobs, kept and rejected

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_filter.py`:

```python
from job_search_email.filter import filter_jobs
from job_search_email.models import SearchPlan


def make_plan(roles: list[str] | None = None) -> SearchPlan:
    return SearchPlan(
        profile_fingerprint="abc123",
        queries=["test query"],
        exclusions={"roles": roles or [], "employment_types": []},
        nhs_rules={},
        evaluator_notes=[],
    )


def make_profile_stub():
    from job_search_email.models import Profile
    return Profile(
        name="Test", current_role="Manager", about="", seniority="Senior",
        industry="NHS", skills=[], previous_roles=[], target_roles=[],
        open_to=[], not_open_to=[], qualifications=[],
        employment_type=["full-time"], location="Bristol", min_salary=60000,
    )


def test_filter_jobs_rejects_contract_role():
    jobs = [make_job(employment_type="contract")]
    results = filter_jobs(jobs, make_plan(), make_profile_stub())
    assert len(results) == 1
    assert results[0].rejected is True


def test_filter_jobs_keeps_full_time_role():
    jobs = [make_job(employment_type="full-time")]
    results = filter_jobs(jobs, make_plan(), make_profile_stub())
    assert len(results) == 1
    assert results[0].rejected is False
    assert results[0].flags == []


def test_filter_jobs_flags_unknown_employment_type():
    jobs = [make_job(employment_type=None, description="A management position.")]
    results = filter_jobs(jobs, make_plan(), make_profile_stub())
    assert len(results) == 1
    assert results[0].rejected is False
    assert "employment_type_unknown" in results[0].flags


def test_filter_jobs_rejects_unsuitable_role_title():
    jobs = [make_job(title="Staff Nurse Band 5", employment_type="full-time")]
    results = filter_jobs(jobs, make_plan(roles=["staff nurse"]), make_profile_stub())
    assert len(results) == 1
    assert results[0].rejected is True
    assert "staff nurse" in results[0].reject_reason


def test_filter_jobs_employment_type_checked_before_role():
    # A contract role with a clinical title: reject reason should be employment type
    jobs = [make_job(title="Staff Nurse", employment_type="contract")]
    results = filter_jobs(jobs, make_plan(roles=["staff nurse"]), make_profile_stub())
    assert results[0].reject_reason == "employment type: contract"


def test_filter_jobs_returns_all_jobs_as_filtered_results():
    jobs = [
        make_job(employment_type="full-time"),
        make_job(employment_type="contract"),
        make_job(employment_type=None),
    ]
    results = filter_jobs(jobs, make_plan(), make_profile_stub())
    assert len(results) == 3


def test_filter_jobs_unknown_flag_preserved_on_passing_job():
    jobs = [make_job(employment_type=None, description="Permanent role with no type specified.")]
    results = filter_jobs(jobs, make_plan(), make_profile_stub())
    assert results[0].rejected is False
    assert "employment_type_unknown" in results[0].flags
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_filter.py -k "filter_jobs" -v
```

Expected: `NotImplementedError` from the stub.

- [ ] **Step 3: Implement `filter_jobs` in `filter.py`**

Replace the stub:

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

        results.append(FilteredResult(
            job=job,
            flags=et_result.flags,
            rejected=False,
            reject_reason=None,
        ))

    return results
```

- [ ] **Step 4: Run all filter tests**

```
pytest tests/test_filter.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/job_search_email/filter.py tests/test_filter.py
git commit -m "feat: add filter_jobs orchestrator combining employment type and role filters"
```

---

## Task 5: Claude exclusion expansion in `exclusions.py`

**Files:**
- Modify: `src/job_search_email/exclusions.py`
- Modify: `tests/test_main.py` (update two existing tests that call `get_exclusions`)

**Interfaces:**
- Consumes: `Profile`
- Produces: updated `get_exclusions(profile) -> dict[str, list[str]]` — `exclusions["roles"]` now includes Claude-generated terms

- [ ] **Step 1: Update the two existing `get_exclusions` tests to mock the Claude call**

In `tests/test_main.py`, find `test_get_exclusions_merges_not_open_to` and `test_get_exclusions_deduplicates`. Add a `patch` so the Claude call is mocked in both:

```python
def test_get_exclusions_merges_not_open_to() -> None:
    profile = make_profile()  # not_open_to: ["clinical roles", "nursing"]

    with patch("job_search_email.exclusions.client") as mock_client:
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text='["ward manager", "clinical lead"]')]
        )
        result = get_exclusions(profile)

    assert "roles" in result
    assert "employment_types" in result
    assert "clinical roles" in result["roles"]
    assert "nursing" in result["roles"]
    assert "locum" in result["roles"]          # from STANDARD_CLINICAL_TERMS
    assert "ward manager" in result["roles"]   # from Claude
    assert "fixed-term" in result["employment_types"]
    assert "bank" in result["employment_types"]


def test_get_exclusions_deduplicates() -> None:
    profile = make_profile()
    profile.not_open_to.append("locum")        # already in STANDARD_CLINICAL_TERMS

    with patch("job_search_email.exclusions.client") as mock_client:
        mock_client.messages.create.return_value = MagicMock(
            content=[MagicMock(text="[]")]
        )
        result = get_exclusions(profile)

    assert result["roles"].count("locum") == 1
```

- [ ] **Step 2: Run the existing exclusions tests to confirm they fail (because `client` doesn't exist in `exclusions.py` yet)**

```
pytest tests/test_main.py -k "exclusion" -v
```

Expected: both tests fail because `get_exclusions` doesn't call Claude yet.

- [ ] **Step 3: Update `exclusions.py`**

Replace the entire file:

```python
import json

import anthropic

from .models import Profile

client = anthropic.Anthropic()

STANDARD_CLINICAL_TERMS: list[str] = [
    "locum",
    "GP",
    "surgeon",
    "nurse",
    "clinical",
    "surgical",
    "physician",
    "dentist",
    "pharmacist",
    "physiotherapist",
    "radiographer",
    "midwife",
    "paramedic",
    "theatre",
    "ward",
    "medical officer",
    "occupational therapist",
]

_EXCLUSION_ROLES_PROMPT = """\
You are helping filter job search results for {name}.

Generate a list of role title keywords that would be UNSUITABLE for this candidate.
Focus especially on NHS clinical and ward-based titles that a non-clinical NHS manager might surface in searches.

Candidate:
  Current role: {current_role}
  Industry: {industry}
  Target roles: {target_roles}
  Not open to: {not_open_to}
  Skills: {skills}

Return a JSON array of lowercase strings (1-4 words each, aim for 20-30 items).
Do not include generic terms that might match legitimate management roles.
No other text.\
"""


def _generate_exclusion_roles(profile: Profile) -> list[str]:
    prompt = _EXCLUSION_ROLES_PROMPT.format(
        name=profile.name,
        current_role=profile.current_role,
        industry=profile.industry,
        target_roles=", ".join(profile.target_roles),
        not_open_to=", ".join(profile.not_open_to),
        skills=", ".join(profile.skills),
    )
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    result = json.loads(response.content[0].text)
    if not isinstance(result, list):
        return []
    return [str(term).lower() for term in result]


def get_exclusions(profile: Profile) -> dict[str, list[str]]:
    claude_roles = _generate_exclusion_roles(profile)
    roles = sorted(set(STANDARD_CLINICAL_TERMS + profile.not_open_to + claude_roles))
    employment = [
        "locum",
        "fixed-term",
        "temporary",
        "bank",
        "agency",
        "casual",
        "zero-hours",
    ]
    return {"roles": roles, "employment_types": employment}
```

- [ ] **Step 4: Run all tests to confirm existing and new tests pass**

```
pytest tests/test_main.py -v
```

Expected: all tests pass (including the two updated exclusion tests).

- [ ] **Step 5: Commit**

```bash
git add src/job_search_email/exclusions.py tests/test_main.py
git commit -m "feat: expand role exclusion list with Claude Haiku at plan-time"
```

---

## Task 6: Wire filter into `main.py` and write output files

**Files:**
- Modify: `src/job_search_email/main.py`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `filter_jobs` from `filter.py`, `FilteredResult` from `models.py`
- Produces: `job_results.json` (unchanged), `job_results_filtered.json` (new)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_main.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from job_search_email.main import write_filtered_results
from job_search_email.models import FilteredResult, JobListing


def make_job_listing(**kwargs) -> JobListing:
    defaults = dict(
        title="Business Manager", company="NHS Trust", location="Bristol",
        salary_min=65000, description="", url="https://example.com/1",
        source="reed", employment_type="full-time",
    )
    defaults.update(kwargs)
    return JobListing(**defaults)


def test_write_filtered_results_creates_file(tmp_path: Path) -> None:
    kept = FilteredResult(job=make_job_listing(), flags=[], rejected=False, reject_reason=None)
    rejected = FilteredResult(
        job=make_job_listing(employment_type="contract"),
        flags=[], rejected=True, reject_reason="employment type: contract",
    )
    output_path = tmp_path / "job_results_filtered.json"

    write_filtered_results([kept, rejected], path=output_path)

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["summary"]["total"] == 2
    assert data["summary"]["kept"] == 1
    assert data["summary"]["rejected"] == 1
    assert data["summary"]["flagged"] == 0
    assert len(data["kept"]) == 1
    assert len(data["rejected"]) == 1


def test_write_filtered_results_counts_flagged(tmp_path: Path) -> None:
    flagged = FilteredResult(
        job=make_job_listing(employment_type=None),
        flags=["employment_type_unknown"], rejected=False, reject_reason=None,
    )
    output_path = tmp_path / "job_results_filtered.json"

    write_filtered_results([flagged], path=output_path)

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["summary"]["flagged"] == 1
    assert data["kept"][0]["flags"] == ["employment_type_unknown"]


def test_write_filtered_results_rejected_includes_reason(tmp_path: Path) -> None:
    result = FilteredResult(
        job=make_job_listing(), flags=[], rejected=True, reject_reason="unsuitable role: nurse",
    )
    output_path = tmp_path / "job_results_filtered.json"

    write_filtered_results([result], path=output_path)

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["rejected"][0]["reject_reason"] == "unsuitable role: nurse"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_main.py -k "filtered_results" -v
```

Expected: `ImportError` — `write_filtered_results` does not exist yet.

- [ ] **Step 3: Add `write_filtered_results` and `FILTERED_RESULTS_PATH` to `main.py`**

At the top of `main.py`, update the existing `from .models import ...` line to include `FilteredResult`, and add the filter import:

```python
from .filter import filter_jobs
from .models import FilteredResult, Profile, SearchPlan
```

Add the path constant after `RESULTS_PATH`:

```python
FILTERED_RESULTS_PATH = ROOT / "job_results_filtered.json"
```

Add the new function after `write_search_plan`:

```python
def write_filtered_results(results: list[FilteredResult], path: Path = FILTERED_RESULTS_PATH) -> None:
    kept = [r for r in results if not r.rejected]
    rejected = [r for r in results if r.rejected]
    flagged = [r for r in kept if r.flags]

    output = {
        "summary": {
            "total": len(results),
            "kept": len(kept),
            "rejected": len(rejected),
            "flagged": len(flagged),
        },
        "kept": [asdict(r) for r in kept],
        "rejected": [asdict(r) for r in rejected],
    }

    with path.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)
```

- [ ] **Step 4: Run tests to verify `write_filtered_results` tests pass**

```
pytest tests/test_main.py -k "filtered_results" -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Wire filter into `main()`**

In `main.py`, locate the existing fetch block (shown below) and insert the five new lines after the last `print` in that block:

```python
    print("Fetching jobs...")
    jobs = fetch_all_jobs(plan, profile)
    with RESULTS_PATH.open("w", encoding="utf-8") as handle:
        json.dump([asdict(job) for job in jobs], handle, indent=2)
    print(f"- jobs fetched: {len(jobs)}")
    print(f"- results written to: {RESULTS_PATH}")
    # --- ADD THESE LINES BELOW ---
    print("Filtering jobs...")
    filtered = filter_jobs(jobs, plan, profile)
    write_filtered_results(filtered)
    kept = [r for r in filtered if not r.rejected]
    flagged = [r for r in kept if r.flags]
    print(f"- filtered: {len(kept)} kept, {len(filtered) - len(kept)} rejected ({len(flagged)} flagged unknown employment type)")
    print(f"- filtered results written to: {FILTERED_RESULTS_PATH}")
```

- [ ] **Step 6: Run the full test suite**

```
pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/job_search_email/main.py tests/test_main.py
git commit -m "feat: wire filter_jobs into main, write job_results_filtered.json"
```
