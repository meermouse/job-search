import json
import os
import tempfile


def load_dismissed_urls(path: str = "dismissed_jobs.json") -> set[str]:
    if not os.path.exists(path):
        return set()
    try:
        with open(path) as f:
            data = json.load(f)
        return set(data.get("dismissed_urls", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_dismissed_urls(urls: set[str], path: str = "dismissed_jobs.json") -> None:
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
