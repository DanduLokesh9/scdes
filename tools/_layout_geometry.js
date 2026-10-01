/* Where does each column of the shell actually sit, and what is in the gap?

   The client marked an empty band down the right-hand side of the window and
   asked for the side panel to be expanded into it. Two different things could
   produce that band — the reason panel being collapsed or hidden, or the
   content measure leaving dead space inside a wider column — and they need
   opposite fixes. So this reports the geometry rather than guessing from a
   screenshot.

   Usage:  node tools/_layout_geometry.js [view] [width] [height]
           GAIUS_AS=sc.des GAIUS_AS_EMAIL=jane.smith@des.sc.gov ...
*/

const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawn } = require("child_process");

const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";
const VIEW = process.argv[2] || "home";
const WIDTH = Number(process.argv[3] || 1440);
const HEIGHT = Number(process.argv[4] || 780);
const PORT = 9225;

const AGENCY = process.env.GAIUS_AS || "gaius.harness";
const EMAIL = process.env.GAIUS_AS_EMAIL || "walk@harness.gaius.test";

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
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "gaius-geom-"));
  const child = spawn(CHROME, [
    "--headless=new", `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`, "--disable-gpu",
    "--no-first-run", "--no-default-browser-check",
    `--window-size=${WIDTH},${HEIGHT}`, "about:blank",
  ], { stdio: "ignore" });
  let listed = null;
  for (let i = 0; i < 60; i++) {
    try {
      listed = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      if (listed.some((t) => t.type === "page")) break;
    } catch { /* not up */ }
    await sleep(250);
  }
  const page = (listed || []).find((t) => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((res, rej) => {
    ws.addEventListener("open", res); ws.addEventListener("error", rej);
  });
  const browser = new Browser(ws);
  await browser.send("Page.enable");
  await browser.send("Runtime.enable");
  await browser.send("Emulation.setDeviceMetricsOverride",
    { width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false });
  return { browser, child, profile };
}

const GEOMETRY = `
(function () {
  const box = (sel) => {
    const n = document.querySelector(sel);
    if (!n) return { sel, missing: true };
    const r = n.getBoundingClientRect();
    const s = getComputedStyle(n);
    return {
      sel,
      left: Math.round(r.left), right: Math.round(r.right),
      width: Math.round(r.width),
      display: s.display, visibility: s.visibility,
      maxWidth: s.maxWidth,
      classes: (n.className || "").toString().slice(0, 40),
    };
  };
  const shell = document.querySelector(".shell");
  const widest = [...document.querySelectorAll("#view .panel")]
    .reduce((w, p) => Math.max(w, Math.round(p.getBoundingClientRect().right)), 0);
  return {
    window: document.documentElement.clientWidth,
    columns: shell ? getComputedStyle(shell).gridTemplateColumns : "(no shell)",
    rail: box(".rail"),
    record: box(".record"),
    view: box("#view"),
    reason: box(".reason"),
    contentEndsAt: widest,
  };
})();`;

async function main() {
  const { browser, child, profile } = await connect();
  try {
    await browser.send("Page.navigate", { url: BASE + "/" });
    await sleep(1200);
    await browser.run(`
      localStorage.setItem("scdes.registration", ${JSON.stringify(
        JSON.stringify({ email: EMAIL, name: "Automated walk", verified: true,
          state: "SC", agency: AGENCY, abbrev: "HARNESS" }))});
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
    await sleep(700);
    await browser.run(`window.go(${JSON.stringify(VIEW)}); true;`);
    await sleep(1500);

    const g = await browser.run(GEOMETRY);
    console.log(`window ${WIDTH}x${HEIGHT} · view "${VIEW}" · as ${AGENCY}\n`);
    console.log(`grid columns : ${g.columns}`);
    for (const key of ["rail", "record", "view", "reason"]) {
      const b = g[key];
      if (b.missing) { console.log(`${key.padEnd(13)}: MISSING`); continue; }
      console.log(`${key.padEnd(13)}: ${String(b.left).padStart(4)} → `
        + `${String(b.right).padStart(4)}   ${String(b.width).padStart(4)}px`
        + `   display:${b.display}  max-width:${b.maxWidth}`);
    }
    console.log(`\ncontent ends : ${g.contentEndsAt}px`);
    const dead = g.window - g.contentEndsAt;
    console.log(`empty to the right of the last panel : ${dead}px`);
    if (g.reason && !g.reason.missing && g.reason.display !== "none") {
      console.log(`  of which the reason panel occupies : ${g.reason.width}px`);
      console.log(`  unaccounted for                    : `
        + `${dead - g.reason.width}px`);
    } else {
      console.log("  the reason panel is not displayed, so all of it is dead");
    }
  } finally {
    try { child.kill(); } catch { /* gone */ }
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch { /* held */ }
  }
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
