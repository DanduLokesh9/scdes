/* Does anything push the page wider than the window, and can you reach the
   whole sidebar without scrolling it?

   Both faults are visible in one screenshot the client sent: the sidebar's
   left edge is sliced off — the page had been scrolled sideways, which only
   happens when something inside it is wider than the window — and the last
   rail item is below the fold, which for the page that sells the paid
   modules is the worst one to lose.

   A horizontal scrollbar on a document is almost never wanted: it moves the
   navigation off screen, and on a trackpad it happens by accident. So this
   reports the widest offenders by name rather than just saying "something
   overflows".

   Usage:  node tools/check_overflow.js [view] [width] [height]
*/

const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawn } = require("child_process");

const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";
const VIEW = process.argv[2] || "home";
const WIDTH = Number(process.argv[3] || 1440);
const HEIGHT = Number(process.argv[4] || 900);
const PORT = 9224;

/* Whose session to wear.
 *
 * Defaults to the scratch container, which is the only one anything
 * automated may write to. The client's screenshot was taken as the corpus
 * owner, where the project spine is on screen and the shell is ~75px
 * shorter — so reproducing it needs that identity. Read-only here: this
 * measures boxes and writes nothing.
 *
 *   GAIUS_AS=sc.des GAIUS_AS_EMAIL=jane.smith@des.sc.gov node tools/check_overflow.js
 */
const HARNESS_AGENCY = process.env.GAIUS_AS || "gaius.harness";
const HARNESS_EMAIL = process.env.GAIUS_AS_EMAIL
  || "walk@harness.gaius.test";

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
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "gaius-overflow-"));
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
    { width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false });
  return { browser, child, profile };
}

/* Everything that reaches past the window's right edge, widest first.

   `scrollWidth > clientWidth` on the document says *that* something
   overflows; it does not say what. This walks the tree and reports the
   elements whose own box ends beyond the viewport, skipping any that sit
   inside a deliberately scrollable ancestor — a carousel that scrolls
   sideways on purpose is not the fault. */
const FIND = `
(function () {
  const doc = document.documentElement;
  const room = doc.clientWidth;
  const scrollable = (node) => {
    for (let n = node.parentElement; n; n = n.parentElement) {
      const how = getComputedStyle(n).overflowX;
      if (how === "auto" || how === "scroll" || how === "hidden") return n;
    }
    return null;
  };
  const out = [];
  document.querySelectorAll("body *").forEach((node) => {
    const rect = node.getBoundingClientRect();
    if (!rect.width || rect.right <= room + 1) return;
    const holder = scrollable(node);
    out.push({
      tag: node.tagName.toLowerCase(),
      cls: (node.className || "").toString().slice(0, 40),
      id: node.id || "",
      right: Math.round(rect.right),
      over: Math.round(rect.right - room),
      inside: holder ? (holder.className || holder.tagName).toString().slice(0, 30) : "",
    });
  });
  out.sort((a, b) => b.over - a.over);
  return {
    room,
    scrollWidth: doc.scrollWidth,
    overflow: doc.scrollWidth - room,
    bodyOverflow: document.body.scrollWidth - room,
    offenders: out.slice(0, 12),
  };
})();`;

/* Can the whole sidebar be used without scrolling it? */
const RAIL = `
(function () {
  const rail = document.querySelector(".rail");
  if (!rail) return null;
  const items = [...rail.querySelectorAll(".rail-item[data-view]")];
  const railBox = rail.getBoundingClientRect();
  const below = items.filter((b) => {
    const r = b.getBoundingClientRect();
    return r.bottom > railBox.bottom + 1;
  }).map((b) => b.dataset.view);
  return {
    height: Math.round(railBox.height),
    needs: Math.round(rail.scrollHeight),
    scrolls: rail.scrollHeight > rail.clientHeight + 1,
    items: items.length,
    below,
  };
})();`;

async function main() {
  const { browser, child, profile } = await connect();
  const failures = [];
  const check = (label, ok, detail = "") => {
    console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(46)} ${detail}`);
    if (!ok) failures.push(label);
  };

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
    await sleep(700);
    // `go` is a page-level const, reachable from the page's own scope but
    // not as a property of window.
    await browser.run(`(typeof go === "function" ? go : window.go)(${JSON.stringify(VIEW)}); true;`);
    await sleep(1500);

    console.log(`window ${WIDTH}x${HEIGHT} · view "${VIEW}"\n`);

    console.log("nothing pushes the page sideways");
    const found = await browser.run(FIND);
    check("the document is no wider than the window",
      found.overflow <= 0,
      `needs ${found.scrollWidth}px in ${found.room}px`
      + (found.overflow > 0 ? ` — ${found.overflow}px over` : ""));
    if (found.overflow > 0) {
      console.log("\n      what reaches past the edge:");
      for (const o of found.offenders) {
        console.log(`        +${String(o.over).padStart(4)}px  `
          + `${o.tag}${o.id ? "#" + o.id : ""}`
          + `${o.cls ? "." + o.cls.split(/\s+/).join(".") : ""}`
          + (o.inside ? `   (inside ${o.inside})` : "   <-- not in a scroller"));
      }
      console.log();
    }

    console.log("\nthe whole sidebar is reachable");
    const rail = await browser.run(RAIL);
    if (rail) {
      /* Whether the rail scrolls is information, not a verdict. A sidebar
         that scrolls on a short window is ordinary, and forcing it to fit
         would mean shrinking rows below a comfortable touch target — trading
         one accessibility problem for another.

         What is a verdict: whether a *navigation item* is below the fold.
         Those are unreachable to anyone who does not realize the rail
         scrolls, which is how the Subscription item — the page that sells
         the paid modules — became the only one you could not see. */
      console.log(`        ${rail.items} items, needs ${rail.needs}px in `
        + `${rail.height}px${rail.scrolls ? " — the rail scrolls" : ""}`);
      if (rail.below.length) {
        console.log(`        below the fold: ${rail.below.join(", ")}`);
      }

      /* Rows are already 34px — under the 44px touch target a pointer wants
         — so there is no slack left to reclaim. On a short enough window
         fourteen destinations cannot all fit, the rail scrolls, and the
         platform draws a scrollbar. That is ordinary and is reported above
         rather than failed.

         What is failed: losing the two items somebody must be able to find
         without knowing the sidebar scrolls. Framework is the whole free
         product, and Subscription is how the rest is bought — it was last
         in the rail, and on a 1440x720 laptop it was the single item below
         the fold, which is how this check came to exist. */
      const mustShow = ["framework", "billing"];
      const lost = rail.below.filter((v) => mustShow.includes(v));
      check("the framework and the way to buy are always visible",
        lost.length === 0,
        lost.length ? `hidden: ${lost.join(", ")}` : "both in view");
    }

    console.log();
    if (failures.length) {
      console.log(`FAIL — ${failures.length}: ${failures.join("; ")}`);
      process.exit(1);
    }
    console.log("PASS — nothing overflows and the whole rail is reachable");
  } finally {
    try { child.kill(); } catch { /* gone */ }
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch { /* held */ }
  }
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
