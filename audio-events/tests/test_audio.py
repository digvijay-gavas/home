"""Optional integration checks using locally generated Windows speech fixtures."""

import os
from pathlib import Path
import unittest
import wave

from commands import CommandDetector
from configuration import read_config
from events import EventBus
from recognition import RecognitionEngine

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.environ.get("BOBO_AUDIO_TESTS") == "1", "Set BOBO_AUDIO_TESTS=1 for model/audio tests")
class AudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from vosk import Model, SetLogLevel
        SetLogLevel(-1)
        cls.config = read_config(ROOT / "config.json")
        cls.model = Model(str(ROOT / cls.config["model_path"]))

    def recognize(self, name, triggers=None):
        emitted, feedback = [], []
        bus = EventBus()
        bus.subscribe(emitted.append)
        detector = CommandDetector(triggers or self.config["triggers"], bus, feedback.append, "wav")
        with wave.open(str(ROOT / "test-audio" / (name + ".wav")), "rb") as audio:
            engine = RecognitionEngine(self.model, audio.getframerate(), detector)
            while data := audio.readframes(1600):
                engine.feed(data)
            engine.end()
        return emitted, feedback

    def test_continuous_and_paused_speech(self):
        for name in ("continuous", "paused"):
            with self.subTest(name=name):
                emitted, feedback = self.recognize(name)
                self.assertEqual(len(emitted), 1, emitted)
                self.assertEqual(emitted[0]["input"], "what is the time now")
                self.assertEqual(emitted[0]["reason"], "silence")
                self.assertEqual(feedback[-1]["input"], emitted[0]["input"])

    def test_unrelated_speech(self):
        self.assertEqual(self.recognize("unrelated")[0], [])

    def test_event_vocabulary_preserves_continuous_and_paused_arguments(self):
        trigger = dict(self.config["triggers"][0], vocabulary={
            "enabled": True,
            "words": ["TimeNow"],
            "sentences": ["what is the TimeNow"],
            "aliases": {"time now": "TimeNow"},
        })
        from listener import validate_vocabulary
        validate_vocabulary(self.model, {"triggers": [trigger]})
        for name in ("continuous", "paused"):
            with self.subTest(name=name):
                emitted, feedback = self.recognize(name, [trigger])
                self.assertEqual(len(emitted), 1, emitted)
                self.assertEqual(emitted[0]["raw_input"], "what is the time now")
                self.assertEqual(emitted[0]["input"], "what is the TimeNow")
                self.assertEqual(emitted[0]["recognition_mode"], "event_vocabulary")
                self.assertEqual(feedback[-1]["input"], emitted[0]["input"])

    def test_aliases_also_correct_spelling_in_open_dictation(self):
        trigger = dict(self.config["triggers"][0], vocabulary={
            "enabled": False, "aliases": {"time now": "TimeNow"},
        })
        emitted, _ = self.recognize("continuous", [trigger])
        self.assertEqual(len(emitted), 1, emitted)
        self.assertEqual(emitted[0]["raw_input"], "what is the time now")
        self.assertEqual(emitted[0]["input"], "what is the TimeNow")
        self.assertEqual(emitted[0]["recognition_mode"], "open_dictation")

    def test_wake_without_arguments_times_out(self):
        emitted, _ = self.recognize("wake-only")
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["input"], "")
        self.assertEqual(emitted[0]["reason"], "no_input")
