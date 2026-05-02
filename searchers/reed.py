import logging
import os
import requests

logger = logging.getLogger(__name__)
_BASE_URL = "https://www.reed.co.uk/api/1.0/search"


def search(queries: list[str], location: str, min_salary: int) -> list[dict]:
    api_key = os.environ["REED_API_KEY"]
    jobs = []
    for query in queries:
        try:
            response = requests.get(
                _BASE_URL,
                auth=(api_key, ""),
                params={
                    "keywords": query,
                    "locationName": location,
                    "minimumSalary": min_salary,
                    "resultsToTake": 100,
                },
                timeout=30,
            )
            response.raise_for_status()
            for r in response.json().get("results", []):
                min_s = r.get("minimumSalary")
                max_s = r.get("maximumSalary")
                salary = f"£{min_s:,.0f}–£{max_s:,.0f}" if min_s and max_s else ""
                jobs.append({
                    "title": r.get("jobTitle", ""),
                    "company": r.get("employerName", ""),
                    "location": r.get("locationName", ""),
                    "salary": salary,
                    "description": str(r.get("jobDescription", ""))[:500],
                    "url": r.get("jobUrl", ""),
                    "source": "Reed",
                })
        except Exception as exc:
            logger.warning("Reed search failed for query '%s': %s", query, exc)
    return jobs
