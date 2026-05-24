# LinkedIn Profile Analysis — Design Spec

**Date:** 2026-05-24
**Branch:** FE-003-linkedin-profile

---

## Overview

Add a LinkedIn Profile tab to the Jie's Job Search Streamlit app. Users enter a public LinkedIn profile URL; the app scrapes the page with a headless browser, sends the content to Claude for analysis, and extracts the same structured data as CV upload (job titles, skills, search queries). The extracted data feeds into the existing search form and chatbot with no changes to those flows.

---

## Architecture

### New file: `linkedin_parser.py`

Mirrors `cv_parser.py`. Two public functions:

**`scrape_profile(url: str) -> str`**
- Launches a headless Chromium browser via `playwright.sync_api`
- Navigates to the URL with a 30-second timeout, waits for `domcontentloaded`
- Checks `page.url` after navigation — if it contains `"authwall"` or `"login"`, raises `ValueError` with a clear message
- Returns `page.inner_text("body")` — full page text, no DOM selector parsing
- Closes the browser in a `finally` block

**`analyse_profile(text: str) -> dict`**
- Sends page text to Claude (`claude-sonnet-4-6`, same model as CV analysis)
- Returns a dict with exactly these keys:
  ```json
  {
    "name": "Jane Doe",
    "headline": "Operations Director | Strategy | NHS",
    "current_position": "Operations Director at ACME NHS Trust",
    "job_titles": ["Operations Director", "Business Manager"],
    "skills": ["Strategy", "Stakeholder Management", "Budget Control"],
    "search_queries": ["Operations Director NHS", "Business Manager Strategy UK"]
  }
  ```
- `search_queries` rules are identical to those in `cv_parser.py`
- Strips markdown fences from the response (same logic as `cv_parser.analyse_cv`)
- Raises `RuntimeError` if `ANTHROPIC_API_KEY` is not set

### Changed file: `app.py`

**Tab structure** changes from two tabs to three:
```python
tab_cv, tab_linkedin, tab_manual = st.tabs(["📄 Upload CV", "🔗 LinkedIn Profile", "✏️ Search manually"])
```

**Inside `tab_linkedin`:**
1. `st.text_input` for the profile URL, stored in session state on change
2. **Analyse** button — sets `st.session_state.linkedin_url` and clears any prior analysis, then reruns
3. On rerun: if URL is set but no `cv_analysis` in state, runs the animated spinner → calls `scrape_profile` then `analyse_profile` → stores result in `st.session_state.cv_analysis` → sets `_new_cv_to_ack = True`
4. If analysis is in state, shows expander **"Extracted from LinkedIn profile"** containing:
   - **Name:** (from `analysis["name"]`)
   - **Headline:** (from `analysis["headline"]`)
   - **Current position:** (from `analysis["current_position"]`)
   - **Job titles:** (from `analysis["job_titles"]`)
   - **Skills:** (from `analysis["skills"]`)
5. Calls `_search_form("linkedin", analysis["search_queries"])` — identical to CV tab

The result is stored in `st.session_state.cv_analysis` (same key), so the chatbot auto-acknowledgement, search form population, and all downstream flows work without modification.

### Changed file: `chatbot.py`

Single wording change in `_CV_SECTION`:

```python
# Before
"The user has uploaded a CV. Here is the extracted analysis:"
# After
"The user has uploaded a CV or connected their LinkedIn profile. Here is the extracted analysis:"
```

No structural changes.

---

## Data Flow

```
User enters LinkedIn URL
        │
        ▼
scrape_profile(url)          ← Playwright headless Chromium
        │
        ▼
analyse_profile(text)        ← Claude claude-sonnet-4-6
        │
        ▼
st.session_state.cv_analysis ← {name, headline, current_position, job_titles, skills, search_queries}
        │
        ├── Expander display (name, headline, current_position, job_titles, skills)
        ├── _search_form (pre-populated with search_queries)
        └── chatbot auto-ack (_new_cv_to_ack = True)
```

---

## Error Handling

| Failure | Trigger | User-facing message |
|---|---|---|
| Authwall / login redirect | `page.url` contains `"authwall"` or `"login"` | "This profile isn't publicly visible. Check the URL is correct and the profile is set to public." |
| Playwright timeout | `TimeoutError` from Playwright | "Couldn't load the LinkedIn profile — the page took too long to respond." |
| Malformed Claude response | `json.JSONDecodeError` | Let exception propagate to `st.error(f"LinkedIn analysis failed: {e}")` in app.py |
| Missing API key | `ANTHROPIC_API_KEY` not set | `RuntimeError("ANTHROPIC_API_KEY is not set.")` — same as cv_parser |

All errors surface via `st.error(...)` in `app.py`, consistent with CV error handling.

---

## Tests: `tests/test_linkedin_parser.py`

Follows the same patterns as `tests/test_cv_parser.py`.

| Test | What it checks |
|---|---|
| `test_analyse_profile_returns_structured_data` | Mocks Anthropic client; asserts all 6 keys present with correct types |
| `test_analyse_profile_raises_when_api_key_missing` | Clears env; asserts `RuntimeError` |
| `test_analyse_profile_raises_on_api_error` | Mocks client to raise; asserts exception propagates |
| `test_scrape_profile_raises_on_authwall` | Mocks Playwright `page.url = "https://linkedin.com/authwall"`; asserts `ValueError` |
| `test_scrape_profile_raises_on_timeout` | Mocks `page.goto` to raise `TimeoutError`; asserts it propagates |

---

## Dependencies

Add to `requirements.txt` (or equivalent):
```
playwright
```

One-time setup required after install:
```
playwright install chromium
```

---

## Out of Scope

- Logged-in profile scraping (requires credentials)
- Profiles that are entirely private / set to connections-only
- Parsing structured sections of the LinkedIn DOM (handled by Claude instead, for resilience)
- Any changes to the sponsor filter, job searchers, or results display
