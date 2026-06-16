import json
import pytest
from unittest.mock import MagicMock, patch


def _make_job(idx, title="Operations Director", score=4):
    return {
        "title": title,
        "company": "NHS Trust",
        "location": "Bristol",
        "salary": "£75,000",
        "description": "Senior management role.",
        "url": f"https://example.com/{idx}",
        "source": "Reed",
        "sponsor_name": "NHS Trust",
    }


def _make_plan():
    return {
        "candidate_qualifications": ["PRINCE2 Practitioner"],
        "evaluator_notes": "Strong management background.",
        "nhs_band_floor": {"default": "8a", "london_remote_exception": "7"},
    }


def _make_profile():
    return {
        "seniority": "Senior",
        "employment_type": ["full-time"],
    }


def _make_scored_response(jobs):
    return [
        {
            "job_index": i,
            "score": 4,
            "score_breakdown": {
                "role_type": 5,
                "seniority": 4,
                "salary_band": 4,
                "employment_type": 5,
                "qualifications": 3,
            },
            "reasoning": "Strong management role.",
        }
        for i in range(len(jobs))
    ]


def test_evaluate_returns_scored_jobs(mocker):
    jobs = [_make_job(0), _make_job(1)]
    response_data = _make_scored_response(jobs)

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(response_data))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("job_evaluator.anthropic.Anthropic", return_value=mock_client)

    from job_evaluator import evaluate
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        result = evaluate(jobs, _make_plan(), _make_profile(), 60000)

    assert len(result) == 2
    assert result[0]["score"] == 4
    assert "score_breakdown" in result[0]
    assert "reasoning" in result[0]
    assert result[0]["title"] == "Operations Director"


def test_evaluate_preserves_original_job_fields(mocker):
    jobs = [_make_job(0)]
    response_data = _make_scored_response(jobs)

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(response_data))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("job_evaluator.anthropic.Anthropic", return_value=mock_client)

    from job_evaluator import evaluate
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        result = evaluate(jobs, _make_plan(), _make_profile(), 60000)

    assert result[0]["url"] == "https://example.com/0"
    assert result[0]["sponsor_name"] == "NHS Trust"


def test_evaluate_returns_empty_list_for_empty_input():
    from job_evaluator import evaluate
    result = evaluate([], _make_plan(), _make_profile(), 60000)
    assert result == []


def test_evaluate_returns_jobs_unscored_on_api_failure(mocker):
    jobs = [_make_job(0)]
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")
    mocker.patch("job_evaluator.anthropic.Anthropic", return_value=mock_client)

    from job_evaluator import evaluate
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        result = evaluate(jobs, _make_plan(), _make_profile(), 60000)

    assert len(result) == 1
    assert result[0]["title"] == "Operations Director"
    assert "score" not in result[0]


def test_evaluate_returns_jobs_unscored_on_invalid_json(mocker):
    jobs = [_make_job(0)]
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="not json {{")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("job_evaluator.anthropic.Anthropic", return_value=mock_client)

    from job_evaluator import evaluate
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        result = evaluate(jobs, _make_plan(), _make_profile(), 60000)

    assert len(result) == 1
    assert "score" not in result[0]
