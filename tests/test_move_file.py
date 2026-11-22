"""move_file: one allowed folder, confirm first, never delete, log everything."""

import json

import pytest

from tools import TOOLS, move_file


class Confirmer:
    """Records each question and answers from a queue (default: yes)."""

    def __init__(self, answers=None, on_ask=None):
        self.questions = []
        self.answers = list(answers or [])
        self.on_ask = on_ask

    def __call__(self, question):
        self.questions.append(question)
        if self.on_ask:
            self.on_ask()
        return self.answers.pop(0) if self.answers else True


@pytest.fixture
def root(tmp_path, monkeypatch):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    (allowed / "Archive").mkdir()
    monkeypatch.setenv("ASH_MOVE_ROOT", str(allowed))
    monkeypatch.setenv("ASH_MOVE_LOG", str(tmp_path / "move.jsonl"))
    return allowed


@pytest.fixture
def confirm(monkeypatch):
    confirmer = Confirmer()
    monkeypatch.setattr(move_file, "_confirmer", confirmer)
    return confirmer


def log_records(tmp_path):
    path = tmp_path / "move.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_registered_with_only_source_and_destination_parameters():
    props = TOOLS["move_file"].TOOL_DEFINITION["parameters"]["properties"]
    assert set(props) == {"source", "destination"}  # no overwrite/force flag for the model to set


def test_moves_file_into_existing_folder_after_confirmation(root, confirm, tmp_path):
    (root / "report.txt").write_text("hello")
    result = move_file.run(source="report.txt", destination="Archive")

    assert (root / "Archive" / "report.txt").read_text() == "hello"
    assert not (root / "report.txt").exists()
    assert "Moved" in result
    assert len(confirm.questions) == 1 and "report.txt" in confirm.questions[0] and "Archive" in confirm.questions[0]
    assert log_records(tmp_path)[-1]["outcome"] == "moved"


def test_nothing_moves_before_the_user_confirms(root, tmp_path, monkeypatch):
    (root / "report.txt").write_text("x")
    still_there = []
    confirmer = Confirmer(on_ask=lambda: still_there.append((root / "report.txt").exists()))
    monkeypatch.setattr(move_file, "_confirmer", confirmer)
    move_file.run(source="report.txt", destination="Archive")
    assert still_there == [True]


def test_declined_confirmation_leaves_everything_in_place(root, monkeypatch, tmp_path):
    (root / "report.txt").write_text("x")
    monkeypatch.setattr(move_file, "_confirmer", Confirmer(answers=[False]))
    result = move_file.run(source="report.txt", destination="Archive")
    assert (root / "report.txt").exists() and not (root / "Archive" / "report.txt").exists()
    assert "Not moved" in result
    assert log_records(tmp_path)[-1]["outcome"] == "denied"


@pytest.mark.parametrize(
    "source,destination",
    [("../outside.txt", "Archive"), ("report.txt", "../elsewhere"), ("report.txt", "Archive/../../x")],
)
def test_paths_escaping_the_folder_are_rejected_without_asking(root, confirm, tmp_path, source, destination):
    (root / "report.txt").write_text("x")
    (tmp_path / "outside.txt").write_text("secret")
    result = move_file.run(source=source, destination=destination)
    assert result.startswith("error:")
    assert confirm.questions == []
    assert (tmp_path / "outside.txt").exists() and (root / "report.txt").exists()
    assert log_records(tmp_path)[-1]["outcome"] == "rejected"


def test_absolute_path_outside_the_folder_is_rejected(root, confirm, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    result = move_file.run(source=str(outside), destination="Archive")
    assert result.startswith("error:") and outside.exists() and confirm.questions == []


def test_symlink_source_is_rejected(root, confirm, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (root / "link.txt").symlink_to(outside)
    result = move_file.run(source="link.txt", destination="Archive")
    assert result.startswith("error:") and outside.exists() and confirm.questions == []


def test_destination_folder_that_is_a_symlink_out_is_rejected(root, confirm, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (root / "portal").symlink_to(elsewhere)
    (root / "report.txt").write_text("x")
    result = move_file.run(source="report.txt", destination="portal")
    assert result.startswith("error:") and not list(elsewhere.iterdir()) and (root / "report.txt").exists()


def test_existing_destination_file_needs_its_own_overwrite_confirmation(root, monkeypatch, tmp_path):
    (root / "report.txt").write_text("new")
    (root / "Archive" / "report.txt").write_text("old")
    monkeypatch.setattr(move_file, "_confirmer", Confirmer(answers=[True, False]))  # move ok, overwrite no
    result = move_file.run(source="report.txt", destination="Archive")
    assert (root / "Archive" / "report.txt").read_text() == "old" and (root / "report.txt").read_text() == "new"
    assert "Not moved" in result


def test_overwrite_happens_only_after_explicit_yes(root, monkeypatch, tmp_path):
    (root / "report.txt").write_text("new")
    (root / "Archive" / "report.txt").write_text("old")
    confirmer = Confirmer(answers=[True, True])
    monkeypatch.setattr(move_file, "_confirmer", confirmer)
    move_file.run(source="report.txt", destination="Archive")
    assert any("overwrite" in q.lower() or "replace" in q.lower() for q in confirmer.questions)
    assert (root / "Archive" / "report.txt").read_text() == "new"
    assert log_records(tmp_path)[-1]["outcome"] == "overwritten"


def test_a_destination_folder_is_never_overwritten(root, confirm):
    (root / "Docs").mkdir()
    (root / "Docs" / "Archive").mkdir()
    result = move_file.run(source="Docs/Archive", destination=".")
    assert result.startswith("error:") and (root / "Docs" / "Archive").exists()


def test_does_not_create_missing_folders(root, confirm):
    (root / "report.txt").write_text("x")
    result = move_file.run(source="report.txt", destination="Nope/report.txt")
    assert result.startswith("error:") and not (root / "Nope").exists() and (root / "report.txt").exists()


def test_missing_source_and_moving_the_root_are_errors(root, confirm):
    assert move_file.run(source="ghost.txt", destination="Archive").startswith("error:")
    assert move_file.run(source=".", destination="Archive").startswith("error:")
    assert confirm.questions == []


def test_cannot_move_a_folder_into_itself(root, confirm):
    (root / "Docs").mkdir()
    result = move_file.run(source="Docs", destination="Docs")
    assert "into itself" in result and (root / "Docs").exists()
    assert move_file.run(source="Docs", destination="Docs/inner.txt").startswith("error:")


def test_a_destination_that_does_not_exist_is_refused_not_turned_into_a_rename(root, confirm, tmp_path):
    (root / "report.txt").write_text("keep")
    result = move_file.run(source="report.txt", destination="Trash")
    assert result.startswith("error:") and "doesn't rename" in result
    assert (root / "report.txt").read_text() == "keep" and not (root / "Trash").exists()
    assert confirm.questions == []  # refused before asking, so no misleading "move to Trash?" prompt
    assert log_records(tmp_path)[-1]["outcome"] == "rejected"


def test_renaming_onto_an_existing_file_with_a_different_name_is_refused(root, confirm):
    (root / "report.txt").write_text("new")
    (root / "Archive" / "old.txt").write_text("old")
    result = move_file.run(source="report.txt", destination="Archive/old.txt")
    assert result.startswith("error:") and (root / "Archive" / "old.txt").read_text() == "old"
    assert (root / "report.txt").exists() and confirm.questions == []


def test_a_full_path_that_keeps_the_file_name_still_works(root, confirm):
    (root / "report.txt").write_text("hello")
    result = move_file.run(source="report.txt", destination="Archive/report.txt")
    assert "Moved" in result and (root / "Archive" / "report.txt").read_text() == "hello"


def test_tool_definition_says_it_cannot_rename():
    assert "rename" in move_file.TOOL_DEFINITION["description"]


def test_unconfigured_or_missing_root_is_a_clear_error(monkeypatch, tmp_path):
    monkeypatch.setenv("ASH_MOVE_LOG", str(tmp_path / "move.jsonl"))
    monkeypatch.delenv("ASH_MOVE_ROOT", raising=False)
    assert "ASH_MOVE_ROOT" in move_file.run(source="a", destination="b")
    monkeypatch.setenv("ASH_MOVE_ROOT", str(tmp_path / "does-not-exist"))
    assert move_file.run(source="a", destination="b").startswith("error:")


def test_console_confirm_defaults_to_no(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    assert move_file.console_confirm("Go?") is False
    monkeypatch.setattr("builtins.input", lambda prompt="": "Yes")
    assert move_file.console_confirm("Go?") is True

    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert move_file.console_confirm("Go?") is False
