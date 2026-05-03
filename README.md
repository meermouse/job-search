# Jie's Job Search

A Streamlit app that helps UK visa sponsorship candidates find jobs. It analyses your CV with Claude AI, searches multiple job platforms concurrently, and filters results to only show employers on the UK government's licensed Skilled Worker visa sponsor register.

## Features

- **CV analysis** — upload a PDF, DOCX, or TXT CV; Claude extracts your job titles, skills, and generates search queries
- **Multi-platform search** — searches LinkedIn, Indeed, Reed, and NHS Jobs concurrently
- **Sponsor filtering** — cross-references every result against the official UK Worker and Temporary Worker licensed sponsor register
- **Result filtering** — filter displayed results by location and minimum salary in the sidebar

## Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/)
- A [Reed API key](https://www.reed.co.uk/developers/jobseeker) (for Reed job search)

## Setup

**1. Clone and install dependencies**

```bash
git clone <repo-url>
cd job-search
pip install -r requirements.txt
```

**2. Configure environment variables**

Copy the example env file and fill in your API keys:

```bash
cp .env.example .env
```

Edit `.env`:

```
ANTHROPIC_API_KEY=your_anthropic_key_here
REED_API_KEY=your_reed_key_here
SPONSOR_CSV_URL=https://www.gov.uk/csv-preview/69f47183ab602a88957eefa6/2026-05-01_-_Worker_and_Temporary_Worker.csv
```

The `SPONSOR_CSV_URL` defaults to the UK government's latest sponsor register. Update it if a newer CSV is published.

## Launching the App

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501` in your browser.

## Usage

1. **Upload your CV** (PDF, DOCX, or TXT) — Claude analyses it and extracts job titles, skills, and suggested search queries
2. **Review and edit** the extracted queries, location, and minimum salary, then click **Search**
3. **Wait** while the app searches all platforms and loads the sponsor register (progress shown live)
4. **Browse results** in the table — only roles from licensed visa sponsors are shown. Use the sidebar to filter further by location or salary

## Running Tests

```bash
pytest
```

## Project Structure

```
app.py               # Streamlit UI
cv_parser.py         # CV text extraction and Claude analysis
sponsor_filter.py    # Loads sponsor register and filters job results
searchers/
  runner.py          # Concurrent search orchestration
  jobspy_searcher.py # LinkedIn + Indeed via python-jobspy
  reed.py            # Reed API searcher
  nhs_jobs.py        # NHS Jobs scraper
tests/               # pytest test suite
```

## Notes

- Not all licensed sponsors actively offer visa sponsorship for every role — the register is a necessary but not sufficient filter
- Job listings may not explicitly mention sponsorship; treat results as candidates requiring further verification
- The sponsor register CSV URL may change when the UK government publishes an updated version; keep `SPONSOR_CSV_URL` in `.env` current
