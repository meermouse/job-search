import json
import logging
import os
import anthropic

logger = logging.getLogger(__name__)

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
    "The candidate is in management, administration, and digital transformation — NOT clinical practice "
    "and NOT other specialist professions.\n"
    "Two categories of roles must be excluded from job titles:\n"
    "1. Clinical roles: nurse, doctor, ward manager, therapist, midwife, physiotherapist, clinical practitioner, "
    "surgeon, radiographer, paramedic, pharmacist, dentist, psychologist, dietitian, optometrist.\n"
    "2. Non-clinical specialist roles outside the candidate's background: lawyer, solicitor, barrister, "
    "legal counsel, legal advisor, engineer, developer, software engineer, architect (technical), "
    "accountant, finance business partner, auditor, scientist, researcher, analyst (data/research).\n"
    "A role is only relevant if its primary function is management, leadership, operations, programme delivery, "
    "or digital transformation — not if it is a specialist professional role that happens to be in the NHS.\n\n"
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
- "exclusion_keywords": comprehensive list of keywords to exclude from job titles — include both \
clinical role keywords (nurse, doctor, therapist, etc.) AND specialist professional roles outside the \
candidate's background (lawyer, solicitor, engineer, developer, accountant, scientist, etc.). \
These are title-level signals: if a job title contains any of these words, the role is a specialist \
individual-contributor post, not a management or leadership role relevant to this candidate
- "employment_type_exclusions": list of phrases that signal non-permanent or non-full-time employment. \
Use specific multi-word phrases — do NOT include bare "contract" because it appears in all employment \
descriptions ("contract of employment", "AfC contract", "permanent contract", "NHS contract") and will \
produce false positives. Use instead: "fixed-term contract", "fixed term", "temporary contract", \
"contract role", "contract post", "contract basis", "locum", "bank staff", "secondment". \
For part-time: ["part-time", "part time"]. For temporary: ["temporary", "fixed-term", "fixed term", \
"contract role", "contract post", "contract basis", "locum", "bank staff"]
- "nhs_band_floor": object with exactly two keys: "default" (always "8a") and \
"london_remote_exception" (always "7")
- "candidate_qualifications": list of candidate's qualifications phrased to match JD language
- "evaluator_notes": string with context for the evaluator — qualifications to weight, \
strengths, nuances"""


def create_plan(profile: dict, location: str, min_salary: int) -> dict:
    """Phase 0: produce a SearchPlan dict from the candidate profile."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")
    client = anthropic.Anthropic(api_key=api_key)

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
        max_tokens=4096,
        system=_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        text_blocks = [b for b in message.content if hasattr(b, "text")]
        if not text_blocks:
            raise RuntimeError("Planner returned no text content")
        raw = text_blocks[0].text.strip()
        # Strip markdown code fences if the model wrapped the JSON
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        plan = json.loads(raw)
    except (json.JSONDecodeError, IndexError, AttributeError) as exc:
        raise RuntimeError(f"Planner returned invalid JSON: {exc}") from exc

    _validate_plan(plan)
    logger.info("SearchPlan created: %d queries", len(plan.get("queries", [])))
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
    band_floor = plan.get("nhs_band_floor")
    if not isinstance(band_floor, dict) or "default" not in band_floor or "london_remote_exception" not in band_floor:
        raise RuntimeError("SearchPlan nhs_band_floor must be a dict with 'default' and 'london_remote_exception' keys")
