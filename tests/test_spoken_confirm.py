import threading

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


def test_a_mismatched_click_stays_pending_and_silence_is_no():
    """A click counts only for the open id. The second click is dropped.
    No click and no clear speech is a no, including on the next question."""
    question = "Ash wants to move 'report.txt' to 'Archive/report.txt'. Go ahead?"
    overwrite = "'Archive/report.txt' already exists. Replace it with 'report.txt'? The existing file will be overwritten."
    said, events, logs = [], [], []
    started, release = threading.Event(), threading.Event()

    def listen():
        if not release.is_set():
            started.set()
            release.wait(2)
            return "yes"  # would win if the click were ignored
        confirm.on_answer(events[0]["id"], "yes")  # previous question's id
        confirm.on_answer("debug", "yes")
        return ""

    confirm = make_spoken_confirmer(said.append, listen, logs.append, emit=events.append)
    holder = {}

    def run():
        holder["result"] = confirm(question)

    thread = threading.Thread(target=run)
    thread.start()
    try:
        assert started.wait(2)
        confirm.on_answer("not-this-question", "yes")
        assert thread.is_alive() and "result" not in holder  # mismatched id stays pending

        confirm.on_answer(events[0]["id"], "no")
        confirm.on_answer(events[0]["id"], "yes")  # second answer is dropped
        assert thread.is_alive() and "result" not in holder  # the callback only stored it
    finally:
        release.set()
        thread.join(2)
    assert not thread.is_alive()
    assert holder["result"] is False
    assert said == [speakable(question)]
    assert events[0] == {"type": "confirm", "id": events[0]["id"], "question": question}
    assert "/" in events[0]["question"] and "slash" in said[0]

    confirm.on_answer(events[0]["id"], "yes")  # nothing is pending
    assert confirm(overwrite) is False
    confirms = [event for event in events if event["type"] == "confirm"]
    closed = [event for event in events if event["type"] == "confirm_closed"]
    assert [event["id"] for event in confirms] == [event["id"] for event in closed]
    assert len(set(event["id"] for event in confirms)) == 2
    assert confirms[1]["question"] == overwrite
    assert closed[0]["answer"] == "no"
    assert closed[1]["answer"] == "timeout"
