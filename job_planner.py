import json
import os
import anthropic

_NHS_BANDING = """
NHS Pay Bands:
Band 6:  £37,338 – £44,962
Band 7:  £46,148 – £52,809
Band 8a: £53,755 – £60,504
Band 8b: £62,215 – £72,293
Band 8c: £74,290 – £85,601
Band 8d: £88,168 – £102,493
Band 9:  £105,385 – £121,271
"""

_SYSTEM = (
    "You are a job search strategist. Given a candidate profile, produce a structured search plan as JSON.\n\n"
    + _NHS_BANDING
    + "\nBand floor rule:\n"
    "- Default: Band 8a+ (below 8a is below threshold regardless of salary text)\n"
    "- Exception: Band 7+ is acceptable ONLY if the role is London-based AND remote or hybrid working "
    "is explicitly mentioned in the job description\n\n"
    "The candidate is in management, administration, and digital transformation — NOT clinical practice. "
    "Clinical roles (nurse, doctor, ward manager, therapist, midwife, physiotherapist, clinical practitioner, "
    "surgeon, radiographer, paramedic, pharmacist, dentist) must be excluded.\n\n"
    "Return only valid JSON, no markdown."
)

_PROMPT = """\
Create a job search plan for this candidate.

Profile:
- Name: {name}
- Current role: {current_role}
- About: {about}
- Seniority: {seniority}
- Industry: {industry}
- Skills: {skills}
- Previous roles: {previous_roles}
- Target roles (directional intent — not literal keywords): {target_roles}
- Open to: {open_to}
- Qualifications: {qualifications}
- Preferred location: {location}
- Minimum salary: £{min_salary:,}
- Employment type required: {employment_type}

Return a JSON object with exactly these keys:
- "queries": list of 5-8 specific search strings. Use target_roles as direction, not keywords — \
generate queries from the intersection of that direction with skills, background, and qualifications. \
Include adjacent titles a recruiter would use (e.g. "Deputy Director Digital", "Senior Programme Manager NHS").
- "locations": list of locations to cover
- "exclusion_keywords": comprehensive list of clinical role keywords to exclude from job titles
- "employment_type_exclusions": list of employment type keywords to exclude based on the candidate's \
employment_type preference (e.g. if full-time only: ["part-time", "part time", "contract", \
"fixed term", "fixed-term", "temporary"])
- "nhs_band_floor": object with exactly two keys: "default" (always "8a") and \
"london_remote_exception" (always "7")
- "candidate_qualifications": list of candidate's qualifications phrased to match JD language
- "evaluator_notes": string with context for the evaluator — qualifications to weight, \
strengths, nuances"""


def create_plan(profile: dict, location: str, min_salary: int) -> dict:
    """Phase 0: produce a SearchPlan dict from the candidate profile."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    prompt = _PROMPT.format(
        name=profile.get("name", ""),
        current_role=profile.get("current_role", ""),
        about=profile.get("about", ""),
        seniority=profile.get("seniority", ""),
        industry=profile.get("industry", ""),
        skills=", ".join(profile.get("skills") or []),
        previous_roles=", ".join(profile.get("previous_roles") or []),
        target_roles=", ".join(profile.get("target_roles") or []),
        open_to=", ".join(profile.get("open_to") or []),
        qualifications=", ".join(profile.get("qualifications") or []) or "not specified",
        location=location,
        min_salary=min_salary,
        employment_type=", ".join(profile.get("employment_type") or ["any"]),
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        plan = json.loads(message.content[0].text)
    except (json.JSONDecodeError, IndexError, AttributeError) as exc:
        raise RuntimeError(f"Planner returned invalid JSON: {exc}") from exc

    _validate_plan(plan)
    return plan


def _validate_plan(plan: dict) -> None:
    required = {
        "queries", "locations", "exclusion_keywords", "employment_type_exclusions",
        "nhs_band_floor", "candidate_qualifications", "evaluator_notes",
    }
    missing = required - set(plan.keys())
    if missing:
        raise RuntimeError(f"SearchPlan missing required keys: {missing}")
    if not plan.get("queries"):
        raise RuntimeError("SearchPlan has no queries")
