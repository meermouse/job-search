# Local Testing Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `job-search-email-local` command that runs the full pipeline end-to-end with hardcoded fixture data — no Claude API, no job board APIs, no SMTP — and writes the email output to `email_preview.html`.

**Architecture:** Two new files are added alongside the existing production code: `fixtures.py` holds all hardcoded test data, and `local_run.py` is a self-contained orchestrator that calls the pipeline's pure-logic functions directly while substituting fixture data for every API call. A second script entry point is registered in `pyproject.toml`. No production module is modified.

**Tech Stack:** Python 3.11, pytest, existing project models in `src/job_search_email/models.py`.

## Global Constraints

- Python ≥ 3.11
- Do NOT modify `main.py`, `queries.py`, `scorer.py`, `exclusions.py`, `search_api/fetcher.py`, or `email.py`
- `local_run.py` must NOT import from `main.py`, `queries.py`, `scorer.py`, or `exclusions.py` — these instantiate `anthropic.Anthropic()` at module level, which raises `AuthenticationError` if `ANTHROPIC_API_KEY` is unset
- All new files live in `src/job_search_email/`
- Tests live in `tests/`
- Working directory is the project root (`c:\Code\job-search-email`)

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `src/job_search_email/fixtures.py` | Create | All hardcoded test data: queries, jobs, scores |
| `src/job_search_email/local_run.py` | Create | Local test orchestrator — no API calls |
| `pyproject.toml` | Modify | Register `job-search-email-local` script entry point |
| `tests/test_local_testing.py` | Create | Tests for fixtures and local run smoke test |

---

### Task 1: `fixtures.py` — hardcoded test data

**Files:**
- Create: `src/job_search_email/fixtures.py`
- Test: `tests/test_local_testing.py`

**Interfaces:**
- Produces:
  - `fixture_queries() -> list[str]`
  - `fixture_jobs() -> list[JobListing]`
  - `fixture_scores(results: list[FilteredResult]) -> list[ScoredResult]`

The five fixture jobs are designed to exercise the filter pipeline:

| Job | URL key | Expected filter outcome |
|-----|---------|------------------------|
| "Senior Business Manager" | `.../12345678` | Kept — permanent, £75k |
| "Digital Transformation Consultant" | `.../12345679` | Rejected — employment_type = "contract" |
| "Band 8b NHS Digital Transformation Manager" | `.../A1234-25-0001` | Kept — Band 8b (£62,215 > £60,000 min) |
| "Band 5 NHS Administrator" | `.../A1234-25-0002` | Rejected — Band 5 not in salary map (£0 < £60,000) |
| "Strategy Consultant" | `.../12345680` | Kept — permanent, £65k |

`fixture_scores` maps kept jobs to hardcoded `JobAnalysis` by URL. Rejected jobs get `analysis=None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_local_testing.py`:

```python
import pytest
from job_search_email.fixtures import fixture_queries, fixture_jobs, fixture_scores
from job_search_email.models import FilteredResult, JobAnalysis, JobListing


def test_fixture_queries_returns_eight_strings():
    queries = fixture_queries()
    assert len(queries) == 8
    assert all(isinstance(q, str) and q.strip() for q in queries)


def test_fixture_jobs_returns_five_listings():
    jobs = fixture_jobs()
    assert len(jobs) == 5
    assert all(isinstance(j, JobListing) for j in jobs)


def test_fixture_jobs_cover_expected_scenarios():
    jobs = fixture_jobs()
    types = [j.employment_type for j in jobs]
    assert "contract" in types, "need a contract job for employment-type rejection"
    titles_combined = " ".join(j.title for j in jobs)
    assert "Band 5" in titles_combined, "need a low-band NHS job for band-salary rejection"
    assert "Band 8b" in titles_combined, "need a passing NHS job"


def test_fixture_scores_output_length_matches_input():
    jobs = fixture_jobs()
    results = [
        FilteredResult(job=j, flags=[], rejected=False, reject_reason=None)
        for j in jobs
    ]
    scored = fixture_scores(results)
    assert len(scored) == len(results)


def test_fixture_scores_kept_known_jobs_have_analysis():
    jobs = fixture_jobs()
    results = [
        FilteredResult(job=j, flags=[], rejected=False, reject_reason=None)
        for j in jobs
    ]
    scored = fixture_scores(results)
    # All five inputs are "kept" here; known URLs should have an analysis
    known_url = "https://www.reed.co.uk/jobs/senior-business-manager/12345678"
    match = next(s for s in scored if s.job.url == known_url)
    assert match.analysis is not None
    assert isinstance(match.analysis.score, int)
    assert 1 <= match.analysis.score <= 10


def test_fixture_scores_rejected_jobs_have_no_analysis():
    jobs = fixture_jobs()
    results = [
        FilteredResult(job=j, flags=[], rejected=True, reject_reason="employment type: contract")
        if j.employment_type == "contract"
        else FilteredResult(job=j, flags=[], rejected=False, reject_reason=None)
        for j in jobs
    ]
    scored = fixture_scores(results)
    rejected = [s for s in scored if s.rejected]
    assert all(s.analysis is None for s in rejected)
```

- [ ] **Step 2: Run tests to confirm they fail**

```
cd c:\Code\job-search-email
python -m pytest tests/test_local_testing.py -v
```

Expected: `ModuleNotFoundError: No module named 'job_search_email.fixtures'`

- [ ] **Step 3: Create `fixtures.py`**

Create `src/job_search_email/fixtures.py`:

```python
from .models import FilteredResult, JobAnalysis, JobListing, ScoredResult

_FIXTURE_ANALYSES: dict[str, JobAnalysis] = {
    "https://www.reed.co.uk/jobs/senior-business-manager/12345678": JobAnalysis(
        score=9,
        matched_skills=["digital transformation", "Business Strategy", "Project Initiation and Planning"],
        missing_essentials=[],
        employment_type_note="Permanent full-time — matches preference.",
        verdict="Strong match. Senior management role with well-aligned skills and target industry.",
    ),
    "https://www.jobs.nhs.uk/candidate/jobadvert/A1234-25-0001": JobAnalysis(
        score=7,
        matched_skills=["digital transformation", "Analytical Skills"],
        missing_essentials=["dedicated NHS digital leadership experience"],
        employment_type_note="Permanent full-time — matches preference.",
        verdict="Good fit for NHS digital transformation with minor experience gaps.",
    ),
    "https://www.reed.co.uk/jobs/strategy-consultant/12345680": JobAnalysis(
        score=6,
        matched_skills=["Business Strategy", "Analytical Skills"],
        missing_essentials=["consulting firm background"],
        employment_type_note="Permanent full-time — matches preference.",
        verdict="Partial match. Strategy focus aligns but consulting pedigree is thin.",
    ),
}

_FALLBACK_ANALYSIS = JobAnalysis(
    score=5,
    matched_skills=[],
    missing_essentials=[],
    employment_type_note="Unknown.",
    verdict="Insufficient data to score accurately.",
)


def fixture_queries() -> list[str]:
    return [
        "senior business manager NHS",
        "digital transformation manager",
        "head of digital services",
        "senior programme manager health",
        "business transformation lead",
        "strategy and operations manager",
        "senior project manager healthcare",
        "digital change manager NHS",
    ]


def fixture_jobs() -> list[JobListing]:
    return [
        JobListing(
            title="Senior Business Manager",
            company="Accenture UK",
            location="Bristol",
            salary_min=75000,
            description=(
                "Lead business transformation initiatives across our public sector clients. "
                "You will manage cross-functional teams and drive strategic change programmes. "
                "Permanent, full-time role based in Bristol."
            ),
            url="https://www.reed.co.uk/jobs/senior-business-manager/12345678",
            source="reed",
            employment_type="permanent",
        ),
        JobListing(
            title="Digital Transformation Consultant",
            company="Deloitte UK",
            location="Bristol",
            salary_min=80000,
            description=(
                "6-month contract engagement supporting a major NHS trust with their "
                "digital roadmap. Day rate negotiable."
            ),
            url="https://www.linkedin.com/jobs/view/12345679",
            source="linkedin",
            employment_type="contract",
        ),
        JobListing(
            title="Band 8b NHS Digital Transformation Manager",
            company="NHS Bristol, North Somerset and South Gloucestershire ICB",
            location="Bristol",
            salary_min=62215,
            description="",
            url="https://www.jobs.nhs.uk/candidate/jobadvert/A1234-25-0001",
            source="nhs_jobs",
            employment_type="permanent",
        ),
        JobListing(
            title="Band 5 NHS Administrator",
            company="University Hospitals Bristol NHS Foundation Trust",
            location="Bristol",
            salary_min=29970,
            description="",
            url="https://www.jobs.nhs.uk/candidate/jobadvert/A1234-25-0002",
            source="nhs_jobs",
            employment_type="permanent",
        ),
        JobListing(
            title="Strategy Consultant",
            company="PwC UK",
            location="Bristol",
            salary_min=65000,
            description=(
                "Work with senior leadership teams across financial services and public sector "
                "to develop and implement strategic change. Permanent role with hybrid working."
            ),
            url="https://www.reed.co.uk/jobs/strategy-consultant/12345680",
            source="reed",
            employment_type="permanent",
        ),
    ]


def fixture_scores(results: list[FilteredResult]) -> list[ScoredResult]:
    scored = []
    for r in results:
        if r.rejected:
            analysis = None
        else:
            analysis = _FIXTURE_ANALYSES.get(r.job.url, _FALLBACK_ANALYSIS)
        scored.append(ScoredResult(
            job=r.job,
            flags=r.flags,
            rejected=r.rejected,
            reject_reason=r.reject_reason,
            analysis=analysis,
        ))
    return scored
```

- [ ] **Step 4: Run tests to confirm they pass**

```
python -m pytest tests/test_local_testing.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```
git add src/job_search_email/fixtures.py tests/test_local_testing.py
git commit -m "feat: add fixture module for local testing"
```

---

### Task 2: `local_run.py` + `pyproject.toml` entry point

**Files:**
- Create: `src/job_search_email/local_run.py`
- Modify: `pyproject.toml` lines 25-26
- Test: `tests/test_local_testing.py` (append)

**Interfaces:**
- Consumes: `fixture_queries`, `fixture_jobs`, `fixture_scores` from Task 1
- Consumes (pure-logic, no Anthropic import): `filter_jobs` from `filter.py`, `build_email_html` from `email.py`, `get_nhs_rules` from `nhs_rules.py`, `get_evaluator_notes` from `evaluator_notes.py`, `fingerprint_profile` from `cache.py`
- Produces: `local_run.main()` entry point; writes `email_preview.html` and JSON artefacts to cwd

**Why `local_run.py` does NOT import from `main.py`:**
`main.py` imports `queries`, `scorer`, and `exclusions` at the top level. All three instantiate `anthropic.Anthropic()` as a module-level global. That constructor raises `anthropic.AuthenticationError` when `ANTHROPIC_API_KEY` is unset — exactly the scenario this feature is designed for. The path constants and write helpers from `main.py` are duplicated here (≈50 lines) to avoid that transitive import.

- [ ] **Step 1: Write the smoke test (append to `tests/test_local_testing.py`)**

```python
import json
from pathlib import Path
import pytest


def test_local_run_writes_email_preview(tmp_path, monkeypatch):
    import shutil

    # Copy profile.yaml into the temp directory
    project_root = Path(__file__).parent.parent
    shutil.copy(project_root / "profile.yaml", tmp_path / "profile.yaml")

    # Point cwd at tmp_path so all file writes land there
    monkeypatch.chdir(tmp_path)

    from job_search_email import local_run
    local_run.main()

    preview = tmp_path / "email_preview.html"
    assert preview.exists(), "email_preview.html was not created"
    content = preview.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "Senior Business Manager" in content


def test_local_run_writes_json_artefacts(tmp_path, monkeypatch):
    import shutil

    project_root = Path(__file__).parent.parent
    shutil.copy(project_root / "profile.yaml", tmp_path / "profile.yaml")
    monkeypatch.chdir(tmp_path)

    from job_search_email import local_run
    local_run.main()

    assert (tmp_path / "search_plan.json").exists()
    assert (tmp_path / "job_results_filtered.json").exists()
    assert (tmp_path / "job_results_scored.json").exists()

    filtered = json.loads((tmp_path / "job_results_filtered.json").read_text())
    assert filtered["summary"]["kept"] >= 1
```

- [ ] **Step 2: Run tests to confirm they fail**

```
python -m pytest tests/test_local_testing.py::test_local_run_writes_email_preview tests/test_local_testing.py::test_local_run_writes_json_artefacts -v
```

Expected: `ImportError` or `ModuleNotFoundError` for `local_run`.

- [ ] **Step 3: Create `local_run.py`**

Create `src/job_search_email/local_run.py`:

```python
import json
import os
from dataclasses import asdict
from pathlib import Path

import yaml

from .cache import fingerprint_profile
from .email import build_email_html
from .evaluator_notes import get_evaluator_notes
from .filter import filter_jobs
from .fixtures import fixture_jobs, fixture_queries, fixture_scores
from .models import FilteredResult, Profile, SearchPlan, ScoredResult
from .nhs_rules import get_nhs_rules

_EXCLUSION_ROLES = [
    "locum", "gp", "surgeon", "nurse", "clinical", "surgical", "physician",
    "dentist", "pharmacist", "physiotherapist", "radiographer", "midwife",
    "paramedic", "theatre", "ward", "medical officer", "occupational therapist",
    "nursing", "ward-based", "gp / medical practitioner",
]


def _load_profile(path: Path) -> Profile:
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    p = data["profile"]
    return Profile(
        name=p["name"],
        current_role=p.get("current_role", ""),
        about=p.get("about", ""),
        seniority=p.get("seniority", ""),
        industry=p.get("industry", ""),
        skills=p.get("skills", []),
        previous_roles=p.get("previous_roles", []),
        target_roles=p.get("target_roles", []),
        open_to=p.get("open_to", []),
        not_open_to=p.get("not_open_to", []),
        qualifications=p.get("qualifications", []),
        employment_type=p.get("employment_type", []),
        location=data.get("location", ""),
        min_salary=data.get("min_salary", 0),
        preamble=data.get("preamble", ""),
        recipient_email=data.get("recipient_email", ""),
    )


def _write_search_plan(plan: SearchPlan, path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(asdict(plan), handle, indent=2)


def _write_filtered_results(results: list[FilteredResult], path: Path) -> None:
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


def _write_scored_results(results: list[ScoredResult], path: Path) -> None:
    kept = [r for r in results if not r.rejected]
    rejected = [r for r in results if r.rejected]
    analysed = [r for r in kept if r.analysis is not None]
    kept_sorted = sorted(kept, key=lambda r: (r.analysis.score if r.analysis else 0), reverse=True)
    output = {
        "summary": {
            "total": len(results),
            "kept": len(kept),
            "rejected": len(rejected),
            "analysed": len(analysed),
        },
        "kept": [asdict(r) for r in kept_sorted],
        "rejected": [asdict(r) for r in rejected],
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)


def main() -> None:
    root = Path.cwd()
    profile = _load_profile(root / "profile.yaml")
    fingerprint = fingerprint_profile(profile)

    exclusion_roles = sorted(set(_EXCLUSION_ROLES + [t.lower() for t in profile.not_open_to]))
    plan = SearchPlan(
        profile_fingerprint=fingerprint,
        queries=fixture_queries(),
        exclusions={"roles": exclusion_roles, "employment_types": ["locum", "fixed-term", "temporary", "bank", "agency", "casual", "zero-hours"]},
        nhs_rules=get_nhs_rules(),
        evaluator_notes=get_evaluator_notes(profile),
    )
    _write_search_plan(plan, root / "search_plan.json")
    print("[local-test] search plan written")

    jobs = fixture_jobs()
    print(f"[local-test] fixture jobs loaded: {len(jobs)}")

    filtered = filter_jobs(jobs, plan, profile)
    _write_filtered_results(filtered, root / "job_results_filtered.json")
    kept = [r for r in filtered if not r.rejected]
    print(f"[local-test] filtered: {len(kept)} kept, {len(filtered) - len(kept)} rejected")

    scored = fixture_scores(filtered)
    _write_scored_results(scored, root / "job_results_scored.json")

    html, top_n = build_email_html(scored, profile)
    preview_path = root / "email_preview.html"
    preview_path.write_text(html, encoding="utf-8")
    print(f"[local-test] email preview written to {preview_path} ({top_n} jobs)")
```

- [ ] **Step 4: Run tests to confirm they pass**

```
python -m pytest tests/test_local_testing.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Add entry point to `pyproject.toml`**

In `pyproject.toml`, find the `[project.scripts]` section (currently lines 25-26):

```toml
[project.scripts]
job-search-email = "job_search_email.main:main"
```

Change to:

```toml
[project.scripts]
job-search-email = "job_search_email.main:main"
job-search-email-local = "job_search_email.local_run:main"
```

- [ ] **Step 6: Reinstall the package to register the new script**

```
pip install -e .
```

Expected: output ends with `Successfully installed job-search-email-0.1.0` (or similar).

- [ ] **Step 7: Run the local command end-to-end**

```
job-search-email-local
```

Expected output:
```
[local-test] search plan written
[local-test] fixture jobs loaded: 5
[local-test] filtered: 3 kept, 2 rejected
[local-test] email preview written to ...\email_preview.html (3 jobs)
```

Open `email_preview.html` in a browser and confirm the table shows three jobs: Senior Business Manager (score 9), Band 8b NHS Digital Transformation Manager (score 7), Strategy Consultant (score 6).

- [ ] **Step 8: Commit**

```
git add src/job_search_email/local_run.py pyproject.toml tests/test_local_testing.py
git commit -m "feat: add local test entry point with fixture data"
```
