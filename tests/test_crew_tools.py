import json
import threading
import time

import pytest

from crew import runner
from tools import TOOLS, crew_status, run_crew
from providers.base import Provider, TurnResult


@pytest.fixture(autouse=True)
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setenv("ASH_CREW_ROOT", str(tmp_path))
    monkeypatch.setattr(run_crew, "_active", None)
    return tmp_path


class Quick(Provider):
    def __init__(self, name, gate=None):
        self.name, self.gate = name, gate

    def replace_history(self, turns):
        pass

    def run_turn(self, user_text, system_prompt, tool_definitions, run_tool, on_tool_call=None):
        if self.gate:
            self.gate.wait(5)
        if "You are Madhi" in system_prompt:
            return TurnResult(text="Research questions: none")
        if "You are Kural" in system_prompt:
            return TurnResult(text=json.dumps({"verdict": "approved"}))
        return TurnResult(text="# Doc\n\nBody text here.")


def use_providers(monkeypatch, gate=None):
    monkeypatch.setattr(run_crew, "available_providers", lambda: ({"claude": Quick("claude", gate), "matilda": Quick("matilda")}, []))


def wait_done():
    thread = run_crew._active[1]
    thread.join(5)
    assert not thread.is_alive()


def test_tools_are_registered_with_neutral_definitions():
    for name in ("run_crew", "crew_status"):
        assert TOOLS[name].TOOL_DEFINITION["name"] == name
        assert "parameters" in TOOLS[name].TOOL_DEFINITION


def test_run_crew_returns_immediately_then_finishes_in_the_background(monkeypatch, sandbox):
    gate = threading.Event()
    use_providers(monkeypatch, gate)
    started = time.perf_counter()
    reply = run_crew.run(task="Write a README for X")
    assert time.perf_counter() - started < 1 and reply.startswith("Started crew run")
    status = crew_status.run()
    assert "running" in status or "queued" in status

    gate.set()
    wait_done()
    status = crew_status.run()
    assert "done" in status and "final.md" in status
    run_id = reply.split("run ")[1].split(". ")[0].strip()
    assert (sandbox / run_id / "final.md").read_text().startswith("# Doc")


def test_only_one_run_at_a_time(monkeypatch):
    gate = threading.Event()
    use_providers(monkeypatch, gate)
    run_crew.run(task="First")
    assert "already in progress" in run_crew.run(task="Second")
    gate.set()
    wait_done()
    assert run_crew.run(task="Third").startswith("Started")
    wait_done()


@pytest.mark.parametrize("task", ["", "   ", None])
def test_empty_task_is_rejected_without_creating_a_run(task, sandbox):
    assert run_crew.run(task=task).startswith("error")
    assert list(sandbox.iterdir()) == []


def test_overlong_task_is_rejected(sandbox):
    assert "too long" in run_crew.run(task="x" * 5000)
    assert list(sandbox.iterdir()) == []


def test_a_crash_in_the_worker_is_recorded_not_lost(monkeypatch):
    def boom():
        raise RuntimeError("no providers")

    monkeypatch.setattr(run_crew, "available_providers", boom)
    run_crew.run(task="Anything")
    wait_done()
    status = crew_status.run()
    assert "failed" in status and "no providers" in status


def test_crew_status_with_no_runs():
    assert crew_status.run() == "No crew runs yet."


def test_crew_status_rejects_ids_that_escape_the_folder():
    assert crew_status.run(run_id="../../etc").startswith("error")


def test_crew_status_unknown_id():
    assert "no crew run" in crew_status.run(run_id="nope")


def test_unresearched_runs_say_so(sandbox):
    run_dir = runner.prepare_run("T", sandbox)
    meta = json.loads((run_dir / "run.json").read_text())
    meta.update(status="done", unresearched=True, edits_applied=[], edits_skipped=[], flags=[])
    (run_dir / "run.json").write_text(json.dumps(meta))
    assert "unresearched" in crew_status.run(run_id=run_dir.name)
