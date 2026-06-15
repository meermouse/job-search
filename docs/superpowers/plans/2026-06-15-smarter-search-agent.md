# Smarter Search Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace static search queries in the daily digest with an autonomous Claude tool-use agent that reasons from a structured candidate profile and iterates searches until satisfied with result quality.

**Architecture:** A new `search_agent.py` module defines a `search_jobs` Claude tool and drives an agentic loop: Claude calls the tool with queries, sees real results, then decides whether to refine and search again or stop and emit a strategy note. `digest.py` branches on whether a `profile` block is present in the config — if yes, delegate to the agent; if not, existing static-query path runs unchanged.

**Tech Stack:** Python, Anthropic Python SDK (tool use / `messages.create` with `tools=`), PyYAML, pytest + unittest.mock

---

### Task 1: Create `search_agent.py` — helpers (`SEARCH_TOOL`, `_build_system_prompt`, `_execute_search`)

**Files:**
- Create: `search_agent.py`
- Create: `tests/test_search_agent.py`

- [ ] **Step 1: Write failing tests for `_execute_search`**

Create `tests/test_search_agent.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
import search_agent


def _make_job(url, title="Operations Director", company="NHS Trust"):
    return {
        "url": url,
        "title": title,
        "company": company,
        "location": "Bristol",
        "salary": "£70,000",
        "source": "Reed",
        "description": "",
    }


def test_execute_search_returns_sponsored_jobs_and_text():
    job = _make_job("https://example.com/1")
    with patch("search_agent.search_all_streaming", return_value=[("Reed", [job], None)]):
        with patch("search_agent.sponsor_filter.filter_jobs", return_value=[job]):
            seen: set[str] = set()
            jobs, text = search_agent._execute_search(
                {"queries": ["Operations Director"]},
                default_location="Bristol",
                min_salary=60000,
                sponsor_names=["NHS Trust"],
                seen_urls=seen,
            )
    assert len(jobs) == 1
    assert jobs[0]["url"] == "https://example.com/1"
    assert "Operations Director" in text
    assert "https://example.com/1" in seen


def test_execute_search_deduplicates_seen_urls():
    job = _make_job("https://example.com/1")
    seen = {"https://example.com/1"}
    with patch("search_agent.search_all_streaming", return_value=[("Reed", [job], None)]):
        with patch("search_agent.sponsor_filter.filter_jobs", return_value=[job]):
            jobs, text = search_agent._execute_search(
                {"queries": ["Operations Director"]},
                default_location="Bristol",
                min_salary=60000,
                sponsor_names=["NHS Trust"],
                seen_urls=seen,
            )
    assert jobs == []
    assert text == "No sponsored jobs found for these queries."


def test_execute_search_defaults_location_and_distance():
    with patch("search_agent.search_all_streaming", return_value=[]) as mock_search:
        with patch("search_agent.sponsor_filter.filter_jobs", return_value=[]):
            search_agent._execute_search(
                {"queries": ["Director"]},
                default_location="Bristol",
                min_salary=60000,
                sponsor_names=[],
                seen_urls=set(),
            )
    mock_search.assert_called_once_with(["Director"], "Bristol", 60000, 50)


def test_execute_search_uses_location_and_distance_from_tool_input():
    with patch("search_agent.search_all_streaming", return_value=[]) as mock_search:
        with patch("search_agent.sponsor_filter.filter_jobs", return_value=[]):
            search_agent._execute_search(
                {"queries": ["Director"], "location": "London", "distance": 25},
                default_location="Bristol",
                min_salary=60000,
                sponsor_names=[],
                seen_urls=set(),
            )
    mock_search.assert_called_once_with(["Director"], "London", 60000, 25)


def test_execute_search_no_results_returns_empty_and_message():
    with patch("search_agent.search_all_streaming", return_value=[("Reed", [], None)]):
        with patch("search_agent.sponsor_filter.filter_jobs", return_value=[]):
            jobs, text = search_agent._execute_search(
                {"queries": ["Unknown Role XYZ"]},
                default_location="Bristol",
                min_salary=60000,
                sponsor_names=[],
                seen_urls=set(),
            )
    assert jobs == []
    assert text == "No sponsored jobs found for these queries."
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_search_agent.py -v
```

Expected: `ModuleNotFoundError: No module named 'search_agent'`

- [ ] **Step 3: Create `search_agent.py` with `SEARCH_TOOL`, `_build_system_prompt`, and `_execute_search`**

```python
import logging
import os

import anthropic

import sponsor_filter
from searchers import search_all_streaming

logger = logging.getLogger(__name__)

MAX_ROUNDS = 5

SEARCH_TOOL = {
    "name": "search_jobs",
    "description": (
        "Search for job listings across LinkedIn, Indeed, Reed, and NHS Jobs. "
        "Only returns jobs from employers licensed to sponsor UK Skilled Worker visas. "
        "Call multiple times with different queries or locations to explore different angles."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Search queries to run. Each is a job title or keyword combination.",
            },
            "location": {
                "type": "string",
                "description": "Location to search. Defaults to the candidate's preferred location if omitted.",
            },
            "distance": {
                "type": "integer",
                "description": "Search radius in miles. Default 50.",
            },
        },
        "required": ["queries"],
    },
}


def _build_system_prompt(profile: dict, location: str, min_salary: int) -> str:
    return (
        f"You are an autonomous job search agent for {profile.get('name', 'the candidate')}. "
        "Your goal is to find the best-matching jobs from employers licensed to sponsor UK Skilled Worker visas.\n\n"
        "Candidate profile:\n"
        f"- Current role: {profile.get('current_role', '')}\n"
        f"- Seniority: {profile.get('seniority', '')}\n"
        f"- Industry: {profile.get('industry', '')}\n"
        f"- Key skills: {', '.join(profile.get('skills', []))}\n"
        f"- Previous roles: {', '.join(profile.get('previous_roles', []))}\n"
        f"- Target roles: {', '.join(profile.get('target_roles', []))}\n"
        f"- Open to: {', '.join(profile.get('open_to', []))}\n"
        f"- Preferred location: {location}\n"
        f"- Minimum salary: £{min_salary:,}\n\n"
        "Use the search_jobs tool to find matching roles. You may call it multiple times to explore "
        "different angles — exact job titles, adjacent roles, transferable skills, different locations.\n\n"
        "After each round, assess whether the results are a good match for the candidate's seniority, "
        "salary expectations, and background. If not, refine your queries and search again.\n\n"
        "When you are satisfied with the results, stop calling the tool and write a 2–3 sentence "
        "strategy note summarising what angles you explored and what you found. Be specific.\n\n"
        f"You have a maximum of {MAX_ROUNDS} search rounds."
    )


def _execute_search(
    tool_input: dict,
    default_location: str,
    min_salary: int,
    sponsor_names: list[str],
    seen_urls: set[str],
) -> tuple[list[dict], str]:
    """Run one search round. Returns (new_sponsored_jobs, result_text_for_claude)."""
    queries = tool_input["queries"]
    location = tool_input.get("location", default_location)
    distance = tool_input.get("distance", 50)

    all_jobs: list[dict] = []
    for _platform, jobs, _error in search_all_streaming(queries, location, min_salary, distance):
        all_jobs.extend(jobs)

    sponsored = sponsor_filter.filter_jobs(all_jobs, sponsor_names)

    new_jobs = []
    for job in sponsored:
        if job["url"] and job["url"] not in seen_urls:
            seen_urls.add(job["url"])
            new_jobs.append(job)

    if not new_jobs:
        return [], "No sponsored jobs found for these queries."

    lines = [f"Found {len(new_jobs)} sponsored jobs:"]
    for i, j in enumerate(new_jobs, 1):
        lines.append(
            f"{i}. {j['title']} at {j.get('company', 'Unknown')} "
            f"({j.get('location', '')}) — {j.get('salary', 'Not stated')} [{j.get('source', '')}]"
        )
    return new_jobs, "\n".join(lines)
```

- [ ] **Step 4: Run tests — all should pass**

```
pytest tests/test_search_agent.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add search_agent.py tests/test_search_agent.py
git commit -m "feat: add search_agent helpers — SEARCH_TOOL, _build_system_prompt, _execute_search"
```

---

### Task 2: Add `run_search_agent` to `search_agent.py`

**Files:**
- Modify: `search_agent.py`
- Modify: `tests/test_search_agent.py`

- [ ] **Step 1: Write failing tests for `run_search_agent`**

Append to `tests/test_search_agent.py`:

```python
def test_run_search_agent_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        search_agent.run_search_agent({}, "Bristol", 60000)


def test_run_search_agent_returns_empty_jobs_and_note_when_claude_stops_immediately():
    mock_text = MagicMock()
    mock_text.type = "text"
    mock_text.text = "No tool calls needed — returning strategy note."

    mock_response = MagicMock()
    mock_response.content = [mock_text]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    profile = {"name": "Jie", "skills": [], "previous_roles": [], "target_roles": [], "open_to": []}

    with patch("search_agent.anthropic.Anthropic", return_value=mock_client):
        with patch("search_agent.sponsor_filter.load_sponsor_names", return_value=[]):
            jobs, note = search_agent.run_search_agent(profile, "Bristol", 60000)

    assert jobs == []
    assert note == "No tool calls needed — returning strategy note."
    mock_client.messages.create.assert_called_once()


def test_run_search_agent_executes_tool_call_and_feeds_result_back():
    mock_tool_use = MagicMock()
    mock_tool_use.type = "tool_use"
    mock_tool_use.id = "tool_abc123"
    mock_tool_use.input = {"queries": ["Operations Director"], "location": "Bristol", "distance": 50}

    mock_text = MagicMock()
    mock_text.type = "text"
    mock_text.text = "Searched ops director roles. Found strong matches."

    mock_response_1 = MagicMock()
    mock_response_1.content = [mock_tool_use]

    mock_response_2 = MagicMock()
    mock_response_2.content = [mock_text]

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [mock_response_1, mock_response_2]

    mock_job = _make_job("https://example.com/job1")
    profile = {"name": "Jie", "skills": [], "previous_roles": [], "target_roles": [], "open_to": []}

    with patch("search_agent.anthropic.Anthropic", return_value=mock_client):
        with patch("search_agent.sponsor_filter.load_sponsor_names", return_value=["NHS Trust"]):
            with patch("search_agent._execute_search", return_value=([mock_job], "Found 1 job")):
                jobs, note = search_agent.run_search_agent(profile, "Bristol", 60000)

    assert len(jobs) == 1
    assert jobs[0]["url"] == "https://example.com/job1"
    assert note == "Searched ops director roles. Found strong matches."
    assert mock_client.messages.create.call_count == 2


def test_run_search_agent_respects_max_rounds_cap():
    mock_tool_use = MagicMock()
    mock_tool_use.type = "tool_use"
    mock_tool_use.id = "tool_xyz"
    mock_tool_use.input = {"queries": ["Director"]}

    mock_response = MagicMock()
    mock_response.content = [mock_tool_use]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    profile = {"name": "Jie", "skills": [], "previous_roles": [], "target_roles": [], "open_to": []}

    with patch("search_agent.anthropic.Anthropic", return_value=mock_client):
        with patch("search_agent.sponsor_filter.load_sponsor_names", return_value=[]):
            with patch("search_agent._execute_search", return_value=([], "No jobs")):
                search_agent.run_search_agent(profile, "Bristol", 60000)

    assert mock_client.messages.create.call_count == search_agent.MAX_ROUNDS


def test_run_search_agent_deduplicates_jobs_across_rounds():
    job = _make_job("https://example.com/same-url")

    mock_tool_use_1 = MagicMock()
    mock_tool_use_1.type = "tool_use"
    mock_tool_use_1.id = "t1"
    mock_tool_use_1.input = {"queries": ["Ops Director"]}

    mock_tool_use_2 = MagicMock()
    mock_tool_use_2.type = "tool_use"
    mock_tool_use_2.id = "t2"
    mock_tool_use_2.input = {"queries": ["Programme Director"]}

    mock_text = MagicMock()
    mock_text.type = "text"
    mock_text.text = "Done."

    mock_response_1 = MagicMock()
    mock_response_1.content = [mock_tool_use_1]
    mock_response_2 = MagicMock()
    mock_response_2.content = [mock_tool_use_2]
    mock_response_3 = MagicMock()
    mock_response_3.content = [mock_text]

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [mock_response_1, mock_response_2, mock_response_3]

    profile = {"name": "Jie", "skills": [], "previous_roles": [], "target_roles": [], "open_to": []}

    seen_across_calls: set[str] = set()

    def fake_execute(tool_input, default_location, min_salary, sponsor_names, seen_urls):
        url = "https://example.com/same-url"
        if url in seen_urls:
            return [], "No new jobs."
        seen_urls.add(url)
        return [job], f"Found 1 job: {url}"

    with patch("search_agent.anthropic.Anthropic", return_value=mock_client):
        with patch("search_agent.sponsor_filter.load_sponsor_names", return_value=[]):
            with patch("search_agent._execute_search", side_effect=fake_execute):
                jobs, note = search_agent.run_search_agent(profile, "Bristol", 60000)

    assert len(jobs) == 1
```

- [ ] **Step 2: Run tests to verify new tests fail**

```
pytest tests/test_search_agent.py -v
```

Expected: 5 new tests FAIL with `AttributeError: module 'search_agent' has no attribute 'run_search_agent'`

- [ ] **Step 3: Add `run_search_agent` to `search_agent.py`**

Append after `_execute_search`:

```python
def run_search_agent(
    profile: dict, location: str, min_salary: int
) -> tuple[list[dict], str]:
    """Drive the agentic search loop. Returns (sponsored_jobs, strategy_note)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    client = anthropic.Anthropic(api_key=api_key)
    sponsor_names = sponsor_filter.load_sponsor_names()
    system_prompt = _build_system_prompt(profile, location, min_salary)

    messages: list[dict] = [
        {"role": "user", "content": "Find the best matching jobs for this candidate."}
    ]
    all_sponsored: list[dict] = []
    seen_urls: set[str] = set()
    strategy_note = "Search complete."

    for _ in range(MAX_ROUNDS):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            tools=[SEARCH_TOOL],
            messages=messages,
        )

        for block in response.content:
            if block.type == "text":
                strategy_note = block.text

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            break

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tool_use in tool_uses:
            new_jobs, result_text = _execute_search(
                tool_use.input,
                default_location=location,
                min_salary=min_salary,
                sponsor_names=sponsor_names,
                seen_urls=seen_urls,
            )
            all_sponsored.extend(new_jobs)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result_text,
            })

        messages.append({"role": "user", "content": tool_results})

    return all_sponsored, strategy_note
```

- [ ] **Step 4: Run all search_agent tests**

```
pytest tests/test_search_agent.py -v
```

Expected: all 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add search_agent.py tests/test_search_agent.py
git commit -m "feat: add run_search_agent — agentic tool-use loop with MAX_ROUNDS cap"
```

---

### Task 3: Integrate agent into `digest.py`

**Files:**
- Modify: `digest.py`
- Modify: `tests/test_digest.py`

- [ ] **Step 1: Write failing tests for the agent branch in `digest.main()`**

Append to `tests/test_digest.py`:

```python
import os


def test_main_uses_agent_when_profile_present_in_config():
    from digest import main

    config = {
        "profile": {
            "name": "Jie",
            "current_role": "Operations Director",
            "seniority": "Senior / Director",
            "industry": "NHS",
            "skills": ["stakeholder management"],
            "previous_roles": ["Project Manager"],
            "target_roles": ["Operations Director"],
            "open_to": ["Head of Operations"],
        },
        "location": "Bristol",
        "min_salary": 60000,
    }
    mock_job = {
        "title": "Operations Director",
        "company": "NHS Trust",
        "url": "https://example.com/1",
        "location": "Bristol",
        "salary": "£75,000",
        "description": "",
        "source": "Reed",
        "sponsor_name": "NHS Trust",
    }

    with patch("digest.load_config", return_value=config), \
         patch("digest.search_agent.run_search_agent", return_value=([mock_job], "Searched 2 angles.")) as mock_agent, \
         patch("digest.format_email_html", return_value="<html>") as mock_html, \
         patch("digest.send_email"), \
         patch.dict(os.environ, {"RECIPIENT_EMAIL": "jie@example.com", "GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
        main()

    mock_agent.assert_called_once_with(config["profile"], "Bristol", 60000)
    args = mock_html.call_args[0]
    assert args[1] == "Searched 2 angles."


def test_main_uses_static_queries_when_no_profile_in_config():
    from digest import main

    config = {
        "search_queries": ["Operations Director Bristol"],
        "location": "Bristol",
        "min_salary": 60000,
    }

    with patch("digest.load_config", return_value=config), \
         patch("digest.collect_jobs", return_value=[]) as mock_collect, \
         patch("digest.sponsor_filter.load_sponsor_names", return_value=[]), \
         patch("digest.sponsor_filter.filter_jobs", return_value=[]), \
         patch("digest.format_email_html", return_value="<html>"), \
         patch("digest.send_email"), \
         patch.dict(os.environ, {"RECIPIENT_EMAIL": "jie@example.com", "GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
        main()

    mock_collect.assert_called_once_with(["Operations Director Bristol"], "Bristol", 60000)
```

- [ ] **Step 2: Run new tests to verify they fail**

```
pytest tests/test_digest.py::test_main_uses_agent_when_profile_present_in_config tests/test_digest.py::test_main_uses_static_queries_when_no_profile_in_config -v
```

Expected: FAIL — `AttributeError: module 'digest' has no attribute 'search_agent'`

- [ ] **Step 3: Update `digest.py`**

Add import at the top with the other imports:

```python
import search_agent
```

Replace the existing `main()` function body:

```python
def main() -> None:
    config = load_config()

    if "profile" in config:
        filtered, summary = search_agent.run_search_agent(
            config["profile"], config["location"], config["min_salary"]
        )
    else:
        jobs = collect_jobs(config["search_queries"], config["location"], config["min_salary"])
        sponsor_names = sponsor_filter.load_sponsor_names()
        filtered = sponsor_filter.filter_jobs(jobs, sponsor_names)
        summary = (
            analyse_results(filtered, config)
            if filtered
            else "No matching roles were found today from licensed UK visa sponsors."
        )

    today = date.today().strftime("%d %B %Y")
    count = len(filtered)
    subject = f"Job digest — {count} match{'es' if count != 1 else ''} — {today}"
    preamble = config.get("preamble", "")
    html_body = format_email_html(filtered, summary, today, preamble)
    send_email(
        subject=subject,
        html_body=html_body,
        recipient=os.environ["RECIPIENT_EMAIL"],
        gmail_user=os.environ["GMAIL_USER"],
        gmail_app_password=os.environ["GMAIL_APP_PASSWORD"],
    )
```

- [ ] **Step 4: Run the full test suite**

```
pytest tests/ -v
```

Expected: all tests PASS, including existing digest tests and two new ones.

- [ ] **Step 5: Commit**

```bash
git add digest.py tests/test_digest.py
git commit -m "feat: integrate search_agent into digest — branch on profile vs static queries"
```

---

### Task 4: Update `digest_config.yaml` with profile block

**Files:**
- Modify: `digest_config.yaml`

- [ ] **Step 1: Replace `digest_config.yaml` with the profile-based config**

The existing `search_queries` key is kept as a fallback comment so it can be restored if needed. Fill in Jie's actual details — the values below are starters; update them to match the real profile.

```yaml
profile:
  name: Jie
  current_role: Operations Director
  seniority: Senior / Director
  industry: NHS / Healthcare / Public Sector
  skills:
    - stakeholder management
    - digital transformation
    - budget control
    - programme delivery
  previous_roles:
    - Business Manager
    - Project Manager
    - Service Improvement Lead
  target_roles:
    - Operations Director
    - Programme Director
    - Digital Transformation Lead
  open_to:
    - Strategy Consultant
    - Head of Operations
    - Deputy Director

location: Bristol
min_salary: 60000

# Uncomment to fall back to static queries (removes agent behaviour):
# search_queries:
#   - "Project Manager digital transformation"
#   - "IT Consultant stakeholder management"

preamble: ""
```

- [ ] **Step 2: Run the full test suite to confirm config change doesn't break anything**

```
pytest tests/ -v
```

Expected: all tests PASS (config file is not read by tests — they mock `load_config`).

- [ ] **Step 3: Commit**

```bash
git add digest_config.yaml
git commit -m "config: switch digest to profile-based agent search"
```

---

### Task 5: Smoke test the agent end-to-end (no email send)

**Files:** none changed — this is a manual verification step.

- [ ] **Step 1: Add a `__main__` guard to `search_agent.py` for quick local testing**

Append to the bottom of `search_agent.py`:

```python
if __name__ == "__main__":
    import yaml
    import logging
    logging.basicConfig(level=logging.INFO)
    with open("digest_config.yaml") as f:
        cfg = yaml.safe_load(f)
    if "profile" not in cfg:
        print("No profile in digest_config.yaml — nothing to test.")
    else:
        jobs, note = run_search_agent(cfg["profile"], cfg["location"], cfg["min_salary"])
        print(f"\n=== Strategy note ===\n{note}")
        print(f"\n=== Jobs found: {len(jobs)} ===")
        for j in jobs[:5]:
            print(f"  - {j['title']} at {j.get('company')} ({j.get('location')}) {j.get('salary')}")
```

- [ ] **Step 2: Run the smoke test**

```
python search_agent.py
```

Expected: agent runs 1–5 rounds, prints a strategy note and at least some job listings. If `ANTHROPIC_API_KEY` is not set, it raises `RuntimeError` — set it in `.env` first.

- [ ] **Step 3: Commit**

```bash
git add search_agent.py
git commit -m "chore: add smoke test entry point to search_agent"
```
