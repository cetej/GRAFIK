"""Srovnání modelů na návrzích skladby: stejný dossier, stejné zadání, náčrty vedle sebe a skutečná cena z usage.

Operátor 1. 11. 2026: používat i modely ChatGPT, když jsou na něco lepší a levnější. O výchozím modelu `proposals.DEFAULT_MODEL`
rozhoduje operátor podle stránky, kterou skript vyrobí (jeden soubor, náčrty jsou v něm). Placené: bez --confirm-cost jen vypíše
odhad a skončí. Cena jde po řádcích do `library/costs.jsonl` jako u Engine (`pending`, pak `ok` nebo `failed`).

python scripts/navrhy_srovnani.py library/research/koloseum-v1/dossier.json --out library/navrhy/srovnani-koloseum --confirm-cost
"""
from __future__ import annotations

import argparse
import html
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import proposals  # noqa: E402 (engine/__init__.py dává na sys.path i shared/)
from engine.config import Settings  # noqa: E402
from ngm_shared import claude  # noqa: E402

MODELS = ["claude-sonnet-5-5", "claude-haiku-5-5", "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna"]
STYLE = """body{font:14px Bahnschrift,Segoe UI,sans-serif;margin:24px;background:#f5f6f8;color:#1d1f23}
section{background:#fff;border:1px solid #d5d7dc;border-radius:8px;padding:12px;margin-bottom:16px}
.row{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start}.card{width:320px}.card.big{width:100%}
.card svg{display:block;width:100%;height:auto;border:1px solid #d5d7dc;cursor:zoom-in}.card.big svg{cursor:zoom-out}
h2{margin:0 0 4px}h3{margin:8px 0 2px}p{margin:2px 0}.warn{color:#b3261e}.hint{color:#5c6270;font-size:12px}
ol{padding-left:18px;margin:4px 0}li{margin-bottom:6px}ul{padding-left:14px;margin:2px 0;font-size:12px;color:#444a55}"""


def panel_html(panel: dict, facts: dict) -> str:
    cited = "".join(f"<li>{html.escape(facts[f]['tvrzeni'][:160])} <span class='hint'>({facts[f]['stav']})</span></li>" for f in panel["fakta"])
    return f"<li><b>{html.escape(panel['titulek'])}</b> {html.escape(panel['co'])}" + (f"<ul>{cited}</ul>" if cited else " <span class='warn'>bez faktu</span>") + "</li>"


def page(dossier: dict, rows: list[dict]) -> str:
    facts = {f["id"]: f for f in dossier["facts"]}
    parts = [f"<!doctype html><meta charset='utf-8'><title>Návrhy: {html.escape(dossier['tema'])}</title><style>{STYLE}</style>",
             f"<h1>Návrhy skladby: {html.escape(dossier['tema'])}</h1><p class='hint'>Stejný dossier, stejné zadání. Klik na náčrt ho zvětší.</p>"]
    for row in rows:
        parts.append(f"<section><h2>{html.escape(row['model'])}</h2>")
        if row.get("chyba"):
            parts.append(f"<p class='warn'>{html.escape(row['chyba'])}</p></section>")
            continue
        parts.append(f"<p>{row['usd']} USD · vstup {row['in']} tokenů, výstup {row['out']} tokenů · {row['s']} s</p><div class='row'>")
        for p in row["navrhy"]:
            sketch = proposals.sketch(p)
            parts.append(f"<div class='card' onclick=\"this.classList.toggle('big')\">{sketch}<h3>{html.escape(p['nazev'])}</h3><p>{html.escape(p['veta'])}</p>"
                         f"<p class='hint'>Formát {p['format']}, panelů {len(p['panely'])}, faktů {p['fakta']}, neexistujících odkazů {p['neznama_fakta']}, rozporných {len(p['rozpory'])}</p>"
                         f"<details onclick='event.stopPropagation()'><summary>Panely a fakta</summary><ol>{''.join(panel_html(x, facts) for x in p['panely'])}</ol></details></div>")
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
    ledger = Settings().costs_path
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    def log_cost(row: dict) -> None:
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), **row}, ensure_ascii=False) + "\n")

    rows = []
    for model in args.models:
        t0 = time.time()
        what = f"srovnání: návrhy skladby ({model})"
        base = {"job_id": f"srovnani-{stamp}-{model}", "caller": "scripts:navrhy_srovnani", "backend": f"{proposals.vendor(model)}:navrhy", "n": 1}
        log_cost({**base, "usd": estimate[model], "status": "pending", "items": [{"what": f"{what}, odhad", "usd": estimate[model]}]})
        try:
            out = proposals.propose(dossier, model=model)
        except claude.ClaudeError as e:
            cost = e.cost or {"usd": 0.0}
            log_cost({**base, "usd": cost["usd"], "status": "failed", "usage": cost, "items": [{"what": what, "usd": cost["usd"]}]})
            rows.append({"model": model, "chyba": str(e), **cost})
            print(model, "chyba:", e, flush=True)
            continue
        cost = out["cost"]
        log_cost({**base, "usd": cost["usd"], "status": "ok", "usage": cost, "items": [{"what": what, "usd": cost["usd"]}]})
        rows.append({"model": model, "usd": cost["usd"], "in": cost["in"], "out": cost["out"], "s": round(time.time() - t0), "navrhy": out["navrhy"]})
        print(model, cost["usd"], "USD", cost["in"], cost["out"], f"{time.time() - t0:.0f} s", [p["nazev"] for p in out["navrhy"]], flush=True)
    (args.out / "srovnani.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.out / "index.html").write_text(page(dossier, rows), encoding="utf-8")
    print("celkem", round(sum(r["usd"] for r in rows), 4), "USD ·", args.out / "index.html")


if __name__ == "__main__":
    main()
