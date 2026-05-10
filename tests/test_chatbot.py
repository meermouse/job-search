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


@patch("chatbot.anthropic.Anthropic")
def test_get_response_no_double_spaces_after_strip(mock_cls):
    mock_cls.return_value.messages.create.return_value = _mock_claude(
        "I'll set that up [ACTION:set_location:London] for you now."
    )
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}):
        reply, _ = chatbot.get_response("go to London", [], None)
    assert "  " not in reply
    assert reply == "I'll set that up for you now."


def test_apply_actions_set_queries_all_blank_ignored():
    state = {}
    chatbot.apply_actions([{"type": "set_queries", "params": "| |  "}], state)
    assert "_chat_queries" not in state


@patch("chatbot.anthropic.Anthropic")
def test_get_response_history_window_starts_with_user(mock_cls):
    mock_client = mock_cls.return_value
    mock_client.messages.create.return_value = _mock_claude("OK")
    # 21 messages: indices 0-20, starting with user (0), so history[-20:] = indices 1-20
    # Index 1 is "assistant" — the window would start on assistant without the fix
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
        for i in range(21)
    ]
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "key"}):
        chatbot.get_response("new", history, None)
    messages = mock_client.messages.create.call_args.kwargs["messages"]
    assert messages[0]["role"] == "user"
