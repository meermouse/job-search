# Dismiss Jobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dismiss page to the Streamlit app so Jie can permanently remove unwanted jobs from future daily digest emails via a link in the email itself.

**Architecture:** A new shared module (`dismiss_store.py`) handles all reads/writes to two JSON files — `dismissed_jobs.json` (persisted dismissed URLs) and `today_jobs.json` (today's emailed jobs). `digest.py` filters dismissed URLs before evaluation and saves today's jobs after sending. A new Streamlit page (`pages/Dismiss_Jobs.py`) reads those files, renders the same table structure as the email, and lets Jie dismiss or restore each job with a button.

**Tech Stack:** Python 3.11, Streamlit, pytest, `unittest.mock` — all already in use.

## Global Constraints

- All file paths default to the project root (same directory as `digest.py` and `app.py`)
- JSON files use `indent=2` for readability
- Dismissed URLs are stored sorted to keep diffs clean
- `SITE_URL` env var holds the Streamlit app base URL (e.g. `https://yourapp.streamlit.app`) — if unset, the email link is silently omitted
- Follow the existing test pattern: `from <module> import <function>` inside each test, `unittest.mock.patch` for dependencies, `tmp_path` for file I/O tests

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `dismiss_store.py` | Load/save `dismissed_jobs.json` and `today_jobs.json` |
| Create | `tests/test_dismiss_store.py` | Tests for all four dismiss_store functions |
| Modify | `digest.py` | Import dismiss_store; filter dismissed jobs in main(); save today_jobs after send; add email link in format_email_html |
| Modify | `tests/test_digest.py` | Two new tests for email link; one new test for dismiss filtering; mock `dismiss_store.save_today_jobs` in all existing test_main_* tests |
| Create | `pages/Dismiss_Jobs.py` | Streamlit dismiss page |

---

## Task 1: `dismiss_store.py` — shared persistence module

**Files:**
- Create: `dismiss_store.py`
- Create: `tests/test_dismiss_store.py`

**Interfaces:**
- Produces:
  - `load_dismissed_urls(path: str = "dismissed_jobs.json") -> set[str]`
  - `save_dismissed_urls(urls: set[str], path: str = "dismissed_jobs.json") -> None`
  - `load_today_jobs(path: str = "today_jobs.json") -> dict | None`
  - `save_today_jobs(strong, worth_a_look, near_misses, today, path="today_jobs.json") -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dismiss_store.py`:

```python
import json
import pytest


def test_load_dismissed_urls_returns_empty_set_when_file_missing(tmp_path):
    from dismiss_store import load_dismissed_urls
    result = load_dismissed_urls(str(tmp_path / "dismissed_jobs.json"))
    assert result == set()


def test_load_dismissed_urls_returns_urls_from_file(tmp_path):
    from dismiss_store import load_dismissed_urls
    path = tmp_path / "dismissed_jobs.json"
    path.write_text(json.dumps({"dismissed_urls": ["https://a.com/1", "https://b.com/2"]}))
    result = load_dismissed_urls(str(path))
    assert result == {"https://a.com/1", "https://b.com/2"}


def test_load_dismissed_urls_handles_empty_list(tmp_path):
    from dismiss_store import load_dismissed_urls
    path = tmp_path / "dismissed_jobs.json"
    path.write_text(json.dumps({"dismissed_urls": []}))
    result = load_dismissed_urls(str(path))
    assert result == set()


def test_save_dismissed_urls_writes_sorted_list(tmp_path):
    from dismiss_store import save_dismissed_urls
    path = tmp_path / "dismissed_jobs.json"
    save_dismissed_urls({"https://b.com/2", "https://a.com/1"}, str(path))
    data = json.loads(path.read_text())
    assert data == {"dismissed_urls": ["https://a.com/1", "https://b.com/2"]}


def test_save_then_load_dismissed_urls_roundtrip(tmp_path):
    from dismiss_store import save_dismissed_urls, load_dismissed_urls
    path = str(tmp_path / "dismissed_jobs.json")
    urls = {"https://example.com/1", "https://example.com/2"}
    save_dismissed_urls(urls, path)
    assert load_dismissed_urls(path) == urls


def test_load_today_jobs_returns_none_when_file_missing(tmp_path):
    from dismiss_store import load_today_jobs
    result = load_today_jobs(str(tmp_path / "today_jobs.json"))
    assert result is None


def test_load_today_jobs_returns_dict(tmp_path):
    from dismiss_store import load_today_jobs
    path = tmp_path / "today_jobs.json"
    payload = {"date": "21 June 2026", "strong": [], "worth_a_look": [], "near_misses": []}
    path.write_text(json.dumps(payload))
    result = load_today_jobs(str(path))
    assert result == payload


def test_save_today_jobs_writes_correct_structure(tmp_path):
    from dismiss_store import save_today_jobs
    path = str(tmp_path / "today_jobs.json")
    strong = [{"title": "Manager", "url": "https://a.com/1"}]
    save_today_jobs(strong, [], [], "21 June 2026", path)
    data = json.loads((tmp_path / "today_jobs.json").read_text())
    assert data["date"] == "21 June 2026"
    assert data["strong"] == strong
    assert data["worth_a_look"] == []
    assert data["near_misses"] == []


def test_save_today_jobs_roundtrip(tmp_path):
    from dismiss_store import save_today_jobs, load_today_jobs
    path = str(tmp_path / "today_jobs.json")
    strong = [{"title": "A", "url": "https://a.com"}]
    near = [{"title": "B", "url": "https://b.com"}]
    save_today_jobs(strong, [], near, "21 June 2026", path)
    result = load_today_jobs(path)
    assert result["strong"] == strong
    assert result["near_misses"] == near
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_dismiss_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'dismiss_store'`

- [ ] **Step 3: Create `dismiss_store.py`**

```python
import json
import os


def load_dismissed_urls(path: str = "dismissed_jobs.json") -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        data = json.load(f)
    return set(data.get("dismissed_urls", []))


def save_dismissed_urls(urls: set[str], path: str = "dismissed_jobs.json") -> None:
    with open(path, "w") as f:
        json.dump({"dismissed_urls": sorted(urls)}, f, indent=2)


def load_today_jobs(path: str = "today_jobs.json") -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def save_today_jobs(
    strong: list[dict],
    worth_a_look: list[dict],
    near_misses: list[dict],
    today: str,
    path: str = "today_jobs.json",
) -> None:
    with open(path, "w") as f:
        json.dump(
            {
                "date": today,
                "strong": strong,
                "worth_a_look": worth_a_look,
                "near_misses": near_misses,
            },
            f,
            indent=2,
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_dismiss_store.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add dismiss_store.py tests/test_dismiss_store.py
git commit -m "feat: add dismiss_store module for dismissed jobs and today's job persistence"
```

---

## Task 2: Add dismiss link to the digest email

**Files:**
- Modify: `digest.py` — `format_email_html()` only
- Modify: `tests/test_digest.py` — two new tests appended at the end

**Interfaces:**
- Consumes: `os.environ.get("SITE_URL", "")` — read inside `format_email_html()`
- `format_email_html` signature does not change

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_digest.py`:

```python
def test_format_email_html_includes_dismiss_link_when_site_url_set():
    from digest import format_email_html
    with patch.dict("os.environ", {"SITE_URL": "https://myapp.streamlit.app"}):
        html = format_email_html([], "Summary.", "21 June 2026")
    assert "https://myapp.streamlit.app/Dismiss_Jobs" in html
    assert "View and dismiss" in html


def test_format_email_html_omits_dismiss_link_when_site_url_empty():
    from digest import format_email_html
    with patch.dict("os.environ", {"SITE_URL": ""}):
        html = format_email_html([], "Summary.", "21 June 2026")
    assert "Dismiss_Jobs" not in html
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_digest.py::test_format_email_html_includes_dismiss_link_when_site_url_set tests/test_digest.py::test_format_email_html_omits_dismiss_link_when_site_url_empty -v
```

Expected: both FAIL — `Dismiss_Jobs` not yet in HTML

- [ ] **Step 3: Modify `format_email_html` in `digest.py`**

Replace the opening of `format_email_html`:

```python
def format_email_html(
    strong_jobs: list[dict],
    summary: str,
    today: str,
    preamble: str = "",
    worth_a_look: list[dict] | None = None,
    near_misses: list[dict] | None = None,
) -> str:
    site_url = os.environ.get("SITE_URL", "").rstrip("/")
    dismiss_link_html = (
        f"<p style='margin-bottom:12px'>"
        f"<a href='{site_url}/Dismiss_Jobs'>View and dismiss today's jobs</a>"
        f"</p>"
        if site_url else ""
    )
    preamble_html = md_lib.markdown(preamble) if preamble else ""
    strong_table = _make_table(strong_jobs, include_reasoning=True)
    worth_table = _make_table(worth_a_look or [], include_reasoning=True)
    near_misses_table = _make_table(near_misses or [], include_reasoning=True)

    strong_section = f"<h3>Strong matches</h3>{strong_table}" if strong_table else ""
    worth_section = f"<h3>Worth a look</h3>{worth_table}" if worth_table else ""
    near_misses_section = (
        f"<h3>Near misses — why today's closest results didn't make it</h3>"
        f"<p style='color:#666;font-size:0.9em'>These scored too low to recommend, "
        f"but are shown so you can see what came up and why it was filtered out.</p>"
        f"{near_misses_table}"
    ) if near_misses_table else ""

    return (
        f"<html><body>"
        f"<h2>Jie's Job Digest — {html.escape(today)}</h2>"
        f"{dismiss_link_html}"
        f"{preamble_html}"
        f"<hr/>"
        f"{md_lib.markdown(summary)}"
        f"{strong_section}"
        f"{worth_section}"
        f"{near_misses_section}"
        f"</body></html>"
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_digest.py -v
```

Expected: all existing tests plus the two new ones PASS

- [ ] **Step 5: Commit**

```bash
git add digest.py tests/test_digest.py
git commit -m "feat: add dismiss link to digest email when SITE_URL is set"
```

---

## Task 3: Filter dismissed jobs and save today's jobs in `digest.main()`

**Files:**
- Modify: `digest.py` — `main()` only
- Modify: `tests/test_digest.py` — one new test; six existing test_main_* tests updated

**Interfaces:**
- Consumes:
  - `dismiss_store.load_dismissed_urls() -> set[str]`
  - `dismiss_store.save_today_jobs(strong, worth_a_look, near_misses, today) -> None`

- [ ] **Step 1: Write the new failing test**

Append to `tests/test_digest.py`:

```python
def test_main_filters_dismissed_jobs_before_evaluation():
    from digest import main

    config = {
        "profile": {
            "name": "Jie",
            "current_role": "Operations Director",
            "seniority": "Senior",
            "industry": "NHS",
            "skills": [],
            "previous_roles": [],
            "target_roles": [],
            "open_to": [],
            "qualifications": [],
            "employment_type": ["full-time"],
        },
        "location": "Bristol",
        "min_salary": 60000,
    }
    mock_plan = {
        "queries": [],
        "locations": ["Bristol"],
        "exclusion_keywords": [],
        "employment_type_exclusions": [],
        "nhs_band_floor": {"default": "8a", "london_remote_exception": "7"},
        "candidate_qualifications": [],
        "evaluator_notes": "",
    }
    kept_job = {
        "title": "Manager",
        "company": "Org A",
        "url": "https://example.com/kept",
        "location": "Bristol",
        "salary": "£70k",
        "source": "Reed",
        "score": 4,
        "score_breakdown": {},
        "reasoning": "Good match.",
    }
    dismissed_job = {
        "title": "Admin",
        "company": "Org B",
        "url": "https://example.com/dismissed",
        "location": "Bristol",
        "salary": "£60k",
        "source": "Reed",
        "score": 4,
        "score_breakdown": {},
        "reasoning": "Also good.",
    }

    with patch("digest.load_config", return_value=config), \
         patch("digest.job_planner.create_plan", return_value=mock_plan), \
         patch("digest.search_agent.run_search_agent",
               return_value=([kept_job, dismissed_job], "Searched.", [])), \
         patch("digest.job_evaluator.evaluate", return_value=[kept_job]) as mock_eval, \
         patch("digest.format_email_html", return_value="<html>"), \
         patch("digest.send_email"), \
         patch("digest.dismiss_store.load_dismissed_urls",
               return_value={"https://example.com/dismissed"}), \
         patch("digest.dismiss_store.save_today_jobs"), \
         patch.dict(os.environ, {
             "RECIPIENT_EMAIL": "jie@example.com",
             "GMAIL_USER": "a@gmail.com",
             "GMAIL_APP_PASSWORD": "pw",
         }):
        main()

    eval_jobs = mock_eval.call_args[0][0]
    assert len(eval_jobs) == 1
    assert eval_jobs[0]["url"] == "https://example.com/kept"
```

- [ ] **Step 2: Run the new test to confirm it fails**

```
pytest tests/test_digest.py::test_main_filters_dismissed_jobs_before_evaluation -v
```

Expected: FAIL — evaluator receives both jobs (no filtering yet)

- [ ] **Step 3: Modify `main()` in `digest.py`**

Add `import dismiss_store` at the top of `digest.py` (after the existing imports):

```python
import dismiss_store
```

Then replace the body of `main()` with the version below. Changes are marked with `# NEW`:

```python
def main() -> None:
    config = load_config()
    dismissed_urls = dismiss_store.load_dismissed_urls()  # NEW

    if "profile" in config:
        fingerprint = _plan_fingerprint(
            config["profile"], config["location"], config["min_salary"]
        )
        plan = load_or_create_plan(
            config["profile"], config["location"], config["min_salary"]
        )
        raw_jobs, strategy_note, filter_log = search_agent.run_search_agent(
            config["profile"], plan, config["location"], config["min_salary"]
        )
        raw_jobs = [j for j in raw_jobs if j.get("url") not in dismissed_urls]  # NEW

        job_cache = load_job_cache(fingerprint)
        cache_size_before = sum(1 for k in job_cache if not k.startswith("_"))
        cached_scored, jobs_to_eval = apply_job_cache(raw_jobs, job_cache)
        cache_hits = len(cached_scored)
        logger.info(
            "Job score cache: %d stored, %d hit(s) today, %d to evaluate",
            cache_size_before, cache_hits, len(jobs_to_eval),
        )

        newly_scored = job_evaluator.evaluate(
            jobs_to_eval, plan, config["profile"], config["min_salary"]
        )
        for j in newly_scored:
            url = j.get("url", "")
            if url and j.get("score") is not None:
                job_cache[url] = {
                    "score": j["score"],
                    "reasoning": j.get("reasoning", ""),
                    "score_breakdown": j.get("score_breakdown", {}),
                    "cached_at": date.today().isoformat(),
                }
        save_job_cache(job_cache)

        scored_jobs = cached_scored + newly_scored

        meta = next((e for e in filter_log if e.get("_meta")), None)
        if meta is not None:
            meta["job_cache_size"] = cache_size_before
            meta["job_cache_hits"] = cache_hits
        strong = [j for j in scored_jobs if j.get("score", 0) >= 4]
        worth_a_look = [j for j in scored_jobs if j.get("score", 0) == 3]
        unscored = [j for j in scored_jobs if j.get("score") is None]
        if unscored:
            logger.warning("%d job(s) returned unscored and excluded from email", len(unscored))
        for j in scored_jobs:
            score = j.get("score")
            if score is None:
                filter_log.append({
                    "stage": "Evaluator",
                    "title": j.get("title", ""),
                    "company": j.get("company", ""),
                    "url": j.get("url", ""),
                    "reason": "Not scored by evaluator",
                })
            elif score in (1, 2):
                reasoning = j.get("reasoning", "")
                short = reasoning.split(".")[0] if reasoning else ""
                filter_log.append({
                    "stage": "Evaluator",
                    "title": j.get("title", ""),
                    "company": j.get("company", ""),
                    "url": j.get("url", ""),
                    "reason": f"Score {score}/5 — {short}" if short else f"Score {score}/5",
                })
        if not strong and not worth_a_look:
            near_misses = sorted(
                [j for j in scored_jobs if j.get("score") in (1, 2)],
                key=lambda j: j["score"],
                reverse=True,
            )[:5]
            summary = "No roles met the scoring threshold today. " + strategy_note
        else:
            near_misses = []
            summary = strategy_note
        count = len(strong) + len(worth_a_look)
    else:
        filter_log = None
        jobs = collect_jobs(config["search_queries"], config["location"], config["min_salary"])
        sponsor_names = sponsor_filter.load_sponsor_names()
        filtered = sponsor_filter.filter_jobs(jobs, sponsor_names)
        filtered = [j for j in filtered if j.get("url") not in dismissed_urls]  # NEW
        summary = (
            analyse_results(filtered, config)
            if filtered
            else "No matching roles were found today from licensed UK visa sponsors."
        )
        strong = filtered
        worth_a_look = []
        near_misses = []
        count = len(strong)

    today = date.today().strftime("%d %B %Y")
    subject = f"Job digest — {count} match{'es' if count != 1 else ''} — {today}"
    preamble = config.get("preamble", "")
    html_body = format_email_html(
        strong, summary, today, preamble, worth_a_look=worth_a_look, near_misses=near_misses
    )
    send_email(
        subject=subject,
        html_body=html_body,
        recipient=os.environ["RECIPIENT_EMAIL"],
        gmail_user=os.environ["GMAIL_USER"],
        gmail_app_password=os.environ["GMAIL_APP_PASSWORD"],
    )
    dismiss_store.save_today_jobs(strong, worth_a_look, near_misses, today)  # NEW

    if filter_log is not None:
        log_html = format_log_email_html(filter_log, today)
        jsonl_filename = f"filter-log-{date.today().isoformat()}.jsonl"
        jsonl_bytes = build_run_jsonl(filter_log, today, count)
        send_email(
            subject=f"Filter log — {len(filter_log)} decisions — {today}",
            html_body=log_html,
            recipient=os.environ["GMAIL_USER"],
            gmail_user=os.environ["GMAIL_USER"],
            gmail_app_password=os.environ["GMAIL_APP_PASSWORD"],
            attachment=(jsonl_filename, jsonl_bytes),
        )
```

- [ ] **Step 4: Update existing test_main_* tests to mock `save_today_jobs`**

Each of the six existing `test_main_*` tests calls `main()`, which now calls `dismiss_store.save_today_jobs()`. Add `patch("digest.dismiss_store.save_today_jobs")` to every `with patch(...)` block in those tests. Below are the complete updated `with` blocks for each — only the mock list changes, nothing else.

**`test_main_sends_email_when_jobs_found`** — add one line:
```python
    with patch("digest.load_config", return_value=config), \
         patch("digest.collect_jobs", return_value=filtered_jobs), \
         patch("digest.sponsor_filter.load_sponsor_names", return_value=["NHS Digital"]), \
         patch("digest.sponsor_filter.filter_jobs", return_value=filtered_jobs), \
         patch("digest.analyse_results", return_value="Great match!"), \
         patch("digest.format_email_html", return_value="<html>content</html>"), \
         patch("digest.send_email") as mock_send, \
         patch("digest.dismiss_store.save_today_jobs"), \
         patch.dict("os.environ", {"GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw", "RECIPIENT_EMAIL": "jie@example.com"}):
```

**`test_main_sends_email_when_no_jobs_found`** — add one line:
```python
    with patch("digest.load_config", return_value=config), \
         patch("digest.collect_jobs", return_value=[]), \
         patch("digest.sponsor_filter.load_sponsor_names", return_value=[]), \
         patch("digest.sponsor_filter.filter_jobs", return_value=[]), \
         patch("digest.analyse_results") as mock_analyse, \
         patch("digest.format_email_html", return_value="<html>no matches</html>"), \
         patch("digest.send_email") as mock_send, \
         patch("digest.dismiss_store.save_today_jobs"), \
         patch.dict("os.environ", {"GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw", "RECIPIENT_EMAIL": "jie@example.com"}):
```

**`test_main_uses_three_phase_pipeline_when_profile_present`** — add one line:
```python
    with patch("digest.load_config", return_value=config), \
         patch("digest.job_planner.create_plan", return_value=mock_plan) as mock_planner, \
         patch("digest.search_agent.run_search_agent", return_value=([mock_job], "Searched 2 angles.", [])) as mock_agent, \
         patch("digest.job_evaluator.evaluate", return_value=[mock_job]) as mock_eval, \
         patch("digest.format_email_html", return_value="<html>") as mock_html, \
         patch("digest.send_email") as mock_send, \
         patch("digest.dismiss_store.save_today_jobs"), \
         patch.dict(os.environ, {"RECIPIENT_EMAIL": "jie@example.com", "GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
```

**`test_main_shows_near_misses_when_no_results_pass_threshold`** — add one line:
```python
    with patch("digest.load_config", return_value=config), \
         patch("digest.job_planner.create_plan", return_value=mock_plan), \
         patch("digest.search_agent.run_search_agent", return_value=(scored_jobs, "Searched 1 angle.", [])), \
         patch("digest.job_evaluator.evaluate", return_value=scored_jobs), \
         patch("digest.format_email_html", return_value="<html>") as mock_html, \
         patch("digest.send_email"), \
         patch("digest.dismiss_store.save_today_jobs"), \
         patch.dict(os.environ, {"RECIPIENT_EMAIL": "jie@example.com", "GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
```

**`test_main_does_not_show_near_misses_when_results_exist`** — add one line:
```python
    with patch("digest.load_config", return_value=config), \
         patch("digest.job_planner.create_plan", return_value=mock_plan), \
         patch("digest.search_agent.run_search_agent", return_value=([strong_job], "Searched.", [])), \
         patch("digest.job_evaluator.evaluate", return_value=[strong_job]), \
         patch("digest.format_email_html", return_value="<html>") as mock_html, \
         patch("digest.send_email"), \
         patch("digest.dismiss_store.save_today_jobs"), \
         patch.dict(os.environ, {"RECIPIENT_EMAIL": "jie@example.com", "GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
```

**`test_main_uses_static_queries_when_no_profile_in_config`** — add one line:
```python
    with patch("digest.load_config", return_value=config), \
         patch("digest.collect_jobs", return_value=[]) as mock_collect, \
         patch("digest.sponsor_filter.load_sponsor_names", return_value=[]), \
         patch("digest.sponsor_filter.filter_jobs", return_value=[]), \
         patch("digest.format_email_html", return_value="<html>"), \
         patch("digest.send_email"), \
         patch("digest.dismiss_store.save_today_jobs"), \
         patch.dict(os.environ, {"RECIPIENT_EMAIL": "jie@example.com", "GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
```

- [ ] **Step 5: Run all tests to confirm they pass**

```
pytest tests/test_digest.py -v
```

Expected: all tests PASS including the new `test_main_filters_dismissed_jobs_before_evaluation`

- [ ] **Step 6: Commit**

```bash
git add digest.py tests/test_digest.py
git commit -m "feat: filter dismissed jobs before evaluation and save today's jobs after digest send"
```

---

## Task 4: Create the dismiss page

**Files:**
- Create: `pages/Dismiss_Jobs.py`

**Interfaces:**
- Consumes:
  - `dismiss_store.load_today_jobs() -> dict | None`
  - `dismiss_store.load_dismissed_urls() -> set[str]`
  - `dismiss_store.save_dismissed_urls(urls: set[str]) -> None`

- [ ] **Step 1: Create `pages/Dismiss_Jobs.py`**

```python
import streamlit as st
import dismiss_store

st.set_page_config(page_title="Dismiss Jobs", layout="wide")

today_data = dismiss_store.load_today_jobs()
if today_data is None:
    st.title("Jie's Job Digest — Dismiss Jobs")
    st.info("No jobs to review yet — check back after today's digest has run.")
    st.stop()

date_str = today_data.get("date", "")
st.title(f"Jie's Job Digest — {date_str}")

dismissed_set = dismiss_store.load_dismissed_urls()

total_jobs = sum(
    len(today_data.get(k, []))
    for k in ("strong", "worth_a_look", "near_misses")
)
dismissed_count = sum(
    1
    for k in ("strong", "worth_a_look", "near_misses")
    for j in today_data.get(k, [])
    if j.get("url") in dismissed_set
)
if dismissed_count:
    st.caption(f"{dismissed_count} of {total_jobs} job(s) dismissed")


def _render_section(section_key: str, heading: str, jobs: list[dict]) -> None:
    if not jobs:
        return
    st.subheader(heading)
    header_cols = st.columns([1, 4, 3, 2, 2, 1, 5])
    for label, col in zip(
        ["Dismiss", "Job Title", "Company", "Location", "Salary", "Source", "Why"],
        header_cols,
    ):
        col.markdown(f"**{label}**")

    for idx, job in enumerate(jobs):
        url = job.get("url", "")
        is_dismissed = url in dismissed_set
        opacity = "0.4" if is_dismissed else "1.0"

        row_cols = st.columns([1, 4, 3, 2, 2, 1, 5])

        with row_cols[0]:
            btn_label = "Restore" if is_dismissed else "Dismiss"
            if st.button(btn_label, key=f"{section_key}_{idx}"):
                if is_dismissed:
                    dismissed_set.discard(url)
                else:
                    dismissed_set.add(url)
                try:
                    dismiss_store.save_dismissed_urls(dismissed_set)
                except Exception as e:
                    st.error(f"Could not save: {e}")
                st.rerun()

        title_html = (
            f"<a href='{url}'>{job.get('title', '')}</a>"
            if url
            else job.get("title", "")
        )
        company = job.get("sponsor_name") or job.get("company", "")
        cells = [
            title_html,
            company,
            job.get("location", ""),
            job.get("salary", ""),
            job.get("source", ""),
            job.get("reasoning", ""),
        ]
        for cell_html, col in zip(cells, row_cols[1:]):
            col.markdown(
                f"<div style='opacity:{opacity}'>{cell_html}</div>",
                unsafe_allow_html=True,
            )


_render_section("strong", "Strong matches", today_data.get("strong", []))
_render_section("worth", "Worth a look", today_data.get("worth_a_look", []))
_render_section("near", "Near misses", today_data.get("near_misses", []))
```

- [ ] **Step 2: Run the full test suite to confirm nothing broke**

```
pytest tests/ -v
```

Expected: all tests PASS

- [ ] **Step 3: Smoke test the dismiss page manually**

Run the Streamlit app:
```
streamlit run app.py
```

Navigate to the Dismiss Jobs page in the sidebar (it will appear automatically as a new page).

Without `today_jobs.json` present, you should see: "No jobs to review yet — check back after today's digest has run."

To test with real data, create a minimal `today_jobs.json` in the project root:
```json
{
  "date": "21 June 2026",
  "strong": [
    {
      "title": "Test Job",
      "company": "Test Co",
      "sponsor_name": "Test Co",
      "location": "Bristol",
      "salary": "£70,000",
      "source": "Reed",
      "url": "https://example.com/job/1",
      "reasoning": "Strong match for skills."
    }
  ],
  "worth_a_look": [],
  "near_misses": []
}
```

Verify:
- The page title shows "Jie's Job Digest — 21 June 2026"
- The "Strong matches" section renders with columns
- Clicking "Dismiss" greys the row and changes the button to "Restore"
- Clicking "Restore" restores the row opacity and changes the button back to "Dismiss"
- `dismissed_jobs.json` is created/updated in the project root after dismissing

Delete the test files when done:
```bash
rm today_jobs.json dismissed_jobs.json
```

- [ ] **Step 4: Add `SITE_URL` to `.env`**

Open `.env` (or `.env.example` if `.env` doesn't exist) and add:
```
SITE_URL=https://your-app-name.streamlit.app
```

Replace `your-app-name` with the actual Streamlit Cloud app URL. This enables the dismiss link in the digest email.

- [ ] **Step 5: Commit**

```bash
git add pages/Dismiss_Jobs.py .env.example
git commit -m "feat: add Dismiss Jobs Streamlit page and SITE_URL config"
```
