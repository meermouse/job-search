# Dismiss Jobs — Design Spec

**Date:** 2026-06-21
**Status:** Approved

---

## Overview

Add a "dismiss" feature to the daily job digest. Each email includes a link to a new Streamlit page that shows today's jobs in the same layout as the email. A "Dismiss" button on each row permanently removes that job from future digest emails. Dismissed rows grey out in place and can be restored.

---

## Architecture

Three new pieces, one change to the email:

| Piece | What it does |
|---|---|
| `today_jobs.json` | Written by `digest.py` after each run. Stores today's scored jobs by section (strong, worth a look, near misses) with the date. |
| `dismissed_jobs.json` | Stores the set of dismissed job URLs. Read by `digest.py` to filter before scoring; written by the dismiss page on every dismiss/restore action. |
| `pages/Dismiss_Jobs.py` | New Streamlit page. Reads both JSON files, renders the job table with a Dismiss column, handles state changes. |
| Email header link | `digest.py` inserts a "View and dismiss jobs" link at the very top of the email HTML. Points to `{SITE_URL}/Dismiss_Jobs`. `SITE_URL` is an env var. |

Both JSON files live in the project root alongside the existing caches (`job_score_cache.json`, `search_plan_cache.json`). This requires `digest.py` and the Streamlit app to share a filesystem — assumed to be the case since both run on the same server.

---

## Data Formats

### `today_jobs.json`
Written by `digest.py` immediately after sending the main email.

```json
{
  "date": "21 June 2026",
  "strong": [ ...job dicts... ],
  "worth_a_look": [ ...job dicts... ],
  "near_misses": [ ...job dicts... ]
}
```

Each job dict is the full job object as already constructed in `digest.py` (includes `title`, `company`, `location`, `salary`, `source`, `url`, `reasoning`, `score`).

### `dismissed_jobs.json`
Written by the dismiss page on every dismiss or restore action.

```json
{
  "dismissed_urls": [
    "https://example.com/job/123",
    "https://reed.co.uk/jobs/456"
  ]
}
```

If the file does not exist, it is treated as an empty dismissed list (no jobs dismissed).

---

## `digest.py` Changes

### 1. Filter dismissed jobs before evaluation

At the start of `main()`, load `dismissed_jobs.json` and extract the set of dismissed URLs. After `collect_jobs` / `search_agent.run_search_agent` returns raw jobs, filter out any job whose URL is in the dismissed set. This happens before scoring so dismissed jobs consume no API calls.

```python
def load_dismissed_urls(path: str = "dismissed_jobs.json") -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        data = json.load(f)
    return set(data.get("dismissed_urls", []))
```

### 2. Save today's jobs after sending

After `send_email(...)` for the main digest, write `today_jobs.json`:

```python
def save_today_jobs(
    strong: list[dict],
    worth_a_look: list[dict],
    near_misses: list[dict],
    today: str,
    path: str = "today_jobs.json",
) -> None:
    with open(path, "w") as f:
        json.dump({
            "date": today,
            "strong": strong,
            "worth_a_look": worth_a_look,
            "near_misses": near_misses,
        }, f, indent=2)
```

### 3. Email header link

At the top of `format_email_html()`, insert a link block if `SITE_URL` is set:

```python
site_url = os.environ.get("SITE_URL", "").rstrip("/")
dismiss_link = (
    f"<p><a href='{site_url}/Dismiss_Jobs'>View and dismiss today's jobs</a></p>"
    if site_url else ""
)
```

This is placed above the preamble in the returned HTML.

---

## `pages/Dismiss_Jobs.py`

### Page structure

```
st.title("Jie's Job Digest — {date}")
[optional: "{N} job(s) dismissed so far" counter]

## Strong matches
[table with Dismiss column]

## Worth a look
[table with Dismiss column]

## Near misses
[table with Dismiss column]
```

If `today_jobs.json` does not exist, show:
> "No jobs to review yet — check back after today's digest has run."

### Table rendering

Each section is rendered row by row using `st.columns`. Column widths:

```
[1, 4, 3, 2, 2, 1, 5]
 ^   ^   ^   ^   ^  ^  ^
btn title co  loc sal src reasoning
```

For each row:
- `is_dismissed = job["url"] in dismissed_set`
- Opacity wrapper: `<div style='opacity:0.4'>...</div>` for dismissed rows, `<div>...</div>` otherwise
- Button label: `"Restore"` if dismissed, `"Dismiss"` otherwise
- On button click: toggle the URL in `dismissed_set`, call `save_dismissed_urls()`, call `st.rerun()`

Job title is rendered as a clickable link: `<a href='{url}'>{title}</a>`.

### Dismissed state management

```python
def load_dismissed_urls(path: str = "dismissed_jobs.json") -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        data = json.load(f)
    return set(data.get("dismissed_urls", []))

def save_dismissed_urls(urls: set[str], path: str = "dismissed_jobs.json") -> None:
    with open(path, "w") as f:
        json.dump({"dismissed_urls": sorted(urls)}, f, indent=2)
```

Dismissed state is loaded from file on each page load. No separate session_state caching is needed — `st.rerun()` re-reads the file after each change, which is cheap for a small JSON file.

---

## Configuration

| Variable | Where | Purpose |
|---|---|---|
| `SITE_URL` | `.env` / deployment env | Base URL of the Streamlit app (e.g. `https://yourapp.streamlit.app`). Used to build the dismiss link in the email. If unset, the link is omitted silently. |

---

## Error Handling

- `today_jobs.json` missing → dismiss page shows "no jobs yet" message, no crash
- `dismissed_jobs.json` missing → treated as empty set, no crash
- `SITE_URL` not set → email link omitted silently, digest still sends normally
- File write failure on dismiss → surface as `st.error(...)` on the dismiss page

---

## Out of Scope

- Un-dismissing jobs from within the email itself
- Viewing or managing dismissed jobs from the main `app.py` Streamlit UI
- Expiring dismissed jobs after a time period
- Showing dismissed job count in the email
