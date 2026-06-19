import os
import re
import anthropic

_SYSTEM_BASE = """\
You are a helpful job search assistant called "The Job Mule" embedded in a UK Skilled Worker visa job finder app.
The app searches LinkedIn, Indeed, Reed, and NHS Jobs, then filters results to only show
employers licensed to sponsor Skilled Worker visas.

The user is Jie, please address her as such.

You guide Jie through the search process and offer practical advice on UK job hunting,
Skilled Worker visa sponsorship, salary expectations, and interview preparation.

You can take actions by including tags in your reply. These tags will be stripped before
Jie sees your message. Available actions:

  [ACTION:set_queries:query one|query two|query three]  — set search queries (pipe-separated)
  [ACTION:set_location:City Name]                       — set search location
  [ACTION:set_distance:25]                              — set search radius in miles (integer)
  [ACTION:set_salary:50000]                             — set minimum salary in pounds (integer)
  [ACTION:trigger_search]                               — trigger the search

Some messages begin with [System: ...] — these are automated events fired by the app itself
(e.g. CV uploaded, search completed), not typed by the user. Respond to them naturally and
concisely (2-4 sentences). You may use actions in response to system events too.

Rules:
- Never fabricate job listings or sponsor status
- Always use set_queries before trigger_search; if no queries are set, decline trigger_search
  and ask the user to provide at least one search term
- If no CV has been uploaded, prompt the user to upload one when they ask for CV-specific advice
- Keep responses concise and practical
- When the user asks to search somewhere or change a parameter, always emit the relevant
  ACTION tags so the form fields update immediately, then confirm what you set
"""

_CV_SECTION = """
The user has uploaded a CV or connected their LinkedIn profile. Here is the extracted analysis:
  Job titles: {job_titles}
  Skills: {skills}
  Suggested search queries: {search_queries}
"""

_RESULTS_SECTION = """
The most recent search returned {total} total jobs, {sponsored} from licensed Skilled Worker visa sponsors.
The sponsored results (up to 20 shown) are:

{listings}
"""

_MAX_RESULTS = 20


def _format_results(jobs: list[dict]) -> str:
    lines = []
    for i, j in enumerate(jobs[:_MAX_RESULTS], 1):
        parts = [f"{i}. {j.get('title', 'Unknown')} at {j.get('company', 'Unknown')}"]
        if j.get("location"):
            parts.append(f"  Location: {j['location']}")
        if j.get("salary"):
            parts.append(f"  Salary: {j['salary']}")
        if j.get("url"):
            parts.append(f"  URL: {j['url']}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


def _build_system_prompt(
    cv_analysis: dict | None,
    search_results: dict | None = None,
) -> str:
    prompt = _SYSTEM_BASE
    if cv_analysis:
        prompt += _CV_SECTION.format(
            job_titles=", ".join(cv_analysis.get("job_titles", [])),
            skills=", ".join(cv_analysis.get("skills", [])),
            search_queries=", ".join(cv_analysis.get("search_queries", [])),
        )
    if search_results:
        filtered = search_results.get("filtered", [])
        all_jobs = search_results.get("all", [])
        prompt += _RESULTS_SECTION.format(
            total=len(all_jobs),
            sponsored=len(filtered),
            listings=_format_results(filtered) if filtered else "No sponsored results found.",
        )
    return prompt


_ACTION_RE = re.compile(r"\[ACTION:([^\]]+)\]")


def _parse_actions(text: str) -> list[dict]:
    actions = []
    for match in _ACTION_RE.finditer(text):
        parts = match.group(1).split(":", 1)
        actions.append({
            "type": parts[0],
            "params": parts[1] if len(parts) > 1 else "",
        })
    return actions


def _strip_actions(text: str) -> str:
    cleaned = _ACTION_RE.sub("", text)
    cleaned = re.sub(r"  +", " ", cleaned)
    return cleaned.strip()


def get_response(
    message: str,
    history: list[dict],
    cv_analysis: dict | None,
    search_results: dict | None = None,
) -> tuple[str, list[dict]]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    client = anthropic.Anthropic(api_key=api_key)
    trimmed = history[-20:]
    if trimmed and trimmed[0]["role"] != "user":
        trimmed = trimmed[1:]
    messages = trimmed + [{"role": "user", "content": message}]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_build_system_prompt(cv_analysis, search_results),
        messages=messages,
    )
    raw = response.content[0].text
    return _strip_actions(raw), _parse_actions(raw)


def apply_actions(actions: list[dict], session_state: dict) -> bool:
    """Apply parsed actions to session_state. Returns True if trigger_search was requested."""
    trigger = False
    for action in actions:
        t = action["type"]
        p = action.get("params", "")
        if t == "set_queries":
            parsed = [q.strip() for q in p.split("|") if q.strip()]
            if parsed:
                session_state["_chat_queries"] = parsed
        elif t == "set_location":
            session_state["_chat_location"] = p.strip()
        elif t == "set_distance":
            try:
                session_state["_chat_distance"] = int(p.strip())
            except ValueError:
                pass
        elif t == "set_salary":
            try:
                session_state["_chat_salary"] = int(p.strip())
            except ValueError:
                pass
        elif t == "trigger_search":
            trigger = True
    return trigger
