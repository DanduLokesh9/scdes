/* Where does text stop short of the card it sits in?

   The client: "Why does the text underneath Download the draft document go
   fully left to right, but above the Save a version it stops halfway? Many
   fields are like this and it leaves a huge blank space to the right. Gives
   it a feeling like we converted a Word table onto a webpage and just left
   it."

   Two separate faults, and only a real browser can tell them apart:

     1. Inconsistency — two paragraphs in the same card wrapping at different
        widths, which is what makes it look unfinished rather than designed.
     2. Marooning — a line of text ending far short of its container, so the
        card is mostly empty on the right.

   So this measures every block of prose against the card it is in, on a real
   viewport, and reports the ones that stop short. Run it before and after a
   change to see whether the change actually did anything.

   Usage:  node tools/check_measure.js [view] [width]
*/

const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawn } = require("child_process");

const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";
const VIEW = process.argv[2] || "framework";
const WIDTH = Number(process.argv[3] || 1440);
const PORT = 9223;

const HARNESS_AGENCY = "gaius.harness";
const HARNESS_EMAIL = "walk@harness.gaius.test";

//: How far short of its card a block may stop before it is worth reporting.
//: A measure is good typography; a measure that leaves a third of the card
//: empty next to a sibling that fills it is the thing being complained about.
const SLACK = 120;

const CHROME = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
].find((p) => fs.existsSync(p));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class Browser {
  constructor(ws) {
    this.ws = ws; this.next = 1; this.waiting = new Map();
    ws.addEventListener("message", (e) => {
      const msg = JSON.parse(e.data);
      const pending = this.waiting.get(msg.id);
      if (!pending) return;
      this.waiting.delete(msg.id);
      msg.error ? pending.reject(new Error(JSON.stringify(msg.error)))
                : pending.resolve(msg.result);
    });
  }
  send(method, params = {}) {
    const id = this.next++;
    return new Promise((resolve, reject) => {
      this.waiting.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.waiting.delete(id)) reject(new Error(`${method} timed out`));
      }, 30000);
    });
  }
  async run(expression) {
    const out = await this.send("Runtime.evaluate",
      { expression, awaitPromise: true, returnByValue: true });
    if (out.exceptionDetails) {
      throw new Error(out.exceptionDetails.exception?.description
                      || out.exceptionDetails.text);
    }
    return out.result.value;
  }
}

async function connect() {
  if (!CHROME) throw new Error("No Chrome or Edge found.");
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "gaius-measure-"));
  const child = spawn(CHROME, [
    "--headless=new", `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`, "--disable-gpu", "--hide-scrollbars",
    "--no-first-run", "--no-default-browser-check",
    `--window-size=${WIDTH},1000`, "about:blank",
  ], { stdio: "ignore" });

  let listed = null;
  for (let i = 0; i < 60; i++) {
    try {
      listed = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      if (listed.some((t) => t.type === "page")) break;
    } catch { /* not up yet */ }
    await sleep(250);
  }
  const page = (listed || []).find((t) => t.type === "page");
  if (!page) throw new Error("Chrome exposed no page.");

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.addEventListener("open", res); ws.addEventListener("error", rej);
  });
  const browser = new Browser(ws);
  await browser.send("Page.enable");
  await browser.send("Runtime.enable");
  await browser.send("Emulation.setDeviceMetricsOverride",
    { width: WIDTH, height: 1000, deviceScaleFactor: 1, mobile: false });
  return { browser, child, profile };
}

const MEASURE = `
(function () {
  const out = [];
  document.querySelectorAll(".panel").forEach((panel, n) => {
    const style = getComputedStyle(panel);
    const inner = panel.clientWidth
      - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
    panel.querySelectorAll("p, li, .intro, .lede, .small").forEach((node) => {
      const text = (node.textContent || "").trim();
      if (text.length < 40) return;              // labels are not prose
      if (node.closest("table")) return;         // cells have their own rules
      const rect = node.getBoundingClientRect();
      if (!rect.width) return;                   // hidden
      /* Against its own container, not against the card.

         Comparing everything to the panel reported a fieldset's own padding
         as a fault — the paragraphs inside a bordered group are 30px
         narrower than the card and correctly so. What is being looked for is
         a block that stops short of the box it is actually in. */
      const parent = node.parentElement;
      const box = getComputedStyle(parent);
      const room = parent.clientWidth
        - parseFloat(box.paddingLeft) - parseFloat(box.paddingRight);
      out.push({
        panel: n,
        card: Math.round(inner),
        width: Math.round(rect.width),
        short: Math.round(room - rect.width),
        cls: node.className || node.tagName.toLowerCase(),
        text: text.slice(0, 44).replace(/\\s+/g, " "),
      });
    });
  });
  return out;
})();`;

async function main() {
  const { browser, child, profile } = await connect();
  try {
    await browser.send("Page.navigate", { url: BASE + "/" });
    await sleep(1200);
    await browser.run(`
      localStorage.setItem("scdes.registration", ${JSON.stringify(
        JSON.stringify({ email: HARNESS_EMAIL, name: "Automated walk",
          verified: true, state: "SC", agency: HARNESS_AGENCY,
          abbrev: "HARNESS" }))});
      localStorage.setItem("scdes.welcomeSeen", "1");
      localStorage.setItem("scdes.tour", "seen");
      localStorage.setItem("scdes.portal", "government");
      localStorage.setItem("scdes.mode", "light");
      true;`);
    await browser.send("Page.navigate", { url: BASE + "/" });
    for (let i = 0; i < 60; i++) {
      if (!await browser.run("document.body.classList.contains('booting')")) break;
      await sleep(300);
    }
    await browser.run("window.closeLauncher && window.closeLauncher(); true;");
    await sleep(800);
    await browser.run(`window.go(${JSON.stringify(VIEW)}); true;`);
    await sleep(1600);

    const found = await browser.run(MEASURE);
    const byPanel = new Map();
    for (const row of found) {
      if (!byPanel.has(row.panel)) byPanel.set(row.panel, []);
      byPanel.get(row.panel).push(row);
    }

    console.log(`viewport ${WIDTH}px · view "${VIEW}" · ${found.length} blocks`
                + ` of prose in ${byPanel.size} card(s)\n`);

    /* One fault, measured one way: a block that stops short of the box it is
       actually in. With `short` measured against each block's own container,
       raggedness between siblings falls out of the same number — two
       paragraphs in one box cannot wrap differently unless at least one of
       them stops short of it. */
    let marooned = 0;
    for (const [panel, rows] of byPanel) {
      console.log(`card ${panel} — ${rows[0].card}px wide`);
      for (const row of rows) {
        const flag = row.short > SLACK ? ` <-- stops ${row.short}px short` : "";
        if (row.short > SLACK) marooned++;
        console.log(`  ${String(row.width).padStart(4)}px  `
                    + `${row.cls.padEnd(18).slice(0, 18)}  ${row.text}${flag}`);
      }
      console.log();
    }

    console.log(`blocks stopping short of their container : ${marooned}`);
    if (marooned) {
      console.log("\nFAIL — prose does not fill the box it sits in");
      process.exit(1);
    }
    console.log("\nPASS — every block of prose fills the box it sits in");
  } finally {
    try { child.kill(); } catch { /* gone */ }
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch { /* held */ }
  }
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
