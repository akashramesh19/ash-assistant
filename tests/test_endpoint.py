from stt.endpoint import CHUNK_SECONDS, TRIM_PAD_SECONDS, Endpointer, trim_quiet_ends

QUIET, LOUD = 40, 2000


def run(levels, **kwargs):
    """Feed loudness values until it stops; return how many chunks it took."""
    endpointer = Endpointer(**kwargs)
    for count, level in enumerate(levels, 1):
        if endpointer.feed(level):
            return count
    return None


def test_stops_after_a_pause_following_speech():
    levels = [QUIET] * 10 + [LOUD] * 100 + [QUIET] * 100
    count = run(levels)
    assert count == 10 + 100 + 40  # 1.2 s of quiet = 40 chunks


def test_a_short_breath_mid_sentence_does_not_end_it():
    levels = [LOUD] * 50 + [QUIET] * 20 + [LOUD] * 50 + [QUIET] * 100  # 0.6 s pause in the middle
    assert run(levels) == 50 + 20 + 50 + 40


def test_a_longer_sentence_than_five_seconds_is_not_cut():
    levels = [LOUD] * 400 + [QUIET] * 100  # 12 s of speech
    assert run(levels) == 440


def test_gives_up_when_nobody_speaks():
    assert run([QUIET] * 1000) == round(5.0 / 0.03)


def test_a_click_is_not_speech():
    levels = [LOUD] * 2 + [QUIET] * 1000
    assert run(levels) == round(5.0 / 0.03)


def test_noisy_room_raises_the_bar():
    # Room hum at 400 sets the floor (threshold 1200); 900 is not louder, so it is not speech.
    levels = [400] * 10 + [900] * 100 + [400] * 1000
    assert run(levels) == round(5.0 / 0.03)


def test_speech_between_500_and_1100_starts_at_the_first_chunks():
    # Those levels are above the noise cap, so they must not set the floor.
    # If they did, the bar would lock at 1200 and a later room dip would trim the opening off.
    opening = [500, 700, 900, 1100, 800, 600] * 5
    assert min(opening) >= 500 and max(opening) <= 1100
    room = [QUIET] * 20  # shorter than the pause that ends a turn
    rest = [800, 1000, 600] * 10
    pause = [QUIET] * 80

    endpointer = Endpointer()
    for level in opening:
        assert not endpointer.feed(level)
    assert endpointer.speaking and endpointer.speech_start == 0 and endpointer.floor is None

    for level in room + rest + pause:
        if endpointer.feed(level):
            break
    assert endpointer.reason == "pause"
    assert endpointer.speech_start == 0
    assert endpointer.speech_end == len(opening) + len(room) + len(rest)

    rate = 16000
    block = int(rate * CHUNK_SECONDS)
    samples = list(range(endpointer.chunks * block))
    trimmed = trim_quiet_ends(samples, endpointer.speech_start, endpointer.speech_end, rate)
    opening_span = len(opening) * block
    assert trimmed[:opening_span] == samples[:opening_span]


def test_hard_cap():
    assert run([LOUD] * 2000, max_seconds=2.0) == round(2.0 / 0.03)


def test_a_1_5_second_pause_does_not_end_the_turn_at_2_seconds():
    endpointer = Endpointer(end_silence=2.0)
    levels = [LOUD] * 10 + [QUIET] * round(1.5 / 0.03)
    stopped = any(endpointer.feed(level) for level in levels)
    assert not stopped and endpointer.speaking and endpointer.reason is None


def test_trim_drops_quiet_ends_and_keeps_a_short_pad():
    endpointer = Endpointer()
    # Leading quiet, speech, a short breath, more speech, then a long enough pause.
    levels = [QUIET] * 20 + [LOUD] * 20 + [QUIET] * 10 + [LOUD] * 20 + [QUIET] * 80
    for level in levels:
        if endpointer.feed(level):
            break
    assert endpointer.reason == "pause"
    assert endpointer.speech_start == 20
    assert endpointer.speech_end == 70

    rate = 16000
    block = int(rate * CHUNK_SECONDS)
    samples = list(range(endpointer.chunks * block))
    trimmed = trim_quiet_ends(samples, endpointer.speech_start, endpointer.speech_end, rate)
    pad = int(TRIM_PAD_SECONDS * rate)
    start = endpointer.speech_start * block - pad
    end = endpointer.speech_end * block + pad
    assert trimmed == samples[start:end]
    assert start > 0 and end < len(samples)
    breath = (20 + 20) * block  # first sample of the mid-sentence quiet, still inside the slice
    assert trimmed[breath - start] == samples[breath]


def test_stop_reason_for_nobody_and_the_cap():
    nobody = Endpointer()
    for level in [QUIET] * 1000:
        if nobody.feed(level):
            break
    assert nobody.reason == "nobody spoke" and nobody.speech_start is None
    assert trim_quiet_ends(list(range(8)), None, None, 16000) == list(range(8))

    cap = Endpointer(max_seconds=20)
    for level in [LOUD] * 2000:
        if cap.feed(level):
            break
    assert cap.reason == "20 second cap"
