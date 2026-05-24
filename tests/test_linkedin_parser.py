import json
import pytest
from unittest.mock import MagicMock
from linkedin_parser import analyse_profile

_SAMPLE_TEXT = """\
Jane Doe
Operations Director | Strategy | Stakeholder Management
Operations Director at ACME Corp
Skills: Strategy, Stakeholder Management, Budget Control, Change Management
"""

_CLAUDE_RESPONSE = {
    "name": "Jane Doe",
    "headline": "Operations Director | Strategy",
    "current_position": "Operations Director at ACME Corp",
    "skills": ["Strategy", "Stakeholder Management", "Budget Control"],
    "job_titles": ["Operations Director", "Business Manager"],
    "search_queries": ["Operations Director NHS", "Business Manager Strategy"],
}


def _mock_claude(mocker, response=None):
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(response or _CLAUDE_RESPONSE))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("linkedin_parser.anthropic.Anthropic", return_value=mock_client)
    return mock_client


def test_analyse_profile_returns_structured_data(mocker):
    mock_client = _mock_claude(mocker)

    result = analyse_profile(_SAMPLE_TEXT)

    assert result["name"] == "Jane Doe"
    assert result["headline"] == "Operations Director | Strategy"
    assert result["current_position"] == "Operations Director at ACME Corp"
    assert result["skills"] == ["Strategy", "Stakeholder Management", "Budget Control"]
    assert result["job_titles"] == ["Operations Director", "Business Manager"]
    assert result["search_queries"] == ["Operations Director NHS", "Business Manager Strategy"]
    mock_client.messages.create.assert_called_once()


def test_analyse_profile_raises_when_api_key_missing(mocker):
    mocker.patch.dict("os.environ", {}, clear=True)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not set"):
        analyse_profile(_SAMPLE_TEXT)


def test_analyse_profile_raises_on_empty_text(mocker):
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    with pytest.raises(ValueError, match="Profile text is empty"):
        analyse_profile("   ")


def test_analyse_profile_raises_on_api_error(mocker):
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API unavailable")
    mocker.patch("linkedin_parser.anthropic.Anthropic", return_value=mock_client)
    with pytest.raises(Exception, match="API unavailable"):
        analyse_profile(_SAMPLE_TEXT)


def test_analyse_profile_strips_code_fences(mocker):
    fenced = "```json\n" + json.dumps(_CLAUDE_RESPONSE) + "\n```"
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=fenced)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("linkedin_parser.anthropic.Anthropic", return_value=mock_client)

    result = analyse_profile(_SAMPLE_TEXT)

    assert result["name"] == "Jane Doe"
