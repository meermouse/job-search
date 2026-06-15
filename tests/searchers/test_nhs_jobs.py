import pytest
from searchers.nhs_jobs import search

NHS_HTML = """
<html><body>
  <div data-test="search-result">
    <a href="/candidate/jobadvert/A123" data-test="job-title">NHS Data Analyst</a>
    <span data-test="employer-name">NHS Bristol Trust</span>
    <span data-test="job-location">Bristol</span>
    <span data-test="job-salary">£35,392 - £42,618 a year</span>
  </div>
  <div data-test="search-result">
    <a href="/candidate/jobadvert/B456" data-test="job-title">IT Support Specialist</a>
    <span data-test="employer-name">NHS Manchester Trust</span>
    <span data-test="job-location">Manchester</span>
    <span data-test="job-salary">£28,000</span>
  </div>
</body></html>
"""


def test_search_returns_normalised_jobs(mocker):
    mock_response = mocker.MagicMock()
    mock_response.text = NHS_HTML
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("searchers.nhs_jobs.requests.get", return_value=mock_response)

    # min_salary=30000: NHS Data Analyst (£35,392) passes; IT Support (£28,000) is filtered
    results = search(["data analyst"], "Bristol", 30000)

    assert len(results) == 1
    assert results[0]["title"] == "NHS Data Analyst"
    assert results[0]["company"] == "NHS Bristol Trust"
    assert results[0]["url"] == "https://www.jobs.nhs.uk/candidate/jobadvert/A123"
    assert results[0]["source"] == "NHS Jobs"


def test_search_filters_below_min_salary(mocker):
    mock_response = mocker.MagicMock()
    mock_response.text = NHS_HTML
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("searchers.nhs_jobs.requests.get", return_value=mock_response)

    # min_salary=40000: both jobs are below this threshold
    results = search(["data analyst"], "Bristol", 40000)
    assert results == []


def test_search_includes_jobs_without_salary(mocker):
    html_no_salary = """
    <html><body>
      <div data-test="search-result">
        <a href="/candidate/jobadvert/C789" data-test="job-title">Mystery Role</a>
        <span data-test="employer-name">NHS Trust</span>
        <span data-test="job-location">Bristol</span>
      </div>
    </body></html>
    """
    mock_response = mocker.MagicMock()
    mock_response.text = html_no_salary
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("searchers.nhs_jobs.requests.get", return_value=mock_response)

    # Jobs with no salary element should pass through (we can't know if they're below threshold)
    results = search(["mystery"], "Bristol", 60000)
    assert len(results) == 1
    assert results[0]["salary"] == ""


def test_search_deduplicates_across_queries(mocker):
    mock_response = mocker.MagicMock()
    mock_response.text = NHS_HTML
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("searchers.nhs_jobs.requests.get", return_value=mock_response)

    results = search(["data analyst", "data analyst duplicate query"], "Bristol", 30000)
    urls = [r["url"] for r in results]
    assert len(urls) == len(set(urls))


def test_search_handles_request_error(mocker):
    mocker.patch("searchers.nhs_jobs.requests.get", side_effect=Exception("Timeout"))

    results = search(["data analyst"], "Bristol", 30000)
    assert results == []
