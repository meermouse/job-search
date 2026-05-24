import json
import pytest
from unittest.mock import MagicMock
from linkedin_parser import fetch_profile, analyse_profile, _profile_id_from_url


# --- _profile_id_from_url ---

def test_profile_id_from_standard_url():
    assert _profile_id_from_url("https://www.linkedin.com/in/jane-doe") == "jane-doe"


def test_profile_id_from_url_with_trailing_slash():
    assert _profile_id_from_url("https://www.linkedin.com/in/jane-doe/") == "jane-doe"


def test_profile_id_from_url_with_query_string():
    assert _profile_id_from_url("https://www.linkedin.com/in/jane-doe?trk=nav") == "jane-doe"


def test_profile_id_raises_on_invalid_url():
    with pytest.raises(ValueError, match="Invalid LinkedIn profile URL"):
        _profile_id_from_url("https://www.linkedin.com/company/acme")


# --- fetch_profile ---

def _mock_linkedin(mocker, profile=None):
    mocker.patch.dict("os.environ", {
        "LINKEDIN_LI_AT": "test-li-at-cookie",
        "LINKEDIN_JSESSIONID": "test-jsessionid-cookie",
    })
    mock_api = MagicMock()
    mock_api.get_profile.return_value = profile or {"firstName": "Jane", "lastName": "Doe"}
    mocker.patch("linkedin_parser.Linkedin", return_value=mock_api)
    return mock_api


def test_fetch_profile_returns_profile_dict(mocker):
    expected = {"firstName": "Jane", "lastName": "Doe", "headline": "Operations Director"}
    mock_api = _mock_linkedin(mocker, profile=expected)

    result = fetch_profile("https://www.linkedin.com/in/jane-doe")

    assert result == expected
    mock_api.get_profile.assert_called_once_with("jane-doe")


def test_fetch_profile_raises_when_credentials_missing(mocker):
    mocker.patch.dict("os.environ", {}, clear=True)
    with pytest.raises(RuntimeError, match="LINKEDIN_LI_AT and LINKEDIN_JSESSIONID"):
        fetch_profile("https://www.linkedin.com/in/jane-doe")


def test_fetch_profile_raises_on_invalid_url(mocker):
    _mock_linkedin(mocker)
    with pytest.raises(ValueError, match="Invalid LinkedIn profile URL"):
        fetch_profile("https://www.linkedin.com/company/acme")


def test_fetch_profile_raises_on_api_error(mocker):
    mock_api = _mock_linkedin(mocker)
    mock_api.get_profile.side_effect = Exception("API error")
    with pytest.raises(Exception, match="API error"):
        fetch_profile("https://www.linkedin.com/in/jane-doe")


# --- analyse_profile ---

_SAMPLE_PROFILE = {
    "firstName": "Jane",
    "lastName": "Doe",
    "headline": "Operations Director | Strategy",
    "experience": [{"title": "Operations Director", "companyName": "ACME Corp"}],
    "skills": [{"name": "Strategy"}, {"name": "Stakeholder Management"}, {"name": "Budget Control"}],
}

_CLAUDE_RESPONSE = {
    "job_titles": ["Operations Director", "Business Manager"],
    "search_queries": ["Operations Director NHS", "Business Manager Strategy"],
}


def test_analyse_profile_returns_structured_data(mocker):
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(_CLAUDE_RESPONSE))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("linkedin_parser.anthropic.Anthropic", return_value=mock_client)

    result = analyse_profile(_SAMPLE_PROFILE)

    assert result["name"] == "Jane Doe"
    assert result["headline"] == "Operations Director | Strategy"
    assert result["current_position"] == "Operations Director at ACME Corp"
    assert result["skills"] == ["Strategy", "Stakeholder Management", "Budget Control"]
    assert result["job_titles"] == ["Operations Director", "Business Manager"]
    assert result["search_queries"] == ["Operations Director NHS", "Business Manager Strategy"]


def test_analyse_profile_extracts_fields_without_claude(mocker):
    """name, headline, current_position and skills come from the dict — not Claude."""
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(_CLAUDE_RESPONSE))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("linkedin_parser.anthropic.Anthropic", return_value=mock_client)

    result = analyse_profile(_SAMPLE_PROFILE)

    # These must come from the profile dict, not Claude
    assert result["name"] == "Jane Doe"
    assert result["current_position"] == "Operations Director at ACME Corp"
    assert "Strategy" in result["skills"]


def test_analyse_profile_raises_when_api_key_missing(mocker):
    mocker.patch.dict("os.environ", {}, clear=True)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY is not set"):
        analyse_profile(_SAMPLE_PROFILE)


def test_analyse_profile_raises_on_api_error(mocker):
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API unavailable")
    mocker.patch("linkedin_parser.anthropic.Anthropic", return_value=mock_client)
    with pytest.raises(Exception, match="API unavailable"):
        analyse_profile(_SAMPLE_PROFILE)


def test_analyse_profile_handles_empty_experience(mocker):
    mocker.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(_CLAUDE_RESPONSE))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mocker.patch("linkedin_parser.anthropic.Anthropic", return_value=mock_client)

    result = analyse_profile({"firstName": "Jane", "lastName": "Doe"})

    assert result["name"] == "Jane Doe"
    assert result["current_position"] == ""
    assert result["skills"] == []
