import os
import pytest
from sponsor_filter import load_sponsor_names

FIXTURE_CSV = os.path.join(os.path.dirname(__file__), "fixtures", "sponsors.csv")


def test_load_sponsor_names_filters_worker_route_only(mocker):
    with open(FIXTURE_CSV, encoding="utf-8") as f:
        csv_text = f.read()
    mock_response = mocker.MagicMock()
    mock_response.text = csv_text
    mock_response.raise_for_status = mocker.MagicMock()
    mocker.patch("sponsor_filter.requests.get", return_value=mock_response)
    mocker.patch("builtins.open", mocker.mock_open())

    names = load_sponsor_names("https://example.com/sponsors.csv", cache_path="/tmp/test_cache.csv")

    assert "NHS Bristol Trust" in names
    assert "Acme Technologies Ltd" in names
    assert "Big Data Corp" in names
    assert "Temp Solutions UK" not in names  # Temporary Worker route excluded
    assert len(names) == 4


def test_load_sponsor_names_falls_back_to_cache_on_network_error(mocker, tmp_path):
    with open(FIXTURE_CSV, encoding="utf-8") as f:
        csv_text = f.read()
    cache_file = tmp_path / "sponsors_cache.csv"
    cache_file.write_text(csv_text, encoding="utf-8")
    mocker.patch("sponsor_filter.requests.get", side_effect=Exception("Network error"))

    names = load_sponsor_names("https://example.com/sponsors.csv", cache_path=str(cache_file))

    assert "NHS Bristol Trust" in names
    assert "Temp Solutions UK" not in names


def test_load_sponsor_names_raises_when_no_cache(mocker, tmp_path):
    mocker.patch("sponsor_filter.requests.get", side_effect=Exception("Network error"))
    missing_cache = str(tmp_path / "nonexistent.csv")

    with pytest.raises(RuntimeError, match="Failed to download sponsor CSV"):
        load_sponsor_names("https://example.com/sponsors.csv", cache_path=missing_cache)


from sponsor_filter import filter_jobs

SPONSOR_NAMES = ["NHS Bristol Trust", "Acme Technologies Ltd", "Big Data Corp"]

SAMPLE_JOBS = [
    {
        "title": "Data Engineer",
        "company": "Acme Technologies",  # close but not exact
        "location": "London",
        "salary": "£65,000",
        "description": "Great role",
        "url": "https://example.com/1",
        "source": "LinkedIn",
    },
    {
        "title": "Nurse",
        "company": "NHS Bristol Trust",  # exact match
        "location": "Bristol",
        "salary": "£35,000",
        "description": "Ward nurse",
        "url": "https://example.com/2",
        "source": "NHS Jobs",
    },
    {
        "title": "Barista",
        "company": "Coffee Shop Ltd",  # no match
        "location": "Bristol",
        "salary": "£22,000",
        "description": "Coffee",
        "url": "https://example.com/3",
        "source": "Reed",
    },
]


def test_filter_jobs_passes_fuzzy_match():
    result = filter_jobs(SAMPLE_JOBS, SPONSOR_NAMES)
    urls = [j["url"] for j in result]
    assert "https://example.com/1" in urls  # Acme Technologies ~= Acme Technologies Ltd


def test_filter_jobs_passes_exact_match():
    result = filter_jobs(SAMPLE_JOBS, SPONSOR_NAMES)
    urls = [j["url"] for j in result]
    assert "https://example.com/2" in urls


def test_filter_jobs_blocks_non_sponsor():
    result = filter_jobs(SAMPLE_JOBS, SPONSOR_NAMES)
    urls = [j["url"] for j in result]
    assert "https://example.com/3" not in urls  # Coffee Shop Ltd not a sponsor


def test_filter_jobs_adds_sponsor_name():
    result = filter_jobs(SAMPLE_JOBS, SPONSOR_NAMES)
    acme_job = next(j for j in result if j["url"] == "https://example.com/1")
    assert acme_job["sponsor_name"] == "Acme Technologies Ltd"


def test_filter_jobs_empty_input():
    assert filter_jobs([], SPONSOR_NAMES) == []


def test_filter_jobs_respects_threshold():
    # "Xyz Corp" won't match anything at 85% threshold
    jobs = [{
        "title": "CEO",
        "company": "Xyz Corp",
        "location": "London",
        "salary": "",
        "description": "",
        "url": "https://example.com/4",
        "source": "Reed",
    }]
    assert filter_jobs(jobs, SPONSOR_NAMES, threshold=85) == []
