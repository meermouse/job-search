import logging
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
_BASE_URL = "https://www.jobs.nhs.uk/candidate/search/results"
_NHS_HOST = "https://www.jobs.nhs.uk"


def search(queries: list[str], location: str, min_salary: int) -> list[dict]:
    jobs = []
    seen_urls: set[str] = set()
    for query in queries:
        try:
            response = requests.get(
                _BASE_URL,
                params={"keyword": query, "location": location, "distance": 15, "language": "en"},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=30,
            )
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            for card in soup.select("[data-test='search-result']"):
                title_el = card.select_one("[data-test='job-title']")
                employer_el = card.select_one("[data-test='employer-name']")
                location_el = card.select_one("[data-test='job-location']")
                salary_el = card.select_one("[data-test='job-salary']")
                link_el = title_el if title_el and title_el.name == "a" else card.select_one("a[href]")
                if not title_el or not link_el:
                    continue
                href = link_el.get("href", "")
                if not href:
                    continue
                url = href if href.startswith("http") else _NHS_HOST + href
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                jobs.append({
                    "title": title_el.get_text(strip=True),
                    "company": employer_el.get_text(strip=True) if employer_el else "",
                    "location": location_el.get_text(strip=True) if location_el else "",
                    "salary": salary_el.get_text(strip=True) if salary_el else "",
                    "description": "",
                    "url": url,
                    "source": "NHS Jobs",
                })
        except Exception as exc:
            logger.warning("NHS Jobs search failed for query '%s': %s", query, exc)
    return jobs
