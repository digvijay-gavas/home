from pathlib import Path
import sys
import unittest
import uuid

from runtime import AlreadyRunning, LocalSignal, claim_listener, listener_running, send_signal


@unittest.skipUnless(sys.platform == "win32", "Windows local process control")
class ServiceControlTests(unittest.TestCase):
    def setUp(self):
        self.config = Path.cwd() / ("control-test-" + uuid.uuid4().hex + ".json")

    def test_signal_is_local_and_consumed_once(self):
        self.assertFalse(send_signal(self.config, "stop"))
        signal = LocalSignal(self.config, "stop")
        try:
            self.assertFalse(signal.received())
            self.assertTrue(send_signal(self.config, "stop"))
            self.assertTrue(signal.received())
            self.assertFalse(signal.received())
        finally:
            signal.close()
        self.assertFalse(send_signal(self.config, "stop"))

    def test_controls_and_settings_do_not_claim_microphone_runtime(self):
        controls = claim_listener(self.config, "controls")
        settings = claim_listener(self.config, "settings")
        try:
            signal = LocalSignal(self.config, "settings")
            try:
                self.assertTrue(send_signal(self.config, "settings"))
                self.assertTrue(signal.received())
            finally:
                signal.close()
            self.assertFalse(listener_running(self.config))
            with self.assertRaises(AlreadyRunning):
                claim_listener(self.config, "controls")
            with self.assertRaises(AlreadyRunning):
                claim_listener(self.config, "settings")
        finally:
            controls[0].CloseHandle(controls[1])
            settings[0].CloseHandle(settings[1])
