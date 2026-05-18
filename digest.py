import os
import smtplib
import ssl
import logging
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
import yaml

import sponsor_filter
from searchers import search_all_streaming

logger = logging.getLogger(__name__)


def load_config(path: str = "digest_config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def collect_jobs(queries: list[str], location: str, min_salary: int) -> list[dict]:
    all_jobs: list[dict] = []
    for _platform, jobs, _error in search_all_streaming(queries, location, min_salary):
        all_jobs.extend(jobs)
    seen_urls: set[str] = set()
    deduped: list[dict] = []
    for job in all_jobs:
        if job["url"] and job["url"] not in seen_urls:
            seen_urls.add(job["url"])
            deduped.append(job)
    return deduped


def analyse_results(jobs: list[dict], config: dict) -> str:
    jobs_text = "\n".join(
        f"- {j['title']} at {j['company']} ({j['location']}) {j['salary']} [{j['source']}]"
        for j in jobs
    )
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[
            {
                "role": "user",
                "content": (
                    f"You are helping Jie, a job seeker in {config['location']} looking for roles "
                    f"with UK Skilled Worker visa sponsorship.\n\n"
                    f"Search criteria:\n"
                    f"- Queries: {', '.join(config['search_queries'])}\n"
                    f"- Location: {config['location']}\n"
                    f"- Minimum salary: £{config['min_salary']:,}\n\n"
                    f"Today's matching jobs from licensed UK visa sponsors:\n{jobs_text}\n\n"
                    f"Write a 2–4 sentence summary of today's results, then highlight 2–3 standout "
                    f"roles with a brief reason why each is a strong match. Be specific and helpful."
                ),
            }
        ],
    )
    return message.content[0].text
