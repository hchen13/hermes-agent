"""Feishu progress stays editable across interim replies, or goes quiet on lost identity."""

import queue
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import Platform
from gateway.platforms.base import SendResult
from gateway.run_turn_runner import TurnRunner


def _turn(platform=Platform.FEISHU):
    ctx = SimpleNamespace(source=SimpleNamespace(platform=platform, chat_id="oc_chat"),
                          progress_grouping="batch", _progress_metadata=None, _progress_reply_to=None,
                          _cleanup_progress=False, progress_queue=queue.Queue(),
                          last_progress_msg=[None], repeat_count=[0])
    adapter = SimpleNamespace(name="Test", MAX_MESSAGE_LENGTH=4000,
                              send=AsyncMock(return_value=SendResult(success=True, message_id="bubble")),
                              edit_message=AsyncMock(return_value=SendResult(success=True, message_id="bubble")))
    turn = TurnRunner(None, ctx)
    return turn, turn._progress_edit_state(adapter)


@pytest.mark.asyncio
async def test_interim_reply_does_not_forget_editable_bubble():
    turn, st = _turn()
    st.progress_lines.append("first tool")
    await turn._progress_send_or_edit(st, "first tool")
    turn._reset_progress_bubble(st)
    st.progress_lines.append("next tool")
    await turn._progress_send_or_edit(st, "next tool")
    st.adapter.send.assert_awaited_once()
    assert st.adapter.edit_message.await_args.kwargs["message_id"] == "bubble"
    assert st.adapter.edit_message.await_args.kwargs["content"] == "first tool\nnext tool"


@pytest.mark.asyncio
async def test_permanent_edit_failure_silences_rest_of_turn_and_cancel_drain():
    turn, st = _turn()
    st.progress_msg_id = "bubble"
    st.progress_lines = ["tool"]
    st.adapter.edit_message.return_value = SendResult(success=False, error="message not found")
    await turn._progress_send_or_edit(st, "tool")
    turn._ctx.progress_queue.put("another tool")
    turn._reset_progress_bubble(st)
    await turn._progress_send_or_edit(st, "another tool")
    await turn._drain_progress_on_cancel(st)
    assert st.suppressed and turn._ctx.progress_queue.empty()
    st.adapter.send.assert_not_awaited()
    st.adapter.edit_message.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", ["peer closed connection incomplete chunked read", "flood retry after 5"])
async def test_temporary_failure_keeps_same_bubble_without_new_message(error):
    turn, st = _turn()
    st.progress_msg_id = "bubble"
    st.progress_lines = ["tool"]
    st.adapter.edit_message.return_value = SendResult(success=False, error=error)
    assert not await turn._progress_send_or_edit(st, "tool")
    assert st.can_edit and not st.suppressed and st.progress_msg_id == "bubble"
    st.adapter.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_first_send_without_message_id_silences_followups():
    turn, st = _turn()
    st.progress_lines = ["tool"]
    st.adapter.send.return_value = SendResult(success=True)
    await turn._progress_send_or_edit(st, "tool")
    await turn._progress_send_or_edit(st, "more")
    assert st.suppressed
    st.adapter.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_overflow_edit_failure_cannot_spawn_continuations():
    turn, st = _turn()
    st._PROGRESS_TEXT_LIMIT = 12
    st.progress_lines = ["first tool", "second tool"]
    st.progress_msg_id = "bubble"
    st.adapter.edit_message.return_value = SendResult(success=False, error="permission denied")
    assert await turn._roll_progress_overflow_if_needed(st)
    assert st.suppressed
    st.adapter.send.assert_not_awaited()


def test_other_platform_reset_behavior_is_unchanged():
    turn, st = _turn(Platform.TELEGRAM)
    st.progress_msg_id = "bubble"
    st.progress_lines = ["tool"]
    turn._reset_progress_bubble(st)
    assert st.progress_msg_id is None and st.progress_lines == []
