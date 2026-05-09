# Chatbot Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a floating chat assistant that guides the user through job searching, reads CV context, manipulates the search form, and persists history in localStorage — all compatible with Streamlit Cloud.

**Architecture:** `chatbot.py` handles Claude API calls and action parsing; `chat_widget.py` generates the HTML/CSS/JS for the floating bubble; `app.py` wires the two together via a hidden `st.text_input` (JS→Python) and a hidden `<div>` reply channel (Python→JS). All communication stays in the main Streamlit page DOM — no iframes, no extra servers.

**Tech Stack:** Python, Streamlit, Anthropic SDK (already installed), plain HTML/CSS/JavaScript, browser localStorage.

---

## File Map

| File | Change |
|---|---|
| `chatbot.py` | CREATE — `get_response()` + `apply_actions()` |
| `chat_widget.py` | CREATE — `render_chat_widget()` |
| `tests/test_chatbot.py` | CREATE — unit tests for chatbot module |
| `app.py` | MODIFY — imports, hidden input, message processing, widget call |

---

## Task 1: `chatbot.py` — Tests

**Files:**
- Create: `tests/test_chatbot.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_chatbot.py
import json
from unittest.mock import MagicMock, patch
import pytest
import chatbot


def _mock_claude(text: str):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


# --- get_response ---

@patch("chatbot.anthropic.Anthropic")
def test_get_response_returns_clean_reply(mock_cls):
    mock_cls.return_value.messages.create.return_value = _mock_claude("Hello!")
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}):
        reply, actions = chatbot.get_response("hi", [], None)
    assert reply == "Hello!"
    assert actions == []


@patch("chatbot.anthropic.Anthropic")
def test_get_response_strips_action_tags_from_reply(mock_cls):
    mock_cls.return_value.messages.create.return_value = _mock_claude(
        "Setting queries now. [ACTION:set_queries:Data Engineer|Python Dev]"
    )
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}):
        reply, _ = chatbot.get_response("search", [], None)
    assert "[ACTION:" not in reply
    assert "Setting queries now." in reply


@patch("chatbot.anthropic.Anthropic")
def test_get_response_parses_set_queries(mock_cls):
    mock_cls.return_value.messages.create.return_value = _mock_claude(
        "Done. [ACTION:set_queries:Data Engineer Python|Senior Data Engineer]"
    )
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}):
        _, actions = chatbot.get_response("search for data jobs", [], None)
    assert len(actions) == 1
    assert actions[0]["type"] == "set_queries"
    assert actions[0]["params"] == "Data Engineer Python|Senior Data Engineer"


@patch("chatbot.anthropic.Anthropic")
def test_get_response_parses_multiple_actions(mock_cls):
    mock_cls.return_value.messages.create.return_value = _mock_claude(
        "On it! [ACTION:set_queries:Engineer][ACTION:set_location:London][ACTION:trigger_search]"
    )
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}):
        _, actions = chatbot.get_response("search London", [], None)
    assert len(actions) == 3
    assert actions[0]["type"] == "set_queries"
    assert actions[1]["type"] == "set_location"
    assert actions[2]["type"] == "trigger_search"


@patch("chatbot.anthropic.Anthropic")
def test_get_response_injects_cv_into_system_prompt(mock_cls):
    mock_client = mock_cls.return_value
    mock_client.messages.create.return_value = _mock_claude("OK")
    cv = {
        "job_titles": ["Data Engineer"],
        "skills": ["Python", "SQL"],
        "search_queries": ["Data Engineer Bristol"],
    }
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}):
        chatbot.get_response("help", [], cv)
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "Data Engineer" in call_kwargs["system"]
    assert "Python" in call_kwargs["system"]


@patch("chatbot.anthropic.Anthropic")
def test_get_response_no_cv_omits_cv_section(mock_cls):
    mock_client = mock_cls.return_value
    mock_client.messages.create.return_value = _mock_claude("OK")
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}):
        chatbot.get_response("help", [], None)
    call_kwargs = mock_client.messages.create.call_args.kwargs
    assert "job_titles" not in call_kwargs["system"]


@patch("chatbot.anthropic.Anthropic")
def test_get_response_trims_history_to_20(mock_cls):
    mock_client = mock_cls.return_value
    mock_client.messages.create.return_value = _mock_claude("OK")
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
        for i in range(30)
    ]
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}):
        chatbot.get_response("new", history, None)
    messages = mock_client.messages.create.call_args.kwargs["messages"]
    # 20 from history + 1 new = 21
    assert len(messages) == 21
    # last history message + new message at end
    assert messages[-1] == {"role": "user", "content": "new"}


def test_get_response_raises_without_api_key():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            chatbot.get_response("hi", [], None)


# --- apply_actions ---

def test_apply_actions_set_queries():
    state = {}
    chatbot.apply_actions(
        [{"type": "set_queries", "params": "Data Engineer|Software Engineer"}], state
    )
    assert state["_chat_queries"] == ["Data Engineer", "Software Engineer"]


def test_apply_actions_set_queries_trims_whitespace():
    state = {}
    chatbot.apply_actions([{"type": "set_queries", "params": " Dev Ops | Cloud "}], state)
    assert state["_chat_queries"] == ["Dev Ops", "Cloud"]


def test_apply_actions_set_location():
    state = {}
    chatbot.apply_actions([{"type": "set_location", "params": "London"}], state)
    assert state["_chat_location"] == "London"


def test_apply_actions_set_distance():
    state = {}
    chatbot.apply_actions([{"type": "set_distance", "params": "25"}], state)
    assert state["_chat_distance"] == 25


def test_apply_actions_set_salary():
    state = {}
    chatbot.apply_actions([{"type": "set_salary", "params": "70000"}], state)
    assert state["_chat_salary"] == 70000


def test_apply_actions_invalid_distance_ignored():
    state = {}
    chatbot.apply_actions([{"type": "set_distance", "params": "far"}], state)
    assert "_chat_distance" not in state


def test_apply_actions_invalid_salary_ignored():
    state = {}
    chatbot.apply_actions([{"type": "set_salary", "params": "lots"}], state)
    assert "_chat_salary" not in state


def test_apply_actions_trigger_search_returns_true():
    state = {}
    result = chatbot.apply_actions([{"type": "trigger_search", "params": ""}], state)
    assert result is True


def test_apply_actions_no_trigger_returns_false():
    state = {}
    result = chatbot.apply_actions([{"type": "set_location", "params": "Leeds"}], state)
    assert result is False


def test_apply_actions_multiple_in_one_reply():
    state = {}
    actions = [
        {"type": "set_queries", "params": "Python Dev"},
        {"type": "set_location", "params": "Manchester"},
        {"type": "set_distance", "params": "30"},
    ]
    chatbot.apply_actions(actions, state)
    assert state["_chat_queries"] == ["Python Dev"]
    assert state["_chat_location"] == "Manchester"
    assert state["_chat_distance"] == 30
```

- [ ] **Step 2: Run tests to confirm they fail (module doesn't exist yet)**

```
pytest tests/test_chatbot.py -v
```

Expected: `ModuleNotFoundError: No module named 'chatbot'`

---

## Task 2: `chatbot.py` — Implementation

**Files:**
- Create: `chatbot.py`

- [ ] **Step 1: Write `chatbot.py`**

```python
import os
import re
import anthropic

_SYSTEM_BASE = """\
You are a helpful job search assistant embedded in a UK Skilled Worker visa job finder app.
The app searches LinkedIn, Indeed, Reed, and NHS Jobs, then filters results to only show
employers licensed to sponsor Skilled Worker visas.

You guide the user through the search process and offer practical advice on UK job hunting,
Skilled Worker visa sponsorship, salary expectations, and interview preparation.

You can take actions by including tags in your reply. These tags will be stripped before
the user sees your message. Available actions:

  [ACTION:set_queries:query one|query two|query three]  — set search queries (pipe-separated)
  [ACTION:set_location:City Name]                       — set search location
  [ACTION:set_distance:25]                              — set search radius in miles (integer)
  [ACTION:set_salary:50000]                             — set minimum salary in pounds (integer)
  [ACTION:trigger_search]                               — trigger the search

Rules:
- Never fabricate job listings or sponsor status
- Always use set_queries before trigger_search; if no queries are set, decline trigger_search
  and ask the user to provide at least one search term
- If no CV has been uploaded, prompt the user to upload one when they ask for CV-specific advice
- Keep responses concise and practical
"""

_CV_SECTION = """
The user has uploaded a CV. Here is the extracted analysis:
  Job titles: {job_titles}
  Skills: {skills}
  Suggested search queries: {search_queries}
"""


def _build_system_prompt(cv_analysis: dict | None) -> str:
    if not cv_analysis:
        return _SYSTEM_BASE
    return _SYSTEM_BASE + _CV_SECTION.format(
        job_titles=", ".join(cv_analysis.get("job_titles", [])),
        skills=", ".join(cv_analysis.get("skills", [])),
        search_queries=", ".join(cv_analysis.get("search_queries", [])),
    )


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
    return _ACTION_RE.sub("", text).strip()


def get_response(
    message: str,
    history: list[dict],
    cv_analysis: dict | None,
) -> tuple[str, list[dict]]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Add it to your .env file.")

    client = anthropic.Anthropic(api_key=api_key)
    messages = history[-20:] + [{"role": "user", "content": message}]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=_build_system_prompt(cv_analysis),
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
            session_state["_chat_queries"] = [q.strip() for q in p.split("|") if q.strip()]
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
```

- [ ] **Step 2: Run tests**

```
pytest tests/test_chatbot.py -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add chatbot.py tests/test_chatbot.py
git commit -m "feat: add chatbot module with Claude conversation and action parsing"
```

---

## Task 3: `chat_widget.py` — Floating Bubble Widget

**Files:**
- Create: `chat_widget.py`

The widget uses two mechanisms:
- **JS→Python:** JS finds the hidden Streamlit input (identified by `placeholder="__chat_hidden__"`) and sets its value to `JSON.stringify({text, ts})`, then dispatches a React input event to trigger a rerun.
- **Python→JS:** Python embeds the reply in `<div id="chat-reply-{counter}" data-trigger-search="true/false">`. A `MutationObserver` watches for new reply divs and appends them to the chat panel.
- **trigger_search:** When `data-trigger-search="true"`, JS fires `JSON.stringify({text: "__TRIGGER_SEARCH__", ts: ...})` into the hidden input after showing the reply. Python intercepts `__TRIGGER_SEARCH__` as a special command.

- [ ] **Step 1: Write `chat_widget.py`**

```python
import html as _html
import streamlit as st

_CSS = """
<style>
#jjs-chat-btn {
  position: fixed; bottom: 24px; right: 24px;
  width: 56px; height: 56px; border-radius: 50%;
  background: #5060cc; color: white; font-size: 24px;
  border: none; cursor: pointer;
  box-shadow: 0 4px 12px rgba(0,0,0,0.25);
  z-index: 9999; display: flex; align-items: center; justify-content: center;
}
#jjs-chat-panel {
  position: fixed; bottom: 92px; right: 24px;
  width: 340px; height: 460px;
  background: white; border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.15);
  border: 1px solid #e0e4f0;
  display: flex; flex-direction: column;
  z-index: 9998; overflow: hidden;
}
#jjs-chat-panel.jjs-hidden { display: none; }
#jjs-chat-header {
  background: #5060cc; color: white;
  padding: 12px 16px; font-weight: 600; font-size: 14px;
  flex-shrink: 0;
}
#jjs-chat-messages {
  flex: 1; overflow-y: auto; padding: 12px;
  display: flex; flex-direction: column; gap: 8px;
}
.jjs-msg {
  max-width: 85%; padding: 8px 12px; border-radius: 8px;
  font-size: 13px; line-height: 1.4; white-space: pre-wrap; word-break: break-word;
}
.jjs-msg.user {
  background: #5060cc; color: white;
  align-self: flex-end; border-bottom-right-radius: 2px;
}
.jjs-msg.assistant {
  background: #f0f2ff; color: #222;
  align-self: flex-start; border-bottom-left-radius: 2px;
}
#jjs-chat-input-row {
  display: flex; padding: 10px; gap: 6px;
  border-top: 1px solid #e0e4f0; flex-shrink: 0;
}
#jjs-chat-textarea {
  flex: 1; border: 1px solid #ccc; border-radius: 6px;
  padding: 8px; font-size: 13px; resize: none; outline: none;
  font-family: inherit; height: 38px; min-height: 38px; max-height: 100px;
  overflow-y: auto;
}
#jjs-chat-send {
  background: #5060cc; color: white; border: none;
  border-radius: 6px; padding: 0 14px; cursor: pointer; font-size: 16px;
}
#jjs-chat-send:disabled { opacity: 0.5; cursor: default; }
#jjs-retry-hint {
  font-size: 11px; color: #c0392b; text-align: center;
  padding: 4px 10px; display: none; flex-shrink: 0;
}
/* Hide the Streamlit hidden input wrapper */
[data-testid="stTextInput"]:has(input[placeholder="__chat_hidden__"]) {
  display: none !important;
}
</style>
"""

_HTML = """
<button id="jjs-chat-btn" onclick="jjsToggle()" title="Job Search Assistant">💬</button>
<div id="jjs-chat-panel" class="jjs-hidden">
  <div id="jjs-chat-header">💬 Job Search Assistant</div>
  <div id="jjs-chat-messages"></div>
  <div id="jjs-retry-hint">Couldn't reach the assistant — reload and try again.</div>
  <div id="jjs-chat-input-row">
    <textarea id="jjs-chat-textarea" placeholder="Ask me anything…" rows="1"
      onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();jjsSend();}"></textarea>
    <button id="jjs-chat-send" onclick="jjsSend()">&#10148;</button>
  </div>
</div>
"""

_JS = """
<script>
(function () {
  var STORAGE_KEY = 'job_search_chat_history';
  var MAX_STORED = 50;
  var lastProcessedCounter = -1;
  var waiting = false;

  function loadHistory() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }
    catch (e) { return []; }
  }

  function saveHistory(h) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(h.slice(-MAX_STORED))); }
    catch (e) {}
  }

  function appendMsg(role, text) {
    var box = document.getElementById('jjs-chat-messages');
    if (!box) return;
    var div = document.createElement('div');
    div.className = 'jjs-msg ' + role;
    div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }

  function setWaiting(on) {
    waiting = on;
    var btn = document.getElementById('jjs-chat-send');
    var ta = document.getElementById('jjs-chat-textarea');
    if (btn) btn.disabled = on;
    if (ta) ta.disabled = on;
  }

  function showRetry(on) {
    var el = document.getElementById('jjs-retry-hint');
    if (el) el.style.display = on ? 'block' : 'none';
  }

  window.jjsToggle = function () {
    var panel = document.getElementById('jjs-chat-panel');
    if (panel) panel.classList.toggle('jjs-hidden');
  };

  function findInput() {
    return document.querySelector('input[placeholder="__chat_hidden__"]');
  }

  function fireInput(payload) {
    var el = findInput();
    if (!el) { showRetry(true); return false; }
    var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    setter.call(el, payload);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  }

  window.jjsSend = function () {
    if (waiting) return;
    var ta = document.getElementById('jjs-chat-textarea');
    if (!ta) return;
    var text = ta.value.trim();
    if (!text) return;

    var ok = fireInput(JSON.stringify({ text: text, ts: Date.now() }));
    if (!ok) return;

    var h = loadHistory();
    h.push({ role: 'user', content: text, timestamp: Date.now() });
    saveHistory(h);
    appendMsg('user', text);
    ta.value = '';
    setWaiting(true);
    showRetry(false);
  };

  function processReplyDiv(div) {
    var counter = parseInt(div.id.replace('chat-reply-', ''), 10);
    if (isNaN(counter) || counter <= lastProcessedCounter) return;
    lastProcessedCounter = counter;

    var replyText = div.textContent.trim();
    if (replyText) {
      var h = loadHistory();
      h.push({ role: 'assistant', content: replyText, timestamp: Date.now() });
      saveHistory(h);
      appendMsg('assistant', replyText);
    }
    setWaiting(false);

    if (div.dataset.triggerSearch === 'true') {
      setTimeout(function () {
        fireInput(JSON.stringify({ text: '__TRIGGER_SEARCH__', ts: Date.now() }));
      }, 400);
    }
  }

  function watchForReplies() {
    // Check existing divs (in case reply was rendered before observer set up)
    document.querySelectorAll('[id^="chat-reply-"]').forEach(processReplyDiv);

    var observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        m.addedNodes.forEach(function (node) {
          if (node.nodeType === 1) {
            if (node.id && node.id.startsWith('chat-reply-')) {
              processReplyDiv(node);
            }
            node.querySelectorAll && node.querySelectorAll('[id^="chat-reply-"]').forEach(processReplyDiv);
          }
        });
      });
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  function restoreHistory() {
    loadHistory().forEach(function (msg) { appendMsg(msg.role, msg.content); });
  }

  function init() {
    restoreHistory();
    watchForReplies();
    // Auto-open if user was mid-conversation
    if (loadHistory().length > 0) {
      var panel = document.getElementById('jjs-chat-panel');
      if (panel) panel.classList.remove('jjs-hidden');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    setTimeout(init, 100);
  }
})();
</script>
"""


def render_chat_widget(
    pending_reply: str | None,
    message_counter: int,
    trigger_search: bool = False,
) -> None:
    st.markdown(_CSS + _HTML + _JS, unsafe_allow_html=True)
    if pending_reply is not None:
        safe = _html.escape(pending_reply)
        ts = "true" if trigger_search else "false"
        st.markdown(
            f'<div id="chat-reply-{message_counter}" style="display:none" '
            f'data-trigger-search="{ts}">{safe}</div>',
            unsafe_allow_html=True,
        )
```

- [ ] **Step 2: Run existing tests to confirm nothing is broken**

```
pytest -v
```

Expected: all existing tests pass (no changes to other modules yet).

- [ ] **Step 3: Commit**

```bash
git add chat_widget.py
git commit -m "feat: add chat widget — floating bubble HTML/CSS/JS"
```

---

## Task 4: Wire `app.py` — Message Processing + Widget Injection

**Files:**
- Modify: `app.py`

This task adds:
1. New imports
2. A `_process_chat_message()` helper that runs at the top of each Streamlit render
3. The hidden `st.text_input` channel
4. A call to `render_chat_widget()` placed **before** the State 2 search block (so the reply div is in the DOM before any `st.rerun()` from the search)

- [ ] **Step 1: Add imports**

In [app.py](app.py), find the block that begins:

```python
import cv_parser
import sponsor_filter
from searchers import search_all_streaming
```

Replace it with:

```python
import json
import chatbot
import chat_widget
import cv_parser
import sponsor_filter
from searchers import search_all_streaming
```

- [ ] **Step 2: Add `_process_chat_message()` helper**

In [app.py](app.py), after the `_min_salary_value` function (after line 154) and before the import block, add:

```python
def _process_chat_message() -> None:
    """Read incoming chat message from hidden input, call Claude, apply actions."""
    raw = st.session_state.get("_chat_input", "")
    if not raw or raw == st.session_state.get("_chat_last_seen", ""):
        return

    st.session_state["_chat_last_seen"] = raw

    try:
        payload = json.loads(raw)
        message_text = payload.get("text", "")
    except (json.JSONDecodeError, KeyError):
        message_text = raw

    if not message_text:
        return

    # Special command fired by JS after showing a trigger_search reply
    if message_text == "__TRIGGER_SEARCH__":
        queries = st.session_state.get("_chat_queries", [])
        if queries:
            st.session_state.search_params = {
                "queries": queries,
                "location": st.session_state.get("_chat_location", "Bristol"),
                "distance": int(st.session_state.get("_chat_distance", 50)),
                "min_salary": int(st.session_state.get("_chat_salary", 60000)),
                "platforms": {"LinkedIn + Indeed": True, "Reed": True, "NHS Jobs": True},
            }
            st.session_state.pop("all_jobs", None)
            st.session_state.pop("filtered_jobs", None)
        return

    # Normal chat message — call Claude
    history = st.session_state.get("_chat_history", [])
    cv_analysis = st.session_state.get("cv_analysis")

    try:
        reply, actions = chatbot.get_response(message_text, history, cv_analysis)
    except Exception as e:
        reply = f"Sorry, I couldn't reach the assistant right now. ({e})"
        actions = []

    history.append({"role": "user", "content": message_text})
    history.append({"role": "assistant", "content": reply})
    st.session_state["_chat_history"] = history

    should_trigger = chatbot.apply_actions(actions, st.session_state)

    st.session_state["_chat_reply"] = reply
    st.session_state["_chat_trigger_search"] = should_trigger
    st.session_state["_chat_counter"] = st.session_state.get("_chat_counter", 0) + 1
```

- [ ] **Step 3: Add hidden input and widget call after page title**

In [app.py](app.py), find:

```python
st.set_page_config(page_title="Jie's Job Search", layout="wide")
st.title("Jie's Job Search")
st.caption("Finds UK roles from licensed Skilled Worker visa sponsors only.")
```

Replace with:

```python
st.set_page_config(page_title="Jie's Job Search", layout="wide")
st.title("Jie's Job Search")
st.caption("Finds UK roles from licensed Skilled Worker visa sponsors only.")

# Hidden input: JS writes user messages here to trigger a Streamlit rerun
st.text_input("", key="_chat_input", label_visibility="collapsed", placeholder="__chat_hidden__")

# Process any incoming message before rendering the rest of the page
_process_chat_message()

# Render the chat widget (reply div must be in DOM before the search block can call st.rerun())
chat_widget.render_chat_widget(
    pending_reply=st.session_state.get("_chat_reply"),
    message_counter=st.session_state.get("_chat_counter", 0),
    trigger_search=st.session_state.get("_chat_trigger_search", False),
)
# Clear reply after rendering so it isn't re-shown on subsequent reruns
st.session_state.pop("_chat_reply", None)
st.session_state.pop("_chat_trigger_search", None)
```

- [ ] **Step 4: Run existing tests to confirm nothing is broken**

```
pytest -v
```

Expected: all tests pass.

- [ ] **Step 5: Smoke test — start the app and open it**

```
streamlit run app.py
```

Open `http://localhost:8501`. You should see:
- A blue `💬` button in the bottom-right corner of the page
- Clicking it opens the chat panel
- The chat panel has a text area and send button

You do **not** need the chatbot to work end-to-end yet — just verify the widget renders.

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "feat: wire chat widget into app — hidden input channel and message processing"
```

---

## Task 5: Update `_search_form()` to Read Chat Overrides

**Files:**
- Modify: `app.py` (the `_search_form` function, lines 88–146)

When the bot sets `_chat_queries`, `_chat_location`, etc. via `apply_actions`, the search form should reflect those values as defaults the next time it renders.

- [ ] **Step 1: Update `_search_form` to read `_chat_*` session_state keys**

In [app.py](app.py), find the start of `_search_form`:

```python
def _search_form(key_prefix: str, initial_queries: list[str]) -> None:
    queries_text = st.text_area(
        "Search queries (one per line)",
        value="\n".join(initial_queries),
        height=120,
        placeholder="e.g. Software Engineer\nData Scientist remote UK",
        key=f"{key_prefix}_queries",
    )
    queries = [q.strip() for q in queries_text.splitlines() if q.strip()]

    col1, col2, col3 = st.columns(3)
    with col1:
        location = st.text_input("Location", value="Bristol", key=f"{key_prefix}_location")
    with col2:
        distance = st.number_input("Distance (miles)", value=50, step=10, min_value=1, max_value=500, key=f"{key_prefix}_distance")
    with col3:
        min_salary = st.number_input("Minimum salary (£)", value=60000, step=5000, min_value=0, key=f"{key_prefix}_salary")
```

Replace with:

```python
def _search_form(key_prefix: str, initial_queries: list[str]) -> None:
    chat_queries = st.session_state.get("_chat_queries", [])
    effective_queries = chat_queries if chat_queries else initial_queries

    queries_text = st.text_area(
        "Search queries (one per line)",
        value="\n".join(effective_queries),
        height=120,
        placeholder="e.g. Software Engineer\nData Scientist remote UK",
        key=f"{key_prefix}_queries",
    )
    queries = [q.strip() for q in queries_text.splitlines() if q.strip()]

    col1, col2, col3 = st.columns(3)
    with col1:
        location = st.text_input(
            "Location",
            value=st.session_state.get("_chat_location", "Bristol"),
            key=f"{key_prefix}_location",
        )
    with col2:
        distance = st.number_input(
            "Distance (miles)",
            value=st.session_state.get("_chat_distance", 50),
            step=10, min_value=1, max_value=500,
            key=f"{key_prefix}_distance",
        )
    with col3:
        min_salary = st.number_input(
            "Minimum salary (£)",
            value=st.session_state.get("_chat_salary", 60000),
            step=5000, min_value=0,
            key=f"{key_prefix}_salary",
        )
```

- [ ] **Step 2: Run all tests**

```
pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: End-to-end test — run the app with a real API key**

Start the app:
```
streamlit run app.py
```

Test the following scenarios:

**Scenario A — Basic conversation:**
1. Click the `💬` button to open the chat
2. Type "Hello, what can you do?"
3. The bot should reply describing its capabilities
4. Refresh the page — the conversation history should still be visible

**Scenario B — CV-aware advice:**
1. Upload a CV via the "Upload CV" tab
2. Open the chat and type "What job titles suit my CV?"
3. The bot should reference the CV's extracted job titles in its reply

**Scenario C — Set queries action:**
1. In the chat, type "Search for Python developer jobs in London"
2. The bot should reply and the search query field should update to reflect Python developer queries, and location should change to London

**Scenario D — Trigger search:**
1. In the chat, type "Find me data engineering jobs in Manchester"
2. The bot should set queries and location, then trigger a search automatically
3. The search results should appear

**Scenario E — Error gracefully:**
1. Temporarily unset `ANTHROPIC_API_KEY` in `.env`
2. Send a chat message — the bot should show a friendly error without crashing the main app

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: update search form to reflect chat-applied overrides"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered by |
|---|---|
| Floating chat bubble, bottom-right | Task 3 — `chat_widget.py` CSS `position: fixed` |
| Claude API for conversation | Task 2 — `chatbot.get_response()` |
| CV analysis injected as context | Task 2 — `_build_system_prompt(cv_analysis)` |
| History trimmed to 20 for API | Task 2 — `history[-20:]` |
| localStorage persistence (50 msg cap) | Task 3 — JS `loadHistory`/`saveHistory` |
| Restore history on page load | Task 3 — JS `restoreHistory()` in `init()` |
| Auto-open if prior history | Task 3 — JS checks `loadHistory().length > 0` |
| set_queries action | Task 2 — `apply_actions` + Task 5 — form reads `_chat_queries` |
| set_location action | Task 2 — `apply_actions` + Task 5 — form reads `_chat_location` |
| set_distance action | Task 2 — `apply_actions` + Task 5 — form reads `_chat_distance` |
| set_salary action | Task 2 — `apply_actions` + Task 5 — form reads `_chat_salary` |
| trigger_search action | Task 4 — `__TRIGGER_SEARCH__` special command path |
| Claude API error → friendly message | Task 4 — `_process_chat_message` try/except |
| Hidden input not found → retry hint | Task 3 — JS `showRetry(true)` when `findInput()` returns null |
| localStorage unavailable → silent | Task 3 — JS try/catch in `loadHistory`/`saveHistory` |
| Streamlit Cloud compatible | Task 3 — `st.markdown` not `st.components.v1.html`; no parent frame access |
| No new dependencies | Confirmed — only `html` (stdlib), `json` (stdlib), `re` (stdlib) |
