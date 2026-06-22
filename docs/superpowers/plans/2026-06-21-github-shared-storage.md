# GitHub-as-Shared-Storage for Dismiss Jobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the dismiss jobs feature work when `digest.py` runs on GitHub Actions and the Streamlit app is hosted on Streamlit Cloud, by using the GitHub repository as shared storage for `today_jobs.json` and `dismissed_jobs.json`.

**Architecture:** `digest.py` writes `today_jobs.json` to disk during each Actions run; the workflow commits it back to the repo afterward, triggering a Streamlit redeploy with the fresh file. The Streamlit dismiss page reads `dismissed_jobs.json` from the local filesystem and writes it back via the GitHub Contents API (using a PAT in Streamlit secrets); `digest.py` reads it from the local checkout on the next run.

**Tech Stack:** Python 3.11, `requests` (already in requirements), GitHub Contents API (REST v3), GitHub Actions, Streamlit Cloud

## Global Constraints

- Python 3.11
- `requests>=2.31.0` — already in requirements; do NOT add PyGitHub or any other HTTP library
- GitHub API base URL: `https://api.github.com`
- Environment variables used: `GITHUB_TOKEN` (fine-grained PAT with `contents: write`), `GITHUB_REPO` (e.g. `meermouse/job-search`)
- `dismiss_store.py` must remain backward-compatible: when either `GITHUB_TOKEN` or `GITHUB_REPO` is absent, all functions fall through to the existing local file path unchanged
- All 12 existing tests in `tests/test_dismiss_store.py` must continue to pass without modification
- The workflow bot commit message must contain `[skip ci]` to prevent re-triggering the workflow
- No new Python packages

---

## Files

**Modified:**
- `dismiss_store.py` — add GitHub API helpers; make `load_dismissed_urls` / `save_dismissed_urls` environment-aware
- `.github/workflows/daily-digest.yml` — add `permissions: contents: write`, `SITE_URL` env var, commit-back step
- `.env.example` — document `GITHUB_TOKEN` and `GITHUB_REPO`
- `tests/test_dismiss_store.py` — 3 new tests for the GitHub API path

**Not changed:**
- `pages/Dismiss_Jobs.py` — calls `dismiss_store` transparently; no changes needed
- `digest.py` — unchanged; reads `dismissed_jobs.json` via local checkout on each run
- `.gitignore` — both files already removed in a previous commit; do not touch

---

### Task 1: GitHub API path in `dismiss_store.py`

**Files:**
- Modify: `dismiss_store.py`
- Test: `tests/test_dismiss_store.py`

**Interfaces:**
- Consumes: `os.environ.get("GITHUB_TOKEN")`, `os.environ.get("GITHUB_REPO")`
- Produces: unchanged public signatures — `load_dismissed_urls(path)` → `set[str]`, `save_dismissed_urls(urls, path)` → `None` — callers need no changes

- [ ] **Step 1: Write the failing tests**

Add these three tests at the bottom of `tests/test_dismiss_store.py`. The existing `import json` at the top of the file covers the `json` usage in these new tests; add `import base64` and `from unittest.mock import patch, MagicMock` alongside it.

```python
import base64
from unittest.mock import patch, MagicMock


def test_load_dismissed_urls_uses_github_api_when_env_set():
    from dismiss_store import load_dismissed_urls
    payload = {"dismissed_urls": ["https://a.com/1"]}
    # GitHub API returns base64-encoded content (sometimes with embedded newlines)
    encoded = base64.b64encode(json.dumps(payload).encode()).decode() + "\n"
    get_mock = MagicMock()
    get_mock.status_code = 200
    get_mock.json.return_value = {"content": encoded, "sha": "abc123"}
    with patch.dict("os.environ", {"GITHUB_TOKEN": "tok", "GITHUB_REPO": "user/repo"}):
        with patch("requests.get", return_value=get_mock):
            result = load_dismissed_urls("dismissed_jobs.json")
    assert result == {"https://a.com/1"}


def test_load_dismissed_urls_returns_empty_when_github_404():
    from dismiss_store import load_dismissed_urls
    get_mock = MagicMock()
    get_mock.status_code = 404
    with patch.dict("os.environ", {"GITHUB_TOKEN": "tok", "GITHUB_REPO": "user/repo"}):
        with patch("requests.get", return_value=get_mock):
            result = load_dismissed_urls("dismissed_jobs.json")
    assert result == set()


def test_save_dismissed_urls_uses_github_api_when_env_set():
    from dismiss_store import save_dismissed_urls
    # GET returns 404 — file doesn't exist yet, so no sha in the PUT body
    get_mock = MagicMock()
    get_mock.status_code = 404
    put_mock = MagicMock()
    put_mock.raise_for_status.return_value = None
    with patch.dict("os.environ", {"GITHUB_TOKEN": "tok", "GITHUB_REPO": "user/repo"}):
        with patch("requests.get", return_value=get_mock):
            with patch("requests.put", return_value=put_mock) as mock_put:
                save_dismissed_urls({"https://example.com/1"})
    mock_put.assert_called_once()
    sent = mock_put.call_args.kwargs["json"]
    decoded = json.loads(base64.b64decode(sent["content"]).decode())
    assert decoded == {"dismissed_urls": ["https://example.com/1"]}
    assert "[skip ci]" in sent["message"]
    assert sent.get("sha") is None
```

- [ ] **Step 2: Run new tests to confirm they fail**

```
pytest tests/test_dismiss_store.py::test_load_dismissed_urls_uses_github_api_when_env_set tests/test_dismiss_store.py::test_load_dismissed_urls_returns_empty_when_github_404 tests/test_dismiss_store.py::test_save_dismissed_urls_uses_github_api_when_env_set -v
```

Expected: 3 FAILED (the functions don't call `requests.get`/`requests.put` yet)

- [ ] **Step 3: Implement the GitHub API helpers and environment-aware functions**

Replace the entire contents of `dismiss_store.py` with:

```python
import base64
import json
import os
import tempfile

import requests


def _github_headers() -> dict:
    return {
        "Authorization": f"token {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github.v3+json",
    }


def _github_get_file(repo: str, path: str) -> tuple[str | None, str | None]:
    """Return (decoded_content, sha) or (None, None) if the file doesn't exist."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    r = requests.get(url, headers=_github_headers(), timeout=10)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"]).decode()
    return content, data["sha"]


def _github_put_file(
    repo: str, path: str, content: str, sha: str | None, message: str
) -> None:
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    payload: dict = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(url, json=payload, headers=_github_headers(), timeout=10)
    r.raise_for_status()


def load_dismissed_urls(path: str = "dismissed_jobs.json") -> set[str]:
    github_token = os.environ.get("GITHUB_TOKEN")
    github_repo = os.environ.get("GITHUB_REPO")

    if github_token and github_repo:
        try:
            content, _ = _github_get_file(github_repo, path)
            if content is None:
                return set()
            data = json.loads(content)
            return set(data.get("dismissed_urls", []))
        except Exception:
            return set()

    if not os.path.exists(path):
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
        return set(data.get("dismissed_urls", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_dismissed_urls(urls: set[str], path: str = "dismissed_jobs.json") -> None:
    github_token = os.environ.get("GITHUB_TOKEN")
    github_repo = os.environ.get("GITHUB_REPO")

    if github_token and github_repo:
        content = json.dumps({"dismissed_urls": sorted(urls)}, indent=2)
        _, sha = _github_get_file(github_repo, path)
        _github_put_file(
            github_repo, path, content, sha,
            "chore: update dismissed jobs [skip ci]",
        )
        return

    dir_ = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp") as f:
        json.dump({"dismissed_urls": sorted(urls)}, f, indent=2)
        tmp = f.name
    os.replace(tmp, path)


def load_today_jobs(path: str = "today_jobs.json") -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_today_jobs(
    strong: list[dict],
    worth_a_look: list[dict],
    near_misses: list[dict],
    today: str,
    path: str = "today_jobs.json",
) -> None:
    dir_ = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp") as f:
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
        tmp = f.name
    os.replace(tmp, path)
```

- [ ] **Step 4: Run all dismiss_store tests**

```
pytest tests/test_dismiss_store.py -v
```

Expected: 15 passed (12 existing + 3 new)

- [ ] **Step 5: Run full suite to check for regressions**

```
pytest tests/ -v
```

Expected: 178 passed, 1 skipped

- [ ] **Step 6: Commit**

```bash
git add dismiss_store.py tests/test_dismiss_store.py
git commit -m "feat: add GitHub API storage path to dismiss_store for Streamlit Cloud"
```

---

### Task 2: Workflow commit-back + config

**Files:**
- Modify: `.github/workflows/daily-digest.yml`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `today_jobs.json` written to the runner's working directory by `digest.py`
- Produces: `today_jobs.json` committed to the repo; Streamlit Cloud reads it on next redeploy triggered by the push

- [ ] **Step 1: Update `.github/workflows/daily-digest.yml`**

Replace the entire file with:

```yaml
name: Daily job digest

on:
  schedule:
    - cron: "0 7 * * *"   # 7:00 UTC — 8:00 BST (summer) / 7:00 GMT (winter)
    # To run twice a week instead, replace the line above with:
    # - cron: "0 7 * * 1,4"   # Monday and Thursday only
  workflow_dispatch:        # allow manual trigger for testing

jobs:
  digest:
    runs-on: ubuntu-latest
    permissions:
      contents: write
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
          RECIPIENT_EMAIL: ${{ secrets.RECIPIENT_EMAIL }}
          SITE_URL: ${{ secrets.SITE_URL }}
        run: python digest.py

      - name: Commit today's jobs
        run: |
          if [ -f today_jobs.json ]; then
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add today_jobs.json
            git diff --staged --quiet || git commit -m "chore: update today_jobs.json [skip ci]"
            git push
          fi
```

- [ ] **Step 2: Update `.env.example`**

Replace the file with:

```
ANTHROPIC_API_KEY=your_key_here
REED_API_KEY=your_key_here
SPONSOR_CSV_URL=https://www.gov.uk/csv-preview/69f47183ab602a88957eefa6/2026-05-01_-_Worker_and_Temporary_Worker.csv
SITE_URL=https://your-app-name.streamlit.app

# Required in Streamlit Cloud secrets for the dismiss page to write
# dismissed_jobs.json back to the repo. Create a fine-grained PAT with
# "Contents: Read and write" scoped to this repository only.
# Not needed for local development.
GITHUB_TOKEN=your_github_pat_here
GITHUB_REPO=meermouse/job-search
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/daily-digest.yml .env.example
git commit -m "feat: commit today_jobs.json back to repo after each digest run"
```

---

## After implementation: manual production setup

These steps require action in external dashboards — they cannot be automated:

1. **GitHub** — create a fine-grained Personal Access Token:
   - Go to GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
   - Repository access: this repo only
   - Permissions: Contents → Read and write
   - Copy the token value

2. **GitHub Actions secrets** — add `SITE_URL`:
   - Go to the repo → Settings → Secrets and variables → Actions
   - Add secret: `SITE_URL` = `https://your-app.streamlit.app`

3. **Streamlit Cloud secrets** — add all three values:
   - Go to your app → Settings → Secrets
   - Add:
     ```toml
     GITHUB_TOKEN = "your_pat_from_step_1"
     GITHUB_REPO = "meermouse/job-search"
     SITE_URL = "https://your-app.streamlit.app"
     ```

4. **Trigger a test run** — go to GitHub Actions → "Daily job digest" → Run workflow
   - This commits `today_jobs.json` to the repo, triggering a Streamlit redeploy
   - After the redeploy, open the Streamlit app and check the Dismiss Jobs page in the sidebar
