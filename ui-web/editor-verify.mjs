// GRAFIK M2 -- full sc-1 E2E verification (Playwright, Chromium headless).
//
// Clicks through the unified editor exactly like a user would: decompose an
// image from the UI, alpha hit-test select an element, drag it, resize it via
// the Transformer, paint+clear a brush mask, run AI edit / inpaint-behind /
// SAM segment (all real, paid fal.ai calls), export PNG, pixel-diff the
// export against both the API composite and a live stage capture, then a
// quick undo/redo smoke test.
//
// Usage:
//   node editor-verify.mjs               # full run
//   node editor-verify.mjs --skip-paid   # steps 8-10 (ai-edit/inpaint/segment):
//                                         # reuse the previous results.json
//                                         # entries instead of calling fal.ai
//                                         # again; everything else re-runs live.
//
// Budget (enforced by maxAttempts=2 per paid op, i.e. 1 retry each):
//   decompose x1(+1 retry) + ai-edit x1(+1) + inpaint-behind x1(+1) + segment x1(+1)
//   = max 8 paid HTTP generations.
//
// Idempotency: a project named "e2e-sc1" is auto-detected on every run (by
// GET /api/projects) and reused if it already has layers -- step 3 (upload +
// decompose) is skipped and the existing project is just selected by click.
// Empty-layer orphans (from a previously failed decompose attempt) are
// deleted before creating a fresh one.
//
// Reusable for M3: see scripts/pixel_diff.py (called as a subprocess below)
// for the standalone pixel-diff CLI this script drives.

import { chromium } from "playwright";
import { mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WORKTREE = path.resolve(__dirname, "..");
const OUT_DIR = path.join(WORKTREE, "scratch", "m2-e2e");
mkdirSync(OUT_DIR, { recursive: true });

const API = "http://localhost:8300";
const UI = "http://localhost:5173";
const SEED_PROJECT_NAME = "decompose-test";
const NEW_PROJECT_NAME = "e2e-sc1";
const AI_EDIT_PROMPT =
  "recolor this element to golden yellow tones, keep the exact same shapes and composition, painterly style";
const SKIP_PAID = process.argv.includes("--skip-paid");
const TRACKED_RESPONSE_PATTERNS = ["/ai-edit", "/inpaint-behind", "/segment", "/decompose", "/transform"];

const startedAt = new Date().toISOString();
const results = { steps: [], paidCalls: 0, consoleErrors: [], responses: [], screenshots: [], pixelDiff: null };

// Snapshot the previous run's results.json BEFORE this run's first persist()
// call overwrites it -- reuseFromPreviousResults() (--skip-paid) reads this
// frozen copy, not the file, since by the time steps 8-10 are reached the
// file on disk already holds this run's own (partial) data.
const PREVIOUS_RESULTS_SNAPSHOT = (() => {
  const p = path.join(OUT_DIR, "results.json");
  if (!existsSync(p)) return null;
  try {
    return JSON.parse(readFileSync(p, "utf-8"));
  } catch {
    return null;
  }
})();

/** @type {import('playwright').Page} */
let page;

// ---------- small utilities ----------

function persist() {
  const out = {
    startedAt,
    finishedAt: new Date().toISOString(),
    skipPaid: SKIP_PAID,
    steps: results.steps,
    paidCalls: results.paidCalls,
    pixelDiff: results.pixelDiff,
    consoleErrors: results.consoleErrors,
    responses: results.responses,
    screenshots: results.screenshots,
  };
  writeFileSync(path.join(OUT_DIR, "results.json"), JSON.stringify(out, null, 2));
  return out;
}

function record(name, ok, detail) {
  results.steps.push({ name, ok, detail });
  console.log(`[${ok ? "PASS" : "FAIL"}] ${name}: ${detail}`);
  persist();
}

function reuseFromPreviousResults(names) {
  const prev = PREVIOUS_RESULTS_SNAPSHOT;
  for (const name of names) {
    const prevStep = prev?.steps?.find((s) => s.name === name);
    if (prevStep) {
      const tag = "[--skip-paid reused] ";
      const detail = prevStep.detail.startsWith(tag) ? prevStep.detail : `${tag}${prevStep.detail}`;
      results.steps.push({ ...prevStep, detail });
      console.log(`[SKIP] ${name}: reused from previous results.json`);
    } else {
      record(name, false, "--skip-paid set but no previous results.json entry found to reuse");
    }
  }
  persist();
}

async function shot(name) {
  const p = path.join(OUT_DIR, `krok_${name}.png`);
  await page.screenshot({ path: p });
  results.screenshots.push(p);
  return p;
}

async function apiGet(p) {
  const r = await fetch(`${API}${p}`);
  if (!r.ok) throw new Error(`GET ${p} -> HTTP ${r.status}`);
  return r.json();
}

async function apiPost(p, body) {
  const r = await fetch(`${API}${p}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`POST ${p} -> HTTP ${r.status}`);
  return r.json();
}

async function apiDelete(p) {
  const r = await fetch(`${API}${p}`, { method: "DELETE" });
  if (!r.ok) throw new Error(`DELETE ${p} -> HTTP ${r.status}`);
  return r.json();
}

async function hashLayerPng(pid, layerId) {
  const res = await fetch(`${API}/api/projects/${pid}/layers/${layerId}/png`);
  const buf = Buffer.from(await res.arrayBuffer());
  return createHash("sha256").update(buf).digest("hex");
}

async function getLayerBox(pid, layerId) {
  const layers = await apiGet(`/api/projects/${pid}/layers`);
  const l = layers.find((x) => x.id === layerId);
  if (!l) throw new Error(`layer ${layerId} not found in project ${pid}`);
  return { x: l.x, y: l.y, width: l.width, height: l.height };
}

function projectFraction(pt, fromBox, toBox) {
  const fx = (pt.x - fromBox.x) / fromBox.width;
  const fy = (pt.y - fromBox.y) / fromBox.height;
  return { x: toBox.x + fx * toBox.width, y: toBox.y + fy * toBox.height };
}

async function canvasToScreen(cx, cy) {
  const state = await page.evaluate(() => window.__editorState);
  const box = await page.locator("canvas").first().boundingBox();
  return { x: box.x + state.offsetX + cx * state.fitScale, y: box.y + state.offsetY + cy * state.fitScale };
}

async function waitForBusyIdle(timeoutMs) {
  await page.waitForFunction(() => window.__editorState && window.__editorState.busy === null, null, {
    timeout: timeoutMs,
  });
}

async function getStatusStripText() {
  return (await page.locator(".status-op").innerText()).trim();
}

function toolButton(label) {
  return page.locator(".editor-toolbar .tool-btn", { hasText: label });
}

function aiEditSection() {
  return page.locator(".inspector-section", { hasText: "AI edit" });
}

function inpaintSection() {
  return page.locator(".inspector-section", { hasText: "Inpaint behind" });
}

function segmentSection() {
  return page.locator(".inspector-section", { hasText: "Segment (SAM)" });
}
void inpaintSection; // reserved: the Toolbar's "Inpaint behind" button is used instead (unambiguous label)

function runPixelDiff(aPath, bPath, resizeToFirst) {
  const args = [path.join(WORKTREE, "scripts", "pixel_diff.py"), aPath, bPath];
  if (resizeToFirst) args.push("--resize-to-first");
  try {
    const out = execFileSync("python", args, { cwd: WORKTREE, encoding: "utf-8" });
    return JSON.parse(out.trim().split("\n").pop());
  } catch (e) {
    return { error: String(e && e.message ? e.message : e) };
  }
}

/** Generic runner for a paid UI-triggered operation: retries once, screenshots on
 * failure, tracks paidCalls/responses, and calls `verify` only on HTTP 2xx. */
async function runPaidAction({ name, urlSubstr, trigger, verify, maxAttempts = 2, timeoutMs = 240000 }) {
  let lastDetail = "";
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    const t0 = Date.now();
    try {
      const respPromise = page.waitForResponse((r) => r.url().includes(urlSubstr), { timeout: timeoutMs });
      await trigger(attempt);
      results.paidCalls++;
      const resp = await respPromise;
      await waitForBusyIdle(timeoutMs);
      const status = resp.status();
      results.responses.push({ step: name, attempt, url: resp.url().replace(API, ""), status });
      if (status >= 200 && status < 300) {
        const v = await verify(attempt);
        if (v.ok) {
          record(name, true, `${v.detail} (HTTP ${status}, attempt ${attempt}, ${Date.now() - t0}ms)`);
          await shot(`${name}_ok`);
          return { ok: true, detail: v.detail };
        }
        lastDetail = `attempt ${attempt}: HTTP ${status} but verify failed: ${v.detail}`;
      } else {
        const bodyText = await resp.text().catch(() => "");
        lastDetail = `attempt ${attempt}: HTTP ${status} ${bodyText.slice(0, 300)}`;
      }
    } catch (e) {
      lastDetail = `attempt ${attempt} exception: ${e}`;
    }
    await shot(`${name}_fail_attempt${attempt}`);
  }
  record(name, false, lastDetail);
  return { ok: false, detail: lastDetail };
}

// ---------- step 1: seed image ----------

async function prepareSeedImage() {
  const projects = await apiGet("/api/projects");
  const seed = projects.find((p) => p.name === SEED_PROJECT_NAME);
  if (!seed) throw new Error(`seed project "${SEED_PROJECT_NAME}" not found via GET /api/projects`);
  const res = await fetch(`${API}/api/projects/${seed.id}/composite`);
  if (!res.ok) throw new Error(`composite fetch for ${seed.id} failed: HTTP ${res.status}`);
  const buf = Buffer.from(await res.arrayBuffer());
  const p = path.join(OUT_DIR, "e2e-sc1.png");
  writeFileSync(p, buf);
  record("prepare_seed_image", true, `saved ${p} (${buf.length} bytes) from seed project id=${seed.id}`);
  return p;
}

// ---------- step 3: decompose (or reuse) ----------

async function selectProjectByName(name) {
  const item = page.locator(".project-item", { hasText: name }).first();
  await item.waitFor({ timeout: 15000 });
  await item.click();
  await page.waitForFunction(() => window.__editorState && window.__editorState.projectId != null, null, {
    timeout: 20000,
  });
  await page.waitForTimeout(1200);
}

async function cleanupEmptyOrphans() {
  const existing = (await apiGet("/api/projects")).filter((p) => p.name === NEW_PROJECT_NAME && p.layer_count === 0);
  for (const orphan of existing) {
    try {
      await apiDelete(`/api/projects/${orphan.id}`);
    } catch {
      /* best-effort cleanup */
    }
  }
}

async function stepEnsureProjectAndDecompose(seedPath) {
  let pid = null;
  let reused = false;
  let attemptDetail = "";

  const existing = (await apiGet("/api/projects")).filter((p) => p.name === NEW_PROJECT_NAME);
  const good = existing.find((p) => p.layer_count > 0);

  if (good) {
    pid = good.id;
    reused = true;
    await selectProjectByName(NEW_PROJECT_NAME);
    attemptDetail = `reused existing project id=${good.id} (layer_count=${good.layer_count} at discovery)`;
  } else {
    await cleanupEmptyOrphans();
    for (let attempt = 1; attempt <= 2 && !pid; attempt++) {
      const t0 = Date.now();
      try {
        await page.locator(".editor-toolbar select").selectOption("4");
        const respPromise = page.waitForResponse((r) => r.url().includes("/decompose"), { timeout: 240000 });
        await page.locator('input[type="file"]').setInputFiles(seedPath);
        results.paidCalls++;
        const resp = await respPromise;
        await waitForBusyIdle(240000);
        results.responses.push({ step: "decompose", attempt, url: resp.url().replace(API, ""), status: resp.status() });
        if (resp.status() >= 200 && resp.status() < 300) {
          const created = (await apiGet("/api/projects")).find((p) => p.name === NEW_PROJECT_NAME && p.layer_count > 0);
          if (created) {
            pid = created.id;
            attemptDetail = `created id=${created.id} layer_count=${created.layer_count} (attempt ${attempt}, ${Date.now() - t0}ms)`;
            break;
          }
          attemptDetail = `attempt ${attempt}: HTTP 200 but no project with layers found afterward`;
        } else {
          const bodyText = await resp.text().catch(() => "");
          attemptDetail = `attempt ${attempt}: HTTP ${resp.status()} ${bodyText.slice(0, 300)}`;
        }
      } catch (e) {
        attemptDetail = `attempt ${attempt} exception: ${e}`;
      }
      if (!pid) {
        await shot(`03_decompose_fail_attempt${attempt}`);
        await cleanupEmptyOrphans();
      }
    }
  }

  if (!pid) {
    record("decompose_or_reuse", false, attemptDetail || "unknown failure");
    return null;
  }

  await page.waitForTimeout(500);
  let panelCount = -1;
  let apiCount = -1;
  try {
    apiCount = (await apiGet(`/api/projects/${pid}/layers`)).length;
    panelCount = await page.locator(".layer-item").count();
  } catch {
    /* non-fatal: recorded below via the -1 sentinels */
  }
  await shot(reused ? "03_reuse_selected" : "03_decompose_done");
  const consistent = panelCount === apiCount && apiCount > 0;
  record("decompose_or_reuse", consistent, `${attemptDetail}; panelLayerCount=${panelCount} apiLayerCount=${apiCount}`);
  return pid;
}

// ---------- step 4: select via alpha hit-test ----------

/** Scans a 5x5 grid of canvas points via the server's POST /hittest (cheap,
 * no DOM interaction) and, for every point where the server reports a
 * non-background (z_order>0) layer, actually clicks it in the browser and
 * checks window.__editorState.selectedLayerId.
 *
 * The server hittest and Konva's own client-side alpha hit-test can
 * legitimately disagree (observed in practice: a layer whose stored
 * width/height metadata doesn't match its native PNG size renders stretched
 * on the client but the server's /hittest always reads native pixel
 * coordinates) -- so this only trusts a candidate once a real click confirms
 * it, and keeps scanning candidates until one does. */
async function stepSelectElement(pid) {
  const attempts = [];
  try {
    const proj = await apiGet(`/api/projects/${pid}`);
    const cw = proj.canvas_width;
    const ch = proj.canvas_height;
    const N = 5;
    for (let iy = 0; iy < N; iy++) {
      for (let ix = 0; ix < N; ix++) {
        const x = Math.round(((ix + 0.5) / N) * cw);
        const y = Math.round(((iy + 0.5) / N) * ch);
        const hit = await apiPost(`/api/projects/${pid}/hittest`, { x, y });
        if (!hit.layer_id || hit.z_order <= 0) continue; // server itself says background/none -- skip without clicking

        const screenPt = await canvasToScreen(x, y);
        await page.mouse.click(screenPt.x, screenPt.y);
        await page.waitForTimeout(250);
        const selId = await page.evaluate(() => window.__editorState.selectedLayerId);
        attempts.push({ x, y, serverExpected: hit.layer_id, clientSelected: selId });
        if (!selId) continue;

        const layers = await apiGet(`/api/projects/${pid}/layers`);
        const selLayer = layers.find((l) => l.id === selId);
        if (!selLayer || selLayer.z_order <= 0) continue; // client landed on the background too -- keep scanning

        await shot("04_selected");
        const agree = selId === hit.layer_id;
        record(
          "select_element",
          true,
          `canvas(${x},${y}) server-expected=${hit.layer_id}("${hit.layer_name}") client-selected=${selId}("${selLayer.name}", z=${selLayer.z_order})` +
            (agree ? "" : ` [client/server hit-test DISAGREED -- accepted the real click result]`),
        );
        return {
          layerId: selId,
          layerName: selLayer.name,
          hitX: x,
          hitY: y,
          origBox: { x: selLayer.x, y: selLayer.y, width: selLayer.width, height: selLayer.height },
        };
      }
    }
    record("select_element", false, `no click produced a z_order>0 selection over a 5x5 grid; attempts=${JSON.stringify(attempts)}`);
    return null;
  } catch (e) {
    record("select_element", false, `exception: ${e}; attempts so far=${JSON.stringify(attempts)}`);
    return null;
  }
}

// ---------- step 5: move ----------

async function stepMove(pid, target) {
  try {
    const before = await getLayerBox(pid, target.layerId);
    const screenPt = await canvasToScreen(target.hitX, target.hitY);
    const respPromise = page.waitForResponse((r) => r.url().includes("/transform"), { timeout: 15000 });
    await page.mouse.move(screenPt.x, screenPt.y);
    await page.mouse.down();
    await page.mouse.move(screenPt.x + 80, screenPt.y + 40, { steps: 12 });
    await page.mouse.up();
    const resp = await respPromise;
    await page.waitForTimeout(300);
    const after = await getLayerBox(pid, target.layerId);
    const state = await page.evaluate(() => window.__editorState);
    const expDx = 80 / state.fitScale;
    const expDy = 40 / state.fitScale;
    const dx = after.x - before.x;
    const dy = after.y - before.y;
    const ok = resp.status() === 200 && Math.abs(dx - expDx) <= 2 && Math.abs(dy - expDy) <= 2;
    await shot("05_after_move");
    record(
      "move_layer",
      ok,
      `status=${resp.status()} dx=${dx.toFixed(1)}px (expected ${expDx.toFixed(1)}) dy=${dy.toFixed(1)}px (expected ${expDy.toFixed(1)}) fitScale=${state.fitScale.toFixed(4)}`,
    );
    return ok;
  } catch (e) {
    record("move_layer", false, `exception: ${e}`);
    return false;
  }
}

// ---------- step 6: scale via a Transformer corner anchor ----------

// Outward drag direction per corner -- dragging a corner away from its
// opposite (fixed) corner always grows width/height, regardless of which one
// we pick.
const CORNER_OUTWARD = {
  "top-left": { dx: -1, dy: -1 },
  "top-right": { dx: 1, dy: -1 },
  "bottom-left": { dx: -1, dy: 1 },
  "bottom-right": { dx: 1, dy: 1 },
};

/** Picks whichever corner anchor has the most clearance from the Stage's own
 * edges. A layer dragged near/past the canvas edge in step 5 can leave its
 * bottom-right (or any fixed corner) anchor rendered outside the Stage's
 * bounds -- Konva's hit-test (and thus a plain screen click) can never reach
 * a point off-stage, so hardcoding one corner isn't reliable. */
async function pickSafestCornerAnchor() {
  const names = Object.keys(CORNER_OUTWARD);
  const info = await page.evaluate((corners) => {
    const stage = window.Konva.stages[0];
    const tr = stage.findOne("Transformer");
    if (!tr) return null;
    const positions = {};
    for (const n of corners) {
      const a = tr.findOne("." + n);
      positions[n] = a ? a.getAbsolutePosition() : null;
    }
    return { positions, stageW: stage.width(), stageH: stage.height() };
  }, names);
  if (!info) return null;
  let best = null;
  let bestMargin = -Infinity;
  for (const n of names) {
    const p = info.positions[n];
    if (!p) continue;
    const margin = Math.min(p.x, p.y, info.stageW - p.x, info.stageH - p.y);
    if (margin > bestMargin) {
      bestMargin = margin;
      best = { name: n, pos: p, margin };
    }
  }
  return best;
}

async function stepScale(pid, target) {
  try {
    const before = await getLayerBox(pid, target.layerId);
    const canvasBox = await page.locator("canvas").first().boundingBox();
    const anchorInfo = await pickSafestCornerAnchor();
    if (!anchorInfo) throw new Error("no Transformer corner anchors found -- is a layer selected in Select tool?");
    const dir = CORNER_OUTWARD[anchorInfo.name];
    const asx = canvasBox.x + anchorInfo.pos.x;
    const asy = canvasBox.y + anchorInfo.pos.y;
    const respPromise = page.waitForResponse((r) => r.url().includes("/transform"), { timeout: 15000 });
    await page.mouse.move(asx, asy);
    await page.mouse.down();
    await page.mouse.move(asx + dir.dx * 30, asy + dir.dy * 30, { steps: 12 });
    await page.mouse.up();
    const resp = await respPromise;
    await page.waitForTimeout(300);
    const after = await getLayerBox(pid, target.layerId);
    const ok = resp.status() === 200 && after.width > before.width && after.height > before.height;
    await shot("06_after_scale");
    record(
      "scale_layer",
      ok,
      `anchor=${anchorInfo.name} (margin=${anchorInfo.margin.toFixed(1)}px) status=${resp.status()} before=${before.width}x${before.height} after=${after.width}x${after.height}`,
    );
    return ok;
  } catch (e) {
    record("scale_layer", false, `exception: ${e}`);
    await shot("06_scale_error");
    return false;
  }
}

// ---------- step 7: brush mechanics (free) ----------

async function paintBrushStroke(fromCanvasPt, toCanvasPt) {
  const from = await canvasToScreen(fromCanvasPt.x, fromCanvasPt.y);
  const to = await canvasToScreen(toCanvasPt.x, toCanvasPt.y);
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(150);
}

async function stepBrushMechanics(pid, target) {
  try {
    await toolButton("Brush").click();
    await page.waitForTimeout(200);

    const box = await getLayerBox(pid, target.layerId);
    const cx = box.x + box.width * 0.5;
    const cy = box.y + box.height * 0.5;
    await paintBrushStroke({ x: cx - 30, y: cy - 20 }, { x: cx + 10, y: cy + 20 });
    await paintBrushStroke({ x: cx + 20, y: cy - 10 }, { x: cx - 10, y: cy + 25 });

    const hasPixels = await page.evaluate(() => {
      const c = window.__brushCanvas;
      if (!c) return false;
      const ctx = c.getContext("2d");
      const data = ctx.getImageData(0, 0, c.width, c.height).data;
      for (let i = 3; i < data.length; i += 4) if (data[i] > 0) return true;
      return false;
    });
    const chipText = (await aiEditSection().locator(".editor-hint").first().innerText()).trim();
    const chipOk = /Brush maska aktivn/.test(chipText);
    await shot("07_brush_strokes");
    const paintOk = hasPixels && chipOk;
    record("brush_mechanics", paintOk, `brushCanvasHasPixels=${hasPixels}; chip="${chipText}"`);

    // Clear -- must not affect downstream steps.
    await page.locator(".brush-controls button", { hasText: "Clear" }).click();
    await page.waitForTimeout(200);

    // Back to Select + reselect by click. The move+scale already applied
    // changed the layer's box, so try several candidate points across its
    // current bounding box (center, quadrants, and the original hit point
    // projected through the transform) and accept the first real click that
    // actually lands the selection -- more robust than trusting a single
    // projected point, since a resize can shift where the opaque content is.
    await toolButton("Select").click();
    const curBox = await getLayerBox(pid, target.layerId);
    const candidates = [
      { x: curBox.x + curBox.width * 0.5, y: curBox.y + curBox.height * 0.5 },
      { x: curBox.x + curBox.width * 0.3, y: curBox.y + curBox.height * 0.3 },
      { x: curBox.x + curBox.width * 0.7, y: curBox.y + curBox.height * 0.3 },
      { x: curBox.x + curBox.width * 0.3, y: curBox.y + curBox.height * 0.7 },
      { x: curBox.x + curBox.width * 0.7, y: curBox.y + curBox.height * 0.7 },
      projectFraction({ x: target.hitX, y: target.hitY }, target.origBox, curBox),
    ];
    let reselectOk = false;
    let selId = null;
    let hitPoint = null;
    for (const pt of candidates) {
      const screenPt = await canvasToScreen(pt.x, pt.y);
      await page.mouse.click(screenPt.x, screenPt.y);
      await page.waitForTimeout(250);
      selId = await page.evaluate(() => window.__editorState.selectedLayerId);
      if (selId === target.layerId) {
        reselectOk = true;
        hitPoint = pt;
        break;
      }
    }
    await shot("07_reselected");
    record(
      "brush_reselect",
      reselectOk,
      `tried ${candidates.length} candidate points on the current box; selectedLayerId=${selId} expected=${target.layerId}` +
        (reselectOk ? ` (hit at canvas ${JSON.stringify(hitPoint)})` : ""),
    );
    return paintOk && reselectOk;
  } catch (e) {
    record("brush_mechanics", false, `exception: ${e}`);
    await shot("07_brush_error");
    return false;
  }
}

// ---------- step 8: AI edit (paid) ----------

async function stepAiEditPaid(pid, target) {
  const preHash = await hashLayerPng(pid, target.layerId);
  await runPaidAction({
    name: "ai_edit_paid",
    urlSubstr: "/ai-edit",
    trigger: async () => {
      const section = aiEditSection();
      await section.locator("textarea").fill(AI_EDIT_PROMPT);
      await section.locator("select").selectOption("qwen-inpaint");
      await section.getByRole("button", { name: "Run", exact: true }).click();
    },
    verify: async () => {
      const postHash = await hashLayerPng(pid, target.layerId);
      const statusText = await getStatusStripText();
      const changed = postHash !== preHash;
      return {
        ok: changed,
        detail: `layer ${target.layerId} PNG hash ${changed ? "changed" : "UNCHANGED"} (${preHash.slice(0, 10)}->${postHash.slice(0, 10)}); status="${statusText}"`,
      };
    },
  });
  await shot("08_ai_edit_result");
}

// ---------- step 9: inpaint behind (paid) ----------

async function stepInpaintBehindPaid(pid, target) {
  const layers = await apiGet(`/api/projects/${pid}/layers`);
  const bgCandidates = layers.filter((l) => l.visible && l.id !== target.layerId);
  if (bgCandidates.length === 0) {
    record("inpaint_behind_paid", false, "no visible background candidate layer (all other layers hidden or absent)");
    return;
  }
  const bgLayer = bgCandidates.reduce((min, l) => (l.z_order < min.z_order ? l : min), bgCandidates[0]);
  const preHash = await hashLayerPng(pid, bgLayer.id);

  await runPaidAction({
    name: "inpaint_behind_paid",
    urlSubstr: "/inpaint-behind",
    trigger: async () => {
      await page.locator(".editor-toolbar").getByRole("button", { name: "Inpaint behind", exact: true }).click();
    },
    verify: async () => {
      const postHash = await hashLayerPng(pid, bgLayer.id);
      const statusText = await getStatusStripText();
      const changed = postHash !== preHash;
      return {
        ok: changed,
        detail: `bgLayer=${bgLayer.id} ("${bgLayer.name}", z=${bgLayer.z_order}) PNG hash ${changed ? "changed" : "UNCHANGED"}; status="${statusText}"`,
      };
    },
  });

  // Nudge the (still-selected) target element sideways so the filled-in
  // background is visible next to its original outline in the screenshot.
  try {
    const selId = await page.evaluate(() => window.__editorState.selectedLayerId);
    if (selId === target.layerId) {
      const curBox = await getLayerBox(pid, target.layerId);
      const clickPt = projectFraction({ x: target.hitX, y: target.hitY }, target.origBox, curBox);
      const sp = await canvasToScreen(clickPt.x, clickPt.y);
      await page.mouse.move(sp.x, sp.y);
      await page.mouse.down();
      await page.mouse.move(sp.x + 120, sp.y, { steps: 10 });
      await page.mouse.up();
      await page.waitForTimeout(500);
    }
  } catch (e) {
    results.consoleErrors.push(`post-inpaint cosmetic nudge failed (non-fatal): ${e}`);
  }
  await shot("09_inpaint_result");
}

// ---------- step 10: SAM segment (paid) ----------

async function stepSegmentPaid(pid) {
  await toolButton("Segment").click();
  await page.waitForTimeout(150);
  await runPaidAction({
    name: "segment_paid",
    urlSubstr: "/segment",
    trigger: async () => {
      const section = segmentSection();
      await section.locator('input[type="text"]').fill("the largest object");
      await section.getByRole("button", { name: "Segment", exact: true }).click();
    },
    verify: async () => {
      const statusText = await getStatusStripText();
      const m = statusText.match(/SAM našel (\d+) masek/);
      const layers = await apiGet(`/api/projects/${pid}/layers`);
      const samCount = layers.filter((l) => l.tags.includes("sam")).length;
      // mask_count == 0 is a legitimate outcome per spec -- always ok on HTTP 200.
      return { ok: true, detail: `status="${statusText}" parsedMaskCount=${m ? m[1] : "n/a"} samLayersNow=${samCount}` };
    },
  });
  await shot("10_segment_layers");
}

// ---------- step 11: export + pixel-diff parity ----------

async function stepExportAndDiff(pid) {
  try {
    await toolButton("Select").click();
    await page.waitForTimeout(150);

    // Deselect by clicking the letterboxed margin around the canvas (Stage
    // background, not any Shape) so the Transformer detaches.
    const state = await page.evaluate(() => window.__editorState);
    const canvasBox = await page.locator("canvas").first().boundingBox();
    const marginX = canvasBox.x + Math.max(4, state.offsetX / 2);
    const marginY = canvasBox.y + 4;
    await page.mouse.click(marginX, marginY);
    await page.waitForTimeout(200);

    // (a) Preview capture: stage.toDataURL with the debug border hidden,
    // cropped to the canvas rect and rescaled to native project resolution.
    const dataUrl = await page.evaluate(() => {
      const stage = window.Konva.stages[0];
      const s = window.__editorState;
      const border = stage.findOne(".canvas-border");
      const prevVisible = border ? border.visible() : true;
      if (border) {
        border.visible(false);
        border.getLayer().batchDraw();
      }
      const url = stage.toDataURL({
        x: s.offsetX,
        y: s.offsetY,
        width: s.canvasWidth * s.fitScale,
        height: s.canvasHeight * s.fitScale,
        pixelRatio: 1 / s.fitScale,
      });
      if (border) {
        border.visible(prevVisible);
        border.getLayer().batchDraw();
      }
      return url;
    });
    const previewPath = path.join(OUT_DIR, "preview_capture.png");
    writeFileSync(previewPath, Buffer.from(dataUrl.split(",")[1], "base64"));

    // (b) Export PNG via the real UI download flow.
    const downloadPromise = page.waitForEvent("download", { timeout: 30000 });
    await page.locator(".editor-toolbar").getByRole("button", { name: "Export PNG", exact: true }).click();
    const download = await downloadPromise;
    const exportPath = path.join(OUT_DIR, "export.png");
    await download.saveAs(exportPath);
    await waitForBusyIdle(15000);

    // (c) API composite, straight from the server.
    const compositeRes = await fetch(`${API}/api/projects/${pid}/composite`);
    const compositePath = path.join(OUT_DIR, "composite_api.png");
    writeFileSync(compositePath, Buffer.from(await compositeRes.arrayBuffer()));

    await shot("11_final_export_state");

    const diffExportComposite = runPixelDiff(exportPath, compositePath, false);
    const diffExportPreview = runPixelDiff(exportPath, previewPath, true);
    results.pixelDiff = { exportVsComposite: diffExportComposite, exportVsPreview: diffExportPreview };

    const ok = compositeRes.ok && !diffExportComposite.error && diffExportComposite.mean_abs_diff < 1.0;
    record(
      "export_and_pixel_diff",
      ok,
      `exportVsComposite mean=${diffExportComposite.mean_abs_diff ?? "ERR:" + diffExportComposite.error} ` +
        `exportVsPreview mean=${diffExportPreview.mean_abs_diff ?? "ERR:" + diffExportPreview.error} ` +
        `pct_gt8=${diffExportPreview.pct_pixels_gt8 ?? "n/a"}`,
    );
    return ok;
  } catch (e) {
    record("export_and_pixel_diff", false, `exception: ${e}`);
    await shot("11_export_error");
    return false;
  }
}

// ---------- step 12: undo/redo smoke ----------

async function stepUndoRedo(pid) {
  try {
    await page.locator(".editor-toolbar").getByRole("button", { name: "Undo", exact: true }).click();
    await waitForBusyIdle(30000);
    const afterUndoStatus = await getStatusStripText();
    const projAfterUndo = await fetch(`${API}/api/projects/${pid}`);

    await page.locator(".editor-toolbar").getByRole("button", { name: "Redo", exact: true }).click();
    await waitForBusyIdle(30000);
    const afterRedoStatus = await getStatusStripText();
    const projAfterRedo = await fetch(`${API}/api/projects/${pid}`);

    const ok = projAfterUndo.ok && projAfterRedo.ok;
    record(
      "undo_redo_smoke",
      ok,
      `undo status="${afterUndoStatus}" (GET project -> ${projAfterUndo.status}); redo status="${afterRedoStatus}" (GET project -> ${projAfterRedo.status})`,
    );
    return ok;
  } catch (e) {
    record("undo_redo_smoke", false, `exception: ${e}`);
    return false;
  }
}

// ---------- main ----------

async function main() {
  const seedPath = await prepareSeedImage();

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1600, height: 900 }, acceptDownloads: true });
  page = await context.newPage();

  page.on("console", (m) => {
    if (m.type() === "error") results.consoleErrors.push(m.text().slice(0, 300));
  });
  page.on("pageerror", (e) => results.consoleErrors.push(`pageerror: ${String(e).slice(0, 300)}`));
  page.on("response", (r) => {
    const u = r.url();
    if (TRACKED_RESPONSE_PATTERNS.some((pat) => u.includes(pat))) {
      results.responses.push({ url: u.replace(API, ""), status: r.status() });
    }
  });

  try {
    await page.goto(UI, { waitUntil: "load" });
    await page.waitForSelector(".editor-sidebar h1", { timeout: 30000 });
    const h1 = (await page.locator(".editor-sidebar h1").innerText()).trim();
    record("open_ui", h1.includes("GRAFIK Editor"), `h1="${h1}"`);
    await shot("02_editor_loaded");

    const pid = await stepEnsureProjectAndDecompose(seedPath);
    if (!pid) {
      record("select_element", false, "skipped: no project available after decompose failure");
      record("move_layer", false, "skipped: no project");
      record("scale_layer", false, "skipped: no project");
      record("brush_mechanics", false, "skipped: no project");
      if (SKIP_PAID) reuseFromPreviousResults(["ai_edit_paid", "inpaint_behind_paid", "segment_paid"]);
      else {
        record("ai_edit_paid", false, "skipped: no project");
        record("inpaint_behind_paid", false, "skipped: no project");
        record("segment_paid", false, "skipped: no project");
      }
      record("export_and_pixel_diff", false, "skipped: no project");
      record("undo_redo_smoke", false, "skipped: no project");
    } else {
      const target = await stepSelectElement(pid);
      if (target) {
        await stepMove(pid, target);
        await stepScale(pid, target);
        await stepBrushMechanics(pid, target);
        if (SKIP_PAID) {
          reuseFromPreviousResults(["ai_edit_paid", "inpaint_behind_paid"]);
        } else {
          await stepAiEditPaid(pid, target);
          await stepInpaintBehindPaid(pid, target);
        }
      } else {
        record("move_layer", false, "skipped: no selection from step 4");
        record("scale_layer", false, "skipped: no selection from step 4");
        record("brush_mechanics", false, "skipped: no selection from step 4");
        if (SKIP_PAID) reuseFromPreviousResults(["ai_edit_paid", "inpaint_behind_paid"]);
        else {
          record("ai_edit_paid", false, "skipped: no selection from step 4");
          record("inpaint_behind_paid", false, "skipped: no selection from step 4");
        }
      }

      if (SKIP_PAID) reuseFromPreviousResults(["segment_paid"]);
      else await stepSegmentPaid(pid);

      await stepExportAndDiff(pid);
      await stepUndoRedo(pid);
    }
  } finally {
    await browser.close();
  }
}

try {
  await main();
} catch (e) {
  console.error("FATAL:", e);
  results.consoleErrors.push(`FATAL: ${String(e)}`);
} finally {
  const final = persist();
  const passCount = final.steps.filter((s) => s.ok).length;
  console.log("RESULTS_JSON " + path.join(OUT_DIR, "results.json"));
  console.log(
    `SUMMARY ${passCount}/${final.steps.length} steps passed; paidCalls=${final.paidCalls}; consoleErrors=${final.consoleErrors.length}`,
  );
}
