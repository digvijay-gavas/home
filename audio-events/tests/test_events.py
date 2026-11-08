import unittest

from events import EventBus, PhraseDetector


def result(*tokens, confidence=0.95):
    return {"result": [{"word": word, "conf": confidence} for word in tokens]}


class PhraseDetectorTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.emitted = []
        self.bus = EventBus()
        self.bus.subscribe(self.emitted.append)
        self.trigger = {"id": "hey_bobo", "phrase": "hey bobo", "event": "wake_word.detected",
                        "min_confidence": 0.8, "cooldown_seconds": 2.0}
        self.detector = PhraseDetector([self.trigger], self.bus, lambda: self.now)

    def test_match_emits_structured_event(self):
        self.detector.accept(result("hey", "bobo"))
        self.assertEqual(len(self.emitted), 1)
        event = self.emitted[0]
        self.assertEqual(event["type"], "wake_word.detected")
        self.assertEqual(event["trigger_id"], "hey_bobo")
        self.assertEqual(event["confidence"], 0.95)
        self.assertTrue(event["id"])
        self.assertTrue(event["timestamp"])

    def test_requires_contiguous_whole_words_and_confidence(self):
        for tokens in [("bobo",), ("hey",), ("hey", "bob"),
                       ("hey", "[unk]", "bobo"), ("bobo", "hey")]:
            self.detector.accept(result(*tokens))
        self.detector.accept(result("hey", "bobo", confidence=0.79))
        self.detector.accept({"partial": "hey bobo"})
        self.assertEqual(self.emitted, [])

    def test_match_with_surrounding_speech(self):
        self.detector.accept(result("[unk]", "hey", "bobo", "[unk]"))
        self.assertEqual(len(self.emitted), 1)

    def test_cooldown_and_duplicate_matches(self):
        self.detector.accept(result("hey", "bobo", "hey", "bobo"))
        self.now = 1.9
        self.detector.accept(result("hey", "bobo"))
        self.assertEqual(len(self.emitted), 1)
        self.now = 2.0
        self.detector.accept(result("hey", "bobo"))
        self.assertEqual(len(self.emitted), 2)

    def test_other_triggers_have_independent_cooldowns(self):
        other = dict(self.trigger, id="hello", phrase="hello there", event="greeting.detected")
        detector = PhraseDetector([self.trigger, other], self.bus, lambda: self.now)
        detector.accept(result("hey", "bobo"))
        detector.accept(result("hello", "there"))
        self.assertEqual([e["type"] for e in self.emitted],
                         ["wake_word.detected", "greeting.detected"])

    def test_invalid_triggers_rejected(self):
        for changes in [{"min_confidence": 1.1}, {"cooldown_seconds": -1},
                        {"phrase": ""}, {"phrase": "[unk]"}, {"min_confidence": float("nan")}]:
            with self.assertRaises(ValueError):
                PhraseDetector([dict(self.trigger, **changes)], self.bus)
        with self.assertRaises(ValueError):
            PhraseDetector([self.trigger, self.trigger], self.bus)


if __name__ == "__main__":
    unittest.main()
