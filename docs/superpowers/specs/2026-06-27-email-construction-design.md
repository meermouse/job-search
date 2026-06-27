# Email Construction Design

**Date:** 2026-06-27  
**Feature:** FE-007 — Construct and send job search results email  
**Branch:** feature/FE-007-construct-email

---

## Overview

Add an email construction and delivery step to the end of the job search pipeline. After jobs are fetched, filtered, and scored, the top 20 (by LLM score) are rendered into an HTML email and sent to the user via SMTP.

---

## Architecture

### New file

`src/job_search_email/email.py` — single module containing two public functions:

- `build_email_html(results: list[ScoredResult], profile: Profile) -> str`
- `send_email(html: str, profile: Profile) -> None`

### Modified files

| File | Change |
|---|---|
| `src/job_search_email/models.py` | Add `preamble: str` and `recipient_email: str` to `Profile` |
| `src/job_search_email/main.py` | Load new profile fields; call `build_email_html` + `send_email` at end of `main()` |
| `profile.yaml` | Add `recipient_email` field (top-level, alongside existing `preamble`) |
| `.github/workflows/daily_job.yml` | Add `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` env vars from GitHub secrets |

---

## Data Flow

### `build_email_html`

1. Filter `results` to non-rejected entries with a non-`None` analysis.
2. Sort by `analysis.score` descending.
3. Take first 20.
4. Render and return an HTML string (structure described below).

### `send_email`

1. Read `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` from environment variables.
2. If any are missing, print a warning to stderr and return without raising — allows local runs without credentials.
3. Build a `multipart/alternative` `email.message.EmailMessage` with the HTML body.
4. Send via `smtplib.SMTP` with STARTTLS on port 587.
5. Sender: `SMTP_USER`. Recipient: `profile.recipient_email`.
6. Subject: `"Job Search Results – {YYYY-MM-DD} ({n} jobs found)"`.

### `main()` wiring

Called at the very end of the pipeline, after `write_scored_results`:

```python
html = build_email_html(scored, profile)
send_email(html, profile)
```

---

## HTML Email Structure

Rendered with inline CSS only (required for Gmail/Outlook compatibility). No external resources, no images.

| Section | Content |
|---|---|
| **Preamble** | `profile.preamble` in a styled `<p>` header block |
| **Summary** | `"Here are your top {n} jobs from today's search, ranked by suitability."` |
| **Table** | One row per job — see columns below |
| **Footer** | `"Generated on {YYYY-MM-DD}"` |

### Table columns

| Column | Source | Notes |
|---|---|---|
| # | Row index (1-based) | |
| Score | `analysis.score` | Coloured badge: green 8–10, amber 5–7, red 1–4 |
| Job Title | `job.title` | Hyperlinked to `job.url` |
| Company | `job.company` | |
| Salary | `job.salary_min` | `£{n:,}` or *"Not stated"* |
| Verdict | `analysis.verdict` | LLM one-line summary |

### Styling

- White background, `font-family: Arial, sans-serif`
- Alternating light-grey table rows for readability
- Score badge: inline `<span>` with background colour, white text, rounded corners
- All styles inline; no `<style>` block (Outlook strips `<head>` styles)

---

## Configuration

### `profile.yaml` additions

```yaml
recipient_email: marc.j.brookes@gmail.com
preamble: "Hey Jie, its The Job Mule. Lets go through todays jobs."  # already present
```

### GitHub Action secrets required

| Secret name | Example value |
|---|---|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | `sender@gmail.com` |
| `SMTP_PASSWORD` | Gmail app password |

These are added to the workflow `env:` block and passed through to the running process.

---

## No new dependencies

All email functionality uses Python stdlib: `smtplib`, `email.message`, `datetime`. No packages to add to `pyproject.toml`.

---

## Out of scope

- Plain-text fallback part in the multipart email (HTML only for now)
- AI-generated preamble (static from `profile.yaml`)
- Jobs that failed analysis or were not analysed (excluded from the email table)
- Attachment of the full `job_results_scored.json` file
