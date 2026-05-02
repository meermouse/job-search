import pytest
from searchers.runner import search_all_streaming

JOB_A = {
    "title": "Data Engineer", "company": "Tech Ltd", "location": "Bristol",
    "salary": "£70,000", "description": "...", "url": "https://linkedin.com/1", "source": "LinkedIn",
}
JOB_B = {
    "title": "Nurse", "company": "NHS Trust", "location": "Bristol",
    "salary": "£35,000", "description": "...", "url": "https://nhsjobs.com/1", "source": "NHS Jobs",
}


def test_search_all_streaming_yields_three_platforms(mocker):
    mocker.patch("searchers.runner.jobspy_searcher.search", return_value=[JOB_A])
    mocker.patch("searchers.runner.reed.search", return_value=[])
    mocker.patch("searchers.runner.nhs_jobs.search", return_value=[JOB_B])

    results = list(search_all_streaming(["data engineer"], "Bristol", 60000))

    assert len(results) == 3
    platform_names = {name for name, _, _ in results}
    assert platform_names == {"LinkedIn + Indeed", "Reed", "NHS Jobs"}


def test_search_all_streaming_returns_jobs(mocker):
    mocker.patch("searchers.runner.jobspy_searcher.search", return_value=[JOB_A])
    mocker.patch("searchers.runner.reed.search", return_value=[])
    mocker.patch("searchers.runner.nhs_jobs.search", return_value=[])

    results = list(search_all_streaming(["data engineer"], "Bristol", 60000))
    all_jobs = [j for _, jobs, _ in results for j in jobs]
    assert len(all_jobs) == 1
    assert all_jobs[0]["title"] == "Data Engineer"


def test_search_all_streaming_handles_platform_failure(mocker):
    mocker.patch("searchers.runner.jobspy_searcher.search", side_effect=Exception("Blocked"))
    mocker.patch("searchers.runner.reed.search", return_value=[JOB_B])
    mocker.patch("searchers.runner.nhs_jobs.search", return_value=[])

    results = list(search_all_streaming(["nurse"], "Bristol", 30000))

    errors = [(name, err) for name, _, err in results if err]
    successes = [(name, jobs) for name, jobs, err in results if err is None]
    assert len(errors) == 1
    assert errors[0][0] == "LinkedIn + Indeed"
    assert any(jobs for _, jobs in successes)


def test_search_all_streaming_no_error_on_success(mocker):
    mocker.patch("searchers.runner.jobspy_searcher.search", return_value=[])
    mocker.patch("searchers.runner.reed.search", return_value=[])
    mocker.patch("searchers.runner.nhs_jobs.search", return_value=[])

    results = list(search_all_streaming(["anything"], "Bristol", 60000))
    assert all(err is None for _, _, err in results)
