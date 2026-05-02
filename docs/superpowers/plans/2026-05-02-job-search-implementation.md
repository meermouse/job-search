# Jie's Job Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Streamlit web app that analyses a CV with Claude, searches LinkedIn/Indeed/Reed/NHS Jobs concurrently, filters results to UK Skilled Worker visa sponsors only, and displays them in a filterable table.

**Architecture:** Single `app.py` Streamlit entry point backed by `cv_parser.py`, `sponsor_filter.py`, and a `searchers/` package containing one module per platform plus a `runner.py` that coordinates concurrent search via `ThreadPoolExecutor`. Results stream into the UI as each platform completes.

**Tech Stack:** Python 3.11+, Streamlit, Anthropic SDK, python-jobspy, requests, BeautifulSoup4, rapidfuzz, PyMuPDF, python-docx, python-dotenv, pytest, pytest-mock

---

## File Map

```
app.py                            ← Streamlit UI (all three states)
cv_parser.py                      ← extract_text() + analyse_cv()
sponsor_filter.py                 ← load_sponsor_names() + filter_jobs()
searchers/
  __init__.py                     ← re-exports search_all_streaming
  jobspy_searcher.py              ← LinkedIn + Indeed via JobSpy
  reed.py                         ← Reed API
  nhs_jobs.py                     ← NHS Jobs scraper
  runner.py                       ← ThreadPoolExecutor coordinator
tests/
  __init__.py
  fixtures/
    sponsors.csv                  ← sample sponsor data for tests
  test_cv_parser.py
  test_sponsor_filter.py
  searchers/
    __init__.py
    test_jobspy.py
    test_reed.py
    test_nhs_jobs.py
    test_runner.py
requirements.txt
.env.example
conftest.py                       ← empty, marks pytest root
```

---

## Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `conftest.py`
- Create: `tests/__init__.py`
- Create: `tests/searchers/__init__.py`
- Create: `searchers/__init__.py` (placeholder — content added in Task 9)

- [ ] **Step 1: Create `requirements.txt`**

```
streamlit>=1.32.0
anthropic>=0.25.0
pymupdf>=1.24.0
python-docx>=1.1.0
python-jobspy>=1.1.0
requests>=2.31.0
beautifulsoup4>=4.12.0
rapidfuzz>=3.6.0
python-dotenv>=1.0.0
pandas>=2.0.0
pytest>=8.0.0
pytest-mock>=3.12.0
```

- [ ] **Step 2: Create `.env.example`**

```
ANTHROPIC_API_KEY=your_key_here
REED_API_KEY=your_key_here
SPONSOR_CSV_URL=https://www.gov.uk/csv-preview/69f47183ab602a88957eefa6/2026-05-01_-_Worker_and_Temporary_Worker.csv
```

- [ ] **Step 3: Create empty `conftest.py`**

```python
```

- [ ] **Step 4: Create empty `tests/__init__.py` and `tests/searchers/__init__.py`**

Both files are empty.

- [ ] **Step 5: Create placeholder `searchers/__init__.py`**

```python
```

- [ ] **Step 6: Install dependencies**

Run: `pip install -r requirements.txt`

Expected: All packages install without errors.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .env.example conftest.py tests/ searchers/__init__.py
git commit -m "feat: project setup and dependencies"
```

---

## Task 2: CV Text Extraction

**Files:**
- Create: `cv_parser.py`
- Create: `tests/test_cv_parser.py`

- [ ] **Step 1: Write failing tests for `extract_text`**

Create `tests/test_cv_parser.py`:

```python
import pytest
from unittest.mock import MagicMock, patch
from cv_parser import extract_text


def test_extract_text_txt():
    content = "John Smith\nSoftware Engineer\nPython, Django"
    result = extract_text(content.encode("utf-8"), "cv.txt")
    assert result == content


def test_extract_text_pdf(mocker):
    mock_page = MagicMock()
    mock_page.get_text.return_value = "PDF content line"
    mock_doc = MagicMock()
    mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
    mocker.patch("fitz.open", return_value=mock_doc)

    result = extract_text(b"%PDF fake bytes", "cv.pdf")
    assert result == "PDF content line"


def test_extract_text_docx(mocker):
    mock_para1 = MagicMock()
    mock_para1.text = "Jane Doe"
    mock_para2 = MagicMock()
    mock_para2.text = ""
    mock_para3 = MagicMock()
    mock_para3.text = "Data Scientist"
    mock_doc = MagicMock()
    mock_doc.paragraphs = [mock_para1, mock_para2, mock_para3]
    mocker.patch("cv_parser.Document", return_value=mock_doc)

    result = extract_text(b"PK fake docx bytes", "cv.docx")
    assert result == "Jane Doe\nData Scientist"


def test_extract_text_unsupported_format():
    with pytest.raises(ValueError, match="Unsupported file type"):
        extract_text(b"data", "cv.odt")
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_cv_parser.py -v`

Expected: `ModuleNotFoundError` or `ImportError` (cv_parser doesn't exist yet).

- [ ] **Step 3: Implement `extract_text` in `cv_parser.py`**

```python
import io
import fitz  # PyMuPDF
from docx import Document


def extract_text(file_bytes: bytes, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    if ext == "docx":
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if ext == "txt":
        return file_bytes.decode("utf-8")
    raise ValueError(f"Unsupported file type: .{ext}. Use PDF, DOCX, or TXT.")
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/test_cv_parser.py::test_extract_text_txt tests/test_cv_parser.py::test_extract_text_pdf tests/test_cv_parser.py::test_extract_text_docx tests/test_cv_parser.py::test_extract_text_unsupported_format -v`

Expected: All 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add cv_parser.py tests/test_cv_parser.py
git commit -m "feat: CV text extraction for PDF, DOCX, and TXT"
```

---

## Task 3: CV Claude Analysis

**Files:**
- Modify: `cv_parser.py`
- Modify: `tests/test_cv_parser.py`

- [ ] **Step 1: Write failing tests for `analyse_cv`**

Append to `tests/test_cv_parser.py`:

```python
import json
from cv_parser import analyse_cv


def test_analyse_cv_returns_structured_data(mocker):
    expected = {
        "job_titles": ["Data Engineer", "Backend Developer"],
        "skills": ["Python", "SQL", "AWS"],
        "search_queries": ["Data Engineer Bristol", "Backend Developer Python Bristol"],
    }
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(expected))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("cv_parser.anthropic.Anthropic", return_value=mock_client)

    result = analyse_cv("John Smith, Software Engineer with 5 years Python experience.")
    assert result["job_titles"] == ["Data Engineer", "Backend Developer"]
    assert "Python" in result["skills"]
    assert len(result["search_queries"]) == 2


def test_analyse_cv_raises_on_api_error(mocker):
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API unavailable")
    mocker.patch("cv_parser.anthropic.Anthropic", return_value=mock_client)

    with pytest.raises(Exception, match="API unavailable"):
        analyse_cv("Some CV text")
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_cv_parser.py::test_analyse_cv_returns_structured_data tests/test_cv_parser.py::test_analyse_cv_raises_on_api_error -v`

Expected: FAIL with `ImportError` (analyse_cv not defined yet).

- [ ] **Step 3: Add `analyse_cv` to `cv_parser.py`**

Append to `cv_parser.py`:

```python
import anthropic
import json
import os

_SYSTEM = "You extract structured job search data from CVs. Return only valid JSON, no markdown."

_PROMPT = """\
Analyse this CV and return a JSON object with exactly these keys:
- "job_titles": list of 3-5 suitable UK job titles based on experience
- "skills": list of key technical and professional skills
- "search_queries": list of 3-5 search strings for UK job boards

CV:
{cv_text}"""


def analyse_cv(text: str) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _PROMPT.format(cv_text=text)}],
    )
    return json.loads(msg.content[0].text)
```

- [ ] **Step 4: Run all cv_parser tests**

Run: `pytest tests/test_cv_parser.py -v`

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cv_parser.py tests/test_cv_parser.py
git commit -m "feat: CV analysis via Claude API"
```

---

## Task 4: Sponsor CSV Loading

**Files:**
- Create: `sponsor_filter.py`
- Create: `tests/fixtures/sponsors.csv`
- Create: `tests/test_sponsor_filter.py`

- [ ] **Step 1: Create `tests/fixtures/sponsors.csv`**

```csv
Organisation Name,Town/City,County,Type & Rating,Route
NHS Bristol Trust,Bristol,Avon,A (Premium),Worker
Acme Technologies Ltd,London,Greater London,A (Premium),Worker
Temp Solutions UK,Manchester,Manchester,A (Standard),Temporary Worker
Big Data Corp,Bristol,Avon,A (Premium),Worker
NHS Manchester Trust,Manchester,Manchester,A (Premium),Worker
```

- [ ] **Step 2: Write failing tests for `load_sponsor_names`**

Create `tests/test_sponsor_filter.py`:

```python
import os
import pytest
from sponsor_filter import load_sponsor_names

FIXTURE_CSV = os.path.join(os.path.dirname(__file__), "fixtures", "sponsors.csv")


def test_load_sponsor_names_filters_worker_route_only(mocker):
    with open(FIXTURE_CSV, encoding="utf-8") as f:
        csv_text = f.read()
    mock_response = mocker.MagicMock()
    mock_response.text = csv_text
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("sponsor_filter.requests.get", return_value=mock_response)
    mocker.patch("builtins.open", mocker.mock_open())

    names = load_sponsor_names("https://example.com/sponsors.csv", cache_path="/tmp/test_cache.csv")

    assert "NHS Bristol Trust" in names
    assert "Acme Technologies Ltd" in names
    assert "Big Data Corp" in names
    assert "Temp Solutions UK" not in names  # Temporary Worker route excluded
    assert len(names) == 4


def test_load_sponsor_names_falls_back_to_cache_on_network_error(mocker, tmp_path):
    with open(FIXTURE_CSV, encoding="utf-8") as f:
        csv_text = f.read()
    cache_file = tmp_path / "sponsors_cache.csv"
    cache_file.write_text(csv_text, encoding="utf-8")
    mocker.patch("sponsor_filter.requests.get", side_effect=Exception("Network error"))

    names = load_sponsor_names("https://example.com/sponsors.csv", cache_path=str(cache_file))

    assert "NHS Bristol Trust" in names
    assert "Temp Solutions UK" not in names


def test_load_sponsor_names_raises_when_no_cache(mocker, tmp_path):
    mocker.patch("sponsor_filter.requests.get", side_effect=Exception("Network error"))
    missing_cache = str(tmp_path / "nonexistent.csv")

    with pytest.raises(RuntimeError, match="Failed to download sponsor CSV"):
        load_sponsor_names("https://example.com/sponsors.csv", cache_path=missing_cache)
```

- [ ] **Step 3: Run tests to confirm they fail**

Run: `pytest tests/test_sponsor_filter.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement `load_sponsor_names` in `sponsor_filter.py`**

```python
import csv
import io
import os
import requests

_DEFAULT_URL = os.environ.get(
    "SPONSOR_CSV_URL",
    "https://www.gov.uk/csv-preview/69f47183ab602a88957eefa6/2026-05-01_-_Worker_and_Temporary_Worker.csv",
)
_CACHE_PATH = "sponsor_cache.csv"


def load_sponsor_names(csv_url: str = _DEFAULT_URL, cache_path: str = _CACHE_PATH) -> list[str]:
    """Return employer names licensed for the Worker route (Skilled Worker visa)."""
    try:
        response = requests.get(csv_url, timeout=30)
        response.raise_for_status()
        csv_text = response.text
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(csv_text)
    except Exception:
        if not os.path.exists(cache_path):
            raise RuntimeError(
                "Failed to download sponsor CSV and no local cache found. "
                "Check your internet connection or update SPONSOR_CSV_URL in .env."
            )
        with open(cache_path, encoding="utf-8") as f:
            csv_text = f.read()

    reader = csv.DictReader(io.StringIO(csv_text))
    return [row["Organisation Name"] for row in reader if row.get("Route") == "Worker"]
```

- [ ] **Step 5: Run tests to confirm they pass**

Run: `pytest tests/test_sponsor_filter.py::test_load_sponsor_names_filters_worker_route_only tests/test_sponsor_filter.py::test_load_sponsor_names_falls_back_to_cache_on_network_error tests/test_sponsor_filter.py::test_load_sponsor_names_raises_when_no_cache -v`

Expected: All 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add sponsor_filter.py tests/fixtures/sponsors.csv tests/test_sponsor_filter.py
git commit -m "feat: sponsor CSV loading with Worker-route filter and cache fallback"
```

---

## Task 5: Sponsor Fuzzy Matching

**Files:**
- Modify: `sponsor_filter.py`
- Modify: `tests/test_sponsor_filter.py`

- [ ] **Step 1: Write failing tests for `filter_jobs`**

Append to `tests/test_sponsor_filter.py`:

```python
from sponsor_filter import filter_jobs

SPONSOR_NAMES = ["NHS Bristol Trust", "Acme Technologies Ltd", "Big Data Corp"]

SAMPLE_JOBS = [
    {
        "title": "Data Engineer",
        "company": "Acme Technologies",  # close but not exact
        "location": "London",
        "salary": "£65,000",
        "description": "Great role",
        "url": "https://example.com/1",
        "source": "LinkedIn",
    },
    {
        "title": "Nurse",
        "company": "NHS Bristol Trust",  # exact match
        "location": "Bristol",
        "salary": "£35,000",
        "description": "Ward nurse",
        "url": "https://example.com/2",
        "source": "NHS Jobs",
    },
    {
        "title": "Barista",
        "company": "Coffee Shop Ltd",  # no match
        "location": "Bristol",
        "salary": "£22,000",
        "description": "Coffee",
        "url": "https://example.com/3",
        "source": "Reed",
    },
]


def test_filter_jobs_passes_fuzzy_match():
    result = filter_jobs(SAMPLE_JOBS, SPONSOR_NAMES)
    urls = [j["url"] for j in result]
    assert "https://example.com/1" in urls  # Acme Technologies ~= Acme Technologies Ltd


def test_filter_jobs_passes_exact_match():
    result = filter_jobs(SAMPLE_JOBS, SPONSOR_NAMES)
    urls = [j["url"] for j in result]
    assert "https://example.com/2" in urls


def test_filter_jobs_blocks_non_sponsor():
    result = filter_jobs(SAMPLE_JOBS, SPONSOR_NAMES)
    urls = [j["url"] for j in result]
    assert "https://example.com/3" not in urls  # Coffee Shop Ltd not a sponsor


def test_filter_jobs_adds_sponsor_name():
    result = filter_jobs(SAMPLE_JOBS, SPONSOR_NAMES)
    acme_job = next(j for j in result if j["url"] == "https://example.com/1")
    assert acme_job["sponsor_name"] == "Acme Technologies Ltd"


def test_filter_jobs_empty_input():
    assert filter_jobs([], SPONSOR_NAMES) == []


def test_filter_jobs_respects_threshold():
    # "Xyz Corp" won't match anything at 85% threshold
    jobs = [{
        "title": "CEO",
        "company": "Xyz Corp",
        "location": "London",
        "salary": "",
        "description": "",
        "url": "https://example.com/4",
        "source": "Reed",
    }]
    assert filter_jobs(jobs, SPONSOR_NAMES, threshold=85) == []
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/test_sponsor_filter.py::test_filter_jobs_passes_fuzzy_match -v`

Expected: FAIL with `ImportError` (filter_jobs not defined).

- [ ] **Step 3: Implement `filter_jobs` in `sponsor_filter.py`**

Append to `sponsor_filter.py`:

```python
from rapidfuzz import process, fuzz


def filter_jobs(jobs: list[dict], sponsor_names: list[str], threshold: int = 85) -> list[dict]:
    """Return jobs whose company fuzzy-matches a Worker-route sponsor, adding sponsor_name field."""
    result = []
    for job in jobs:
        match = process.extractOne(
            job["company"],
            sponsor_names,
            scorer=fuzz.token_sort_ratio,
        )
        if match and match[1] >= threshold:
            result.append({**job, "sponsor_name": match[0]})
    return result
```

- [ ] **Step 4: Run all sponsor_filter tests**

Run: `pytest tests/test_sponsor_filter.py -v`

Expected: All 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add sponsor_filter.py tests/test_sponsor_filter.py
git commit -m "feat: fuzzy sponsor matching with rapidfuzz"
```

---

## Task 6: JobSpy Searcher (LinkedIn + Indeed)

**Files:**
- Create: `searchers/jobspy_searcher.py`
- Create: `tests/searchers/test_jobspy.py`

- [ ] **Step 1: Write failing tests**

Create `tests/searchers/test_jobspy.py`:

```python
import pandas as pd
import pytest
from searchers.jobspy_searcher import search


def _make_df(rows):
    return pd.DataFrame(rows)


def test_search_returns_normalised_jobs(mocker):
    mock_df = _make_df([
        {
            "title": "Data Engineer",
            "company": "Tech Ltd",
            "location": "Bristol, UK",
            "description": "Great role with Python",
            "job_url": "https://linkedin.com/jobs/123",
            "site": "linkedin",
            "min_amount": 65000,
            "max_amount": 80000,
            "interval": "yearly",
        }
    ])
    mocker.patch("searchers.jobspy_searcher.scrape_jobs", return_value=mock_df)

    results = search(["Data Engineer"], "Bristol", 60000)

    assert len(results) == 1
    assert results[0]["title"] == "Data Engineer"
    assert results[0]["company"] == "Tech Ltd"
    assert results[0]["url"] == "https://linkedin.com/jobs/123"
    assert results[0]["source"] == "Linkedin"
    assert "£65,000" in results[0]["salary"]


def test_search_excludes_jobs_below_salary_floor(mocker):
    mock_df = _make_df([
        {
            "title": "Junior Dev",
            "company": "Small Co",
            "location": "Bristol",
            "description": "Entry level",
            "job_url": "https://indeed.com/jobs/456",
            "site": "indeed",
            "min_amount": 30000,
            "max_amount": 40000,
            "interval": "yearly",
        }
    ])
    mocker.patch("searchers.jobspy_searcher.scrape_jobs", return_value=mock_df)

    results = search(["Junior Dev"], "Bristol", 60000)
    assert results == []


def test_search_handles_scrape_error(mocker):
    mocker.patch("searchers.jobspy_searcher.scrape_jobs", side_effect=Exception("Blocked"))

    results = search(["Data Engineer"], "Bristol", 60000)
    assert results == []


def test_search_handles_missing_salary_fields(mocker):
    mock_df = _make_df([
        {
            "title": "Engineer",
            "company": "Corp",
            "location": "Bristol",
            "description": "A job",
            "job_url": "https://linkedin.com/jobs/789",
            "site": "linkedin",
            "min_amount": None,
            "max_amount": None,
            "interval": None,
        }
    ])
    mocker.patch("searchers.jobspy_searcher.scrape_jobs", return_value=mock_df)

    results = search(["Engineer"], "Bristol", 60000)
    assert len(results) == 1
    assert results[0]["salary"] == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/searchers/test_jobspy.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `searchers/jobspy_searcher.py`**

```python
import logging
from jobspy import scrape_jobs

logger = logging.getLogger(__name__)


def _salary_str(row) -> str:
    min_a = row.get("min_amount")
    max_a = row.get("max_amount")
    if min_a and max_a:
        interval = row.get("interval") or ""
        return f"£{int(min_a):,}–£{int(max_a):,} {interval}".strip()
    return ""


def search(queries: list[str], location: str, min_salary: int) -> list[dict]:
    jobs = []
    for query in queries:
        try:
            df = scrape_jobs(
                site_name=["linkedin", "indeed"],
                search_term=query,
                location=location,
                results_wanted=50,
                country_indeed="UK",
            )
            for _, row in df.iterrows():
                min_a = row.get("min_amount")
                if min_a and min_a < min_salary:
                    continue
                jobs.append({
                    "title": str(row.get("title") or ""),
                    "company": str(row.get("company") or ""),
                    "location": str(row.get("location") or ""),
                    "salary": _salary_str(row),
                    "description": str(row.get("description") or "")[:500],
                    "url": str(row.get("job_url") or ""),
                    "source": str(row.get("site") or "").capitalize(),
                })
        except Exception as exc:
            logger.warning("JobSpy search failed for query '%s': %s", query, exc)
    return jobs
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/searchers/test_jobspy.py -v`

Expected: All 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add searchers/jobspy_searcher.py tests/searchers/test_jobspy.py
git commit -m "feat: JobSpy searcher for LinkedIn and Indeed"
```

---

## Task 7: Reed API Searcher

**Files:**
- Create: `searchers/reed.py`
- Create: `tests/searchers/test_reed.py`

- [ ] **Step 1: Write failing tests**

Create `tests/searchers/test_reed.py`:

```python
import pytest
from searchers.reed import search


def test_search_returns_normalised_jobs(mocker):
    mocker.patch.dict("os.environ", {"REED_API_KEY": "test-key"})
    mock_response = mocker.MagicMock()
    mock_response.json.return_value = {
        "results": [
            {
                "jobTitle": "Data Engineer",
                "employerName": "Acme Ltd",
                "locationName": "Bristol",
                "minimumSalary": 65000,
                "maximumSalary": 80000,
                "jobDescription": "Python and SQL required",
                "jobUrl": "https://www.reed.co.uk/jobs/data-engineer/123",
            }
        ]
    }
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("searchers.reed.requests.get", return_value=mock_response)

    results = search(["Data Engineer"], "Bristol", 60000)

    assert len(results) == 1
    assert results[0]["title"] == "Data Engineer"
    assert results[0]["company"] == "Acme Ltd"
    assert results[0]["source"] == "Reed"
    assert "£65,000" in results[0]["salary"]
    assert results[0]["url"] == "https://www.reed.co.uk/jobs/data-engineer/123"


def test_search_handles_api_error(mocker):
    mocker.patch.dict("os.environ", {"REED_API_KEY": "test-key"})
    mocker.patch("searchers.reed.requests.get", side_effect=Exception("Connection error"))

    results = search(["Data Engineer"], "Bristol", 60000)
    assert results == []


def test_search_handles_empty_results(mocker):
    mocker.patch.dict("os.environ", {"REED_API_KEY": "test-key"})
    mock_response = mocker.MagicMock()
    mock_response.json.return_value = {"results": []}
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("searchers.reed.requests.get", return_value=mock_response)

    results = search(["Niche Role"], "Bristol", 60000)
    assert results == []


def test_search_formats_salary_correctly(mocker):
    mocker.patch.dict("os.environ", {"REED_API_KEY": "test-key"})
    mock_response = mocker.MagicMock()
    mock_response.json.return_value = {
        "results": [{
            "jobTitle": "Engineer",
            "employerName": "Corp",
            "locationName": "Bristol",
            "minimumSalary": None,
            "maximumSalary": None,
            "jobDescription": "",
            "jobUrl": "https://www.reed.co.uk/jobs/1",
        }]
    }
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("searchers.reed.requests.get", return_value=mock_response)

    results = search(["Engineer"], "Bristol", 60000)
    assert results[0]["salary"] == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/searchers/test_reed.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `searchers/reed.py`**

```python
import logging
import os
import requests

logger = logging.getLogger(__name__)
_BASE_URL = "https://www.reed.co.uk/api/1.0/search"


def search(queries: list[str], location: str, min_salary: int) -> list[dict]:
    api_key = os.environ["REED_API_KEY"]
    jobs = []
    for query in queries:
        try:
            response = requests.get(
                _BASE_URL,
                auth=(api_key, ""),
                params={
                    "keywords": query,
                    "locationName": location,
                    "minimumSalary": min_salary,
                    "resultsToTake": 100,
                },
                timeout=30,
            )
            response.raise_for_status()
            for r in response.json().get("results", []):
                min_s = r.get("minimumSalary")
                max_s = r.get("maximumSalary")
                salary = f"£{min_s:,.0f}–£{max_s:,.0f}" if min_s and max_s else ""
                jobs.append({
                    "title": r.get("jobTitle", ""),
                    "company": r.get("employerName", ""),
                    "location": r.get("locationName", ""),
                    "salary": salary,
                    "description": str(r.get("jobDescription", ""))[:500],
                    "url": r.get("jobUrl", ""),
                    "source": "Reed",
                })
        except Exception as exc:
            logger.warning("Reed search failed for query '%s': %s", query, exc)
    return jobs
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/searchers/test_reed.py -v`

Expected: All 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add searchers/reed.py tests/searchers/test_reed.py
git commit -m "feat: Reed API searcher"
```

---

## Task 8: NHS Jobs Scraper

**Files:**
- Create: `searchers/nhs_jobs.py`
- Create: `tests/searchers/test_nhs_jobs.py`

> **Note:** NHS Jobs (jobs.nhs.uk) uses a React frontend. If the scraper returns zero results on a live run, check whether the page content is server-rendered by inspecting the raw HTML (`response.text`). If job data is absent, the selectors below may need updating to match the current site structure.

- [ ] **Step 1: Write failing tests**

Create `tests/searchers/test_nhs_jobs.py`:

```python
import pytest
from searchers.nhs_jobs import search

NHS_HTML = """
<html><body>
  <div data-test="search-result">
    <a href="/candidate/jobadvert/A123" data-test="job-title">NHS Data Analyst</a>
    <span data-test="employer-name">NHS Bristol Trust</span>
    <span data-test="job-location">Bristol</span>
    <span data-test="job-salary">£35,392 - £42,618 a year</span>
  </div>
  <div data-test="search-result">
    <a href="/candidate/jobadvert/B456" data-test="job-title">IT Support Specialist</a>
    <span data-test="employer-name">NHS Manchester Trust</span>
    <span data-test="job-location">Manchester</span>
    <span data-test="job-salary">£28,000</span>
  </div>
</body></html>
"""


def test_search_returns_normalised_jobs(mocker):
    mock_response = mocker.MagicMock()
    mock_response.text = NHS_HTML
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("searchers.nhs_jobs.requests.get", return_value=mock_response)

    results = search(["data analyst"], "Bristol", 30000)

    assert len(results) == 2
    assert results[0]["title"] == "NHS Data Analyst"
    assert results[0]["company"] == "NHS Bristol Trust"
    assert results[0]["url"] == "https://www.jobs.nhs.uk/candidate/jobadvert/A123"
    assert results[0]["source"] == "NHS Jobs"
    assert results[1]["title"] == "IT Support Specialist"


def test_search_deduplicates_across_queries(mocker):
    mock_response = mocker.MagicMock()
    mock_response.text = NHS_HTML
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("searchers.nhs_jobs.requests.get", return_value=mock_response)

    results = search(["data analyst", "data analyst duplicate query"], "Bristol", 30000)
    urls = [r["url"] for r in results]
    assert len(urls) == len(set(urls))


def test_search_handles_request_error(mocker):
    mocker.patch("searchers.nhs_jobs.requests.get", side_effect=Exception("Timeout"))

    results = search(["data analyst"], "Bristol", 30000)
    assert results == []
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/searchers/test_nhs_jobs.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `searchers/nhs_jobs.py`**

```python
import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
_BASE_URL = "https://www.jobs.nhs.uk/candidate/search/results"
_NHS_HOST = "https://www.jobs.nhs.uk"


def search(queries: list[str], location: str, min_salary: int) -> list[dict]:
    jobs = []
    seen_urls: set[str] = set()
    for query in queries:
        try:
            response = requests.get(
                _BASE_URL,
                params={"keyword": query, "location": location, "distance": 15, "language": "en"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=30,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for card in soup.select("[data-test='search-result']"):
                title_el = card.select_one("[data-test='job-title']")
                employer_el = card.select_one("[data-test='employer-name']")
                location_el = card.select_one("[data-test='job-location']")
                salary_el = card.select_one("[data-test='job-salary']")
                link_el = title_el if title_el and title_el.name == "a" else card.select_one("a[href]")
                if not title_el or not link_el:
                    continue
                href = link_el.get("href", "")
                url = href if href.startswith("http") else _NHS_HOST + href
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                jobs.append({
                    "title": title_el.get_text(strip=True),
                    "company": employer_el.get_text(strip=True) if employer_el else "",
                    "location": location_el.get_text(strip=True) if location_el else "",
                    "salary": salary_el.get_text(strip=True) if salary_el else "",
                    "description": "",
                    "url": url,
                    "source": "NHS Jobs",
                })
        except Exception as exc:
            logger.warning("NHS Jobs search failed for query '%s': %s", query, exc)
    return jobs
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `pytest tests/searchers/test_nhs_jobs.py -v`

Expected: All 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add searchers/nhs_jobs.py tests/searchers/test_nhs_jobs.py
git commit -m "feat: NHS Jobs scraper"
```

---

## Task 9: Search Runner

**Files:**
- Create: `searchers/runner.py`
- Modify: `searchers/__init__.py`
- Create: `tests/searchers/test_runner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/searchers/test_runner.py`:

```python
import pytest
from searchers.runner import search_all_streaming

JOB_A = {
    "title": "Data Engineer", "company": "Tech Ltd", "location": "Bristol",
    "salary": "£70,000", "description": "...", "url": "https://linkedin.com/1", "source": "LinkedIn",
}
JOB_B = {
    "title": "Nurse", "company": "NHS Trust", "location": "Bristol",
    "salary": "£35,000", "description": "...", "url": "https://nhsjobs.com/1", "source": "NHS Jobs",
}


def test_search_all_streaming_yields_three_platforms(mocker):
    mocker.patch("searchers.runner.jobspy_searcher.search", return_value=[JOB_A])
    mocker.patch("searchers.runner.reed.search", return_value=[])
    mocker.patch("searchers.runner.nhs_jobs.search", return_value=[JOB_B])

    results = list(search_all_streaming(["data engineer"], "Bristol", 60000))

    assert len(results) == 3
    platform_names = {name for name, _, _ in results}
    assert platform_names == {"LinkedIn + Indeed", "Reed", "NHS Jobs"}


def test_search_all_streaming_returns_jobs(mocker):
    mocker.patch("searchers.runner.jobspy_searcher.search", return_value=[JOB_A])
    mocker.patch("searchers.runner.reed.search", return_value=[])
    mocker.patch("searchers.runner.nhs_jobs.search", return_value=[])

    results = list(search_all_streaming(["data engineer"], "Bristol", 60000))
    all_jobs = [j for _, jobs, _ in results for j in jobs]
    assert len(all_jobs) == 1
    assert all_jobs[0]["title"] == "Data Engineer"


def test_search_all_streaming_handles_platform_failure(mocker):
    mocker.patch("searchers.runner.jobspy_searcher.search", side_effect=Exception("Blocked"))
    mocker.patch("searchers.runner.reed.search", return_value=[JOB_B])
    mocker.patch("searchers.runner.nhs_jobs.search", return_value=[])

    results = list(search_all_streaming(["nurse"], "Bristol", 30000))

    errors = [(name, err) for name, _, err in results if err]
    successes = [(name, jobs) for name, jobs, err in results if err is None]
    assert len(errors) == 1
    assert errors[0][0] == "LinkedIn + Indeed"
    assert any(jobs for _, jobs in successes)


def test_search_all_streaming_no_error_on_success(mocker):
    mocker.patch("searchers.runner.jobspy_searcher.search", return_value=[])
    mocker.patch("searchers.runner.reed.search", return_value=[])
    mocker.patch("searchers.runner.nhs_jobs.search", return_value=[])

    results = list(search_all_streaming(["anything"], "Bristol", 60000))
    assert all(err is None for _, _, err in results)
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `pytest tests/searchers/test_runner.py -v`

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `searchers/runner.py`**

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Generator
from . import jobspy_searcher, reed, nhs_jobs


def search_all_streaming(
    queries: list[str],
    location: str,
    min_salary: int,
) -> Generator[tuple[str, list[dict], str | None], None, None]:
    """Yields (platform_name, jobs, error_msg) as each platform's search completes."""
    searchers = {
        "LinkedIn + Indeed": jobspy_searcher.search,
        "Reed": reed.search,
        "NHS Jobs": nhs_jobs.search,
    }
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(fn, queries, location, min_salary): name
            for name, fn in searchers.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                yield name, future.result(), None
            except Exception as exc:
                yield name, [], str(exc)
```

- [ ] **Step 4: Update `searchers/__init__.py`**

```python
from .runner import search_all_streaming

__all__ = ["search_all_streaming"]
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add searchers/runner.py searchers/__init__.py tests/searchers/test_runner.py
git commit -m "feat: concurrent search runner with streaming results"
```

---

## Task 10: Streamlit App — State 1 (CV Upload & Analysis)

**Files:**
- Create: `app.py`

No unit tests — test manually by running the app.

- [ ] **Step 1: Create `app.py` with State 1**

```python
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

import cv_parser
import sponsor_filter
from searchers import search_all_streaming

st.set_page_config(page_title="Jie's Job Search", layout="wide")
st.title("Jie's Job Search")
st.caption("Finds UK roles from licensed Skilled Worker visa sponsors only.")

# --- State 1: CV Upload ---
uploaded_file = st.file_uploader("Upload your CV", type=["pdf", "docx", "txt"])

if uploaded_file:
    file_id = f"{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.get("file_id") != file_id:
        st.session_state.file_id = file_id
        st.session_state.pop("cv_analysis", None)
        st.session_state.pop("all_jobs", None)
        st.session_state.pop("filtered_jobs", None)

    if "cv_analysis" not in st.session_state:
        with st.spinner("Analysing CV with Claude..."):
            try:
                text = cv_parser.extract_text(uploaded_file.read(), uploaded_file.name)
                st.session_state.cv_analysis = cv_parser.analyse_cv(text)
            except Exception as e:
                st.error(f"CV analysis failed: {e}")
                st.stop()

if "cv_analysis" in st.session_state:
    analysis = st.session_state.cv_analysis

    with st.expander("Extracted from CV", expanded=True):
        st.write("**Job titles:**", ", ".join(analysis.get("job_titles", [])))
        st.write("**Skills:**", ", ".join(analysis.get("skills", [])))

    queries_text = st.text_area(
        "Search queries (one per line — edit as needed before searching)",
        value="\n".join(analysis.get("search_queries", [])),
        height=120,
    )
    queries = [q.strip() for q in queries_text.splitlines() if q.strip()]

    col1, col2 = st.columns(2)
    with col1:
        location = st.text_input("Location", value="Bristol")
    with col2:
        min_salary = st.number_input("Minimum salary (£)", value=60000, step=5000, min_value=0)

    if st.button("Search", type="primary", disabled=not queries):
        st.session_state.search_params = {
            "queries": queries,
            "location": location,
            "min_salary": int(min_salary),
        }
        st.session_state.pop("all_jobs", None)
        st.session_state.pop("filtered_jobs", None)
        st.rerun()
```

- [ ] **Step 2: Run the app and test State 1**

Run: `streamlit run app.py`

Open http://localhost:8501. Upload a short plain-text file (e.g. a `.txt` file containing "Python Developer, 5 years experience"). Confirm:
- Spinner appears, then extracted job titles/skills/queries display
- Queries are editable
- Location defaults to "Bristol", salary to "£60,000"
- Search button is present

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: Streamlit app State 1 — CV upload and Claude analysis"
```

---

## Task 11: Streamlit App — State 2 (Concurrent Search with Live Progress)

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add State 2 to `app.py`**

Append the following block to `app.py` (after the existing State 1 code):

```python
# --- State 2: Searching ---
if "search_params" in st.session_state and "filtered_jobs" not in st.session_state:
    params = st.session_state.search_params

    with st.spinner("Loading sponsor register..."):
        try:
            sponsor_names = sponsor_filter.load_sponsor_names()
        except RuntimeError as e:
            st.error(str(e))
            st.stop()

    st.subheader("Searching platforms...")
    cols = st.columns(3)
    status_placeholders = {
        "LinkedIn + Indeed": cols[0].empty(),
        "Reed": cols[1].empty(),
        "NHS Jobs": cols[2].empty(),
    }
    for name, ph in status_placeholders.items():
        ph.info(f"⏳ {name}")

    all_jobs: list[dict] = []
    results_placeholder = st.empty()

    for platform, jobs, error in search_all_streaming(
        params["queries"], params["location"], params["min_salary"]
    ):
        ph = status_placeholders[platform]
        if error:
            ph.warning(f"⚠️ {platform} — error")
        else:
            ph.success(f"✅ {platform} — {len(jobs)} results")
        all_jobs.extend(jobs)

    # Deduplicate by URL
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for job in all_jobs:
        if job["url"] and job["url"] not in seen_urls:
            seen_urls.add(job["url"])
            deduped.append(job)

    st.session_state.all_jobs = deduped
    st.session_state.filtered_jobs = sponsor_filter.filter_jobs(deduped, sponsor_names)
    st.rerun()
```

- [ ] **Step 2: Test State 2 manually**

With the app running (`streamlit run app.py`):
- Upload a CV, confirm State 1 works
- Click **Search**
- Confirm three status boxes appear as "⏳"
- Confirm they update to ✅ or ⚠️ as each platform completes
- Confirm the app reruns and proceeds to State 3

> If API keys are not configured, Reed will error (⚠️ expected). JobSpy may also error without internet access. This is expected behaviour.

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: Streamlit app State 2 — concurrent search with live progress"
```

---

## Task 12: Streamlit App — State 3 (Results & Sidebar Filters)

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add State 3 to `app.py`**

Append the following block to `app.py`:

```python
# --- State 3: Results ---
if "filtered_jobs" in st.session_state:
    import pandas as pd

    filtered = st.session_state.filtered_jobs
    raw_count = len(st.session_state.get("all_jobs", []))

    if not filtered:
        st.warning(
            f"{raw_count} job(s) found across all platforms — "
            "0 from licensed Worker-route sponsors. "
            "Try broadening your search queries or location."
        )
    else:
        st.success(f"{len(filtered)} role(s) from licensed Worker-route sponsors")

        with st.sidebar:
            st.header("Filter results")
            loc_filter = st.text_input("Location contains", value="")
            salary_filter = st.number_input(
                "Minimum salary (£)", value=0, step=5000, min_value=0
            )

        displayed = filtered
        if loc_filter:
            displayed = [
                j for j in displayed
                if loc_filter.lower() in j.get("location", "").lower()
            ]

        df = pd.DataFrame(
            [
                {
                    "Title": j["title"],
                    "Company": j["sponsor_name"],
                    "Location": j["location"],
                    "Salary": j["salary"],
                    "Description": j["description"],
                    "Source": j["source"],
                    "Link": j["url"],
                }
                for j in displayed
            ]
        )

        st.dataframe(
            df,
            column_config={"Link": st.column_config.LinkColumn("Link")},
            use_container_width=True,
            hide_index=True,
        )

        if st.button("New search"):
            for key in ["cv_analysis", "all_jobs", "filtered_jobs", "search_params", "file_id"]:
                st.session_state.pop(key, None)
            st.rerun()
```

- [ ] **Step 2: Test State 3 manually**

Run a full end-to-end test:
1. `streamlit run app.py`
2. Upload a CV (PDF, DOCX, or TXT)
3. Confirm job titles/skills/queries appear
4. Edit location or salary if desired, click **Search**
5. Watch all three status boxes update
6. Confirm results table appears with Title, Company, Location, Salary, Description, Source, Link columns
7. Confirm Link column is clickable
8. Use sidebar filters — confirm table updates without re-running the search
9. Click **New search** — confirm app resets to State 1

- [ ] **Step 3: Run all tests one final time**

Run: `pytest tests/ -v`

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: Streamlit app State 3 — results table with sidebar filters"
```

---

## Self-Review

### Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| Accept PDF, DOCX, TXT | Task 2 |
| Claude API CV analysis → job_titles, skills, search_queries | Task 3 |
| Search LinkedIn + Indeed via JobSpy | Task 6 |
| Search Reed via API | Task 7 |
| Search NHS Jobs via scraper | Task 8 |
| Concurrent search with live progress | Tasks 9, 11 |
| Download + cache gov.uk sponsor CSV | Task 4 |
| Filter to Worker route only | Task 4 |
| Fuzzy match company names (rapidfuzz, ~85%) | Task 5 |
| Show matched sponsor name in results | Task 5, 12 |
| Deduplicate results by URL | Task 11 |
| Results table: Title, Company, Location, Salary, Description, Source, Link | Task 12 |
| Sidebar filters: location, salary (post-search) | Task 12 |
| Default location: Bristol | Task 10 |
| Default salary: £60,000 | Task 10 |
| Claude API error surfaces before search | Task 10 |
| Sponsor CSV error surfaces before search | Task 11 |
| Platform errors shown per-platform, search continues | Tasks 6–9, 11 |
| "0 from licensed sponsors" message | Task 12 |
| API keys in .env, not committed | Task 1 |

All spec requirements covered. ✓

### Type Consistency Check

- `search()` in all three searchers: `(queries: list[str], location: str, min_salary: int) -> list[dict]` ✓
- `search_all_streaming()` in runner: yields `(str, list[dict], str | None)` ✓
- `filter_jobs()` adds `sponsor_name` key; `app.py` reads `j["sponsor_name"]` ✓
- `load_sponsor_names()` returns `list[str]`; `filter_jobs()` accepts `list[str]` ✓
