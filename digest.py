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

import job_evaluator
import job_planner
import search_agent
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
                    f"- Queries: {', '.join(config.get('search_queries', []))}\n"
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


def _make_table(jobs: list[dict], include_reasoning: bool = False) -> str:
    if not jobs:
        return ""
    headers = ["Job Title", "Company", "Location", "Salary", "Source"]
    if include_reasoning:
        headers.append("Why")
    header_html = "".join(f"<th>{h}</th>" for h in headers)
    rows = ""
    for j in jobs:
        reasoning_cell = (
            f"<td>{html.escape(j.get('reasoning', ''))}</td>" if include_reasoning else ""
        )
        rows += (
            f"<tr>"
            f"<td><a href='{html.escape(j['url'])}'>{html.escape(j['title'])}</a></td>"
            f"<td>{html.escape(j.get('sponsor_name') or j.get('company', ''))}</td>"
            f"<td>{html.escape(j.get('location', ''))}</td>"
            f"<td>{html.escape(j.get('salary', ''))}</td>"
            f"<td>{html.escape(j.get('source', ''))}</td>"
            f"{reasoning_cell}"
            f"</tr>"
        )
    return (
        "<table border='1' cellpadding='6' cellspacing='0' "
        "style='border-collapse:collapse;width:100%'>"
        f"<thead><tr style='background:#f0f0f0'>{header_html}</tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )


def format_email_html(
    strong_jobs: list[dict],
    summary: str,
    today: str,
    preamble: str = "",
    worth_a_look: list[dict] | None = None,
    near_misses: list[dict] | None = None,
) -> str:
    preamble_html = md_lib.markdown(preamble) if preamble else ""
    strong_table = _make_table(strong_jobs, include_reasoning=True)
    worth_table = _make_table(worth_a_look or [], include_reasoning=True)
    near_misses_table = _make_table(near_misses or [], include_reasoning=True)

    strong_section = f"<h3>Strong matches</h3>{strong_table}" if strong_table else ""
    worth_section = f"<h3>Worth a look</h3>{worth_table}" if worth_table else ""
    near_misses_section = (
        f"<h3>Near misses — why today's closest results didn't make it</h3>"
        f"<p style='color:#666;font-size:0.9em'>These scored too low to recommend, "
        f"but are shown so you can see what came up and why it was filtered out.</p>"
        f"{near_misses_table}"
    ) if near_misses_table else ""

    return (
        f"<html><body>"
        f"<h2>Jie's Job Digest — {html.escape(today)}</h2>"
        f"{preamble_html}"
        f"<hr/>"
        f"{md_lib.markdown(summary)}"
        f"{strong_section}"
        f"{worth_section}"
        f"{near_misses_section}"
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

    if "profile" in config:
        plan = job_planner.create_plan(
            config["profile"], config["location"], config["min_salary"]
        )
        raw_jobs, strategy_note = search_agent.run_search_agent(
            config["profile"], plan, config["location"], config["min_salary"]
        )
        scored_jobs = job_evaluator.evaluate(
            raw_jobs, plan, config["profile"], config["min_salary"]
        )
        strong = [j for j in scored_jobs if j.get("score", 0) >= 4]
        worth_a_look = [j for j in scored_jobs if j.get("score", 0) == 3]
        unscored = [j for j in scored_jobs if j.get("score") is None]
        if unscored:
            logger.warning("%d job(s) returned unscored and excluded from email", len(unscored))
        if not strong and not worth_a_look:
            near_misses = sorted(
                [j for j in scored_jobs if j.get("score") in (1, 2)],
                key=lambda j: j["score"],
                reverse=True,
            )[:5]
            summary = "No roles met the scoring threshold today. " + strategy_note
        else:
            near_misses = []
            summary = strategy_note
        count = len(strong) + len(worth_a_look)
    else:
        jobs = collect_jobs(config["search_queries"], config["location"], config["min_salary"])
        sponsor_names = sponsor_filter.load_sponsor_names()
        filtered = sponsor_filter.filter_jobs(jobs, sponsor_names)
        summary = (
            analyse_results(filtered, config)
            if filtered
            else "No matching roles were found today from licensed UK visa sponsors."
        )
        strong = filtered
        worth_a_look = []
        near_misses = []
        count = len(strong)

    today = date.today().strftime("%d %B %Y")
    subject = f"Job digest — {count} match{'es' if count != 1 else ''} — {today}"
    preamble = config.get("preamble", "")
    html_body = format_email_html(
        strong, summary, today, preamble, worth_a_look=worth_a_look, near_misses=near_misses
    )
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
