import json
import os
import re
import anthropic
from linkedin_api import Linkedin


_SYSTEM = "You extract structured job search data from LinkedIn profiles. Return only valid JSON, no markdown."

_PROMPT = """\
Based on this LinkedIn profile, return a JSON object with exactly these keys:
- "job_titles": list of 2-3 most suitable UK job titles based on their experience, ordered by fit
- "search_queries": list of exactly 2-3 search strings for UK job boards

Rules for search_queries:
- Each query must be a specific, targeted phrase a recruiter would use, e.g. "Senior Data Engineer dbt" or "Clinical Pharmacist NHS"
- Combine the primary job title with the single most differentiating skill or sector
- Do NOT use generic single words like "Engineer" or "Manager" alone
- Do NOT repeat the same role with minor wording changes
- Prefer shorter phrases (2-4 words) that job boards handle well
- Order from most to least specific

Profile:
Name: {name}
Headline: {headline}
Current position: {current_position}
Skills: {skills}
Recent experience:
{experience}"""


def _profile_id_from_url(url: str) -> str:
    match = re.search(r'linkedin\.com/in/([^/?#]+)', url)
    if not match:
        raise ValueError(
            "Invalid LinkedIn profile URL. Expected format: https://www.linkedin.com/in/username"
        )
    return match.group(1)


def _format_experience(experience: list) -> str:
    lines = []
    for entry in experience[:5]:
        title = entry.get("title", "")
        company = entry.get("companyName", "")
        if title or company:
            lines.append(f"- {title} at {company}".strip(" at"))
    return "\n".join(lines) or "No experience listed"


def fetch_profile(url: str) -> dict:
    li_at = os.environ.get("LINKEDIN_LI_AT")
    jsessionid = os.environ.get("LINKEDIN_JSESSIONID")
    if not li_at or not jsessionid:
        raise RuntimeError(
            "LINKEDIN_LI_AT and LINKEDIN_JSESSIONID must be set in your .env file."
        )
    profile_id = _profile_id_from_url(url)
    api = Linkedin("", "", cookies={"li_at": li_at, "JSESSIONID": jsessionid})
    return api.get_profile(profile_id)


def analyse_profile(profile: dict) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    first = profile.get("firstName", "")
    last = profile.get("lastName", "")
    name = f"{first} {last}".strip()
    headline = profile.get("headline", "")

    experience = profile.get("experience", [])
    if experience:
        title = experience[0].get("title", "")
        company = experience[0].get("companyName", "")
        current_position = f"{title} at {company}".strip(" at")
    else:
        current_position = ""

    skills = [s.get("name", "") for s in profile.get("skills", []) if s.get("name")][:8]

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _PROMPT.format(
            name=name,
            headline=headline,
            current_position=current_position,
            skills=", ".join(skills) or "None listed",
            experience=_format_experience(experience),
        )}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    claude_data = json.loads(raw)

    return {
        "name": name,
        "headline": headline,
        "current_position": current_position,
        "skills": skills,
        "job_titles": claude_data.get("job_titles", []),
        "search_queries": claude_data.get("search_queries", []),
    }
