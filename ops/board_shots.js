// Phone-size screenshots of every screen of the live app, for the review board (ops/BOARD.md in the records).
// The app reads the private records with the records token, given to the page the same way the owner's phone
// does (local storage). The pictures contain private figures: they are written to a folder that the job
// copies into the private records only. Nothing is printed except counts.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const URL = "https://benipkun.github.io/market-council/";
const TABS = ["today", "brief", "portfolio", "map", "risk", "plans", "log", "research", "watch", "quant", "council",
  "strategy", "checks", "forecasts", "record", "partners", "system", "review", "guide", "board"];

(async () => {
  const out = process.argv[2] || "/tmp/shots";
  fs.mkdirSync(out, { recursive: true });
  const token = process.env.MC_TOKEN || "";
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 1, isMobile: true, hasTouch: true });
  await ctx.addInitScript((t) => { try { if (t) localStorage.setItem("mc_gh_token", t); } catch (e) {} }, token);
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message || e).slice(0, 200)));
  let n = 0;
  const report = [];
  for (const tab of TABS) {
    const t0 = Date.now();
    try {
      await page.goto(URL + "#" + tab, { waitUntil: "networkidle", timeout: 60000 });
      await page.waitForTimeout(3000);
      const h = await page.evaluate(() => document.documentElement.scrollHeight);
      await page.screenshot({ path: path.join(out, tab + ".png"), fullPage: true, clip: { x: 0, y: 0, width: 390, height: Math.min(h, 5000) } });
      report.push({ tab, ok: true, ms: Date.now() - t0, height: h });
      n++;
    } catch (e) {
      report.push({ tab, ok: false, ms: Date.now() - t0, why: String(e.message || e).slice(0, 160) });
    }
  }
  fs.writeFileSync(path.join(out, "report.json"), JSON.stringify({ at: new Date().toISOString(), viewport: "390x844", shots: report, page_errors: errors }, null, 1));
  await browser.close();
  console.log("screens: " + n + " of " + TABS.length + ", page errors: " + errors.length);
})();
