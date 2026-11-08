# Bobo audio events

An offline voice-trigger listener with command input and optional desktop
feedback. These two speaking styles produce the same event and input:

- “Hey Bobo, what is the time now?”
- “Hey Bobo” → pause → “What is the time now?”

It captures the words; it does **not** answer the question or execute commands.
No cloud account, API key, camera, or internet connection is needed at runtime.
No audio or events are uploaded. Audio buffers and recent recognition results
stay in bounded memory and are discarded. Audio is never saved by the listener.

## Install and launch

Requires Windows, Python 3.10+ x64 with Tkinter, and a microphone. Tested with
Python 3.14 x64. From the repository root:

```powershell
cd audio-events
.\setup.ps1
```

Setup downloads dependencies into `.venv` and the roughly 40 MB English model
into `models`. Setup needs internet; listening and settings do not. Downloaded
files, test audio, and optional event logs are excluded from Git.

- **`start.bat`** starts the listener and optional event popups. No settings
  window opens. Keep its console running; Ctrl+C stops listening and closes
  feedback. `start.ps1` starts the same runtime.
- **`ui.bat`** opens **settings only**. It never opens the microphone. Closing
  settings leaves a separately running listener active.
- `listener.py` is the headless JSON-only entry point if popups are unwanted.

### Floating desktop control

Double-click **`bobo.bat`** for a small, always-on-top **B** button with 86%
opacity. It starts with the current listener state; opening it does not start
the microphone. Drag the button anywhere on your desktop; its position is saved
locally in `config.controls.json` and restored next time.

Click or right-click it to open the menu:

- **Start listener / Stop listener** controls the independent listening runtime.
- **Settings / Event log** opens the corresponding tab, reusing the settings
  window and preserving unsaved trigger edits.
- **Quit Bobo** stops the listener and closes the floating control. Closing the
  settings window alone does not stop listening.

The small dot is green while the desktop runtime is running and amber while
off/starting. Controls use named Windows signals within the current local
session, with no sockets, browser, or online service. Only one floating control
and one settings window are opened per config by the updated launchers.
The Windows console launchers remain available for direct use and diagnostics.

Stop any old listener before launching the updated version. The desktop runtime
prevents two instances using the same config within a Windows session. This
does not cover separately launched headless instances.

## Settings

Select a trigger to edit it, or choose **New**. **Save trigger** validates values,
unique IDs/phrases, and the installed model's vocabulary before replacing
`config.json` atomically. **Reload** rereads external changes. A running listener
reloads trigger changes in about a second; any unfinished capture is cancelled.
Microphone, sample-rate, and model changes require a listener restart.

The **Event log** tab shows completed microphone events, including their time,
event name, wake phrase, and captured input. Select a row to inspect the full
event. The list refreshes every second, shows the latest 200 events, and retains
the latest 1,000 in a local SQLite file (`config.events.sqlite3` beside your
config). It persists when settings closes. **Clear history** removes saved events
after confirmation. The database is excluded from Git; nothing is uploaded.
Audio itself is not saved. Earlier events from before logging was added cannot
be recovered. WAV tests and popup previews do not enter this microphone history.

The tab also shows whether the desktop listener runtime is running. This checks
the runtime's Windows session mutex without opening the microphone; separately
launched headless listeners are not covered by this status indicator.

| Setting | Meaning |
| --- | --- |
| Wake phrase | Spoken phrase that opens a session |
| Event name | Type of the final emitted event |
| Trigger ID | Stable, unique identifier for the rule |
| Confidence | Minimum score for each recognized wake word |
| Cooldown / popup hold | Suppress repeat activation for this long after the event; hold the completed popup for the same period |
| Capture speech | Include words spoken after the wake phrase as `input` |
| Show feedback popup | Show a small local overlay for this trigger |
| Wait for input | Time allowed to begin speaking after the wake phrase (default 5 s) |
| End after silence | Silence after the input that completes the command (default 1.2 s) |
| Maximum capture | Maximum capture duration after the wake phrase (default 15 s) |

Choose **Edit speech vocabulary…** to configure recognition for a trigger.
Enable speech capture, then add terms, example sentences, or spoken aliases
such as `team center = Teamcenter`. With that alias, an
example sentence like `open Teamcenter` uses `open team center` for recognition
and writes `open Teamcenter` in the event's `input` and feedback. The event log
also keeps `raw_input` with the decoder's original words. Apply the vocabulary
and choose **Save trigger**. Reopen settings and restart the listener once
after installing this version to load the new code.

Aliases also work in open dictation when the decoded words match the spoken
side of the alias. To change what Vosk listens for, enable **Focus recognition
on these words and sentences**. This narrows the decoder to the listed terms
and sentence words, so include the surrounding words you expect to say. The
installed model must know the spoken words used in focused mode. Use Event log
to compare `raw_input` with the final `input` and check `recognition_mode`.

### Command actions

Open **Edit command actions…** for a trigger with speech capture enabled.
Choose **New group**, pick a script or a registered callback, and enter the
sentences that should run it, one per line. Choose **Apply to trigger**, then
**Save trigger**. Add or save a group before switching to a different group.

Hey Bobo comes with `current_time`. Say **“Hey Bobo, what is the time now?”**
to get the computer's local time in the feedback popup and Event log. To add
another Python callback, register a function that accepts the event dictionary
and returns response text in `CALLBACKS` in `actions.py`.

Scripts can be `.bat`, `.cmd`, or `.sh`. Relative paths start beside the config
file. Scripts run from their own folder, with a 30-second timeout and no speech
arguments. Windows `.sh` support uses Bash from Git for Windows. Use trusted
scripts because a matching voice command runs them with your account's access.

Actions require an exact match of the complete captured command after aliases,
with recognized words meeting the trigger's confidence threshold. Focused mode
includes action sentences in its vocabulary. Only completed microphone events
dispatch actions. Matched events include `action` status and `response` after
the action completes. Feedback displays the response when enabled for the
trigger. The listener runs one action at a time and reports busy if another
match arrives while it is running.

The popup appears on wake detection and shows **Listening…**, then the recognized
input. After the event completes, it stays for the cooldown period, then closes.
It stays out of the taskbar and is configured not to take keyboard focus on
Windows. The × button dismisses feedback for that session without cancelling
capture or stopping the listener. Long input can be scrolled in the popup.
**Preview feedback** shows a sample without using the microphone or emitting an
event. Turning feedback off still emits events normally.

Existing rules without the new settings remain phrase-only with no feedback.
The included Hey Bobo rule enables both command capture and feedback and uses
the event name `voice_command.received`. New rules default to the same mode.

## Events

Stdout contains one JSON object per completed session. Status/errors go to
stderr. The wake signal and partial drafts are internal UI updates; they do not
emit duplicate application events.

```json
{
  "id": "...",
  "type": "voice_command.received",
  "timestamp": "2026-11-08T12:00:00+00:00",
  "source": "microphone",
  "trigger_id": "hey_bobo",
  "phrase": "hey bobo",
  "confidence": 0.99,
  "input": "what is the time now",
  "reason": "silence"
}
```

`reason` is `silence`, `no_input`, `max_duration`, `trigger_only`, or
`end_of_file` for a file ending during capture. Saying only the wake phrase
eventually emits `input: ""` with `reason: "no_input"`. Shutdown, an audio gap,
or settings reload cancels an unfinished session without publishing partial
input. `confidence` describes the wake words, not the accuracy of the input.

```powershell
.\start.ps1 --list-devices
.\start.ps1 --device 1 --check
.\start.ps1 --device 1 --events events.jsonl
.\.venv\Scripts\python.exe listener.py --wav test-audio\continuous.wav
```

Microphone events are automatically saved in the local SQLite history. `--events`
also writes completed events to a local JSONL file. Both include captured input.
`--debug` prints finalized recognition results to stderr and
may include unrelated speech; leave it off for normal use. WAV input must be
uncompressed mono 16-bit PCM. File tests use audio time for timeouts/cooldowns,
so they behave consistently even when processed faster than real time.

## Implementation

`microphone -> parallel wake + full Vosk recognition -> command session -> EventBus -> JSON / optional feedback`

The restricted wake decoder focuses on configured phrases. A second,
unrestricted decoder processes the same audio so the command is retained even
when spoken without a pause. Wake word timestamps separate the phrase from its
arguments even if the full decoder spells the name differently. Stable word
results update the popup; a finalized speech segment plus silence ends input.
This uses more CPU than the original phrase-only implementation. Both decoders
share the same locally loaded model and make no network calls.

`config.json` defines rules; `configuration.py` validates/persists them;
`commands.py` manages command sessions; `recognition.py` runs the decoders;
`listener.py` captures audio and emits JSON; `runtime.py` owns the transient
feedback UI; `feedback.py` draws it; `ui.py` is the independent settings editor.
`EventBus` and the original `PhraseDetector` remain available in `events.py`.

Recognition can miss accents or mistake similar sounds. Wake confidence is a
decoder score, not a calibrated probability. Recorded voices can also trigger
it. This is CPU-based speech recognition, not dedicated low-power hardware. It
cannot hear while the computer sleeps. Automatic startup is not registered.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\start.ps1 --check
.\start.ps1 --duration 5

# Optional real-model tests with locally generated speech:
powershell.exe -NoProfile -File tests/generate_audio.ps1
$env:BOBO_AUDIO_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests cover continuous and paused commands, unrelated audio, empty-input
timeouts, cooldowns, cancellation, feedback timers, and config persistence.
Windows speech synthesis generates the fixtures locally, without playing or
recording microphone audio.

Dependencies: Vosk (Apache-2.0), python-sounddevice (MIT), their transitive
dependencies, and Python's built-in Tkinter. The included model is Apache-2.0.
Existing `lan-desktop` settings are unchanged.
