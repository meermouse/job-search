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
