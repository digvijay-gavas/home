import subprocess
import unittest
from unittest.mock import Mock, patch

from audio_feedback import select_response, select_wake_audio, speak_text, validate_audio_feedback


class AudioFeedbackTests(unittest.TestCase):
    def test_clip_chance_and_spoken_response_are_independent(self):
        rng = Mock()
        rng.choice.return_value = "second.wav"
        event = {"response": "It is noon."}
        settings = {"clips": ["first.wav", "second.wav"], "clip_chance_percent": 25, "speak_response": True}
        rng.random.return_value = 0.249
        self.assertEqual(select_wake_audio(settings, rng), ("second.wav", None))
        self.assertEqual(select_response(settings, event), "It is noon.")
        rng.choice.assert_called_once_with(settings["clips"])
        rng.random.return_value = 0.25
        self.assertEqual(select_wake_audio(settings, rng), (None, None))
        self.assertEqual(select_wake_audio(dict(settings, clip_chance_percent=0), rng), (None, None))

    def test_invalid_clip_and_probability_are_rejected(self):
        for settings in ({"clips": ["clip.mp3"]}, {"clip_chance_percent": -1}, {"clip_chance_percent": 101},
                         {"clip_chance_percent": float("nan")}, {"speak_response": "yes"},
                         {"spoken_text": "a" * 501}, {"spoken_text": None}, {"voice": "unknown"}):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                validate_audio_feedback(settings)

    def test_fixed_text_is_reserved_for_the_wake_stage(self):
        settings = {"clips": ["clip.wav"], "clip_chance_percent": 0, "spoken_text": "  Ready.  "}
        self.assertEqual(select_wake_audio(settings), (None, "Ready."))
        self.assertIsNone(select_response(settings, {"response": "It is noon."}))
        self.assertEqual(select_response(dict(settings, speak_response=True), {"response": "It is noon."}), "It is noon.")

    def test_streamed_final_line_is_not_spoken_twice(self):
        event = {"response": "Finished.", "response_already_spoken": True}
        self.assertIsNone(select_response({"speak_response": True, "spoken_text": "Done."}, event))

    @patch("audio_feedback.subprocess.run")
    def test_speech_is_sent_as_plain_utf8_data(self, run):
        text = "It’s noon. $env:Path"
        speak_text(text)
        args, kwargs = run.call_args
        self.assertNotIn(text, " ".join(args[0]))
        self.assertEqual(kwargs["input"], text.encode("utf-8"))
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)

    @patch("audio_feedback.subprocess.run")
    def test_female_voice_is_selected_from_installed_voices(self, run):
        speak_text("Yes?", voice="female")
        command = run.call_args.args[0][-1]
        self.assertIn("Gender -eq 'Female'", command)
        self.assertIn("SelectVoice($female.VoiceInfo.Name)", command)
