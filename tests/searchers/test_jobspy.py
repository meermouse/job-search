import pandas as pd
import pytest
from searchers.jobspy_searcher import search


def _make_df(rows):
    return pd.DataFrame(rows)


def test_search_returns_normalised_jobs(mocker):
    mock_df = _make_df([
        {
            "title": "Data Engineer",
            "company": "Tech Ltd",
            "location": "Bristol, UK",
            "description": "Great role with Python",
            "job_url": "https://linkedin.com/jobs/123",
            "site": "linkedin",
            "min_amount": 65000,
            "max_amount": 80000,
            "interval": "yearly",
        }
    ])
    mocker.patch("searchers.jobspy_searcher.scrape_jobs", return_value=mock_df)

    results = search(["Data Engineer"], "Bristol", 60000)

    assert len(results) == 1
    assert results[0]["title"] == "Data Engineer"
    assert results[0]["company"] == "Tech Ltd"
    assert results[0]["url"] == "https://linkedin.com/jobs/123"
    assert results[0]["source"] == "Linkedin"
    assert "£65,000" in results[0]["salary"]


def test_search_excludes_jobs_below_salary_floor(mocker):
    mock_df = _make_df([
        {
            "title": "Junior Dev",
            "company": "Small Co",
            "location": "Bristol",
            "description": "Entry level",
            "job_url": "https://indeed.com/jobs/456",
            "site": "indeed",
            "min_amount": 30000,
            "max_amount": 40000,
            "interval": "yearly",
        }
    ])
    mocker.patch("searchers.jobspy_searcher.scrape_jobs", return_value=mock_df)

    results = search(["Junior Dev"], "Bristol", 60000)
    assert results == []


def test_search_handles_scrape_error(mocker):
    mocker.patch("searchers.jobspy_searcher.scrape_jobs", side_effect=Exception("Blocked"))

    results = search(["Data Engineer"], "Bristol", 60000)
    assert results == []


def test_search_handles_missing_salary_fields(mocker):
    mock_df = _make_df([
        {
            "title": "Engineer",
            "company": "Corp",
            "location": "Bristol",
            "description": "A job",
            "job_url": "https://linkedin.com/jobs/789",
            "site": "linkedin",
            "min_amount": None,
            "max_amount": None,
            "interval": None,
        }
    ])
    mocker.patch("searchers.jobspy_searcher.scrape_jobs", return_value=mock_df)

    results = search(["Engineer"], "Bristol", 60000)
    assert len(results) == 1
    assert results[0]["salary"] == ""
