import unittest
from unittest.mock import Mock

from feedback import FeedbackPopup


class Variable:
    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.root = Mock()
        self.root.after.return_value = "timer"
        self.popup = FeedbackPopup(self.root)

        def create():
            self.popup.window = Mock()
            self.popup.text = Mock()
            for name in ("heading", "phrase", "input", "details"):
                setattr(self.popup, name, Variable())

        self.popup._create = Mock(side_effect=create)
        self.update = {"session_id": "one", "phase": "listening", "phrase": "hey bobo",
                       "event": "voice_command.received", "input": "", "cooldown_seconds": 2}

    def test_listening_has_no_timer_and_complete_holds_for_cooldown(self):
        self.popup.update(self.update)
        self.root.after.assert_not_called()
        self.popup.update(dict(self.update, phase="complete", input="what is the time now"))
        self.root.after.assert_called_once_with(2000, self.popup.hide)
        self.popup.text.insert.assert_called_with("1.0", "what is the time now")

    def test_old_timer_is_cancelled_when_a_new_session_starts(self):
        self.popup.update(dict(self.update, phase="complete"))
        self.popup.update(dict(self.update, session_id="two"))
        self.root.after_cancel.assert_called_with("timer")
        self.assertIsNone(self.popup.dismiss_timer)
        self.assertEqual(self.popup.heading.get(), "Listening…")

    def test_dismissal_suppresses_same_session_but_not_the_next(self):
        self.popup.update(self.update)
        self.popup.dismiss()
        self.popup.update(dict(self.update, input="draft"))
        self.assertIsNone(self.popup.window)
        self.popup.update(dict(self.update, session_id="two"))
        self.assertIsNotNone(self.popup.window)
