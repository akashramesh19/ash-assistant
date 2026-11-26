"""Decides when the speaker has finished, from a stream of loudness values.

Plain code, no audio libraries, so it can be tested with made-up numbers.
Replaces the fixed 5 s recording: it waits for speech to start, then stops
after a pause long enough that a mid-sentence breath doesn't end the turn.
"""

CHUNK_SECONDS = 0.03
MIN_THRESHOLD = 250  # int16 RMS; below this is treated as silence regardless of the room
MAX_NOISE_FLOOR = 400  # a loud first chunk is you talking right after the wake word, not the room
NOISE_MULTIPLIER = 3.0  # speech must be this much louder than the quietest stretch heard
START_CHUNKS = 3  # consecutive loud chunks that count as speech starting
END_SILENCE_SECONDS = 1.2  # class default (tests). record() passes ASH_END_SILENCE, default 2s
NO_SPEECH_SECONDS = 5.0  # give up if nobody starts talking
MAX_SECONDS = 20.0  # hard cap on one utterance
TRIM_PAD_SECONDS = 0.2  # quiet kept on each side of the speech when the WAV is trimmed


class Endpointer:
    def __init__(
        self,
        end_silence=END_SILENCE_SECONDS,
        no_speech=NO_SPEECH_SECONDS,
        max_seconds=MAX_SECONDS,
        chunk_seconds=CHUNK_SECONDS,
    ):
        self.end_chunks = round(end_silence / chunk_seconds)
        self.no_speech_chunks = round(no_speech / chunk_seconds)
        self.max_chunks = round(max_seconds / chunk_seconds)
        self.max_seconds = max_seconds
        self.floor = None  # quietest loudness seen: the room's noise level
        self.chunks = 0
        self.loud_run = 0
        self.quiet_run = 0
        self.speaking = False
        self.speech_start = None  # first speech chunk; None until speech actually starts
        self.reason = None  # why feed() returned True: pause, nobody spoke, or the cap

    @property
    def threshold(self) -> float:
        return max(MIN_THRESHOLD, min(self.floor or 0, MAX_NOISE_FLOOR) * NOISE_MULTIPLIER)

    def feed(self, loudness: float) -> bool:
        """Give it the next chunk's loudness. True means stop recording."""
        self.chunks += 1
        self.floor = loudness if self.floor is None else min(self.floor, loudness)
        if loudness > self.threshold:
            self.loud_run += 1
            self.quiet_run = 0
            if self.loud_run >= START_CHUNKS:
                if not self.speaking:
                    self.speech_start = self.chunks - START_CHUNKS
                self.speaking = True
        else:
            self.loud_run = 0
            self.quiet_run += 1

        if self.chunks >= self.max_chunks:
            self.reason = f"{self.max_seconds:g} second cap"
            return True
        if self.speaking:
            if self.quiet_run >= self.end_chunks:
                self.reason = "pause"
                return True
            return False
        if self.chunks >= self.no_speech_chunks:
            self.reason = "nobody spoke"
            return True
        return False

    @property
    def speech_end(self):
        """Exclusive chunk index where speech ends, before the trailing quiet."""
        if self.speech_start is None:
            return None
        return self.chunks - self.quiet_run


def trim_quiet_ends(
    samples,
    speech_start,
    speech_end,
    sample_rate,
    chunk_seconds=CHUNK_SECONDS,
    pad_seconds=TRIM_PAD_SECONDS,
):
    """Drop quiet samples before speech starts and after it ends, leaving a short pad.

    speech_start and speech_end are Endpointer chunk indexes (end exclusive).
    No speech region, or a slice that would be empty: the samples come back unchanged.
    Works on any sequence, so it can be tested without a microphone.
    """
    if speech_start is None or speech_end is None or speech_end <= speech_start:
        return samples
    block = int(sample_rate * chunk_seconds)
    if block <= 0:
        return samples
    pad = int(pad_seconds * sample_rate)
    start = max(0, speech_start * block - pad)
    end = min(len(samples), speech_end * block + pad)
    if end <= start:
        return samples
    return samples[start:end]
