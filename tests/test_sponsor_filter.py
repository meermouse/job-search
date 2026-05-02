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
