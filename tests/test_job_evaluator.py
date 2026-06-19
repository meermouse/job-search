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


def test_truncate_description_short_text_unchanged():
    from job_evaluator import _truncate_description
    text = "A short description."
    assert _truncate_description(text) == text


def test_truncate_description_caps_at_word_limit():
    from job_evaluator import _truncate_description, _DESCRIPTION_WORD_LIMIT
    words = ["word"] * (_DESCRIPTION_WORD_LIMIT + 50)
    result = _truncate_description(" ".join(words))
    assert len(result.split()) == _DESCRIPTION_WORD_LIMIT + 1  # limit words + "…"
    assert result.endswith("…")


def test_evaluate_truncates_description_sent_to_api(mocker):
    from job_evaluator import evaluate, _DESCRIPTION_WORD_LIMIT
    long_desc = " ".join(["word"] * (_DESCRIPTION_WORD_LIMIT + 100))
    jobs = [{**_make_job(0), "description": long_desc}]
    response_data = _make_scored_response(jobs)

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(response_data))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("job_evaluator.anthropic.Anthropic", return_value=mock_client)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        evaluate(jobs, _make_plan(), _make_profile(), 60000)

    call_prompt = mock_client.messages.create.call_args[1]["messages"][0]["content"]
    # The full description should not appear in the prompt
    assert long_desc not in call_prompt
    # But a truncated form should
    assert "word word word" in call_prompt


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


def test_evaluate_handles_markdown_fenced_json(mocker):
    jobs = [_make_job(0)]
    response_data = _make_scored_response(jobs)
    fenced = f"```json\n{json.dumps(response_data)}\n```"

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=fenced)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("job_evaluator.anthropic.Anthropic", return_value=mock_client)

    from job_evaluator import evaluate
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        result = evaluate(jobs, _make_plan(), _make_profile(), 60000)

    assert len(result) == 1
    assert result[0]["score"] == 4


def test_evaluate_splits_large_batch_into_chunks(mocker):
    """Batches larger than _CHUNK_SIZE must result in one API call per chunk."""
    from job_evaluator import evaluate, _CHUNK_SIZE

    n_jobs = _CHUNK_SIZE + 2  # forces exactly 2 chunks
    jobs = [_make_job(i) for i in range(n_jobs)]

    def make_scored_message(n):
        msg = MagicMock()
        msg.content = [MagicMock(text=json.dumps([
            {"job_index": i, "score": 3, "score_breakdown": {}, "reasoning": "ok"}
            for i in range(n)
        ]))]
        return msg

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        make_scored_message(_CHUNK_SIZE),
        make_scored_message(2),
    ]
    mocker.patch("job_evaluator.anthropic.Anthropic", return_value=mock_client)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        result = evaluate(jobs, _make_plan(), _make_profile(), 60000)

    assert mock_client.messages.create.call_count == 2
    assert len(result) == n_jobs
    assert all(j.get("score") == 3 for j in result)


def test_evaluate_chunk_failure_leaves_remaining_chunks_scored(mocker):
    """If one chunk's API call fails, other chunks are still scored."""
    from job_evaluator import evaluate, _CHUNK_SIZE

    n_jobs = _CHUNK_SIZE + 2
    jobs = [_make_job(i) for i in range(n_jobs)]

    good_msg = MagicMock()
    good_msg.content = [MagicMock(text=json.dumps([
        {"job_index": i, "score": 4, "score_breakdown": {}, "reasoning": "good"}
        for i in range(_CHUNK_SIZE)
    ]))]

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        good_msg,
        Exception("API timeout"),
    ]
    mocker.patch("job_evaluator.anthropic.Anthropic", return_value=mock_client)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        result = evaluate(jobs, _make_plan(), _make_profile(), 60000)

    assert len(result) == n_jobs
    # First chunk scored
    assert all(j.get("score") == 4 for j in result[:_CHUNK_SIZE])
    # Second chunk unscored but present
    assert all("score" not in j for j in result[_CHUNK_SIZE:])
