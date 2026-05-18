# Daily Job Search Email Digest — Design Spec

**Date:** 2026-05-18
**Status:** Approved

---

## Overview

A GitHub Actions cron workflow that runs daily at 7am UTC, independently of any Streamlit session. It runs the configured job searches using the existing application modules, filters results against the UK sponsor register, asks Claude to analyse and summarise the results, then sends an HTML email digest to the recipient.

Marc manages the search configuration by editing a committed YAML file. Jie receives the email and does not interact with any tooling.

---

## Architecture

Three new files are added. No existing files are modified.

```
digest_config.yaml                      ← search config committed to repo
digest.py                               ← standalone runner script
.github/workflows/daily-digest.yml      ← GitHub Actions cron workflow
```

Existing modules reused without modification:

- `searchers/runner.py` — concurrent job search across all platforms
- `sponsor_filter.py` — gov.uk sponsor register filtering

---

## `digest_config.yaml`

Committed to the repo. Edited by Marc when search queries need updating.

```yaml
search_queries:
  - "Data Engineer Python SQL Bristol"
  - "ML Engineer Bristol"
  - "Backend Engineer Python Bristol"
location: Bristol
min_salary: 60000
recipient_email: jie@example.com
```

---

## `digest.py` — Script Flow

1. **Load config** — reads `digest_config.yaml`
2. **Run searches** — calls `searchers/runner.py` with `search_queries`, `location`, `min_salary`
3. **Filter sponsors** — passes results through `sponsor_filter.py`
4. **AI analysis** — sends filtered results to Claude API; receives a short summary and ranked recommendations (e.g. "3 strong matches today — the NHS Data Engineer role stands out because...")
5. **Send email** — HTML email with AI summary at top, full results table below; sent via Gmail SMTP (`smtplib`, Python built-in)

**No-results case:** if zero results pass sponsor filtering, still send a short "no matches today" email confirming the digest ran.

**Error behaviour:** unhandled exceptions cause the workflow to fail. GitHub automatically emails the repo owner on workflow failure — no additional error notification code is needed.

---

## Email Format

- **Subject:** `Job digest — {N} matches — {date}`
- **Body (HTML):**
  1. AI summary paragraph with ranked recommendations
  2. Results table: Job Title | Company | Location | Salary | Source | Link (clickable)

---

## AI Analysis Prompt

Claude receives the list of filtered job results and is asked to:
- Summarise the day's results in 2–4 sentences
- Highlight 2–3 standout roles and briefly explain why each is a strong match
- Note any patterns (e.g. many NHS roles, or a cluster in a particular specialism)

The prompt includes Jie's search context (job titles, location, salary floor) so recommendations are personalised.

---

## `.github/workflows/daily-digest.yml`

```yaml
on:
  schedule:
    - cron: "0 7 * * *"   # 7am UTC daily (8am BST / 7am GMT)
  workflow_dispatch:        # allow manual trigger for testing
```

Steps: checkout → setup Python → `pip install -r requirements.txt` → `python digest.py`

All secrets injected as environment variables.

---

## GitHub Secrets Required

Set once in GitHub repo Settings → Secrets and variables → Actions.

| Secret | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API (same key used by Streamlit app) |
| `REED_API_KEY` | Reed job search (same key used by Streamlit app) |
| `SPONSOR_CSV_URL` | Gov.uk sponsor CSV URL (same as app) |
| `GMAIL_USER` | Gmail address to send from |
| `GMAIL_APP_PASSWORD` | Gmail App Password (generated in Google Account settings) |

`recipient_email` is stored in `digest_config.yaml`, not in secrets.

---

## Dependencies

No new packages. `smtplib` and `ssl` are Python standard library. PyYAML (`pyyaml`) will be added to `requirements.txt` for reading the config file.

---

## Testing

- `digest.py` can be triggered manually via `workflow_dispatch` in the GitHub Actions UI before the first scheduled run
- The workflow can also be run locally with `python digest.py` provided the required environment variables are set

---

## Known Limitations

- Schedule is UTC-based; offset from UK local time varies between BST (+1h) and GMT (±0h)
- GitHub Actions cron can be delayed up to ~15 minutes during high load (rare)
- JobSpy scraping of LinkedIn/Indeed is best-effort and may return fewer results than the interactive app on some days
