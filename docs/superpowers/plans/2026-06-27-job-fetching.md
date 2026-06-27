# Job Fetching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fan the 8 generated queries across LinkedIn/Indeed, Reed, and NHS Jobs concurrently, then return a single deduplicated flat list of `JobListing` objects written to `job_results.json`.

**Architecture:** Each of the three API sources gets its own module with a uniform `search(query, profile) -> list[JobListing]` interface. A `ThreadPoolExecutor` orchestrator in `fetcher.py` submits all 24 combinations concurrently, catches per-task failures, then deduplicates before returning. `main.py` wires this into the existing plan-generation flow.

**Tech Stack:** Python 3.11, `python-jobspy` (LinkedIn + Indeed), `requests` + `beautifulsoup4` (Reed REST + NHS scraper), `concurrent.futures.ThreadPoolExecutor`, `pytest` + `unittest.mock`

## Global Constraints

- Python ≥ 3.11 — use `X | Y` union types, not `Optional[X]` or `Union[X, Y]`
- `distance` is a fixed constant of 50 miles across all sources — `Profile` has no distance field
- All API-specific logic stays inside its own module — no cross-module concerns
- Reed API key comes from `REED_API_KEY` env var — never hardcode
- Deduplication key: `(title.lower().strip(), company.lower().strip())` — first occurrence wins
- Source strings: `"linkedin"`, `"indeed"`, `"reed"`, `"nhs"` (lowercase)
- NHS Jobs `description` is always `""` — scraper provides no job description
- `salary_min` and `employment_type` are `None` when unknown — never fabricate values

---

## File Map

**Create:**
- `src/job_search_email/search_api/__init__.py`
- `src/job_search_email/search_api/dedup.py`
- `src/job_search_email/search_api/reed.py`
- `src/job_search_email/search_api/nhs_jobs.py`
- `src/job_search_email/search_api/jobspy_searcher.py`
- `src/job_search_email/search_api/fetcher.py`
- `tests/search_api/__init__.py`
- `tests/search_api/test_dedup.py`
- `tests/search_api/test_reed.py`
- `tests/search_api/test_nhs_jobs.py`
- `tests/search_api/test_jobspy_searcher.py`
- `tests/search_api/test_fetcher.py`

**Modify:**
- `src/job_search_email/models.py` — add `JobListing` dataclass
- `src/job_search_email/main.py` — import and call `fetch_all_jobs`, write `job_results.json`
- `pyproject.toml` — add `python-jobspy`, `requests`, `beautifulsoup4` to dependencies

---

### Task 1: `JobListing` model + project dependencies

**Files:**
- Modify: `src/job_search_email/models.py`
- Modify: `pyproject.toml`
- Test: `tests/test_job_listing.py`

**Interfaces:**
- Produces: `JobListing(title, company, location, salary_min, description, url, source, employment_type)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_job_listing.py
from job_search_email.models import JobListing


def test_job_listing_all_fields():
    job = JobListing(
        title="Digital Transformation Manager",
        company="NHS Bristol",
        location="Bristol",
        salary_min=60000,
        description="A great role.",
        url="https://www.reed.co.uk/jobs/manager/12345",
        source="reed",
        employment_type="full-time",
    )
    assert job.title == "Digital Transformation Manager"
    assert job.salary_min == 60000
    assert job.source == "reed"
    assert job.employment_type == "full-time"


def test_job_listing_optional_fields_accept_none():
    job = JobListing(
        title="NHS Manager",
        company="NHS Trust",
        location="Bristol",
        salary_min=None,
        description="",
        url="https://jobs.nhs.uk/job/1",
        source="nhs",
        employment_type=None,
    )
    assert job.salary_min is None
    assert job.employment_type is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_job_listing.py -v
```
Expected: `ImportError` — `JobListing` not yet defined on `models`.

- [ ] **Step 3: Add `JobListing` to `models.py`**

Add after the `SearchPlan` dataclass (keep all existing code, append only):

```python
@dataclass
class JobListing:
    title: str
    company: str
    location: str
    salary_min: int | None
    description: str
    url: str
    source: str
    employment_type: str | None
```

- [ ] **Step 4: Add new packages to `pyproject.toml`**

Change the `dependencies` list to:

```toml
dependencies = [
  "PyYAML>=6.0",
  "anthropic>=0.40",
  "python-jobspy>=0.2",
  "requests>=2.31",
  "beautifulsoup4>=4.12",
]
```

- [ ] **Step 5: Install new dependencies**

```bash
pip install -e ".[test]"
```
Expected: installs `python-jobspy`, `requests`, `beautifulsoup4`, and their transitive deps (including `pandas`).

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_job_listing.py -v
```
Expected: 2 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/job_search_email/models.py pyproject.toml tests/test_job_listing.py
git commit -m "feat: add JobListing model and job fetching dependencies"
```

---

### Task 2: `search_api` package + deduplication

**Files:**
- Create: `src/job_search_email/search_api/__init__.py`
- Create: `src/job_search_email/search_api/dedup.py`
- Create: `tests/search_api/__init__.py`
- Test: `tests/search_api/test_dedup.py`

**Interfaces:**
- Consumes: `JobListing` from `job_search_email.models`
- Produces: `deduplicate(jobs: list[JobListing]) -> list[JobListing]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/search_api/test_dedup.py
from job_search_email.models import JobListing
from job_search_email.search_api.dedup import deduplicate


def _job(**kwargs) -> JobListing:
    defaults = dict(
        title="Manager", company="NHS", location="Bristol",
        salary_min=60000, description="", url="https://example.com",
        source="reed", employment_type="full-time",
    )
    return JobListing(**{**defaults, **kwargs})


def test_unique_jobs_all_kept():
    jobs = [
        _job(title="Manager", company="NHS"),
        _job(title="Director", company="NHS"),
        _job(title="Manager", company="Accenture"),
    ]
    assert len(deduplicate(jobs)) == 3


def test_exact_duplicate_removed_first_wins():
    jobs = [
        _job(title="Manager", company="NHS", source="reed"),
        _job(title="Manager", company="NHS", source="linkedin"),
    ]
    result = deduplicate(jobs)
    assert len(result) == 1
    assert result[0].source == "reed"


def test_case_insensitive_dedup():
    jobs = [
        _job(title="Digital Manager", company="NHS Bristol"),
        _job(title="digital manager", company="nhs bristol"),
    ]
    assert len(deduplicate(jobs)) == 1


def test_whitespace_stripped_before_dedup():
    jobs = [
        _job(title="  Manager  ", company="NHS"),
        _job(title="Manager", company="NHS"),
    ]
    assert len(deduplicate(jobs)) == 1


def test_empty_list_returns_empty():
    assert deduplicate([]) == []
```

- [ ] **Step 2: Create package `__init__.py` files and run tests to verify they fail**

```powershell
New-Item -ItemType File src/job_search_email/search_api/__init__.py
New-Item -ItemType Directory tests/search_api
New-Item -ItemType File tests/search_api/__init__.py
pytest tests/search_api/test_dedup.py -v
```
Expected: `ModuleNotFoundError: No module named 'job_search_email.search_api.dedup'`

- [ ] **Step 3: Implement `dedup.py`**

```python
# src/job_search_email/search_api/dedup.py
from ..models import JobListing


def deduplicate(jobs: list[JobListing]) -> list[JobListing]:
    seen: set[tuple[str, str]] = set()
    result: list[JobListing] = []
    for job in jobs:
        key = (job.title.lower().strip(), job.company.lower().strip())
        if key not in seen:
            seen.add(key)
            result.append(job)
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/search_api/test_dedup.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/job_search_email/search_api/__init__.py src/job_search_email/search_api/dedup.py tests/search_api/__init__.py tests/search_api/test_dedup.py
git commit -m "feat: add deduplication module for job listings"
```

---

### Task 3: Reed API searcher

**Files:**
- Create: `src/job_search_email/search_api/reed.py`
- Test: `tests/search_api/test_reed.py`

**Interfaces:**
- Consumes: `Profile` from `job_search_email.models`; `REED_API_KEY` env var
- Produces: `search(query: str, profile: Profile) -> list[JobListing]`

Reed API reference: `GET https://www.reed.co.uk/api/1.0/search` with HTTP Basic Auth `(api_key, "")`. Response shape: `{"results": [{jobTitle, employerName, locationName, minimumSalary, jobDescription, jobUrl, fullTime, partTime, contract, permanent}]}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/search_api/test_reed.py
from unittest.mock import patch, MagicMock
import pytest
from job_search_email.models import Profile
from job_search_email.search_api.reed import search


PROFILE = Profile(
    name="Jie", current_role="NHS Digital", about="", seniority="Senior",
    industry="NHS", skills=[], previous_roles=[], target_roles=[],
    open_to=[], not_open_to=[], qualifications=[],
    employment_type=["full-time"], location="Bristol", min_salary=60000,
)

REED_RESPONSE = {
    "results": [
        {
            "jobId": 12345,
            "jobTitle": "Digital Transformation Manager",
            "employerName": "NHS Bristol",
            "locationName": "Bristol, BS1",
            "minimumSalary": 65000,
            "maximumSalary": 75000,
            "jobDescription": "Lead digital transformation.",
            "jobUrl": "https://www.reed.co.uk/jobs/digital-transformation-manager/12345",
            "fullTime": True,
            "partTime": False,
            "contract": False,
            "permanent": True,
        }
    ]
}


def test_search_returns_job_listings(monkeypatch):
    monkeypatch.setenv("REED_API_KEY", "test-key")
    mock_resp = MagicMock()
    mock_resp.json.return_value = REED_RESPONSE
    mock_resp.raise_for_status.return_value = None

    with patch("job_search_email.search_api.reed.requests.get", return_value=mock_resp):
        result = search("digital transformation manager", PROFILE)

    assert len(result) == 1
    job = result[0]
    assert job.title == "Digital Transformation Manager"
    assert job.company == "NHS Bristol"
    assert job.location == "Bristol, BS1"
    assert job.salary_min == 65000
    assert job.url == "https://www.reed.co.uk/jobs/digital-transformation-manager/12345"
    assert job.source == "reed"
    assert job.employment_type == "full-time"


def test_search_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("REED_API_KEY", raising=False)
    with pytest.raises(ValueError, match="REED_API_KEY"):
        search("manager", PROFILE)


def test_search_empty_results(monkeypatch):
    monkeypatch.setenv("REED_API_KEY", "test-key")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": []}
    mock_resp.raise_for_status.return_value = None

    with patch("job_search_email.search_api.reed.requests.get", return_value=mock_resp):
        result = search("no results query", PROFILE)

    assert result == []


def test_search_passes_correct_params(monkeypatch):
    monkeypatch.setenv("REED_API_KEY", "test-key")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"results": []}
    mock_resp.raise_for_status.return_value = None

    with patch("job_search_email.search_api.reed.requests.get", return_value=mock_resp) as mock_get:
        search("business manager", PROFILE)

    params = mock_get.call_args.kwargs["params"]
    assert params["keywords"] == "business manager"
    assert params["locationName"] == "Bristol"
    assert params["minimumSalary"] == 60000
    assert params["distancefromLocation"] == 50
    assert params["resultsToTake"] == 100


def test_employment_type_part_time(monkeypatch):
    monkeypatch.setenv("REED_API_KEY", "test-key")
    response = {"results": [{**REED_RESPONSE["results"][0], "fullTime": False, "partTime": True}]}
    mock_resp = MagicMock()
    mock_resp.json.return_value = response
    mock_resp.raise_for_status.return_value = None

    with patch("job_search_email.search_api.reed.requests.get", return_value=mock_resp):
        result = search("manager", PROFILE)

    assert result[0].employment_type == "part-time"


def test_employment_type_unknown_returns_none(monkeypatch):
    monkeypatch.setenv("REED_API_KEY", "test-key")
    response = {"results": [{**REED_RESPONSE["results"][0], "fullTime": False, "partTime": False, "contract": False, "permanent": False}]}
    mock_resp = MagicMock()
    mock_resp.json.return_value = response
    mock_resp.raise_for_status.return_value = None

    with patch("job_search_email.search_api.reed.requests.get", return_value=mock_resp):
        result = search("manager", PROFILE)

    assert result[0].employment_type is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/search_api/test_reed.py -v
```
Expected: `ModuleNotFoundError: No module named 'job_search_email.search_api.reed'`

- [ ] **Step 3: Implement `reed.py`**

```python
# src/job_search_email/search_api/reed.py
import os
import requests
from ..models import JobListing, Profile

_REED_URL = "https://www.reed.co.uk/api/1.0/search"


def search(query: str, profile: Profile) -> list[JobListing]:
    api_key = os.environ.get("REED_API_KEY")
    if not api_key:
        raise ValueError("REED_API_KEY environment variable is not set")

    params = {
        "keywords": query,
        "locationName": profile.location,
        "distancefromLocation": 50,
        "minimumSalary": profile.min_salary,
        "resultsToTake": 100,
    }
    response = requests.get(_REED_URL, params=params, auth=(api_key, ""))
    response.raise_for_status()

    return [_to_listing(item) for item in response.json().get("results", [])]


def _to_listing(item: dict) -> JobListing:
    return JobListing(
        title=item.get("jobTitle", ""),
        company=item.get("employerName", ""),
        location=item.get("locationName", ""),
        salary_min=item.get("minimumSalary"),
        description=item.get("jobDescription", ""),
        url=item.get("jobUrl", ""),
        source="reed",
        employment_type=_parse_employment_type(item),
    )


def _parse_employment_type(item: dict) -> str | None:
    if item.get("fullTime"):
        return "full-time"
    if item.get("partTime"):
        return "part-time"
    if item.get("contract"):
        return "contract"
    if item.get("permanent"):
        return "permanent"
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/search_api/test_reed.py -v
```
Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/job_search_email/search_api/reed.py tests/search_api/test_reed.py
git commit -m "feat: add Reed API job searcher"
```

---

### Task 4: NHS Jobs scraper

**Files:**
- Create: `src/job_search_email/search_api/nhs_jobs.py`
- Test: `tests/search_api/test_nhs_jobs.py`

**Interfaces:**
- Consumes: `Profile` from `job_search_email.models`
- Produces: `search(query: str, profile: Profile) -> list[JobListing]`

**Selector note:** The selectors below target NHSUK Design System components used by NHS Jobs as of June 2026. If the scraper returns empty results against the live site, inspect the page source at `https://jobs.nhs.uk/candidate/search/results?keyword=manager&location=Bristol&distance=50&language=en` and update `.nhsuk-card.nhsuk-card--clickable`, `a.nhsuk-card__link`, and `p.nhsuk-body` accordingly.

- [ ] **Step 1: Write the failing tests**

```python
# tests/search_api/test_nhs_jobs.py
from unittest.mock import patch, MagicMock
from job_search_email.models import Profile
from job_search_email.search_api.nhs_jobs import search, _parse_salary


PROFILE = Profile(
    name="Jie", current_role="NHS Digital", about="", seniority="Senior",
    industry="NHS", skills=[], previous_roles=[], target_roles=[],
    open_to=[], not_open_to=[], qualifications=[],
    employment_type=["full-time"], location="Bristol", min_salary=60000,
)

NHS_HTML = """
<html><body><ul>
  <li>
    <div class="nhsuk-card nhsuk-card--clickable">
      <div class="nhsuk-card__content">
        <h2><a class="nhsuk-card__link" href="/candidate/jobadvert/view/1001">
          Digital Transformation Manager
        </a></h2>
        <p class="nhsuk-body">NHS Bristol Trust</p>
        <p class="nhsuk-body">Bristol, BS1 2AA</p>
        <p class="nhsuk-body">£65,000 - £75,000 a year</p>
      </div>
    </div>
  </li>
</ul></body></html>
"""


def test_search_returns_job_listings(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.text = NHS_HTML
    mock_resp.raise_for_status.return_value = None

    with patch("job_search_email.search_api.nhs_jobs.requests.get", return_value=mock_resp):
        result = search("digital transformation", PROFILE)

    assert len(result) == 1
    job = result[0]
    assert job.title == "Digital Transformation Manager"
    assert job.company == "NHS Bristol Trust"
    assert job.location == "Bristol, BS1 2AA"
    assert job.salary_min == 65000
    assert job.url == "https://jobs.nhs.uk/candidate/jobadvert/view/1001"
    assert job.source == "nhs"
    assert job.description == ""
    assert job.employment_type is None


def test_search_filters_below_min_salary(monkeypatch):
    html = NHS_HTML.replace("£65,000 - £75,000 a year", "£40,000 a year")
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status.return_value = None

    with patch("job_search_email.search_api.nhs_jobs.requests.get", return_value=mock_resp):
        result = search("digital transformation", PROFILE)

    assert result == []


def test_search_includes_job_with_unknown_salary(monkeypatch):
    html = NHS_HTML.replace("£65,000 - £75,000 a year", "Competitive")
    mock_resp = MagicMock()
    mock_resp.text = html
    mock_resp.raise_for_status.return_value = None

    with patch("job_search_email.search_api.nhs_jobs.requests.get", return_value=mock_resp):
        result = search("digital transformation", PROFILE)

    assert len(result) == 1
    assert result[0].salary_min is None


def test_parse_salary_extracts_first_pound_figure():
    assert _parse_salary("£65,000 - £75,000 a year") == 65000
    assert _parse_salary("£60,000 pa") == 60000
    assert _parse_salary("Competitive") is None
    assert _parse_salary("") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/search_api/test_nhs_jobs.py -v
```
Expected: `ModuleNotFoundError: No module named 'job_search_email.search_api.nhs_jobs'`

- [ ] **Step 3: Implement `nhs_jobs.py`**

```python
# src/job_search_email/search_api/nhs_jobs.py
import re
import requests
from bs4 import BeautifulSoup
from ..models import JobListing, Profile

_NHS_URL = "https://jobs.nhs.uk/candidate/search/results"
_SALARY_RE = re.compile(r'£([\d,]+)')


def search(query: str, profile: Profile) -> list[JobListing]:
    params = {"keyword": query, "location": profile.location, "distance": 50, "language": "en"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml",
    }
    response = requests.get(_NHS_URL, params=params, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    results = []

    for card in soup.select(".nhsuk-card.nhsuk-card--clickable"):
        link = card.select_one("a.nhsuk-card__link")
        paragraphs = card.select("p.nhsuk-body")

        title = link.get_text(strip=True) if link else ""
        href = link.get("href", "") if link else ""
        company = paragraphs[0].get_text(strip=True) if len(paragraphs) > 0 else ""
        location = paragraphs[1].get_text(strip=True) if len(paragraphs) > 1 else ""
        salary_text = paragraphs[2].get_text(strip=True) if len(paragraphs) > 2 else ""

        salary_min = _parse_salary(salary_text)
        if salary_min is not None and salary_min < profile.min_salary:
            continue

        results.append(JobListing(
            title=title,
            company=company,
            location=location,
            salary_min=salary_min,
            description="",
            url=f"https://jobs.nhs.uk{href}" if href else "",
            source="nhs",
            employment_type=None,
        ))

    return results


def _parse_salary(text: str) -> int | None:
    match = _SALARY_RE.search(text)
    if match:
        return int(match.group(1).replace(",", ""))
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/search_api/test_nhs_jobs.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/job_search_email/search_api/nhs_jobs.py tests/search_api/test_nhs_jobs.py
git commit -m "feat: add NHS Jobs web scraper"
```

---

### Task 5: jobspy searcher (LinkedIn + Indeed)

**Files:**
- Create: `src/job_search_email/search_api/jobspy_searcher.py`
- Test: `tests/search_api/test_jobspy_searcher.py`

**Interfaces:**
- Consumes: `Profile` from `job_search_email.models`; `jobspy.scrape_jobs`
- Produces: `search(query: str, profile: Profile) -> list[JobListing]`

`scrape_jobs` returns a pandas `DataFrame` with columns: `site`, `job_url`, `title`, `company`, `location`, `description`, `min_amount`, `max_amount`, `job_type`, `currency`. `site` values are `"linkedin"` or `"indeed"`. `min_amount` is `float` (may be `NaN`). `job_type` values are `"fulltime"`, `"parttime"`, `"contract"`, `"internship"` (may be `None`/`NaN`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/search_api/test_jobspy_searcher.py
from unittest.mock import patch
import pandas as pd
from job_search_email.models import Profile
from job_search_email.search_api.jobspy_searcher import search


PROFILE = Profile(
    name="Jie", current_role="NHS Digital", about="", seniority="Senior",
    industry="NHS", skills=[], previous_roles=[], target_roles=[],
    open_to=[], not_open_to=[], qualifications=[],
    employment_type=["full-time"], location="Bristol", min_salary=60000,
)

SAMPLE_DF = pd.DataFrame([
    {
        "site": "linkedin",
        "job_url": "https://linkedin.com/jobs/1",
        "title": "Digital Transformation Manager",
        "company": "NHS Bristol",
        "location": "Bristol, UK",
        "description": "Lead digital transformation.",
        "min_amount": 65000.0,
        "max_amount": 75000.0,
        "job_type": "fulltime",
        "currency": "GBP",
    },
    {
        "site": "indeed",
        "job_url": "https://indeed.com/jobs/2",
        "title": "Business Manager",
        "company": "Accenture",
        "location": "Bristol, UK",
        "description": "Consulting role.",
        "min_amount": 55000.0,  # below min_salary — must be filtered
        "max_amount": 65000.0,
        "job_type": "fulltime",
        "currency": "GBP",
    },
])


def test_search_returns_job_listings():
    with patch("job_search_email.search_api.jobspy_searcher.scrape_jobs", return_value=SAMPLE_DF):
        result = search("digital transformation", PROFILE)

    assert len(result) == 1
    job = result[0]
    assert job.title == "Digital Transformation Manager"
    assert job.company == "NHS Bristol"
    assert job.salary_min == 65000
    assert job.source == "linkedin"
    assert job.employment_type == "fulltime"
    assert job.url == "https://linkedin.com/jobs/1"


def test_search_filters_below_min_salary():
    with patch("job_search_email.search_api.jobspy_searcher.scrape_jobs", return_value=SAMPLE_DF):
        result = search("manager", PROFILE)

    assert all(j.title != "Business Manager" for j in result)


def test_search_salary_regex_fallback():
    df = pd.DataFrame([{
        "site": "indeed",
        "job_url": "https://indeed.com/jobs/3",
        "title": "Project Manager",
        "company": "NHS",
        "location": "Bristol",
        "description": "Salary: £70,000 per annum",
        "min_amount": float("nan"),
        "max_amount": float("nan"),
        "job_type": None,
        "currency": "GBP",
    }])
    with patch("job_search_email.search_api.jobspy_searcher.scrape_jobs", return_value=df):
        result = search("project manager", PROFILE)

    assert len(result) == 1
    assert result[0].salary_min == 70000


def test_search_passes_correct_params():
    with patch("job_search_email.search_api.jobspy_searcher.scrape_jobs", return_value=pd.DataFrame()) as mock_scrape:
        search("business manager", PROFILE)

    kwargs = mock_scrape.call_args.kwargs
    assert kwargs["search_term"] == "business manager"
    assert kwargs["location"] == "Bristol"
    assert kwargs["site_name"] == ["linkedin", "indeed"]
    assert kwargs["distance"] == 50
    assert kwargs["country_indeed"] == "UK"


def test_search_returns_empty_on_empty_dataframe():
    with patch("job_search_email.search_api.jobspy_searcher.scrape_jobs", return_value=pd.DataFrame()):
        result = search("nothing", PROFILE)
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/search_api/test_jobspy_searcher.py -v
```
Expected: `ModuleNotFoundError: No module named 'job_search_email.search_api.jobspy_searcher'`

- [ ] **Step 3: Implement `jobspy_searcher.py`**

```python
# src/job_search_email/search_api/jobspy_searcher.py
import math
import re
from jobspy import scrape_jobs
from ..models import JobListing, Profile

_SALARY_RE = re.compile(r'£([\d,]+)(k)?', re.IGNORECASE)


def search(query: str, profile: Profile) -> list[JobListing]:
    df = scrape_jobs(
        site_name=["linkedin", "indeed"],
        search_term=query,
        location=profile.location,
        distance=50,
        results_wanted=50,
        country_indeed="UK",
    )

    if df.empty:
        return []

    results = []
    for _, row in df.iterrows():
        salary_min = _extract_salary_min(row)
        if salary_min is not None and salary_min < profile.min_salary:
            continue

        results.append(JobListing(
            title=_str(row.get("title")),
            company=_str(row.get("company")),
            location=_str(row.get("location")),
            salary_min=salary_min,
            description=_str(row.get("description")),
            url=_str(row.get("job_url")),
            source=_str(row.get("site")).lower(),
            employment_type=_str(row.get("job_type")) or None,
        ))

    return results


def _str(value) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value)


def _extract_salary_min(row) -> int | None:
    min_amount = row.get("min_amount")
    if min_amount is not None and not (isinstance(min_amount, float) and math.isnan(min_amount)):
        return int(min_amount)

    match = _SALARY_RE.search(_str(row.get("description")))
    if match:
        value = int(match.group(1).replace(",", ""))
        if match.group(2):
            value *= 1000
        return value

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/search_api/test_jobspy_searcher.py -v
```
Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/job_search_email/search_api/jobspy_searcher.py tests/search_api/test_jobspy_searcher.py
git commit -m "feat: add jobspy searcher for LinkedIn and Indeed"
```

---

### Task 6: Fetcher orchestrator

**Files:**
- Create: `src/job_search_email/search_api/fetcher.py`
- Test: `tests/search_api/test_fetcher.py`

**Interfaces:**
- Consumes: `search(query, profile)` from `jobspy_searcher`, `reed`, `nhs_jobs`; `deduplicate` from `dedup`
- Produces: `fetch_all_jobs(plan: SearchPlan, profile: Profile) -> list[JobListing]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/search_api/test_fetcher.py
from unittest.mock import patch
from job_search_email.models import JobListing, Profile, SearchPlan
from job_search_email.search_api.fetcher import fetch_all_jobs


PROFILE = Profile(
    name="Jie", current_role="NHS Digital", about="", seniority="Senior",
    industry="NHS", skills=[], previous_roles=[], target_roles=[],
    open_to=[], not_open_to=[], qualifications=[],
    employment_type=["full-time"], location="Bristol", min_salary=60000,
)

PLAN = SearchPlan(
    profile_fingerprint="abc123",
    queries=["business manager", "digital transformation"],
    exclusions={}, nhs_rules={}, evaluator_notes=[],
)


def _job(title: str, source: str) -> JobListing:
    return JobListing(
        title=title, company="NHS", location="Bristol",
        salary_min=65000, description="", url="https://example.com",
        source=source, employment_type="full-time",
    )


def test_fetch_calls_all_searchers_with_all_queries():
    with (
        patch("job_search_email.search_api.fetcher.jobspy_searcher.search", return_value=[]) as mock_js,
        patch("job_search_email.search_api.fetcher.reed.search", return_value=[]) as mock_reed,
        patch("job_search_email.search_api.fetcher.nhs_jobs.search", return_value=[]) as mock_nhs,
    ):
        fetch_all_jobs(PLAN, PROFILE)

    assert mock_js.call_count == 2   # 2 queries × 1 searcher
    assert mock_reed.call_count == 2
    assert mock_nhs.call_count == 2


def test_fetch_concatenates_and_deduplicates():
    with (
        patch("job_search_email.search_api.fetcher.jobspy_searcher.search", return_value=[_job("Job A", "linkedin")]),
        patch("job_search_email.search_api.fetcher.reed.search", return_value=[_job("Job B", "reed")]),
        patch("job_search_email.search_api.fetcher.nhs_jobs.search", return_value=[_job("Job C", "nhs")]),
    ):
        result = fetch_all_jobs(PLAN, PROFILE)

    titles = {j.title for j in result}
    assert titles == {"Job A", "Job B", "Job C"}


def test_fetch_deduplicates_cross_source():
    with (
        patch("job_search_email.search_api.fetcher.jobspy_searcher.search", return_value=[_job("Same Job", "linkedin")]),
        patch("job_search_email.search_api.fetcher.reed.search", return_value=[_job("Same Job", "reed")]),
        patch("job_search_email.search_api.fetcher.nhs_jobs.search", return_value=[]),
    ):
        result = fetch_all_jobs(PLAN, PROFILE)

    same = [j for j in result if j.title == "Same Job"]
    assert len(same) == 1


def test_fetch_continues_on_per_task_failure(capsys):
    def fail(query, profile):
        raise ConnectionError("Reed API unreachable")

    with (
        patch("job_search_email.search_api.fetcher.jobspy_searcher.search", return_value=[]),
        patch("job_search_email.search_api.fetcher.reed.search", side_effect=fail),
        patch("job_search_email.search_api.fetcher.nhs_jobs.search", return_value=[_job("NHS Job", "nhs")]),
    ):
        result = fetch_all_jobs(PLAN, PROFILE)

    assert any(j.source == "nhs" for j in result)
    assert "reed" in capsys.readouterr().err.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/search_api/test_fetcher.py -v
```
Expected: `ModuleNotFoundError: No module named 'job_search_email.search_api.fetcher'`

- [ ] **Step 3: Implement `fetcher.py`**

```python
# src/job_search_email/search_api/fetcher.py
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from ..models import JobListing, Profile, SearchPlan
from . import jobspy_searcher, reed, nhs_jobs
from .dedup import deduplicate

_SEARCHERS = [jobspy_searcher, reed, nhs_jobs]


def fetch_all_jobs(plan: SearchPlan, profile: Profile) -> list[JobListing]:
    tasks = [
        (searcher, query)
        for searcher in _SEARCHERS
        for query in plan.queries
    ]

    all_jobs: list[JobListing] = []

    with ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(searcher.search, query, profile): (searcher.__name__, query)
            for searcher, query in tasks
        }
        for future in as_completed(futures):
            module_name, query = futures[future]
            try:
                all_jobs.extend(future.result())
            except Exception as exc:
                print(f"[{module_name}] query {query!r} failed: {exc}", file=sys.stderr)

    return deduplicate(all_jobs)
```

- [ ] **Step 4: Run full test suite to verify all tasks pass**

```bash
pytest -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/job_search_email/search_api/fetcher.py tests/search_api/test_fetcher.py
git commit -m "feat: add concurrent job fetcher orchestrator"
```

---

### Task 7: Wire up `main.py`

**Files:**
- Modify: `src/job_search_email/main.py`

**Interfaces:**
- Consumes: `fetch_all_jobs(plan, profile)` from `search_api.fetcher`; `SearchPlan` from `models`
- Produces: `job_results.json` in the working directory

- [ ] **Step 1: Add the import, path constant, and update `main()`**

Replace the entire contents of `src/job_search_email/main.py` with:

```python
# src/job_search_email/main.py
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from .evaluator_notes import get_evaluator_notes
from .exclusions import get_exclusions
from .models import Profile, SearchPlan
from .nhs_rules import get_nhs_rules
from .queries import generate_queries
from .search_api.fetcher import fetch_all_jobs

ROOT = Path.cwd()
PROFILE_PATH = ROOT / "profile.yaml"
CACHE_PATH = ROOT / "search_plan_cache.json"
PLAN_PATH = ROOT / "search_plan.json"
RESULTS_PATH = ROOT / "job_results.json"


def load_profile(path: Path = PROFILE_PATH) -> Profile:
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
    )


def fingerprint_profile(profile: Profile) -> str:
    canonical = json.dumps(asdict(profile), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def generate_search_plan(profile: Profile, fingerprint: str) -> SearchPlan:
    return SearchPlan(
        profile_fingerprint=fingerprint,
        queries=generate_queries(profile),
        exclusions=get_exclusions(profile),
        nhs_rules=get_nhs_rules(),
        evaluator_notes=get_evaluator_notes(profile),
    )


def load_cached_plan(cache_path: Path = CACHE_PATH, fingerprint: str = "") -> dict[str, Any] | None:
    if not cache_path.exists():
        return None

    with cache_path.open("r", encoding="utf-8") as handle:
        cache = json.load(handle)

    return cache.get(fingerprint)


def save_cached_plan(plan: SearchPlan, cache_path: Path = CACHE_PATH) -> None:
    cache: dict[str, Any] = {}
    if cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as handle:
            try:
                cache = json.load(handle)
            except json.JSONDecodeError:
                cache = {}

    cache[plan.profile_fingerprint] = asdict(plan)
    with cache_path.open("w", encoding="utf-8") as handle:
        json.dump(cache, handle, indent=2)


def write_search_plan(plan: SearchPlan, path: Path = PLAN_PATH) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(asdict(plan), handle, indent=2)


def main() -> None:
    profile = load_profile()
    fingerprint = fingerprint_profile(profile)
    cached = load_cached_plan(fingerprint=fingerprint)

    if cached:
        plan = SearchPlan(**cached)
    else:
        plan = generate_search_plan(profile, fingerprint)
        save_cached_plan(plan)
        write_search_plan(plan)

    print("Job search plan ready:")
    print(f"- profile: {profile.name}")
    print(f"- plan fingerprint: {fingerprint}")
    print(f"- queries: {len(plan.queries)}")

    print("Fetching jobs...")
    jobs = fetch_all_jobs(plan, profile)
    with RESULTS_PATH.open("w", encoding="utf-8") as handle:
        json.dump([asdict(job) for job in jobs], handle, indent=2)
    print(f"- jobs fetched: {len(jobs)}")
    print(f"- results written to: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run full test suite**

```bash
pytest -v
```
Expected: all tests PASS (existing `test_main.py` tests must still pass).

- [ ] **Step 3: Commit**

```bash
git add src/job_search_email/main.py
git commit -m "feat: wire fetch_all_jobs into main, write job_results.json"
```
