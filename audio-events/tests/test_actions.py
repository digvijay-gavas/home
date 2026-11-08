from pathlib import Path
import sys
import tempfile
import unittest

from actions import run_action, validate_actions
from commands import CommandDetector
from events import EventBus


TIME_RULE = {"kind": "callback", "target": "current_time", "sentences": ["what is the time", "what time is it"]}


class ActionTests(unittest.TestCase):
    def test_dispatch_matches_whole_sentences_and_rejects_unknown_or_low_confidence(self):
        trigger = {"id": "bobo", "phrase": "hey bobo", "event": "voice_command.received",
                   "min_confidence": 0.8, "cooldown_seconds": 2, "capture_arguments": True, "actions": [TIME_RULE]}

        def recognize(tokens, source="microphone", confidence=1, wake_tail=False):
            calls = []
            detector = CommandDetector([trigger], EventBus(), source=source, on_action=lambda *args: calls.append(args))
            wake = {"result": [{"word": "hey", "end": 0.3, "conf": 1}, {"word": "bobo", "end": 0.7, "conf": 1}]}
            transcript = [{"word": word, "start": 1 + i / 10, "end": 1.1 + i / 10, "conf": confidence}
                          for i, word in enumerate(tokens.split())]
            if wake_tail:
                transcript.insert(0, {"word": "[unk]", "start": 0.7, "end": 0.76, "conf": 0.5})
            detector.observe(wake, transcript, 4)
            return calls

        for sentence in TIME_RULE["sentences"]:
            self.assertEqual(recognize(sentence)[0][0], TIME_RULE)
        self.assertEqual(recognize("what is the time", wake_tail=True)[0][0], TIME_RULE)
        self.assertFalse(recognize("please what is the time"))
        self.assertFalse(recognize("what is the [unk] time"))
        self.assertFalse(recognize("what is the time", confidence=0.5))
        self.assertFalse(recognize("what is the time", source="wav"))

    def test_callback_returns_a_response_and_duplicate_routes_are_rejected(self):
        result = run_action(TIME_RULE, {}, Path.cwd())
        self.assertEqual(result["status"], "ok")
        self.assertRegex(result["response"], r"^It is \d\d:\d\d [AP]M\.$")
        with self.assertRaises(ValueError):
            validate_actions([TIME_RULE, dict(TIME_RULE, sentences=["What time is it?"])])

    @unittest.skipUnless(sys.platform == "win32", "Windows batch interpreter")
    def test_batch_path_with_spaces_runs_without_forwarding_speech(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            script = path / "local action.bat"
            script.write_text('@echo off\nif not "%~1"=="" exit /b 9\necho ok>done.txt\n', encoding="ascii")
            rule = {"kind": "script", "target": script.name, "sentences": ["run example"]}
            result = run_action(rule, {"input": "run example & exit 5"}, path)
            self.assertEqual(result["status"], "ok", result)
            self.assertEqual((path / "done.txt").read_text().strip(), "ok")

    @unittest.skipUnless(sys.platform == "win32", "Windows batch interpreter")
    def test_batch_output_streams_in_order_and_last_line_becomes_response(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "report.bat").write_text("@echo off\necho Starting.\necho Finished.\n", encoding="ascii")
            rule = {"kind": "script", "target": "report.bat", "speak_stdout": True, "sentences": ["run example"]}
            updates = []
            result = run_action(rule, {}, path, on_output=updates.append)
            self.assertEqual(updates, ["Starting.", "Finished."])
            self.assertEqual(result, {"status": "ok", "response": "Finished."})

    def test_python_protocol_uses_runnable_messages_and_exit_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            script = path / "report.py"
            script.write_text("print('ordinary log')\nprint('BOBO:START:Starting.')\n"
                              "print('BOBO:START:Duplicate.')\nprint('BOBO:FINAL:Could not finish.')\n"
                              "raise SystemExit(3)\n", encoding="utf-8")
            rule = {"kind": "script", "target": script.name, "sentences": ["run example"]}
            updates = []
            validate_actions([rule])
            result = run_action(rule, {}, path, on_output=updates.append)
            self.assertEqual(updates, ["Starting."])
            self.assertEqual(result, {"status": "error", "response": "Could not finish."})
