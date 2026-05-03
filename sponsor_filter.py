import csv
import io
import logging
import os

import requests
from rapidfuzz import process, fuzz

logger = logging.getLogger(__name__)

_DEFAULT_URL = os.environ.get(
    "SPONSOR_CSV_URL",
    "https://assets.publishing.service.gov.uk/media/69f47183ab602a88957eefa6/2026-05-01_-_Worker_and_Temporary_Worker.csv",
)
_CACHE_PATH = "sponsor_cache.csv"


def load_sponsor_names(csv_url: str = _DEFAULT_URL, cache_path: str = _CACHE_PATH) -> list[str]:
    """Return employer names licensed for the Worker route (Skilled Worker visa)."""
    try:
        response = requests.get(csv_url, timeout=30)
        response.raise_for_status()
        csv_text = response.text
        print(f"[DEBUG] sponsor HTTP status={response.status_code} content-type={response.headers.get('Content-Type')} len={len(csv_text)}")
        print(f"[DEBUG] sponsor response preview: {repr(csv_text[:300])}")
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(csv_text)
    except Exception as exc:
        print(f"[DEBUG] sponsor HTTP failed: {exc}")
        if not os.path.exists(cache_path):
            raise RuntimeError(
                "Failed to download sponsor CSV and no local cache found. "
                "Check your internet connection or update SPONSOR_CSV_URL in .env."
            )
        with open(cache_path, encoding="utf-8") as f:
            csv_text = f.read()

    reader = csv.DictReader(io.StringIO(csv_text))
    print(f"[DEBUG] sponsor CSV columns: {reader.fieldnames}")
    names = [
        row["Organisation Name"] for row in reader
        if "Worker" in row.get("Route", "") and "Temporary" not in row.get("Route", "")
    ]
    print(f"[DEBUG] sponsor names found: {len(names)}, sample: {names[:3]}")
    if not names:
        logger.warning(
            "Sponsor CSV parsed but returned 0 Worker-route entries — "
            "check the CSV URL or column headers"
        )
    return names


def filter_jobs(jobs: list[dict], sponsor_names: list[str], threshold: int = 85) -> list[dict]:
    """Return jobs whose company fuzzy-matches a Worker-route sponsor, adding sponsor_name field."""
    result = []
    for job in jobs:
        match = process.extractOne(
            job["company"],
            sponsor_names,
            scorer=fuzz.token_sort_ratio,
        )
        if match and match[1] >= threshold:
            result.append({**job, "sponsor_name": match[0]})
    return result
