"""Stránka pro výběr z N variant: obrázky, krátká videa, HTML úryvky nebo text.

Místo iterace „zkus tohle… ne, tamto“ s agentem vygeneruj 20 variant a jednu
lokální HTML stránku, na které operátor variantu zvětší, označí oblíbené,
poskládá parametry z různých variant a výběr zkopíruje zpátky agentovi.

Stránka je jeden soubor bez sítě (funguje z file:// i z dev serveru projektu).
Média odkazuje relativně k umístění stránky, HTML a text vkládá dovnitř.

Použití:
    python -m ngm_shared.variants_page manifest.json -o out/varianty.html
    python -m ngm_shared.variants_page --dir out/hero -o out/hero/varianty.html --title "Hero"
(STOPA scripts/manual/variants_page.py je re-export tohoto modulu, zdroj je tady.)

Manifest (JSON):
    {"title": "Hero pro článek", "note": "volitelný popis",
     "variants": [
        {"id": "v01", "src": "v01.png", "prompt": "...", "params": {"styl": "akvarel"}},
        {"id": "v02", "kind": "video", "src": "v02.mp4"},
        {"id": "v03", "kind": "html", "html": "<h1>Titulek</h1>"},
        {"id": "v04", "kind": "text", "text": "Perex varianta B"}]}

`src` je relativní k manifestu. `kind` se doplní z přípony. V režimu --dir
patří k souboru `x.png` volitelný `x.json` s klíči prompt/params/label.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".svg"}
VIDEO_EXT = {".mp4", ".webm", ".mov", ".m4v"}
HTML_EXT = {".html", ".htm"}
TEXT_EXT = {".txt", ".md"}
KINDS = ("image", "video", "html", "text")


class ManifestError(ValueError):
    pass


def kind_from_path(path: str) -> str | None:
    ext = Path(path).suffix.lower()
    for kind, exts in (("image", IMAGE_EXT), ("video", VIDEO_EXT), ("html", HTML_EXT), ("text", TEXT_EXT)):
        if ext in exts:
            return kind
    return None


def normalize(data: dict, base_dir: Path) -> dict:
    """Ověří manifest a vrátí ho v jednotném tvaru (cesty absolutní, HTML/text vložené)."""
    if not isinstance(data, dict):
        raise ManifestError("Manifest musí být JSON objekt s klíčem „variants“.")
    raw = data.get("variants")
    if not isinstance(raw, list) or not raw:
        raise ManifestError("Manifest nemá žádné varianty (klíč „variants“ je prázdný nebo chybí).")

    variants, seen = [], set()
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ManifestError(f"Varianta č. {i} není objekt.")
        vid = str(item.get("id") or f"v{i:02d}")
        if vid in seen:
            raise ManifestError(f"Id „{vid}“ je v manifestu dvakrát.")
        seen.add(vid)

        src = item.get("src")
        kind = item.get("kind") or (kind_from_path(src) if src else None)
        if kind is None:
            kind = "html" if "html" in item else "text" if "text" in item else None
        if kind not in KINDS:
            raise ManifestError(f"Varianta {vid}: neznámý druh „{kind}“ (povolené: {', '.join(KINDS)}).")

        params = item.get("params") or {}
        if not isinstance(params, dict):
            raise ManifestError(f"Varianta {vid}: „params“ musí být objekt název → hodnota.")

        v = {
            "id": vid,
            "kind": kind,
            "label": str(item.get("label") or ""),
            "prompt": str(item.get("prompt") or ""),
            "params": {str(k): _scalar(val) for k, val in params.items() if val is not None},
        }
        if kind in ("image", "video"):
            if not src:
                raise ManifestError(f"Varianta {vid}: obrázek a video potřebují „src“.")
            path = (base_dir / src).resolve()
            if not path.is_file():
                raise ManifestError(f"Varianta {vid}: soubor {path} neexistuje.")
            v["path"] = path
        else:
            key = "html" if kind == "html" else "text"
            if key in item:
                v["body"] = str(item[key])
            elif src:
                path = (base_dir / src).resolve()
                if not path.is_file():
                    raise ManifestError(f"Varianta {vid}: soubor {path} neexistuje.")
                v["body"] = path.read_text(encoding="utf-8")
            else:
                raise ManifestError(f"Varianta {vid}: chybí „{key}“ nebo „src“.")
        variants.append(v)

    return {"title": str(data.get("title") or "Varianty"), "note": str(data.get("note") or ""), "variants": variants}


def _scalar(val):
    return val if isinstance(val, (str, int, float, bool)) else json.dumps(val, ensure_ascii=False)


def load_manifest(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"Manifest {path} není platný JSON: {exc}") from exc
    return normalize(data, path.parent)


def manifest_from_dir(folder: Path, title: str | None = None) -> dict:
    """Varianty ze všech podporovaných souborů ve složce; `x.json` vedle `x.png` dodá prompt a parametry."""
    files = sorted(p for p in folder.iterdir() if p.is_file() and kind_from_path(p.name))
    stems_with_media = {p.stem for p in files}
    raw = []
    for p in files:
        item = {"id": p.stem, "src": p.name}
        side = p.with_suffix(".json")
        if side.is_file() and side.stem in stems_with_media:
            meta = json.loads(side.read_text(encoding="utf-8"))
            item.update({k: meta[k] for k in ("prompt", "params", "label") if k in meta})
        raw.append(item)
    if not raw:
        raise ManifestError(f"Ve složce {folder} nejsou žádné obrázky, videa, HTML ani texty.")
    return normalize({"title": title or folder.name, "variants": raw}, folder)


def _rel_url(path: Path, out_dir: Path) -> str:
    rel = os.path.relpath(path, out_dir).replace(os.sep, "/")
    return quote(rel, safe="/.-_~")


def render_page(manifest: dict, out_path: Path) -> str:
    out_dir = out_path.resolve().parent
    items = []
    for v in manifest["variants"]:
        item = {k: v[k] for k in ("id", "kind", "label", "prompt", "params")}
        if "path" in v:
            item["url"] = _rel_url(v["path"], out_dir)
        else:
            item["body"] = v["body"]
        items.append(item)
    data = json.dumps({"title": manifest["title"], "note": manifest["note"], "variants": items}, ensure_ascii=False)
    # JSON jde do <script>: „</“ by předčasně ukončilo blok
    data = data.replace("</", "<\\/")
    return (
        TEMPLATE.replace("__TITLE__", html.escape(manifest["title"]))
        .replace("__DATA__", data)
    )


def write_page(manifest: dict, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_page(manifest, out_path), encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Stránka pro výběr z N variant.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("manifest", nargs="?", type=Path, help="manifest JSON")
    src.add_argument("--dir", type=Path, help="složka s variantami (bez manifestu)")
    ap.add_argument("-o", "--out", type=Path, help="výstupní HTML (výchozí: varianty.html vedle vstupu)")
    ap.add_argument("--title", help="nadpis stránky (jen s --dir)")
    args = ap.parse_args(argv)

    try:
        if args.dir:
            manifest = manifest_from_dir(args.dir, args.title)
            default_out = args.dir / "varianty.html"
        else:
            manifest = load_manifest(args.manifest)
            default_out = args.manifest.with_name("varianty.html")
    except ManifestError as exc:
        print(f"Chyba: {exc}", file=sys.stderr)
        return 2
    out = write_page(manifest, args.out or default_out)
    print(f"{len(manifest['variants'])} variant → {out.resolve()}")
    return 0


TEMPLATE = r"""<!doctype html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --bg: #16181C; --card: #1F2228; --card-2: #272B32; --line: #343943; --line-strong: #4A505C;
  --text: #E8EAED; --muted: #A3A9B4; --faint: #7A808C;
  --accent: #3FB8AF; --accent-ink: #0D2B29; --accent-soft: #173A38;
  --font: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", Consolas, monospace;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 var(--font); padding-bottom: 220px; }
header { padding: 20px 24px 8px; display: flex; flex-wrap: wrap; gap: 12px 24px; align-items: baseline; justify-content: space-between; }
h1 { font-size: 20px; font-weight: 600; margin: 0; }
.count { color: var(--muted); font-size: 14px; margin-left: 8px; font-weight: 400; }
.note { color: var(--muted); margin: 4px 0 0; max-width: 70ch; }
.hint { color: var(--faint); font-size: 13px; }
button { font: inherit; font-size: 14px; color: var(--text); background: var(--card-2); border: 1px solid var(--line-strong);
  border-radius: 6px; padding: 6px 12px; cursor: pointer; }
button:hover { border-color: var(--accent); }
button:focus-visible, .thumb:focus-visible, .chip:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
button.on { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); font-weight: 600; }
button.primary { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); font-weight: 600; }
.seg { display: inline-flex; gap: 6px; align-items: center; }
.seg-label { color: var(--muted); font-size: 13px; }
main { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; padding: 12px 24px 24px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; display: flex; flex-direction: column; }
.card.fav { border: 2px solid var(--accent); }
.thumb { display: block; width: 100%; aspect-ratio: 4 / 3; background: #0E0F12; border: 0; padding: 0; cursor: zoom-in; position: relative; overflow: hidden; }
.thumb img, .thumb video { width: 100%; height: 100%; object-fit: contain; display: block; }
.thumb iframe { width: 200%; height: 200%; transform: scale(.5); transform-origin: 0 0; border: 0; pointer-events: none; background: #fff; }
.thumb .txt { text-align: left; padding: 12px 14px; color: var(--text); font-size: 14px; white-space: pre-wrap; height: 100%; overflow: hidden;
  -webkit-mask-image: linear-gradient(#000 75%, transparent); mask-image: linear-gradient(#000 75%, transparent); }
.kind { position: absolute; top: 8px; left: 8px; font-size: 11px; color: var(--muted); background: rgba(14,15,18,.8); padding: 1px 6px; border-radius: 4px; }
.body { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 8px; flex: 1; }
.idline { display: flex; align-items: center; gap: 8px; }
.vid { font-family: var(--mono); font-weight: 600; }
.badge { font-size: 12px; background: var(--accent-soft); color: var(--accent); padding: 1px 7px; border-radius: 4px; }
.label { color: var(--muted); font-size: 13px; }
dl { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 3px 10px; font-size: 13px; }
dt { color: var(--faint); }
dd { margin: 0; }
.chip { all: unset; cursor: pointer; color: var(--text); border-bottom: 1px dashed var(--line-strong); }
.chip:hover { color: var(--accent); border-color: var(--accent); }
.chip.taken { color: var(--accent); border-bottom: 1px solid var(--accent); }
details { font-size: 13px; color: var(--muted); }
details summary { cursor: pointer; color: var(--faint); }
details p { margin: 6px 0 0; white-space: pre-wrap; color: var(--muted); }
.actions { display: flex; gap: 8px; margin-top: auto; }
.empty { color: var(--muted); padding: 24px; }
#panel { position: fixed; left: 0; right: 0; bottom: 0; background: var(--card); border-top: 1px solid var(--line-strong);
  padding: 12px 24px; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.3fr) auto; gap: 16px; align-items: start; max-height: 40vh; overflow: auto; }
#panel h2 { font-size: 14px; font-weight: 600; margin: 0 0 6px; }
#combo { font-size: 13px; color: var(--muted); }
#combo .row { display: flex; gap: 8px; align-items: baseline; }
#combo .x { all: unset; cursor: pointer; color: var(--faint); padding: 0 4px; }
#combo .x:hover { color: var(--text); }
textarea { width: 100%; min-height: 64px; background: var(--bg); color: var(--text); border: 1px solid var(--line); border-radius: 6px; font: 13px var(--font); padding: 6px 8px; resize: vertical; }
pre#out { margin: 6px 0 0; font: 12px/1.5 var(--mono); color: var(--muted); white-space: pre-wrap; background: var(--bg); border: 1px solid var(--line); border-radius: 6px; padding: 6px 8px; }
.panel-actions { display: flex; flex-direction: column; gap: 8px; min-width: 150px; }
#copied { font-size: 12px; color: var(--accent); min-height: 1em; }
#lb { position: fixed; inset: 0; background: rgba(8,9,11,.94); display: none; z-index: 10; }
#lb.open { display: grid; grid-template-columns: minmax(0, 1fr) 320px; }
#lb .stage { display: flex; align-items: center; justify-content: center; padding: 24px; min-height: 0; position: relative; }
#lb .stage img, #lb .stage video { max-width: 100%; max-height: calc(100vh - 48px); object-fit: contain; }
#lb .stage iframe { width: 100%; height: calc(100vh - 48px); border: 0; background: #fff; border-radius: 6px; }
#lb .stage .txt { max-width: 70ch; max-height: calc(100vh - 48px); overflow: auto; white-space: pre-wrap; font-size: 17px; line-height: 1.6; background: var(--card); padding: 24px; border-radius: 8px; }
#lb aside { background: var(--card); border-left: 1px solid var(--line); padding: 20px; overflow: auto; display: flex; flex-direction: column; gap: 12px; }
#lb .nav { display: flex; gap: 8px; flex-wrap: wrap; }
@media (max-width: 760px) {
  header, main { padding-left: 16px; padding-right: 16px; }
  #panel { grid-template-columns: 1fr; padding: 12px 16px; }
  #lb.open { grid-template-columns: 1fr; grid-template-rows: minmax(0, 1fr) auto; }
  #lb aside { border-left: 0; border-top: 1px solid var(--line); max-height: 45vh; }
}
</style>
</head>
<body>
<header>
  <div>
    <h1 id="title"></h1>
    <p class="note" id="note"></p>
    <div class="hint">Klik na náhled ho zvětší · klik na podtrženou hodnotu parametru ji vezme do kombinace · v zvětšení: ← → listování, F oblíbit, Esc zavřít</div>
  </div>
  <div class="seg" role="group" aria-label="Filtr">
    <span class="seg-label">Zobrazit:</span>
    <button id="f-all" class="on" type="button">Vše</button>
    <button id="f-fav" type="button">Jen oblíbené</button>
  </div>
</header>
<main id="grid"></main>

<section id="panel" aria-label="Výběr">
  <div>
    <h2>Kombinace parametrů</h2>
    <div id="combo"></div>
  </div>
  <div>
    <h2>Text pro agenta</h2>
    <textarea id="memo" placeholder="Poznámka k výběru, např. „v03, ale tmavší pozadí“"></textarea>
    <pre id="out"></pre>
  </div>
  <div class="panel-actions">
    <button id="copy" class="primary" type="button">Kopírovat výběr</button>
    <button id="clear" type="button">Vymazat výběr</button>
    <span id="copied" aria-live="polite"></span>
  </div>
</section>

<div id="lb" role="dialog" aria-modal="true" aria-label="Zvětšená varianta">
  <div class="stage" id="lb-stage"></div>
  <aside>
    <div class="nav">
      <button id="lb-prev" type="button">← Předchozí</button>
      <button id="lb-next" type="button">Další →</button>
      <button id="lb-close" type="button">Zavřít (Esc)</button>
    </div>
    <div id="lb-info"></div>
  </aside>
</div>

<script type="application/json" id="data">__DATA__</script>
<script>
(function () {
  const DATA = JSON.parse(document.getElementById('data').textContent);
  const V = DATA.variants;
  const KIND = { image: 'obrázek', video: 'video', html: 'HTML', text: 'text' };
  const KEY = 'varianty:' + DATA.title + ':' + V.map(v => v.id).join(',');
  let state = { fav: [], combo: {}, memo: '', onlyFav: false };
  try { Object.assign(state, JSON.parse(localStorage.getItem(KEY) || '{}')); } catch (e) {}
  const save = () => { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} };
  const $ = id => document.getElementById(id);
  const el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === 'class') n.className = v; else if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v);
    }
    for (const k of kids) if (k != null) n.append(k);
    return n;
  };
  const isFav = id => state.fav.includes(id);

  function media(v, big) {
    if (v.kind === 'image') return el('img', { src: v.url, alt: 'Varianta ' + v.id, loading: big ? 'eager' : 'lazy' });
    if (v.kind === 'video') {
      const vid = el('video', { src: v.url, muted: '', loop: '', playsinline: '', preload: 'metadata' });
      vid.muted = true;
      if (big) { vid.controls = true; vid.autoplay = true; }
      return vid;
    }
    if (v.kind === 'html') {
      const f = el('iframe', { sandbox: 'allow-scripts', title: 'Varianta ' + v.id, tabindex: '-1' });
      f.srcdoc = v.body;
      return f;
    }
    return el('div', { class: 'txt' }, v.body);
  }

  function params(v) {
    const keys = Object.keys(v.params);
    if (!keys.length) return null;
    const dl = el('dl');
    for (const k of keys) {
      const val = String(v.params[k]);
      const taken = state.combo[k] && state.combo[k].from === v.id;
      dl.append(el('dt', {}, k), el('dd', {}, el('button', {
        class: 'chip' + (taken ? ' taken' : ''), type: 'button',
        title: 'Vzít „' + k + ' = ' + val + '“ do kombinace',
        onclick: () => { state.combo[k] = { value: v.params[k], from: v.id }; save(); render(); }
      }, val)));
    }
    return dl;
  }

  function favButton(v) {
    return el('button', { type: 'button', class: isFav(v.id) ? 'on' : '', 'aria-pressed': String(isFav(v.id)),
      onclick: () => toggleFav(v.id) }, isFav(v.id) ? '★ Oblíbená' : '☆ Oblíbit');
  }

  function toggleFav(id) {
    state.fav = isFav(id) ? state.fav.filter(x => x !== id) : V.filter(v => v.id === id || isFav(v.id)).map(v => v.id);
    save(); render(); if (lbIndex >= 0) showLb(lbIndex);
  }

  function card(v, i) {
    const thumb = el('button', { class: 'thumb', type: 'button', 'aria-label': 'Zvětšit variantu ' + v.id, onclick: () => showLb(i) },
      media(v, false), el('span', { class: 'kind' }, KIND[v.kind]));
    if (v.kind === 'video') {
      const vid = thumb.querySelector('video');
      thumb.addEventListener('mouseenter', () => vid.play().catch(() => {}));
      thumb.addEventListener('mouseleave', () => vid.pause());
    }
    const prompt = v.prompt ? el('details', {}, el('summary', {}, 'Prompt'), el('p', {}, v.prompt)) : null;
    return el('article', { class: 'card' + (isFav(v.id) ? ' fav' : ''), id: 'card-' + v.id },
      thumb,
      el('div', { class: 'body' },
        el('div', { class: 'idline' }, el('span', { class: 'vid' }, v.id), isFav(v.id) ? el('span', { class: 'badge' }, 'oblíbená') : null),
        v.label ? el('div', { class: 'label' }, v.label) : null,
        params(v), prompt,
        el('div', { class: 'actions' }, favButton(v), el('button', { type: 'button', onclick: () => showLb(i) }, 'Zvětšit'))));
  }

  function output() {
    const lines = ['Výběr z „' + DATA.title + '“'];
    lines.push('Oblíbené: ' + (state.fav.length ? state.fav.join(', ') : '(žádná)'));
    const keys = Object.keys(state.combo);
    if (keys.length) {
      lines.push('Kombinace parametrů:');
      for (const k of keys) lines.push('  ' + k + ' = ' + state.combo[k].value + '  (z ' + state.combo[k].from + ')');
    }
    if (state.memo.trim()) lines.push('Poznámka: ' + state.memo.trim());
    return lines.join('\n');
  }

  function render() {
    $('title').replaceChildren(DATA.title, el('span', { class: 'count' }, V.length + ' variant'));
    $('note').textContent = DATA.note;
    $('note').hidden = !DATA.note;
    $('f-all').className = state.onlyFav ? '' : 'on';
    $('f-fav').className = state.onlyFav ? 'on' : '';
    const grid = $('grid');
    grid.replaceChildren();
    V.forEach((v, i) => { if (!state.onlyFav || isFav(v.id)) grid.append(card(v, i)); });
    if (!grid.children.length) grid.append(el('p', { class: 'empty' }, 'Zatím žádná oblíbená. Označ ji tlačítkem ☆ Oblíbit.'));
    const combo = $('combo');
    combo.replaceChildren();
    const keys = Object.keys(state.combo);
    if (!keys.length) combo.append(el('span', {}, 'Klikni na hodnotu parametru v kartě a vezme se sem. Tak složíš třeba styl z jedné varianty a světlo z jiné.'));
    for (const k of keys) combo.append(el('div', { class: 'row' },
      el('span', {}, k + ': ' + state.combo[k].value + ' (z ' + state.combo[k].from + ')'),
      el('button', { class: 'x', type: 'button', 'aria-label': 'Odebrat ' + k, onclick: () => { delete state.combo[k]; save(); render(); } }, '×')));
    if ($('memo').value !== state.memo) $('memo').value = state.memo;
    $('out').textContent = output();
  }

  let lbIndex = -1;
  function showLb(i) {
    lbIndex = (i + V.length) % V.length;
    const v = V[lbIndex];
    $('lb-stage').replaceChildren(media(v, true));
    const info = $('lb-info');
    info.replaceChildren(
      el('div', { class: 'idline' }, el('span', { class: 'vid' }, v.id), el('span', { class: 'label' }, KIND[v.kind] + ' · ' + (lbIndex + 1) + ' / ' + V.length)),
      v.label ? el('div', { class: 'label' }, v.label) : null,
      el('div', { class: 'actions' }, favButton(v)),
      params(v) || el('div', { class: 'label' }, 'Bez parametrů'),
      v.prompt ? el('div', {}, el('div', { class: 'label' }, 'Prompt'), el('p', { style: 'white-space:pre-wrap;margin:4px 0 0;font-size:13px' }, v.prompt)) : null);
    $('lb').classList.add('open');
  }
  function closeLb() { lbIndex = -1; $('lb').classList.remove('open'); $('lb-stage').replaceChildren(); }

  $('f-all').onclick = () => { state.onlyFav = false; save(); render(); };
  $('f-fav').onclick = () => { state.onlyFav = true; save(); render(); };
  $('memo').oninput = e => { state.memo = e.target.value; save(); $('out').textContent = output(); };
  $('clear').onclick = () => { state.fav = []; state.combo = {}; state.memo = ''; save(); render(); };
  $('copy').onclick = async () => {
    const text = output();
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {
      const t = el('textarea'); t.value = text; document.body.append(t); t.select();
      try { ok = document.execCommand('copy'); } catch (e2) {} t.remove();
    }
    $('copied').textContent = ok ? 'Zkopírováno, vlož agentovi.' : 'Kopírování selhalo, označ text vlevo ručně.';
  };
  $('lb-prev').onclick = () => showLb(lbIndex - 1);
  $('lb-next').onclick = () => showLb(lbIndex + 1);
  $('lb-close').onclick = closeLb;
  $('lb').addEventListener('click', e => { if (e.target.id === 'lb' || e.target.id === 'lb-stage') closeLb(); });
  document.addEventListener('keydown', e => {
    if (lbIndex < 0 || e.target.tagName === 'TEXTAREA') return;
    if (e.key === 'Escape') closeLb();
    else if (e.key === 'ArrowLeft') showLb(lbIndex - 1);
    else if (e.key === 'ArrowRight') showLb(lbIndex + 1);
    else if (e.key === 'f' || e.key === 'F') toggleFav(V[lbIndex].id);
  });
  render();
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    sys.exit(main())
