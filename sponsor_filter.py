import csv
import io
import os
import requests

_DEFAULT_URL = os.environ.get(
    "SPONSOR_CSV_URL",
    "https://www.gov.uk/csv-preview/69f47183ab602a88957eefa6/2026-05-01_-_Worker_and_Temporary_Worker.csv",
)
_CACHE_PATH = "sponsor_cache.csv"


def load_sponsor_names(csv_url: str = _DEFAULT_URL, cache_path: str = _CACHE_PATH) -> list[str]:
    """Return employer names licensed for the Worker route (Skilled Worker visa)."""
    try:
        response = requests.get(csv_url, timeout=30)
        response.raise_for_status()
        csv_text = response.text
        with open(cache_path, "w", encoding="utf-8") as f:
            f.write(csv_text)
    except Exception:
        if not os.path.exists(cache_path):
            raise RuntimeError(
                "Failed to download sponsor CSV and no local cache found. "
                "Check your internet connection or update SPONSOR_CSV_URL in .env."
            )
        with open(cache_path, encoding="utf-8") as f:
            csv_text = f.read()

    reader = csv.DictReader(io.StringIO(csv_text))
    return [row["Organisation Name"] for row in reader if row.get("Route") == "Worker"]
