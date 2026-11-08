from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

from event_log import EventLog, log_path
from runtime import claim_listener, listener_running


def event(index):
    return {"id": str(index), "type": "voice_command.received", "phrase": "hey bobo",
            "input": "what is the time now", "timestamp": "2026-11-08T12:00:00+00:00"}


class EventLogTests(unittest.TestCase):
    def test_reading_empty_history_creates_no_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = log_path(Path(directory) / "config.json")
            self.assertEqual(EventLog(path).latest(), [])
            self.assertFalse(path.exists())

    def test_history_persists_across_instances_with_complete_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite3"
            EventLog(path).append(event(1))
            self.assertEqual(EventLog(path).latest(), [event(1)])

    def test_bounded_history_newest_first_and_duplicate_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            log = EventLog(Path(directory) / "events.sqlite3", retention=3)
            for i in range(5):
                log.append(event(i))
            log.append(event(4))
            self.assertEqual([row["id"] for row in log.latest()], ["4", "3", "2"])
            self.assertEqual(len(log.latest(limit=1)), 1)

    def test_clear_removes_all_history(self):
        with tempfile.TemporaryDirectory() as directory:
            log = EventLog(Path(directory) / "events.sqlite3")
            log.append(event(1))
            log.clear()
            self.assertEqual(log.latest(), [])

    def test_two_writers_keep_all_unique_events(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.sqlite3"
            def write(i):
                EventLog(path).append(event(i))
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(write, range(12)))
            self.assertEqual(len(EventLog(path).latest()), 12)

    @unittest.skipUnless(sys.platform == "win32", "Windows runtime status")
    def test_runtime_status_tracks_mutex_lifetime(self):
        path = Path.cwd() / ("test-" + uuid.uuid4().hex + ".json")
        self.assertFalse(listener_running(path))
        claim = claim_listener(path)
        try:
            self.assertTrue(listener_running(path))
        finally:
            claim[0].CloseHandle(claim[1])
        self.assertFalse(listener_running(path))
