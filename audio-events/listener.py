"""Offline microphone -> wake phrase + arguments -> JSON events."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import queue
import sys
import threading
import time
import wave

from commands import CommandDetector
from actions import run_action
from audio_feedback import play_clip, select_audio, speak_text
from configuration import read_config
from events import EventBus, words
from event_log import EventLog, log_path
from recognition import RecognitionEngine
from vocabulary import grammar_phrases, trigger_vocabulary

ROOT = Path(__file__).resolve().parent


def validate_vocabulary(model, config):
    for trigger in config["triggers"]:
        for word in words(trigger["phrase"]):
            if model.vosk_model_find_word(word) < 0:
                raise ValueError(f"Model does not know {word!r}; choose another model or phrase")
        vocabulary = trigger.get("vocabulary", {})
        if vocabulary.get("enabled"):
            for phrase in grammar_phrases(trigger_vocabulary(trigger)):
                for word in words(phrase):
                    if model.vosk_model_find_word(word) < 0:
                        raise ValueError(f"Vocabulary for {trigger['id']!r}: model does not know {word!r}. "
                                         "Add a spoken alias made from known words, or choose another model.")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--device", help="Input device index or name (overrides config)")
    parser.add_argument("--check", action="store_true", help="Validate model/config without recording")
    parser.add_argument("--validate-config", action="store_true", help="Validate config/model without microphone access")
    parser.add_argument("--debug", action="store_true", help="Print final transcripts to stderr")
    parser.add_argument("--events", type=Path, help="Also append emitted events to a JSONL file")
    parser.add_argument("--wav", type=Path, help="Process a mono 16-bit PCM WAV instead of microphone")
    parser.add_argument("--duration", type=float, help="Stop microphone capture after this many seconds")
    args = parser.parse_args()
    if args.duration is not None and not 0 < args.duration < float("inf"):
        parser.error("--duration must be a finite positive number")
    return args


def main(feedback=lambda update: None, stop_event=None, args=None):
    args = args or parse_args()
    stop_event = stop_event or threading.Event()

    import sounddevice as sd
    from vosk import Model, SetLogLevel

    if args.list_devices:
        print(sd.query_devices())
        return
    config = read_config(args.config)
    model_path = args.config.resolve().parent / config["model_path"]
    if not model_path.is_dir():
        raise ValueError(f"Model missing: {model_path}. Run setup.ps1 first.")
    SetLogLevel(-1)
    model = Model(str(model_path))
    validate_vocabulary(model, config)
    if args.validate_config:
        print("Config and phrase vocabulary OK.", file=sys.stderr)
        return
    rate = config["sample_rate"]
    device = args.device if args.device is not None else config.get("device")
    if isinstance(device, str) and device.isdecimal():
        device = int(device)
    if args.check:
        sd.check_input_settings(device=device, channels=1, dtype="int16", samplerate=rate)
        print("Config, phrase vocabulary, model, and microphone settings OK.", file=sys.stderr)
        return
    bus = EventBus()
    history = EventLog(log_path(args.config))
    output_lock = threading.Lock()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bobo-action")
    action_slot = threading.BoundedSemaphore()
    audio_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bobo-playback")
    playing = threading.Event()
    disrupted = threading.Event()
    config_dir = args.config.resolve().parent

    def emit(event):
        line = json.dumps(event)
        print(line, flush=True)
        if not args.wav:
            try:
                history.append(event)
            except Exception as error:
                # A full disk or busy history must not disable wake detection.
                print(f"Could not save local event history: {error}", file=sys.stderr)
        if args.events:
            with args.events.open("a", encoding="utf-8") as output:
                output.write(line + "\n")

    def publish(event):
        with output_lock:
            emit(event)
            if args.wav or stop_event.is_set():
                return
            trigger = next((t for t in config["triggers"] if t["id"] == event["trigger_id"]), {})
            clip, response = select_audio(trigger.get("audio_feedback", {}), event)
            if (clip or response) and not playing.is_set():
                playing.set()
                try:
                    audio_executor.submit(play_feedback, clip, response)
                except RuntimeError:
                    # The action may finish as the listener shuts down.
                    playing.clear()

    def play_feedback(clip, response):
        try:
            if clip and not stop_event.is_set():
                try:
                    play_clip(config_dir / clip)
                except Exception as error:
                    print(f"Could not play feedback clip: {error}", file=sys.stderr)
            if response and not stop_event.is_set():
                try:
                    speak_text(response)
                except Exception as error:
                    print(f"Could not speak feedback: {error}", file=sys.stderr)
        finally:
            # Allow speaker echo to fade before accepting new microphone input.
            stop_event.wait(0.25)
            disrupted.set()
            playing.clear()

    bus.subscribe(publish)

    def on_action(rule, event, popup):
        def complete(result):
            event["action"] = {"kind": rule["kind"], "target": rule["target"], **result}
            event["response"] = result["response"]
            if popup:
                feedback(dict(popup, action_result=True, response=result["response"]))
            bus.publish(event)

        if not action_slot.acquire(blocking=False):
            complete({"status": "busy", "response": "Another action is running. Try again when it finishes."})
            return

        def execute():
            try:
                try:
                    result = run_action(rule, event, args.config.resolve().parent)
                except Exception as error:
                    result = {"status": "error", "response": str(error)[:2000]}
                complete(result)
            finally:
                action_slot.release()

        if popup:
            feedback(dict(popup, phase="running"))
        executor.submit(execute)
    debug = (lambda result: print(json.dumps(result), file=sys.stderr)) if args.debug else (lambda result: None)

    def make_engine(current, sample_rate):
        detector = CommandDetector(current["triggers"], bus, feedback, "wav" if args.wav else "microphone", on_action)
        return RecognitionEngine(model, sample_rate, detector, debug)

    if args.wav:
        with wave.open(str(args.wav), "rb") as recording:
            if recording.getnchannels() != 1 or recording.getsampwidth() != 2 or recording.getcomptype() != "NONE":
                raise ValueError("WAV must be uncompressed mono 16-bit PCM")
            engine = make_engine(config, recording.getframerate())
            while data := recording.readframes(1600):
                engine.feed(data)
            engine.end()
        executor.shutdown()
        audio_executor.shutdown()
        return

    engine = make_engine(config, rate)
    audio = queue.Queue(maxsize=50)

    def capture(data, frames, timing, status):
        if playing.is_set():
            return
        if status:
            disrupted.set()
            return
        try:
            audio.put_nowait(bytes(data))
        except queue.Full:
            disrupted.set()

    def signature():
        stat = args.config.stat()
        return stat.st_mtime_ns, stat.st_size

    previous = signature()
    next_check = time.monotonic() + 1
    with sd.RawInputStream(samplerate=rate, blocksize=int(rate / 10), device=device,
                           channels=1, dtype="int16", callback=capture):
        print("Listening for " + ", ".join(t["phrase"] for t in config["triggers"]) + ". Ctrl+C to stop.", file=sys.stderr)
        deadline = time.monotonic() + args.duration if args.duration else float("inf")
        try:
            while not stop_event.is_set() and time.monotonic() < deadline:
                if time.monotonic() >= next_check:
                    next_check = time.monotonic() + 1
                    try:
                        current_signature = signature()
                        if current_signature != previous:
                            previous = current_signature
                            updated = read_config(args.config)
                            if any(updated.get(key) != config.get(key) for key in ("device", "sample_rate", "model_path")):
                                raise ValueError("Microphone/model changes require restarting the listener")
                            validate_vocabulary(model, updated)
                            replacement = make_engine(updated, rate)
                            engine.detector.cancel("settings_changed")
                            engine = replacement
                            config = updated
                            disrupted.set()
                            print("Trigger settings reloaded locally.", file=sys.stderr)
                    except Exception as error:
                        print(f"Settings reload skipped: {error}", file=sys.stderr)
                if playing.is_set():
                    stop_event.wait(0.05)
                    continue
                if disrupted.is_set():
                    while True:
                        try:
                            audio.get_nowait()
                        except queue.Empty:
                            break
                    engine.cancel()
                    disrupted.clear()
                    print("Audio reset: discarded backlog and unfinished input.", file=sys.stderr)
                try:
                    data = audio.get(timeout=0.1)
                except queue.Empty:
                    continue
                if not playing.is_set() and not disrupted.is_set():
                    engine.feed(data)
        finally:
            stop_event.set()
            engine.detector.cancel("listener_stopped")
            executor.shutdown(wait=False)
            audio_executor.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nListener stopped.", file=sys.stderr)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
