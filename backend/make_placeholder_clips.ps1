# Placeholder radio clips via Windows SAPI, for smoke-testing the pipeline only.
# These are synthetic and monotone: they vary in rate and loudness (so arousal moves)
# but they cannot produce realistic vocal strain. Record real voices before the demo.

param([string]$OutDir = "$PSScriptRoot\sample_audio\placeholder")

Add-Type -AssemblyName System.Speech
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$clips = @(
    @{ Name = "baseline_1"; Rate = 0;  Volume = 70; Text = "Copy that, understood. Balance feels okay on this set." }
    @{ Name = "baseline_2"; Rate = 0;  Volume = 70; Text = "Yeah the car is working fine here, no complaints so far." }
    @{ Name = "baseline_3"; Rate = 0;  Volume = 70; Text = "Understood, staying out for now. Let me know the gap." }
    @{ Name = "calm_ask";   Rate = 0;  Volume = 70; Text = "What is the gap to the car behind me right now?" }
    @{ Name = "stressed";   Rate = 5;  Volume = 100; Text = "There is no grip at all out here, the rear is completely gone, I cannot hold this pace." }
    @{ Name = "selfblame";  Rate = 4;  Volume = 95; Text = "That was me, I lost it in turn four, sorry about that." }
    @{ Name = "tired";      Rate = -5; Volume = 40; Text = "I am really struggling now, my neck is gone and I cannot see the braking points." }
    @{ Name = "downplay";   Rate = -3; Volume = 45; Text = "No it is fine, I am fine, do not worry about it." }
    @{ Name = "hazard";     Rate = 6;  Volume = 100; Text = "Yellow flag, yellow flag, there is a car in the wall at turn seven." }
)

foreach ($clip in $clips) {
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $synth.Rate = $clip.Rate
    $synth.Volume = $clip.Volume
    $path = Join-Path $OutDir "$($clip.Name).wav"
    $synth.SetOutputToWaveFile($path)
    $synth.Speak($clip.Text)
    $synth.Dispose()
    Write-Host "  wrote $($clip.Name).wav"
}

Write-Host "`n$($clips.Count) placeholder clips in $OutDir"
