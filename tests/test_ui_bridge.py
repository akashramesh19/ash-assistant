import json
import os
import shutil
import socket
import stat
import tempfile
import time
from pathlib import Path

import pytest

from providers.base import ProviderError
from ui_bridge import UIBridge
from voice_loop import handle_turn


@pytest.fixture
def sock_dir():
    # Unix socket paths are limited to ~100 characters, so pytest's tmp_path is too long.
    folder = Path(tempfile.mkdtemp(prefix="ash", dir="/tmp"))
    yield folder
    shutil.rmtree(folder, ignore_errors=True)


@pytest.fixture
def bridge(sock_dir):
    answers = []
    b = UIBridge(sock_dir / "ui" / "a.sock", on_answer=lambda i, a: answers.append((i, a)), log=lambda line: None)
    b.answers = answers
    b.start()
    yield b
    b.stop()


def connect(bridge):
    client = socket.socket(socket.AF_UNIX)
    client.settimeout(2)
    client.connect(str(bridge.path))
    return client


def read_line(client):
    data = b""
    while not data.endswith(b"\n"):
        data += client.recv(1)
    return json.loads(data)


def wait_for(condition, seconds=2):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_socket_and_folder_are_owner_only(bridge):
    assert stat.S_IMODE(os.stat(bridge.path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(bridge.path.parent).st_mode) == 0o700


def test_events_reach_a_connected_app_as_json_lines(bridge):
    client = connect(bridge)
    assert wait_for(lambda: bridge._client is not None)
    bridge.emit({"type": "reply", "text": "22 and clear, Sir — ünïcode ok"})
    assert read_line(client) == {"type": "reply", "text": "22 and clear, Sir — ünïcode ok"}


def test_emit_with_no_app_connected_is_a_silent_no_op(bridge):
    bridge.emit({"type": "state", "state": "idle"})


def test_a_late_app_is_told_the_latest_state(bridge):
    bridge.emit({"type": "state", "state": "idle"})
    bridge.emit({"type": "state", "state": "thinking"})
    bridge.emit({"type": "reply", "text": "not replayed"})
    client = connect(bridge)
    assert read_line(client) == {"type": "state", "state": "thinking"}


def test_answers_from_the_app_reach_the_callback(bridge):
    client = connect(bridge)
    client.sendall(b'{"type":"answer","id":"c1","answer":"yes"}\n')
    assert wait_for(lambda: bridge.answers == [("c1", "yes")])


@pytest.mark.parametrize("line", [
    b"not json\n",
    b'{"type":"answer","id":"c1","answer":"maybe"}\n',
    b'{"type":"answer","id":7,"answer":"yes"}\n',
    b'{"type":"answer","answer":"yes"}\n',
    b'{"type":"nonsense"}\n',
    b"[1,2,3]\n",
])
def test_malformed_or_unknown_messages_are_ignored(bridge, line):
    client = connect(bridge)
    client.sendall(line + b'{"type":"answer","id":"ok","answer":"no"}\n')
    assert wait_for(lambda: bridge.answers == [("ok", "no")])  # and it kept working afterwards


def test_a_new_app_replaces_the_old_one(bridge):
    first = connect(bridge)
    assert wait_for(lambda: bridge._client is not None)
    second = connect(bridge)
    time.sleep(0.2)
    bridge.emit({"type": "state", "state": "listening"})
    assert read_line(second)["state"] == "listening"
    assert first.recv(10) == b""  # closed by the bridge


def test_a_stalled_reader_is_dropped_instead_of_blocking_emit(bridge):
    client = connect(bridge)
    assert wait_for(lambda: bridge._client is not None)
    bridge._client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
    client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024)
    started = time.time()
    bridge.emit({"type": "reply", "text": "x" * 8000})
    assert time.time() - started < 5
    assert bridge._client is None
    bridge.emit({"type": "state", "state": "idle"})  # a dead UI does not raise, and is not a yes


def test_a_disconnected_app_does_not_break_emit(bridge):
    client = connect(bridge)
    assert wait_for(lambda: bridge._client is not None)
    client.close()
    for _ in range(5):
        bridge.emit({"type": "state", "state": "idle"})
        time.sleep(0.02)


def test_a_probe_that_hangs_up_does_not_stop_accepting(bridge):
    with pytest.raises(RuntimeError, match="already running"):
        UIBridge(bridge.path, log=lambda line: None).start()
    client = connect(bridge)
    deadline = time.time() + 2
    while time.time() < deadline:
        bridge.emit({"type": "state", "state": "idle"})
        client.settimeout(0.1)
        try:
            assert read_line(client)["state"] == "idle"
            return
        except (TimeoutError, socket.timeout):
            continue
    raise AssertionError("accept loop died after the probe hung up")


def test_a_second_agent_refuses_to_start_but_a_stale_file_is_replaced(bridge, sock_dir):
    with pytest.raises(RuntimeError, match="already running"):
        UIBridge(bridge.path, log=lambda line: None).start()
    stale = sock_dir / "stale.sock"
    leftover = socket.socket(socket.AF_UNIX)
    leftover.bind(str(stale))
    leftover.close()  # file remains, nothing is listening
    fresh = UIBridge(stale, log=lambda line: None)
    fresh.start()
    fresh.stop()


def test_stop_removes_the_socket_file(sock_dir):
    b = UIBridge(sock_dir / "s.sock", log=lambda line: None)
    b.start()
    b.stop()
    assert not (sock_dir / "s.sock").exists()


# --- handle_turn events -------------------------------------------------

def turn_events(respond, transcript="what's the weather"):
    events, spoken = [], []
    handle_turn(respond, transcribe=lambda: transcript, say=spoken.append, log=lambda line: None, emit=events.append)
    return events, spoken


def states(events):
    return [e["state"] for e in events if e["type"] == "state"]


def test_a_normal_turn_goes_listening_thinking_reply_idle():
    events, spoken = turn_events(lambda text, on_tool_call=None: "22 and clear.")
    assert states(events) == ["listening", "thinking", "idle"]
    assert {"type": "heard", "text": "what's the weather"} in events
    assert {"type": "reply", "text": "22 and clear."} in events
    assert events[-1] == {"type": "state", "state": "idle"} and spoken == ["22 and clear."]


def test_the_reply_is_shown_before_it_is_spoken():
    order = []
    handle_turn(
        lambda text, on_tool_call=None: "hi",
        transcribe=lambda: "x",
        say=lambda text: order.append("say"),
        log=lambda line: None,
        emit=lambda event: order.append(event["type"] if event["type"] != "state" else event["state"]),
    )
    assert order.index("reply") < order.index("say") < order.index("idle")


def test_an_empty_transcript_returns_to_idle_without_thinking():
    events, spoken = turn_events(lambda *a, **k: "never", transcript="")
    assert states(events) == ["listening", "idle"] and spoken == []


def test_a_model_error_is_reported_and_returns_to_idle():
    def respond(text, on_tool_call=None):
        raise ProviderError("down")

    events, spoken = turn_events(respond)
    assert {"type": "error", "message": "down"} in events
    assert states(events)[-1] == "idle" and spoken == []


def test_a_crash_mid_turn_still_returns_to_idle():
    def respond(text, on_tool_call=None):
        raise RuntimeError("boom")

    events = []
    with pytest.raises(RuntimeError):
        handle_turn(respond, transcribe=lambda: "x", say=lambda t: None, log=lambda l: None, emit=events.append)
    assert states(events)[-1] == "idle"
