/* Real screenshots of the real interface, for the user guide.

   Why this exists rather than a folder of hand-cropped images: a manual whose
   pictures were taken once goes stale the first time a heading changes, and
   nobody notices until a user follows a step that is not there any more. This
   drives an actual browser against an actual server, so re-running it is how
   the guide stays true.

   It also draws the numbered callouts. Those are positioned from the live DOM
   by CSS selector, so a badge cannot end up pointing at empty space — if the
   element is gone, the run says so instead of producing a confident arrow to
   nothing.

   No dependencies. Node 24 has fetch and WebSocket built in, and Chrome
   speaks CDP over one — which is the whole of a screenshot tool.

   Usage:
       $env:IIA_SUBSCRIPTION = "1"     # on the server being shot
       node tools/shots.js

   Writes docs/img/*.png and refuses to run anywhere but the scratch tenant.
*/

const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawn } = require("child_process");

const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";
const OUT = path.join(__dirname, "..", "docs", "img");
const PORT = 9222;

const HARNESS_AGENCY = "gaius.harness";
const HARNESS_EMAIL = "walk@harness.gaius.test";

/* What the header says. The container underneath is the scratch tenant — the
   only one anything automated is allowed to write to — but a manual cannot
   show a real agency's name without implying that agency is a customer, and
   it cannot show "TEST — automated checks only" without looking broken. So
   the guide is illustrated with a placeholder, and says so on its first
   page. */
const SHOWN_AS = "Example County";
const SHOWN_ABBREV = "EXAMPLE";

const CHROME = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
].find((p) => fs.existsSync(p));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ------------------------------------------------------------------ the wire

class Browser {
  constructor(ws) {
    this.ws = ws;
    this.next = 1;
    this.waiting = new Map();
    this.ws.addEventListener("message", (e) => {
      const msg = JSON.parse(e.data);
      if (msg.id && this.waiting.has(msg.id)) {
        const { resolve, reject } = this.waiting.get(msg.id);
        this.waiting.delete(msg.id);
        msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
      }
    });
  }

  send(method, params = {}) {
    const id = this.next++;
    return new Promise((resolve, reject) => {
      this.waiting.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
      setTimeout(() => {
        if (this.waiting.has(id)) {
          this.waiting.delete(id);
          reject(new Error(`${method} timed out`));
        }
      }, 45000);
    });
  }

  /** Run an expression in the page and hand back its value. */
  async run(expression) {
    const out = await this.send("Runtime.evaluate", {
      expression, awaitPromise: true, returnByValue: true,
    });
    if (out.exceptionDetails) {
      throw new Error(out.exceptionDetails.exception?.description
                      || out.exceptionDetails.text);
    }
    return out.result.value;
  }
}

async function connect() {
  if (!CHROME) throw new Error("No Chrome or Edge found.");
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "gaius-shots-"));
  const child = spawn(CHROME, [
    "--headless=new", `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${profile}`, "--disable-gpu", "--hide-scrollbars",
    "--no-first-run", "--no-default-browser-check",
    "--window-size=1440,1000", "about:blank",
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
  if (!page) throw new Error("Chrome started but exposed no page.");

  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve);
    ws.addEventListener("error", reject);
  });
  const browser = new Browser(ws);
  await browser.send("Page.enable");
  await browser.send("Runtime.enable");
  await browser.send("Emulation.setDeviceMetricsOverride", {
    width: 1440, height: 1000, deviceScaleFactor: 2, mobile: false,
  });
  return { browser, child, profile };
}

// ------------------------------------------------------------- the data shown

const auth = `user=sean.ot&email=${encodeURIComponent(HARNESS_EMAIL)}`;
const api = async (p) => (await fetch(`${BASE}${p}?${auth}`)).json();
const post = (p, body) => fetch(`${BASE}${p}?${auth}`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body) }).then((r) => r.json());

async function demandScratchContainer() {
  const url = `${BASE}/api/whose-container?email=${encodeURIComponent(HARNESS_EMAIL)}`;
  let found = await (await fetch(url)).json();
  if (!found.safe_to_overwrite) {
    await fetch(`${BASE}/api/agency/register`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agency: HARNESS_AGENCY, name: "Automated walk",
        title: "Harness", email: HARNESS_EMAIL,
        phone: "(843) 555 0100", attested: true }) });
    found = await (await fetch(url)).json();
  }
  if (!found.safe_to_overwrite) {
    console.error(`\n  Refusing to run — writes would land in ${found.agency}.\n`);
    process.exit(2);
  }
}

/* A small, plausible set of entries, so the guide shows a working register
   rather than five empty tables. Everything here is invented. */
async function seed() {
  for (const row of (await api("/api/holdings")).holdings || []) {
    await post("/api/holdings/forget", { id: row.id });
  }
  for (const row of (await api("/api/vendors")).vendors || []) {
    await post("/api/vendors/forget", { id: row.id });
  }

  const answers = {
    "org.kind": "county",
    "data.never": ["personal", "medical", "personnel"],
    "data.where": "partly",
    "proc.terms": ["disclose", "notice", "accuracy", "audit", "return",
                   "breach", "accessibility"],
    "proc.full_cost": "yes",
    "proc.cost_parts": ["licence", "setup", "training", "staff_time", "exit"],
    "proc.added_ai": "as_new",
    "proc.reuse": "yes",
  };
  for (const [key, value] of Object.entries(answers)) {
    await post("/api/versions/answer", { key, value });
  }

  const holdings = [
    { name: "Permit system", contains: "Every permit application, decision "
        + "and inspection since 2009", purpose: "Issuing and tracking permits",
      format: "structured", location: "gov_cloud", system: "PermitPro",
      owner: "The Permitting Manager", reachable: "api",
      endpoint: "https://example.com/permits/v1",
      auth: "An API key issued by IT", freshness: "live",
      sensitive: ["personal"] },
    { name: "The K drive", contains: "Twenty years of letters, reports and "
        + "spreadsheets", purpose: "Wherever staff put things",
      format: "mixed", location: "onprem", system: "File server",
      owner: "", reachable: "screen", freshness: "unknown",
      sensitive: ["personal", "personnel"] },
    { name: "Scanned inspection files", contains: "Paper inspection reports, "
        + "1994 to 2009", purpose: "Records retention and public requests",
      format: "scanned", location: "unknown", owner: "The Records Officer",
      reachable: "export", freshness: "static" },
  ];
  const ids = {};
  for (const h of holdings) {
    const saved = await post("/api/holdings", h);
    ids[h.name] = saved.holding?.id;
  }
  // One check, so the monitor column is not all "not checked yet".
  if (ids["Permit system"]) {
    await post("/api/holdings/check", { id: ids["Permit system"] });
  }

  const vendors = [
    { name: "Northbridge Software", product: "CaseNote",
      what_for: "Summarizing inspection reports for the weekly review",
      could_also: "Drafting standard letters, and searching across old reports",
      status: "in_use", involvement: "core", owner: "The Permitting Manager",
      amount: "41500", basis: "year", contract: "PO-2024-118",
      renewal: nextMonth(45), criticality: "low", facing: "internal",
      training: "no", accessibility: "report",
      terms: ["disclose", "notice", "accuracy", "return", "accessibility"],
      costed: ["licence", "setup", "training"],
      holdings: [ids["Permit system"]].filter(Boolean) },
    { name: "Ridgeline Analytics", product: "Constituent Assist",
      what_for: "Answering questions on the county website",
      could_also: "Call transcription, and translating published notices",
      status: "pilot", involvement: "core", owner: "The Communications Lead",
      amount: "18", basis: "per_user", criticality: "low", facing: "public",
      training: "opt_out", accessibility: "unknown",
      terms: ["disclose", "accuracy"], costed: ["licence"],
      holdings: [] },
    { name: "Harborline Systems", product: "Records Manager",
      what_for: "Storing and retrieving scanned records",
      could_also: "Automatic redaction of personal details before release",
      status: "in_use", involvement: "added", owner: "The Records Officer",
      amount: "9600", basis: "year", contract: "PO-2022-041",
      renewal: nextMonth(210), criticality: "high", facing: "internal",
      training: "unknown", accessibility: "claimed",
      terms: ["disclose", "notice", "accuracy", "audit", "return", "breach",
              "accessibility"],
      costed: ["licence", "setup", "training", "staff_time", "exit"],
      holdings: [ids["Scanned inspection files"]].filter(Boolean) },
  ];
  for (const v of vendors) await post("/api/vendors", v);
}

function nextMonth(days) {
  const when = new Date(Date.now() + days * 86400000);
  return when.toISOString().slice(0, 10);
}

// -------------------------------------------------------------- the shooting

const MARKER = `
window.__mark = function (selector, n, side) {
  const target = document.querySelector(selector);
  if (!target) return false;
  const rect = target.getBoundingClientRect();
  const badge = document.createElement("div");
  badge.className = "__shotmark";
  badge.textContent = String(n);
  Object.assign(badge.style, {
    position: "fixed", zIndex: 99999,
    width: "26px", height: "26px", borderRadius: "50%",
    background: "#b3261e", color: "#fff", font: "700 15px/26px system-ui",
    textAlign: "center", boxShadow: "0 1px 6px rgba(0,0,0,.4)",
    top: (rect.top + (side === "top" ? -13 : rect.height / 2 - 13)) + "px",
    left: (rect.left - 13) + "px",
  });
  document.body.appendChild(badge);
  const ring = document.createElement("div");
  ring.className = "__shotmark";
  Object.assign(ring.style, {
    position: "fixed", zIndex: 99998, pointerEvents: "none",
    border: "2px solid #b3261e", borderRadius: "8px",
    top: (rect.top - 4) + "px", left: (rect.left - 4) + "px",
    width: (rect.width + 8) + "px", height: (rect.height + 8) + "px",
  });
  document.body.appendChild(ring);
  return true;
};
window.__unmark = function () {
  document.querySelectorAll(".__shotmark").forEach((n) => n.remove());
};
true;`;

/* The placeholder name, reapplied after every navigation because the shell
   repaints the header from the registry each time. `Runtime.evaluate` runs in
   the page's global scope, so this is a function rather than a repeated block
   of `const` declarations — the second one was a redeclaration error. */
function relabel(browser) {
  return browser.run(`
    (function () {
      const el = document.getElementById("agencyShort");
      if (el) el.textContent = ${JSON.stringify(SHOWN_ABBREV)};
      const crumb = document.getElementById("agencyCrumb");
      if (crumb) crumb.textContent = ${JSON.stringify(SHOWN_AS)};
      return true;
    })();`);
}

async function openApp(browser) {
  await browser.send("Page.navigate", { url: BASE + "/" });
  await sleep(1200);
  await browser.run(`
    localStorage.setItem("scdes.registration", ${JSON.stringify(
      JSON.stringify({ email: HARNESS_EMAIL, name: "Dana Reed",
        verified: true, state: "SC", agency: HARNESS_AGENCY,
        title: "Chief of Staff",
        agencyName: SHOWN_AS, abbrev: SHOWN_ABBREV }))});
    localStorage.setItem("scdes.welcomeSeen", "1");
    localStorage.setItem("scdes.tour", "seen");
    localStorage.setItem("scdes.portal", "government");
    localStorage.setItem("scdes.mode", "light");
    true;`);
  await browser.send("Page.navigate", { url: BASE + "/" });
  for (let i = 0; i < 60; i++) {
    const booting = await browser.run(
      "document.body.classList.contains('booting')");
    if (!booting) break;
    await sleep(300);
  }
  await browser.run("window.closeLauncher && window.closeLauncher(); true;");
  await sleep(900);
  // The header is painted from the registry, which knows this container by
  // its real name. Replaced for the guide, and stated on the guide's cover.
  await browser.run(MARKER);
  await relabel(browser);
}

const WIDE = 1440;
const TALL = 1000;

function metrics(browser, height) {
  return browser.send("Emulation.setDeviceMetricsOverride", {
    width: WIDE, height, deviceScaleFactor: 2, mobile: false,
  });
}

function rectOf(browser, selector) {
  return browser.run(`
    (function () {
      const t = document.querySelector(${JSON.stringify(selector)});
      if (!t) return null;
      const r = t.getBoundingClientRect();
      return { x: r.left, y: r.top, width: r.width, height: r.height };
    })();`);
}

async function shoot(browser, name, { view, marks = [], focus = "",
                                      scrollTo = "", pad = 18,
                                      padTop = 4, maxHeight = 0 } = {}) {
  if (view) {
    await browser.run(`window.go(${JSON.stringify(view)}); true;`);
    await sleep(1400);
    await relabel(browser);
  }
  await browser.run("window.__unmark(); true;");

  /* A panel taller than the window would be cropped at the fold, and a
     screenshot of the top half of a form is worse than none — a reader
     follows it, reaches the bottom of the picture and assumes that is the end
     of the form. So the window is grown to fit the thing being photographed,
     and put back afterward. */
  let grown = false;
  const target = focus || scrollTo;
  if (target) {
    const first = await rectOf(browser, target);
    if (first && first.height > TALL - 160) {
      await metrics(browser, Math.min(Math.ceil(first.height) + 200, 4200));
      grown = true;
      await sleep(500);
    }
  }

  const where = scrollTo || focus;
  if (where) {
    const found = await browser.run(`
      (function () {
        const t = document.querySelector(${JSON.stringify(where)});
        if (!t) return false;
        t.scrollIntoView({ block: "start" });
        return true;
      })();`);
    if (!found) console.log(`      ! nothing matched ${where}`);
    await sleep(500);
  }

  // After the resize and the scroll, because the badges are positioned from
  // where things actually ended up.
  for (const [selector, n, side] of marks) {
    const ok = await browser.run(
      `window.__mark(${JSON.stringify(selector)}, ${n}, ${
        JSON.stringify(side || "middle")});`);
    if (!ok) console.log(`      ! callout ${n} found no ${selector}`);
  }

  let clip;
  if (focus) {
    const rect = await rectOf(browser, focus);
    if (rect) {
      const height = await browser.run("window.innerHeight");
      /* `maxHeight` cuts a long panel off deliberately. The vendor form is
         3,694 pixels tall, which on a printed page comes out either taller
         than the page or shrunk to the width of a postcard. The parts below
         the cut have pictures of their own, so this shows the top and the
         guide's caption says so. */
      const want = rect.height + padTop + pad;
      clip = {
        x: Math.max(0, rect.x - pad),
        // Only a hair above the panel. A full pad of headroom reached up into
        // the sticky header and put a stripe of it across every picture.
        y: Math.max(0, rect.y - padTop),
        width: Math.min(WIDE, rect.width + pad * 2),
        height: Math.min(height, maxHeight ? Math.min(want, maxHeight) : want),
        scale: 1,
      };
    } else {
      console.log(`      ! nothing matched ${focus} — full frame instead`);
    }
  }

  const shot = await browser.send("Page.captureScreenshot",
    { format: "png", ...(clip ? { clip } : {}) });
  fs.writeFileSync(path.join(OUT, `${name}.png`),
                   Buffer.from(shot.data, "base64"));
  console.log(`  ${name}.png`);

  if (grown) {
    await metrics(browser, TALL);
    await sleep(300);
  }
}

// ------------------------------------------------------------------ the plan

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  await demandScratchContainer();
  console.log("seeding the example entries");
  await seed();

  const { browser, child, profile } = await connect();
  try {
    await openApp(browser);
    console.log("\ntaking the pictures");

    // The whole window, so the header and the command bar are in it.
    await shoot(browser, "01-shell", {
      view: "home",
      marks: [['.rail-item[data-view="framework"]', 1],
              ['.rail-item[data-view="holdings"]', 2],
              ['.rail-item[data-view="vendors"]', 3],
              ["#cmdkBtn", 4, "top"],
              ["#reason", 5, "top"]],
    });

    await shoot(browser, "02-framework", {
      view: "framework", focus: "#view > div > .panel:nth-of-type(1)",
    });

    await shoot(browser, "03-data-top", {
      view: "holdings",
      marks: [[".dh-tiles", 1, "top"]],
      focus: "#view > div > .panel:nth-of-type(1)",
    });

    await shoot(browser, "04-data-findings", {
      marks: [[".dh-flags", 1, "top"]],
      focus: "#view > div > .panel:nth-of-type(2)",
    });

    await shoot(browser, "05-data-monitor", {
      marks: [["#dhSweep", 1]],
      focus: "#view > div > .panel:nth-of-type(3)",
    });

    // One badge, not two: Edit and Check sit side by side and the rings
    // landed on top of each other. The word in the endpoint column is the
    // part that needs pointing at.
    await shoot(browser, "06-data-table", {
      marks: [[".dh-state", 1, "top"]],
      focus: "#view > div > .panel:nth-of-type(4)",
    });

    await shoot(browser, "07-data-form", {
      marks: [["#dh-name", 1], ["#dh-reachable", 2], ["#dh-endpoint", 3],
              ["#dhSave", 4]],
      focus: "#dhForm",
    });

    await shoot(browser, "08-data-sensitive", {
      marks: [[".dh-sens", 1, "top"]],
      focus: ".dh-sens",
    });

    await shoot(browser, "09-vendors-top", {
      view: "vendors",
      marks: [[".vr-tiles", 1, "top"]],
      focus: "#view > div > .panel:nth-of-type(1)",
    });

    await shoot(browser, "10-vendors-findings", {
      focus: "#view > div > .panel:nth-of-type(2)",
    });

    await shoot(browser, "11-vendors-renewals", {
      focus: "#view > div > .panel:nth-of-type(3)",
    });

    await shoot(browser, "12-vendors-potential", {
      focus: "#view > div > .panel:nth-of-type(4)",
    });

    await shoot(browser, "13-vendors-table", {
      focus: "#view > div > .panel:nth-of-type(5)",
    });

    // The top of the form only — the three fieldsets below it are shot
    // separately, and the whole thing at once is taller than a printed page.
    await shoot(browser, "14-vendors-form", {
      marks: [["#vn-name", 1], ["#vn-amount", 2], ["#vn-basis", 3]],
      focus: "#vnForm", maxHeight: 1150,
    });

    await shoot(browser, "15-vendors-tier", {
      marks: [["#vn-criticality", 1], ["#vn-facing", 2]],
      focus: ".vr-sens",
    });

    await shoot(browser, "16-vendors-terms", {
      focus: "#vnForm .vr-sens:nth-of-type(2)",
    });

    await shoot(browser, "17-vendors-sees", {
      focus: '#vnForm fieldset:has([name="vn-holdings"])',
    });

    await shoot(browser, "20-handoff", {
      view: "framework",
      focus: ".fb-handoff",
    });
    await shoot(browser, "21-billing", {
      view: "billing",
      focus: "#view",
    });
    console.log("\ndone —", OUT);
  } finally {
    try { child.kill(); } catch { /* already gone */ }
    try { fs.rmSync(profile, { recursive: true, force: true }); }
    catch { /* windows holds it briefly */ }
  }
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
