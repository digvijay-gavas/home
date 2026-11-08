"""Explicit sentence-to-action rules and local action execution."""

from datetime import datetime
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading

from events import words


def current_time(_event):
    return datetime.now().astimezone().strftime("It is %I:%M %p.")


CALLBACKS = {"current_time": current_time}
SCRIPT_SUFFIXES = (".bat", ".cmd", ".sh", ".py", ".js")


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
            if Path(target).suffix.lower() not in SCRIPT_SUFFIXES:
                raise ValueError("Choose a .bat, .cmd, .sh, .py, or .js script")
            if type(rule.get("speak_stdout", False)) is not bool:
                raise ValueError("Report script output must be true or false")
            for field in ("start_message", "success_message"):
                message = rule.get(field, "")
                if not isinstance(message, str) or len(message) > 500:
                    raise ValueError(f"{field} must be text up to 500 characters")
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
    suffix = path.suffix.lower()
    if suffix == ".py":
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":
            python = python.with_name("python.exe")
        return [str(python), "-u", "-X", "utf8", str(path)]
    if suffix == ".js":
        node = shutil.which("node.exe" if sys.platform == "win32" else "node")
        if not node:
            raise ValueError("Put Node.js on PATH to run .js scripts")
        return [node, str(path)]
    if suffix in (".bat", ".cmd"):
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


def run_script(path, on_output, report_plain_output=False):
    process = subprocess.Popen(script_command(path), cwd=path.parent, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    last = ""
    final = ""
    active = threading.Event()
    active.set()

    def read_output():
        nonlocal last, final
        started = False
        # The reader owns the pipe. A detached child can keep it open after the
        # script exits, so the action worker never waits indefinitely for EOF.
        with process.stdout as stdout:
            while line := stdout.readline(2048):
                if not active.is_set():
                    break
                # Skip the remainder of an overlong line without accumulating it.
                if not line.endswith(b"\n") and len(line) == 2048:
                    while (remainder := stdout.readline(2048)) and not remainder.endswith(b"\n"):
                        pass
                text = line.decode("utf-8", errors="replace").strip()[:500]
                if not text or not active.is_set() or final:
                    continue
                if text.startswith("BOBO:FINAL:"):
                    final = text.removeprefix("BOBO:FINAL:").strip()
                elif text.startswith("BOBO:START:"):
                    message = text.removeprefix("BOBO:START:").strip()
                    if message and not started:
                        started = True
                        if on_output:
                            on_output(message)
                elif report_plain_output:
                    last = text
                    if on_output:
                        on_output(text)

    reader = threading.Thread(target=read_output, daemon=True, name="bobo-script-output")
    reader.start()
    try:
        code = process.wait(timeout=30)
        reader.join(timeout=1)
        return code, final, last
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise
    finally:
        active.clear()


def run_action(rule, event, config_dir, on_output=None):
    try:
        if rule["kind"] == "callback":
            return {"status": "ok", "response": str(CALLBACKS[rule["target"]](dict(event)))[:2000]}
        path = (config_dir / rule["target"]).resolve(strict=True)
        if not path.is_file() or path.suffix.lower() not in SCRIPT_SUFFIXES:
            raise ValueError("Action target must resolve to a script file")
        code, final, last = run_script(path, on_output, rule.get("speak_stdout", False))
        if code:
            return {"status": "error", "response": final or f"Script exited with code {code}."}
        return {"status": "ok", "response": final or rule.get("success_message", "").strip() or last or "Script completed."}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return {"status": "error", "response": str(error)[:2000]}
