# Job Search — Planned Workflow & Filtering Design Spec

**Date:** 2026-06-16
**Status:** Approved
**Branch:** feature/FE-005-workflow

---

## Overview

Replace the current single-phase agentic search loop with a three-phase pipeline: **Plan → Search → Evaluate**. Each phase has a single responsibility. The planner reasons about the candidate's profile and produces a structured search plan; the search agent executes that plan and collects raw results; the evaluator scores every result 1–5 across five dimensions and produces the final filtered list for the email digest.

Key improvements over the current approach:
- Clinical NHS roles are excluded before Claude ever sees them (pre-filter in search phase)
- NHS banding is enforced against a known banding table, not inferred from free-text salary fields
- Qualification matching is a first-class scoring dimension
- Employment type preference is respected
- Every included job has a score and reasoning the recipient can see

---

## Architecture

```
digest_config.yaml       ← add qualifications + employment_type fields
job_planner.py           ← NEW: Phase 0 — produces a structured SearchPlan
search_agent.py          ← MODIFIED: Phase 1 — follows the plan, quality signal per round
job_evaluator.py         ← NEW: Phase 2 — grades every job 1–5 across five dimensions
digest.py                ← MODIFIED: wire the three phases together
```

### Data Flow

```
digest_config.yaml
       │
       ▼
[job_planner.py]  → SearchPlan
       │
       ▼
[search_agent.py] → raw sponsored jobs[]  (up to 5 rounds, plan-guided)
       │
       ▼
[job_evaluator.py] → ScoredJob[]
       │
       ▼
[digest.py]  → email
   ├── score 4–5: "Strong matches"
   └── score 3:   "Worth a look"
        (1–2: silently dropped)
```

---

## Profile Enhancements

Two new optional fields in `digest_config.yaml`:

```yaml
profile:
  # ... existing fields unchanged ...
  qualifications:
    - "PRINCE2 Practitioner"   # example — fill in actual qualifications
    - "MSc Digital Health"
  employment_type:             # one or more of: full-time, part-time, contract
    - full-time
    - contract
```

Both fields are optional. If `qualifications` is absent, the evaluator skips the qualification-match dimension. If `employment_type` is absent, the evaluator treats any employment type as acceptable.

---

## NHS Domain Knowledge

Baked into the system prompts for both the planner and evaluator as a reference table. Neither phase infers band/salary relationships from free text — the table is authoritative.

| Band | Salary range |
|------|-------------|
| 6    | £37,338 – £44,962 |
| 7    | £46,148 – £52,809 |
| 8a   | £53,755 – £60,504 |
| 8b   | £62,215 – £72,293 |
| 8c   | £74,290 – £85,601 |
| 8d   | £88,168 – £102,493 |
| 9    | £105,385 – £121,271 |

**Band floor rule:**
- Default: **Band 8a+** (£53,755+)
- Exception: **Band 7+** if the role is London-based AND remote or hybrid working is explicitly mentioned in the job description

Any NHS role below the applicable band floor scores 1 on the salary dimension regardless of what the salary field text says.

**Clinical vs management distinction:**
- The candidate's background is management, administration, digital transformation, and governance — not clinical practice
- Clinical roles (nurse, doctor, therapist, ward manager, midwife, physiotherapist, etc.) score 1 on the role-type dimension — automatic disqualifier
- NHS management, digital services, transformation, project/programme management, and governance roles are in-scope

---

## Phase 0: Planner (`job_planner.py`)

A single Claude call. Runs once per digest before any searching. Produces a `SearchPlan` dict.

### Input
Full profile dict from `digest_config.yaml` (name, current_role, skills, target_roles, qualifications, employment_type, about, location, min_salary).

### Output — `SearchPlan`

```python
{
  "queries": [                              # 5–8 search strings, ready to pass to search agent
    "Digital Services Manager NHS Bristol",
    "Head of Business Transformation South West",
    ...
  ],
  "locations": ["Bristol", "Bath", "Remote"],
  "exclusion_keywords": [                  # titles/keywords to drop pre-filter in search phase
    "nurse", "clinical", "ward", "doctor",
    "therapist", "midwife", "physiotherapist"
  ],
  "nhs_band_floor": {
    "default": "8a",                       # 8a+ for all non-exception roles
    "london_remote_exception": "7"         # 7+ if London-based AND remote/hybrid confirmed
  },
  "candidate_qualifications": [            # synthesised from profile.qualifications
    "PRINCE2 Practitioner",                # may be rephrased to match JD language
    "MSc Digital Health"
  ],
  "evaluator_notes": "..."                 # free-text context for evaluator: strengths, priorities
}
```

### Planner System Prompt — Key Instructions

- `target_roles` is **directional intent**, not literal keywords. Use it to understand what kind of work the candidate is moving towards, then generate queries from the intersection of that direction + current skills + previous roles + qualifications.
- Generate queries specific enough to surface relevant roles — avoid generic terms like "manager Bristol". Prefer role titles a recruiter or NHS hiring manager would actually use.
- Include adjacent and transferable titles (e.g. "Deputy Director Digital", "Senior Programme Manager", "Head of Transformation").
- Employment type from profile constrains query strategy — if `contract` only, generate contract-appropriate queries.
- Derive `nhs_band_floor` from `min_salary` using the banding table; apply the London/remote exception rule.
- `exclusion_keywords` must cover clinical role synonyms; err on the side of more exclusions.
- `evaluator_notes` should highlight qualifications the evaluator should weight, and any role-specific nuances.

### Failure Handling
If the planner call fails or returns invalid JSON, `digest.py` raises immediately — no searching begins.

---

## Phase 1: Search Agent (`search_agent.py`)

Enhanced version of the existing agentic loop. Takes a `SearchPlan` as input; Claude's role is **tactical execution** (which queries to run first, what to try next based on results) rather than strategy.

### Key Changes from Current

**1. Plan-driven queries**
Claude is given the `SearchPlan.queries` list as a starting point. It may refine, reorder, or combine them, but cannot invent strategy from scratch.

**2. Exclusion pre-filter (in `_execute_search`)**
Before returning results to Claude, any job whose title matches an exclusion keyword from the plan is silently dropped. Clinical roles never enter Claude's context.

**3. NHS band pre-filter (in `_execute_search`)**
If a job description or title references an NHS band below the plan's band floor (accounting for the London/remote exception), it is dropped before Claude sees it.

**4. Quality signal per round**
After each round, Claude receives the raw results plus a brief structured signal:
```
Round 2: 8 jobs returned. Rough breakdown: 3 look senior/management level, 5 look marginal or unclear.
Remaining rounds: 3. Refine queries, try a new location, or satisfied?
```
Claude decides: refine and search again, try a different location/query angle, or stop early.

**5. No final summary**
The search agent no longer writes a summary or highlights standout roles — that is the evaluator's job. It returns `(raw_jobs: list[dict], strategy_note: str)` where `strategy_note` is a brief description of what angles were searched.

### Output
`(raw_jobs: list[dict], strategy_note: str)` — same signature as current, raw jobs passed directly to evaluator.

---

## Phase 2: Evaluator (`job_evaluator.py`)

A dedicated module that scores every collected job 1–5 across five dimensions.

### Scoring Dimensions

| Dimension | What it checks | Weight |
|---|---|---|
| **Role type** | Management/admin/digital vs clinical. Clinical → 1 (disqualifier) | High |
| **Seniority** | Does the level match "Senior"? Junior/entry → 1–2 | Medium |
| **Salary / band** | NHS: band ≥ floor (with London/remote exception)? Private: salary ≥ min? Unclear → 3 | Medium |
| **Employment type** | Matches full-time/contract preference? Opposite type → 2. Absent from profile → ignored | Medium |
| **Qualification match** | JD requires quals candidate holds → 4–5. Requires quals they lack → 1–2. No requirements stated → 3 | High |

**Overall score** = weighted average, rounded to the nearest integer (1–5). Role type and qualification match carry higher weight — a mismatch on either cannot be compensated by strong scores elsewhere.

### Implementation

A **single batched Claude call** — all jobs sent together, Claude returns a JSON array. Not one call per job.

### Output per Job

```python
{
  # ...all original job fields preserved...
  "score": 4,
  "score_breakdown": {
    "role_type": 5,
    "seniority": 4,
    "salary_band": 4,
    "employment_type": 5,
    "qualifications": 3
  },
  "reasoning": "Senior programme manager role in NHS digital services — strong role-type match. Band 8b confirmed. Requires PRINCE2 which candidate holds. MSc not mentioned. Employment type matches."
}
```

### Failure Handling
If the evaluator call fails or returns malformed JSON, `digest.py` logs a warning and falls back to including all raw sponsored jobs in the email unscored, with a note that grading was unavailable.

---

## `digest.py` Integration

```python
# Phase 0
plan = job_planner.create_plan(config["profile"], config["location"], config["min_salary"])

# Phase 1
raw_jobs, strategy_note = search_agent.run_search_agent(config["profile"], plan, config["location"], config["min_salary"])

# Phase 2
scored_jobs = job_evaluator.evaluate(raw_jobs, plan, config["profile"])

# Split by score
strong = [j for j in scored_jobs if j["score"] >= 4]
worth_a_look = [j for j in scored_jobs if j["score"] == 3]

# Email includes both sections, strategy_note in header
```

---

## Email Output

The email now has two sections:

**Strong matches (score 4–5)**
Full table with title, company, location, salary, source, link — plus the `reasoning` field so Jie can see why each was included.

**Worth a look (score 3)**
Same table, smaller section. Jie can decide whether to follow up.

Score 1–2 jobs are silently dropped — not included in either section.

---

## Error Handling

| Failure | Behaviour |
|---|---|
| Planner call fails / bad JSON | Raise before searching; email not sent |
| Search agent hits round cap | Proceed to evaluator with whatever was found |
| Platform search error (Reed, NHS Jobs, etc.) | Existing behaviour — log warning, continue |
| Evaluator call fails / bad JSON | Log warning; fall back to unscored full job list in email |
| No jobs after evaluator (all scored 1–2) | Email sent with "No strong matches today" message |

---

## Testing

- Unit tests for `job_planner.py`: mock Claude response, assert SearchPlan structure is valid
- Unit tests for `job_evaluator.py`: mock Claude response, assert scoring and breakdown fields present
- Unit tests for `search_agent.py` pre-filters: assert clinical/below-band jobs are dropped before Claude sees them
- Existing tests for searchers, sponsor_filter, runner unchanged
- No live API calls in tests
