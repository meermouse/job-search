import logging
import os
import re

import anthropic

import sponsor_filter
from searchers import search_all_streaming

logger = logging.getLogger(__name__)

MAX_ROUNDS = 5

SEARCH_TOOL = {
    "name": "search_jobs",
    "description": (
        "Search for job listings across LinkedIn, Indeed, Reed, and NHS Jobs. "
        "Only returns jobs from employers licensed to sponsor UK Skilled Worker visas. "
        "Call multiple times with different queries or locations to explore different angles."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Search queries to run. Each is a job title or keyword combination.",
            },
            "location": {
                "type": "string",
                "description": "Location to search. Defaults to the candidate's preferred location if omitted.",
            },
            "distance": {
                "type": "integer",
                "description": "Search radius in miles. Default 50.",
            },
        },
        "required": ["queries"],
    },
}

_BAND_PATTERN = re.compile(r'\b(?:afc\s+)?band\s+(6|7|8a|8b|8c|8d|9)\b', re.IGNORECASE)
_BAND_RANK = {"6": 0, "7": 1, "8a": 2, "8b": 3, "8c": 4, "8d": 5, "9": 6}


_TITLE_SEPARATORS = (",", " - ", " · ", " | ", " — ", " at ")

_NON_ALNUM = re.compile(r'[^a-z0-9]')


def _normalize_key(text: str) -> str:
    return _NON_ALNUM.sub('', text.lower())


def dedup_by_title_company(jobs: list[dict]) -> list[dict]:
    """Remove jobs whose (title, company) pair has already been seen. Keeps first occurrence.

    This catches the same posting appearing on multiple job boards with different URLs.
    Normalisation strips punctuation and case so 'NHS Trust' == 'nhs-trust'.
    """
    seen: set[tuple[str, str]] = set()
    result = []
    for job in jobs:
        key = (_normalize_key(job.get("title", "")), _normalize_key(job.get("company", "")))
        if key not in seen:
            seen.add(key)
            result.append(job)
    return result


def _is_clinical(job: dict, exclusion_keywords: list[str]) -> bool:
    """Return True if the primary role function in the job title contains a clinical keyword.

    Only the part of the title before the first separator is checked, so company or department
    context appended by scrapers (e.g. 'Manager, Royal College of Surgeons') does not trigger
    a false positive.
    """
    full_title = job.get("title", "").lower()
    role_title = full_title
    for sep in _TITLE_SEPARATORS:
        if sep in full_title:
            role_title = full_title.split(sep)[0]
            break
    return any(kw.lower() in role_title for kw in exclusion_keywords)


def _is_excluded_employment_type(job: dict, exclusion_keywords: list[str]) -> bool:
    """Return True if job title or description indicates an excluded employment type."""
    if not exclusion_keywords:
        return False
    title = job.get("title", "").lower()
    description = job.get("description", "").lower()
    # A posting that explicitly states "permanent" is not a fixed-term or temporary role
    if "permanent" in title or "permanent" in description:
        return False
    text = f"{title} {description}"
    return any(kw.lower() in text for kw in exclusion_keywords)


def _band_below_floor(job: dict, plan: dict) -> bool:
    """Return True if job mentions a NHS band below the plan's applicable floor."""
    floor_config = plan.get("nhs_band_floor", {})
    default_floor = floor_config.get("default", "8a")
    exception_floor = floor_config.get("london_remote_exception", "7")

    location = job.get("location", "").lower()
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    description = job.get("description", "").lower()

    is_london = "london" in location
    is_remote = any(w in description for w in ["remote", "hybrid", "work from home"])

    applicable_floor = exception_floor if (is_london and is_remote) else default_floor
    floor_rank = _BAND_RANK.get(applicable_floor, 2)

    for band_str in _BAND_PATTERN.findall(text):
        rank = _BAND_RANK.get(band_str.lower(), 99)
        if rank < floor_rank:
            return True
    return False


def _quality_signal(new_jobs: list[dict], round_num: int, max_rounds: int) -> str:
    remaining = max_rounds - round_num - 1
    count = len(new_jobs)
    if count == 0:
        level = "No new jobs found"
    elif count < 4:
        level = f"{count} new job(s) — low yield"
    elif count < 10:
        level = f"{count} new job(s) — moderate yield"
    else:
        level = f"{count} new job(s) — high yield"
    return f"Round quality: {level}. Remaining rounds: {remaining}."


def _build_system_prompt(profile: dict, location: str, min_salary: int) -> str:
    return (
        f"You are an autonomous job search agent for {profile.get('name', 'the candidate')}. "
        "Your goal is to collect as many relevant job listings as possible from employers licensed "
        "to sponsor UK Skilled Worker visas.\n\n"
        "Candidate profile:\n"
        f"- Current role: {profile.get('current_role', '')}\n"
        f"- Seniority: {profile.get('seniority', '')}\n"
        f"- Industry: {profile.get('industry', '')}\n"
        f"- Key skills: {', '.join(profile.get('skills') or [])}\n"
        f"- Previous roles: {', '.join(profile.get('previous_roles') or [])}\n"
        f"- Target roles: {', '.join(profile.get('target_roles') or [])}\n"
        f"- Open to: {', '.join(profile.get('open_to') or [])}\n"
        f"- Preferred location: {location}\n"
        f"- Minimum salary: £{min_salary:,}\n\n"
        "You have been given suggested queries to start with. Use the search_jobs tool to execute searches. "
        "You may adapt the queries, try different locations, or explore adjacent role titles.\n\n"
        "After each round you will receive a quality signal — use it to decide whether to refine your "
        "approach or stop early.\n\n"
        "When satisfied you have collected a good set of results, stop calling the tool. "
        "Write only a brief strategy note (2–3 sentences) describing what angles you searched and why. "
        "Do NOT list or summarise individual jobs — a separate evaluator will handle that.\n\n"
        f"You have a maximum of {MAX_ROUNDS} search rounds."
    )


def _execute_search(
    tool_input: dict,
    default_location: str,
    min_salary: int,
    sponsor_names: list[str],
    seen_urls: set[str],
    plan: dict,
    filter_log: list,
) -> tuple[list[dict], str]:
    """Run one search round. Returns (new_sponsored_jobs, result_text_for_claude)."""
    queries = tool_input["queries"]
    location = tool_input.get("location", default_location)
    distance = tool_input.get("distance", 50)

    exclusion_keywords = plan.get("exclusion_keywords", [])
    employment_type_exclusions = plan.get("employment_type_exclusions", [])

    all_jobs: list[dict] = []
    for _platform, jobs, error in search_all_streaming(queries, location, min_salary, distance):
        if error:
            logger.warning("Platform '%s' returned an error: %s", _platform, error)
        all_jobs.extend(jobs)

    filtered_jobs = []
    for job in all_jobs:
        if _is_clinical(job, exclusion_keywords):
            matched = next((kw for kw in exclusion_keywords if kw.lower() in job.get("title", "").lower()), "?")
            filter_log.append({
                "stage": "Role type",
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "url": job.get("url", ""),
                "reason": f"Title contains '{matched}'",
            })
            continue
        if _is_excluded_employment_type(job, employment_type_exclusions):
            text = f"{job.get('title', '')} {job.get('description', '')}".lower()
            matched = next((kw for kw in employment_type_exclusions if kw.lower() in text), "?")
            filter_log.append({
                "stage": "Employment type",
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "url": job.get("url", ""),
                "reason": f"Contains '{matched}'",
            })
            continue
        if _band_below_floor(job, plan):
            text = f"{job.get('title', '')} {job.get('description', '')}".lower()
            bands = _BAND_PATTERN.findall(text) or ["?"]
            floor = plan.get("nhs_band_floor", {}).get("default", "8a")
            filter_log.append({
                "stage": "NHS band floor",
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "url": job.get("url", ""),
                "reason": f"Band {', '.join(bands)} below floor ({floor})",
            })
            continue
        filtered_jobs.append(job)

    sponsored = sponsor_filter.filter_jobs(filtered_jobs, sponsor_names)
    sponsored_urls = {j.get("url") for j in sponsored}
    for job in filtered_jobs:
        if job.get("url") not in sponsored_urls:
            filter_log.append({
                "stage": "Sponsor register",
                "title": job.get("title", ""),
                "company": job.get("company", ""),
                "url": job.get("url", ""),
                "reason": f"'{job.get('company', '')}' not on UK visa sponsor register",
            })

    new_jobs = []
    for job in sponsored:
        if job["url"] and job["url"] not in seen_urls:
            seen_urls.add(job["url"])
            new_jobs.append(job)

    if not new_jobs:
        return [], "No sponsored jobs found for these queries."

    lines = [f"Found {len(new_jobs)} sponsored jobs:"]
    for i, j in enumerate(new_jobs, 1):
        lines.append(
            f"{i}. {j['title']} at {j.get('company', 'Unknown')} "
            f"({j.get('location', '')}) — {j.get('salary', 'Not stated')} [{j.get('source', '')}]\n"
            f"   URL: {j.get('url', '')}"
        )
    return new_jobs, "\n".join(lines)


def run_search_agent(
    profile: dict, plan: dict, location: str, min_salary: int
) -> tuple[list[dict], str, list]:
    """Phase 1: drive the agentic search loop. Returns (sponsored_jobs, strategy_note, filter_log)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    client = anthropic.Anthropic(api_key=api_key)
    sponsor_names = sponsor_filter.load_sponsor_names()
    system_prompt = _build_system_prompt(profile, location, min_salary)

    initial_queries = plan.get("queries", [])
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"Find the best matching jobs for this candidate. "
                f"Suggested queries from the search plan: {initial_queries}. "
                f"Adapt these as needed."
            ),
        }
    ]
    all_sponsored: list[dict] = []
    seen_urls: set[str] = set()
    filter_log: list[dict] = [{"_meta": True, "sponsor_count": len(sponsor_names)}]
    strategy_note = "Search complete."
    hit_cap = True

    print(f"[Agent] Starting search for {profile.get('name', 'candidate')} — up to {MAX_ROUNDS} rounds")

    for round_num in range(MAX_ROUNDS):
        print(f"[Agent] Round {round_num + 1}: asking Claude what to search...")
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            tools=[SEARCH_TOOL],
            messages=messages,
        )

        tool_uses = [b for b in response.content if b.type == "tool_use"]

        if not tool_uses:
            hit_cap = False
            for block in response.content:
                if block.type == "text":
                    strategy_note = block.text
            print(f"[Agent] Claude satisfied — stopping after {round_num + 1} round(s), {len(all_sponsored)} jobs found")
            break

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tool_use in tool_uses:
            queries = tool_use.input.get("queries", [])
            search_location = tool_use.input.get("location", location)
            print(f"[Agent] Round {round_num + 1}: searching {queries} in {search_location}")
            new_jobs, result_text = _execute_search(
                tool_use.input,
                default_location=location,
                min_salary=min_salary,
                sponsor_names=sponsor_names,
                seen_urls=seen_urls,
                plan=plan,
                filter_log=filter_log,
            )
            quality = _quality_signal(new_jobs, round_num, MAX_ROUNDS)
            print(f"[Agent] Round {round_num + 1}: found {len(new_jobs)} new sponsored jobs (total: {len(all_sponsored) + len(new_jobs)})")
            all_sponsored.extend(new_jobs)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": f"{result_text}\n\n{quality}",
            })

        messages.append({"role": "user", "content": tool_results})

    if hit_cap:
        print(f"[Agent] Reached {MAX_ROUNDS}-round limit — {len(all_sponsored)} jobs found")
        strategy_note = f"Search reached the {MAX_ROUNDS}-round limit without a final summary."

    before = len(all_sponsored)
    all_sponsored = dedup_by_title_company(all_sponsored)
    removed = before - len(all_sponsored)
    if removed:
        logger.info("Removed %d cross-platform duplicate job(s)", removed)

    return all_sponsored, strategy_note, filter_log


if __name__ == "__main__":
    import yaml
    logging.basicConfig(level=logging.INFO)
    with open("digest_config.yaml") as f:
        cfg = yaml.safe_load(f)
    if "profile" not in cfg:
        print("No profile in digest_config.yaml — nothing to test.")
    else:
        import job_planner
        plan = job_planner.create_plan(cfg["profile"], cfg["location"], cfg["min_salary"])
        jobs, note, _log = run_search_agent(cfg["profile"], plan, cfg["location"], cfg["min_salary"])
        print(f"\n=== Strategy note ===\n{note}")
        print(f"\n=== Jobs found: {len(jobs)} ===")
        for j in jobs[:5]:
            print(f"  - {j['title']} at {j.get('company')} ({j.get('location')}) {j.get('salary')}")
