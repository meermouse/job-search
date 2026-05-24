import json
import os
import anthropic

_SYSTEM = "You extract structured job search data from LinkedIn profiles. Return only valid JSON, no markdown."

_PROMPT = """\
Based on this LinkedIn profile text, return a JSON object with exactly these keys:
- "name": full name (empty string if not found)
- "headline": professional headline (empty string if not found)
- "current_position": most recent job title and company, e.g. "Senior Engineer at ACME Corp" (empty string if not found)
- "skills": list of up to 8 skills mentioned
- "job_titles": list of 2-3 most suitable UK job titles based on their experience, ordered by fit
- "search_queries": list of exactly 2-3 search strings for UK job boards

Rules for search_queries:
- Each query must be a specific, targeted phrase a recruiter would use, e.g. "Senior Data Engineer dbt" or "Clinical Pharmacist NHS"
- Combine the primary job title with the single most differentiating skill or sector
- Do NOT use generic single words like "Engineer" or "Manager" alone
- Do NOT repeat the same role with minor wording changes
- Prefer shorter phrases (2-4 words) that job boards handle well
- Order from most to least specific

Profile text:
{text}"""


def analyse_profile(text: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
    if not text or not text.strip():
        raise ValueError("Profile text is empty.")
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=_SYSTEM,
        messages=[{"role": "user", "content": _PROMPT.format(text=text.strip())}],
    )
    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()
    data = json.loads(raw)
    return {
        "name": data.get("name", ""),
        "headline": data.get("headline", ""),
        "current_position": data.get("current_position", ""),
        "skills": data.get("skills", []),
        "job_titles": data.get("job_titles", []),
        "search_queries": data.get("search_queries", []),
    }
