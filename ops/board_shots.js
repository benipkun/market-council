// Phone-size screenshots of every screen of the live app, for the review board (ops/BOARD.md in the records).
// The app reads the private records with the records token, given to the page the same way the owner's phone
// does (local storage). The pictures contain private figures: they are written to a folder that the job
// copies into the private records only. Nothing is printed except counts.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const URL = "https://benipkun.github.io/market-council/";
const TABS = ["today", "memos", "learn", "brief", "portfolio", "map", "risk", "plans", "log", "research", "watch", "quant", "council",
  "strategy", "checks", "forecasts", "record", "partners", "system", "review", "guide", "board", "earnings", "behaviour"];

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
      // "network idle" never comes on screens that keep loading, so wait for the page and then a fixed time
      await page.goto(URL + "#" + tab, { waitUntil: "load", timeout: 60000 });
      await page.waitForTimeout(6000);
      const idle = await page.waitForLoadState("networkidle", { timeout: 4000 }).then(() => true).catch(() => false);
      const h = await page.evaluate(() => document.documentElement.scrollHeight);
      // a screen still showing its loading text after ten seconds never got its data (PLANS and BOARD, 1 Nov)
      const stuck = await page.evaluate(() => { const v = document.querySelector("section.view:not([hidden])"); return !!v && /Loading the|has not met yet|appear after the next engine run/.test(v.innerText); });
      await page.screenshot({ path: path.join(out, tab + ".png"), fullPage: true, clip: { x: 0, y: 0, width: 390, height: Math.min(h, 6000) } });
      // the screen's visible text, for the contradiction check and the board (private records only)
      const text = await page.evaluate(() => { const v = document.querySelector("section.view:not([hidden])"); return v ? v.innerText.slice(0, 8000) : ""; });
      // TODAY: the first phone screen alone (844 px tall, the viewport above), and whether the whole answer ends inside it (the rule of 4 Nov 2026)
      let top = null;
      if (tab === "today") {
        await page.evaluate(() => window.scrollTo(0, 0));
        await page.screenshot({ path: path.join(out, "today_top.png") });
        top = await page.evaluate(() => {
          const h = [...document.querySelectorAll("div")].find(d => d.style.fontSize === "18px" && /^DO (NOTHING TODAY|THIS 1 THING|THESE \d+ THINGS)/.test((d.innerText || "").trim()));
          const box = h && h.parentElement ? h.parentElement.getBoundingClientRect() : null;
          return box ? { answer_bottom: Math.round(box.bottom), fits_first_screen: box.bottom <= 844 } : { answer_found: false };
        });
      }
      report.push({ tab, ok: !stuck, stuck, ms: Date.now() - t0, height: h, settled: idle, text, top });
      if (!stuck) n++;
    } catch (e) {
      report.push({ tab, ok: false, ms: Date.now() - t0, why: String(e.message || e).slice(0, 160) });
    }
  }
  fs.writeFileSync(path.join(out, "report.json"), JSON.stringify({ at: new Date().toISOString(), viewport: "390x844", shots: report, page_errors: errors }, null, 1));
  await browser.close();
  console.log("screens: " + n + " of " + TABS.length + ", page errors: " + errors.length);
})();
