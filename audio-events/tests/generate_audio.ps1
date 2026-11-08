$ErrorActionPreference = 'Stop'
# Run with Windows PowerShell: powershell.exe -File tests/generate_audio.ps1
Add-Type -AssemblyName System.Speech
$destination = Join-Path $PSScriptRoot '../test-audio'
New-Item -ItemType Directory -Force $destination | Out-Null
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
try {
    foreach ($case in @(
        @{ Name = 'continuous'; Text = 'Hey Bobo, what is the time now?' },
        @{ Name = 'paused'; Text = 'Hey Bobo.<break time="1800ms"/>What is the time now?' },
        @{ Name = 'unrelated'; Text = 'The weather is sunny today. Please open the window.' },
        @{ Name = 'wake-only'; Text = 'Hey Bobo.' }
    )) {
        $synth.SetOutputToWaveFile((Join-Path $destination ($case.Name + '.wav')), $format)
        $synth.SpeakSsml('<speak version="1.0" xml:lang="en-US">' + $case.Text + '<break time="7000ms"/></speak>')
        $synth.SetOutputToNull()
    }
} finally {
    $synth.Dispose()
}
