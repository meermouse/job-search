import json
import logging
import os

import anthropic

logger = logging.getLogger(__name__)

_NHS_BANDING = """
Band 6:  £37,338 – £44,962
Band 7:  £46,148 – £52,809
Band 8a: £53,755 – £60,504
Band 8b: £62,215 – £72,293
Band 8c: £74,290 – £85,601
Band 8d: £88,168 – £102,493
Band 9:  £105,385 – £121,271
"""

_SYSTEM = (
    "You are a job suitability evaluator. Score each job 1–5 across five dimensions, "
    "then compute a weighted overall score (rounded to nearest integer).\n\n"
    "NHS Pay Bands:\n" + _NHS_BANDING + "\n"
    "Band floor rules:\n"
    "- Default: Band 8a+ (below 8a → score 1 on salary_band)\n"
    "- Exception: Band 7+ is acceptable ONLY if the role is London-based AND remote/hybrid "
    "is explicitly mentioned in the description\n\n"
    "Scoring dimensions (apply weighted judgment — role_type, employment_type, and qualifications "
    "carry higher weight):\n"
    "- role_type: Does the PRIMARY FUNCTION of this role match the candidate's background in "
    "management, leadership, operations, programme delivery, or digital transformation?\n"
    "  Score 1 (automatic disqualifier) when the CANDIDATE'S OWN duties are specialist professional practice:\n"
    "  - Clinical practice: the candidate would be nursing, doctoring, performing surgery, providing therapy, etc.\n"
    "  - Legal practice: the candidate would be providing legal advice, drafting contracts as a lawyer, etc.\n"
    "  - Technical practice: the candidate would be writing code, engineering systems, conducting research, etc.\n"
    "  - Finance practice: the candidate would be preparing accounts, conducting audits, etc.\n"
    "  IMPORTANT: the disqualifier is about what the CANDIDATE DOES, not who they work with or who employs them.\n"
    "  A Business Development Manager at the Royal College of Surgeons is a management role — score it on "
    "whether the candidate manages and leads, not on whether the employer's specialty is surgery.\n"
    "  A Head of Digital at a law firm is a management role — the employer being a law firm is irrelevant.\n"
    "  Score 4–5 for clear management, leadership, or transformation roles with meaningful scope.\n"
    "  Score 2–3 for hybrid or ambiguous roles — e.g. a 'Digital Transformation Lead' that is partly hands-on.\n"
    "  Use the job title and PRIMARY DUTIES described to make this judgment, not the employer's sector.\n"
    "- seniority: Does the level match the candidate's stated seniority?\n"
    "- salary_band: Does it meet the min salary and band floor? Unclear/unstated → 3\n"
    "- employment_type: HARD FILTER. If employment_type_required is set, any role that is "
    "not that type (part-time, contract, fixed-term, temporary) → 1. If not set → 5\n"
    "- qualifications: Does the JD require quals the candidate holds? "
    "Requires quals they lack → 1–2. Matches well → 4–5. No requirements stated → 3\n\n"
    "Return a JSON array — one object per job — with fields:\n"
    "- job_index: integer (0-based, matching input array order)\n"
    "- score: integer 1–5 (weighted average, rounded)\n"
    "- score_breakdown: object with keys role_type, seniority, salary_band, "
    "employment_type, qualifications (each integer 1–5)\n"
    "- reasoning: string (1–2 sentences explaining the overall score)\n\n"
    "Return only valid JSON array, no markdown."
)

_BATCH_WARN_THRESHOLD = 50


def evaluate(jobs: list[dict], plan: dict, profile: dict, min_salary: int) -> list[dict]:
    """Phase 2: score every job 1–5. Returns jobs with score/score_breakdown/reasoning added.
    Falls back to returning unscored jobs if the evaluator call fails."""
    if not jobs:
        return []

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    if len(jobs) > _BATCH_WARN_THRESHOLD:
        logger.warning(
            "Evaluator received %d jobs — large batches risk response truncation (limit ~%d)",
            len(jobs),
            _BATCH_WARN_THRESHOLD,
        )

    client = anthropic.Anthropic(api_key=api_key)

    employment_type_required = ", ".join(profile.get("employment_type") or []) or "not specified"
    candidate_qualifications = (
        plan.get("candidate_qualifications")
        or profile.get("qualifications")
        or []
    )

    jobs_text = json.dumps(
        [
            {
                "index": i,
                "title": j.get("title", ""),
                "company": j.get("company", ""),
                "location": j.get("location", ""),
                "salary": j.get("salary", ""),
                "description": j.get("description", ""),
                "source": j.get("source", ""),
            }
            for i, j in enumerate(jobs)
        ],
        indent=2,
    )

    target_roles = ", ".join(profile.get("target_roles") or []) or "not specified"
    prompt = (
        f"Evaluate these jobs for the following candidate.\n\n"
        f"Candidate:\n"
        f"- Current role: {profile.get('current_role', '')}\n"
        f"- Target roles: {target_roles}\n"
        f"- Seniority: {profile.get('seniority', '')}\n"
        f"- Required employment type: {employment_type_required}\n"
        f"- Qualifications: {', '.join(candidate_qualifications) or 'not specified'}\n"
        f"- Minimum salary: £{min_salary:,}\n\n"
        f"Evaluator notes: {plan.get('evaluator_notes', '')}\n\n"
        f"Jobs to evaluate:\n{jobs_text}"
    )

    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text_blocks = [b for b in message.content if hasattr(b, "text")]
        raw = text_blocks[0].text.strip() if text_blocks else ""
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        scores = json.loads(raw)
    except Exception as exc:
        logger.warning("Evaluator failed: %s — returning jobs unscored", exc)
        return jobs

    score_map = {entry.get("job_index"): entry for entry in scores}
    result = []
    missing = 0
    for idx, job in enumerate(jobs):
        if idx in score_map:
            entry = score_map[idx]
            result.append({
                **job,
                "score": entry.get("score"),
                "score_breakdown": entry.get("score_breakdown", {}),
                "reasoning": entry.get("reasoning", ""),
            })
        else:
            missing += 1
            result.append(job)

    if missing:
        logger.warning("Evaluator omitted %d job(s) from response — included unscored", missing)

    return result
