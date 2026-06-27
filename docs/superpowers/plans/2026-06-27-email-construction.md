# Email Construction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an HTML email construction and SMTP delivery step to the end of the job search pipeline, sending the top 20 scored jobs to the user.

**Architecture:** A new `email.py` module provides `build_email_html()` (renders inline-CSS HTML from scored results) and `send_email()` (delivers via SMTP using env-var credentials). `Profile` gains two defaulted fields (`preamble`, `recipient_email`). `main()` calls both functions after scoring.

**Tech Stack:** Python stdlib only — `smtplib`, `email.message.EmailMessage`, `datetime`. No new dependencies.

## Global Constraints

- Python 3.11+
- All styles must be inline CSS — no `<style>` blocks (Gmail/Outlook strip `<head>` styles)
- No new entries in `pyproject.toml` dependencies
- New Profile fields must use default values (`= ""`) so existing test helpers compile without modification
- All tests run with: `pytest tests/ -v`
- Working directory for all commands: `c:\Code\job-search-email`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/job_search_email/models.py` | Add `preamble: str = ""` and `recipient_email: str = ""` to `Profile` |
| Modify | `src/job_search_email/main.py` | Read new Profile fields in `load_profile()`; call email functions at end of `main()` |
| Modify | `profile.yaml` | Add `recipient_email: marc.j.brookes@gmail.com` |
| Modify | `tests/test_main.py` | Fix `test_load_profile` assertion for `preamble`; add `recipient_email` assertion |
| Create | `src/job_search_email/email.py` | `build_email_html()` and `send_email()` |
| Create | `tests/test_email.py` | Tests for both email functions |
| Modify | `.github/workflows/daily_job.yml` | Add SMTP env vars from GitHub secrets |

---

## Task 1: Extend Profile with preamble and recipient_email

**Files:**
- Modify: `src/job_search_email/models.py`
- Modify: `src/job_search_email/main.py` (only `load_profile`)
- Modify: `profile.yaml`
- Modify: `tests/test_main.py` (fix one assertion, add one)

**Interfaces:**
- Produces: `Profile.preamble: str` and `Profile.recipient_email: str` — both default to `""` so all existing `Profile(...)` call-sites compile unchanged

- [ ] **Step 1: Write the failing test**

Add to `tests/test_main.py`. The existing `test_load_profile` has `assert not hasattr(profile, "preamble")` on line 83 — replace that line and add a `recipient_email` assertion:

```python
# In test_main.py — replace line 83:
assert profile.preamble == "Test preamble"
assert profile.recipient_email == ""   # not in PROFILE_YAML, should default
```

The `PROFILE_YAML` constant at the top of `test_main.py` already contains `preamble: "Test preamble"` so no change needed there.

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_main.py::test_load_profile -v
```

Expected: FAIL — `AttributeError: 'Profile' object has no attribute 'preamble'`

- [ ] **Step 3: Add fields to Profile dataclass**

In `src/job_search_email/models.py`, append two defaulted fields at the end of `Profile` (defaulted fields must follow non-defaulted fields):

```python
@dataclass
class Profile:
    name: str
    current_role: str
    about: str
    seniority: str
    industry: str
    skills: list[str]
    previous_roles: list[str]
    target_roles: list[str]
    open_to: list[str]
    not_open_to: list[str]
    qualifications: list[str]
    employment_type: list[str]
    location: str
    min_salary: int
    preamble: str = ""
    recipient_email: str = ""
```

- [ ] **Step 4: Update load_profile() to read new fields**

In `src/job_search_email/main.py`, inside `load_profile()`, add two lines to the `Profile(...)` constructor call. The new fields read from `data` (root level of YAML), matching the pattern already used for `location` and `min_salary`:

```python
def load_profile(path: Path = PROFILE_PATH) -> Profile:
    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)

    p = data["profile"]
    return Profile(
        name=p["name"],
        current_role=p.get("current_role", ""),
        about=p.get("about", ""),
        seniority=p.get("seniority", ""),
        industry=p.get("industry", ""),
        skills=p.get("skills", []),
        previous_roles=p.get("previous_roles", []),
        target_roles=p.get("target_roles", []),
        open_to=p.get("open_to", []),
        not_open_to=p.get("not_open_to", []),
        qualifications=p.get("qualifications", []),
        employment_type=p.get("employment_type", []),
        location=data.get("location", ""),
        min_salary=data.get("min_salary", 0),
        preamble=data.get("preamble", ""),
        recipient_email=data.get("recipient_email", ""),
    )
```

- [ ] **Step 5: Add recipient_email to profile.yaml**

In `profile.yaml`, add `recipient_email` at the root level alongside `preamble`:

```yaml
location: Bristol
min_salary: 60000

preamble: "Hey Jie, its The Job Mule. Lets go through todays jobs."
recipient_email: marc.j.brookes@gmail.com
```

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/test_main.py -v
pytest tests/test_scorer.py -v
```

Expected: all pass. The `make_profile()` helpers in both files omit `preamble`/`recipient_email` and will receive `""` defaults — no changes needed in those helpers.

- [ ] **Step 7: Commit**

```
git add src/job_search_email/models.py src/job_search_email/main.py profile.yaml tests/test_main.py
git commit -m "feat: add preamble and recipient_email fields to Profile"
```

---

## Task 2: Build HTML email body

**Files:**
- Create: `src/job_search_email/email.py`
- Create: `tests/test_email.py`

**Interfaces:**
- Consumes: `ScoredResult` (from `models.py`), `Profile.preamble: str` (from Task 1)
- Produces: `build_email_html(results: list[ScoredResult], profile: Profile) -> str`

- [ ] **Step 1: Create test file with failing tests**

Create `tests/test_email.py`:

```python
import pytest
from job_search_email.email import build_email_html
from job_search_email.models import JobAnalysis, JobListing, Profile, ScoredResult


def _make_profile(**kwargs) -> Profile:
    defaults = dict(
        name="Jie", current_role="Manager", about="", seniority="Senior",
        industry="NHS", skills=[], previous_roles=[], target_roles=[],
        open_to=[], not_open_to=[], qualifications=[], employment_type=[],
        location="Bristol", min_salary=60000,
        preamble="Hey Jie!", recipient_email="jie@example.com",
    )
    defaults.update(kwargs)
    return Profile(**defaults)


def _make_result(
    score: int,
    title: str = "Job Title",
    url: str = "https://example.com/job/1",
    salary: int | None = 70000,
    rejected: bool = False,
) -> ScoredResult:
    job = JobListing(
        title=title, company="Acme Corp", location="Bristol",
        salary_min=salary, description="",
        url=url, source="reed", employment_type="full-time",
    )
    analysis = JobAnalysis(
        score=score, matched_skills=[], missing_essentials=[],
        employment_type_note="Permanent", verdict=f"Good match for {title}",
    )
    return ScoredResult(
        job=job, flags=[], rejected=rejected,
        reject_reason="employment type: contract" if rejected else None,
        analysis=None if rejected else analysis,
    )


def test_build_email_html_includes_preamble():
    profile = _make_profile(preamble="Hey Jie, welcome!")
    html = build_email_html([], profile)
    assert "Hey Jie, welcome!" in html


def test_build_email_html_limits_to_20_jobs():
    profile = _make_profile()
    results = [_make_result(score=5, title=f"Position{i:02d}") for i in range(25)]
    html = build_email_html(results, profile)
    assert "Position00" in html
    assert "Position19" in html
    assert "Position20" not in html
    assert "Position24" not in html


def test_build_email_html_sorted_by_score_desc():
    profile = _make_profile()
    results = [
        _make_result(score=3, title="LowScore"),
        _make_result(score=9, title="HighScore"),
    ]
    html = build_email_html(results, profile)
    assert html.index("HighScore") < html.index("LowScore")


def test_build_email_html_excludes_rejected():
    profile = _make_profile()
    results = [
        _make_result(score=8, title="GoodJob"),
        _make_result(score=7, title="RejectedJob", rejected=True),
    ]
    html = build_email_html(results, profile)
    assert "GoodJob" in html
    assert "RejectedJob" not in html


def test_build_email_html_excludes_no_analysis():
    profile = _make_profile()
    no_analysis = ScoredResult(
        job=JobListing(
            title="NoAnalysisJob", company="Corp", location="Bristol",
            salary_min=70000, description="", url="https://example.com/2",
            source="reed", employment_type="full-time",
        ),
        flags=[], rejected=False, reject_reason=None, analysis=None,
    )
    results = [_make_result(score=8, title="AnalysedJob"), no_analysis]
    html = build_email_html(results, profile)
    assert "AnalysedJob" in html
    assert "NoAnalysisJob" not in html


def test_build_email_html_links_job_url():
    profile = _make_profile()
    results = [_make_result(score=8, url="https://jobs.example.com/abc123")]
    html = build_email_html(results, profile)
    assert 'href="https://jobs.example.com/abc123"' in html


def test_build_email_html_salary_not_stated_when_none():
    profile = _make_profile()
    results = [_make_result(score=8, salary=None)]
    html = build_email_html(results, profile)
    assert "Not stated" in html


def test_build_email_html_formats_salary_with_commas():
    profile = _make_profile()
    results = [_make_result(score=8, salary=75000)]
    html = build_email_html(results, profile)
    assert "£75,000" in html


def test_build_email_html_green_badge_for_high_score():
    profile = _make_profile()
    results = [_make_result(score=9)]
    html = build_email_html(results, profile)
    assert "#28a745" in html


def test_build_email_html_amber_badge_for_mid_score():
    profile = _make_profile()
    results = [_make_result(score=6)]
    html = build_email_html(results, profile)
    assert "#ffc107" in html


def test_build_email_html_red_badge_for_low_score():
    profile = _make_profile()
    results = [_make_result(score=3)]
    html = build_email_html(results, profile)
    assert "#dc3545" in html


def test_build_email_html_includes_verdict():
    profile = _make_profile()
    results = [_make_result(score=8, title="MyJob")]
    html = build_email_html(results, profile)
    assert "Good match for MyJob" in html


def test_build_email_html_zero_results_shows_count():
    profile = _make_profile()
    html = build_email_html([], profile)
    assert "0 jobs" in html
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_email.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'job_search_email.email'`

- [ ] **Step 3: Create email.py with build_email_html**

Create `src/job_search_email/email.py`:

```python
import os
import smtplib
import sys
from datetime import date
from email.message import EmailMessage

from .models import Profile, ScoredResult


def _score_badge(score: int) -> str:
    if score >= 8:
        bg, fg = "#28a745", "#ffffff"
    elif score >= 5:
        bg, fg = "#ffc107", "#333333"
    else:
        bg, fg = "#dc3545", "#ffffff"
    return (
        f'<span style="background:{bg}; color:{fg}; padding:2px 8px; '
        f'border-radius:4px; font-weight:bold; font-size:12px;">{score}/10</span>'
    )


def build_email_html(results: list[ScoredResult], profile: Profile) -> str:
    eligible = [r for r in results if not r.rejected and r.analysis is not None]
    eligible.sort(key=lambda r: r.analysis.score, reverse=True)
    top = eligible[:20]

    rows = []
    for i, r in enumerate(top, 1):
        row_bg = "#f9f9f9" if i % 2 == 0 else "#ffffff"
        salary = f"£{r.job.salary_min:,}" if r.job.salary_min else "Not stated"
        badge = _score_badge(r.analysis.score)
        cell = 'style="padding:8px 6px; border-bottom:1px solid #eeeeee;"'
        rows.append(
            f'<tr style="background:{row_bg};">'
            f"<td {cell}>{i}</td>"
            f"<td {cell}>{badge}</td>"
            f'<td {cell}><a href="{r.job.url}" style="color:#0066cc; text-decoration:none;">{r.job.title}</a></td>'
            f"<td {cell}>{r.job.company}</td>"
            f'<td {cell} style="white-space:nowrap;">{salary}</td>'
            f"<td {cell}>{r.analysis.verdict}</td>"
            f"</tr>"
        )

    n = len(top)
    today = date.today().strftime("%Y-%m-%d")
    th = 'style="padding:8px 6px; text-align:left; border-bottom:2px solid #dddddd; background:#f0f0f0;"'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif; background:#ffffff; color:#333333; max-width:920px; margin:0 auto; padding:20px;">
  <p style="font-size:16px; margin-bottom:20px;">{profile.preamble}</p>
  <p style="font-size:14px; color:#666666; margin-bottom:16px;">Here are your top {n} jobs from today's search, ranked by suitability.</p>
  <table style="width:100%; border-collapse:collapse; font-size:13px;">
    <thead>
      <tr>
        <th {th}>#</th>
        <th {th}>Score</th>
        <th {th}>Job Title</th>
        <th {th}>Company</th>
        <th {th}>Salary</th>
        <th {th}>Verdict</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows)}
    </tbody>
  </table>
  <p style="font-size:12px; color:#999999; margin-top:24px;">Generated on {today}</p>
</body>
</html>"""


def send_email(html: str, profile: Profile, n: int = 0) -> None:
    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")

    if not all([host, port, user, password]):
        print("[email] SMTP credentials not configured — skipping email send", file=sys.stderr)
        return

    today = date.today().strftime("%Y-%m-%d")
    msg = EmailMessage()
    msg["Subject"] = f"Job Search Results – {today} ({n} jobs found)"
    msg["From"] = user
    msg["To"] = profile.recipient_email
    msg.set_content("Please view this email in an HTML-capable client.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP(host, int(port)) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)

    print(f"[email] sent to {profile.recipient_email}")
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_email.py -v
```

Expected: all 13 tests PASS

- [ ] **Step 5: Run full test suite to check for regressions**

```
pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```
git add src/job_search_email/email.py tests/test_email.py
git commit -m "feat: add email module with build_email_html and send_email"
```

---

## Task 3: Wire send_email into pipeline and update GitHub Actions

**Files:**
- Modify: `src/job_search_email/main.py` (add import + two lines at end of `main()`)
- Modify: `tests/test_email.py` (add `send_email` skip test)
- Modify: `.github/workflows/daily_job.yml` (add env block to run step)

**Interfaces:**
- Consumes: `build_email_html(results, profile) -> str` and `send_email(html, profile, n) -> None` from Task 2
- Consumes: `Profile.recipient_email: str` from Task 1

- [ ] **Step 1: Write the failing send_email skip test**

First, update the import at the top of `tests/test_email.py` to include `send_email`:

```python
from job_search_email.email import build_email_html, send_email
```

Then add the test function to `tests/test_email.py`:

```python
def test_send_email_skips_and_warns_when_no_credentials(monkeypatch, capsys):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    profile = _make_profile()
    send_email("<html></html>", profile, n=5)  # must not raise
    captured = capsys.readouterr()
    assert "skipping" in captured.err
```

- [ ] **Step 2: Run test to verify it passes (send_email is already implemented)**

```
pytest tests/test_email.py::test_send_email_skips_and_warns_when_no_credentials -v
```

Expected: PASS (the function was written in Task 2)

- [ ] **Step 3: Wire email into main()**

In `src/job_search_email/main.py`, add the import at the top (with the other local imports):

```python
from .email import build_email_html, send_email
```

Then at the end of `main()`, after the scoring print statements, add:

```python
    top_n = len([r for r in scored if not r.rejected and r.analysis is not None and "analysis_failed" not in r.flags])
    top_n = min(top_n, 20)
    print("Sending email...")
    html = build_email_html(scored, profile)
    send_email(html, profile, n=top_n)
```

The complete tail of `main()` after this change:

```python
    print("Scoring jobs...")
    scored = score_jobs(filtered, profile)
    write_scored_results(scored)
    kept_scored = [r for r in scored if not r.rejected]
    top_score = max((r.analysis.score for r in kept_scored if r.analysis), default="n/a")
    print(f"- scored: {len(kept_scored)} kept, top score: {top_score}")
    print(f"- scored results written to: {SCORED_RESULTS_PATH}")

    top_n = len([r for r in scored if not r.rejected and r.analysis is not None and "analysis_failed" not in r.flags])
    top_n = min(top_n, 20)
    print("Sending email...")
    html = build_email_html(scored, profile)
    send_email(html, profile, n=top_n)
```

- [ ] **Step 4: Update GitHub Actions workflow**

In `.github/workflows/daily_job.yml`, add an `env:` block to the "Run job search email plan" step:

```yaml
      - name: Run job search email plan
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          SMTP_HOST: ${{ secrets.SMTP_HOST }}
          SMTP_PORT: ${{ secrets.SMTP_PORT }}
          SMTP_USER: ${{ secrets.SMTP_USER }}
          SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}
        run: job-search-email
```

- [ ] **Step 5: Run full test suite**

```
pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```
git add src/job_search_email/main.py tests/test_email.py .github/workflows/daily_job.yml
git commit -m "feat: wire email delivery into pipeline and add SMTP secrets to workflow"
```

---

## GitHub Secrets to Configure

Before the GitHub Action can send email, add these four secrets in the repository settings (Settings → Secrets and variables → Actions):

| Secret | Value |
|--------|-------|
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Gmail address used as sender |
| `SMTP_PASSWORD` | Gmail app password (not account password — generate at myaccount.google.com/apppasswords) |
| `ANTHROPIC_API_KEY` | Anthropic API key (needed for existing scorer step) |
