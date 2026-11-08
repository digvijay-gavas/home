"""Audio-time command sessions. No microphone, GUI, or network dependencies."""

from datetime import datetime, timezone
import math
import uuid

from events import matching_phrases
from vocabulary import apply_aliases


class CommandDetector:
    def __init__(self, triggers, bus, feedback=lambda update: None, source="microphone"):
        self.triggers = triggers
        self.bus = bus
        self.feedback = feedback
        self.source = source
        self.active = None
        self.cooldowns = {}

    def wake_match(self, wake_result, audio_time):
        if self.active is None:
            for match in matching_phrases(wake_result, self.triggers):
                if audio_time >= self.cooldowns.get(match[0]["id"], -math.inf):
                    return match
        return None

    def observe(self, wake_result, transcript, audio_time, speech_pending=False):
        match = self.wake_match(wake_result, audio_time)
        if match:
            trigger, matched, confidence = match
            self.active = {
                "id": str(uuid.uuid4()), "trigger": trigger, "confidence": confidence,
                "wake_end": matched[-1]["end"], "input": "", "last_word_end": None,
            }
            self._feedback("listening")
            if not trigger.get("capture_arguments", False):
                return self.finish(audio_time, "trigger_only")
        if self.active is None:
            return False
        session = self.active
        # Use word times, rather than searching the full transcript for the name:
        # the unrestricted decoder may spell Bobo differently.
        after_wake = [word for word in transcript if word["start"] >= session["wake_end"] - 0.08]
        argument_words = [word for word in after_wake if word["word"] != "[unk]"]
        text = " ".join(word["word"] for word in argument_words)
        vocabulary = session["trigger"].get("vocabulary", {})
        if vocabulary.get("enabled") or vocabulary.get("aliases"):
            session["raw_input"] = text
            text = apply_aliases(" ".join(word["word"] for word in after_wake), vocabulary)
        if text != session["input"]:
            session["input"] = text
            self._feedback("listening")
        if argument_words:
            session["last_word_end"] = argument_words[-1]["end"]
        trigger = session["trigger"]
        if audio_time - session["wake_end"] >= trigger.get("max_argument_seconds", 15.0):
            return self.finish(audio_time, "max_duration")
        if session["last_word_end"] is not None:
            if not speech_pending and audio_time - session["last_word_end"] >= trigger.get("silence_seconds", 1.2):
                return self.finish(audio_time, "silence")
        elif audio_time - session["wake_end"] >= trigger.get("argument_timeout_seconds", 5.0):
            # Do not abandon speech already being decoded merely because the
            # first stable word has not arrived yet.
            if not speech_pending:
                return self.finish(audio_time, "no_input")
        return False

    def _feedback(self, phase, reason=None):
        session = self.active
        trigger = session["trigger"]
        if trigger.get("show_feedback", False):
            self.feedback({"phase": phase, "session_id": session["id"], "phrase": trigger["phrase"],
                           "input": session["input"], "event": trigger["event"],
                           "cooldown_seconds": trigger["cooldown_seconds"], "reason": reason})

    def finish(self, audio_time, reason):
        if self.active is None:
            return False
        session = self.active
        trigger = session["trigger"]
        event = {
            "id": session["id"], "type": trigger["event"],
            "timestamp": datetime.now(timezone.utc).isoformat(), "source": self.source,
            "trigger_id": trigger["id"], "phrase": trigger["phrase"],
            "confidence": round(session["confidence"], 4), "input": session["input"], "reason": reason,
        }
        vocabulary = trigger.get("vocabulary", {})
        if vocabulary.get("enabled") or vocabulary.get("aliases"):
            event["raw_input"] = session.get("raw_input", "")
            event["recognition_mode"] = "event_vocabulary" if vocabulary.get("enabled") else "open_dictation"
        self.cooldowns[trigger["id"]] = audio_time + trigger["cooldown_seconds"]
        self._feedback("complete", reason)
        self.active = None
        self.bus.publish(event)
        return True

    def cancel(self, reason="audio_gap"):
        if self.active:
            self._feedback("cancelled", reason)
            self.active = None
