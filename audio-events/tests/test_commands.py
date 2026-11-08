import unittest

from commands import CommandDetector
from events import EventBus


def word(text, start, end, confidence=0.99):
    return {"word": text, "start": start, "end": end, "conf": confidence}


WAKE = {"result": [word("hey", 0.0, 0.3), word("bobo", 0.3, 0.7)]}
QUESTION = [word("what", 2.0, 2.2), word("is", 2.2, 2.4), word("the", 2.4, 2.5),
            word("time", 2.5, 2.8), word("now", 2.8, 3.1)]


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.feedback = []
        self.bus = EventBus()
        self.bus.subscribe(self.events.append)
        self.trigger = {"id": "bobo", "phrase": "hey bobo", "event": "voice_command.received",
                        "min_confidence": 0.8, "cooldown_seconds": 2.0,
                        "capture_arguments": True, "show_feedback": True}
        self.detector = CommandDetector([self.trigger], self.bus, self.feedback.append)

    def test_continuous_and_paused_produce_same_input_once(self):
        for paused in (False, True):
            with self.subTest(paused=paused):
                self.setUp()
                if paused:
                    self.detector.observe(WAKE, WAKE["result"], 1.4)
                    self.assertEqual(self.events, [])
                    self.detector.observe({}, WAKE["result"] + QUESTION, 3.2, True)
                else:
                    self.detector.observe(WAKE, WAKE["result"] + QUESTION, 3.2, True)
                self.detector.observe({}, WAKE["result"] + QUESTION, 4.4)
                self.assertEqual(len(self.events), 1)
                self.assertEqual(self.events[0]["input"], "what is the time now")
                self.assertEqual(self.events[0]["type"], "voice_command.received")
                self.assertEqual(self.feedback[0]["phase"], "listening")
                self.assertEqual(self.feedback[-1]["phase"], "complete")

    def test_unrelated_transcript_without_wake_is_discarded(self):
        self.detector.observe({}, QUESTION, 5)
        self.assertEqual(self.events, [])
        self.assertEqual(self.feedback, [])

    def test_no_input_timeout_finishes_with_empty_input(self):
        self.detector.observe(WAKE, WAKE["result"], 1)
        self.detector.observe({}, [], 5.8)
        self.assertEqual(self.events[0]["input"], "")
        self.assertEqual(self.events[0]["reason"], "no_input")

    def test_pending_speech_is_not_cut_off_by_silence_timeout(self):
        self.detector.observe(WAKE, QUESTION[:1], 2.3, True)
        self.detector.observe({}, QUESTION[:2], 4, True)
        self.assertEqual(self.events, [])

    def test_maximum_duration_bounds_session(self):
        self.detector.observe(WAKE, QUESTION, 3.3, True)
        self.detector.observe({}, QUESTION, 16, True)
        self.assertEqual(self.events[0]["reason"], "max_duration")

    def test_cooldown_begins_after_completion(self):
        self.detector.observe(WAKE, QUESTION, 4.5)
        self.detector.observe(WAKE, QUESTION, 5)
        self.assertEqual(len(self.events), 1)
        self.assertIsNone(self.detector.active)
        later_wake = {"result": [word("hey", 6.1, 6.4), word("bobo", 6.4, 6.7)]}
        self.detector.observe(later_wake, [], 6.8)
        self.assertIsNotNone(self.detector.active)

    def test_audio_gap_cancels_without_publishing_partial_command(self):
        self.detector.observe(WAKE, QUESTION, 3.2, True)
        self.detector.cancel()
        self.assertEqual(self.events, [])
        self.assertEqual(self.feedback[-1]["phase"], "cancelled")

    def test_feedback_is_opt_in_and_trigger_only_remains_supported(self):
        self.trigger.update(show_feedback=False, capture_arguments=False)
        self.detector.observe(WAKE, QUESTION, 1)
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["reason"], "trigger_only")
        self.assertEqual(self.events[0]["input"], "")
        self.assertEqual(self.feedback, [])

    def test_weak_wake_never_opens_a_session(self):
        weak = {"result": [word("hey", 0, 0.3), word("bobo", 0.3, 0.7, 0.5)]}
        self.detector.observe(weak, QUESTION, 4.5)
        self.assertEqual(self.events, [])
        self.assertEqual(self.feedback, [])
