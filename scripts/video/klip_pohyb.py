# Klip postavy z jednoho obrázku a videa s pohybem přes fal.ai (PLACENÉ, jen s --confirm-cost).
# Bez --confirm-cost jen ořízne pohyb, vypíše cenu a skončí. Srovnání modelů: docs/spikes/2026-11-06-klipy-pohyb.md
#   python scripts/video/klip_pohyb.py --image ref-front.png --motion chuze.mp4 --start 1 --duration 6 [--model kling26]
#   python scripts/video/klip_pohyb.py --dobrat library/klipy/<slozka>   (stáhne výsledek podle request.json, nic neplatí)
import argparse
import json
import math
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from engine.keys import get_key  # noqa: E402

# Knihovna a účet cen jsou v hlavním checkoutu, ne ve worktree.
LIB = Path("C:/Users/stock/Documents/000_NGM/GRAFIK/library")
LEDGER = LIB / "costs.jsonl"

# Cena za sekundu výstupu podle stránek fal.ai 2026-11-06; účtuje se délka výstupu, počítáme celé sekundy nahoru.
MODELS = {
    "kling26": {"endpoint": "fal-ai/kling-video/v2.6/pro/motion-control", "usd_s": 0.112, "what": "Kling 2.6 Pro motion control"},
    "kling3": {"endpoint": "fal-ai/kling-video/v3/pro/motion-control", "usd_s": 0.168, "what": "Kling 3.0 Pro motion control"},
    "recast": {"endpoint": "minimax/h3-max/recast", "usd_s": 0.30, "what": "MiniMax H3 Max Recast 768P"},
    # Kling 4.0 nemá motion control; pohyb nese referenční video (@Video1), postavu element (@Element1).
    # S videem 0,094 USD/s (720p) / 0,141 USD/s (1080p), účtuje se vstup + výstup, nejméně 2× výstup.
    "kling4": {"endpoint": "kling/v4/reference-to-video", "usd_s": {"720p": 0.094, "1080p": 0.141}, "what": "Kling 4.0 reference-to-video"},
}
PROMPT_V4 = ("@Element1, a Roman legionary, walks toward the camera on a plain light grey studio floor, following exactly "
             "the body motion and timing of @Video1. Keep the helmet without crest, segmented armour, belt with hanging straps, "
             "red tunic and laced sandals exactly as on @Element1. Clean face without scratches. Realistic photo, static camera.")
PROMPT = ("A Roman legionary walks toward the camera. Keep the helmet, segmented armour, belt with hanging straps, "
          "red tunic and laced sandals exactly as in the reference image. Realistic photo, natural motion.")


def ffprobe_duration(p: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def trim(src: Path, dst: Path, start: float, duration: float):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start}", "-i", str(src), "-t", f"{duration}", "-an",
                    "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", str(dst)], check=True)


def frames(video: Path, out: Path, n: int = 6):
    out.mkdir(exist_ok=True)
    d = ffprobe_duration(video)
    paths = []
    for i in range(n):
        t = d * (i + 0.5) / n
        p = out / f"snimek-{i + 1:02d}-{t:04.1f}s.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1", str(p)], check=True)
        paths.append(p)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-vf", f"fps={n}/{d},scale=360:-1,tile={n}x1",
                    "-frames:v", "1", str(out / "prehled.jpg")], check=True)
    return paths


def min_side(src: Path, d: Path, side: int = 300) -> Path:
    # fal odmítne obrázek elementu s kratší stranou pod 300 px nebo poměrem stran mimo 0,4–2,5 (úzký boční pohled):
    # doplní se barvou rohu. Kontrola proběhne až po odeslání, proto ji děláme tady.
    from PIL import Image
    im = Image.open(src).convert("RGB")
    w = max(im.width, side, math.ceil(0.4 * im.height))
    h = max(im.height, side, math.ceil(0.4 * w))
    if (w, h) == im.size:
        return src
    out = Image.new("RGB", (w, h), im.getpixel((0, 0)))
    out.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    p = d / f"element-{src.stem}.png"
    out.save(p)
    return p


def log(entry: dict, status: str):
    with open(LEDGER, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"), **entry, "status": status}, ensure_ascii=False) + "\n")


def fetch(client, d: Path, endpoint: str, request_id: str):
    import httpx
    r = client.result(endpoint, request_id)
    (d / "result.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    out = d / "klip.mp4"
    out.write_bytes(httpx.get(r["video"]["url"], timeout=600, follow_redirects=True).raise_for_status().content)
    shots = frames(out, d / "snimky")
    print(f"klip {out} {out.stat().st_size} B, {ffprobe_duration(out):.2f} s; snímky {len(shots)} v {d / 'snimky'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", type=Path)
    ap.add_argument("--motion", type=Path, help="video s pohybem (celá postava, jeden člověk)")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--duration", type=float, default=6.0)
    ap.add_argument("--model", choices=MODELS, default="kling26")
    ap.add_argument("--orientation", choices=["video", "image"], default="video", help="Kling: rámování podle videa (do 30 s) nebo obrázku (do 10 s)")
    ap.add_argument("--element", type=Path, nargs="*", default=[], help="kling3/kling4: další pohledy postavy pro element (1–3)")
    ap.add_argument("--resolution", choices=["720p", "1080p"], default="1080p", help="jen kling4")
    ap.add_argument("--prompt")
    ap.add_argument("--out", type=Path, help="výstupní složka (výchozí library/klipy/<čas>-<model>)")
    ap.add_argument("--confirm-cost", action="store_true")
    ap.add_argument("--dobrat", type=Path, help="složka s request.json: stáhni hotový výsledek bez nového placení")
    a = ap.parse_args()

    import fal_client
    client = fal_client.SyncClient(key=get_key("FAL_KEY", "FAL_API_KEY"), default_timeout=1800)

    if a.dobrat:
        req = json.loads((a.dobrat / "request.json").read_text(encoding="utf-8"))
        fetch(client, a.dobrat, req["endpoint"], req["request_id"])
        return

    if not (a.image and a.motion):
        ap.error("--image a --motion jsou povinné")
    m = MODELS[a.model]
    if a.model == "recast" and a.duration < 5:
        ap.error("H3 Max Recast chce video 5–30 s")
    if a.orientation == "image" and a.duration > 10:
        ap.error("orientation=image dovolí nejvýš 10 s")
    if a.element and a.model not in ("kling3", "kling4"):
        ap.error("--element jen s --model kling3 nebo kling4")
    if a.model == "kling3" and a.element and a.orientation != "video":
        ap.error("element u kling3 jen s --orientation video")
    if a.model == "kling4" and not a.element:
        ap.error("kling4 potřebuje --element (1–3 další pohledy postavy)")
    prompt = a.prompt or (PROMPT_V4 if a.model == "kling4" else PROMPT)

    d = a.out or LIB / "klipy" / f"{datetime.now():%Y%m%d-%H%M%S}-{a.model}"
    d.mkdir(parents=True, exist_ok=True)
    pohyb = d / "pohyb.mp4"
    trim(a.motion, pohyb, a.start, a.duration)
    dur = ffprobe_duration(pohyb)
    secs = math.ceil(dur - 0.02)
    usd_s = m["usd_s"][a.resolution] if a.model == "kling4" else m["usd_s"]
    if a.model == "kling4":
        out_s = round(dur)
        secs = max(out_s + secs, 2 * out_s)  # vstup + výstup, nejméně 2× výstup
    usd = round(usd_s * secs, 3)
    print(f"model {m['what']} ({m['endpoint']}), pohyb {dur:.2f} s -> účtováno {secs} s x {usd_s} USD = {usd} USD")
    print(f"vstupy: obrázek {a.image}, pohyb {pohyb}")
    if not a.confirm_cost:
        print("Bez --confirm-cost nic neposílám. Cena výše je odhad za jeden klip.")
        return

    img_url = client.upload_file(a.image)
    vid_url = client.upload_file(pohyb)
    if a.model == "recast":
        args = {"video_url": vid_url, "reference_image_urls": [img_url], "prompt": prompt, "resolution": "768P"}
    elif a.model == "kling4":
        args = {"prompt": prompt, "duration": round(dur), "resolution": a.resolution, "aspect_ratio": "9:16",
                "video_urls": [vid_url],
                "elements": [{"frontal_image_url": img_url, "reference_image_urls": [client.upload_file(min_side(p, d)) for p in a.element]}]}
    else:
        args = {"image_url": img_url, "video_url": vid_url, "character_orientation": a.orientation,
                "prompt": prompt, "keep_original_sound": False}
        if a.element:
            args["elements"] = [{"frontal_image_url": img_url, "reference_image_urls": [client.upload_file(min_side(p, d)) for p in a.element]}]
            args["prompt"] = prompt.replace("A Roman legionary", "@Element1, a Roman legionary,")

    t = time.time()
    handle = client.submit(m["endpoint"], arguments=args)
    req = {"endpoint": m["endpoint"], "request_id": handle.request_id, "submitted": datetime.now().isoformat(timespec="seconds"),
           "image": str(a.image), "motion": str(a.motion), "start": a.start, "duration": dur, "usd": usd, "arguments": args}
    (d / "request.json").write_text(json.dumps(req, ensure_ascii=False, indent=2), encoding="utf-8")
    entry = {"job_id": None, "caller": "klip-pohyb", "backend": f"fal:{m['endpoint']}", "n": 1, "usd": usd,
             "items": [{"what": f"{m['what']} {secs} s", "usd": usd}], "request_id": handle.request_id}
    log(entry, "pending")
    print(f"odesláno, request_id {handle.request_id}, složka {d}")
    try:
        handle.get()
    except Exception:
        log(entry, "failed")
        raise
    log(entry, "ok")
    print(f"hotovo za {time.time() - t:.0f} s")
    fetch(client, d, m["endpoint"], handle.request_id)


if __name__ == "__main__":
    main()
