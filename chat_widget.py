import streamlit as st
import streamlit.components.v1 as _components

# Only CSS lives here — all HTML is created by JS and appended to document.body
# so the panel sits OUTSIDE Streamlit's app container and is unaffected by its
# loading overlay / opacity changes.
_CSS = """
<style>
#jjs-toggle { display: none; }
#jjs-chat-btn {
  position: fixed; bottom: 24px; right: 24px;
  width: 56px; height: 56px; border-radius: 50%;
  background: #5060cc; color: white; font-size: 24px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0,0,0,0.25);
  z-index: 999999; display: flex; align-items: center; justify-content: center;
  user-select: none;
}
#jjs-chat-panel {
  position: fixed; bottom: 92px; right: 24px;
  width: 680px; height: 840px;
  background: white; border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.15);
  border: 1px solid #e0e4f0;
  flex-direction: column;
  z-index: 999998; overflow: hidden;
  display: none;
}
body.jjs-chat-open #jjs-chat-panel { display: flex; }
#jjs-chat-header {
  background: #5060cc; color: white;
  padding: 12px 16px; font-weight: 600; font-size: 14px;
  flex-shrink: 0; display: flex; align-items: center;
}
#jjs-clear-btn {
  margin-left: auto; background: none; border: none;
  color: rgba(255,255,255,0.75); cursor: pointer;
  font-size: 17px; padding: 3px 7px; border-radius: 6px; line-height: 1;
}
#jjs-clear-btn:hover { background: rgba(255,255,255,0.2); color: white; }
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
/* Confirmation modal */
#jjs-modal-overlay {
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,0.45); z-index: 9999999;
  align-items: center; justify-content: center;
}
#jjs-modal-overlay.jjs-open { display: flex; }
#jjs-modal-box {
  background: white; border-radius: 14px;
  padding: 28px 24px 22px; width: 300px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.25); text-align: center;
}
#jjs-modal-box h3 { margin: 0 0 10px; font-size: 17px; color: #1a1a2e; }
#jjs-modal-box p  { margin: 0 0 22px; font-size: 14px; color: #555; line-height: 1.5; }
.jjs-modal-btns { display: flex; gap: 10px; justify-content: center; }
.jjs-modal-btns button {
  flex: 1; padding: 9px 16px; border: none;
  border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer;
}
#jjs-modal-cancel  { background: #eee; color: #444; }
#jjs-modal-confirm { background: #d63031; color: white; }
#jjs-modal-cancel:hover  { background: #ddd; }
#jjs-modal-confirm:hover { background: #b71c1c; }
/* Typing indicator (manual messages) */
#jjs-typing { align-self: flex-start; padding: 10px 14px; }
@keyframes jjs-blink {
  0%, 80%, 100% { opacity: 0.2; transform: scale(0.75); }
  40%           { opacity: 1;   transform: scale(1); }
}
.jjs-dot {
  display: inline-block; width: 9px; height: 9px; border-radius: 50%;
  background: #8892cc; margin: 0 3px;
  animation: jjs-blink 1.4s infinite;
}
.jjs-dot:nth-child(2) { animation-delay: 0.2s; }
.jjs-dot:nth-child(3) { animation-delay: 0.4s; }
/* Thinking state: animated border + small header spinner */
@keyframes jjs-spin { to { transform: rotate(360deg); } }
#jjs-chat-panel.jjs-thinking {
  border-color: #5060cc;
  box-shadow: 0 0 0 3px rgba(80,96,204,0.18), 0 8px 32px rgba(0,0,0,0.15);
}
#jjs-header-spinner {
  display: none; flex-shrink: 0;
  width: 14px; height: 14px; margin-left: 8px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: white; border-radius: 50%;
  animation: jjs-spin 0.7s linear infinite;
}
#jjs-chat-panel.jjs-thinking #jjs-header-spinner { display: block; }

/* Dock st.chat_input at the panel bottom when open */
body.jjs-chat-open [data-testid="stBottom"],
body.jjs-chat-open [data-testid="stChatInput"] {
  position: fixed !important;
  bottom: 92px !important; right: 24px !important; left: auto !important;
  width: 680px !important; z-index: 999999 !important;
  border-radius: 0 0 12px 12px !important;
  border-top: 1px solid #e0e4f0 !important;
  background: white !important; box-shadow: none !important;
  margin: 0 !important; padding: 0 !important;
  pointer-events: auto !important; max-width: none !important;
}
body.jjs-chat-open [data-testid="stBottom"] *,
body.jjs-chat-open [data-testid="stChatInput"] * { pointer-events: auto !important; }
body:not(.jjs-chat-open) [data-testid="stBottom"],
body:not(.jjs-chat-open) [data-testid="stChatInput"] { display: none !important; }
</style>
"""

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

  function showTypingIndicator() {{
    var panel = doc.getElementById('jjs-chat-panel');
    if (panel) panel.classList.add('jjs-thinking');
    if (doc.getElementById('jjs-typing')) return;
    var box = doc.getElementById('jjs-chat-messages');
    if (!box) return;
    var el = doc.createElement('div');
    el.id = 'jjs-typing'; el.className = 'jjs-msg assistant';
    el.innerHTML = '<span class="jjs-dot"></span><span class="jjs-dot"></span><span class="jjs-dot"></span>';
    box.appendChild(el);
    box.scrollTop = box.scrollHeight;
  }}

  function removeTypingIndicator() {{
    var el = doc.getElementById('jjs-typing');
    if (el) el.parentNode.removeChild(el);
    var panel = doc.getElementById('jjs-chat-panel');
    if (panel) panel.classList.remove('jjs-thinking');
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

  // Create all panel DOM elements and append directly to document.body so they
  // live outside Streamlit's app container and are immune to its loading overlay.
  function createChatUI() {{
    if (doc.getElementById('jjs-chat-panel')) return;

    var toggle = doc.createElement('input');
    toggle.type = 'checkbox'; toggle.id = 'jjs-toggle'; toggle.style.display = 'none';
    doc.body.appendChild(toggle);

    var btn = doc.createElement('label');
    btn.setAttribute('for', 'jjs-toggle');
    btn.id = 'jjs-chat-btn'; btn.title = 'Job Search Assistant'; btn.textContent = '💬';
    doc.body.appendChild(btn);

    var panel = doc.createElement('div');
    panel.id = 'jjs-chat-panel';

    var header = doc.createElement('div');
    header.id = 'jjs-chat-header';
    var title = doc.createElement('span');
    title.textContent = '💬 Job Search Assistant';
    var clearBtn = doc.createElement('button');
    clearBtn.id = 'jjs-clear-btn'; clearBtn.title = 'Clear chat history';
    clearBtn.textContent = '🗑';
    var headerSpinner = doc.createElement('div');
    headerSpinner.id = 'jjs-header-spinner';
    header.appendChild(title); header.appendChild(headerSpinner); header.appendChild(clearBtn);

    var messages = doc.createElement('div');
    messages.id = 'jjs-chat-messages';

    panel.appendChild(header); panel.appendChild(messages);
    doc.body.appendChild(panel);

    var overlay = doc.createElement('div');
    overlay.id = 'jjs-modal-overlay';
    var box = doc.createElement('div');
    box.id = 'jjs-modal-box';
    box.innerHTML = '<h3>Clear chat history?</h3>'
      + '<p>All messages will be deleted and the page will reload for a fresh session.</p>'
      + '<div class="jjs-modal-btns">'
      + '<button id="jjs-modal-cancel">Cancel</button>'
      + '<button id="jjs-modal-confirm">Clear</button>'
      + '</div>';
    overlay.appendChild(box);
    doc.body.appendChild(overlay);

    // Capture-phase keydown fires before React — intercept Enter in the chat textarea
    // to show the user message + typing indicator before Streamlit reruns.
    function handleChatSubmit(text) {{
      if (!text) return;
      var msgBox = doc.getElementById('jjs-chat-messages');
      var alreadyShown = false;
      if (msgBox) {{
        for (var i = 0; i < msgBox.children.length; i++) {{
          if (msgBox.children[i].classList.contains('user') && msgBox.children[i].textContent === text) {{
            alreadyShown = true; break;
          }}
        }}
      }}
      if (!alreadyShown) {{
        appendMsg('user', text);
        var h = loadHistory();
        h.push({{ role: 'user', content: text, timestamp: Date.now() }});
        saveHistory(h);
      }}
      showTypingIndicator();
    }}

    doc.addEventListener('keydown', function (e) {{
      if (e.key !== 'Enter' || e.shiftKey) return;
      var t = e.target;
      var inChat = false;
      while (t) {{
        if (t.getAttribute && (
          t.getAttribute('data-testid') === 'stChatInput' ||
          t.getAttribute('data-testid') === 'stBottom'
        )) {{ inChat = true; break; }}
        t = t.parentElement;
      }}
      if (!inChat) return;
      var text = e.target.value ? e.target.value.trim() : '';
      handleChatSubmit(text);
    }}, true); // capture phase — fires before React

    // Also handle send-button click
    doc.addEventListener('click', function (e) {{
      var t = e.target;
      while (t) {{
        if (t.tagName === 'BUTTON' && (t.type === 'submit' || t.getAttribute('aria-label'))) {{
          var p = t;
          var inChat = false;
          while (p) {{
            if (p.getAttribute && (
              p.getAttribute('data-testid') === 'stChatInput' ||
              p.getAttribute('data-testid') === 'stBottom'
            )) {{ inChat = true; break; }}
            p = p.parentElement;
          }}
          if (inChat) {{
            var form = t.closest ? t.closest('form') : null;
            var input = form ? form.querySelector('textarea, input') : null;
            var text = input && input.value ? input.value.trim() : '';
            handleChatSubmit(text);
          }}
          break;
        }}
        t = t.parentElement;
      }}
    }}, true);
  }}

  var PENDING_REPLY = {pending_reply_js};
  var PENDING_USER_MSG = {pending_user_msg_js};
  var IS_LOADING = {is_loading_js};

  function init() {{
    // Remove any typing indicator left from the previous submission
    removeTypingIndicator();

    // Restore history only if messages box is empty
    var box = doc.getElementById('jjs-chat-messages');
    if (box && box.children.length === 0) {{
      loadHistory().forEach(function (msg) {{ appendMsg(msg.role, msg.content); }});
    }}

    // Append user message if not already visible (submit listener may have added it)
    if (PENDING_USER_MSG) {{
      var box2 = doc.getElementById('jjs-chat-messages');
      var alreadyShown = false;
      if (box2) {{
        for (var i = 0; i < box2.children.length; i++) {{
          if (box2.children[i].classList.contains('user') && box2.children[i].textContent === PENDING_USER_MSG) {{
            alreadyShown = true; break;
          }}
        }}
        if (!alreadyShown) {{
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

    // Sync body.jjs-chat-open with the toggle AFTER content is saved to localStorage,
    // so the auto-open check sees the new message even on the first bot-initiated reply.
    var toggle = doc.getElementById('jjs-toggle');
    if (toggle) {{
      if (loadHistory().length > 0 && !toggle.checked) toggle.checked = true;
      doc.body.classList.toggle('jjs-chat-open', toggle.checked);
      toggle.addEventListener('change', function () {{
        doc.body.classList.toggle('jjs-chat-open', toggle.checked);
      }});
    }}

    // If Python is mid-computation (auto-ack), show thinking style and open panel
    var panel = doc.getElementById('jjs-chat-panel');
    if (IS_LOADING) {{
      showTypingIndicator();
      if (toggle && !toggle.checked) {{
        toggle.checked = true;
        doc.body.classList.add('jjs-chat-open');
      }}
    }}

    watchForReplies();

    // Clear button + confirmation modal
    var clearBtn  = doc.getElementById('jjs-clear-btn');
    var overlay   = doc.getElementById('jjs-modal-overlay');
    var cancelBtn = doc.getElementById('jjs-modal-cancel');
    var confirmBtn = doc.getElementById('jjs-modal-confirm');

    function showModal() {{ if (overlay) overlay.classList.add('jjs-open'); }}
    function hideModal() {{ if (overlay) overlay.classList.remove('jjs-open'); }}

    if (clearBtn)   clearBtn.onclick   = function (e) {{ e.stopPropagation(); showModal(); }};
    if (cancelBtn)  cancelBtn.onclick  = hideModal;
    if (overlay)    overlay.onclick    = function (e) {{ if (e.target === overlay) hideModal(); }};
    if (confirmBtn) confirmBtn.onclick = function () {{
      hideModal();
      parentWin.localStorage.removeItem(STORAGE_KEY);
      parentWin.sessionStorage.removeItem('jjs_last_counter');
      parentWin.location.reload();
    }};
  }}

  function tryInit() {{
    createChatUI();
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
    is_loading: bool = False,
) -> None:
    import json
    st.markdown(_CSS, unsafe_allow_html=True)

    pending_reply_js = json.dumps(pending_reply) if pending_reply is not None else "null"
    pending_user_msg_js = json.dumps(pending_user_msg) if pending_user_msg is not None else "null"
    is_loading_js = json.dumps(is_loading)

    js = _JS_TEMPLATE.format(
        pending_reply_js=pending_reply_js,
        pending_user_msg_js=pending_user_msg_js,
        is_loading_js=is_loading_js,
        counter=message_counter,
    )
    _components.html(js, height=0)
