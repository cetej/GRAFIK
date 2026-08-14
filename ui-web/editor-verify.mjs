// Editor MVP verification — headed Chromium: load project, select layer, drag, verify persistence.
import { chromium } from "playwright";

const UI = "http://localhost:5173";
const results = { transformPosts: [], consoleErrors: [] };

const browser = await chromium.launch({ headless: false, args: ["--window-size=1680,1020", "--window-position=40,40"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
page.on("console", (m) => { if (m.type() === "error") results.consoleErrors.push(m.text().slice(0, 200)); });
page.on("response", (r) => {
  if (r.url().includes("/transform")) results.transformPosts.push({ url: r.url().split("/api/")[1], status: r.status() });
});

await page.goto(UI, { waitUntil: "load" });
await page.waitForTimeout(1500);

// select the copied project in the sidebar (project.json name is "decompose-test")
results.pageText = (await page.locator("body").innerText()).slice(0, 400);
const projectBtn = page.locator("text=decompose").first();
await projectBtn.waitFor({ timeout: 10000 });
await projectBtn.click();
await page.waitForTimeout(3500); // layers + PNGs + cache
await page.screenshot({ path: "../scratch/smoke/editor_loaded.png" });

// click on canvas center to select a layer (alpha hit-test)
const canvas = page.locator("canvas").first();
const box = await canvas.boundingBox();
const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
await page.mouse.click(cx, cy);
await page.waitForTimeout(600);
await page.screenshot({ path: "../scratch/smoke/editor_selected.png" });

// drag the selected layer by (120, 60)
await page.mouse.move(cx, cy);
await page.mouse.down();
await page.mouse.move(cx + 120, cy + 60, { steps: 12 });
await page.mouse.up();
await page.waitForTimeout(1500); // dragend -> POST transform
await page.screenshot({ path: "../scratch/smoke/editor_after_drag.png" });

results.statusStrip = await page.locator(".status-strip, footer, [class*=status]").first().innerText().catch(() => "n/a");
console.log("EDITOR_VERIFY " + JSON.stringify(results));
await browser.close();
