import os
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


def test_collect_jobs_skips_jobs_with_no_url():
    from digest import collect_jobs

    def fake_streaming(queries, location, min_salary, distance=50, platforms=None):
        yield "Reed", [_make_job(None), _make_job("http://example.com/1")], None

    with patch("digest.search_all_streaming", fake_streaming):
        result = collect_jobs(["query"], "Bristol", 60000)

    assert len(result) == 1
    assert result[0]["url"] == "http://example.com/1"


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


def test_format_email_html_escapes_special_characters():
    from digest import format_email_html

    jobs = [
        {
            "title": "Senior & Junior Dev",
            "company": "<Acme>",
            "location": "Bristol",
            "salary": "",
            "source": "Reed",
            "url": "https://example.com/job/1",
            "sponsor_name": "",
        }
    ]
    html_out = format_email_html(jobs, "Good results.", "18 May 2026")

    assert "Senior &amp; Junior Dev" in html_out
    assert "&lt;Acme&gt;" in html_out
    assert "<Acme>" not in html_out


def test_send_email_logs_in_and_sends():
    from digest import send_email

    mock_server = MagicMock()

    with patch("digest.smtplib.SMTP_SSL") as mock_ssl:
        mock_ssl.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_ssl.return_value.__exit__ = MagicMock(return_value=False)
        send_email(
            subject="Test digest",
            html_body="<p>hello</p>",
            recipient="jie@example.com",
            gmail_user="sender@gmail.com",
            gmail_app_password="app-password",
        )

    mock_server.login.assert_called_once_with("sender@gmail.com", "app-password")
    mock_server.sendmail.assert_called_once()
    call_args = mock_server.sendmail.call_args
    assert call_args[0][0] == "sender@gmail.com"
    assert call_args[0][1] == "jie@example.com"
    assert "<p>hello</p>" in call_args[0][2]


def test_main_sends_email_when_jobs_found():
    from digest import main

    config = {
        "search_queries": ["Data Engineer Bristol"],
        "location": "Bristol",
        "min_salary": 60000,
        "recipient_email": "jie@example.com",
    }
    filtered_jobs = [
        {
            "title": "Data Engineer",
            "company": "NHS",
            "url": "http://example.com/1",
            "location": "Bristol",
            "salary": "£65,000",
            "description": "",
            "source": "NHS Jobs",
            "sponsor_name": "NHS Digital",
        }
    ]

    with patch("digest.load_config", return_value=config), \
         patch("digest.collect_jobs", return_value=filtered_jobs), \
         patch("digest.sponsor_filter.load_sponsor_names", return_value=["NHS Digital"]), \
         patch("digest.sponsor_filter.filter_jobs", return_value=filtered_jobs), \
         patch("digest.analyse_results", return_value="Great match!"), \
         patch("digest.format_email_html", return_value="<html>content</html>"), \
         patch("digest.send_email") as mock_send, \
         patch.dict("os.environ", {"GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw", "RECIPIENT_EMAIL": "jie@example.com"}):
        main()

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args[1]
    assert call_kwargs["recipient"] == "jie@example.com"
    assert "1 match" in call_kwargs["subject"]


def test_main_sends_email_when_no_jobs_found():
    from digest import main

    config = {
        "search_queries": ["Data Engineer Bristol"],
        "location": "Bristol",
        "min_salary": 60000,
        "recipient_email": "jie@example.com",
    }

    with patch("digest.load_config", return_value=config), \
         patch("digest.collect_jobs", return_value=[]), \
         patch("digest.sponsor_filter.load_sponsor_names", return_value=[]), \
         patch("digest.sponsor_filter.filter_jobs", return_value=[]), \
         patch("digest.analyse_results") as mock_analyse, \
         patch("digest.format_email_html", return_value="<html>no matches</html>"), \
         patch("digest.send_email") as mock_send, \
         patch.dict("os.environ", {"GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw", "RECIPIENT_EMAIL": "jie@example.com"}):
        main()

    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args[1]
    assert "0 matches" in call_kwargs["subject"]
    mock_analyse.assert_not_called()


def test_main_uses_three_phase_pipeline_when_profile_present():
    from digest import main

    config = {
        "profile": {
            "name": "Jie",
            "current_role": "Operations Director",
            "seniority": "Senior",
            "industry": "NHS",
            "skills": ["stakeholder management"],
            "previous_roles": ["Project Manager"],
            "target_roles": ["Operations Director"],
            "open_to": ["Head of Operations"],
            "qualifications": [],
            "employment_type": ["full-time"],
        },
        "location": "Bristol",
        "min_salary": 60000,
    }
    mock_plan = {
        "queries": ["Operations Director Bristol"],
        "locations": ["Bristol"],
        "exclusion_keywords": [],
        "employment_type_exclusions": [],
        "nhs_band_floor": {"default": "8a", "london_remote_exception": "7"},
        "candidate_qualifications": [],
        "evaluator_notes": "",
    }
    mock_job = {
        "title": "Operations Director",
        "company": "NHS Trust",
        "url": "https://example.com/1",
        "location": "Bristol",
        "salary": "£75,000",
        "description": "",
        "source": "Reed",
        "sponsor_name": "NHS Trust",
        "score": 4,
        "score_breakdown": {},
        "reasoning": "Strong match.",
    }

    with patch("digest.load_config", return_value=config), \
         patch("digest.job_planner.create_plan", return_value=mock_plan) as mock_planner, \
         patch("digest.search_agent.run_search_agent", return_value=([mock_job], "Searched 2 angles.", [])) as mock_agent, \
         patch("digest.job_evaluator.evaluate", return_value=[mock_job]) as mock_eval, \
         patch("digest.format_email_html", return_value="<html>") as mock_html, \
         patch("digest.send_email") as mock_send, \
         patch.dict(os.environ, {"RECIPIENT_EMAIL": "jie@example.com", "GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
        main()

    mock_planner.assert_called_once_with(config["profile"], "Bristol", 60000)
    mock_agent.assert_called_once_with(config["profile"], mock_plan, "Bristol", 60000)
    mock_eval.assert_called_once_with([mock_job], mock_plan, config["profile"], 60000)
    html_call_args = mock_html.call_args
    assert html_call_args[0][0] == [mock_job]       # strong_jobs: score 4 lands here
    assert html_call_args[0][1] == "Searched 2 angles."
    assert html_call_args[1]["worth_a_look"] == []   # no score-3 jobs
    # digest is the first send_email call; second is the filter log
    assert mock_send.call_count == 2
    digest_call = mock_send.call_args_list[0]
    assert "1 match" in digest_call[1]["subject"]


def test_main_shows_near_misses_when_no_results_pass_threshold():
    from digest import main

    config = {
        "profile": {
            "name": "Jie",
            "current_role": "Operations Director",
            "seniority": "Senior",
            "industry": "NHS",
            "skills": [],
            "previous_roles": [],
            "target_roles": [],
            "open_to": [],
            "qualifications": [],
            "employment_type": ["full-time"],
        },
        "location": "Bristol",
        "min_salary": 60000,
    }
    mock_plan = {
        "queries": [],
        "locations": ["Bristol"],
        "exclusion_keywords": [],
        "employment_type_exclusions": [],
        "nhs_band_floor": {"default": "8a", "london_remote_exception": "7"},
        "candidate_qualifications": [],
        "evaluator_notes": "",
    }

    def _make_scored(score):
        return {
            "title": "Some Role",
            "company": "NHS Trust",
            "url": f"https://example.com/{score}",
            "location": "Bristol",
            "salary": "",
            "source": "Reed",
            "sponsor_name": "NHS Trust",
            "score": score,
            "score_breakdown": {},
            "reasoning": f"Scored {score} because of poor fit.",
        }

    # All jobs score 1 or 2 — nothing passes threshold
    scored_jobs = [_make_scored(2), _make_scored(1), _make_scored(2)]

    with patch("digest.load_config", return_value=config), \
         patch("digest.job_planner.create_plan", return_value=mock_plan), \
         patch("digest.search_agent.run_search_agent", return_value=(scored_jobs, "Searched 1 angle.", [])), \
         patch("digest.job_evaluator.evaluate", return_value=scored_jobs), \
         patch("digest.format_email_html", return_value="<html>") as mock_html, \
         patch("digest.send_email"), \
         patch.dict(os.environ, {"RECIPIENT_EMAIL": "jie@example.com", "GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
        main()

    html_kwargs = mock_html.call_args[1]
    near_misses = html_kwargs["near_misses"]
    assert len(near_misses) <= 5
    assert near_misses[0]["score"] == 2   # score-2 jobs appear before score-1
    assert near_misses[-1]["score"] >= 1
    assert html_kwargs["worth_a_look"] == []


def test_main_does_not_show_near_misses_when_results_exist():
    from digest import main

    config = {
        "profile": {
            "name": "Jie",
            "current_role": "Operations Director",
            "seniority": "Senior",
            "industry": "NHS",
            "skills": [],
            "previous_roles": [],
            "target_roles": [],
            "open_to": [],
            "qualifications": [],
            "employment_type": ["full-time"],
        },
        "location": "Bristol",
        "min_salary": 60000,
    }
    mock_plan = {
        "queries": [],
        "locations": ["Bristol"],
        "exclusion_keywords": [],
        "employment_type_exclusions": [],
        "nhs_band_floor": {"default": "8a", "london_remote_exception": "7"},
        "candidate_qualifications": [],
        "evaluator_notes": "",
    }
    strong_job = {
        "title": "Senior Manager",
        "company": "NHS Trust",
        "url": "https://example.com/1",
        "location": "Bristol",
        "salary": "£70,000",
        "source": "Reed",
        "sponsor_name": "NHS Trust",
        "score": 4,
        "score_breakdown": {},
        "reasoning": "Strong fit.",
    }

    with patch("digest.load_config", return_value=config), \
         patch("digest.job_planner.create_plan", return_value=mock_plan), \
         patch("digest.search_agent.run_search_agent", return_value=([strong_job], "Searched.", [])), \
         patch("digest.job_evaluator.evaluate", return_value=[strong_job]), \
         patch("digest.format_email_html", return_value="<html>") as mock_html, \
         patch("digest.send_email"), \
         patch.dict(os.environ, {"RECIPIENT_EMAIL": "jie@example.com", "GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
        main()

    html_kwargs = mock_html.call_args[1]
    assert html_kwargs["near_misses"] == []


def test_main_uses_static_queries_when_no_profile_in_config():
    from digest import main

    config = {
        "search_queries": ["Operations Director Bristol"],
        "location": "Bristol",
        "min_salary": 60000,
    }

    with patch("digest.load_config", return_value=config), \
         patch("digest.collect_jobs", return_value=[]) as mock_collect, \
         patch("digest.sponsor_filter.load_sponsor_names", return_value=[]), \
         patch("digest.sponsor_filter.filter_jobs", return_value=[]), \
         patch("digest.format_email_html", return_value="<html>"), \
         patch("digest.send_email"), \
         patch.dict(os.environ, {"RECIPIENT_EMAIL": "jie@example.com", "GMAIL_USER": "a@gmail.com", "GMAIL_APP_PASSWORD": "pw"}):
        main()

    mock_collect.assert_called_once_with(["Operations Director Bristol"], "Bristol", 60000)
