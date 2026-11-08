"""Wake recognition, open dictation, and optional trigger vocabulary decoding."""

import json
from collections import deque

from events import words
from vocabulary import grammar_phrases, trigger_vocabulary


class VocabularyStream:
    def __init__(self, model, rate, vocabulary, offset):
        from vosk import KaldiRecognizer
        self.decoder = KaldiRecognizer(model, rate, json.dumps(grammar_phrases(vocabulary) + ["[unk]"]))
        self.decoder.SetWords(True)
        self.decoder.SetPartialWords(True)
        self.offset = offset
        self.history = []
        self.partial = []
        self.pending = False

    def _read(self, raw, final):
        result = json.loads(raw)
        tokens = result.get("result", result.get("partial_result", []))
        for word in tokens:
            word["start"] += self.offset
            word["end"] += self.offset
        if final:
            self.history.extend(tokens)
            self.partial = []
            self.pending = False
        else:
            self.partial = tokens
            self.pending = bool(result.get("partial"))

    @property
    def transcript(self):
        return self.history + self.partial

    def feed(self, data):
        final = self.decoder.AcceptWaveform(data)
        self._read(self.decoder.Result() if final else self.decoder.PartialResult(), final)

    def end(self):
        self._read(self.decoder.FinalResult(), True)


class RecognitionEngine:
    def __init__(self, model, rate, detector, debug=lambda result: None):
        self.model = model
        self.rate = rate
        self.detector = detector
        self.debug = debug
        self.audio_time = 0.0
        self.needs_pre_roll = any(t.get("vocabulary", {}).get("enabled") for t in detector.triggers)
        self._reset_recognizers()

    def _reset_recognizers(self):
        from vosk import KaldiRecognizer
        self.offset = self.audio_time
        grammar = json.dumps([" ".join(words(t["phrase"])) for t in self.detector.triggers] + ["[unk]"])
        self.wake = KaldiRecognizer(self.model, self.rate, grammar)
        self.full = KaldiRecognizer(self.model, self.rate)
        for recognizer in (self.wake, self.full):
            recognizer.SetWords(True)
            recognizer.SetPartialWords(True)
        self.history = []
        self.pre_roll = deque()
        self.vocabulary = None

    def _ensure_vocabulary(self, wake_words):
        if self.vocabulary is not None:
            return
        match = self.detector.wake_match({"result": wake_words}, self.audio_time)
        if not match or not match[0].get("vocabulary", {}).get("enabled"):
            return
        trigger, matched, _ = match
        wake_end = matched[-1]["end"]
        offset = max(wake_end, self.pre_roll[0][0]) if self.pre_roll else wake_end
        self.vocabulary = VocabularyStream(self.model, self.rate, trigger_vocabulary(trigger), offset)
        # Replay only audio after the wake word, including words spoken before
        # the wake decoder reported its match. No disk recording is involved.
        for start, data in self.pre_roll:
            skip = max(0, round((offset - start) * self.rate)) * 2
            if skip < len(data):
                self.vocabulary.feed(data[skip:])

    def _parse(self, raw):
        result = json.loads(raw)
        tokens = result.get("result", result.get("partial_result", []))
        for word in tokens:
            word["start"] += self.offset
            word["end"] += self.offset
        return result, tokens

    def feed(self, data):
        start = self.audio_time
        self.audio_time += len(data) / (2 * self.rate)
        if self.needs_pre_roll:
            self.pre_roll.append((start, data))
            while self.pre_roll and self.pre_roll[0][0] + len(self.pre_roll[0][1]) / (2 * self.rate) < self.audio_time - 8:
                self.pre_roll.popleft()
        if self.vocabulary:
            self.vocabulary.feed(data)
        full_final = self.full.AcceptWaveform(data)
        active = self.detector.active
        force_final = active and self.audio_time - active["wake_end"] >= active["trigger"].get("max_argument_seconds", 15.0)
        if force_final and not full_final:
            full_result, full_words = self._parse(self.full.FinalResult())
            full_final = True
        else:
            full_result, full_words = self._parse(self.full.Result() if full_final else self.full.PartialResult())
        if full_final:
            self.history.extend(full_words)
            self.debug(full_result)
        retention = max(t.get("max_argument_seconds", 15.0) for t in self.detector.triggers) + 10
        self.history = [w for w in self.history if w["end"] > self.audio_time - retention]
        transcript = self.history if full_final else self.history + full_words
        wake_final = self.wake.AcceptWaveform(data)
        _, wake_words = self._parse(self.wake.Result() if wake_final else self.wake.PartialResult())
        pending = bool(full_result.get("partial")) if not full_final else False
        self._ensure_vocabulary(wake_words)
        if self.vocabulary:
            if force_final:
                self.vocabulary.end()
            transcript, pending = self.vocabulary.transcript, self.vocabulary.pending
        completed = self.detector.observe({"result": wake_words}, transcript, self.audio_time, pending)
        if completed:
            self._reset_recognizers()

    def end(self):
        full_result, full_words = self._parse(self.full.FinalResult())
        self.debug(full_result)
        self.history.extend(full_words)
        _, wake_words = self._parse(self.wake.FinalResult())
        self._ensure_vocabulary(wake_words)
        transcript = self.history
        if self.vocabulary:
            self.vocabulary.end()
            transcript = self.vocabulary.transcript
        self.detector.observe({"result": wake_words}, transcript, self.audio_time)
        self.detector.finish(self.audio_time, "end_of_file")

    def cancel(self):
        self.detector.cancel()
        self._reset_recognizers()
