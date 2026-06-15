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


def run_search_agent(
    profile: dict, location: str, min_salary: int
) -> tuple[list[dict], str]:
    """Drive the agentic search loop. Returns (sponsored_jobs, strategy_note)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    client = anthropic.Anthropic(api_key=api_key)
    sponsor_names = sponsor_filter.load_sponsor_names()
    system_prompt = _build_system_prompt(profile, location, min_salary)

    messages: list[dict] = [
        {"role": "user", "content": "Find the best matching jobs for this candidate."}
    ]
    all_sponsored: list[dict] = []
    seen_urls: set[str] = set()
    strategy_note = "Search complete."
    hit_cap = True

    for _ in range(MAX_ROUNDS):
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
            break

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for tool_use in tool_uses:
            new_jobs, result_text = _execute_search(
                tool_use.input,
                default_location=location,
                min_salary=min_salary,
                sponsor_names=sponsor_names,
                seen_urls=seen_urls,
            )
            all_sponsored.extend(new_jobs)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result_text,
            })

        messages.append({"role": "user", "content": tool_results})

    if hit_cap:
        strategy_note = f"Search reached the {MAX_ROUNDS}-round limit without a final summary."

    return all_sponsored, strategy_note


if __name__ == "__main__":
    import yaml
    logging.basicConfig(level=logging.INFO)
    with open("digest_config.yaml") as f:
        cfg = yaml.safe_load(f)
    if "profile" not in cfg:
        print("No profile in digest_config.yaml — nothing to test.")
    else:
        jobs, note = run_search_agent(cfg["profile"], cfg["location"], cfg["min_salary"])
        print(f"\n=== Strategy note ===\n{note}")
        print(f"\n=== Jobs found: {len(jobs)} ===")
        for j in jobs[:5]:
            print(f"  - {j['title']} at {j.get('company')} ({j.get('location')}) {j.get('salary')}")
