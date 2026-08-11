"""Throwaway probe: are these two datasets usable, and do either carry LABELS?

Our biggest stated limitation is that the biomarkers are validated against
synthetic signals, not labelled driver-stress data. A labelled F1 audio set
would close that. Verify what is actually in them.
"""
import json

import httpx

TARGETS = ["Tanishqbhatia/f1-team-radio", "renumics/f1_dataset"]


with httpx.Client(timeout=90, follow_redirects=True) as client:
    for dataset in TARGETS:
        print(f"\n{'=' * 78}\n### {dataset}")

        info = client.get(f"https://huggingface.co/api/datasets/{dataset}")
        if info.status_code != 200:
            print(f"  hub -> {info.status_code}: not accessible")
            continue

        meta = info.json()
        card = meta.get("cardData") or {}
        print(f"  downloads={meta.get('downloads')} likes={meta.get('likes')} "
              f"gated={meta.get('gated')} private={meta.get('private')}")
        print(f"  license={card.get('license')} tasks={card.get('task_categories')}")
        print(f"  tags={meta.get('tags', [])[:12]}")
        files = [f["rfilename"] for f in meta.get("siblings", [])]
        print(f"  files({len(files)})={files[:12]}")

        splits = client.get("https://datasets-server.huggingface.co/splits", params={"dataset": dataset})
        configs = []
        if splits.status_code == 200:
            for s in splits.json().get("splits", []):
                configs.append((s["config"], s["split"]))
                print(f"  split: {s['config']}/{s['split']}")
        else:
            print(f"  splits -> {splits.status_code} {splits.text[:200]}")

        for config, split in configs[:2]:
            size = client.get(
                "https://datasets-server.huggingface.co/size",
                params={"dataset": dataset, "config": config},
            )
            if size.status_code == 200:
                s = size.json().get("size", {}).get("config", {})
                print(f"  size[{config}]: {s.get('num_rows')} rows, "
                      f"{(s.get('num_bytes_original_files') or 0) / 1e6:.0f} MB")

            rows = client.get(
                "https://datasets-server.huggingface.co/first-rows",
                params={"dataset": dataset, "config": config, "split": split},
            )
            if rows.status_code != 200:
                print(f"  first-rows -> {rows.status_code} {rows.text[:200]}")
                continue

            body = rows.json()
            print(f"\n  COLUMNS in {config}/{split}:")
            label_like = []
            for feature in body["features"]:
                kind = feature["type"].get("_type")
                extra = ""
                if kind == "ClassLabel":
                    names = feature["type"].get("names", [])
                    extra = f"  <-- LABELS: {names[:12]}"
                    label_like.append(feature["name"])
                print(f"    {feature['name']:<28} {kind}{extra}")
                if any(k in feature["name"].lower() for k in ("label", "emotion", "stress", "class")):
                    label_like.append(feature["name"])

            print(f"\n  sample rows:")
            for row in body["rows"][:2]:
                trimmed = {k: str(v)[:80] for k, v in row["row"].items()}
                print(f"    {json.dumps(trimmed)[:520]}")

            print(f"\n  VERDICT: {'LABELLED -> ' + str(set(label_like)) if label_like else 'no label column found'}")
