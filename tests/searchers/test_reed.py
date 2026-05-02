import pytest
from searchers.reed import search


def test_search_returns_normalised_jobs(mocker):
    mocker.patch.dict("os.environ", {"REED_API_KEY": "test-key"})
    mock_response = mocker.MagicMock()
    mock_response.json.return_value = {
        "results": [
            {
                "jobTitle": "Data Engineer",
                "employerName": "Acme Ltd",
                "locationName": "Bristol",
                "minimumSalary": 65000,
                "maximumSalary": 80000,
                "jobDescription": "Python and SQL required",
                "jobUrl": "https://www.reed.co.uk/jobs/data-engineer/123",
            }
        ]
    }
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("searchers.reed.requests.get", return_value=mock_response)

    results = search(["Data Engineer"], "Bristol", 60000)

    assert len(results) == 1
    assert results[0]["title"] == "Data Engineer"
    assert results[0]["company"] == "Acme Ltd"
    assert results[0]["source"] == "Reed"
    assert "£65,000" in results[0]["salary"]
    assert results[0]["url"] == "https://www.reed.co.uk/jobs/data-engineer/123"


def test_search_handles_api_error(mocker):
    mocker.patch.dict("os.environ", {"REED_API_KEY": "test-key"})
    mocker.patch("searchers.reed.requests.get", side_effect=Exception("Connection error"))

    results = search(["Data Engineer"], "Bristol", 60000)
    assert results == []


def test_search_handles_empty_results(mocker):
    mocker.patch.dict("os.environ", {"REED_API_KEY": "test-key"})
    mock_response = mocker.MagicMock()
    mock_response.json.return_value = {"results": []}
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("searchers.reed.requests.get", return_value=mock_response)

    results = search(["Niche Role"], "Bristol", 60000)
    assert results == []


def test_search_formats_salary_correctly(mocker):
    mocker.patch.dict("os.environ", {"REED_API_KEY": "test-key"})
    mock_response = mocker.MagicMock()
    mock_response.json.return_value = {
        "results": [{
            "jobTitle": "Engineer",
            "employerName": "Corp",
            "locationName": "Bristol",
            "minimumSalary": None,
            "maximumSalary": None,
            "jobDescription": "",
            "jobUrl": "https://www.reed.co.uk/jobs/1",
        }]
    }
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("searchers.reed.requests.get", return_value=mock_response)

    results = search(["Engineer"], "Bristol", 60000)
    assert results[0]["salary"] == ""
