"""Does the voice reading predict anything real, measured across many races?

Every weight and threshold in state.py was chosen by reasoning. That is the
fairest criticism of this project, and it is answerable, because there is an
objective label the driver never talks about: what their lap time does next.

For each radio clip this pairs the voice measured at the moment of the call with
the lap that followed it, expressed as a change against that driver's own clean
pace in that race. Then it asks three questions in order:

  1. Does the hand-weighted load correlate with the next lap at all?
  2. Can a model *learn* better weights than the ones chosen by hand, scored on
     races it never saw? Held out by session, so a race is never in both halves.
  3. Is any of it real? The same fit is repeated against shuffled labels a few
     hundred times to get a null distribution. A model that beats hand-chosen
     weights but sits inside the null has learned nothing.

Nothing here is circular: the features come from audio, the label comes from
timing hardware, and the two never touch until this script pairs them.

    .venv\\Scripts\\python.exe validate_at_scale.py --races 6 --per-race 90
"""
import argparse
import io
import json
import urllib.request
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from services.features import extract, signal_quality
from services.state import AROUSAL_FEATURES, POPULATION_PRIORS, STRAIN_FEATURES, Z_CLAMP

OPENF1 = "https://api.openf1.org/v1"
ROWS = Path(__file__).parent / "data" / "validation_rows.json"
SR = 16000

# A lap this far off a driver's own median is a pit stop, a safety car or a red
# flag, not a lap their voice could have predicted.
RACING_LAP_TOLERANCE = 1.3
# Matches MIN_BASELINE_SAMPLES in state.py: the same rule the live system uses to
# decide it knows a driver's normal voice.
MIN_CLIPS_PER_DRIVER = 3
# A clip missing more than this many measurements is dropped rather than imputed.
MAX_MISSING_FEATURES = 2


def openf1(path: str, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
    request = urllib.request.Request(f"{OPENF1}/{path}?{query}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode())


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def audio_for(url: str) -> np.ndarray | None:
    from transformers.pipelines.audio_utils import ffmpeg_read

    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return ffmpeg_read(response.read(), SR)
    except Exception:
        return None


def next_lap_delta(message_time: datetime, laps: list[dict]) -> float | None:
    """Lap time after this call, relative to the driver's own clean pace."""
    timed = [lap for lap in laps if lap.get("lap_duration") and lap.get("date_start")]
    if len(timed) < 8:
        return None

    median = float(np.median([lap["lap_duration"] for lap in timed]))
    clean = [lap for lap in timed if lap["lap_duration"] <= median * RACING_LAP_TOLERANCE]
    if len(clean) < 8:
        return None
    reference = float(np.median([lap["lap_duration"] for lap in clean]))

    after = [lap for lap in clean if parse_time(lap["date_start"]) > message_time]
    if not after:
        return None
    following = min(after, key=lambda lap: parse_time(lap["date_start"]))
    return (following["lap_duration"] - reference) / reference


def gather(races: int, per_race: int) -> list[dict]:
    sessions = openf1("sessions", year=2024, session_name="Race")[:races]
    rows = []

    for session in sessions:
        key = session["session_key"]
        name = session["country_name"]
        try:
            radio = openf1("team_radio", session_key=key)
            laps = openf1("laps", session_key=key)
        except Exception as error:
            print(f"  {name}: skipped ({type(error).__name__})")
            continue

        by_driver: dict[int, list] = {}
        for lap in laps:
            by_driver.setdefault(lap["driver_number"], []).append(lap)

        # Spread the budget over drivers so one talkative driver cannot dominate.
        messages: dict[int, list] = {}
        for message in sorted(radio, key=lambda m: m["date"]):
            messages.setdefault(message["driver_number"], []).append(message)

        chosen, index = [], 0
        while len(chosen) < per_race and any(index < len(v) for v in messages.values()):
            for number, items in messages.items():
                if index < len(items) and len(chosen) < per_race:
                    chosen.append(items[index])
            index += 1

        kept = 0
        for message in chosen:
            number = message["driver_number"]
            delta = next_lap_delta(parse_time(message["date"]), by_driver.get(number, []))
            if delta is None:
                continue

            audio = audio_for(message["recording_url"])
            if audio is None or len(audio) < SR:
                continue
            if not signal_quality(audio, SR)["usable"]:
                continue

            features = extract(audio, SR)
            if not features.get("f0MeanHz"):
                continue

            rows.append({
                "session": key,
                "race": name,
                "driver": number,
                "delta": delta,
                **{f: features.get(f) for f in POPULATION_PRIORS},
            })
            kept += 1

        print(f"  {name:<16} {kept:>4} usable clips  (running total {len(rows)})")

    return rows


def z_by_driver(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[str]]:
    """Robust z-scores within each driver-race, exactly as the live baseline does."""
    names = list(POPULATION_PRIORS)
    groups: dict[tuple, list[int]] = {}
    for index, row in enumerate(rows):
        groups.setdefault((row["session"], row["driver"]), []).append(index)

    matrix = np.full((len(rows), len(names)), np.nan)
    for indices in groups.values():
        if len(indices) < MIN_CLIPS_PER_DRIVER:
            continue
        for column, feature in enumerate(names):
            # An explicit None check: pauseRatio and several others are legitimately
            # 0.0, and treating that as missing silently emptied the whole set.
            raw = [rows[i].get(feature) for i in indices]
            values = np.array([np.nan if v is None else float(v) for v in raw])
            if np.isnan(values).all():
                continue
            centre = np.nanmedian(values)
            spread = np.nanmedian(np.abs(values - centre)) / 0.6745
            spread = max(spread, POPULATION_PRIORS[feature][1] * 0.5)
            matrix[indices, column] = np.clip((values - centre) / spread, -Z_CLAMP, Z_CLAMP)

    grouped = np.array([len(groups[(r["session"], r["driver"])]) >= MIN_CLIPS_PER_DRIVER for r in rows])
    missing = np.isnan(matrix).sum(axis=1)
    keep = grouped & (missing <= MAX_MISSING_FEATURES)

    print(f"  dropped: {int((~grouped).sum())} in driver-races under {MIN_CLIPS_PER_DRIVER} clips, "
          f"{int((grouped & (missing > MAX_MISSING_FEATURES)).sum())} missing too many measurements")

    matrix = np.nan_to_num(matrix[keep], nan=0.0)  # a missing measurement sits at baseline
    target = np.array([r["delta"] for r in rows])[keep]
    session = np.array([r["session"] for r in rows])[keep]
    return matrix, target, session, names


def hand_weighted(matrix: np.ndarray, names: list[str]) -> np.ndarray:
    """The shipped formula, so it is scored on exactly the same rows."""
    def axis(weights):
        total = sum(abs(w) for w in weights.values())
        return sum(matrix[:, names.index(f)] * w for f, w in weights.items()) / total

    return 50 + 16 * (0.45 * axis(AROUSAL_FEATURES) + 0.55 * axis(STRAIN_FEATURES))


def ridge(x: np.ndarray, y: np.ndarray, penalty: float) -> np.ndarray:
    x = np.column_stack([x, np.ones(len(x))])
    identity = np.eye(x.shape[1])
    identity[-1, -1] = 0.0
    return np.linalg.solve(x.T @ x + penalty * identity, x.T @ y)


def leave_one_session_out(matrix: np.ndarray, target: np.ndarray, session: np.ndarray,
                          penalty: float = 10.0) -> float:
    """R^2 on races the model never saw. Negative means worse than the mean."""
    predictions = np.zeros_like(target)
    for held in np.unique(session):
        train, test = session != held, session == held
        if train.sum() < 20 or not test.any():
            predictions[test] = target[train].mean() if train.any() else 0.0
            continue
        weights = ridge(matrix[train], target[train] - target[train].mean(), penalty)
        predictions[test] = np.column_stack([matrix[test], np.ones(test.sum())]) @ weights
        predictions[test] += target[train].mean()

    residual = float(np.sum((target - predictions) ** 2))
    total = float(np.sum((target - target.mean()) ** 2))
    return 1 - residual / total if total else 0.0


def correlation(a: np.ndarray, b: np.ndarray) -> float:
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    rank = lambda v: np.argsort(np.argsort(v)).astype(float)
    return correlation(rank(a), rank(b))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--races", type=int, default=6)
    parser.add_argument("--per-race", type=int, default=90)
    parser.add_argument("--permutations", type=int, default=300)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    if ROWS.exists() and not args.refresh:
        rows = json.loads(ROWS.read_text())
        print(f"{len(rows)} clips loaded from cache ({ROWS.name}); --refresh to re-collect\n")
    else:
        print("collecting real radio and timing\n")
        rows = gather(args.races, args.per_race)
        ROWS.parent.mkdir(parents=True, exist_ok=True)
        ROWS.write_text(json.dumps(rows))
        print(f"\n{len(rows)} clips collected\n")

    if len(rows) < 60:
        raise SystemExit("too few clips to say anything; raise --races or --per-race")

    matrix, target, session, names = z_by_driver(rows)
    print(f"{'=' * 70}\nDATA\n{'=' * 70}")
    print(f"  clips scored           {len(target)}")
    print(f"  races                  {len(np.unique(session))}")
    print(f"  drivers                {len({(r['session'], r['driver']) for r in rows})} driver-races")

    # A verdict from an empty set is worse than no verdict: the first run of this
    # script scored 0 clips and printed a confident "no signal".
    if len(target) < 50 or len(np.unique(session)) < 3:
        raise SystemExit(
            f"\n  Only {len(target)} clips across {len(np.unique(session))} races survived. "
            "That is not enough to conclude anything either way - collect more before reading "
            "any result as a null."
        )

    print(f"  next-lap delta         median {np.median(target):+.3f}  sd {np.std(target):.3f}")

    load = hand_weighted(matrix, names)
    print(f"\n{'=' * 70}\n1. DOES THE SHIPPED FORMULA PREDICT THE NEXT LAP?\n{'=' * 70}")
    print(f"  load vs next-lap delta   pearson {correlation(load, target):+.3f}  "
          f"spearman {spearman(load, target):+.3f}")
    for label, weights in (("arousal", AROUSAL_FEATURES), ("strain", STRAIN_FEATURES)):
        total = sum(abs(w) for w in weights.values())
        axis = sum(matrix[:, names.index(f)] * w for f, w in weights.items()) / total
        print(f"  {label:<8} vs next lap      pearson {correlation(axis, target):+.3f}")

    print(f"\n{'=' * 70}\n2. CAN THE WEIGHTS BE LEARNED INSTEAD?\n{'=' * 70}")
    observed = leave_one_session_out(matrix, target, session)
    print(f"  held-out R^2 (races unseen)   {observed:+.4f}")
    print("  predicting the mean            0.0000  (by definition)")

    print(f"\n{'=' * 70}\n3. IS IT REAL? SHUFFLED-LABEL NULL\n{'=' * 70}")
    rng = np.random.default_rng(0)
    null = []
    for _ in range(args.permutations):
        shuffled = target.copy()
        for held in np.unique(session):
            mask = session == held
            shuffled[mask] = rng.permutation(shuffled[mask])
        null.append(leave_one_session_out(matrix, shuffled, session))
    null = np.array(null)
    p_value = float(np.mean(null >= observed))
    print(f"  null R^2 over {args.permutations} shuffles   mean {null.mean():+.4f}  "
          f"95th pct {np.percentile(null, 95):+.4f}")
    print(f"  observed                      {observed:+.4f}")
    print(f"  p                             {p_value:.3f}")

    print(f"\n{'=' * 70}\nVERDICT\n{'=' * 70}")
    if p_value < 0.05 and observed > 0:
        print("  The voice carries real, held-out signal about the next lap.")
        print("  Learned weights beat the shuffled null on races the model never saw.")
        best = ridge(matrix, target - target.mean(), 10.0)[:-1]
        order = np.argsort(-np.abs(best))
        print("\n  strongest learned features:")
        for i in order[:5]:
            print(f"    {names[i]:<18} {best[i]:+.4f}")
    else:
        print("  No held-out signal. On this data the voice does NOT predict the next")
        print("  lap better than chance, and learning the weights does not rescue the")
        print("  hand-chosen ones.")
        print()
        print("  What this rules out: any claim that the state score forecasts lap time.")
        print("  What it does not rule out: that the score tracks driver state. Lap time")
        print("  is a poor proxy for it - fuel load, tyre age, traffic and safety cars")
        print("  all move it far more than a driver's condition does - and most clips")
        print("  carry the engineer's voice as well as the driver's, which is the")
        print("  confound diarize.py measured and failed to remove.")


if __name__ == "__main__":
    main()
