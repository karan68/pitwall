"""Throwaway harness: does the analysis engine measure what it claims to measure?

Every check is a known-answer test or an ablation, so a regression here means
the numbers shown on the pit wall stopped meaning what the UI says they mean.

Run:  .venv\\Scripts\\python.exe verify_features.py
"""
import numpy as np

from services import advisor, analytics, content, state
from services.features import extract, signal_quality

SR = 16000
RESULTS = []


def check(label, passed, detail=""):
    RESULTS.append(passed)
    print(f"  [{'PASS' if passed else 'FAIL'}] {label}{f'  {detail}' if detail else ''}")


def synth_voice(f0, seconds=2.0, jitter=0.0, tremor=0.0, noise=0.0, amp=0.3, harmonics=6):
    """A glottal-source-like signal with controllable pitch, instability and noise."""
    n = int(SR * seconds)
    t = np.arange(n) / SR
    rng = np.random.default_rng(7)

    inst_f0 = f0 * (1 + jitter * np.cumsum(rng.standard_normal(n)) / np.sqrt(n))
    phase = 2 * np.pi * np.cumsum(inst_f0) / SR

    signal = sum(np.sin(k * phase) / k for k in range(1, harmonics + 1))
    signal = signal / np.abs(signal).max()

    if tremor:  # amplitude instability -> shimmer
        signal *= 1 + tremor * np.sin(2 * np.pi * 7 * t) * rng.uniform(0.6, 1.4, n)

    # Gate speech on and off so the clip has pauses, like real radio.
    gate = (np.sin(2 * np.pi * 1.6 * t) > -0.55).astype(float)
    gate = np.convolve(gate, np.ones(400) / 400, mode="same")
    signal = amp * signal * gate

    if noise:
        signal += noise * rng.standard_normal(n)
    return signal.astype(np.float32)


print("\n1. Pitch tracking recovers a known F0")
for target in (95, 140, 220, 300):
    measured = extract(synth_voice(target), SR)["f0MeanHz"]
    check(f"F0 {target} Hz", abs(measured - target) <= target * 0.06, f"got {measured} Hz")

print("\n2. Instability measures respond to instability")
steady = extract(synth_voice(150), SR)
shaky = extract(synth_voice(150, jitter=0.30, tremor=0.5), SR)
check("unstable voice reads higher jitter", shaky["jitterPct"] > steady["jitterPct"],
      f"{steady['jitterPct']}% -> {shaky['jitterPct']}%")
check("unstable voice reads higher shimmer", shaky["shimmerPct"] > steady["shimmerPct"],
      f"{steady['shimmerPct']}% -> {shaky['shimmerPct']}%")

print("\n3. Harmonics-to-noise ratio falls as noise is added")
clean = extract(synth_voice(150), SR)["hnrDb"]
noisy = extract(synth_voice(150, noise=0.05), SR)["hnrDb"]
check("clean voice has higher HNR", clean > noisy, f"{clean} dB -> {noisy} dB")

print("\n4. Quality gate accepts good audio and rejects the rest")
cases = [
    ("clean 2s clip", synth_voice(150, amp=0.4), True),
    ("buried in noise", synth_voice(150, amp=0.04, noise=0.3), False),
    ("0.4s fragment", synth_voice(150, seconds=0.4), False),
    ("hard clipped", np.clip(synth_voice(150, amp=3.0), -1, 1), False),
    ("near silence", synth_voice(150, amp=0.005), False),
]
for name, audio, want_usable in cases:
    q = signal_quality(audio, SR)
    check(name, q["usable"] == want_usable, f"usable={q['usable']} snr={q['snrDb']}dB {q['issues']}")

print("\n5. Baseline-relative scoring: a driver's own voice reads Calm")
calm_samples = []
for i in range(4):
    sample = extract(synth_voice(150 + i * 4, jitter=0.02), SR)
    sample["articulationRate"] = 3.2 + i * 0.1
    calm_samples.append(sample)
baseline = state.build_baseline(calm_samples)

own = extract(synth_voice(152, jitter=0.02), SR)
own["articulationRate"] = 3.3
reading = state.classify(own, baseline)
check("own-baseline voice reads Calm", reading["state"] == "Calm",
      f"arousal={reading['arousal']:+.2f} strain={reading['strain']:+.2f} load={reading['driverLoad']}")

print("\n6. Quadrants separate — high arousal alone is not stress")
profiles = {}
for name, audio, rate in [
    ("Locked In", synth_voice(225, jitter=0.02, amp=0.75), 5.4),
    ("Stressed", synth_voice(225, jitter=0.30, tremor=0.5, amp=0.75), 5.4),
    ("Tired", synth_voice(126, jitter=0.30, tremor=0.5, amp=0.12), 2.0),
]:
    f = extract(audio, SR)
    f["articulationRate"] = rate
    profiles[name] = state.classify(f, baseline)
    r = profiles[name]
    print(f"    {name:<10} -> {r['state']:<10} arousal={r['arousal']:+.2f} "
          f"strain={r['strain']:+.2f} load={r['driverLoad']}")

for expected, reading in profiles.items():
    check(f"{expected} profile classified as {expected}", reading["state"] == expected,
          f"got {reading['state']}")

print("\n7. Z-scores stay bounded even against a very tight baseline")
tight = state.build_baseline([extract(synth_voice(150, jitter=0.02), SR) for _ in range(4)])
extreme = extract(synth_voice(300, jitter=0.5, tremor=0.9, amp=0.9), SR)
extreme_reading = state.classify(extreme, tight)
check("no z-score exceeds the clamp",
      all(abs(z) <= state.Z_CLAMP for z in extreme_reading["zScores"].values()),
      f"max |z| = {max(abs(z) for z in extreme_reading['zScores'].values())}")
check("load stays in range", 0 <= extreme_reading["driverLoad"] <= 100,
      f"load={extreme_reading['driverLoad']}")

print("\n8. Message compression respects the radio brevity budget")
long_call = ("Okay so we're looking at plan B which is the two stop, we need you to push "
             "for three laps and then we'll bring you in, and just watch the front left "
             "because it's degrading a bit faster than we expected")
for budget in (26, 12, 6):
    out = advisor.compress(long_call, budget)
    words = len(out["adapted"].split())
    check(f"budget {budget} respected", words <= budget, f'({words}w) "{out["adapted"]}"')

print("\n9. Correlation stays silent until there is enough evidence")
laps = [{"lap": i, "timeSeconds": 92.4 + 0.1 * i} for i in range(1, 21)]
thin = analytics.analyze(laps, [{"lap": 3, "driverLoad": 70.0}], 92.4)
check("1 radio call -> suppressed", not thin["sufficientData"], thin["note"])

events = [{"lap": lap, "driverLoad": load} for lap, load in
          [(2, 48), (5, 52), (8, 74), (10, 82), (12, 71), (15, 55), (18, 50)]]
rich_laps = [{"lap": i, "timeSeconds": 92.4} for i in range(1, 21)]
for e in events:
    rich_laps[e["lap"] - 1]["timeSeconds"] = 92.4 + max(0, e["driverLoad"] - 58) * 0.05
rich = analytics.analyze(rich_laps, events, 92.4)
check("recovers an injected relationship", rich["sufficientData"] and abs(rich["correlation"]) > 0.4,
      f"n={rich['sampleSize']} calls r={rich['correlation']} lag={rich['lagLaps']} "
      f"lost={rich['estimatedSecondsLost']}s ({rich['strength']})")

print("\n10. Advisor holds the radio when it should, and never sits on a safety call")
stressed = {"driverLoad": 82.0, "state": "Stressed", "strain": 1.2, "calibrated": True}
calm = {"driverLoad": 48.0, "state": "Calm", "strain": 0.1, "calibrated": True}
routine = {"intent": "Information request", "priority": "Informational", "downplaying": False}
hazard = {"intent": "Hazard", "priority": "Critical", "downplaying": False}

check("stressed + routine -> Closed",
      advisor.advise(stressed, routine, {})["radioWindow"] == "Closed")
check("stressed + hazard -> Open",
      advisor.advise(stressed, hazard, {})["radioWindow"] == "Open")
check("calm + routine -> Open",
      advisor.advise(calm, routine, {})["radioWindow"] == "Open")

downplay = {"intent": "Acknowledgement", "priority": "Informational", "downplaying": True}
flags = advisor.advise(stressed, downplay, {})["flags"]
check("tone/content mismatch is flagged",
      any(f["title"] == "Possible under-reporting" for f in flags))

print("\n11. Phrase signals survive Whisper's expanded contractions")
# These are verbatim transcripts that the contraction-only term list missed.
whisper_downplay = "No it is fine. I am fine. Do not worry about it."
whisper_limit = "I am really struggling now. My neck is gone and I cannot see the braking points."

check("'it is fine / I am fine / do not worry' reads as downplaying",
      content.text_signals(whisper_downplay)["downplaying"],
      f'"{whisper_downplay}"')
check("'I am struggling / I cannot see' reads as a self-reported limit",
      content.text_signals(whisper_limit)["selfReportedLimit"],
      f'"{whisper_limit}"')
check("a neutral question is neither",
      not any(content.text_signals("What is the gap to the car behind me right now?").values()))
check("hazard terms still detected after normalisation",
      content.text_signals("Yellow flag, yellow flag, there is a car in the wall at turn 7.")["hazardTerms"])

print("\n12. A calm-sounding driver reporting a limit is not treated as free to chat")
limit_content = {
    "intent": "Physical strain", "priority": "Strategic",
    "downplaying": False, "selfReportedLimit": True,
}
before = advisor.advise(calm, {**limit_content, "selfReportedLimit": False}, {})
after = advisor.advise(calm, limit_content, {})

print(f"    ignoring the words -> {before['radioWindow']:<8} \"{before['action']['headline']}\"")
print(f"    acting on them     -> {after['radioWindow']:<8} \"{after['action']['headline']}\"")

check("window escalates off Open", after["radioWindow"] == "Caution")
check("word budget tightens", after["wordBudget"] < before["wordBudget"])
check("no longer invites a full briefing", "anything complex" not in after["action"]["headline"])
check("composed-but-reporting is flagged",
      any(f["title"] == "Reported limit, composed voice" for f in after["flags"]))
check("REGRESSION: safety still overrides a reported limit",
      advisor.advise(calm, {**hazard, "selfReportedLimit": True}, {})["radioWindow"] == "Open")
check("REGRESSION: calm + car problem still gets the debrief window",
      advisor.advise(calm, {"intent": "Car problem", "priority": "Strategic",
                            "downplaying": False, "selfReportedLimit": False}, {})["radioWindow"] == "Open")

passed = sum(1 for r in RESULTS if r)
print(f"\n{'=' * 62}\n  {passed}/{len(RESULTS)} checks passed\n{'=' * 62}")
