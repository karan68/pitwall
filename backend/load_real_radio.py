"""Pull real Formula 1 team radio from the Hugging Face hub.

Dataset: MikCil/f1-team-radio (CC-BY-4.0, public, not gated)
  columns: id, driver_id, racing_number, grand_prix, race_id, session_date,
           message_timestamp, audio {bytes, path}, transcription

The `transcription` column is human ground truth, which is what lets us measure
our own ASR error rate on real broadcast audio instead of asserting it works.

Clips are written to sample_audio/real/<driver>/ with a manifest holding the
ground-truth text, so nothing downstream has to hit the network again.
"""
import argparse
import io
import json
from collections import Counter
from pathlib import Path

import httpx
import pyarrow.parquet as pq
import soundfile as sf

DATASET = "MikCil/f1-team-radio"
SHARD_URL = f"https://huggingface.co/datasets/{DATASET}/resolve/main/data/train-{{:05d}}-of-00005.parquet"
CACHE = Path(__file__).parent / "data" / "hf_cache"
OUT_ROOT = Path(__file__).parent / "sample_audio" / "real"


def fetch_shard(index: int) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    local = CACHE / f"train-{index:05d}.parquet"
    if local.exists():
        print(f"  shard {index}: cached ({local.stat().st_size / 1e6:.0f} MB)")
        return local

    url = SHARD_URL.format(index)
    print(f"  shard {index}: downloading {url}")
    with httpx.stream("GET", url, follow_redirects=True, timeout=600) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        written = 0
        with local.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
                written += len(chunk)
                if total:
                    print(f"\r    {written / 1e6:6.0f} / {total / 1e6:.0f} MB", end="")
    print(f"\r    {written / 1e6:.0f} MB downloaded")
    return local


def survey(table) -> None:
    drivers = Counter(table.column("driver_id").to_pylist())
    races = Counter(table.column("grand_prix").to_pylist())
    print(f"\n  rows: {table.num_rows}")
    print(f"  drivers: {len(drivers)}   grands prix: {len(races)}")
    print("  most radio traffic:")
    for driver, count in drivers.most_common(8):
        print(f"    {driver:<12} {count:>4} clips")


def export(table, driver_id: str, baseline_count: int, call_count: int) -> dict:
    rows = table.to_pylist()
    clips = [r for r in rows if r["driver_id"] == driver_id]
    clips.sort(key=lambda r: r["message_timestamp"] or "")

    if len(clips) < baseline_count + call_count:
        raise SystemExit(
            f"{driver_id} only has {len(clips)} clips, need {baseline_count + call_count}"
        )

    out_dir = OUT_ROOT / driver_id
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.wav"):
        stale.unlink()

    # Both groups are drawn from one evenly-spaced sample across the session and
    # then interleaved. Taking the baseline from across the race and the calls
    # from the start alone made the two groups differ by 8.5 dB in level, which
    # the scoring then read as the driver rather than the broadcast mix.
    wanted = baseline_count + call_count
    stride = max(1, len(clips) // wanted)
    sample = clips[::stride][:wanted]

    baseline, calls = [], []
    ratio = max(1, round(call_count / max(baseline_count, 1)))
    for index, clip in enumerate(sample):
        if index % (ratio + 1) == 0 and len(baseline) < baseline_count:
            baseline.append(clip)
        elif len(calls) < call_count:
            calls.append(clip)
        elif len(baseline) < baseline_count:
            baseline.append(clip)

    manifest = {"dataset": DATASET, "driverId": driver_id, "clips": []}
    for kind, group in (("baseline", baseline), ("call", calls)):
        for index, clip in enumerate(group, 1):
            audio, rate = sf.read(io.BytesIO(clip["audio"]["bytes"]), dtype="float32", always_2d=False)
            name = f"{kind}_{index:02d}.wav"
            sf.write(out_dir / name, audio, rate)
            manifest["clips"].append(
                {
                    "file": name,
                    "kind": kind,
                    "id": clip["id"],
                    "grandPrix": clip["grand_prix"],
                    "sessionDate": clip["session_date"],
                    "racingNumber": clip["racing_number"],
                    "groundTruth": clip["transcription"],
                    "durationSeconds": round(len(audio) / rate, 2),
                    "sampleRate": rate,
                }
            )

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver", default=None, help="driver_id, e.g. VERMAX01")
    parser.add_argument("--baseline", type=int, default=6)
    parser.add_argument("--calls", type=int, default=10)
    parser.add_argument("--shard", type=int, default=0)
    args = parser.parse_args()

    print(f"Dataset: {DATASET} (CC-BY-4.0)")
    table = pq.read_table(fetch_shard(args.shard))
    survey(table)

    driver = args.driver
    if not driver:
        counts = Counter(table.column("driver_id").to_pylist())
        driver = counts.most_common(1)[0][0]
        print(f"\n  no --driver given, using the busiest: {driver}")

    manifest = export(table, driver, args.baseline, args.calls)
    total = manifest["clips"]
    seconds = sum(c["durationSeconds"] for c in total)
    print(f"\n  wrote {len(total)} clips ({seconds:.0f}s) to {OUT_ROOT / driver}")
    print(f"  {sum(1 for c in total if c['kind'] == 'baseline')} baseline, "
          f"{sum(1 for c in total if c['kind'] == 'call')} calls")
    print("\n  sample ground truth:")
    for clip in [c for c in total if c["kind"] == "call"][:5]:
        print(f"    {clip['file']}  {clip['durationSeconds']:>5.1f}s  \"{clip['groundTruth']}\"")


if __name__ == "__main__":
    main()
