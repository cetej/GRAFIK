"""Čtení podkladu: barva pozadí pod textem a odhad voda / pevnina.

Pracuje se zmenšenou kopií (delší strana `WORK_SIZE` px), souřadnice se zadávají
v bodech podkladu. Voda se pozná podle barvy: modrá převažuje nad červenou
a barva je sytá (oceán, fjordy, mělčiny). Led a sníh (světlé, nesyté), skály
a vegetace jsou pevnina. Odlesk slunce na hladině (šedostříbrný) se jako voda
nepozná — proto se rozhoduje podílem v okolí bodu a nejistý výsledek je
„pobřeží“, ne „pevnina“.

Měřeno na `processed/2026-02-03_viking-greenland-norse-vanished/images/
infographic_01_visual.png` 2026-10-08: oceán i fjordy správně, odlesk vlevo nahoře
jako pevnina.

Kopie z NG-ROBOT `ng_vector_labels/raster.py`, commit f27580e9534a408e35b153d06376e4d34697b092
(2026-10-29, GRAFIK fáze 3). Opravy z NG-ROBOT přenášej diffem originálu od tohoto commitu:
`git -C NG-ROBOT diff f27580e9 -- ng_vector_labels/raster.py`.
Změny proti originálu: žádné.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

WORK_SIZE = 900
WATER, LAND, COAST = "water", "land", "coast"
WATER_LABEL = {WATER: "ve vodě", LAND: "na pevnině", COAST: "na pobřeží"}


class Base:
    """Zmenšený podklad s maskou vody."""

    def __init__(self, path: Path):
        with Image.open(path) as im:
            self.width, self.height = im.size
            im = im.convert("RGB")
            k = WORK_SIZE / max(im.size)
            small = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.BILINEAR)
        self.k = k
        self.rgb = np.asarray(small).astype(np.float32)
        r, b = self.rgb[..., 0], self.rgb[..., 2]
        mx = self.rgb.max(-1)
        mn = self.rgb.min(-1)
        sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
        # Webová voda NG 197/223/239 (map_styles) má jas 0,94 — práh 0,96 ji pustí, led (≈ 238/242/245) ne
        self.water = ((b - r) > 18) & (sat > 0.15) & (mx / 255 < 0.96)

    def _box(self, x: float, y: float, w: float, h: float):
        H, W = self.water.shape
        x0 = int(max(0, min(W - 1, x * self.k)))
        y0 = int(max(0, min(H - 1, y * self.k)))
        x1 = int(max(x0 + 1, min(W, (x + w) * self.k)))
        y1 = int(max(y0 + 1, min(H, (y + h) * self.k)))
        return slice(y0, y1), slice(x0, x1)

    def region_pixels(self, x: float, y: float, w: float, h: float) -> np.ndarray:
        ys, xs = self._box(x, y, w, h)
        return self.rgb[ys, xs].reshape(-1, 3)

    def bg_color(self, x: float, y: float, w: float, h: float) -> tuple:
        """Medián barvy v obdélníku (body podkladu)."""
        px = self.region_pixels(x, y, w, h)
        return tuple(float(v) for v in np.median(px, axis=0))

    def bg_percentiles(self, x: float, y: float, w: float, h: float) -> tuple:
        """Nejtmavší a nejsvětlejší okolí (10. a 90. percentil jasu) — pro nejhorší kontrast."""
        px = self.region_pixels(x, y, w, h)
        lum = px @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
        lo, hi = np.percentile(lum, [10, 90])
        dark = px[lum <= lo].mean(axis=0) if (lum <= lo).any() else px.mean(axis=0)
        light = px[lum >= hi].mean(axis=0) if (lum >= hi).any() else px.mean(axis=0)
        return tuple(float(v) for v in dark), tuple(float(v) for v in light)

    def water_share(self, x: float, y: float, r: float) -> float:
        ys, xs = self._box(x - r, y - r, 2 * r, 2 * r)
        return float(self.water[ys, xs].mean())

    def classify(self, x: float, y: float, r: float) -> tuple:
        """(`water`|`land`|`coast`, podíl vody v okolí o poloměru r bodů)."""
        share = self.water_share(x, y, r)
        if share >= 0.65:
            return WATER, share
        if share <= 0.35:
            return LAND, share
        return COAST, share

    def nearest(self, x: float, y: float, want: str, max_r: float, r: float) -> tuple | None:
        """Nejbližší bod (body podkladu) do `max_r`, kde `classify` vrátí `want`; jinak None."""
        step = max(r, 4.0 / self.k)
        for ring in range(1, int(max_r / step) + 1):
            d = ring * step
            n = max(8, ring * 8)
            best = None
            for i in range(n):
                ang = 2 * np.pi * i / n
                px, py = x + d * np.cos(ang), y + d * np.sin(ang)
                if not (0 <= px < self.width and 0 <= py < self.height):
                    continue
                if self.classify(px, py, r)[0] == want:
                    best = (float(px), float(py))
                    break
            if best:
                return best
        return None
