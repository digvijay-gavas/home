"""Offline microphone -> phrase detector -> JSON events."""

import argparse
import json
from pathlib import Path
import queue
import sys
import threading
import time
import wave

from events import EventBus, PhraseDetector, words

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--device", help="Input device index or name (overrides config)")
    parser.add_argument("--check", action="store_true", help="Validate model/config without recording")
    parser.add_argument("--debug", action="store_true", help="Print final recognition results to stderr")
    parser.add_argument("--events", type=Path, help="Also append emitted events to a JSONL file")
    parser.add_argument("--wav", type=Path, help="Process a mono 16-bit PCM WAV instead of microphone")
    parser.add_argument("--duration", type=float, help="Stop microphone capture after this many seconds")
    args = parser.parse_args()
    if args.duration is not None and not 0 < args.duration < float("inf"):
        parser.error("--duration must be a finite positive number")

    import sounddevice as sd
    from vosk import KaldiRecognizer, Model, SetLogLevel

    if args.list_devices:
        print(sd.query_devices())
        return
    config = json.loads(args.config.read_text(encoding="utf-8"))
    bus = EventBus()
    detector = PhraseDetector(config["triggers"], bus)
    model_path = args.config.resolve().parent / config["model_path"]
    if not model_path.is_dir():
        raise ValueError(f"Model missing: {model_path}. Run setup.ps1 first.")
    SetLogLevel(-1)
    model = Model(str(model_path))
    for trigger in config["triggers"]:
        for word in words(trigger["phrase"]):
            if model.vosk_model_find_word(word) < 0:
                raise ValueError(f"Model does not know {word!r}; choose another model or phrase")
    grammar = json.dumps([" ".join(words(t["phrase"])) for t in config["triggers"]] + ["[unk]"])
    rate = config["sample_rate"]
    device = args.device if args.device is not None else config.get("device")
    if isinstance(device, str) and device.isdecimal():
        device = int(device)
    if args.check:
        sd.check_input_settings(device=device, channels=1, dtype="int16", samplerate=rate)
        print("Config, phrase vocabulary, model, and microphone settings OK.", file=sys.stderr)
        return

    def emit(event):
        if args.wav:
            event["source"] = "wav"
        line = json.dumps(event)
        print(line, flush=True)
        if args.events:
            with args.events.open("a", encoding="utf-8") as output:
                output.write(line + "\n")

    bus.subscribe(emit)

    def accept(result):
        parsed = json.loads(result)
        if args.debug:
            print(json.dumps(parsed), file=sys.stderr)
        detector.accept(parsed)

    if args.wav:
        with wave.open(str(args.wav), "rb") as recording:
            if recording.getnchannels() != 1 or recording.getsampwidth() != 2 or recording.getcomptype() != "NONE":
                raise ValueError("WAV must be uncompressed mono 16-bit PCM")
            recognizer = KaldiRecognizer(model, recording.getframerate(), grammar)
            recognizer.SetWords(True)
            while data := recording.readframes(4000):
                if recognizer.AcceptWaveform(data):
                    accept(recognizer.Result())
            accept(recognizer.FinalResult())
        return

    recognizer = KaldiRecognizer(model, rate, grammar)
    recognizer.SetWords(True)
    audio = queue.Queue(maxsize=20)  # Five seconds; never build an unbounded audio backlog.
    disrupted = threading.Event()

    def capture(data, frames, timing, status):
        if status:
            disrupted.set()
            return
        try:
            audio.put_nowait(bytes(data))
        except queue.Full:
            disrupted.set()

    with sd.RawInputStream(samplerate=rate, blocksize=int(rate / 4), device=device,
                           channels=1, dtype="int16", callback=capture):
        phrases = ", ".join(t["phrase"] for t in config["triggers"])
        print(f'Listening for {phrases!r}. Press Ctrl+C to stop. Events go to stdout.', file=sys.stderr)
        deadline = time.monotonic() + args.duration if args.duration else float("inf")
        while time.monotonic() < deadline:
            if disrupted.is_set():
                # Gaps must not join unrelated speech into a wake phrase.
                while True:
                    try:
                        audio.get_nowait()
                    except queue.Empty:
                        break
                recognizer.Reset()
                disrupted.clear()
                print("Audio gap: discarded backlog and reset recognition.", file=sys.stderr)
            try:
                data = audio.get(timeout=0.25)
            except queue.Empty:
                continue
            if recognizer.AcceptWaveform(data):
                accept(recognizer.Result())
    # Deliberately discard unfinished speech when stopping.


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nListener stopped.", file=sys.stderr)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        sys.exit(1)
