# Chatbot Assistant — Design Spec

**Date:** 2026-05-09
**Status:** Approved
**Branch:** FE-001-chat-bot

---

## Overview

A floating chat assistant embedded in the existing Streamlit job search app. The bot guides the user through the job search process, offers advice, and can directly manipulate the search form (queries, location, distance, salary) and trigger searches. It has access to the uploaded CV's analysis and persists conversation history across browser sessions via `localStorage`.

---

## Architecture

Three additions to the existing codebase:

```
app.py          ← gains: chat widget injection, hidden input, reply rendering
chatbot.py      ← NEW: Claude conversation management + action parsing
chat_widget.py  ← NEW: generates the HTML/CSS/JS for the floating bubble
```

No new dependencies, no build toolchain, no React code. The widget is pure HTML/CSS/JavaScript injected via `st.markdown(unsafe_allow_html=True)`.

---

## UI

A `position: fixed` chat bubble in the bottom-right corner of the page. Clicking it opens/collapses a chat panel. The bubble and panel render directly in the Streamlit page DOM (not in an iframe), so `position: fixed` is relative to the visible viewport — this is compatible with Streamlit Cloud deployment.

The widget is injected on every Streamlit render via `st.markdown`. Its visual state (open/closed, scroll position) is managed entirely in JS — Streamlit reruns do not reset it.

---

## Communication Channels

### JS → Python (user sends a message)

A hidden `st.text_input` with key `_chat_input` is rendered in `app.py` and visually suppressed via injected CSS. When the user sends a message, the widget JS:

1. Sets the input's value using React's native property setter (bypasses React's synthetic event system)
2. Dispatches a bubbling `input` event
3. Streamlit detects the change on the next rerun

```javascript
const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
setter.call(inputEl, message);
inputEl.dispatchEvent(new Event('input', { bubbles: true }));
```

If the hidden input is not found in the DOM, JS logs a console warning and shows a visible "retry" hint in the chat panel.

### Python → JS (bot reply)

After processing, Python writes the reply into a hidden `<div>` with a unique ID based on a session-scoped message counter:

```html
<div id="chat-reply-{counter}" style="display:none">{reply_text}</div>
```

A `MutationObserver` in the widget JS watches for this div to appear, extracts the reply, appends it to the chat panel, and saves the updated history to `localStorage`.

---

## Modules

### `chatbot.py`

```python
def get_response(
    message: str,
    history: list[dict],   # [{role: "user"|"assistant", content: str}]
    cv_analysis: dict | None,
) -> tuple[str, list[dict]]:
    ...
    # returns (reply_text_with_actions_stripped, parsed_actions)
```

- Builds a system prompt incorporating CV context (if available)
- Passes `history` (last 20 messages) to the Claude messages API
- Parses `[ACTION:...]` tags from the raw response before returning the display text
- Returns `(clean_reply, actions)` where `actions` is a list of `{type, params}` dicts

**System prompt includes:**
- Role: UK job search assistant for a Skilled Worker visa job finder
- CV context: job titles, skills, search queries (omitted if no CV uploaded)
- Available actions and their syntax
- Instruction to stay grounded — never fabricate job listings or sponsor status

### `chat_widget.py`

```python
def render_chat_widget(pending_reply: str | None, message_counter: int) -> None:
    ...
    # calls st.markdown(unsafe_allow_html=True) with the full widget HTML/CSS/JS
```

Accepts `pending_reply` (the latest bot message to embed in the hidden reply div, or `None`) and `message_counter` (unique ID for the reply div). All widget markup is generated here; `app.py` just calls this function.

---

## Bot Actions

Claude outputs action tags inline in its response. Python strips them before displaying the reply.

| Tag | Effect |
|---|---|
| `[ACTION:set_queries:query one\|query two]` | Sets `st.session_state._chat_queries` |
| `[ACTION:set_location:Bristol]` | Sets `st.session_state._chat_location` |
| `[ACTION:set_distance:25]` | Sets `st.session_state._chat_distance` |
| `[ACTION:set_salary:50000]` | Sets `st.session_state._chat_salary` |
| `[ACTION:trigger_search]` | Assembles `search_params` from current chat overrides and calls `st.rerun()` |

Multiple actions may appear in one reply. `trigger_search` is a no-op if no queries are set — the bot is instructed to set queries before triggering.

The existing `_search_form()` function is updated to check for `_chat_*` session_state overrides and use them as default values, so the form reflects bot-applied values when it next renders.

---

## CV Access

If `st.session_state.cv_analysis` exists, `chatbot.get_response()` injects its contents (job_titles, skills, search_queries) into the system prompt. Claude uses this to give CV-specific advice and generate relevant action suggestions.

If no CV is uploaded, the bot works normally for general advice and prompts the user to upload a CV when asked for CV-specific guidance.

CV analysis is **not** persisted to `localStorage` — it lives in Streamlit session_state and is re-read each call.

---

## Persistence

- `localStorage` key: `job_search_chat_history`
- Format: JSON array of `{role, content, timestamp}` objects
- Restored on every page load by the widget JS
- Capped at **50 messages** in storage; trimmed from the oldest end when exceeded
- Claude API calls use the last **20 messages** from history to bound token usage
- If `localStorage` is unavailable (e.g. private browsing), the chat functions normally for the session with no error shown

---

## Changes to `app.py`

1. Import `chatbot` and `chat_widget`
2. Initialise session_state keys: `_chat_input`, `_chat_reply`, `_chat_counter`, `_chat_queries`, `_chat_location`, `_chat_distance`, `_chat_salary`
3. Render hidden `st.text_input(key="_chat_input", label="", label_visibility="collapsed")`; suppress it visually via injected CSS
4. On each rerun, check if `_chat_input` has a new value:
   - Call `chatbot.get_response()`
   - Apply returned actions to session_state
   - Store reply in `_chat_reply`, increment `_chat_counter`
   - Clear `_chat_input` to avoid re-processing on the next rerun
5. Call `chat_widget.render_chat_widget(pending_reply, counter)` once, near the bottom of the script
6. Update `_search_form()` to read `_chat_*` session_state overrides as default values

---

## Error Handling

| Failure | Behaviour |
|---|---|
| Claude API error | Bot replies with a friendly error in the chat panel; main app unaffected |
| Action parse failure | Action silently skipped; reply text still shown |
| `trigger_search` with no queries | Bot declines and asks user to set at least one query first |
| `localStorage` unavailable | Chat works for session; history not saved; no error shown |
| Hidden input not found in DOM | JS console warning; "retry" hint shown in chat panel |

---

## Testing

- Unit tests for `chatbot.py`: mock Claude API, assert correct action parsing for each action type, assert CV context appears in system prompt when provided, assert history is truncated to 20 messages
- Unit tests for action application in `app.py`: assert session_state keys are set correctly for each action type
- No live API calls in tests
- Widget HTML/JS is not unit tested (plain JS, no build toolchain)

---

## Out of Scope

- Saving conversation history server-side
- Multi-user conversation isolation (this is a single-user local/Streamlit Cloud app)
- Voice input
- The bot proactively sending messages unprompted
