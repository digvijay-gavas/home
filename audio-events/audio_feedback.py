"""Local Windows sound clips and speech output for completed events."""

import math
import os
from pathlib import Path
import random
import subprocess
import wave

MAX_SPEECH_CHARS = 500
VOICE_OPTIONS = ("default", "female")


def validate_audio_feedback(settings):
    if not isinstance(settings, dict):
        raise ValueError("Audio feedback must be an object")
    clips = settings.get("clips", [])
    if not isinstance(clips, list) or any(
        not isinstance(path, str) or Path(path).suffix.lower() != ".wav" for path in clips
    ):
        raise ValueError("Audio clips must be .wav paths")
    if len(clips) != len(set(clips)):
        raise ValueError("Each audio clip should be listed once")
    chance = settings.get("clip_chance_percent", 100)
    if type(chance) not in (int, float) or not math.isfinite(chance) or not 0 <= chance <= 100:
        raise ValueError("Clip chance must be a percentage from 0 to 100")
    for field in ("speak_response", "wake_cue"):
        if type(settings.get(field, False)) is not bool:
            raise ValueError(f"{field} must be true or false")
    text = settings.get("spoken_text", "")
    if not isinstance(text, str) or len(text) > MAX_SPEECH_CHARS:
        raise ValueError(f"Speak this text must be at most {MAX_SPEECH_CHARS} characters")
    if settings.get("voice", "default") not in VOICE_OPTIONS:
        raise ValueError("Voice must be Windows default or female")


def select_wake_audio(settings, rng=random):
    clips = settings.get("clips", [])
    chance = settings.get("clip_chance_percent", 100)
    clip = rng.choice(clips) if clips and chance > 0 and rng.random() * 100 < chance else None
    return clip, settings.get("spoken_text", "").strip() or None


def select_response(settings, event):
    response = (event.get("response") or "").strip() if settings.get("speak_response") and not event.get("response_already_spoken") else ""
    return response[:MAX_SPEECH_CHARS] or None


def play_clip(path):
    import winsound

    # Bound the microphone pause and reject malformed or unsupported files.
    with wave.open(str(path), "rb") as clip:
        if clip.getnframes() / clip.getframerate() > 15:
            raise ValueError("Choose a WAV clip no longer than 15 seconds")
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_NODEFAULT)


def play_wake_cue():
    import winsound

    winsound.Beep(880, 100)


def speak_text(text, voice="default"):
    powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    # Pass speech through stdin, separate from the fixed PowerShell code.
    select_voice = ""
    if voice == "female":
        select_voice = (
            "$female = $voice.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Gender -eq 'Female' } | Select-Object -First 1; "
            "if ($female) { $voice.SelectVoice($female.VoiceInfo.Name) }; "
        )
    script = (
        "$ErrorActionPreference = 'Stop'; "
        "Add-Type -AssemblyName System.Speech; "
        "[Console]::InputEncoding = [Text.Encoding]::UTF8; "
        "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "try { " + select_voice + "$voice.Speak([Console]::In.ReadToEnd()) } finally { $voice.Dispose() }"
    )
    subprocess.run([str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
                   input=text.encode("utf-8"), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                   check=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
