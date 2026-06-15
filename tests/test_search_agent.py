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
