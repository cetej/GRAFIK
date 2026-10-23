"""Keypoint check of the local generator on PromptEnhancer/T2I-Keypoints-Eval (cetej/GRAFIK#9, point A).

Each English prompt in the dataset comes with 3-5 keypoints (category + the phrase that must be
visible). The script samples N of them, generates one image per prompt through the Engine (local FLUX,
free), and asks a Claude vision model about every keypoint: judge only what is visible, infer nothing,
reason first and end with accept or reject. The verdict is the LAST accept/reject in the answer.

Output: share of images with all keypoints accepted, accuracy per category, written to
docs/spikes/<date>-keypoints-<label>.md (+ .json). Images stay in library/eval/<label>/.

The judge is paid. Without --confirm-cost the script prints the estimate and stops.
With 20-30 prompts the error bar is about +-10 pp: do not read smaller differences between runs.

    python scripts/eval_keypoints.py --n 24                     # estimate only
    python scripts/eval_keypoints.py --n 24 --confirm-cost      # run
    python scripts/eval_keypoints.py --n 24 --expand --label expand --confirm-cost
"""
from __future__ import annotations

import argparse
import base64
import json
import random
import re
import sys
from collections import defaultdict
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "clients"))

import grafik_client  # noqa: E402
from engine.backends import claude_text, expand_prompt  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATASET = ("https://huggingface.co/datasets/PromptEnhancer/T2I-Keypoints-Eval/resolve/"
           "refs%2Fconvert%2Fparquet/default/train/0000.parquet")  # apache-2.0
CACHE = ROOT / "library" / "eval" / "t2i-keypoints-eval.parquet"
JUDGE_EDGE = 768  # px sent to the judge, ~800 image tokens
# USD per million tokens (input, output), claude-api skill table cached 2026-10-06
PRICES = {"claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50), "claude-opus-5-5": (4.0, 20.0)}
JUDGE_TOKENS = (1100, 900)  # per call: image + instruction in; reasoning (with thinking) + verdict out
EXPAND_TOKENS = (400, 300)

JUDGE_INSTRUCTION = (
    "You check whether a generated image shows one required element. Look only at what is visible in the "
    "image; do not assume anything that cannot be seen, and do not give credit for something that is only "
    "suggested by the rest of the scene. First explain briefly what you see that is relevant. Then finish "
    "with exactly one word on the last line: accept if the element is clearly present as described, "
    "reject otherwise.\n\nImage prompt (context): {prompt}\nCategory: {category}\nRequired element: {point}"
)
VERDICT = re.compile(r"\b(accept|reject)\b", re.IGNORECASE)


def load_rows():
    import pandas as pd
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        r = httpx.get(DATASET, follow_redirects=True, timeout=120)
        r.raise_for_status()
        CACHE.write_bytes(r.content)
    df = pd.read_parquet(CACHE)
    return [{"ind": int(r.ind), "prompt": r.prompt, "points": list(zip(r.prompt_points, r.prompt_points_des))}
            for r in df[df.language == "en"].itertuples()]


def verdict(answer: str) -> str | None:
    found = VERDICT.findall(answer)
    return found[-1].lower() if found else None


def judge(png: Path, prompt: str, category: str, point: str, model: str) -> tuple[str | None, str]:
    img = Image.open(png).convert("RGB")
    img.thumbnail((JUDGE_EDGE, JUDGE_EDGE))
    buf = BytesIO()
    img.save(buf, "PNG")
    answer = claude_text([
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": base64.b64encode(buf.getvalue()).decode()}},
        {"type": "text", "text": JUDGE_INSTRUCTION.format(prompt=prompt, category=category, point=point)}],
        4000, "hodnocení klíčového bodu", model=model)
    return verdict(answer), answer


def estimate(sample, model: str, expand: bool) -> float:
    pin, pout = PRICES[model]
    calls = sum(len(s["points"]) for s in sample)
    usd = calls * (JUDGE_TOKENS[0] * pin + JUDGE_TOKENS[1] * pout) / 1e6
    if expand:  # expand_prompt runs on the Engine's Haiku
        hin, hout = PRICES["claude-haiku-5-5"]
        usd += len(sample) * (EXPAND_TOKENS[0] * hin + EXPAND_TOKENS[1] * hout) / 1e6
    return usd


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=24)
    ap.add_argument("--seed", type=int, default=7, help="sampling seed (same seed = same prompts)")
    ap.add_argument("--image-seed", type=int, default=1)
    ap.add_argument("--size", default="1024x1024")
    ap.add_argument("--judge-model", default="claude-sonnet-5-5", choices=sorted(PRICES))
    ap.add_argument("--expand", action="store_true", help="rewrite each prompt with 'Rozepsat zadání' first")
    ap.add_argument("--label", default="raw")
    ap.add_argument("--confirm-cost", action="store_true")
    a = ap.parse_args(argv)

    rows = load_rows()
    sample = random.Random(a.seed).sample(rows, a.n)
    usd = estimate(sample, a.judge_model, a.expand)
    calls = sum(len(s["points"]) for s in sample)
    print(f"{a.n} promptů, {calls} klíčových bodů, soudce {a.judge_model}"
          f"{', rozepsání Haiku' if a.expand else ''}: odhad {usd:.2f} USD (generování lokálně 0 USD).")
    if not a.confirm_cost:
        print("Nic nespuštěno. Po schválení ceny spusťte znovu s --confirm-cost.")
        return 0

    out_dir = ROOT / "library" / "eval" / a.label
    results = []
    for i, s in enumerate(sample, 1):
        prompt = expand_prompt(s["prompt"]) if a.expand else s["prompt"]
        png = grafik_client.generate(prompt, out_dir=out_dir, size=a.size, seed=a.image_seed,
                                     caller="eval_keypoints", timeout=1800)[0]
        points = []
        for category, point in s["points"]:
            v, answer = judge(png, s["prompt"], category, point, a.judge_model)
            points.append({"category": category, "point": point, "verdict": v, "answer": answer})
        ok = all(p["verdict"] == "accept" for p in points)
        results.append({"ind": s["ind"], "prompt": s["prompt"], "prompt_sent": prompt, "image": str(png),
                        "all_ok": ok, "points": points})
        print(f"[{i}/{a.n}] {'OK ' if ok else '-- '}{sum(p['verdict'] == 'accept' for p in points)}/{len(points)}"
              f"  {s['prompt'][:70]}")

    per_cat = defaultdict(lambda: [0, 0])
    for r in results:
        for p in r["points"]:
            per_cat[p["category"]][0] += p["verdict"] == "accept"
            per_cat[p["category"]][1] += 1
    all_ok = sum(r["all_ok"] for r in results)
    undecided = sum(p["verdict"] is None for r in results for p in r["points"])

    stem = ROOT / "docs" / "spikes" / f"{date.today()}-keypoints-{a.label}"
    stem.with_suffix(".json").write_text(json.dumps(
        {"label": a.label, "n": a.n, "seed": a.seed, "image_seed": a.image_seed, "size": a.size,
         "judge_model": a.judge_model, "expand": a.expand, "estimate_usd": round(usd, 4), "results": results},
        ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [f"# Klíčové body T2I-Keypoints-Eval — {a.label} ({date.today()})", "",
             f"Lokální FLUX {a.size}, seed obrázku {a.image_seed}, vzorek {a.n} anglických promptů (seed {a.seed}), "
             f"soudce {a.judge_model}{', zadání rozepsané přes „Rozepsat zadání“' if a.expand else ''}. "
             f"Odhad útraty {usd:.2f} USD. Dataset PromptEnhancer/T2I-Keypoints-Eval (apache-2.0).", "",
             f"**Obrázky se všemi body: {all_ok}/{a.n} ({100 * all_ok / a.n:.0f} %).** "
             f"Při {a.n} promptech je nejistota kolem ±10 p. b.; menší rozdíly mezi běhy nečíst."
             + (f" Bez verdiktu: {undecided} bodů (počítáno jako zamítnuto)." if undecided else ""), "",
             "| Kategorie | Přijato | Úspěšnost |", "|---|---|---|"]
    for cat, (acc, tot) in sorted(per_cat.items(), key=lambda kv: kv[1][0] / kv[1][1]):
        lines.append(f"| {cat} | {acc}/{tot} | {100 * acc / tot:.0f} % |")
    lines += ["", f"Podrobnosti po bodech: `{stem.name}.json`."]
    stem.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with open(ROOT / "library" / "costs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), "job_id": None,
                            "caller": "eval_keypoints", "backend": f"claude:{a.judge_model}", "n": calls,
                            "usd": round(usd, 4), "items": [{"what": f"hodnocení klíčových bodů ({a.label}), odhad",
                                                             "usd": round(usd, 4)}]}, ensure_ascii=False) + "\n")
    print(f"Hotovo: {all_ok}/{a.n} obrázků se všemi body → {stem.with_suffix('.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
