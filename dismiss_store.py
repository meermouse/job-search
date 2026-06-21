import base64
import json
import os
import tempfile

import requests


def _github_headers() -> dict:
    return {
        "Authorization": f"token {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github.v3+json",
    }


def _github_get_file(repo: str, path: str) -> tuple[str | None, str | None]:
    """Return (decoded_content, sha) or (None, None) if the file doesn't exist."""
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    r = requests.get(url, headers=_github_headers(), timeout=10)
    if r.status_code == 404:
        return None, None
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"]).decode()
    return content, data["sha"]


def _github_put_file(
    repo: str, path: str, content: str, sha: str | None, message: str
) -> None:
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    payload: dict = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(url, json=payload, headers=_github_headers(), timeout=10)
    r.raise_for_status()


def load_dismissed_urls(path: str = "dismissed_jobs.json") -> set[str]:
    github_token = os.environ.get("GITHUB_TOKEN")
    github_repo = os.environ.get("GITHUB_REPO")

    if github_token and github_repo:
        try:
            content, _ = _github_get_file(github_repo, path)
            if content is None:
                return set()
            data = json.loads(content)
            return set(data.get("dismissed_urls", []))
        except Exception:
            return set()

    if not os.path.exists(path):
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
        return set(data.get("dismissed_urls", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_dismissed_urls(urls: set[str], path: str = "dismissed_jobs.json") -> None:
    github_token = os.environ.get("GITHUB_TOKEN")
    github_repo = os.environ.get("GITHUB_REPO")

    if github_token and github_repo:
        content = json.dumps({"dismissed_urls": sorted(urls)}, indent=2)
        _, sha = _github_get_file(github_repo, path)
        _github_put_file(
            github_repo, path, content, sha,
            "chore: update dismissed jobs [skip ci]",
        )
        return

    dir_ = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp") as f:
        json.dump({"dismissed_urls": sorted(urls)}, f, indent=2)
        tmp = f.name
    os.replace(tmp, path)


def load_today_jobs(path: str = "today_jobs.json") -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_today_jobs(
    strong: list[dict],
    worth_a_look: list[dict],
    near_misses: list[dict],
    today: str,
    path: str = "today_jobs.json",
) -> None:
    dir_ = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp") as f:
        json.dump(
            {
                "date": today,
                "strong": strong,
                "worth_a_look": worth_a_look,
                "near_misses": near_misses,
            },
            f,
            indent=2,
        )
        tmp = f.name
    os.replace(tmp, path)
