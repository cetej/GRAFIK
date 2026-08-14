// Konva spike benchmark runner — headed Chromium via Playwright.
// Opens the spike page, waits for window.__benchResults, prints JSON, screenshots, exits.
import { chromium } from "playwright";

const url = process.env.SPIKE_URL || "http://localhost:5173";

const browser = await chromium.launch({
  headless: false,
  args: ["--window-size=1680,1020", "--window-position=40,40"],
});
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });

page.on("pageerror", (e) => console.log("PAGE_ERROR " + e.message));
await page.goto(url, { waitUntil: "load" });

await page.waitForFunction("!!window.__benchResults", { timeout: 240_000, polling: 1000 });
const results = await page.evaluate("window.__benchResults");
console.log("BENCH_JSON " + JSON.stringify(results));

await page.screenshot({ path: "../scratch/smoke/konva_spike_bench.png" });

// interaction proof: click near stage center to select a layer -> Transformer handles
await page.mouse.click(800, 430);
await page.waitForTimeout(400);
await page.screenshot({ path: "../scratch/smoke/konva_spike_selected.png" });

await browser.close();
console.log("RUNNER_DONE");
