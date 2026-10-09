/* Shared boot for the screen walks: load the real page and its scripts into
   jsdom, signed in as the harness container, against a local server only.

   Every walk that uses this writes records, so it refuses anything but a
   local base — the rule after a walk once posted to staging. */

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";
const HARNESS_AGENCY = "gaius.harness";
const HARNESS_EMAIL = "walk@harness.gaius.test";

function refuseRemote() {
  if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(BASE)) {
    console.error(`\n  Refusing to run against ${BASE} — this walk writes records.\n`);
    process.exit(2);
  }
}

async function demandScratchContainer() {
  // The harness accepts the Terms of Use like anybody else — registering
  // needs it, and so does getting past the agreement when a walk resumes a
  // signed-in session. Idempotent: accepting again records the same version.
  await fetch(`${BASE}/api/terms/accept`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: HARNESS_EMAIL, name: "Automated walk", title: "Harness",
      unit: "GAIUS harness", agency: HARNESS_AGENCY, authority: true, scrolled: true }) });
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

function store(seed = {}) {
  const d = { ...seed };
  return { getItem: (k) => (k in d ? d[k] : null),
           setItem: (k, v) => { d[k] = String(v); },
           removeItem: (k) => { delete d[k]; } };
}

/* A real session for the harness, obtained the way a person gets one: ask for
   a code, read it (the local server shows it), verify. Changes need a proven
   sign-in now (server._proven_session_gate), so a walk that saves anything
   has to be signed in for real. One per process. */
let HARNESS_SESSION = null;
async function harnessSession() {
  if (HARNESS_SESSION) return HARNESS_SESSION;
  const post = (p, b) => fetch(BASE + p, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify(b) }).then((r) => r.json());
  const asked = await post("/api/agency/signin", { email: HARNESS_EMAIL });
  if (!asked.code) throw new Error(`no sign-in code for the harness: ${asked.error || JSON.stringify(asked)}`);
  const done = await post("/api/agency/verify", { email: HARNESS_EMAIL, code: asked.code });
  if (!done.session) throw new Error(`the harness could not verify: ${done.error || JSON.stringify(done)}`);
  HARNESS_SESSION = done.session;
  return HARNESS_SESSION;
}

async function boot({ storage = null, before = null } = {}) {
  refuseRemote();
  await demandScratchContainer();
  const session = storage ? null : await harnessSession();
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  window.fetch = async (url, opts) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url, opts);
    return { json: () => r.json(), ok: r.ok, status: r.status };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  // A walk can start from a fresh browser by passing its own storage — the
  // first-visit screens only show when nothing has been answered yet.
  Object.defineProperty(window, "localStorage", {
    value: store(storage || { "scdes.registration": JSON.stringify(
      { email: HARNESS_EMAIL, name: "Automated walk", verified: true,
        state: "SC", agency: HARNESS_AGENCY, abbrev: "HARNESS",
        // On no state's list, so described as an unlisted unit is — without
        // it a resumed session cannot be placed and the home page shows.
        unlisted: true, agencyName: "GAIUS harness" }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
      "scdes.portal": "government", "scdes.session": session }), writable: true });
  Object.defineProperty(window, "sessionStorage", { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });
  if (!window.CSS) window.CSS = {};
  if (!window.CSS.escape) window.CSS.escape = (s) => String(s).replace(/["\\]/g, "\\$&");

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  // A walk that has to watch something the page does while it boots — before
  // boot() returns — hooks it here, ahead of the page's own scripts.
  if (before) before(window);
  // One evaluation, so the scripts share one scope the way a page does.
  const all = ["bugs.js", "dock.js", "guide.js", "notify.js", "home.js", "onboard.js",
               "welcome.js", "tour.js", "launcher.js", "speech.js",
               "builder.js", "app.js"].map((f) => read(path.join("assets", f)));
  try { window.eval(all.join("\n;\n")); } catch (e) { errors.push(e.message); }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 80; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  if (window.closeLauncher) window.closeLauncher();
  await new Promise((r) => setTimeout(r, 800));
  return { window, errors };
}

const settle = (ms = 500) => new Promise((r) => setTimeout(r, ms));
async function until(condition, ms = 12000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    try { if (await condition()) return true; } catch { /* not yet */ }
    await settle(150);
  }
  return false;
}

function reporter() {
  const failures = [];
  const check = (label, ok, detail = "") => {
    console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(56)} ${detail}`);
    if (!ok) failures.push(label);
  };
  const finish = (errors, passLine) => {
    console.log(`\nerrors             : ${errors.length ? errors.join("; ") : "none"}`);
    if (errors.length) failures.push("script errors");
    console.log();
    if (failures.length) {
      console.log(`FAIL — ${failures.length}: ${failures.slice(0, 4).join("; ")}`);
      process.exit(1);
    }
    console.log(`PASS — ${passLine}`);
    process.exit(0);
  };
  return { check, finish };
}

/* Open a view and wait for text that proves it rendered, retrying go()
   because boot navigation can land after the first call. */
async function openView(window, view, proof) {
  const said = () => window.document.getElementById("view").textContent;
  for (let i = 0; i < 6; i++) {
    await window.go(view);
    if (await until(() => proof.test(said()), 4000)) return true;
  }
  return false;
}

module.exports = { boot, settle, until, reporter, openView, BASE, harnessSession };
