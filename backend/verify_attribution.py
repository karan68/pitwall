"""Can the words tell the driver from their engineer, on human transcripts?

Two acoustic attempts failed (speaker.py 0.011 separation; diarize.py 66% against
50% chance). This measures the linguistic route on human ground truth from
MikCil/f1-team-radio, so nothing depends on Whisper being right.

The trap in a test like this is circularity: label the data with a rule, then
score the same rule and call it accurate. So the labels come from a small set of
unambiguous cues, and those exact cues are then STRIPPED from the text before
anything is scored. A classifier that still works is using other language, not
the cue that defined the label.

Three arms, all on the stripped text:

    majority class   what you get for free by always guessing the commoner label
    markers          the deterministic scorer in attribution.py
    zero-shot        distilbart-mnli, no F1 knowledge at all

    .venv\\Scripts\\python.exe verify_attribution.py --limit 400
"""
import argparse
import random
import re
from pathlib import Path

CACHE = Path(__file__).parent / "data" / "hf_cache"

# Labelling cues. Deliberately narrow and unambiguous, and every one of them is
# removed from the text before scoring.
ENGINEER_LABEL_CUES = (
    r"\bbox,? box(?:,? box)?\b",
    r"\bwell done\b",
    r"\bgood job\b",
    r"\bwe need you to\b",
    r"\bhow are the (?:tyres|tires)\b",
    r"\bcan you (?:go|give|do)\b",
)
DRIVER_LABEL_CUES = (
    r"\bi'm (?:struggling|losing|pushing|flat out|okay|fine)\b",
    r"\bi am (?:struggling|losing|pushing|flat out|okay|fine)\b",
    r"\bmy (?:tyres|tires|brakes|neck|drink|seat)\b",
    r"\bno grip\b",
    r"\bthese (?:tyres|tires) are\b",
    r"\bgive me\b",
)


def label_of(text: str) -> str | None:
    engineer = sum(1 for c in ENGINEER_LABEL_CUES if re.search(c, text, re.IGNORECASE))
    driver = sum(1 for c in DRIVER_LABEL_CUES if re.search(c, text, re.IGNORECASE))
    if engineer and not driver:
        return "engineer"
    if driver and not engineer:
        return "driver"
    return None


def strip_cues(text: str) -> str:
    for cue in ENGINEER_LABEL_CUES + DRIVER_LABEL_CUES:
        text = re.sub(cue, " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip(" ,.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=400)
    args = parser.parse_args()

    import pyarrow.parquet as pq

    shard = next(iter(sorted(CACHE.glob("train-*.parquet"))), None)
    if shard is None:
        raise SystemExit(f"no cached shard in {CACHE}; run load_real_radio.py first")

    table = pq.read_table(shard, columns=["transcription"])
    transcripts = [t for t in table.column("transcription").to_pylist() if t and len(t.split()) >= 6]
    print(f"{len(transcripts)} human transcriptions in {shard.name}")

    labelled = []
    for text in transcripts:
        label = label_of(text)
        if label is None:
            continue
        stripped = strip_cues(text)
        if len(stripped.split()) >= 5:  # something must survive to classify
            labelled.append((stripped, label, text))

    random.Random(0).shuffle(labelled)
    labelled = labelled[: args.limit]
    if len(labelled) < 40:
        raise SystemExit(f"only {len(labelled)} labelled examples; too few to measure")

    counts = {l: sum(1 for _, lab, _ in labelled if lab == l) for l in ("engineer", "driver")}
    majority = max(counts.values()) / len(labelled)
    print(f"{len(labelled)} labelled after stripping cues  "
          f"(engineer {counts['engineer']}, driver {counts['driver']})")
    print(f"majority-class baseline: {majority:.0%}\n")

    print("example of what the classifier actually sees:")
    example = labelled[0]
    print(f"  label     {example[1]}")
    print(f"  original  {example[2][:88]!r}")
    print(f"  stripped  {example[0][:88]!r}\n")

    from services.attribution import attribute

    def report(name: str, predictions: list[str]) -> float:
        """Balanced accuracy, because always guessing the commoner class scores 77%."""
        per_class = []
        for target in ("engineer", "driver"):
            actual = [(p, l) for p, (_, l, _) in zip(predictions, labelled) if l == target]
            hit = sum(1 for p, l in actual if p == l)
            per_class.append(hit / len(actual) if actual else 0.0)
            print(f"  {name:<16} {target:<9} {hit:>3}/{len(actual):<4} {per_class[-1]:>5.0%}")
        balanced = sum(per_class) / 2
        overall = sum(1 for p, (_, l, _) in zip(predictions, labelled) if p == l) / len(labelled)
        print(f"  {name:<16} {'overall':<9} {overall:>10.0%}   balanced {balanced:.0%}\n")
        return balanced

    print("per-class results (chance on balanced accuracy is 50%)\n")

    marker_predictions = [attribute(t, use_model=False)["speaker"] for t, _, _ in labelled]
    answered = [p for p in marker_predictions if p in ("engineer", "driver")]
    coverage = len(answered) / len(labelled)
    marker_balanced = report("markers", marker_predictions)

    print("zero-shot  running distilbart-mnli ...", flush=True)
    from services.attribution import _zero_shot

    zero_predictions = [_zero_shot(t)[0] for t, _, _ in labelled]
    zero_balanced = report("zero-shot", zero_predictions)

    combined_predictions = [attribute(t, use_model=True)["speaker"] for t, _, _ in labelled]
    combined_balanced = report("markers + model", combined_predictions)

    print(f"{'=' * 64}\nRESULT\n{'=' * 64}")
    print(f"  majority class      {majority:.0%} overall, 50% balanced")
    print(f"  markers             balanced {marker_balanced:.0%}, answers {coverage:.0%} of clips")
    print(f"  zero-shot           balanced {zero_balanced:.0%}")
    print(f"  markers + model     balanced {combined_balanced:.0%}")

    print()
    if combined_balanced > 0.65:
        print(f"  Balanced accuracy {combined_balanced:.0%} against 50% chance, on text stripped of")
        print("  the cues used to label it. Worth wiring in as a gate on whose voice")
        print("  is being measured.")
    else:
        print(f"  Balanced accuracy {combined_balanced:.0%} is too close to chance to withhold a")
        print("  reading on. Do not wire in; record the negative result.")


if __name__ == "__main__":
    main()
