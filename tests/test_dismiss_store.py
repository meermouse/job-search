import base64
import json
from unittest.mock import patch, MagicMock


def test_load_dismissed_urls_returns_empty_set_when_file_missing(tmp_path):
    from dismiss_store import load_dismissed_urls
    result = load_dismissed_urls(str(tmp_path / "dismissed_jobs.json"))
    assert result == set()


def test_load_dismissed_urls_returns_urls_from_file(tmp_path):
    from dismiss_store import load_dismissed_urls
    path = tmp_path / "dismissed_jobs.json"
    path.write_text(json.dumps({"dismissed_urls": ["https://a.com/1", "https://b.com/2"]}))
    result = load_dismissed_urls(str(path))
    assert result == {"https://a.com/1", "https://b.com/2"}


def test_load_dismissed_urls_handles_empty_list(tmp_path):
    from dismiss_store import load_dismissed_urls
    path = tmp_path / "dismissed_jobs.json"
    path.write_text(json.dumps({"dismissed_urls": []}))
    result = load_dismissed_urls(str(path))
    assert result == set()


def test_save_dismissed_urls_writes_sorted_list(tmp_path):
    from dismiss_store import save_dismissed_urls
    path = tmp_path / "dismissed_jobs.json"
    save_dismissed_urls({"https://b.com/2", "https://a.com/1"}, str(path))
    data = json.loads(path.read_text())
    assert data == {"dismissed_urls": ["https://a.com/1", "https://b.com/2"]}


def test_save_then_load_dismissed_urls_roundtrip(tmp_path):
    from dismiss_store import save_dismissed_urls, load_dismissed_urls
    path = str(tmp_path / "dismissed_jobs.json")
    urls = {"https://example.com/1", "https://example.com/2"}
    save_dismissed_urls(urls, path)
    assert load_dismissed_urls(path) == urls


def test_load_today_jobs_returns_none_when_file_missing(tmp_path):
    from dismiss_store import load_today_jobs
    result = load_today_jobs(str(tmp_path / "today_jobs.json"))
    assert result is None


def test_load_today_jobs_returns_dict(tmp_path):
    from dismiss_store import load_today_jobs
    path = tmp_path / "today_jobs.json"
    payload = {"date": "21 June 2026", "strong": [], "worth_a_look": [], "near_misses": []}
    path.write_text(json.dumps(payload))
    result = load_today_jobs(str(path))
    assert result == payload


def test_save_today_jobs_writes_correct_structure(tmp_path):
    from dismiss_store import save_today_jobs
    path = str(tmp_path / "today_jobs.json")
    strong = [{"title": "Manager", "url": "https://a.com/1"}]
    save_today_jobs(strong, [], [], "21 June 2026", path)
    data = json.loads((tmp_path / "today_jobs.json").read_text())
    assert data["date"] == "21 June 2026"
    assert data["strong"] == strong
    assert data["worth_a_look"] == []
    assert data["near_misses"] == []


def test_save_today_jobs_roundtrip(tmp_path):
    from dismiss_store import save_today_jobs, load_today_jobs
    path = str(tmp_path / "today_jobs.json")
    strong = [{"title": "A", "url": "https://a.com"}]
    near = [{"title": "B", "url": "https://b.com"}]
    save_today_jobs(strong, [], near, "21 June 2026", path)
    result = load_today_jobs(path)
    assert result["strong"] == strong
    assert result["near_misses"] == near


def test_save_dismissed_urls_is_atomic(tmp_path):
    from dismiss_store import save_dismissed_urls
    path = tmp_path / "dismissed_jobs.json"
    # Write a sentinel file at the path first
    path.write_text("sentinel")
    urls = {"https://a.com/1", "https://b.com/2"}
    save_dismissed_urls(urls, str(path))
    # The atomic replace must have written the correct JSON (not the sentinel)
    data = json.loads(path.read_text())
    assert data == {"dismissed_urls": ["https://a.com/1", "https://b.com/2"]}


def test_load_dismissed_urls_returns_empty_on_corrupt_file(tmp_path):
    from dismiss_store import load_dismissed_urls
    path = tmp_path / "dismissed_jobs.json"
    path.write_bytes(b"not json")
    result = load_dismissed_urls(str(path))
    assert result == set()


def test_load_today_jobs_returns_none_on_corrupt_file(tmp_path):
    from dismiss_store import load_today_jobs
    path = tmp_path / "today_jobs.json"
    path.write_bytes(b"not json")
    result = load_today_jobs(str(path))
    assert result is None


def test_load_dismissed_urls_uses_github_api_when_env_set():
    from dismiss_store import load_dismissed_urls
    payload = {"dismissed_urls": ["https://a.com/1"]}
    # GitHub API returns base64-encoded content (sometimes with embedded newlines)
    encoded = base64.b64encode(json.dumps(payload).encode()).decode() + "\n"
    get_mock = MagicMock()
    get_mock.status_code = 200
    get_mock.json.return_value = {"content": encoded, "sha": "abc123"}
    with patch.dict("os.environ", {"GITHUB_TOKEN": "tok", "GITHUB_REPO": "user/repo"}):
        with patch("requests.get", return_value=get_mock):
            result = load_dismissed_urls("dismissed_jobs.json")
    assert result == {"https://a.com/1"}


def test_load_dismissed_urls_returns_empty_when_github_404():
    from dismiss_store import load_dismissed_urls
    get_mock = MagicMock()
    get_mock.status_code = 404
    with patch.dict("os.environ", {"GITHUB_TOKEN": "tok", "GITHUB_REPO": "user/repo"}):
        with patch("requests.get", return_value=get_mock):
            result = load_dismissed_urls("dismissed_jobs.json")
    assert result == set()


def test_save_dismissed_urls_uses_github_api_when_env_set():
    from dismiss_store import save_dismissed_urls
    # GET returns 404 — file doesn't exist yet, so no sha in the PUT body
    get_mock = MagicMock()
    get_mock.status_code = 404
    put_mock = MagicMock()
    put_mock.raise_for_status.return_value = None
    with patch.dict("os.environ", {"GITHUB_TOKEN": "tok", "GITHUB_REPO": "user/repo"}):
        with patch("requests.get", return_value=get_mock):
            with patch("requests.put", return_value=put_mock) as mock_put:
                save_dismissed_urls({"https://example.com/1"})
    mock_put.assert_called_once()
    sent = mock_put.call_args.kwargs["json"]
    decoded = json.loads(base64.b64decode(sent["content"]).decode())
    assert decoded == {"dismissed_urls": ["https://example.com/1"]}
    assert "[skip ci]" in sent["message"]
    assert sent.get("sha") is None
