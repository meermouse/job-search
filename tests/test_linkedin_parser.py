import json
import pytest
from unittest.mock import MagicMock
from linkedin_parser import analyse_profile


def test_analyse_profile_returns_structured_data(mocker):
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    expected = {
        "name": "Jane Doe",
        "headline": "Operations Director | Strategy",
        "current_position": "Operations Director at ACME Corp",
        "job_titles": ["Operations Director", "Business Manager"],
        "skills": ["Strategy", "Stakeholder Management", "Budget Control"],
        "search_queries": ["Operations Director NHS", "Business Manager Strategy"],
    }
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(expected))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("linkedin_parser.anthropic.Anthropic", return_value=mock_client)

    result = analyse_profile("Jane Doe\nOperations Director at ACME Corp\nStrategy, NHS...")

    assert result == expected


def test_analyse_profile_raises_when_api_key_missing(mocker):
    mocker.patch.dict("os.environ", {}, clear=True)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not set"):
        analyse_profile("Some profile text")


def test_analyse_profile_raises_on_api_error(mocker):
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API unavailable")
    mocker.patch("linkedin_parser.anthropic.Anthropic", return_value=mock_client)

    with pytest.raises(Exception, match="API unavailable"):
        analyse_profile("Some profile text")
