"""Explicit sentence-to-action rules and local action execution."""

from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from events import words


def current_time(_event):
    return datetime.now().astimezone().strftime("It is %I:%M %p.")


CALLBACKS = {"current_time": current_time}


def sentence_key(sentence):
    return tuple(words(sentence))


def validate_actions(rules):
    if not isinstance(rules, list):
        raise ValueError("Command actions must be a list")
    seen = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("Each command action must be an object")
        kind, target, sentences = rule.get("kind"), rule.get("target"), rule.get("sentences")
        if not isinstance(target, str) or not target.strip():
            raise ValueError("Each command action needs a callback or script path")
        if kind == "callback":
            if target not in CALLBACKS:
                raise ValueError(f"Unknown callback {target!r}")
        elif kind == "script":
            if Path(target).suffix.lower() not in (".bat", ".cmd", ".sh"):
                raise ValueError("Choose a .bat, .cmd, or .sh script")
        else:
            raise ValueError("Command action must be a script or callback")
        if not isinstance(sentences, list) or not sentences:
            raise ValueError("Enter at least one sentence for each action")
        for sentence in sentences:
            key = sentence_key(sentence) if isinstance(sentence, str) else ()
            if not key or "[unk]" in key or key in seen:
                raise ValueError("Action sentences must be nonempty and unique within a trigger")
            seen.add(key)


def match_action(trigger, text):
    key = sentence_key(text)
    for rule in trigger.get("actions", []):
        if any(sentence_key(sentence) == key for sentence in rule["sentences"]):
            return rule
    return None


def script_command(path):
    if path.suffix.lower() in (".bat", ".cmd"):
        if sys.platform != "win32":
            raise ValueError("Batch scripts require Windows")
        # Pass only a fixed basename to cmd.exe. The directory is passed as cwd,
        # outside shell parsing. Speech never becomes part of the command line.
        if not re.fullmatch(r"[A-Za-z0-9_. -]+", path.name):
            raise ValueError("Batch filename may contain letters, numbers, spaces, dots, hyphens, and underscores")
        cmd = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "cmd.exe"
        return [str(cmd), "/d", "/v:off", "/c", ".\\" + path.name]
    if sys.platform == "win32":
        git = shutil.which("git.exe")
        bash = Path(git).resolve().parent.parent / "bin" / "bash.exe" if git else None
        if bash is None or not bash.is_file():
            raise ValueError("Install Git for Windows and put its git.exe on PATH to run .sh scripts")
    else:
        bash = shutil.which("bash")
        if not bash:
            raise ValueError("Bash is required to run .sh scripts")
    return [str(bash), "--", "./" + path.name]


def run_action(rule, event, config_dir):
    try:
        if rule["kind"] == "callback":
            return {"status": "ok", "response": str(CALLBACKS[rule["target"]](dict(event)))[:2000]}
        path = (config_dir / rule["target"]).resolve(strict=True)
        if not path.is_file() or path.suffix.lower() not in (".bat", ".cmd", ".sh"):
            raise ValueError("Action target must resolve to a script file")
        result = subprocess.run(script_command(path), cwd=path.parent, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            return {"status": "error", "response": f"Script exited with code {result.returncode}."}
        return {"status": "ok", "response": "Script completed."}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {"status": "error", "response": str(error)[:2000]}
