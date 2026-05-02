# Jie's Job Search — Design Spec

**Date:** 2026-05-02
**Status:** Approved

---

## Overview

A Streamlit web application that helps Jie find UK job listings from employers licensed to sponsor Skilled Worker visas. The app analyses an uploaded CV using the Claude API, searches multiple job platforms concurrently, filters results against the UK government's licensed sponsor register (Worker route only), and displays matching roles in a filterable table.

---

## Architecture

Single Streamlit app (`app.py`) backed by four modules:

```
app.py                  ← Streamlit UI entry point
cv_parser.py            ← CV text extraction + Claude API analysis
searchers/
  __init__.py
  jobspy.py             ← JobSpy client (LinkedIn + Indeed)
  reed.py               ← Reed API client
  nhs_jobs.py           ← NHS Jobs scraper (requests + BeautifulSoup)
  runner.py             ← ThreadPoolExecutor, concurrent search + deduplication
sponsor_filter.py       ← Gov.uk CSV download/cache + fuzzy employer matching
requirements.txt
.env.example
```

---

## Data Flow

1. User uploads CV (PDF, DOCX, or TXT)
2. `cv_parser.py` extracts text and sends it to Claude API, which returns structured JSON:
   - `job_titles`: suitable role titles inferred from the CV
   - `skills`: key technical skills
   - `search_queries`: 3–5 ready-to-use search strings (e.g. `"Data Engineer Python SQL Bristol"`)
3. App shows extracted job titles and search queries in an editable text area; user adjusts if needed
4. User sets location (default: **Bristol**) and minimum salary (default: **£60,000**), then clicks **Search**
5. `runner.py` launches one thread per platform via `ThreadPoolExecutor`
6. Each thread posts normalised results into a thread-safe queue; Streamlit polls it with `st.status` blocks showing per-platform progress
7. As each platform completes, its results are appended to the live results table
8. Once all threads finish, `sponsor_filter.py` cross-references every result's company name against the gov.uk sponsor CSV
9. Only sponsor-matched results are displayed; others are silently discarded

---

## Modules

### `cv_parser.py`

- Accepts PDF (via `PyMuPDF`), DOCX (via `python-docx`), or plain text
- Sends extracted text to Claude API with a prompt requesting structured JSON output
- Returns `{"job_titles": [...], "skills": [...], "search_queries": [...]}`
- Raises a clear exception if Claude API call fails (surfaces in UI before any search begins)

### `searchers/runner.py`

- Accepts a list of search query strings, location, and salary minimum
- Runs all four searchers concurrently via `ThreadPoolExecutor`
- Deduplicates results by URL before returning
- Each searcher returns a list of normalised job dicts (see below)
- Platform failures are caught per-thread; failed platforms return an empty list and log a warning

### Normalised Job Dict

```python
{
  "title": str,
  "company": str,       # used for sponsor matching
  "location": str,
  "salary": str,        # raw string, may be empty
  "description": str,   # brief snippet
  "url": str,
  "source": str         # "LinkedIn" | "Indeed" | "Reed" | "NHS Jobs"
}
```

### `searchers/jobspy.py`

- Uses the [JobSpy](https://github.com/Bunsly/JobSpy) library to scrape **LinkedIn** and **Indeed** concurrently
- No API key required — JobSpy handles scraping and anti-bot measures internally
- Returns results as a pandas DataFrame; normalised to the standard job dict before returning
- If scraping is blocked on either platform, logs a warning and returns results from whichever platforms succeeded
- LinkedIn/Indeed ToS technically prohibit scraping; treat as best-effort, same as NHS Jobs

### `searchers/reed.py`

- Uses the [Reed API](https://www.reed.co.uk/developers/jobseeker) (free, requires API key)
- UK-focused; strong permanent role listings

### `searchers/nhs_jobs.py`

- Scrapes `nhsjobs.com` using `requests` + `BeautifulSoup`
- No official API available; implementation may need updating if the site structure changes

### `searchers/linkedin.py`

- **Best-effort / experimental** — labelled clearly in the UI
- Uses Playwright (headless Chromium) to search `linkedin.com/jobs`
- If a login wall, CAPTCHA, or block is encountered, logs a warning and returns an empty list
- Never crashes the overall search on failure

### `sponsor_filter.py`

- Downloads the gov.uk Worker and Temporary Worker Licensed Sponsors CSV on first use per session and caches it in memory
- The CSV URL is dated (e.g. `2026-05-01_-_Worker_and_Temporary_Worker.csv`) and changes when the register is updated. The URL is configured via an env var (`SPONSOR_CSV_URL`) so it can be updated without a code change. Default URL points to the version in the spec; the gov.uk page to find the latest is: `https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers`
- Filters CSV to **Worker route only** (permanent Skilled Worker visa sponsorship)
- Matches job result company names against sponsor names using fuzzy matching (`rapidfuzz`, threshold ~85%)
- Falls back to a locally cached CSV file if the download fails; errors clearly if no cache exists
- Returns matched sponsor name alongside each passing result for transparency

---

## UI Flow

### State 1 — CV Upload

- `st.file_uploader` accepting PDF, DOCX, TXT
- On upload: spinner while Claude analyses the CV
- Displays extracted job titles and an editable `st.text_area` for search queries
- `st.text_input` for location (default: `Bristol`)
- `st.number_input` for minimum salary (default: `60000`)
- **Search** button

### State 2 — Searching

- Three `st.status` blocks, one per searcher, updating as threads complete:
  - e.g. `LinkedIn + Indeed ✓ — 41 results` / `Reed ✓ — 18 results` / `NHS Jobs ✓ — 5 results`
- Results appear in the table incrementally as each searcher finishes

### State 3 — Results

- Summary line: e.g. `"23 roles from licensed Worker-route sponsors"`
- If jobs were found but none passed sponsor filtering, show: `"47 jobs found across all platforms — 0 from licensed Worker-route sponsors"`
- `st.dataframe` with columns: Title, Company (matched sponsor name), Location, Salary, Description, Source, Link
- Sidebar filters: location keyword and minimum salary (adjustable without re-running the search)

---

## Error Handling

| Failure | Behaviour |
|---|---|
| Claude API error | Surface error before searching; do not proceed |
| Sponsor CSV fetch fails, no cache | Surface error before searching; do not proceed |
| Sponsor CSV fetch fails, cache exists | Use cached copy, show warning |
| JobSpy scrape blocked (LinkedIn/Indeed) | Show warning in status block with which platforms failed; continue with other results |
| Reed API error | Show warning in that platform's status block; continue with other results |
| NHS Jobs scrape error | Show warning in that platform's status block; continue |
| No results after sponsor filtering | Show explanatory message with raw result count |

---

## Configuration

All API keys stored in a `.env` file (not committed). Required variables:

```
ANTHROPIC_API_KEY=
REED_API_KEY=
SPONSOR_CSV_URL=https://www.gov.uk/csv-preview/69f47183ab602a88957eefa6/2026-05-01_-_Worker_and_Temporary_Worker.csv
```

---

## Testing

- Unit tests for `cv_parser.py` (mock Claude API responses)
- Unit tests for `sponsor_filter.py` (CSV fixture file + known company names, including fuzzy match edge cases)
- Unit tests for each searcher (mock HTTP responses / mock JobSpy)
- No live API calls in tests

---

## Known Limitations

- LinkedIn and Indeed coverage via JobSpy is best-effort — scraping may be blocked; no API key required but ToS apply
- Employer name fuzzy matching may produce false positives or false negatives at the margin; matched sponsor name is shown so Jie can verify
- Not all licensed sponsors actively offer sponsorship for every role — the filter is a necessary but not sufficient condition
- NHS Jobs scraper may break if the site structure changes

---
