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


def test_is_clinical_matches_legal_role_in_title():
    # Lawyer, solicitor etc. are outside Jie's background and should be caught by title exclusions
    job = _make_job("https://example.com/1", title="NHS Lawyer (Employment Law)")
    assert search_agent._is_clinical(job, ["nurse", "clinical", "lawyer", "solicitor"]) is True


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


def test_is_excluded_employment_type_permanent_in_description_overrides_contract_keyword():
    # "contract" appears in many permanent NHS job descriptions (AfC contract, contract of employment)
    # A posting that says "permanent" should never be filtered on employment type
    job = _make_job(
        "https://example.com/1",
        title="Operations Director",
        description="This is a permanent, full-time post. The post-holder will be employed on an AfC contract.",
    )
    assert search_agent._is_excluded_employment_type(job, ["contract", "fixed term"]) is False


def test_is_excluded_employment_type_permanent_in_title_overrides():
    job = _make_job("https://example.com/1", title="Permanent Operations Director")
    assert search_agent._is_excluded_employment_type(job, ["contract"]) is False


def test_is_excluded_employment_type_fixed_term_contract_still_excluded():
    # Multi-word phrase "fixed-term contract" correctly flags a contract role even without bare "contract"
    job = _make_job(
        "https://example.com/1",
        title="Operations Director",
        description="This is a fixed-term contract position for 12 months.",
    )
    assert search_agent._is_excluded_employment_type(job, ["fixed-term contract", "fixed term"]) is True


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
                filter_log=[],
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
                filter_log=[],
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
                filter_log=[],
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
                filter_log=[],
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
                filter_log=[],
            )
    assert jobs == []
    assert text == "No sponsored jobs found for these queries."


def test_execute_search_drops_clinical_jobs():
    clinical_job = _make_job("https://example.com/1", title="Senior Ward Nurse Manager")
    log: list = []
    with patch("search_agent.search_all_streaming", return_value=[("NHS Jobs", [clinical_job], None)]):
        with patch("search_agent.sponsor_filter.filter_jobs", side_effect=lambda jobs, names: jobs):
            jobs, _ = search_agent._execute_search(
                {"queries": ["Manager"]},
                default_location="Bristol",
                min_salary=60000,
                sponsor_names=[],
                seen_urls=set(),
                plan=_make_plan(),
                filter_log=log,
            )
    assert jobs == []
    assert any(e["stage"] == "Role type" for e in log)


def test_execute_search_drops_part_time_jobs():
    pt_job = _make_job("https://example.com/1", title="Part-Time Operations Director")
    log: list = []
    with patch("search_agent.search_all_streaming", return_value=[("Reed", [pt_job], None)]):
        with patch("search_agent.sponsor_filter.filter_jobs", side_effect=lambda jobs, names: jobs):
            jobs, _ = search_agent._execute_search(
                {"queries": ["Operations Director"]},
                default_location="Bristol",
                min_salary=60000,
                sponsor_names=[],
                seen_urls=set(),
                plan=_make_plan(),
                filter_log=log,
            )
    assert jobs == []
    assert any(e["stage"] == "Employment type" for e in log)


def test_execute_search_drops_below_band_floor_jobs():
    band7_job = _make_job("https://example.com/1", title="Programme Manager Band 7", location="Bristol")
    log: list = []
    with patch("search_agent.search_all_streaming", return_value=[("NHS Jobs", [band7_job], None)]):
        with patch("search_agent.sponsor_filter.filter_jobs", side_effect=lambda jobs, names: jobs):
            jobs, _ = search_agent._execute_search(
                {"queries": ["Programme Manager"]},
                default_location="Bristol",
                min_salary=60000,
                sponsor_names=[],
                seen_urls=set(),
                plan=_make_plan(),
                filter_log=log,
            )
    assert jobs == []
    assert any(e["stage"] == "NHS band floor" for e in log)


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
                jobs, note, _log = search_agent.run_search_agent(profile, _make_plan(), "Bristol", 60000)

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
                    jobs, note, _log = search_agent.run_search_agent(profile, _make_plan(), "Bristol", 60000)

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

    def fake_execute(tool_input, default_location, min_salary, sponsor_names, seen_urls, plan, filter_log):
        url = "https://example.com/same-url"
        if url in seen_urls:
            return [], "No new jobs."
        seen_urls.add(url)
        return [job], f"Found 1 job: {url}"

    with patch("search_agent.anthropic.Anthropic", return_value=mock_client):
        with patch("search_agent.sponsor_filter.load_sponsor_names", return_value=[]):
            with patch("search_agent._execute_search", side_effect=fake_execute):
                with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                    jobs, note, _log = search_agent.run_search_agent(profile, _make_plan(), "Bristol", 60000)

    assert len(jobs) == 1
