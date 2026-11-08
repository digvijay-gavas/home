"""Parallel restricted wake recognition and unrestricted argument transcription."""

import json

from events import words


class RecognitionEngine:
    def __init__(self, model, rate, detector, debug=lambda result: None):
        self.model = model
        self.rate = rate
        self.detector = detector
        self.debug = debug
        self.audio_time = 0.0
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

    def _parse(self, raw):
        result = json.loads(raw)
        tokens = result.get("result", result.get("partial_result", []))
        for word in tokens:
            word["start"] += self.offset
            word["end"] += self.offset
        return result, tokens

    def feed(self, data):
        self.audio_time += len(data) / (2 * self.rate)
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
        completed = self.detector.observe({"result": wake_words}, transcript, self.audio_time, pending)
        if completed:
            self._reset_recognizers()

    def end(self):
        full_result, full_words = self._parse(self.full.FinalResult())
        self.debug(full_result)
        self.history.extend(full_words)
        _, wake_words = self._parse(self.wake.FinalResult())
        self.detector.observe({"result": wake_words}, self.history, self.audio_time)
        self.detector.finish(self.audio_time, "end_of_file")

    def cancel(self):
        self.detector.cancel()
        self._reset_recognizers()
