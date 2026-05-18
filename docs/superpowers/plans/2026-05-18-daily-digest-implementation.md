# Daily Email Digest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a GitHub Actions cron job that runs job searches daily, filters by visa sponsor, asks Claude for a summary, and emails the results.

**Architecture:** Three new files — `digest_config.yaml` (search config), `digest.py` (standalone script reusing existing modules), and `.github/workflows/daily-digest.yml` (cron workflow). No existing files are modified except `requirements.txt` (add `pyyaml`).

**Tech Stack:** Python `smtplib`/`ssl` (stdlib), `pyyaml`, `anthropic`, existing `searchers` and `sponsor_filter` modules, GitHub Actions.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `requirements.txt` | Modify | Add `pyyaml>=6.0.0` |
| `digest_config.yaml` | Create | Search config committed to repo |
| `digest.py` | Create | Standalone digest script |
| `tests/test_digest.py` | Create | Unit tests for digest.py |
| `.github/workflows/daily-digest.yml` | Create | GitHub Actions cron workflow |

---

## Task 1: Add pyyaml and create digest_config.yaml

**Files:**
- Modify: `requirements.txt`
- Create: `digest_config.yaml`

- [ ] **Step 1: Add pyyaml to requirements.txt**

Add this line after the last entry in `requirements.txt`:

```
pyyaml>=6.0.0
```

- [ ] **Step 2: Create digest_config.yaml**

```yaml
search_queries:
  - "Data Engineer Python SQL Bristol"
  - "ML Engineer Bristol"
  - "Backend Engineer Python Bristol"
location: Bristol
min_salary: 60000
recipient_email: jie@example.com
```

- [ ] **Step 3: Install updated dependencies**

Run: `pip install -r requirements.txt`
Expected: installs PyYAML with no errors

- [ ] **Step 4: Commit**

```bash
git add requirements.txt digest_config.yaml
git commit -m "feat: add pyyaml dependency and digest config file"
```

---

## Task 2: load_config()

**Files:**
- Create: `digest.py`
- Create: `tests/test_digest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_digest.py`:

```python
import yaml
import pytest


def test_load_config_returns_expected_keys(tmp_path):
    from digest import load_config

    cfg = {
        "search_queries": ["Data Engineer Bristol"],
        "location": "Bristol",
        "min_salary": 60000,
        "recipient_email": "test@example.com",
    }
    config_file = tmp_path / "digest_config.yaml"
    config_file.write_text(yaml.dump(cfg))

    result = load_config(str(config_file))

    assert result["search_queries"] == ["Data Engineer Bristol"]
    assert result["location"] == "Bristol"
    assert result["min_salary"] == 60000
    assert result["recipient_email"] == "test@example.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_digest.py::test_load_config_returns_expected_keys -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'digest'`

- [ ] **Step 3: Implement load_config() in digest.py**

Create `digest.py`:

```python
import os
import smtplib
import ssl
import logging
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
import yaml

import sponsor_filter
from searchers import search_all_streaming

logger = logging.getLogger(__name__)


def load_config(path: str = "digest_config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_digest.py::test_load_config_returns_expected_keys -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digest.py tests/test_digest.py
git commit -m "feat: add digest.py with load_config"
```

---

## Task 3: collect_jobs()

**Files:**
- Modify: `digest.py`
- Modify: `tests/test_digest.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_digest.py`:

```python
from unittest.mock import patch


def _make_job(url, source="Reed"):
    return {
        "title": "Dev",
        "company": "Acme",
        "url": url,
        "location": "Bristol",
        "salary": "",
        "description": "",
        "source": source,
    }


def test_collect_jobs_deduplicates_by_url():
    from digest import collect_jobs

    def fake_streaming(queries, location, min_salary, distance=50, platforms=None):
        yield "Reed", [_make_job("http://example.com/1")], None
        yield "LinkedIn + Indeed", [_make_job("http://example.com/1", "LinkedIn + Indeed")], None
        yield "NHS Jobs", [_make_job("http://example.com/2", "NHS Jobs")], None

    with patch("digest.search_all_streaming", fake_streaming):
        result = collect_jobs(["query"], "Bristol", 60000)

    assert len(result) == 2
    assert {j["url"] for j in result} == {"http://example.com/1", "http://example.com/2"}


def test_collect_jobs_handles_platform_errors():
    from digest import collect_jobs

    def fake_streaming(queries, location, min_salary, distance=50, platforms=None):
        yield "Reed", [_make_job("http://example.com/1")], None
        yield "LinkedIn + Indeed", [], "Connection error"

    with patch("digest.search_all_streaming", fake_streaming):
        result = collect_jobs(["query"], "Bristol", 60000)

    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_digest.py::test_collect_jobs_deduplicates_by_url tests/test_digest.py::test_collect_jobs_handles_platform_errors -v`
Expected: FAIL with `ImportError` or `AttributeError`

- [ ] **Step 3: Implement collect_jobs() in digest.py**

Add after `load_config`:

```python
def collect_jobs(queries: list[str], location: str, min_salary: int) -> list[dict]:
    all_jobs: list[dict] = []
    for _platform, jobs, _error in search_all_streaming(queries, location, min_salary):
        all_jobs.extend(jobs)
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for job in all_jobs:
        if job["url"] and job["url"] not in seen_urls:
            seen_urls.add(job["url"])
            deduped.append(job)
    return deduped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_digest.py::test_collect_jobs_deduplicates_by_url tests/test_digest.py::test_collect_jobs_handles_platform_errors -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digest.py tests/test_digest.py
git commit -m "feat: add collect_jobs with deduplication"
```

---

## Task 4: analyse_results()

**Files:**
- Modify: `digest.py`
- Modify: `tests/test_digest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_digest.py`:

```python
from unittest.mock import MagicMock


def test_analyse_results_calls_claude_and_returns_text():
    from digest import analyse_results

    jobs = [
        {
            "title": "Data Engineer",
            "company": "NHS",
            "location": "Bristol",
            "salary": "£65,000",
            "source": "NHS Jobs",
        }
    ]
    config = {
        "search_queries": ["Data Engineer Bristol"],
        "location": "Bristol",
        "min_salary": 60000,
    }
    mock_client = MagicMock()
    mock_client.messages.create.return_value.content = [MagicMock(text="Great match today!")]

    with patch("digest.anthropic.Anthropic", return_value=mock_client), \
         patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        result = analyse_results(jobs, config)

    assert result == "Great match today!"
    mock_client.messages.create.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_digest.py::test_analyse_results_calls_claude_and_returns_text -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement analyse_results() in digest.py**

Add after `collect_jobs`:

```python
def analyse_results(jobs: list[dict], config: dict) -> str:
    jobs_text = "\n".join(
        f"- {j['title']} at {j['company']} ({j['location']}) {j['salary']} [{j['source']}]"
        for j in jobs
    )
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": (
                    f"You are helping Jie, a job seeker in {config['location']} looking for roles "
                    f"with UK Skilled Worker visa sponsorship.\n\n"
                    f"Search criteria:\n"
                    f"- Queries: {', '.join(config['search_queries'])}\n"
                    f"- Location: {config['location']}\n"
                    f"- Minimum salary: £{config['min_salary']:,}\n\n"
                    f"Today's matching jobs from licensed UK visa sponsors:\n{jobs_text}\n\n"
                    f"Write a 2–4 sentence summary of today's results, then highlight 2–3 standout "
                    f"roles with a brief reason why each is a strong match. Be specific and helpful."
                ),
            }
        ],
    )
    return message.content[0].text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_digest.py::test_analyse_results_calls_claude_and_returns_text -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digest.py tests/test_digest.py
git commit -m "feat: add analyse_results with Claude API call"
```

---

## Task 5: format_email_html()

**Files:**
- Modify: `digest.py`
- Modify: `tests/test_digest.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_digest.py`:

```python
def test_format_email_html_contains_summary_and_jobs():
    from digest import format_email_html

    jobs = [
        {
            "title": "Data Engineer",
            "company": "NHS Digital",
            "location": "Bristol",
            "salary": "£65,000",
            "source": "NHS Jobs",
            "url": "https://example.com/job/1",
            "sponsor_name": "NHS Digital",
        }
    ]
    html = format_email_html(jobs, "Strong match today.", "18 May 2026")

    assert "Strong match today." in html
    assert "Data Engineer" in html
    assert "NHS Digital" in html
    assert "https://example.com/job/1" in html
    assert "18 May 2026" in html


def test_format_email_html_no_results_omits_table():
    from digest import format_email_html

    html = format_email_html([], "No matches today.", "18 May 2026")

    assert "No matches today." in html
    assert "<table" not in html
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_digest.py::test_format_email_html_contains_summary_and_jobs tests/test_digest.py::test_format_email_html_no_results_omits_table -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement format_email_html() in digest.py**

Add after `analyse_results`:

```python
def format_email_html(jobs: list[dict], summary: str, today: str) -> str:
    if jobs:
        rows = "".join(
            f"<tr>"
            f"<td><a href='{j['url']}'>{j['title']}</a></td>"
            f"<td>{j.get('sponsor_name') or j.get('company', '')}</td>"
            f"<td>{j.get('location', '')}</td>"
            f"<td>{j.get('salary', '')}</td>"
            f"<td>{j.get('source', '')}</td>"
            f"</tr>"
            for j in jobs
        )
        table = (
            "<table border='1' cellpadding='6' cellspacing='0' "
            "style='border-collapse:collapse;width:100%'>"
            "<thead><tr style='background:#f0f0f0'>"
            "<th>Job Title</th><th>Company</th><th>Location</th><th>Salary</th><th>Source</th>"
            "</tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        table = ""

    return (
        f"<html><body>"
        f"<h2>Jie's Job Digest — {today}</h2>"
        f"<p>{summary}</p>"
        f"{table}"
        f"</body></html>"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_digest.py::test_format_email_html_contains_summary_and_jobs tests/test_digest.py::test_format_email_html_no_results_omits_table -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digest.py tests/test_digest.py
git commit -m "feat: add format_email_html"
```

---

## Task 6: send_email()

**Files:**
- Modify: `digest.py`
- Modify: `tests/test_digest.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_digest.py`:

```python
def test_send_email_logs_in_and_sends():
    from digest import send_email

    mock_server = MagicMock()

    with patch("digest.smtplib.SMTP_SSL") as mock_ssl:
        mock_ssl.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_ssl.return_value.__exit__ = MagicMock(return_value=False)
        send_email(
            subject="Test digest",
            html_body="<p>hello</p>",
            recipient="jie@example.com",
            gmail_user="sender@gmail.com",
            gmail_app_password="app-password",
        )

    mock_server.login.assert_called_once_with("sender@gmail.com", "app-password")
    mock_server.sendmail.assert_called_once()
    call_args = mock_server.sendmail.call_args
    assert call_args[0][0] == "sender@gmail.com"
    assert call_args[0][1] == "jie@example.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_digest.py::test_send_email_logs_in_and_sends -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement send_email() in digest.py**

Add after `format_email_html`:

```python
def send_email(
    subject: str,
    html_body: str,
    recipient: str,
    gmail_user: str,
    gmail_app_password: str,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html"))
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, recipient, msg.as_string())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_digest.py::test_send_email_logs_in_and_sends -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digest.py tests/test_digest.py
git commit -m "feat: add send_email via Gmail SMTP"
```

---

## Task 7: main()

**Files:**
- Modify: `digest.py`
- Modify: `tests/test_digest.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_digest.py`:

```python
def test_main_sends_email_when_jobs_found():
    from digest import main

    config = {
        "search_queries": ["Data Engineer Bristol"],
        "location": "Bristol",
        "min_salary": 60000,
        "recipient_email": "jie@example.com",
    }
    filtered_jobs = [
        {
            "title": "Data Engineer",
            "company": "NHS",
            "url": "http://example.com/1",
            "location": "Bristol",
            "salary": "£65,000",
            "description": "",
            "source": "NHS Jobs",
            "sponsor_name": "NHS Digital",
        }
    ]

    with patch("digest.load_config", return_value=config), \
         patch("digest.collect_jobs", return_value=filtered_jobs), \
         patch("digest.sponsor_filter.load_sponsor_names", return_value=["NHS Digital"]), \
         patch("digest.sponsor_filter.filter_jobs", return_value=filtered_jobs), \
         patch("digest.analyse_results", return_value="Great match!"), \
         patch("digest.format_email_html", return_value="<html>content</html>"), \
         patch("digest.send_email") as mock_send, \
         patch.dict("os.environ", {"GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
        main()

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args[1]
    assert call_kwargs["recipient"] == "jie@example.com"
    assert "1 match" in call_kwargs["subject"]


def test_main_sends_email_when_no_jobs_found():
    from digest import main

    config = {
        "search_queries": ["Data Engineer Bristol"],
        "location": "Bristol",
        "min_salary": 60000,
        "recipient_email": "jie@example.com",
    }

    with patch("digest.load_config", return_value=config), \
         patch("digest.collect_jobs", return_value=[]), \
         patch("digest.sponsor_filter.load_sponsor_names", return_value=[]), \
         patch("digest.sponsor_filter.filter_jobs", return_value=[]), \
         patch("digest.format_email_html", return_value="<html>no matches</html>"), \
         patch("digest.send_email") as mock_send, \
         patch.dict("os.environ", {"GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
        main()

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args[1]
    assert "0 matches" in call_kwargs["subject"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_digest.py::test_main_sends_email_when_jobs_found tests/test_digest.py::test_main_sends_email_when_no_jobs_found -v`
Expected: FAIL with `AttributeError`

- [ ] **Step 3: Implement main() in digest.py**

Add at the end of `digest.py`:

```python
def main() -> None:
    config = load_config()
    jobs = collect_jobs(config["search_queries"], config["location"], config["min_salary"])
    sponsor_names = sponsor_filter.load_sponsor_names()
    filtered = sponsor_filter.filter_jobs(jobs, sponsor_names)

    if filtered:
        summary = analyse_results(filtered, config)
    else:
        summary = "No matching roles were found today from licensed UK visa sponsors."

    today = date.today().strftime("%d %B %Y")
    count = len(filtered)
    subject = f"Job digest — {count} match{'es' if count != 1 else ''} — {today}"
    html_body = format_email_html(filtered, summary, today)
    send_email(
        subject=subject,
        html_body=html_body,
        recipient=config["recipient_email"],
        gmail_user=os.environ["GMAIL_USER"],
        gmail_app_password=os.environ["GMAIL_APP_PASSWORD"],
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
```

- [ ] **Step 4: Run all digest tests to verify they pass**

Run: `pytest tests/test_digest.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add digest.py tests/test_digest.py
git commit -m "feat: add main() orchestration and complete digest.py"
```

---

## Task 8: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/daily-digest.yml`

- [ ] **Step 1: Create the workflows directory**

Run: `mkdir -p .github/workflows`

- [ ] **Step 2: Create `.github/workflows/daily-digest.yml`**

```yaml
name: Daily job digest

on:
  schedule:
    - cron: "0 7 * * *"   # 7am UTC (8am BST / 7am GMT)
  workflow_dispatch:        # allow manual trigger for testing

jobs:
  digest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run digest
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          REED_API_KEY: ${{ secrets.REED_API_KEY }}
          SPONSOR_CSV_URL: ${{ secrets.SPONSOR_CSV_URL }}
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
        run: python digest.py
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/daily-digest.yml
git commit -m "feat: add GitHub Actions daily digest workflow"
```

---

## Task 9: Add GitHub Secrets

These must be set manually in GitHub: **Settings → Secrets and variables → Actions → New repository secret**

- [ ] Add `ANTHROPIC_API_KEY` — same value as your local `.env`
- [ ] Add `REED_API_KEY` — same value as your local `.env`
- [ ] Add `SPONSOR_CSV_URL` — same value as your local `.env`
- [ ] Add `GMAIL_USER` — the Gmail address you want to send from (e.g. `jie.job.digest@gmail.com`)
- [ ] Add `GMAIL_APP_PASSWORD` — generate at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) (requires 2FA enabled on the Gmail account)

- [ ] **Step: Trigger a manual test run**

In GitHub: go to **Actions → Daily job digest → Run workflow → Run workflow**

Check the run log to confirm the script completes without error and the email arrives.

---

## Post-implementation: Update digest_config.yaml

After confirming the workflow runs correctly, update `digest_config.yaml` with Jie's real search queries and recipient email, then commit.

```bash
git add digest_config.yaml
git commit -m "chore: update digest config with real search queries"
```
