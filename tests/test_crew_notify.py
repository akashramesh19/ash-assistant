import json
import threading
import time
from pathlib import Path

import pytest

from crew import notify as crew_notify
from crew.notify import completion_message, notify, set_notifier
from providers.base import Provider, TurnResult
from tools import crew_status, run_crew
from voice_loop import make_announcer


@pytest.fixture(autouse=True)
def clean(tmp_path, monkeypatch):
    monkeypatch.setenv("ASH_CREW_ROOT", str(tmp_path))
    monkeypatch.setattr(run_crew, "_active", None)
    yield
    set_notifier(None)


def test_messages_come_from_the_outcome():
    assert completion_message({"status": "done"}, "/x/final.md") == ("Your draft is ready, Sir.", "/x/final.md")
    assert "unresearched" in completion_message({"status": "done", "unresearched": True})[0]
    assert "unreviewed" in completion_message({"status": "done-unreviewed"})[0]
    assert "warnings" in completion_message({"status": "done", "warnings": ["w"]})[0]
    message, detail = completion_message({"status": "failed", "failed_stage": "kural", "error": "kural failed: down"})
    assert message == "The draft failed at the kural stage, Sir." and detail == "kural failed: down"


def test_failure_never_claims_the_draft_is_ready():
    assert "ready" not in completion_message({"status": "failed", "failed_stage": "madhi"})[0]


def test_no_notifier_is_a_silent_no_op():
    set_notifier(None)
    notify({"status": "done"})


def test_a_broken_notifier_does_not_raise(capsys):
    def broken(message, detail):
        raise RuntimeError("speaker off")

    set_notifier(broken)
    notify({"status": "done"})
    assert "notification failed" in capsys.readouterr().out


class Quick(Provider):
    name = "claude"

    def replace_history(self, turns):
        pass

    def run_turn(self, user_text, system_prompt, tool_definitions, run_tool, on_tool_call=None):
        if "You are Madhi" in system_prompt:
            return TurnResult(text="Research questions: none")
        if "You are Kural" in system_prompt:
            return TurnResult(text=json.dumps({"verdict": "approved"}))
        return TurnResult(text="# Doc\n\nBody.")


def test_a_finished_run_notifies_with_the_file_path(monkeypatch, tmp_path):
    monkeypatch.setattr(run_crew, "available_providers", lambda: ({"claude": Quick(), "matilda": Quick()}, []))
    got = []
    set_notifier(lambda message, detail: got.append((message, detail)))
    run_crew.run(task="Write X")
    run_crew._active[1].join(5)
    assert got and got[0][0] == "Your draft is ready, Sir." and got[0][1].endswith("final.md")


def test_a_crashed_run_notifies_failure(monkeypatch):
    def boom():
        raise RuntimeError("no providers")

    monkeypatch.setattr(run_crew, "available_providers", boom)
    got = []
    set_notifier(lambda message, detail: got.append(message))
    run_crew.run(task="Write X")
    run_crew._active[1].join(5)
    assert got == ["The draft failed at the start stage, Sir."]


def test_announcer_speaks_and_logs_the_detail():
    said, logs = [], []
    make_announcer(said.append, threading.Lock(), logs.append)("Your draft is ready, Sir.", "/x/final.md")
    assert said == ["Your draft is ready, Sir."] and "/x/final.md" in logs[0]


def test_announcer_waits_for_a_turn_in_progress():
    lock, said = threading.Lock(), []
    announce = make_announcer(said.append, lock, lambda line: None)
    with lock:  # a turn is using the speakers
        thread = threading.Thread(target=announce, args=("done",))
        thread.start()
        time.sleep(0.1)
        assert said == []  # held back
    thread.join(2)
    assert said == ["done"]


def test_status_lists_warnings(tmp_path):
    from crew import runner

    run_dir = runner.prepare_run("T", tmp_path)
    meta = json.loads((run_dir / "run.json").read_text())
    meta.update(status="done", edits_applied=[], edits_skipped=[], flags=[], warnings=["Oli made 7 tool calls; the cap is 5"])
    (run_dir / "run.json").write_text(json.dumps(meta))
    assert "Warning: Oli made 7 tool calls; the cap is 5." in crew_status.run(run_id=run_dir.name)


def test_persona_tells_ash_how_to_handle_a_crew_run():
    persona = (Path(__file__).resolve().parents[1] / "docs" / "persona.md").read_text()
    assert "run_crew" in persona and "crew_status" in persona
    assert "Never say it is finished" in persona
    assert "one spoken sentence" in persona and "straight answer" in persona
    move = persona.split("Just move the damn file already.", 1)[1].split("> User:", 1)[0]
    assert 'Ash: "Moved, Sir."' in move
    assert "second" not in move.lower()
