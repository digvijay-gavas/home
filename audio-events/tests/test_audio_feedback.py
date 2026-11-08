import subprocess
import unittest
from unittest.mock import Mock, patch

from audio_feedback import select_audio, speak_text, validate_audio_feedback


class AudioFeedbackTests(unittest.TestCase):
    def test_clip_chance_and_spoken_response_are_independent(self):
        rng = Mock()
        rng.choice.return_value = "second.wav"
        event = {"response": "It is noon."}
        settings = {"clips": ["first.wav", "second.wav"], "clip_chance_percent": 25, "speak_response": True}
        rng.random.return_value = 0.249
        self.assertEqual(select_audio(settings, event, rng), ("second.wav", "It is noon."))
        rng.choice.assert_called_once_with(settings["clips"])
        rng.random.return_value = 0.25
        self.assertEqual(select_audio(settings, event, rng), (None, "It is noon."))
        self.assertEqual(select_audio(dict(settings, clip_chance_percent=0), {}, rng), (None, None))

    def test_invalid_clip_and_probability_are_rejected(self):
        for settings in ({"clips": ["clip.mp3"]}, {"clip_chance_percent": -1}, {"clip_chance_percent": 101},
                         {"clip_chance_percent": float("nan")}, {"speak_response": "yes"},
                         {"spoken_text": "a" * 501}, {"spoken_text": None}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                validate_audio_feedback(settings)

    def test_fixed_text_works_without_clip_or_action_and_precedes_reply(self):
        settings = {"clips": ["clip.wav"], "clip_chance_percent": 0, "spoken_text": "  Ready.  "}
        self.assertEqual(select_audio(settings, {}), (None, "Ready."))
        self.assertEqual(select_audio(settings, {"response": "It is noon."}), (None, "Ready."))
        self.assertEqual(select_audio(dict(settings, speak_response=True), {"response": "It is noon."}),
                         (None, "Ready.\nIt is noon."))

    def test_streamed_final_line_is_not_spoken_twice(self):
        event = {"response": "Finished.", "response_already_spoken": True}
        self.assertEqual(select_audio({"speak_response": True, "spoken_text": "Done."}, event), (None, "Done."))

    @patch("audio_feedback.subprocess.run")
    def test_speech_is_sent_as_plain_utf8_data(self, run):
        text = "It’s noon. $env:Path"
        speak_text(text)
        args, kwargs = run.call_args
        self.assertNotIn(text, " ".join(args[0]))
        self.assertEqual(kwargs["input"], text.encode("utf-8"))
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
