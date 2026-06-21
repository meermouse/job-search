import hashlib
import html
import json
import os
import markdown as md_lib
import smtplib
import ssl
import logging
from datetime import date
from email import encoders as email_encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
import yaml

import dismiss_store
import job_evaluator
import job_planner
import search_agent
import sponsor_filter
from searchers import search_all_streaming

logger = logging.getLogger(__name__)

_PLAN_CACHE_PATH = "search_plan_cache.json"
_JOB_CACHE_PATH = "job_score_cache.json"


def _plan_fingerprint(profile: dict, location: str, min_salary: int) -> str:
    key = json.dumps({"profile": profile, "location": location, "min_salary": min_salary}, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()


def load_or_create_plan(profile: dict, location: str, min_salary: int) -> dict:
    fingerprint = _plan_fingerprint(profile, location, min_salary)
    if os.path.exists(_PLAN_CACHE_PATH):
        with open(_PLAN_CACHE_PATH) as f:
            cached = json.load(f)
        if cached.get("fingerprint") == fingerprint:
            logger.info("Using cached search plan (profile unchanged)")
            return cached["plan"]
    plan = job_planner.create_plan(profile, location, min_salary)
    with open(_PLAN_CACHE_PATH, "w") as f:
        json.dump({"fingerprint": fingerprint, "plan": plan}, f, indent=2)
    logger.info("Generated and cached new search plan to %s", _PLAN_CACHE_PATH)
    return plan


def load_job_cache(fingerprint: str) -> dict:
    """Load the per-URL score cache. Returns empty dict if missing or profile has changed."""
    if os.path.exists(_JOB_CACHE_PATH):
        with open(_JOB_CACHE_PATH) as f:
            data = json.load(f)
        if data.get("_fingerprint") == fingerprint:
            return data
        logger.info("Job score cache invalidated (profile changed) — starting fresh")
    return {"_fingerprint": fingerprint}


def save_job_cache(cache: dict) -> None:
    with open(_JOB_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def apply_job_cache(
    jobs: list[dict], cache: dict
) -> tuple[list[dict], list[dict]]:
    """Split jobs into those already scored in the cache and those needing evaluation."""
    from_cache, needs_eval = [], []
    for job in jobs:
        url = job.get("url", "")
        entry = cache.get(url) if (url and not url.startswith("_")) else None
        if entry and entry.get("score") is not None:
            from_cache.append({
                **job,
                "score": entry["score"],
                "reasoning": entry.get("reasoning", ""),
                "score_breakdown": entry.get("score_breakdown", {}),
            })
        else:
            needs_eval.append(job)
    return from_cache, needs_eval


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
    return search_agent.dedup_by_title_company(deduped)


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
    site_url = os.environ.get("SITE_URL", "").rstrip("/")
    dismiss_link_html = (
        f"<p style='margin-bottom:12px'>"
        f"<a href='{html.escape(site_url)}/Dismiss_Jobs'>View and dismiss today's jobs</a>"
        f"</p>"
        if site_url else ""
    )
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
        f"{dismiss_link_html}"
        f"{preamble_html}"
        f"<hr/>"
        f"{md_lib.markdown(summary)}"
        f"{strong_section}"
        f"{worth_section}"
        f"{near_misses_section}"
        f"</body></html>"
    )


def format_log_email_html(filter_log: list[dict], today: str) -> str:
    meta = next((e for e in filter_log if e.get("_meta")), {})
    decisions = [e for e in filter_log if not e.get("_meta")]

    sponsor_count = meta.get("sponsor_count")
    sponsor_note = (
        f"Sponsor register loaded: <strong>{sponsor_count:,} companies</strong>."
        if sponsor_count is not None
        else "<em>Sponsor register count unavailable.</em>"
    )

    cache_size = meta.get("job_cache_size")
    cache_hits = meta.get("job_cache_hits")
    if cache_size is not None and cache_hits is not None:
        cache_note = (
            f"Job score cache: <strong>{cache_size:,} record(s) stored</strong>, "
            f"<strong>{cache_hits}</strong> reused today (skipped re-evaluation)."
        )
    else:
        cache_note = ""

    rows = ""
    for entry in decisions:
        url = entry.get("url", "")
        title = html.escape(entry.get("title", ""))
        title_cell = f"<a href='{html.escape(url)}'>{title}</a>" if url else title
        rows += (
            f"<tr>"
            f"<td style='white-space:nowrap'>{html.escape(entry.get('stage', ''))}</td>"
            f"<td>{title_cell}</td>"
            f"<td>{html.escape(entry.get('company', ''))}</td>"
            f"<td>{html.escape(entry.get('reason', ''))}</td>"
            f"</tr>"
        )
    if not rows:
        rows = (
            "<tr><td colspan='4' style='color:#666;font-style:italic'>"
            "No jobs were filtered today.</td></tr>"
        )
    table = (
        "<table border='1' cellpadding='6' cellspacing='0' "
        "style='border-collapse:collapse;width:100%;font-size:0.9em'>"
        "<thead><tr style='background:#f0f0f0'>"
        "<th>Stage</th><th>Job Title</th><th>Company</th><th>Reason</th>"
        "</tr></thead>"
        f"<tbody>{rows}</tbody>"
        "</table>"
    )
    cache_line = f"<p>{cache_note}</p>" if cache_note else ""
    return (
        f"<html><body>"
        f"<h2>Filter Decision Log — {html.escape(today)}</h2>"
        f"<p>{sponsor_note} {len(decisions)} job(s) filtered across all stages.</p>"
        f"{cache_line}"
        f"{table}"
        f"</body></html>"
    )


def build_run_jsonl(filter_log: list[dict], today: str, jobs_passed: int) -> bytes:
    meta = next((e for e in filter_log if e.get("_meta")), {})
    decisions = [e for e in filter_log if not e.get("_meta")]
    lines = [json.dumps({
        "type": "run",
        "date": today,
        "jobs_passed": jobs_passed,
        "jobs_filtered": len(decisions),
        "sponsor_register_size": meta.get("sponsor_count"),
        "job_cache_size": meta.get("job_cache_size"),
        "job_cache_hits": meta.get("job_cache_hits"),
    })]
    for entry in decisions:
        lines.append(json.dumps({"type": "decision", "date": today, **entry}))
    return "\n".join(lines).encode("utf-8")


def send_email(
    subject: str,
    html_body: str,
    recipient: str,
    gmail_user: str,
    gmail_app_password: str,
    attachment: tuple[str, bytes] | None = None,
) -> None:
    outer = MIMEMultipart("mixed")
    outer["Subject"] = subject
    outer["From"] = gmail_user
    outer["To"] = recipient
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(html_body, "html"))
    outer.attach(alt)
    if attachment:
        filename, content = attachment
        part = MIMEBase("application", "octet-stream")
        part.set_payload(content)
        email_encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
        outer.attach(part)
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(gmail_user, gmail_app_password)
        server.sendmail(gmail_user, recipient, outer.as_string())


def main() -> None:
    config = load_config()
    dismissed_urls = dismiss_store.load_dismissed_urls()  # NEW

    if "profile" in config:
        fingerprint = _plan_fingerprint(
            config["profile"], config["location"], config["min_salary"]
        )
        plan = load_or_create_plan(
            config["profile"], config["location"], config["min_salary"]
        )
        raw_jobs, strategy_note, filter_log = search_agent.run_search_agent(
            config["profile"], plan, config["location"], config["min_salary"]
        )
        raw_jobs = [j for j in raw_jobs if j.get("url") not in dismissed_urls]  # NEW

        job_cache = load_job_cache(fingerprint)
        cache_size_before = sum(1 for k in job_cache if not k.startswith("_"))
        cached_scored, jobs_to_eval = apply_job_cache(raw_jobs, job_cache)
        cache_hits = len(cached_scored)
        logger.info(
            "Job score cache: %d stored, %d hit(s) today, %d to evaluate",
            cache_size_before, cache_hits, len(jobs_to_eval),
        )

        newly_scored = job_evaluator.evaluate(
            jobs_to_eval, plan, config["profile"], config["min_salary"]
        )
        for j in newly_scored:
            url = j.get("url", "")
            if url and j.get("score") is not None:
                job_cache[url] = {
                    "score": j["score"],
                    "reasoning": j.get("reasoning", ""),
                    "score_breakdown": j.get("score_breakdown", {}),
                    "cached_at": date.today().isoformat(),
                }
        save_job_cache(job_cache)

        scored_jobs = cached_scored + newly_scored

        meta = next((e for e in filter_log if e.get("_meta")), None)
        if meta is not None:
            meta["job_cache_size"] = cache_size_before
            meta["job_cache_hits"] = cache_hits
        strong = [j for j in scored_jobs if j.get("score", 0) >= 4]
        worth_a_look = [j for j in scored_jobs if j.get("score", 0) == 3]
        unscored = [j for j in scored_jobs if j.get("score") is None]
        if unscored:
            logger.warning("%d job(s) returned unscored and excluded from email", len(unscored))
        for j in scored_jobs:
            score = j.get("score")
            if score is None:
                filter_log.append({
                    "stage": "Evaluator",
                    "title": j.get("title", ""),
                    "company": j.get("company", ""),
                    "url": j.get("url", ""),
                    "reason": "Not scored by evaluator",
                })
            elif score in (1, 2):
                reasoning = j.get("reasoning", "")
                short = reasoning.split(".")[0] if reasoning else ""
                filter_log.append({
                    "stage": "Evaluator",
                    "title": j.get("title", ""),
                    "company": j.get("company", ""),
                    "url": j.get("url", ""),
                    "reason": f"Score {score}/5 — {short}" if short else f"Score {score}/5",
                })
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
        filter_log = None
        jobs = collect_jobs(config["search_queries"], config["location"], config["min_salary"])
        sponsor_names = sponsor_filter.load_sponsor_names()
        filtered = sponsor_filter.filter_jobs(jobs, sponsor_names)
        filtered = [j for j in filtered if j.get("url") not in dismissed_urls]  # NEW
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
    dismiss_store.save_today_jobs(strong, worth_a_look, near_misses, today)  # NEW

    if filter_log is not None:
        log_html = format_log_email_html(filter_log, today)
        jsonl_filename = f"filter-log-{date.today().isoformat()}.jsonl"
        jsonl_bytes = build_run_jsonl(filter_log, today, count)
        send_email(
            subject=f"Filter log — {len(filter_log)} decisions — {today}",
            html_body=log_html,
            recipient=os.environ["GMAIL_USER"],
            gmail_user=os.environ["GMAIL_USER"],
            gmail_app_password=os.environ["GMAIL_APP_PASSWORD"],
            attachment=(jsonl_filename, jsonl_bytes),
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
