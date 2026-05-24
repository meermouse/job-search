import html
import os
import markdown as md_lib
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
        if not job["url"]:
            logger.debug("Skipping job with no URL: %s at %s", job.get("title"), job.get("company"))
            continue
        if job["url"] not in seen_urls:
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


def format_email_html(jobs: list[dict], summary: str, today: str) -> str:
    if jobs:
        rows = "".join(
            f"<tr>"
            f"<td><a href='{html.escape(j['url'])}'>{html.escape(j['title'])}</a></td>"
            f"<td>{html.escape(j.get('sponsor_name') or j.get('company', ''))}</td>"
            f"<td>{html.escape(j.get('location', ''))}</td>"
            f"<td>{html.escape(j.get('salary', ''))}</td>"
            f"<td>{html.escape(j.get('source', ''))}</td>"
            f"</tr>"
            for j in jobs
        )
        table = (
            "<table border='1' cellpadding='6' cellspacing='0' "
            "style='border-collapse:collapse;width:100%'>"
            "<thead><tr style='background:#f0f0f0'>"
            "<th>Job Title</th><th>Company</th><th>Location</th><th>Salary</th><th>Source</th>"
            "</tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    else:
        table = ""

    return (
        f"<html><body>"
        f"<h2>Jie's Job Digest — {html.escape(today)}</h2>"
        f"{md_lib.markdown(summary)}"
        f"{table}"
        f"</body></html>"
    )


def send_email(
    subject: str,
    html_body: str,
    recipient: str,
    gmail_user: str,
    gmail_app_password: str,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.attach(MIMEText(html_body, "html"))
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, recipient, msg.as_string())


def main() -> None:
    config = load_config()
    jobs = collect_jobs(config["search_queries"], config["location"], config["min_salary"])
    sponsor_names = sponsor_filter.load_sponsor_names()
    filtered = sponsor_filter.filter_jobs(jobs, sponsor_names)

    if filtered:
        summary = analyse_results(filtered, config)
    else:
        summary = "No matching roles were found today from licensed UK visa sponsors."

    today = date.today().strftime("%d %B %Y")
    count = len(filtered)
    subject = f"Job digest — {count} match{'es' if count != 1 else ''} — {today}"
    html_body = format_email_html(filtered, summary, today)
    send_email(
        subject=subject,
        html_body=html_body,
        recipient=os.environ["RECIPIENT_EMAIL"],
        gmail_user=os.environ["GMAIL_USER"],
        gmail_app_password=os.environ["GMAIL_APP_PASSWORD"],
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
