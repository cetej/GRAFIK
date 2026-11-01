"""Srovnání modelů na návrzích skladby: stejný dossier, stejné zadání, náčrty vedle sebe a skutečná cena z usage.

Operátor 1. 11. 2026: používat i modely ChatGPT, když jsou na něco lepší a levnější. O výchozím modelu `proposals.DEFAULT_MODEL`
rozhoduje operátor podle stránky, kterou skript vyrobí. Placené: bez --confirm-cost jen vypíše odhad a skončí.

python scripts/navrhy_srovnani.py library/research/koloseum-v1/dossier.json --out library/navrhy/srovnani-koloseum --confirm-cost
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import proposals  # noqa: E402 (engine/__init__.py dává na sys.path i shared/)
from ngm_shared import claude  # noqa: E402

MODELS = ["claude-sonnet-5-5", "claude-haiku-5-5", "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna"]


def page(dossier: dict, rows: list[dict]) -> str:
    parts = [f"<!doctype html><meta charset='utf-8'><title>Návrhy: {html.escape(dossier['tema'])}</title>",
             "<style>body{font:14px Bahnschrift,Segoe UI,sans-serif;margin:24px;background:#f5f6f8}section{background:#fff;border:1px solid #d5d7dc;border-radius:8px;padding:12px;margin-bottom:16px}"
             ".row{display:flex;gap:12px;flex-wrap:wrap}.card{width:300px}.card img{width:100%;max-height:360px;object-fit:contain;border:1px solid #d5d7dc}h3{margin:6px 0 2px}p{margin:2px 0}.warn{color:#b3261e}</style>",
             f"<h1>Návrhy skladby: {html.escape(dossier['tema'])}</h1>"]
    for row in rows:
        parts.append(f"<section><h2>{html.escape(row['model'])}</h2>")
        if row.get("chyba"):
            parts.append(f"<p class='warn'>{html.escape(row['chyba'])}</p></section>")
            continue
        parts.append(f"<p>{row['usd']} USD · vstup {row['in']} tokenů, výstup {row['out']} tokenů · {row['s']} s</p><div class='row'>")
        for p in row["navrhy"]:
            parts.append(f"<div class='card'><img src='{row['slug']}-{p['id']}.svg'><h3>{html.escape(p['nazev'])}</h3><p>{html.escape(p['veta'])}</p>"
                         f"<p>Formát {p['format']}, panelů {len(p['panely'])}, faktů {p['fakta']}, neexistujících odkazů {p['neznama_fakta']}, rozporných {len(p['rozpory'])}</p></div>")
        parts.append("</div></section>")
    return "".join(parts)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dossier", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--models", nargs="+", default=MODELS)
    parser.add_argument("--confirm-cost", action="store_true")
    args = parser.parse_args()
    dossier = json.loads(args.dossier.read_text(encoding="utf-8"))
    estimate = {m: proposals.estimate_usd(m) for m in args.models}
    print("odhad:", estimate, "celkem", round(sum(estimate.values()), 4), "USD")
    if not args.confirm_cost:
        print("Placené. Spusťte s --confirm-cost.")
        return
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for model in args.models:
        t0 = time.time()
        slug = model.replace(".", "_")
        try:
            out = proposals.propose(dossier, model=model)
        except claude.ClaudeError as e:
            rows.append({"model": model, "chyba": str(e), **(e.cost or {"usd": 0.0})})
            print(model, "chyba:", e)
            continue
        for p in out["navrhy"]:
            (args.out / f"{slug}-{p['id']}.svg").write_text(proposals.sketch(p), encoding="utf-8")
        cost = out["cost"]
        rows.append({"model": model, "slug": slug, "usd": cost["usd"], "in": cost["in"], "out": cost["out"], "s": round(time.time() - t0), "navrhy": out["navrhy"]})
        print(model, cost["usd"], "USD", cost["in"], cost["out"], f"{time.time() - t0:.0f} s", [p["nazev"] for p in out["navrhy"]])
    (args.out / "srovnani.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "index.html").write_text(page(dossier, rows), encoding="utf-8")
    print("celkem", round(sum(r["usd"] for r in rows), 4), "USD ·", args.out / "index.html")


if __name__ == "__main__":
    main()
