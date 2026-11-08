import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from configuration import read_config, save_config, validate_config


BASE = {
    "model_path": "models/example", "sample_rate": 16000, "device": None,
    "triggers": [{"id": "bobo", "phrase": "hey bobo", "event": "wake_word.detected",
                  "min_confidence": 0.8, "cooldown_seconds": 2.0}],
}


class ConfigurationTests(unittest.TestCase):
    def test_command_and_feedback_settings_are_validated(self):
        for change in ({"show_feedback": "yes"}, {"capture_arguments": 1},
                       {"silence_seconds": 0}, {"argument_timeout_seconds": float("inf")},
                       {"max_argument_seconds": 121}, {"max_argument_seconds": 2}, {"cooldown_seconds": 86401}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_config(dict(BASE, triggers=[dict(BASE["triggers"][0], **change)]))

    def test_invalid_config_rejected(self):
        for changes in [{"triggers": []}, {"sample_rate": 0}, {"sample_rate": True},
                        {"model_path": ""}, {"device": {}}, {"triggers": [None]}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_config(dict(BASE, **changes))

    def test_rejects_duplicate_ids_and_normalized_phrases(self):
        for extra in [dict(BASE["triggers"][0], phrase="hello there"),
                      dict(BASE["triggers"][0], id="other", phrase="Hey, Bobo!")]:
            with self.assertRaises(ValueError):
                validate_config(dict(BASE, triggers=BASE["triggers"] + [extra]))

    def test_save_roundtrip_preserves_settings_and_original_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            config = copy.deepcopy(BASE)
            config["device"] = 12
            config["future_setting"] = {"enabled": True}
            before = copy.deepcopy(config)
            save_config(path, config)
            self.assertEqual(read_config(path), before)
            self.assertEqual(config, before)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_invalid_save_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(BASE), encoding="utf-8")
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                save_config(path, dict(BASE, triggers=[]))
            self.assertEqual(path.read_bytes(), original)

    def test_failed_replace_preserves_original_and_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(BASE), encoding="utf-8")
            original = path.read_bytes()
            with patch("configuration.os.replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    save_config(path, dict(BASE, device=1))
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [path])
