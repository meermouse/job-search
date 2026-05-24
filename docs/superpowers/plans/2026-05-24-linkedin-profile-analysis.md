# LinkedIn Profile Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a LinkedIn Profile tab to Jie's Job Search that scrapes a public LinkedIn profile with Playwright, analyses it with Claude, and feeds extracted data into the existing search and chatbot flows.

**Architecture:** A new `linkedin_parser.py` module (mirrors `cv_parser.py`) provides `scrape_profile` (Playwright) and `analyse_profile` (Claude). Results are stored in `st.session_state.cv_analysis` under a new `_analysis_source` key so the existing chatbot, search form, and auto-acknowledgement flows work unchanged.

**Tech Stack:** Python, Streamlit, Playwright (headless Chromium), Anthropic SDK, pytest, pytest-mock

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `linkedin_parser.py` | Scrape public LinkedIn profile; analyse text with Claude |
| Create | `tests/test_linkedin_parser.py` | Unit tests for both functions |
| Modify | `requirements.txt` | Add `playwright>=1.40.0` |
| Modify | `app.py` | Add LinkedIn tab; wire session state; update auto-ack |
| Modify | `chatbot.py` | Wording: "CV or LinkedIn profile" |

---

### Task 1: Add Playwright dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add playwright to requirements.txt**

Open `requirements.txt` and add one line:

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
pyyaml>=6.0.0
playwright>=1.40.0
```

- [ ] **Step 2: Install playwright and download Chromium**

```bash
pip install playwright
playwright install chromium
```

Expected: Chromium browser binaries downloaded to playwright's cache directory. Final line of output will be something like `✓ Chromium 123.x.x (playwright build ...) downloaded to ...`

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add playwright dependency for LinkedIn scraping"
```

---

### Task 2: `analyse_profile` — TDD

**Files:**
- Create: `linkedin_parser.py`
- Create: `tests/test_linkedin_parser.py`

- [ ] **Step 1: Write failing tests for `analyse_profile`**

Create `tests/test_linkedin_parser.py`:

```python
import json
import pytest
from unittest.mock import MagicMock
from linkedin_parser import analyse_profile


def test_analyse_profile_returns_structured_data(mocker):
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    expected = {
        "name": "Jane Doe",
        "headline": "Operations Director | Strategy",
        "current_position": "Operations Director at ACME Corp",
        "job_titles": ["Operations Director", "Business Manager"],
        "skills": ["Strategy", "Stakeholder Management", "Budget Control"],
        "search_queries": ["Operations Director NHS", "Business Manager Strategy"],
    }
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(expected))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("linkedin_parser.anthropic.Anthropic", return_value=mock_client)

    result = analyse_profile("Jane Doe\nOperations Director at ACME Corp\nStrategy, NHS...")

    assert result["name"] == "Jane Doe"
    assert result["headline"] == "Operations Director | Strategy"
    assert result["current_position"] == "Operations Director at ACME Corp"
    assert isinstance(result["job_titles"], list)
    assert len(result["job_titles"]) == 2
    assert isinstance(result["skills"], list)
    assert isinstance(result["search_queries"], list)
    assert len(result["search_queries"]) == 2


def test_analyse_profile_raises_when_api_key_missing(mocker):
    mocker.patch.dict("os.environ", {}, clear=True)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not set"):
        analyse_profile("Some profile text")


def test_analyse_profile_raises_on_api_error(mocker):
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API unavailable")
    mocker.patch("linkedin_parser.anthropic.Anthropic", return_value=mock_client)

    with pytest.raises(Exception, match="API unavailable"):
        analyse_profile("Some profile text")
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_linkedin_parser.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'linkedin_parser'`

- [ ] **Step 3: Create `linkedin_parser.py` with `analyse_profile`**

Create `linkedin_parser.py`:

```python
import json
import os
import anthropic
from playwright.sync_api import sync_playwright


_SYSTEM = "You extract structured job search data from LinkedIn profiles. Return only valid JSON, no markdown."

_PROMPT = """\
Analyse this LinkedIn profile page text and return a JSON object with exactly these keys:
- "name": the person's full name
- "headline": their LinkedIn headline or tagline
- "current_position": their most recent job title and company (e.g. "Operations Director at ACME Corp")
- "job_titles": list of 2-3 most suitable UK job titles based on their experience, ordered by fit
- "skills": list of up to 8 most distinctive technical and professional skills
- "search_queries": list of exactly 2-3 search strings for UK job boards

Rules for search_queries:
- Each query must be a specific, targeted phrase a recruiter would use, e.g. "Senior Data Engineer dbt" or "Clinical Pharmacist NHS"
- Combine the primary job title with the single most differentiating skill or sector
- Do NOT use generic single words like "Engineer" or "Manager" alone
- Do NOT repeat the same role with minor wording changes
- Prefer shorter phrases (2-4 words) that job boards handle well
- Order from most to least specific

Profile text:
{profile_text}"""


def scrape_profile(url: str) -> str:
    raise NotImplementedError


def analyse_profile(text: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _PROMPT.format(profile_text=text)}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    return json.loads(raw)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_linkedin_parser.py -v
```

Expected:
```
PASSED tests/test_linkedin_parser.py::test_analyse_profile_returns_structured_data
PASSED tests/test_linkedin_parser.py::test_analyse_profile_raises_when_api_key_missing
PASSED tests/test_linkedin_parser.py::test_analyse_profile_raises_on_api_error
```

- [ ] **Step 5: Commit**

```bash
git add linkedin_parser.py tests/test_linkedin_parser.py
git commit -m "feat: add analyse_profile with Claude extraction"
```

---

### Task 3: `scrape_profile` — TDD

**Files:**
- Modify: `linkedin_parser.py`
- Modify: `tests/test_linkedin_parser.py`

- [ ] **Step 1: Add failing tests for `scrape_profile`**

Append to `tests/test_linkedin_parser.py`:

```python
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from linkedin_parser import scrape_profile


def _mock_playwright(mocker, *, page_url="https://www.linkedin.com/in/janedoe", goto_side_effect=None):
    """Helper that sets up a full Playwright context manager mock."""
    mock_page = MagicMock()
    mock_page.url = page_url
    if goto_side_effect:
        mock_page.goto.side_effect = goto_side_effect
    mock_page.inner_text.return_value = "Jane Doe\nOperations Director"

    mock_browser = MagicMock()
    mock_browser.new_page.return_value = mock_page

    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser

    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_pw
    mock_cm.__exit__.return_value = False

    mocker.patch("linkedin_parser.sync_playwright", return_value=mock_cm)
    return mock_page, mock_browser


def test_scrape_profile_returns_page_text(mocker):
    _mock_playwright(mocker)
    result = scrape_profile("https://www.linkedin.com/in/janedoe")
    assert "Jane Doe" in result


def test_scrape_profile_raises_on_authwall(mocker):
    _mock_playwright(mocker, page_url="https://www.linkedin.com/authwall?trk=bf_...")
    with pytest.raises(ValueError, match="publicly visible"):
        scrape_profile("https://www.linkedin.com/in/janedoe")


def test_scrape_profile_raises_on_login_redirect(mocker):
    _mock_playwright(mocker, page_url="https://www.linkedin.com/login?session_redirect=...")
    with pytest.raises(ValueError, match="publicly visible"):
        scrape_profile("https://www.linkedin.com/in/janedoe")


def test_scrape_profile_raises_on_timeout(mocker):
    _mock_playwright(mocker, goto_side_effect=PlaywrightTimeoutError("30000ms exceeded"))
    with pytest.raises(TimeoutError, match="took too long"):
        scrape_profile("https://www.linkedin.com/in/janedoe")


def test_scrape_profile_closes_browser_on_error(mocker):
    _, mock_browser = _mock_playwright(
        mocker, page_url="https://www.linkedin.com/authwall?trk=..."
    )
    with pytest.raises(ValueError):
        scrape_profile("https://www.linkedin.com/in/janedoe")
    mock_browser.close.assert_called_once()
```

- [ ] **Step 2: Run tests to confirm new ones fail**

```bash
pytest tests/test_linkedin_parser.py -v
```

Expected: The three new `test_analyse_profile_*` tests still pass. The five new `test_scrape_profile_*` tests fail with `NotImplementedError`.

- [ ] **Step 3: Implement `scrape_profile` in `linkedin_parser.py`**

Replace the `scrape_profile` stub:

```python
def scrape_profile(url: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                if "timeout" in str(exc).lower() or "TimeoutError" in type(exc).__name__:
                    raise TimeoutError(
                        "Couldn't load the LinkedIn profile — the page took too long to respond."
                    ) from exc
                raise
            if "authwall" in page.url or "login" in page.url:
                raise ValueError(
                    "This profile isn't publicly visible. "
                    "Check the URL is correct and the profile is set to public."
                )
            return page.inner_text("body")
        finally:
            browser.close()
```

- [ ] **Step 4: Run all tests to confirm everything passes**

```bash
pytest tests/test_linkedin_parser.py -v
```

Expected: All 8 tests pass.

```bash
pytest -v
```

Expected: All tests in the full suite pass (no regressions).

- [ ] **Step 5: Commit**

```bash
git add linkedin_parser.py tests/test_linkedin_parser.py
git commit -m "feat: add scrape_profile with Playwright and authwall detection"
```

---

### Task 4: Update chatbot wording

**Files:**
- Modify: `chatbot.py`

- [ ] **Step 1: Update `_CV_SECTION` in `chatbot.py`**

In `chatbot.py`, find line 39 and change:

```python
# Before
_CV_SECTION = """
The user has uploaded a CV. Here is the extracted analysis:
  Job titles: {job_titles}
  Skills: {skills}
  Suggested search queries: {search_queries}
"""
```

```python
# After
_CV_SECTION = """
The user has uploaded a CV or connected their LinkedIn profile. Here is the extracted analysis:
  Job titles: {job_titles}
  Skills: {skills}
  Suggested search queries: {search_queries}
"""
```

- [ ] **Step 2: Run existing tests to confirm no regression**

```bash
pytest tests/test_chatbot.py -v
```

Expected: All chatbot tests pass.

- [ ] **Step 3: Commit**

```bash
git add chatbot.py
git commit -m "fix: update chatbot to mention LinkedIn profile as a valid source"
```

---

### Task 5: Add LinkedIn tab to `app.py`

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add `import linkedin_parser` near the other imports**

In `app.py`, find the import block around line 303:

```python
import cv_parser
import sponsor_filter
from searchers import search_all_streaming
```

Change it to:

```python
import cv_parser
import linkedin_parser
import sponsor_filter
from searchers import search_all_streaming
```

- [ ] **Step 2: Change the tab declaration from two to three tabs**

Find line 367:

```python
tab_cv, tab_manual = st.tabs(["📄 Upload CV", "✏️ Search manually"])
```

Change to:

```python
tab_cv, tab_linkedin, tab_manual = st.tabs(["📄 Upload CV", "🔗 LinkedIn Profile", "✏️ Search manually"])
```

- [ ] **Step 3: Update the CV tab to track `_analysis_source` and clear it on new upload**

Inside `with tab_cv:`, find the block that runs when `file_id` changes (around line 373):

```python
        if st.session_state.get("file_id") != file_id:
            st.session_state.file_id = file_id
            st.session_state.pop("cv_analysis", None)
            st.session_state.pop("all_jobs", None)
            st.session_state.pop("filtered_jobs", None)
```

Change to:

```python
        if st.session_state.get("file_id") != file_id:
            st.session_state.file_id = file_id
            st.session_state.pop("cv_analysis", None)
            st.session_state.pop("all_jobs", None)
            st.session_state.pop("filtered_jobs", None)
            st.session_state.pop("linkedin_url", None)
            st.session_state.pop("_analysis_source", None)
```

Then find the block that stores `cv_analysis` after parsing (around line 380):

```python
        if "cv_analysis" not in st.session_state:
            with _animated_spinner("Analysing your CV"):
                try:
                    text = cv_parser.extract_text(uploaded_file.read(), uploaded_file.name)
                    st.session_state.cv_analysis = cv_parser.analyse_cv(text)
                    st.session_state["_new_cv_to_ack"] = True
                except Exception as e:
                    st.error(f"CV analysis failed: {e}")
                    st.stop()
            st.rerun()
```

Change to:

```python
        if "cv_analysis" not in st.session_state:
            with _animated_spinner("Analysing your CV"):
                try:
                    text = cv_parser.extract_text(uploaded_file.read(), uploaded_file.name)
                    st.session_state.cv_analysis = cv_parser.analyse_cv(text)
                    st.session_state["_new_cv_to_ack"] = True
                    st.session_state["_analysis_source"] = "cv"
                except Exception as e:
                    st.error(f"CV analysis failed: {e}")
                    st.stop()
            st.rerun()
```

Then find the expander block (around line 391):

```python
    if "cv_analysis" in st.session_state:
        analysis = st.session_state.cv_analysis
        with st.expander("Extracted from CV", expanded=True):
            st.write("**Job titles:**", ", ".join(analysis.get("job_titles", [])))
            st.write("**Skills:**", ", ".join(analysis.get("skills", [])))
        _search_form("cv", analysis.get("search_queries", []))
```

Change to:

```python
    if "cv_analysis" in st.session_state and st.session_state.get("_analysis_source") == "cv":
        analysis = st.session_state.cv_analysis
        with st.expander("Extracted from CV", expanded=True):
            st.write("**Job titles:**", ", ".join(analysis.get("job_titles", [])))
            st.write("**Skills:**", ", ".join(analysis.get("skills", [])))
        _search_form("cv", analysis.get("search_queries", []))
```

- [ ] **Step 4: Add the LinkedIn tab block**

After the `with tab_cv:` block ends (around line 397) and before `with tab_manual:`, add:

```python
with tab_linkedin:
    url_input = st.text_input(
        "LinkedIn profile URL",
        placeholder="https://www.linkedin.com/in/your-profile",
        key="linkedin_url_input",
    )
    if st.button("Analyse profile", key="linkedin_analyse"):
        new_url = url_input.strip()
        if new_url:
            if st.session_state.get("linkedin_url") != new_url:
                st.session_state.linkedin_url = new_url
                st.session_state.pop("cv_analysis", None)
                st.session_state.pop("_analysis_source", None)
                st.session_state.pop("all_jobs", None)
                st.session_state.pop("filtered_jobs", None)
            st.rerun()

    if "linkedin_url" in st.session_state and "cv_analysis" not in st.session_state:
        with _animated_spinner("Analysing LinkedIn profile"):
            try:
                text = linkedin_parser.scrape_profile(st.session_state.linkedin_url)
                st.session_state.cv_analysis = linkedin_parser.analyse_profile(text)
                st.session_state["_new_cv_to_ack"] = True
                st.session_state["_analysis_source"] = "linkedin"
            except ValueError as e:
                st.error(str(e))
                st.stop()
            except Exception as e:
                st.error(f"LinkedIn analysis failed: {e}")
                st.stop()
        st.rerun()

    if "cv_analysis" in st.session_state and st.session_state.get("_analysis_source") == "linkedin":
        analysis = st.session_state.cv_analysis
        with st.expander("Extracted from LinkedIn profile", expanded=True):
            st.write("**Name:**", analysis.get("name", ""))
            st.write("**Headline:**", analysis.get("headline", ""))
            st.write("**Current position:**", analysis.get("current_position", ""))
            st.write("**Job titles:**", ", ".join(analysis.get("job_titles", [])))
            st.write("**Skills:**", ", ".join(analysis.get("skills", [])))
        _search_form("linkedin", analysis.get("search_queries", []))
```

- [ ] **Step 5: Update the "New search" button to clear LinkedIn state**

Find the "New search" button (around line 519):

```python
    if st.button("New search"):
        for key in ["cv_analysis", "all_jobs", "filtered_jobs", "search_params", "file_id"]:
            st.session_state.pop(key, None)
        st.rerun()
```

Change to:

```python
    if st.button("New search"):
        for key in ["cv_analysis", "all_jobs", "filtered_jobs", "search_params", "file_id",
                    "linkedin_url", "_analysis_source"]:
            st.session_state.pop(key, None)
        st.rerun()
```

- [ ] **Step 6: Update `_auto_ack_cv` to use source-aware trigger message**

Find the `trigger` assignment in `_auto_ack_cv` (around line 190):

```python
        trigger = (
            f"[System: User just uploaded their CV. "
            f"Extracted — job titles: {titles}; skills: {skills}; "
            f"suggested search queries: {queries}. "
            f"Acknowledge the upload, briefly summarise what you found, and suggest next steps. "
            f"Use set_queries to pre-populate the search with the suggested queries.]"
        )
```

Change to:

```python
        source = st.session_state.get("_analysis_source", "cv")
        source_label = "connected their LinkedIn profile" if source == "linkedin" else "uploaded their CV"
        trigger = (
            f"[System: User just {source_label}. "
            f"Extracted — job titles: {titles}; skills: {skills}; "
            f"suggested search queries: {queries}. "
            f"Acknowledge the upload, briefly summarise what you found, and suggest next steps. "
            f"Use set_queries to pre-populate the search with the suggested queries.]"
        )
```

- [ ] **Step 7: Run the full test suite**

```bash
pytest -v
```

Expected: All tests pass.

- [ ] **Step 8: Manually verify the UI**

```bash
streamlit run app.py
```

Verify:
1. Three tabs appear: "📄 Upload CV", "🔗 LinkedIn Profile", "✏️ Search manually"
2. LinkedIn tab shows URL input and "Analyse profile" button
3. Entering a public LinkedIn URL and clicking "Analyse profile" triggers the spinner
4. After analysis, the expander shows Name, Headline, Current position, Job titles, Skills
5. The search form below is pre-populated with search queries
6. The chatbot acknowledges the LinkedIn connection (not "CV upload")
7. CV tab still works — uploading a CV shows "Extracted from CV" expander, not LinkedIn fields
8. "New search" button clears LinkedIn analysis and returns to the input state

- [ ] **Step 9: Commit**

```bash
git add app.py
git commit -m "feat: add LinkedIn profile analysis tab"
```
