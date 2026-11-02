"""Kolik údajů z ruční rešerše našla volná rešerše. Měřítko pro osobu a zvíře, stanovené před změnou kódu (docs/spikes/2026-11-02-resers-osoba-zvire.md).

Seznam vychází z docs/spikes/2026-11-01-plakaty-fakta-tesla.md a -axolotl.md. Údaj je nalezený, když ho jeden fakt dossieru říká
v tvrzení nebo v citaci a má URL zdroje. Údaj jen někde na stažené stránce nestačí, ten počítá `strop` (co vůbec bylo k mání).

    python scripts/research_kontrola.py tesla <dossier.json> [--pages <složka pages>] [--missing]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TESLA = [
    ("narození 10. 7. 1856", r"10\.? (?:July|července|Juli|luglio),? 1856|July 10,? 1856|10\. ?7\. ?1856"),
    ("rodiště Smiljan", r"Smiljan"),
    ("úmrtí 7. 1. 1943", r"7\.? (?:January|ledna|Januar|gennaio),? 1943|January 7,? 1943|7\. ?1\. ?1943"),
    ("hotel New Yorker, pokoj 3327", r"3327|Hotel New Yorker|New Yorker Hotel"),
    ("příjezd do USA červen 1884", r"June 1884|červn\w* 1884"),
    ("občanství USA 1891", r"citizen.{0,80}1891|1891.{0,80}citizen|občan.{0,80}1891|1891.{0,80}občan"),
    ("Edison Machine Works", r"Edison Machine Works"),
    ("patenty střídavého motoru 1. 5. 1888", r"381,?968|May 1,? 1888|1 May 1888|1\. kvě\w* 1888"),
    ("přednáška AIEE 16. 5. 1888", r"AIEE|American Institute of Electrical Engineers"),
    ("Westinghouse: USD 60 000", r"60,000|60 000"),
    ("Westinghouse: USD 2,50 za koňskou sílu", r"\$2\.50|2,50"),
    ("počet patentů: 278 nebo kolem 300", r"\b278\b|(?:around|about|some|nearly|kolem|přes) 300"),
    ("Teslova cívka 1891", r"(?:Tesla coil|cívk|transformátor).{0,160}1891|1891.{0,160}(?:Tesla coil|cívk|transformátor)"),
    ("Niagara, Adamsova elektrárna 1895", r"(?:Niagara|Adams).{0,160}1895|1895.{0,160}(?:Niagara|Adams)"),
    ("proud do Buffala 1896", r"Buffalo.{0,160}1896|1896.{0,160}Buffalo"),
    ("dálkově řízená loď, Madison Square Garden 1898", r"Madison Square Garden"),
    ("Colorado Springs 1899", r"Colorado Springs.{0,160}1899|1899.{0,160}Colorado Springs"),
    ("výboje 135 stop / 41 m", r"135 (?:feet|ft)|\b41 m\b"),
    ("fotka z Colorada je dvojitá expozice", r"double exposure|multiple exposure|dvojit\w+ expozic"),
    ("Wardenclyffe 187 stop / 57 m", r"187 (?:feet|ft)|\b57 m\b"),
    ("Wardenclyffe stržena 1917", r"(?:demolish|dynamit|zbořen|scrap|torn down|tore down).{0,160}1917|1917.{0,160}(?:demolish|dynamit|zbořen|scrap|torn down|tore down)"),
    ("Morgan: USD 150 000 za 51 %", r"150,000|150 000|\b51 ?%|51 percent"),
    ("bezlopatková turbína", r"bladeless|bezlopatk|Tesla turbine.{0,120}patent|turbine was patented"),
    ("mezní vrstva, přilnavost", r"boundary.?layer|adhesion|mezní vrstv"),
    ("rentgen 1894 až 1896", r"X-ray|rentgen|Röntgen|Roentgen"),
    ("bezdrátové svícení, výbojky", r"Geissler|wireless lighting|fluorescent|wireless\w* (?:light|power)\w*"),
    ("rozsudek Marconi 1943", r"Supreme Court.{0,200}1943|1943.{0,200}Supreme Court|Marconi.{0,200}1943"),
    ("jednotka tesla 1960", r"1960.{0,200}(?:unit|jednotk|General Conference)|(?:unit|jednotk|General Conference).{0,200}1960"),
    ("výška přes šest stop", r"6 feet|six feet|6 ft|188 cm|1[.,]88 m|\b6'"),
    ("paprsek smrti (teleforce)", r"death.?(?:beam|ray)|teleforce|paprs\w+ smrti"),
    ("zemětřesení z oscilátoru", r"earthquake|zemětřes"),
    ("vzdal se licenčních poplatků", r"royalt.{0,160}(?:release|clause|gave up|tore|cancel)|(?:release|gave up|tore|cancel).{0,160}royalt"),
    ("výkup patentů USD 216 000", r"216,[06]00"),
    ("USD 125 měsíčně od Westinghouse", r"\$125\b"),
    ("hotelové dluhy", r"(?:unpaid|debt|dluh|owed|owing).{0,160}(?:hotel|Waldorf|St\. Regis)|(?:hotel|Waldorf|St\. Regis).{0,160}(?:unpaid|debt|dluh|owed|owing)"),
]

AXOLOTL = [
    ("délka 15 až 45 cm nebo kolem 23 cm", r"\b45 cm\b|\b23 cm\b|0,15 až 0,45|0,23"),
    ("hmotnost 60 až 110 g", r"\b110 ?g\b|60.{0,8}110 ?(?:g|gram)|0,06 až 0,11"),
    ("délka života v letech", r"(?:life|lifespan|živ|dožív|věk).{0,80}\b\d+ (?:years|let|roků)|\b\d+ (?:years|let|roků).{0,80}(?:life|lifespan|živ|dožív)|\b\d+(?:–| to | and | až )\d+ (?:years|let)"),
    ("tři páry vnějších žaber", r"(?:three|tři|tří|3).{0,24}(?:pairs?|pár).{0,40}gill|(?:three|tři|tří).{0,40}(?:žáb|gill)"),
    ("prsty 4 a 5", r"(?:four|five|čtyři|pět|4|5)\b.{0,24}(?:digits|toes|fingers|prst)"),
    ("oči bez víček", r"lidless|eyelid|víč"),
    ("ploutevní lem", r"caudal fin|tail fin|dorsal fin|ocasní ploutev|ploutevní lem|hřbetní lem"),
    ("plíce", r"\blungs?\b|plíc"),
    ("lov sáním", r"suction|vacuum|sucking|nasáv"),
    ("Xochimilco", r"Xochimilco"),
    ("Chalco", r"Chalco"),
    ("Chapultepec", r"Chapultepec"),
    ("nadmořská výška 2 240 m", r"2,?[  ]?240|2,?[  ]?274|7,?[  ]?[34]\d\d (?:ft|feet)"),
    ("teplota vody", r"\d ?°C"),
    ("IUCN: kriticky ohrožený", r"[Cc]ritically [Ee]ndangered|kriticky ohrožen"),
    ("CITES příloha II", r"CITES|Appendix II"),
    ("rozsah výskytu 467 km²", r"\b467\b"),
    ("50 až 1 000 dospělců", r"50.{0,12}1,?[  ]?000.{0,40}(?:adult|mature|dospěl)|(?:adult|mature|dospěl).{0,40}50.{0,12}1,?[  ]?000"),
    ("hustota 6 000, 1 000, 100, 35 na km²", r"6,?[  ]?000.{0,60}(?:km|kilomet)|(?:per|na) (?:square )?(?:km|kilomet)"),
    ("kapr a tilápie", r"\bcarps?\b|tilapi|kapr|tilápi"),
    ("znečištění, urbanizace", r"pollut|urbani[sz]|wastewater|znečiš|expansion of Mexico City"),
    ("chinampa-refugia", r"chinamp"),
    ("neotenie", r"neoten|paedomorph|pedomorf"),
    ("metamorfóza hormonem", r"thyroid|thyroxin|iodine|\bTSH\b|štítn|jód"),
    ("Duméril 1864", r"Dum[ée]ril"),
    ("34 nebo 33 zvířat, 1863 a 1864", r"\b3[34]\b.{0,40}(?:axolotl|specimen|animals|zvířat)|\b186[34]\b"),
    ("Marie von Chauvin", r"Chauvin"),
    ("Ambystoma Genetic Stock Center", r"Stock Center|University of Kentucky"),
    ("divoký typ", r"wild.?type|divok\w+ (?:forma|typ|zbarv)|natural.{0,3} form"),
    ("leucistická forma", r"leuci[st]"),
    ("albín a tygrovaný mlok", r"albin"),
    ("regenerace končetin", r"regenerat\w*.{0,120}(?:limb|tail)|(?:limb|tail).{0,120}regenerat|regener\w*.{0,120}končet|dorůst\w*.{0,120}končet"),
    ("regenerace srdce, míchy, mozku", r"regener.{0,160}(?:spinal cord|heart|brain|mích|srdc|mozk)|(?:spinal cord|heart|brain|mích|srdc|mozk).{0,160}regener"),
    ("genom 32 Gb", r"\b32\b.{0,6}(?:Gb|billion|miliard|Gigabase)"),
    ("genom 10krát větší než lidský", r"(?:ten|10).{0,16}(?:times|×|krát|-fold).{0,40}(?:human|lidsk)"),
    ("14 párů chromozomů", r"14 (?:chromosome )?pairs|14 párů|2n ?= ?28|\b28 chromosom|14 chromosom"),
    ("bůh Xolotl", r"Xolotl|Xōlōtl"),
    ("význam jména: vodní sluha", r"water[- ](?:slave|servant|dog|monster|sprite|twin)|vodní (?:sluha|netvor|otrok|pes|duch|Xolotl)"),
    ("Diego Rivera", r"\bRivera\b"),
    ("bankovka 50 pesos", r"50.{0,10}peso|peso.{0,40}\b50\b"),
    ("potrava", r"mollus|\bworms?\b|aquatic insects|měkkýš|červ|hmyz"),
    ("predátoři", r"predat|heron|stork|volavk|čáp"),
    ("100 až 300 vajec", r"(?:100|300|hundred).{0,40}(?:eggs|vajíč|vajec)|(?:eggs|vajíč|vajec).{0,40}(?:100|300|hundred)"),
    ("dospívání 18 až 27 měsíců", r"18.{0,6}2[47] (?:months|měsíc)|sexual maturity|pohlavní\w* dosp"),
]

CHECKS = {"tesla": TESLA, "axolotl": AXOLOTL}


def fact_texts(fact: dict) -> list[str]:
    return [fact["tvrzeni"], *[z.get("citace") or "" for z in fact["zdroje"] if z.get("url")]]


def found(checks: list[tuple[str, str]], facts: list[dict]) -> dict[str, dict | None]:
    out: dict[str, dict | None] = {}
    for name, pattern in checks:
        out[name] = next((f for f in facts if any(re.search(pattern, t, re.S | re.I) for t in fact_texts(f))), None)
    return out


def ceiling(checks: list[tuple[str, str]], pages: Path) -> set[str]:
    """Co vůbec stojí na stažených stránkách: stejný vzor po odstavcích, bez ohledu na to, co dossier vybral."""
    paragraphs = [p for f in sorted(pages.glob("*.txt")) for p in f.read_text(encoding="utf-8").splitlines()]
    return {name for name, pattern in checks if any(re.search(pattern, p, re.S | re.I) for p in paragraphs)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("tema", choices=sorted(CHECKS))
    ap.add_argument("dossier", type=Path)
    ap.add_argument("--pages", type=Path)
    ap.add_argument("--missing", action="store_true")
    args = ap.parse_args()
    dossier = json.loads(args.dossier.read_text(encoding="utf-8"))
    checks = CHECKS[args.tema]
    hits = found(checks, dossier["facts"])
    states: dict[str, int] = {}
    for fact in dossier["facts"]:
        states[fact["stav"]] = states.get(fact["stav"], 0) + 1
    roles: dict[str, int] = {}
    for image in dossier["images"]:
        roles[image["role"]] = roles.get(image["role"], 0) + 1
    print(f"{args.dossier.parent.name}: {len(dossier['facts'])} faktů {states}, {len(dossier['images'])} obrázků {roles}")
    print(f"z ruční rešerše: {sum(v is not None for v in hits.values())} z {len(checks)}")
    if args.pages:
        top = ceiling(checks, args.pages)
        print(f"strop (stojí na stažených stránkách): {len(top)} z {len(checks)}")
    if args.missing:
        for name, fact in hits.items():
            if fact is None:
                print(f"  chybí: {name}")


if __name__ == "__main__":
    main()
