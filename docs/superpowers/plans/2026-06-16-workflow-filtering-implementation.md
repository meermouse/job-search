# Workflow & Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single-phase search loop with a three-phase Plan→Search→Evaluate pipeline that enforces employment type, NHS banding, clinical role exclusion, and qualification matching with a 1–5 suitability score per job.

**Architecture:** `job_planner.py` produces a `SearchPlan` from the profile; `search_agent.py` follows the plan and pre-filters raw results; `job_evaluator.py` scores every collected job 1–5; `digest.py` wires all three phases and splits the email into "Strong matches" (4–5) and "Worth a look" (3).

**Tech Stack:** Python 3.11+, anthropic SDK, PyYAML, pytest, pytest-mock

---

## File Map

```
digest_config.yaml            ← add qualifications + employment_type
job_planner.py                ← NEW: create_plan() → SearchPlan dict
job_evaluator.py              ← NEW: evaluate() → list of scored jobs
search_agent.py               ← MODIFY: accept plan, add pre-filters + quality signal
digest.py                     ← MODIFY: three-phase main(), updated format_email_html()
tests/test_job_planner.py     ← NEW
tests/test_job_evaluator.py   ← NEW
tests/test_search_agent.py    ← MODIFY: update signatures, add pre-filter tests
tests/test_digest.py          ← MODIFY: update agent integration test
```

---

## Task 1: Profile Config Update

**Files:**
- Modify: `digest_config.yaml`

- [ ] **Step 1: Add new fields to `digest_config.yaml`**

Open `digest_config.yaml` and add two fields inside the `profile` block:

```yaml
profile:
  name: Jie
  current_role: NHS Digital Transformation
  about: |
    Experienced with health care project management, digital transformation and education
    facilities management. Technology and consulting acumen. Works closely with practitioners
    and IT professionals to develop new ways of working in order to improve patient access
    and patient experience. Works with stakeholders such as health providers, and local
    education and training boards to deliver value. Understands and responds to patients
    needs by positioning appropriate solutions and services to meet best outcomes. Sets up
    and leads projects that are vital to patient care being of the highest possible standard.
  seniority: Senior
  industry: NHS / Private Sector / Business
  skills:
    - Analytical Skills
    - digital transformation
    - Digital Marketing
    - Project Initiation and Planning
    - Operations and Supply Chain Decisions and Metrics
    - Business Strategy
  previous_roles:
    - Executive Secretary to the General Manager
    - Business Manager of Research Centre
    - Instructor of Clinical Skills
    - Workforce and Governance Manager for Digital Services
  target_roles:
    - Business Manager
    - Digital Transformation
    - Senior Management
  open_to:
    - Strategy Consultant
    - Project Planning
  qualifications: []                   # fill in Jie's actual qualifications later
  employment_type:
    - full-time

location: Bristol
min_salary: 60000

preamble: "Hey Jie, its your mule here. Good morning/afternoon/evening. I hope these results are getting better. Just a thought, what shall we call this robot?"
```

- [ ] **Step 2: Commit**

```bash
git add digest_config.yaml
git commit -m "feat: add qualifications and employment_type fields to profile"
```

---

## Task 2: Job Planner

**Files:**
- Create: `job_planner.py`
- Create: `tests/test_job_planner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_job_planner.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, patch


SAMPLE_PLAN = {
    "queries": ["Digital Transformation Manager Bristol"],
    "locations": ["Bristol"],
    "exclusion_keywords": ["nurse", "clinical", "ward"],
    "employment_type_exclusions": ["part-time", "part time", "contract", "fixed term", "fixed-term", "temporary"],
    "nhs_band_floor": {"default": "8a", "london_remote_exception": "7"},
    "candidate_qualifications": ["PRINCE2 Practitioner"],
    "evaluator_notes": "Strong management background.",
}


def test_create_plan_returns_valid_plan(mocker):
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(SAMPLE_PLAN))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("job_planner.anthropic.Anthropic", return_value=mock_client)

    from job_planner import create_plan
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        plan = create_plan(
            {"name": "Jie", "target_roles": ["Business Manager"], "skills": ["Digital Transformation"],
             "current_role": "NHS", "about": "", "seniority": "Senior", "industry": "NHS",
             "previous_roles": [], "open_to": [], "qualifications": [], "employment_type": ["full-time"]},
            "Bristol",
            60000,
        )

    assert plan["queries"] == ["Digital Transformation Manager Bristol"]
    assert plan["nhs_band_floor"]["default"] == "8a"
    assert plan["nhs_band_floor"]["london_remote_exception"] == "7"
    assert "nurse" in plan["exclusion_keywords"]
    assert "contract" in plan["employment_type_exclusions"]


def test_create_plan_raises_on_invalid_json(mocker):
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="not valid json {{")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("job_planner.anthropic.Anthropic", return_value=mock_client)

    from job_planner import create_plan
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with pytest.raises(RuntimeError, match="invalid JSON"):
            create_plan({}, "Bristol", 60000)


def test_validate_plan_raises_on_missing_keys():
    from job_planner import _validate_plan
    with pytest.raises(RuntimeError, match="missing required keys"):
        _validate_plan({"queries": ["something"]})


def test_validate_plan_raises_on_empty_queries():
    from job_planner import _validate_plan
    plan = {**SAMPLE_PLAN, "queries": []}
    with pytest.raises(RuntimeError, match="no queries"):
        _validate_plan(plan)


def test_validate_plan_passes_with_valid_plan():
    from job_planner import _validate_plan
    _validate_plan(SAMPLE_PLAN)  # should not raise
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_job_planner.py -v
```

Expected: `ModuleNotFoundError: No module named 'job_planner'`

- [ ] **Step 3: Create `job_planner.py`**

```python
import json
import os
import anthropic

_NHS_BANDING = """
NHS Pay Bands:
Band 6:  £37,338 – £44,962
Band 7:  £46,148 – £52,809
Band 8a: £53,755 – £60,504
Band 8b: £62,215 – £72,293
Band 8c: £74,290 – £85,601
Band 8d: £88,168 – £102,493
Band 9:  £105,385 – £121,271
"""

_SYSTEM = (
    "You are a job search strategist. Given a candidate profile, produce a structured search plan as JSON.\n\n"
    + _NHS_BANDING
    + "\nBand floor rule:\n"
    "- Default: Band 8a+ (below 8a is below threshold regardless of salary text)\n"
    "- Exception: Band 7+ is acceptable ONLY if the role is London-based AND remote or hybrid working "
    "is explicitly mentioned in the job description\n\n"
    "The candidate is in management, administration, and digital transformation — NOT clinical practice. "
    "Clinical roles (nurse, doctor, ward manager, therapist, midwife, physiotherapist, clinical practitioner, "
    "surgeon, radiographer, paramedic, pharmacist, dentist) must be excluded.\n\n"
    "Return only valid JSON, no markdown."
)

_PROMPT = """\
Create a job search plan for this candidate.

Profile:
- Name: {name}
- Current role: {current_role}
- About: {about}
- Seniority: {seniority}
- Industry: {industry}
- Skills: {skills}
- Previous roles: {previous_roles}
- Target roles (directional intent — not literal keywords): {target_roles}
- Open to: {open_to}
- Qualifications: {qualifications}
- Preferred location: {location}
- Minimum salary: £{min_salary:,}
- Employment type required: {employment_type}

Return a JSON object with exactly these keys:
- "queries": list of 5-8 specific search strings. Use target_roles as direction, not keywords — \
generate queries from the intersection of that direction with skills, background, and qualifications. \
Include adjacent titles a recruiter would use (e.g. "Deputy Director Digital", "Senior Programme Manager NHS").
- "locations": list of locations to cover
- "exclusion_keywords": comprehensive list of clinical role keywords to exclude from job titles
- "employment_type_exclusions": list of employment type keywords to exclude based on the candidate's \
employment_type preference (e.g. if full-time only: ["part-time", "part time", "contract", \
"fixed term", "fixed-term", "temporary"])
- "nhs_band_floor": object with exactly two keys: "default" (always "8a") and \
"london_remote_exception" (always "7")
- "candidate_qualifications": list of candidate's qualifications phrased to match JD language
- "evaluator_notes": string with context for the evaluator — qualifications to weight, \
strengths, nuances"""


def create_plan(profile: dict, location: str, min_salary: int) -> dict:
    """Phase 0: produce a SearchPlan dict from the candidate profile."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = _PROMPT.format(
        name=profile.get("name", ""),
        current_role=profile.get("current_role", ""),
        about=profile.get("about", ""),
        seniority=profile.get("seniority", ""),
        industry=profile.get("industry", ""),
        skills=", ".join(profile.get("skills") or []),
        previous_roles=", ".join(profile.get("previous_roles") or []),
        target_roles=", ".join(profile.get("target_roles") or []),
        open_to=", ".join(profile.get("open_to") or []),
        qualifications=", ".join(profile.get("qualifications") or []) or "not specified",
        location=location,
        min_salary=min_salary,
        employment_type=", ".join(profile.get("employment_type") or ["any"]),
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        plan = json.loads(message.content[0].text)
    except (json.JSONDecodeError, IndexError, AttributeError) as exc:
        raise RuntimeError(f"Planner returned invalid JSON: {exc}") from exc

    _validate_plan(plan)
    return plan


def _validate_plan(plan: dict) -> None:
    required = {
        "queries", "locations", "exclusion_keywords", "employment_type_exclusions",
        "nhs_band_floor", "candidate_qualifications", "evaluator_notes",
    }
    missing = required - set(plan.keys())
    if missing:
        raise RuntimeError(f"SearchPlan missing required keys: {missing}")
    if not plan.get("queries"):
        raise RuntimeError("SearchPlan has no queries")
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_job_planner.py -v
```

Expected: All 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add job_planner.py tests/test_job_planner.py
git commit -m "feat: job planner — Phase 0 produces SearchPlan from candidate profile"
```

---

## Task 3: Search Agent Pre-filters & Updated Signatures

**Files:**
- Modify: `search_agent.py`
- Modify: `tests/test_search_agent.py`

- [ ] **Step 1: Write new failing tests and update existing ones**

Replace the contents of `tests/test_search_agent.py` with:

```python
import pytest
from unittest.mock import patch, MagicMock
import search_agent


def _make_job(url, title="Operations Director", company="NHS Trust", location="Bristol", description=""):
    return {
        "url": url,
        "title": title,
        "company": company,
        "location": location,
        "salary": "£70,000",
        "source": "Reed",
        "description": description,
    }


def _make_plan():
    return {
        "queries": ["Operations Director Bristol"],
        "locations": ["Bristol"],
        "exclusion_keywords": ["nurse", "clinical", "ward", "therapist", "midwife"],
        "employment_type_exclusions": ["part-time", "part time", "contract", "fixed term", "fixed-term", "temporary"],
        "nhs_band_floor": {"default": "8a", "london_remote_exception": "7"},
        "candidate_qualifications": [],
        "evaluator_notes": "",
    }


# --- _is_clinical ---

def test_is_clinical_matches_keyword_in_title():
    job = _make_job("https://example.com/1", title="Senior Nurse Manager")
    assert search_agent._is_clinical(job, ["nurse", "clinical"]) is True


def test_is_clinical_no_match():
    job = _make_job("https://example.com/1", title="Operations Director")
    assert search_agent._is_clinical(job, ["nurse", "clinical"]) is False


def test_is_clinical_empty_keywords():
    job = _make_job("https://example.com/1", title="Senior Nurse Manager")
    assert search_agent._is_clinical(job, []) is False


# --- _is_excluded_employment_type ---

def test_is_excluded_employment_type_matches_part_time_in_title():
    job = _make_job("https://example.com/1", title="Part-Time Programme Manager")
    assert search_agent._is_excluded_employment_type(job, ["part-time", "part time"]) is True


def test_is_excluded_employment_type_matches_contract_in_description():
    job = _make_job("https://example.com/1", description="This is a fixed term contract position.")
    assert search_agent._is_excluded_employment_type(job, ["fixed term", "contract"]) is True


def test_is_excluded_employment_type_no_match():
    job = _make_job("https://example.com/1", title="Full-Time Operations Director", description="Permanent role.")
    assert search_agent._is_excluded_employment_type(job, ["part-time", "contract"]) is False


def test_is_excluded_employment_type_empty_keywords():
    job = _make_job("https://example.com/1", title="Part-Time Manager")
    assert search_agent._is_excluded_employment_type(job, []) is False


# --- _band_below_floor ---

def test_band_below_floor_drops_band_7_for_bristol():
    job = _make_job("https://example.com/1", title="Programme Manager Band 7", location="Bristol")
    plan = _make_plan()
    assert search_agent._band_below_floor(job, plan) is True


def test_band_below_floor_keeps_band_8a_for_bristol():
    job = _make_job("https://example.com/1", title="Senior Manager Band 8a", location="Bristol")
    plan = _make_plan()
    assert search_agent._band_below_floor(job, plan) is False


def test_band_below_floor_london_remote_exception_allows_band_7():
    job = _make_job(
        "https://example.com/1",
        title="Programme Manager Band 7",
        location="London",
        description="This is a remote/hybrid working role.",
    )
    plan = _make_plan()
    assert search_agent._band_below_floor(job, plan) is False


def test_band_below_floor_london_without_remote_still_requires_8a():
    job = _make_job(
        "https://example.com/1",
        title="Programme Manager Band 7",
        location="London",
        description="Office-based role in central London.",
    )
    plan = _make_plan()
    assert search_agent._band_below_floor(job, plan) is True


def test_band_below_floor_drops_band_6():
    job = _make_job("https://example.com/1", title="Manager Band 6", location="Bristol")
    plan = _make_plan()
    assert search_agent._band_below_floor(job, plan) is True


def test_band_below_floor_no_band_mentioned():
    job = _make_job("https://example.com/1", title="Operations Director", description="£75,000 salary")
    plan = _make_plan()
    assert search_agent._band_below_floor(job, plan) is False


# --- _quality_signal ---

def test_quality_signal_no_jobs():
    signal = search_agent._quality_signal([], round_num=0, max_rounds=5)
    assert "No new jobs" in signal
    assert "Remaining rounds: 4" in signal


def test_quality_signal_moderate_yield():
    jobs = [_make_job(f"https://example.com/{i}") for i in range(5)]
    signal = search_agent._quality_signal(jobs, round_num=1, max_rounds=5)
    assert "5" in signal
    assert "Remaining rounds: 3" in signal


def test_quality_signal_last_round():
    signal = search_agent._quality_signal([], round_num=4, max_rounds=5)
    assert "Remaining rounds: 0" in signal


# --- _execute_search (updated with plan param) ---

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
                plan=_make_plan(),
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
                plan=_make_plan(),
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
                plan=_make_plan(),
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
                plan=_make_plan(),
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
                plan=_make_plan(),
            )
    assert jobs == []
    assert text == "No sponsored jobs found for these queries."


def test_execute_search_drops_clinical_jobs():
    clinical_job = _make_job("https://example.com/1", title="Senior Ward Nurse Manager")
    with patch("search_agent.search_all_streaming", return_value=[("NHS Jobs", [clinical_job], None)]):
        with patch("search_agent.sponsor_filter.filter_jobs", side_effect=lambda jobs, names: jobs):
            jobs, _ = search_agent._execute_search(
                {"queries": ["Manager"]},
                default_location="Bristol",
                min_salary=60000,
                sponsor_names=[],
                seen_urls=set(),
                plan=_make_plan(),
            )
    assert jobs == []


def test_execute_search_drops_part_time_jobs():
    pt_job = _make_job("https://example.com/1", title="Part-Time Operations Director")
    with patch("search_agent.search_all_streaming", return_value=[("Reed", [pt_job], None)]):
        with patch("search_agent.sponsor_filter.filter_jobs", side_effect=lambda jobs, names: jobs):
            jobs, _ = search_agent._execute_search(
                {"queries": ["Operations Director"]},
                default_location="Bristol",
                min_salary=60000,
                sponsor_names=[],
                seen_urls=set(),
                plan=_make_plan(),
            )
    assert jobs == []


def test_execute_search_drops_below_band_floor_jobs():
    band7_job = _make_job("https://example.com/1", title="Programme Manager Band 7", location="Bristol")
    with patch("search_agent.search_all_streaming", return_value=[("NHS Jobs", [band7_job], None)]):
        with patch("search_agent.sponsor_filter.filter_jobs", side_effect=lambda jobs, names: jobs):
            jobs, _ = search_agent._execute_search(
                {"queries": ["Programme Manager"]},
                default_location="Bristol",
                min_salary=60000,
                sponsor_names=[],
                seen_urls=set(),
                plan=_make_plan(),
            )
    assert jobs == []


# --- run_search_agent (updated signature: takes plan) ---

def test_run_search_agent_raises_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        search_agent.run_search_agent({}, _make_plan(), "Bristol", 60000)


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
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                jobs, note = search_agent.run_search_agent(profile, _make_plan(), "Bristol", 60000)

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
                with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                    jobs, note = search_agent.run_search_agent(profile, _make_plan(), "Bristol", 60000)

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
                with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                    search_agent.run_search_agent(profile, _make_plan(), "Bristol", 60000)

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

    def fake_execute(tool_input, default_location, min_salary, sponsor_names, seen_urls, plan):
        url = "https://example.com/same-url"
        if url in seen_urls:
            return [], "No new jobs."
        seen_urls.add(url)
        return [job], f"Found 1 job: {url}"

    with patch("search_agent.anthropic.Anthropic", return_value=mock_client):
        with patch("search_agent.sponsor_filter.load_sponsor_names", return_value=[]):
            with patch("search_agent._execute_search", side_effect=fake_execute):
                with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                    jobs, note = search_agent.run_search_agent(profile, _make_plan(), "Bristol", 60000)

    assert len(jobs) == 1
```

- [ ] **Step 2: Run tests to confirm new tests fail, existing ones may error**

```
pytest tests/test_search_agent.py -v
```

Expected: New tests fail with `AttributeError` (functions not yet defined); existing tests may fail due to missing `plan` kwarg in `_execute_search`.

- [ ] **Step 3: Update `search_agent.py`**

Replace the full contents of `search_agent.py`:

```python
import logging
import os
import re

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

_BAND_PATTERN = re.compile(r'\b(?:afc\s+)?band\s+(6|7|8a|8b|8c|8d|9)\b', re.IGNORECASE)
_BAND_RANK = {"6": 0, "7": 1, "8a": 2, "8b": 3, "8c": 4, "8d": 5, "9": 6}


def _is_clinical(job: dict, exclusion_keywords: list[str]) -> bool:
    """Return True if job title contains a clinical exclusion keyword."""
    title = job.get("title", "").lower()
    return any(kw.lower() in title for kw in exclusion_keywords)


def _is_excluded_employment_type(job: dict, exclusion_keywords: list[str]) -> bool:
    """Return True if job title or description indicates an excluded employment type."""
    if not exclusion_keywords:
        return False
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    return any(kw.lower() in text for kw in exclusion_keywords)


def _band_below_floor(job: dict, plan: dict) -> bool:
    """Return True if job mentions a NHS band below the plan's applicable floor."""
    floor_config = plan.get("nhs_band_floor", {})
    default_floor = floor_config.get("default", "8a")
    exception_floor = floor_config.get("london_remote_exception", "7")

    location = job.get("location", "").lower()
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()

    is_london = "london" in location
    is_remote = any(w in text for w in ["remote", "hybrid", "work from home"])

    applicable_floor = exception_floor if (is_london and is_remote) else default_floor
    floor_rank = _BAND_RANK.get(applicable_floor, 2)

    for band_str in _BAND_PATTERN.findall(text):
        rank = _BAND_RANK.get(band_str.lower(), 99)
        if rank < floor_rank:
            return True
    return False


def _quality_signal(new_jobs: list[dict], round_num: int, max_rounds: int) -> str:
    remaining = max_rounds - round_num - 1
    count = len(new_jobs)
    if count == 0:
        level = "No new jobs found"
    elif count < 4:
        level = f"{count} new job(s) — low yield"
    elif count < 10:
        level = f"{count} new job(s) — moderate yield"
    else:
        level = f"{count} new job(s) — high yield"
    return f"Round quality: {level}. Remaining rounds: {remaining}."


def _build_system_prompt(profile: dict, location: str, min_salary: int) -> str:
    return (
        f"You are an autonomous job search agent for {profile.get('name', 'the candidate')}. "
        "Your goal is to collect as many relevant job listings as possible from employers licensed "
        "to sponsor UK Skilled Worker visas.\n\n"
        "Candidate profile:\n"
        f"- Current role: {profile.get('current_role', '')}\n"
        f"- Seniority: {profile.get('seniority', '')}\n"
        f"- Industry: {profile.get('industry', '')}\n"
        f"- Key skills: {', '.join(profile.get('skills') or [])}\n"
        f"- Previous roles: {', '.join(profile.get('previous_roles') or [])}\n"
        f"- Target roles: {', '.join(profile.get('target_roles') or [])}\n"
        f"- Open to: {', '.join(profile.get('open_to') or [])}\n"
        f"- Preferred location: {location}\n"
        f"- Minimum salary: £{min_salary:,}\n\n"
        "You have been given suggested queries to start with. Use the search_jobs tool to execute searches. "
        "You may adapt the queries, try different locations, or explore adjacent role titles.\n\n"
        "After each round you will receive a quality signal — use it to decide whether to refine your "
        "approach or stop early.\n\n"
        "When satisfied you have collected a good set of results, stop calling the tool. "
        "Write only a brief strategy note (2–3 sentences) describing what angles you searched and why. "
        "Do NOT list or summarise individual jobs — a separate evaluator will handle that.\n\n"
        f"You have a maximum of {MAX_ROUNDS} search rounds."
    )


def _execute_search(
    tool_input: dict,
    default_location: str,
    min_salary: int,
    sponsor_names: list[str],
    seen_urls: set[str],
    plan: dict,
) -> tuple[list[dict], str]:
    """Run one search round. Returns (new_sponsored_jobs, result_text_for_claude)."""
    queries = tool_input["queries"]
    location = tool_input.get("location", default_location)
    distance = tool_input.get("distance", 50)

    exclusion_keywords = plan.get("exclusion_keywords", [])
    employment_type_exclusions = plan.get("employment_type_exclusions", [])

    all_jobs: list[dict] = []
    for _platform, jobs, error in search_all_streaming(queries, location, min_salary, distance):
        if error:
            logger.warning("Platform '%s' returned an error: %s", _platform, error)
        all_jobs.extend(jobs)

    filtered_jobs = []
    for job in all_jobs:
        if _is_clinical(job, exclusion_keywords):
            continue
        if _is_excluded_employment_type(job, employment_type_exclusions):
            continue
        if _band_below_floor(job, plan):
            continue
        filtered_jobs.append(job)

    sponsored = sponsor_filter.filter_jobs(filtered_jobs, sponsor_names)

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
            f"({j.get('location', '')}) — {j.get('salary', 'Not stated')} [{j.get('source', '')}]\n"
            f"   URL: {j.get('url', '')}"
        )
    return new_jobs, "\n".join(lines)


def run_search_agent(
    profile: dict, plan: dict, location: str, min_salary: int
) -> tuple[list[dict], str]:
    """Phase 1: drive the agentic search loop. Returns (sponsored_jobs, strategy_note)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    client = anthropic.Anthropic(api_key=api_key)
    sponsor_names = sponsor_filter.load_sponsor_names()
    system_prompt = _build_system_prompt(profile, location, min_salary)

    initial_queries = plan.get("queries", [])
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"Find the best matching jobs for this candidate. "
                f"Suggested queries from the search plan: {initial_queries}. "
                f"Adapt these as needed."
            ),
        }
    ]
    all_sponsored: list[dict] = []
    seen_urls: set[str] = set()
    strategy_note = "Search complete."
    hit_cap = True

    print(f"[Agent] Starting search for {profile.get('name', 'candidate')} — up to {MAX_ROUNDS} rounds")

    for round_num in range(MAX_ROUNDS):
        print(f"[Agent] Round {round_num + 1}: asking Claude what to search...")
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            tools=[SEARCH_TOOL],
            messages=messages,
        )

        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if not tool_uses:
            hit_cap = False
            for block in response.content:
                if block.type == "text":
                    strategy_note = block.text
            print(f"[Agent] Claude satisfied — stopping after {round_num + 1} round(s), {len(all_sponsored)} jobs found")
            break

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tool_use in tool_uses:
            queries = tool_use.input.get("queries", [])
            search_location = tool_use.input.get("location", location)
            print(f"[Agent] Round {round_num + 1}: searching {queries} in {search_location}")
            new_jobs, result_text = _execute_search(
                tool_use.input,
                default_location=location,
                min_salary=min_salary,
                sponsor_names=sponsor_names,
                seen_urls=seen_urls,
                plan=plan,
            )
            quality = _quality_signal(new_jobs, round_num, MAX_ROUNDS)
            print(f"[Agent] Round {round_num + 1}: found {len(new_jobs)} new sponsored jobs (total: {len(all_sponsored) + len(new_jobs)})")
            all_sponsored.extend(new_jobs)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": f"{result_text}\n\n{quality}",
            })

        messages.append({"role": "user", "content": tool_results})

    if hit_cap:
        print(f"[Agent] Reached {MAX_ROUNDS}-round limit — {len(all_sponsored)} jobs found")
        strategy_note = f"Search reached the {MAX_ROUNDS}-round limit without a final summary."

    return all_sponsored, strategy_note


if __name__ == "__main__":
    import yaml
    logging.basicConfig(level=logging.INFO)
    with open("digest_config.yaml") as f:
        cfg = yaml.safe_load(f)
    if "profile" not in cfg:
        print("No profile in digest_config.yaml — nothing to test.")
    else:
        import job_planner
        plan = job_planner.create_plan(cfg["profile"], cfg["location"], cfg["min_salary"])
        jobs, note = run_search_agent(cfg["profile"], plan, cfg["location"], cfg["min_salary"])
        print(f"\n=== Strategy note ===\n{note}")
        print(f"\n=== Jobs found: {len(jobs)} ===")
        for j in jobs[:5]:
            print(f"  - {j['title']} at {j.get('company')} ({j.get('location')}) {j.get('salary')}")
```

- [ ] **Step 4: Run all search_agent tests**

```
pytest tests/test_search_agent.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add search_agent.py tests/test_search_agent.py
git commit -m "feat: search agent pre-filters — clinical, employment type, NHS band floor"
```

---

## Task 4: Job Evaluator

**Files:**
- Create: `job_evaluator.py`
- Create: `tests/test_job_evaluator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_job_evaluator.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, patch


def _make_job(idx, title="Operations Director", score=4):
    return {
        "title": title,
        "company": "NHS Trust",
        "location": "Bristol",
        "salary": "£75,000",
        "description": "Senior management role.",
        "url": f"https://example.com/{idx}",
        "source": "Reed",
        "sponsor_name": "NHS Trust",
    }


def _make_plan():
    return {
        "candidate_qualifications": ["PRINCE2 Practitioner"],
        "evaluator_notes": "Strong management background.",
        "nhs_band_floor": {"default": "8a", "london_remote_exception": "7"},
    }


def _make_profile():
    return {
        "seniority": "Senior",
        "employment_type": ["full-time"],
    }


def _make_scored_response(jobs):
    return [
        {
            "job_index": i,
            "score": 4,
            "score_breakdown": {
                "role_type": 5,
                "seniority": 4,
                "salary_band": 4,
                "employment_type": 5,
                "qualifications": 3,
            },
            "reasoning": "Strong management role.",
        }
        for i in range(len(jobs))
    ]


def test_evaluate_returns_scored_jobs(mocker):
    jobs = [_make_job(0), _make_job(1)]
    response_data = _make_scored_response(jobs)

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(response_data))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("job_evaluator.anthropic.Anthropic", return_value=mock_client)

    from job_evaluator import evaluate
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        result = evaluate(jobs, _make_plan(), _make_profile(), 60000)

    assert len(result) == 2
    assert result[0]["score"] == 4
    assert "score_breakdown" in result[0]
    assert "reasoning" in result[0]
    assert result[0]["title"] == "Operations Director"


def test_evaluate_preserves_original_job_fields(mocker):
    jobs = [_make_job(0)]
    response_data = _make_scored_response(jobs)

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(response_data))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("job_evaluator.anthropic.Anthropic", return_value=mock_client)

    from job_evaluator import evaluate
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        result = evaluate(jobs, _make_plan(), _make_profile(), 60000)

    assert result[0]["url"] == "https://example.com/0"
    assert result[0]["sponsor_name"] == "NHS Trust"


def test_evaluate_returns_empty_list_for_empty_input():
    from job_evaluator import evaluate
    result = evaluate([], _make_plan(), _make_profile(), 60000)
    assert result == []


def test_evaluate_returns_jobs_unscored_on_api_failure(mocker):
    jobs = [_make_job(0)]
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")
    mocker.patch("job_evaluator.anthropic.Anthropic", return_value=mock_client)

    from job_evaluator import evaluate
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        result = evaluate(jobs, _make_plan(), _make_profile(), 60000)

    assert len(result) == 1
    assert result[0]["title"] == "Operations Director"
    assert "score" not in result[0]


def test_evaluate_returns_jobs_unscored_on_invalid_json(mocker):
    jobs = [_make_job(0)]
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="not json {{")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("job_evaluator.anthropic.Anthropic", return_value=mock_client)

    from job_evaluator import evaluate
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        result = evaluate(jobs, _make_plan(), _make_profile(), 60000)

    assert len(result) == 1
    assert "score" not in result[0]
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_job_evaluator.py -v
```

Expected: `ModuleNotFoundError: No module named 'job_evaluator'`

- [ ] **Step 3: Create `job_evaluator.py`**

```python
import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

_NHS_BANDING = """
Band 6:  £37,338 – £44,962
Band 7:  £46,148 – £52,809
Band 8a: £53,755 – £60,504
Band 8b: £62,215 – £72,293
Band 8c: £74,290 – £85,601
Band 8d: £88,168 – £102,493
Band 9:  £105,385 – £121,271
"""

_SYSTEM = (
    "You are a job suitability evaluator. Score each job 1–5 across five dimensions, "
    "then compute a weighted overall score (rounded to nearest integer).\n\n"
    "NHS Pay Bands:\n" + _NHS_BANDING + "\n"
    "Band floor rules:\n"
    "- Default: Band 8a+ (below 8a → score 1 on salary_band)\n"
    "- Exception: Band 7+ is acceptable ONLY if the role is London-based AND remote/hybrid "
    "is explicitly mentioned in the description\n\n"
    "Scoring dimensions (apply weighted judgment — role_type, employment_type, and qualifications "
    "carry higher weight):\n"
    "- role_type: Is this a management/admin/digital/transformation role? "
    "Clinical roles (nurse, ward, doctor, therapist etc.) → 1 (automatic disqualifier)\n"
    "- seniority: Does the level match the candidate's stated seniority?\n"
    "- salary_band: Does it meet the min salary and band floor? Unclear/unstated → 3\n"
    "- employment_type: HARD FILTER. If employment_type_required is set, any role that is "
    "not that type (part-time, contract, fixed-term, temporary) → 1. If not set → 5\n"
    "- qualifications: Does the JD require quals the candidate holds? "
    "Requires quals they lack → 1–2. Matches well → 4–5. No requirements stated → 3\n\n"
    "Return a JSON array — one object per job — with fields:\n"
    "- job_index: integer (0-based, matching input array order)\n"
    "- score: integer 1–5 (weighted average, rounded)\n"
    "- score_breakdown: object with keys role_type, seniority, salary_band, "
    "employment_type, qualifications (each integer 1–5)\n"
    "- reasoning: string (1–2 sentences explaining the overall score)\n\n"
    "Return only valid JSON array, no markdown."
)


def evaluate(jobs: list[dict], plan: dict, profile: dict, min_salary: int) -> list[dict]:
    """Phase 2: score every job 1–5. Returns jobs with score/score_breakdown/reasoning added.
    Falls back to returning unscored jobs if the evaluator call fails."""
    if not jobs:
        return []

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    employment_type_required = ", ".join(profile.get("employment_type") or []) or "not specified"
    candidate_qualifications = (
        plan.get("candidate_qualifications")
        or profile.get("qualifications")
        or []
    )

    jobs_text = json.dumps(
        [
            {
                "index": i,
                "title": j.get("title", ""),
                "company": j.get("company", ""),
                "location": j.get("location", ""),
                "salary": j.get("salary", ""),
                "description": j.get("description", ""),
                "source": j.get("source", ""),
            }
            for i, j in enumerate(jobs)
        ],
        indent=2,
    )

    prompt = (
        f"Evaluate these jobs for the following candidate.\n\n"
        f"Candidate:\n"
        f"- Seniority: {profile.get('seniority', '')}\n"
        f"- Required employment type: {employment_type_required}\n"
        f"- Qualifications: {', '.join(candidate_qualifications) or 'not specified'}\n"
        f"- Minimum salary: £{min_salary:,}\n\n"
        f"Evaluator notes: {plan.get('evaluator_notes', '')}\n\n"
        f"Jobs to evaluate:\n{jobs_text}"
    )

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        scores = json.loads(message.content[0].text)
    except Exception as exc:
        logger.warning("Evaluator failed: %s — returning jobs unscored", exc)
        return jobs

    scored = []
    for entry in scores:
        idx = entry.get("job_index", -1)
        if 0 <= idx < len(jobs):
            scored.append(
                {
                    **jobs[idx],
                    "score": entry.get("score", 0),
                    "score_breakdown": entry.get("score_breakdown", {}),
                    "reasoning": entry.get("reasoning", ""),
                }
            )

    return scored
```

- [ ] **Step 4: Run all evaluator tests**

```
pytest tests/test_job_evaluator.py -v
```

Expected: All 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add job_evaluator.py tests/test_job_evaluator.py
git commit -m "feat: job evaluator — Phase 2 scores jobs 1-5 across five dimensions"
```

---

## Task 5: Digest Integration

**Files:**
- Modify: `digest.py`
- Modify: `tests/test_digest.py`

- [ ] **Step 1: Update `digest.py`**

Replace the full contents of `digest.py`:

```python
import html
import os
import markdown as md_lib
import smtplib
import ssl
import logging
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
import yaml

import job_evaluator
import job_planner
import search_agent
import sponsor_filter
from searchers import search_all_streaming

logger = logging.getLogger(__name__)


def load_config(path: str = "digest_config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def collect_jobs(queries: list[str], location: str, min_salary: int) -> list[dict]:
    all_jobs: list[dict] = []
    for _platform, jobs, _error in search_all_streaming(queries, location, min_salary):
        all_jobs.extend(jobs)
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for job in all_jobs:
        if not job["url"]:
            logger.debug("Skipping job with no URL: %s at %s", job.get("title"), job.get("company"))
            continue
        if job["url"] not in seen_urls:
            seen_urls.add(job["url"])
            deduped.append(job)
    return deduped


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
                    f"- Queries: {', '.join(config.get('search_queries', []))}\n"
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


def _make_table(jobs: list[dict], include_reasoning: bool = False) -> str:
    if not jobs:
        return ""
    headers = ["Job Title", "Company", "Location", "Salary", "Source"]
    if include_reasoning:
        headers.append("Why")
    header_html = "".join(f"<th>{h}</th>" for h in headers)
    rows = ""
    for j in jobs:
        reasoning_cell = (
            f"<td>{html.escape(j.get('reasoning', ''))}</td>" if include_reasoning else ""
        )
        rows += (
            f"<tr>"
            f"<td><a href='{html.escape(j['url'])}'>{html.escape(j['title'])}</a></td>"
            f"<td>{html.escape(j.get('sponsor_name') or j.get('company', ''))}</td>"
            f"<td>{html.escape(j.get('location', ''))}</td>"
            f"<td>{html.escape(j.get('salary', ''))}</td>"
            f"<td>{html.escape(j.get('source', ''))}</td>"
            f"{reasoning_cell}"
            f"</tr>"
        )
    return (
        "<table border='1' cellpadding='6' cellspacing='0' "
        "style='border-collapse:collapse;width:100%'>"
        f"<thead><tr style='background:#f0f0f0'>{header_html}</tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def format_email_html(
    strong_jobs: list[dict],
    summary: str,
    today: str,
    preamble: str = "",
    worth_a_look: list[dict] | None = None,
) -> str:
    preamble_html = md_lib.markdown(preamble) if preamble else ""
    strong_table = _make_table(strong_jobs, include_reasoning=True)
    worth_table = _make_table(worth_a_look or [], include_reasoning=True)

    strong_section = f"<h3>Strong matches</h3>{strong_table}" if strong_table else ""
    worth_section = f"<h3>Worth a look</h3>{worth_table}" if worth_table else ""

    return (
        f"<html><body>"
        f"<h2>Jie's Job Digest — {html.escape(today)}</h2>"
        f"{preamble_html}"
        f"<hr/>"
        f"{md_lib.markdown(summary)}"
        f"{strong_section}"
        f"{worth_section}"
        f"</body></html>"
    )


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


def main() -> None:
    config = load_config()

    if "profile" in config:
        plan = job_planner.create_plan(
            config["profile"], config["location"], config["min_salary"]
        )
        raw_jobs, strategy_note = search_agent.run_search_agent(
            config["profile"], plan, config["location"], config["min_salary"]
        )
        scored_jobs = job_evaluator.evaluate(
            raw_jobs, plan, config["profile"], config["min_salary"]
        )
        strong = [j for j in scored_jobs if j.get("score", 0) >= 4]
        worth_a_look = [j for j in scored_jobs if j.get("score", 0) == 3]
        summary = strategy_note
        count = len(strong)
    else:
        jobs = collect_jobs(config["search_queries"], config["location"], config["min_salary"])
        sponsor_names = sponsor_filter.load_sponsor_names()
        filtered = sponsor_filter.filter_jobs(jobs, sponsor_names)
        summary = (
            analyse_results(filtered, config)
            if filtered
            else "No matching roles were found today from licensed UK visa sponsors."
        )
        strong = filtered
        worth_a_look = []
        count = len(strong)

    today = date.today().strftime("%d %B %Y")
    subject = f"Job digest — {count} match{'es' if count != 1 else ''} — {today}"
    preamble = config.get("preamble", "")
    html_body = format_email_html(strong, summary, today, preamble, worth_a_look=worth_a_look)
    send_email(
        subject=subject,
        html_body=html_body,
        recipient=os.environ["RECIPIENT_EMAIL"],
        gmail_user=os.environ["GMAIL_USER"],
        gmail_app_password=os.environ["GMAIL_APP_PASSWORD"],
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
```

- [ ] **Step 2: Update `tests/test_digest.py` — replace the agent integration test**

Find and replace `test_main_uses_agent_when_profile_present_in_config` with the following (all other tests in the file remain unchanged):

```python
def test_main_uses_three_phase_pipeline_when_profile_present():
    from digest import main

    config = {
        "profile": {
            "name": "Jie",
            "current_role": "Operations Director",
            "seniority": "Senior",
            "industry": "NHS",
            "skills": ["stakeholder management"],
            "previous_roles": ["Project Manager"],
            "target_roles": ["Operations Director"],
            "open_to": ["Head of Operations"],
            "qualifications": [],
            "employment_type": ["full-time"],
        },
        "location": "Bristol",
        "min_salary": 60000,
    }
    mock_plan = {
        "queries": ["Operations Director Bristol"],
        "locations": ["Bristol"],
        "exclusion_keywords": [],
        "employment_type_exclusions": [],
        "nhs_band_floor": {"default": "8a", "london_remote_exception": "7"},
        "candidate_qualifications": [],
        "evaluator_notes": "",
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
        "score": 4,
        "score_breakdown": {},
        "reasoning": "Strong match.",
    }

    with patch("digest.load_config", return_value=config), \
         patch("digest.job_planner.create_plan", return_value=mock_plan) as mock_planner, \
         patch("digest.search_agent.run_search_agent", return_value=([mock_job], "Searched 2 angles.")) as mock_agent, \
         patch("digest.job_evaluator.evaluate", return_value=[mock_job]) as mock_eval, \
         patch("digest.format_email_html", return_value="<html>") as mock_html, \
         patch("digest.send_email"), \
         patch.dict(os.environ, {"RECIPIENT_EMAIL": "jie@example.com", "GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
        main()

    mock_planner.assert_called_once_with(config["profile"], "Bristol", 60000)
    mock_agent.assert_called_once_with(config["profile"], mock_plan, "Bristol", 60000)
    mock_eval.assert_called_once_with([mock_job], mock_plan, config["profile"], 60000)
    html_call_args = mock_html.call_args
    assert html_call_args[0][1] == "Searched 2 angles."
```

- [ ] **Step 3: Run all tests**

```
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add digest.py tests/test_digest.py
git commit -m "feat: wire three-phase pipeline in digest — plan, search, evaluate, split email by score"
```

---

## Self-Review

### Spec Coverage

| Spec requirement | Task |
|---|---|
| `qualifications` + `employment_type` profile fields | Task 1 |
| `job_planner.create_plan()` → SearchPlan | Task 2 |
| SearchPlan fields: queries, locations, exclusion_keywords, employment_type_exclusions, nhs_band_floor, candidate_qualifications, evaluator_notes | Task 2 |
| `target_roles` used as directional intent (planner prompt) | Task 2 |
| Band floor default 8a, London/remote exception 7 | Tasks 2, 3 |
| Clinical role pre-filter (`_is_clinical`) | Task 3 |
| Employment type pre-filter (`_is_excluded_employment_type`) | Task 3 |
| NHS band pre-filter (`_band_below_floor`) | Task 3 |
| Quality signal per round | Task 3 |
| `run_search_agent` accepts plan, passes to `_execute_search` | Task 3 |
| Strategy note only — no job summary in search phase | Task 3 |
| `job_evaluator.evaluate()` — five dimensions, 1–5 score | Task 4 |
| Employment type is hard filter (scores 1 if wrong type) | Task 4 (evaluator prompt) |
| Evaluator fallback on failure (returns unscored jobs) | Task 4 |
| Three-phase `main()` in `digest.py` | Task 5 |
| Email split: strong matches (4–5) / worth a look (3) | Task 5 |
| Reasoning column in email table | Task 5 |

### Type Consistency

- `create_plan(profile: dict, location: str, min_salary: int) -> dict` — used consistently in Task 2 and Task 5
- `run_search_agent(profile: dict, plan: dict, location: str, min_salary: int) -> tuple[list[dict], str]` — updated in Task 3, called correctly in Task 5
- `evaluate(jobs: list[dict], plan: dict, profile: dict, min_salary: int) -> list[dict]` — defined in Task 4, called correctly in Task 5
- `format_email_html(strong_jobs, summary, today, preamble="", worth_a_look=None)` — updated in Task 5; existing tests pass `[]` or `[job]` as first arg, which is compatible ✓
- `_execute_search(..., plan: dict)` — updated signature used consistently in Task 3 tests and implementation ✓
