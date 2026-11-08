"""Shared config validation and atomic local persistence."""

import json
import math
from pathlib import Path
import os
import tempfile

from events import EventBus, PhraseDetector


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("Configuration must be an object")
    if not isinstance(config.get("model_path"), str) or not config["model_path"].strip():
        raise ValueError("Model path must be nonempty")
    rate = config.get("sample_rate")
    if type(rate) is not int or rate <= 0:
        raise ValueError("Sample rate must be a positive integer")
    device = config.get("device")
    if device is not None and type(device) not in (str, int):
        raise ValueError("Microphone device must be a name, index, or null")
    triggers = config.get("triggers")
    if not isinstance(triggers, list) or not triggers:
        raise ValueError("Keep at least one trigger")
    for trigger in triggers:
        if not isinstance(trigger, dict):
            raise ValueError("Each trigger must be an object")
        for field in ("id", "phrase", "event"):
            if not isinstance(trigger.get(field), str) or not trigger[field].strip():
                raise ValueError(f"Each trigger needs a nonempty {field}")
        for field in ("min_confidence", "cooldown_seconds"):
            if type(trigger.get(field)) not in (int, float):
                raise ValueError(f"{field} must be a number")
        for field in ("capture_arguments", "show_feedback"):
            if field in trigger and type(trigger[field]) is not bool:
                raise ValueError(f"{field} must be true or false")
        for field, default in (("argument_timeout_seconds", 5.0), ("silence_seconds", 1.2),
                               ("max_argument_seconds", 15.0)):
            value = trigger.get(field, default)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 120:
                raise ValueError(f"{field} must be greater than 0 and at most 120 seconds")
        if trigger.get("max_argument_seconds", 15.0) < trigger.get("argument_timeout_seconds", 5.0):
            raise ValueError("Maximum capture time must be at least the wait-for-input time")
        if trigger["cooldown_seconds"] > 86400:
            raise ValueError("Cooldown / popup hold must be at most 86400 seconds")
    PhraseDetector(triggers, EventBus())
    return config


def read_config(path):
    return validate_config(json.loads(Path(path).read_text(encoding="utf-8")))


def save_config(path, config):
    """A failed write must leave the previous config intact."""
    validate_config(config)
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         suffix=".json", delete=False) as output:
            temporary = Path(output.name)
            json.dump(config, output, indent=2, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
