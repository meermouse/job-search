import json
import os


def load_dismissed_urls(path: str = "dismissed_jobs.json") -> set[str]:
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        data = json.load(f)
    return set(data.get("dismissed_urls", []))


def save_dismissed_urls(urls: set[str], path: str = "dismissed_jobs.json") -> None:
    with open(path, "w") as f:
        json.dump({"dismissed_urls": sorted(urls)}, f, indent=2)


def load_today_jobs(path: str = "today_jobs.json") -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def save_today_jobs(
    strong: list[dict],
    worth_a_look: list[dict],
    near_misses: list[dict],
    today: str,
    path: str = "today_jobs.json",
) -> None:
    with open(path, "w") as f:
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
