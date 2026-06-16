import json
import pytest
from unittest.mock import MagicMock, patch


SAMPLE_PLAN = {
    "queries": ["Digital Transformation Manager Bristol"],
    "locations": ["Bristol"],
    "exclusion_keywords": ["nurse", "clinical", "ward"],
    "employment_type_exclusions": ["part-time", "part time", "contract", "fixed term", "fixed-term", "temporary"],
    "nhs_band_floor": {"default": "8a", "london_remote_exception": "7"},
    "candidate_qualifications": ["PRINCE2 Practitioner"],
    "evaluator_notes": "Strong management background.",
}


def test_create_plan_returns_valid_plan(mocker):
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(SAMPLE_PLAN))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("job_planner.anthropic.Anthropic", return_value=mock_client)

    from job_planner import create_plan
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        plan = create_plan(
            {"name": "Jie", "target_roles": ["Business Manager"], "skills": ["Digital Transformation"],
             "current_role": "NHS", "about": "", "seniority": "Senior", "industry": "NHS",
             "previous_roles": [], "open_to": [], "qualifications": [], "employment_type": ["full-time"]},
            "Bristol",
            60000,
        )

    assert plan["queries"] == ["Digital Transformation Manager Bristol"]
    assert plan["nhs_band_floor"]["default"] == "8a"
    assert plan["nhs_band_floor"]["london_remote_exception"] == "7"
    assert "nurse" in plan["exclusion_keywords"]
    assert "contract" in plan["employment_type_exclusions"]


def test_create_plan_raises_on_invalid_json(mocker):
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text="not valid json {{")]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("job_planner.anthropic.Anthropic", return_value=mock_client)

    from job_planner import create_plan
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
        with pytest.raises(RuntimeError, match="invalid JSON"):
            create_plan({}, "Bristol", 60000)


def test_validate_plan_raises_on_missing_keys():
    from job_planner import _validate_plan
    with pytest.raises(RuntimeError, match="missing required keys"):
        _validate_plan({"queries": ["something"]})


def test_validate_plan_raises_on_empty_queries():
    from job_planner import _validate_plan
    plan = {**SAMPLE_PLAN, "queries": []}
    with pytest.raises(RuntimeError, match="no queries"):
        _validate_plan(plan)


def test_validate_plan_passes_with_valid_plan():
    from job_planner import _validate_plan
    _validate_plan(SAMPLE_PLAN)  # should not raise
