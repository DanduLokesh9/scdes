/* Does the Framework screen actually let you build a framework?

   It used to open on a status page — four layers, which files are present,
   record an adoption when it happens. Useful once you have a framework, useless
   on the day you are writing one. This drives the real screen: opens Framework,
   walks into a section, answers a question, and checks it stuck.

   Usage:  node tools/check_builder.js
           GAIUS_BASE=https://app.staging.governingai.us node tools/check_builder.js
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";

function store(seed = {}) {
  const d = { ...seed };
  return { getItem: (k) => (k in d ? d[k] : null),
           setItem: (k, v) => { d[k] = String(v); },
           removeItem: (k) => { delete d[k]; } };
}

async function boot() {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  window.fetch = async (url, opts) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url, opts);
    return { json: () => r.json(), ok: r.ok };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage", {
    value: store({ "scdes.registration": JSON.stringify(
      { email: "lokesh@iiac.ai", verified: true, tester: true }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
      "scdes.portal": "government" }), writable: true });
  Object.defineProperty(window, "sessionStorage", { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });
  // jsdom has neither, and dictationSupported() checks for both before it
  // offers anything. Faked so the control renders; nothing is recorded here.
  Object.defineProperty(window.navigator, "mediaDevices", {
    value: { getUserMedia: async () => ({ getTracks: () => [] }) },
    configurable: true });
  window.MediaRecorder = function () {};
  if (!window.WebAssembly) window.WebAssembly = globalThis.WebAssembly || {};
  if (!window.Worker) window.Worker = function () {};

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  window.onunhandledrejection = (e) => errors.push("unhandled: " + e.reason);
  window.console = { ...console, log: () => {},
    error: (...a) => errors.push(a.map(String).join(" ")),
    warn: () => {} };

  for (const f of ["onboard.js", "welcome.js", "tour.js", "launcher.js",
                   "speech.js", "builder.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f} threw at load: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 80; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  if (window.closeLauncher) window.closeLauncher();
  // Sign in, as the real flow does. An agency's first registrant holds the
  // Office of Technology capacity — framework answers are OT's to give, and
  // without this the harness posts as an operator and every save is refused.
  if (window.signInAs) await window.signInAs("sean.ot", "Test Person", "CTO");
  await new Promise((r) => setTimeout(r, 900));
  return { window, errors };
}

const click = (el, w) =>
  el && el.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));

async function main() {
  const { window, errors } = await boot();
  const doc = window.document;

  window.go("framework");
  await new Promise((r) => setTimeout(r, 1500));

  console.log("supported here    :", window.dictationSupported());
  const toggle = doc.getElementById("fbDictate");
  console.log("switch present    :", !!toggle);
  console.log("off by default    :", toggle && !toggle.checked);

  const open = [...doc.querySelectorAll(".fb-section")].find((s) => !s.disabled);
  open.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 1000));
  console.log("mics while off    :", doc.querySelectorAll(".dictate").length,
              "(should be 0)");

  window.setDictation(true);
  window.go("framework");
  await new Promise((r) => setTimeout(r, 1200));
  const again = [...doc.querySelectorAll(".fb-section")].find((s) => !s.disabled);
  again.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 1000));
  const mics = doc.querySelectorAll(".dictate");
  console.log("mics while on     :", mics.length,
              "on", doc.querySelectorAll("textarea").length, "textareas");
  console.log("button label      :",
    mics[0] && mics[0].querySelector(".dictate-btn").textContent.trim());
  console.log("errors            :", errors.length || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));
}

main().catch((e) => { console.error(e); process.exit(1); });
