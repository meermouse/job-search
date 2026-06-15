import logging
import os

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


def _build_system_prompt(profile: dict, location: str, min_salary: int) -> str:
    return (
        f"You are an autonomous job search agent for {profile.get('name', 'the candidate')}. "
        "Your goal is to find the best-matching jobs from employers licensed to sponsor UK Skilled Worker visas.\n\n"
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
        "Use the search_jobs tool to find matching roles. You may call it multiple times to explore "
        "different angles — exact job titles, adjacent roles, transferable skills, different locations.\n\n"
        "After each round, assess whether the results are a good match for the candidate's seniority, "
        "salary expectations, and background. If not, refine your queries and search again.\n\n"
        "When you are satisfied with the results, stop calling the tool and write a 2–3 sentence "
        "strategy note summarising what angles you explored and what you found. Be specific.\n\n"
        f"You have a maximum of {MAX_ROUNDS} search rounds."
    )


def _execute_search(
    tool_input: dict,
    default_location: str,
    min_salary: int,
    sponsor_names: list[str],
    seen_urls: set[str],
) -> tuple[list[dict], str]:
    """Run one search round. Returns (new_sponsored_jobs, result_text_for_claude)."""
    queries = tool_input["queries"]
    location = tool_input.get("location", default_location)
    distance = tool_input.get("distance", 50)

    all_jobs: list[dict] = []
    for _platform, jobs, error in search_all_streaming(queries, location, min_salary, distance):
        if error:
            logger.warning("Platform '%s' returned an error: %s", _platform, error)
        all_jobs.extend(jobs)

    sponsored = sponsor_filter.filter_jobs(all_jobs, sponsor_names)

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
            f"({j.get('location', '')}) — {j.get('salary', 'Not stated')} [{j.get('source', '')}]"
        )
    return new_jobs, "\n".join(lines)
