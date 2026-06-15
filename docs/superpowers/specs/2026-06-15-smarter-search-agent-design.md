# Smarter Search Agent — Design Spec

**Date:** 2026-06-15
**Branch:** feature/FE-004-smarter-searching

---

## Overview

Replace the static `search_queries` in the daily digest with an autonomous Claude agent that reasons from a structured candidate profile and iteratively refines its searches until it is satisfied with the quality of results. The agent uses Claude's tool use API, calling a `search_jobs` tool as many times as it judges necessary (up to a safety cap of 5), then emits a brief strategy note summarising what it tried. Everything downstream — sponsor filtering, deduplication, email formatting — is unchanged.

---

## Architecture

### Changed file: `digest_config.yaml`

Add an optional `profile` block. If present, the agent path is used. If absent, the existing `search_queries` fallback runs unchanged.

```yaml
profile:
  name: Jie
  current_role: Operations Director
  seniority: Senior / Director
  industry: NHS / Healthcare / Public Sector
  skills:
    - stakeholder management
    - digital transformation
    - budget control
    - programme delivery
  previous_roles:
    - Business Manager
    - Project Manager
    - Service Improvement Lead
  target_roles:
    - Operations Director
    - Programme Director
    - Digital Transformation Lead
  open_to:
    - Strategy Consultant
    - Head of Operations
    - Deputy Director

location: Bristol
min_salary: 60000
preamble: ""          # optional one-off announcement, unchanged
```

`search_queries` becomes optional — only needed as a fallback when `profile` is absent.

---

### New file: `search_agent.py`

Owns the agentic search loop entirely. One public function:

**`run_search_agent(profile: dict, location: str, min_salary: int) -> tuple[list[dict], str]`**

Returns `(sponsored_jobs, strategy_note)` where:
- `sponsored_jobs` — deduplicated list of job dicts from all rounds that passed the sponsor filter
- `strategy_note` — the agent's final text block, used as the email summary

**Tool definition:**

```python
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
                "description": "Search queries to run. Each is a job title or keyword combination."
            },
            "location": {
                "type": "string",
                "description": "Location to search. Defaults to the candidate's preferred location if omitted."
            },
            "distance": {
                "type": "integer",
                "description": "Search radius in miles. Default 50."
            }
        },
        "required": ["queries"]
    }
}
```

**System prompt:**

```
You are an autonomous job search agent for {name}. Your goal is to find the best-matching
jobs from employers licensed to sponsor UK Skilled Worker visas.

Candidate profile:
- Current role: {current_role}
- Seniority: {seniority}
- Industry: {industry}
- Key skills: {skills}
- Previous roles: {previous_roles}
- Target roles: {target_roles}
- Open to: {open_to}
- Preferred locations: {preferred_locations}
- Minimum salary: £{min_salary:,}

Use the search_jobs tool to find matching roles. You may call it multiple times to explore
different angles — exact job titles, adjacent roles, transferable skills, different locations.

After each round, assess whether the results are a good match for the candidate's seniority,
salary expectations, and background. If not, refine your queries and search again.

When you are satisfied with the results, stop calling the tool and write a 2–3 sentence
strategy note summarising what angles you explored and what you found. Be specific.

You have a maximum of 5 search rounds.
```

**Agent loop:**

```python
MAX_ROUNDS = 5
messages = [{"role": "user", "content": "Find the best matching jobs for this candidate."}]
all_sponsored: list[dict] = []
seen_urls: set[str] = set()
sponsor_names = sponsor_filter.load_sponsor_names()

for _ in range(MAX_ROUNDS):
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system_prompt,
        tools=[SEARCH_TOOL],
        messages=messages,
    )

    # Collect any text blocks
    # Execute any tool calls
    # If stop_reason == "end_turn" (no tool use), break

    # For each tool_use block:
    #   run search_all_streaming with the given queries/location/distance
    #   filter by sponsor list
    #   deduplicate into all_sponsored
    #   append tool_result to messages so Claude sees the output

# Final text block from the last response = strategy_note
```

**Tool result format returned to Claude:**

```
Found {n} sponsored jobs:
1. {title} at {company} ({location}) — {salary} [{source}]
2. ...

(or: "No sponsored jobs found for these queries.")
```

This gives Claude concrete signal to reason about quality before deciding whether to refine.

---

### Changed file: `digest.py`

Import `search_agent`. In `main()`, branch on whether `profile` is present in config:

```python
def main() -> None:
    config = load_config()

    if "profile" in config:
        filtered, summary = search_agent.run_search_agent(
            config["profile"], config["location"], config["min_salary"]
        )
    else:
        jobs = collect_jobs(config["search_queries"], config["location"], config["min_salary"])
        sponsor_names = sponsor_filter.load_sponsor_names()
        filtered = sponsor_filter.filter_jobs(jobs, sponsor_names)
        summary = analyse_results(filtered, config) if filtered else "No matching roles found today."

    today = date.today().strftime("%d %B %Y")
    count = len(filtered)
    subject = f"Job digest — {count} match{'es' if count != 1 else ''} — {today}"
    preamble = config.get("preamble", "")
    html_body = format_email_html(filtered, summary, today, preamble)
    send_email(...)
```

`collect_jobs`, `analyse_results`, and `format_email_html` are unchanged. The strategy note from the agent slots directly into the `summary` argument.

---

## Data Flow

```
digest_config.yaml (profile block)
        │
        ▼
search_agent.run_search_agent()
        │
        ├── Build system prompt from profile
        ├── Round 1: Claude → search_jobs(queries, location, distance)
        │       └── search_all_streaming → sponsor_filter → results back to Claude
        ├── Round 2 (if Claude refines): search_jobs(new_queries, ...)
        │       └── ...
        └── Claude stops → final text = strategy_note
        │
        ▼
(sponsored_jobs, strategy_note)
        │
        ▼
format_email_html(jobs, strategy_note, today, preamble)
        │
        ▼
send_email(...)
```

---

## Email Output

Same HTML table format as today. The strategy note (agent's final text) appears above the table where the Claude-generated summary used to appear. The `preamble` field still renders above the strategy note for one-off announcements.

Example strategy note the agent might produce:

> *Searched three angles this run: senior NHS operations roles near Bristol, digital transformation director positions across the South West, and programme director roles in public sector. Round 1 was sparse (3 results), so round 2 broadened the search radius to 75 miles. Round 3 drew on the project management background with adjacent queries. 14 sponsored roles found across all rounds.*

---

## Error Handling

| Failure | Behaviour |
|---|---|
| `ANTHROPIC_API_KEY` not set | `RuntimeError` — same as existing digest behaviour |
| All search rounds return 0 results | Agent stops naturally; strategy note explains; empty table in email |
| Max rounds (5) hit without Claude stopping | Loop exits; all results collected so far are used |
| A single platform search fails | Logged as warning, other platforms continue — same as current `search_all_streaming` behaviour |
| Claude returns malformed tool input | `KeyError` / `ValidationError` propagated; digest fails with stack trace |

---

## Backwards Compatibility

If `profile` is absent from `digest_config.yaml`, the digest runs exactly as today using `search_queries`. No existing behaviour changes until a `profile` block is added to the config.

---

## Out of Scope

- Changes to the Streamlit app UI
- Scraping LinkedIn (profile text is hardcoded in config)
- Per-round result storage or search history
- Personalised email formatting beyond the strategy note
- Scoring or ranking results by match quality
