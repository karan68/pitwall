"""Throwaway probe: which real F1 team-radio datasets actually exist and are usable?

Queries the Hugging Face APIs directly rather than trusting any README. Prints
the real schema, splits and row counts so the loader is written against
observed structure, not assumed structure.
"""
import json

import httpx

CANDIDATES = ["MikCil/f1-team-radio"]


def show(title: str, payload) -> None:
    print(f"\n--- {title}\n{json.dumps(payload, indent=1)[:1400]}")


with httpx.Client(timeout=60, follow_redirects=True) as client:
    print("=== SEARCH: hub datasets matching f1 / formula1 radio ===")
    found = []
    for term in ("f1 team radio", "formula1 radio", "f1 radio", "team radio"):
        r = client.get("https://huggingface.co/api/datasets", params={"search": term, "limit": 20})
        if r.status_code != 200:
            print(f"  [{term}] search failed {r.status_code}")
            continue
        for d in r.json():
            if d["id"] not in [f["id"] for f in found]:
                found.append({"id": d["id"], "downloads": d.get("downloads", 0), "likes": d.get("likes", 0)})
    for d in sorted(found, key=lambda x: -x["downloads"]):
        print(f"  {d['downloads']:>8} dl  {d['likes']:>3} likes  {d['id']}")
        if d["id"] not in CANDIDATES:
            CANDIDATES.append(d["id"])

    print("\n=== DETAIL: does each candidate exist, and what is in it? ===")
    for dataset in CANDIDATES[:8]:
        info = client.get(f"https://huggingface.co/api/datasets/{dataset}")
        print(f"\n### {dataset}  -> hub {info.status_code}")
        if info.status_code != 200:
            print("    does not exist / not accessible")
            continue

        meta = info.json()
        print(f"    gated={meta.get('gated')}  private={meta.get('private')}  "
              f"downloads={meta.get('downloads')}  likes={meta.get('likes')}")
        card = meta.get("cardData") or {}
        print(f"    license={card.get('license')}  task={card.get('task_categories')}")
        print(f"    files={[f['rfilename'] for f in meta.get('siblings', [])][:10]}")

        splits = client.get("https://datasets-server.huggingface.co/splits", params={"dataset": dataset})
        if splits.status_code == 200:
            for s in splits.json().get("splits", []):
                print(f"    split: {s['config']}/{s['split']}")
        else:
            print(f"    splits endpoint -> {splits.status_code} {splits.text[:160]}")

        rows = client.get(
            "https://datasets-server.huggingface.co/first-rows",
            params={"dataset": dataset, "config": "default", "split": "train"},
        )
        if rows.status_code == 200:
            body = rows.json()
            print(f"    COLUMNS: {[f['name'] + ':' + str(f['type'].get('_type')) for f in body['features']]}")
            for row in body["rows"][:2]:
                trimmed = {k: (str(v)[:110]) for k, v in row["row"].items()}
                print(f"    row: {json.dumps(trimmed)[:600]}")
        else:
            print(f"    first-rows -> {rows.status_code} {rows.text[:200]}")
