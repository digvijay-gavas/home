# Audio events

An independent, local audio listener. Say **Hey Bobo**, pause briefly, and the
program emits a `wake_word.detected` JSON event. It listens continuously while
running. Stop with Ctrl+C. No camera, cloud account, API key, or internet access
is needed at runtime. Microphone audio stays in a bounded memory queue and is
discarded after processing; audio recordings are not saved.

## Run on Windows

Requires Python 3.10+ x64 and a microphone. Tested here with Python 3.14 x64.
From the repository root:

```powershell
cd audio-events
.\setup.ps1
.\start.ps1
```

Setup installs dependencies in `.venv` and downloads the roughly 40 MB
[Vosk English model](https://alphacephei.com/vosk/models) under `models`.
These are excluded from Git. Setup needs internet; listening does not.
The microphone is opened only by `start.ps1`, not setup. On Windows, enable
microphone access for desktop apps in Settings if capture fails.

After setup, you can also double-click `start.bat` to open the listener in a
terminal. It works from any working directory and accepts the same options as
`start.ps1`. If startup fails, the window stays open so you can read the error.

To choose a microphone, validate setup, or save emitted events:

```powershell
.\start.ps1 --list-devices
.\start.ps1 --device 1 --check
.\start.ps1 --device 1 --events events.jsonl
```

Stdout contains one JSON object per event; status and errors go to stderr.
For example (IDs and times vary):

```json
{"id":"...","type":"wake_word.detected","timestamp":"2026-11-08T12:00:00+00:00","source":"microphone","trigger_id":"hey_bobo","phrase":"hey bobo","confidence":0.95}
```

Another program can read stdout line by line. In-process consumers can subscribe
to `EventBus` in `events.py`; the listener currently registers the JSON output
handler. Handlers run synchronously and should stay fast. No network port is
opened, and recognized text never executes a command.

## How detection works

`microphone -> Vosk restricted speech recognition -> phrase/confidence check -> EventBus -> JSON`

This first version uses CPU-based offline speech recognition, not a dedicated
low-power chip or a trained neural wake-word classifier. It continually decodes
a small phrase grammar plus an unknown-speech alternative. A complete phrase
with every word at or above 0.8 confidence emits an event, then a two-second
per-trigger cooldown suppresses duplicates. Results finalize after a pause;
partial recognition never fires events. An audio overrun discards the backlog
and resets recognition so phrases cannot span dropped audio.

Recognition confidence is the decoder's score, not a calibrated probability.
Unrelated sounds, recordings, or similar phrases can trigger it. Test your voice,
distance, microphone, and room noise before relying on it. The small English
model may struggle with some accents. A custom-trained wake-word model can
replace this detector later while retaining the event interface. No claim of
Siri-level accuracy or hardware-like power consumption is made.

## Add phrase events later

Edit `config.json` and restart. Add another object to `triggers` with a unique
`id`, `phrase`, `event`, `min_confidence` (0–1), and `cooldown_seconds`.
Phrases must consist of words known to the selected model; startup verifies
this. `model_path` is relative to the config file. `device` may be a device
index, name, or `null` for the default. `sample_rate` defaults here to 16000.

This extension point currently supports spoken phrases. Other sound detectors
(claps, alarms, etc.) would be separate producers publishing to the same bus.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\start.ps1 --check
.\start.ps1 --duration 5
.\start.ps1 --wav path\to\sample.wav --debug
```

WAV input must be uncompressed mono 16-bit PCM; its sample rate is read from
the header. WAV events use `source: "wav"`. `--debug` prints final recognition
results to stderr for troubleshooting and may expose unrelated recognized words.
Normal mode emits only matched events. The WAV path exercises the same model,
grammar, confidence checks, and event pipeline as live capture. When processing
files faster than real time, cooldown uses processing time.

There is no automatic startup registration yet. Run the listener in a terminal
for now; it stops on logout, shutdown, or Ctrl+C and cannot hear while the
computer is asleep. No existing `lan-desktop` settings are changed.

Dependencies: [Vosk](https://github.com/alphacep/vosk-api) (Apache-2.0),
[python-sounddevice](https://python-sounddevice.readthedocs.io/) (MIT), and their
transitive dependencies. The selected speech model is Apache-2.0.
