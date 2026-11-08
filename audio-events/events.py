"""Audio-independent event dispatch and recognized-phrase matching."""

import math
import re
import time
import uuid
from datetime import datetime, timezone


def words(text):
    return re.findall(r"[a-z0-9']+|\[unk\]", text.lower())


def matching_phrases(result, triggers):
    recognized = result.get("result", [])
    tokens = [item["word"] for item in recognized]
    for trigger in triggers:
        phrase = words(trigger["phrase"])
        for offset in range(len(tokens) - len(phrase) + 1):
            if tokens[offset:offset + len(phrase)] == phrase:
                matched = recognized[offset:offset + len(phrase)]
                confidence = min(item.get("conf", 0) for item in matched)
                if confidence >= trigger["min_confidence"]:
                    yield trigger, matched, confidence
                    break


class EventBus:
    def __init__(self):
        self._handlers = []

    def subscribe(self, handler):
        """Handlers receive an event dict synchronously; keep them fast."""
        self._handlers.append(handler)

    def publish(self, event):
        for handler in self._handlers:
            handler(event)


class PhraseDetector:
    def __init__(self, triggers, bus, clock=time.monotonic):
        if not triggers:
            raise ValueError("Configure at least one trigger")
        self.triggers = triggers
        self.bus = bus
        self.clock = clock
        self.last_fired = {}
        ids = set()
        phrases = set()
        for trigger in triggers:
            trigger_id = trigger["id"]
            phrase = tuple(words(trigger["phrase"]))
            if not trigger_id or trigger_id in ids or not phrase or phrase in phrases:
                raise ValueError("Triggers need unique ids and unique, nonempty phrases")
            if "[unk]" in phrase or not trigger["event"]:
                raise ValueError("Trigger phrases cannot contain [unk]; event must be nonempty")
            confidence = trigger["min_confidence"]
            cooldown = trigger["cooldown_seconds"]
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ValueError("min_confidence must be between 0 and 1")
            if not math.isfinite(cooldown) or cooldown < 0:
                raise ValueError("cooldown_seconds must be finite and nonnegative")
            ids.add(trigger_id)
            phrases.add(phrase)

    def accept(self, result):
        """Only finalized Vosk word results enter this boundary, never partials."""
        recognized = result.get("result", [])
        tokens = [item["word"] for item in recognized]
        for trigger in self.triggers:
            phrase = words(trigger["phrase"])
            for offset in range(len(tokens) - len(phrase) + 1):
                if tokens[offset:offset + len(phrase)] != phrase:
                    continue
                matched = recognized[offset:offset + len(phrase)]
                confidence = min(item.get("conf", 0) for item in matched)
                if confidence < trigger["min_confidence"]:
                    continue
                now = self.clock()
                last = self.last_fired.get(trigger["id"], -math.inf)
                if now - last < trigger["cooldown_seconds"]:
                    break
                self.last_fired[trigger["id"]] = now
                self.bus.publish({
                    "id": str(uuid.uuid4()),
                    "type": trigger["event"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "microphone",
                    "trigger_id": trigger["id"],
                    "phrase": trigger["phrase"],
                    "confidence": round(confidence, 4),
                })
                break
