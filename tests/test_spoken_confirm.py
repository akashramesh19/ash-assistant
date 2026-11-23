import pytest

from spoken_confirm import make_spoken_confirmer, parse_answer, speakable


@pytest.mark.parametrize("text", ["yes", "Yes.", "yeah", "Yep!", "go ahead", "Yes, go ahead.", "do it", "okay", "sure"])
def test_clear_yes(text):
    assert parse_answer(text) is True


@pytest.mark.parametrize("text", ["no", "No.", "nope", "cancel", "don't", "Don't do it", "do not", "wait", "stop", "yes, no wait", "hold on"])
def test_clear_no_and_no_beats_yes(text):
    assert parse_answer(text) is False


@pytest.mark.parametrize("text", ["", "   ", None, "Thank you.", "you", "uh", "mm-hmm", "the weather is nice today and I like it", "yes please move the other file instead of that one"])
def test_unclear_is_none(text):
    assert parse_answer(text) is None


def test_words_inside_other_words_do_not_count():
    assert parse_answer("yesterday") is None
    assert parse_answer("know") is None
    assert parse_answer("nobody") is None


def test_speakable_reads_paths_naturally():
    assert speakable("Ash wants to move 'report.txt' to 'Archive/report.txt'. Go ahead?") == (
        "Ash wants to move report dot txt to Archive slash report dot txt. Go ahead?"
    )


def run(heard, max_attempts=2):
    said, heard_iter, logs = [], iter(heard), []
    confirm = make_spoken_confirmer(said.append, lambda: next(heard_iter), logs.append, max_attempts)
    return confirm, said, logs


def test_yes_is_true_and_the_question_is_spoken():
    confirm, said, _ = run(["yes"])
    assert confirm("Move 'a.txt' to 'Archive'. Go ahead?") is True
    assert said == ["Move a dot txt to Archive. Go ahead?"]


def test_no_is_false():
    confirm, said, _ = run(["no"])
    assert confirm("Go ahead?") is False
    assert said == ["Go ahead?"]


def test_unclear_then_yes_asks_again_once():
    confirm, said, _ = run(["Thank you.", "yes"])
    assert confirm("Go ahead?") is True
    assert said == ["Go ahead?", "Sorry, was that a yes or a no?"]


def test_unclear_twice_is_no_and_says_so():
    confirm, said, _ = run(["", "mumble"])
    assert confirm("Go ahead?") is False
    assert said[-1] == "I didn't catch a clear yes, so I'll leave it."


def test_a_mic_failure_is_no_not_yes():
    def broken():
        raise OSError("no input device")

    logs = []
    confirm = make_spoken_confirmer(lambda text: None, broken, logs.append)
    assert confirm("Go ahead?") is False
    assert any("treating as no" in line for line in logs)


def test_a_speaker_failure_is_no_not_yes():
    def broken(text):
        raise RuntimeError("audio out failed")

    confirm = make_spoken_confirmer(broken, lambda: "yes", lambda line: None)
    assert confirm("Go ahead?") is False


def test_works_as_the_move_file_confirmer(tmp_path, monkeypatch):
    from tools import move_file

    root = tmp_path / "root"
    (root / "Archive").mkdir(parents=True)
    (root / "report.txt").write_text("v1")
    monkeypatch.setenv("ASH_MOVE_ROOT", str(root))
    monkeypatch.setenv("ASH_MOVE_LOG", str(tmp_path / "log.jsonl"))
    saved = move_file._confirmer

    try:
        said = []
        move_file.set_confirmer(make_spoken_confirmer(said.append, lambda: "no thanks", lambda line: None))
        assert move_file.run(source="report.txt", destination="Archive").startswith("Not moved")
        assert (root / "report.txt").exists()

        move_file.set_confirmer(make_spoken_confirmer(said.append, lambda: "yes", lambda line: None))
        assert move_file.run(source="report.txt", destination="Archive").startswith("Moved")
        assert (root / "Archive" / "report.txt").exists()
    finally:
        move_file.set_confirmer(saved)
