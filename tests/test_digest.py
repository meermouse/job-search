import yaml
import pytest
from unittest.mock import patch


def test_load_config_returns_expected_keys(tmp_path):
    from digest import load_config

    cfg = {
        "search_queries": ["Data Engineer Bristol"],
        "location": "Bristol",
        "min_salary": 60000,
        "recipient_email": "test@example.com",
    }
    config_file = tmp_path / "digest_config.yaml"
    config_file.write_text(yaml.dump(cfg))

    result = load_config(str(config_file))

    assert result["search_queries"] == ["Data Engineer Bristol"]
    assert result["location"] == "Bristol"
    assert result["min_salary"] == 60000
    assert result["recipient_email"] == "test@example.com"


def _make_job(url, source="Reed"):
    return {
        "title": "Dev",
        "company": "Acme",
        "url": url,
        "location": "Bristol",
        "salary": "",
        "description": "",
        "source": source,
    }


def test_collect_jobs_deduplicates_by_url():
    from digest import collect_jobs

    def fake_streaming(queries, location, min_salary, distance=50, platforms=None):
        yield "Reed", [_make_job("http://example.com/1")], None
        yield "LinkedIn + Indeed", [_make_job("http://example.com/1", "LinkedIn + Indeed")], None
        yield "NHS Jobs", [_make_job("http://example.com/2", "NHS Jobs")], None

    with patch("digest.search_all_streaming", fake_streaming):
        result = collect_jobs(["query"], "Bristol", 60000)

    assert len(result) == 2
    assert {j["url"] for j in result} == {"http://example.com/1", "http://example.com/2"}


def test_collect_jobs_handles_platform_errors():
    from digest import collect_jobs

    def fake_streaming(queries, location, min_salary, distance=50, platforms=None):
        yield "Reed", [_make_job("http://example.com/1")], None
        yield "LinkedIn + Indeed", [], "Connection error"

    with patch("digest.search_all_streaming", fake_streaming):
        result = collect_jobs(["query"], "Bristol", 60000)

    assert len(result) == 1
