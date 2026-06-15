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
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
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
                with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
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
                with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
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

    def fake_execute(tool_input, default_location, min_salary, sponsor_names, seen_urls):
        url = "https://example.com/same-url"
        if url in seen_urls:
            return [], "No new jobs."
        seen_urls.add(url)
        return [job], f"Found 1 job: {url}"

    with patch("search_agent.anthropic.Anthropic", return_value=mock_client):
        with patch("search_agent.sponsor_filter.load_sponsor_names", return_value=[]):
            with patch("search_agent._execute_search", side_effect=fake_execute):
                with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                    jobs, note = search_agent.run_search_agent(profile, "Bristol", 60000)

    assert len(jobs) == 1
