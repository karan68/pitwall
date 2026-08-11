"""An uncalibrated reading must not drive a comms decision.

Measured with ablate_baseline.py on six real Hamilton calls (Spa 2024): scored
against population priors they read Tired at load 60-73, which closed to Caution,
fired a "Sustained load" warning and recommended an earlier stop. The same six
clips against a valid baseline read Calm at load 50-54 -> "normal comms". The
operational output flipped on baseline size alone, not on the audio.

These checks pin the fix. Each one fails on the pre-fix advisor.

    .venv\\Scripts\\python.exe verify_calibration_gate.py
"""
from services.advisor import advise

# The uncalibrated Hamilton reading, taken verbatim from the ablation run.
UNCALIBRATED = {
    "state": "Tired",
    "driverLoad": 73.5,
    "arousal": 0.21,
    "strain": 2.5,
    "calibrated": False,
}
CALIBRATED = dict(UNCALIBRATED, calibrated=True)

ROUTINE = {"intent": "Acknowledgement", "priority": "Normal", "downplaying": False,
           "selfReportedLimit": False}
CRITICAL = dict(ROUTINE, intent="Hazard", priority="Critical")
LIMIT = dict(ROUTINE, selfReportedLimit=True)
SUSTAINED = {"recentLoads": [68.4, 69.3, 73.5], "stintLaps": 20}


def check(name: str, condition: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    return condition


def main() -> None:
    results = []
    print("uncalibrated reading")

    uncal = advise(UNCALIBRATED, ROUTINE, SUSTAINED)
    titles = [f["title"] for f in uncal["flags"]]

    results.append(check(
        "comms are not restricted on a population-prior state",
        uncal["radioWindow"] == "Open", f"window={uncal['radioWindow']}"))
    results.append(check(
        "full word budget, not a fatigue-shortened one",
        uncal["wordBudget"] == 26, f"budget={uncal['wordBudget']}"))
    results.append(check(
        "no fabricated sustained-load warning",
        "Sustained load" not in titles))
    results.append(check(
        "no fabricated fatigue-in-stint warning",
        "Fatigue in a long stint" not in titles))
    results.append(check(
        "does not recommend an earlier stop",
        "earlier stop" not in uncal["action"]["headline"].lower(),
        repr(uncal["action"]["headline"][:52])))
    results.append(check(
        "missing calibration is raised as a warning, not buried as info",
        any(f["level"] == "warning" and "calibrat" in f["title"].lower() for f in uncal["flags"])))

    print("\nsafety and first-hand reports still override")
    critical = advise(UNCALIBRATED, CRITICAL, SUSTAINED)
    results.append(check(
        "safety-critical traffic still goes through",
        critical["radioWindow"] == "Open"))

    limit = advise(UNCALIBRATED, LIMIT, SUSTAINED)
    results.append(check(
        "a stated limit still narrows the window without a baseline",
        limit["radioWindow"] == "Caution", f"window={limit['radioWindow']}"))
    results.append(check(
        "a stated limit is still acted on",
        "report" in limit["action"]["headline"].lower()))

    print("\ncalibrated reading is untouched by the gate")
    cal = advise(CALIBRATED, ROUTINE, SUSTAINED)
    cal_titles = [f["title"] for f in cal["flags"]]
    results.append(check(
        "a real fatigue reading still narrows the window",
        cal["radioWindow"] == "Caution", f"window={cal['radioWindow']}"))
    results.append(check(
        "a real sustained load is still flagged",
        "Sustained load" in cal_titles))
    results.append(check(
        "a real fatigue reading still suggests an earlier stop",
        "earlier stop" in cal["action"]["headline"].lower()))

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
