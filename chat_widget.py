import streamlit as st
import streamlit.components.v1 as _components

_CSS = """
<style>
#jjs-toggle { display: none; }
#jjs-chat-btn {
  position: fixed; bottom: 24px; right: 24px;
  width: 56px; height: 56px; border-radius: 50%;
  background: #5060cc; color: white; font-size: 24px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0,0,0,0.25);
  z-index: 9999; display: flex; align-items: center; justify-content: center;
  user-select: none;
}
#jjs-chat-panel {
  position: fixed; bottom: 92px; right: 24px;
  width: 680px; height: 840px;
  background: white; border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.15);
  border: 1px solid #e0e4f0;
  flex-direction: column;
  z-index: 9998; overflow: hidden;
  display: none;
}
#jjs-toggle:checked ~ #jjs-chat-panel { display: flex; }
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
  font-size: 18px; line-height: 1.5; white-space: pre-wrap; word-break: break-word;
}
.jjs-msg.user {
  background: #5060cc; color: white;
  align-self: flex-end; border-bottom-right-radius: 2px;
}
.jjs-msg.assistant {
  background: #f0f2ff; color: #222;
  align-self: flex-start; border-bottom-left-radius: 2px;
}

/* Reposition st.chat_input into the floating panel when open.
   Target both the sticky footer wrapper (stBottom) and the widget itself. */
body:has(#jjs-toggle:checked) [data-testid="stBottom"],
body:has(#jjs-toggle:checked) [data-testid="stChatInput"] {
  position: fixed !important;
  bottom: 92px !important;
  right: 24px !important;
  left: auto !important;
  width: 680px !important;
  z-index: 10001 !important;
  border-radius: 0 0 12px 12px !important;
  border-top: 1px solid #e0e4f0 !important;
  background: white !important;
  box-shadow: none !important;
  margin: 0 !important;
  padding: 0 !important;
  pointer-events: auto !important;
  max-width: none !important;
}
body:has(#jjs-toggle:checked) [data-testid="stBottom"] *,
body:has(#jjs-toggle:checked) [data-testid="stChatInput"] * {
  pointer-events: auto !important;
}
/* Hide when panel is closed */
body:not(:has(#jjs-toggle:checked)) [data-testid="stBottom"],
body:not(:has(#jjs-toggle:checked)) [data-testid="stChatInput"] {
  display: none !important;
}
</style>
"""

_HTML = """
<input type="checkbox" id="jjs-toggle">
<label for="jjs-toggle" id="jjs-chat-btn" title="Job Search Assistant">💬</label>
<div id="jjs-chat-panel">
  <div id="jjs-chat-header">💬 Job Search Assistant</div>
  <div id="jjs-chat-messages"></div>
</div>
"""

# Runs in a same-origin iframe; appends new messages to the parent panel.
# Sending is handled natively by st.chat_input() — no JS needed for that.
_JS_TEMPLATE = """
<script>
window.addEventListener('load', function () {{
  var parentWin, doc;
  try {{
    parentWin = window.parent;
    doc = parentWin.document;
  }} catch (e) {{
    return;
  }}

  var STORAGE_KEY = 'job_search_chat_history';
  var MAX_STORED = 50;

  function getLastProcessed() {{
    return parseInt(parentWin.sessionStorage.getItem('jjs_last_counter') || '-1', 10);
  }}
  function setLastProcessed(n) {{
    parentWin.sessionStorage.setItem('jjs_last_counter', String(n));
  }}

  function loadHistory() {{
    try {{ return JSON.parse(parentWin.localStorage.getItem(STORAGE_KEY) || '[]'); }}
    catch (e) {{ return []; }}
  }}
  function saveHistory(h) {{
    try {{ parentWin.localStorage.setItem(STORAGE_KEY, JSON.stringify(h.slice(-MAX_STORED))); }}
    catch (e) {{}}
  }}

  function appendMsg(role, text) {{
    var box = doc.getElementById('jjs-chat-messages');
    if (!box) return;
    var div = doc.createElement('div');
    div.className = 'jjs-msg ' + role;
    div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
  }}

  function processReplyDiv(div) {{
    var counter = parseInt(div.id.replace('chat-reply-', ''), 10);
    if (isNaN(counter) || counter <= getLastProcessed()) return;
    setLastProcessed(counter);
    var replyText = div.textContent.trim();
    if (replyText) {{
      var h = loadHistory();
      h.push({{ role: 'assistant', content: replyText, timestamp: Date.now() }});
      saveHistory(h);
      appendMsg('assistant', replyText);
    }}
  }}

  function watchForReplies() {{
    doc.querySelectorAll('[id^="chat-reply-"]').forEach(processReplyDiv);
    if (parentWin._jjsObserver) parentWin._jjsObserver.disconnect();
    parentWin._jjsObserver = new MutationObserver(function (mutations) {{
      mutations.forEach(function (m) {{
        m.addedNodes.forEach(function (node) {{
          if (node.nodeType !== 1) return;
          if (node.id && node.id.startsWith('chat-reply-')) processReplyDiv(node);
          if (node.querySelectorAll)
            node.querySelectorAll('[id^="chat-reply-"]').forEach(processReplyDiv);
        }});
      }});
    }});
    parentWin._jjsObserver.observe(doc.body, {{ childList: true, subtree: true }});
  }}

  // Pending reply from Python this rerun
  var PENDING_REPLY = {pending_reply_js};
  var PENDING_USER_MSG = {pending_user_msg_js};

  function init() {{
    // Restore history only if messages box is empty
    var box = doc.getElementById('jjs-chat-messages');
    if (box && box.children.length === 0) {{
      loadHistory().forEach(function (msg) {{ appendMsg(msg.role, msg.content); }});
    }}

    // Auto-open if there is history
    if (loadHistory().length > 0) {{
      var toggle = doc.getElementById('jjs-toggle');
      if (toggle && !toggle.checked) toggle.checked = true;
    }}

    // Append user message optimistically (already saved to history by Python)
    if (PENDING_USER_MSG) {{
      var box2 = doc.getElementById('jjs-chat-messages');
      // Only append if not already shown (history restore above may have shown it)
      if (box2) {{
        var last = box2.lastElementChild;
        if (!last || last.textContent !== PENDING_USER_MSG) {{
          appendMsg('user', PENDING_USER_MSG);
          var h = loadHistory();
          var alreadySaved = h.length && h[h.length-1].content === PENDING_USER_MSG && h[h.length-1].role === 'user';
          if (!alreadySaved) {{
            h.push({{ role: 'user', content: PENDING_USER_MSG, timestamp: Date.now() }});
            saveHistory(h);
          }}
        }}
      }}
    }}

    // Append bot reply
    if (PENDING_REPLY) {{
      var counter = {counter};
      if (counter > getLastProcessed()) {{
        setLastProcessed(counter);
        var h2 = loadHistory();
        h2.push({{ role: 'assistant', content: PENDING_REPLY, timestamp: Date.now() }});
        saveHistory(h2);
        appendMsg('assistant', PENDING_REPLY);
      }}
    }}

    watchForReplies();
  }}

  function tryInit() {{
    if (doc.getElementById('jjs-chat-messages')) {{ init(); }}
    else {{ setTimeout(tryInit, 50); }}
  }}

  tryInit();
}});
</script>
"""


def render_chat_widget(
    pending_reply: str | None,
    message_counter: int,
    pending_user_msg: str | None = None,
) -> None:
    import json
    st.markdown(_CSS + _HTML, unsafe_allow_html=True)

    pending_reply_js = json.dumps(pending_reply) if pending_reply is not None else "null"
    pending_user_msg_js = json.dumps(pending_user_msg) if pending_user_msg is not None else "null"

    js = _JS_TEMPLATE.format(
        pending_reply_js=pending_reply_js,
        pending_user_msg_js=pending_user_msg_js,
        counter=message_counter,
    )
    _components.html(js, height=0)
