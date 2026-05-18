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


from unittest.mock import MagicMock


def test_analyse_results_calls_claude_and_returns_text():
    from digest import analyse_results

    jobs = [
        {
            "title": "Data Engineer",
            "company": "NHS",
            "location": "Bristol",
            "salary": "£65,000",
            "source": "NHS Jobs",
        }
    ]
    config = {
        "search_queries": ["Data Engineer Bristol"],
        "location": "Bristol",
        "min_salary": 60000,
    }
    mock_client = MagicMock()
    mock_client.messages.create.return_value.content = [MagicMock(text="Great match today!")]

    with patch("digest.anthropic.Anthropic", return_value=mock_client), \
         patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        result = analyse_results(jobs, config)

    assert result == "Great match today!"
    mock_client.messages.create.assert_called_once()


def test_format_email_html_contains_summary_and_jobs():
    from digest import format_email_html

    jobs = [
        {
            "title": "Data Engineer",
            "company": "NHS Digital",
            "location": "Bristol",
            "salary": "£65,000",
            "source": "NHS Jobs",
            "url": "https://example.com/job/1",
            "sponsor_name": "NHS Digital",
        }
    ]
    html = format_email_html(jobs, "Strong match today.", "18 May 2026")

    assert "Strong match today." in html
    assert "Data Engineer" in html
    assert "NHS Digital" in html
    assert "https://example.com/job/1" in html
    assert "18 May 2026" in html


def test_format_email_html_no_results_omits_table():
    from digest import format_email_html

    html = format_email_html([], "No matches today.", "18 May 2026")

    assert "No matches today." in html
    assert "<table" not in html
