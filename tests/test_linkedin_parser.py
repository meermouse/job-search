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


from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from linkedin_parser import scrape_profile


def _mock_playwright(mocker, *, page_url="https://www.linkedin.com/in/janedoe", goto_side_effect=None):
    """Helper that sets up a full Playwright context manager mock."""
    mocker.patch.dict("os.environ", {"LINKEDIN_SESSION_COOKIE": "test-session-cookie"})

    mock_page = MagicMock()
    mock_page.url = page_url
    if goto_side_effect is not None:
        mock_page.goto.side_effect = goto_side_effect
    mock_page.inner_text.return_value = "Jane Doe\nOperations Director"

    mock_context = MagicMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = MagicMock()
    mock_browser.new_context.return_value = mock_context

    mock_pw = MagicMock()
    mock_pw.chromium.launch.return_value = mock_browser

    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_pw
    mock_cm.__exit__.return_value = False

    mocker.patch("linkedin_parser.sync_playwright", return_value=mock_cm)
    return mock_page, mock_browser


def test_scrape_profile_returns_page_text(mocker):
    _mock_playwright(mocker)
    result = scrape_profile("https://www.linkedin.com/in/janedoe")
    assert "Jane Doe" in result


def test_scrape_profile_raises_on_authwall(mocker):
    _mock_playwright(mocker, page_url="https://www.linkedin.com/authwall?trk=bf_...")
    with pytest.raises(ValueError, match="session cookie"):
        scrape_profile("https://www.linkedin.com/in/janedoe")


def test_scrape_profile_raises_on_login_redirect(mocker):
    _mock_playwright(mocker, page_url="https://www.linkedin.com/login?session_redirect=...")
    with pytest.raises(ValueError, match="session cookie"):
        scrape_profile("https://www.linkedin.com/in/janedoe")


def test_scrape_profile_raises_on_timeout(mocker):
    _mock_playwright(mocker, goto_side_effect=PlaywrightTimeoutError("30000ms exceeded"))
    with pytest.raises(TimeoutError, match="took too long"):
        scrape_profile("https://www.linkedin.com/in/janedoe")


def test_scrape_profile_closes_browser_on_error(mocker):
    _, mock_browser = _mock_playwright(
        mocker, page_url="https://www.linkedin.com/authwall?trk=..."
    )
    with pytest.raises(ValueError):
        scrape_profile("https://www.linkedin.com/in/janedoe")
    mock_browser.close.assert_called_once()


def test_scrape_profile_propagates_non_timeout_errors(mocker):
    _mock_playwright(mocker, goto_side_effect=ConnectionError("Network unreachable"))
    with pytest.raises(ConnectionError, match="Network unreachable"):
        scrape_profile("https://www.linkedin.com/in/janedoe")


def test_scrape_profile_raises_when_session_cookie_missing(mocker):
    mocker.patch.dict("os.environ", {}, clear=True)
    with pytest.raises(RuntimeError, match="LINKEDIN_SESSION_COOKIE is not set"):
        scrape_profile("https://www.linkedin.com/in/janedoe")
