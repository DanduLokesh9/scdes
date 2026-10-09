/* Does voice navigation go where you asked?

   The matching is what makes this usable or infuriating. Whisper-tiny will
   mishear, people phrase things differently, and half the destinations are
   locked behind the subscription — so the interesting cases are not "audit
   trail" working, they are:

     · politeness not changing the answer  ("take me to the audit trail")
     · a locked room being named as locked, not silently ignored
     · an ambiguous or absent match refusing rather than guessing

   Going to the wrong screen is worse than going nowhere, which is why the
   refusals are tested as hard as the matches.

   Usage:  node tools/check_voice.js
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
      { email: "jane.smith@des.sc.gov", verified: true,
        state: "SC", agency: "sc.des", abbrev: "SCDES" }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
      "scdes.portal": "government",
      ...(process.env.VOICE_OFF ? {} : { "scdes.voice": "1" }) }),
    writable: true });
  Object.defineProperty(window, "sessionStorage", { value: store(), writable: true });
  Object.defineProperty(window.navigator, "mediaDevices", {
    value: { getUserMedia: async () => ({ getTracks: () => [] }) },
    configurable: true });
  window.MediaRecorder = function () {};
  if (!window.WebAssembly) window.WebAssembly = globalThis.WebAssembly || {};
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  window.onunhandledrejection = (e) => errors.push("unhandled: " + e.reason);
  for (const f of ["onboard.js", "welcome.js", "tour.js", "launcher.js",
                   "speech.js", "builder.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f}: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 80; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  if (window.closeLauncher) window.closeLauncher();
  if (window.signInAs) await window.signInAs("sean.ot", "Test", "CTO");
  await new Promise((r) => setTimeout(r, 900));
  return { window, errors };
}

const SHOULD_MATCH = [
  ["open the framework", "framework"],
  ["framework", "framework"],
  ["take me to the audit trail", "audit"],
  ["show me the audit log", "audit"],
  ["go to the registry", "registry"],
  ["I want to see the budget", "budget"],
  ["who decides", "council"],
  ["terminology", "setup"],
  ["agency profile", "agency"],
  ["show me oversight", "oversight"],
  ["the lifecycle", "workflow"],
  ["gates", "workflow"],
  ["integrity", "integrity"],
  ["vision", "vision"],
];

const SHOULD_REFUSE = [
  "",
  "hello",
  "what is the weather",
  "please can you",
  "delete everything",
];

async function main() {
  const { window, errors } = await boot();
  const doc = window.document;

  console.log("chip present    :", !!doc.getElementById("voiceChip"));
  console.log("chip visible    :", !doc.getElementById("voiceChip").hidden);
  console.log("switched on     :", window.voiceOn());
  console.log("no textarea mics:", doc.querySelectorAll(".dictate").length === 0);

  console.log("\ncommands that should land somewhere:");
  let good = 0;
  for (const [said, want] of SHOULD_MATCH) {
    const hit = window.matchDestination(said);
    const got = hit ? hit.view : "(refused)";
    const ok = got === want;
    if (ok) good += 1;
    console.log(`  ${ok ? "ok  " : "MISS"} "${said}"`.padEnd(46)
                + `-> ${got}${ok ? "" : `  wanted ${want}`}`
                + (hit && hit.locked ? "  [locked]" : ""));
  }
  console.log(`  ${good}/${SHOULD_MATCH.length} matched`);

  console.log("\ncommands that should refuse rather than guess:");
  let refused = 0;
  for (const said of SHOULD_REFUSE) {
    const hit = window.matchDestination(said);
    if (!hit) refused += 1;
    console.log(`  ${hit ? "GUESSED" : "refused"}  "${said}"`
                + (hit ? ` -> ${hit.view}` : ""));
  }
  console.log(`  ${refused}/${SHOULD_REFUSE.length} refused`);

  console.log("\nlocked rooms are named as locked, not ignored:");
  const locked = window.matchDestination("registry");
  console.log(`  registry -> ${locked && locked.view}, locked=${locked && locked.locked}`);

  console.log("\nerrors          :", errors.length || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));
  const pass = good === SHOULD_MATCH.length && refused === SHOULD_REFUSE.length;
  console.log(`\n${pass ? "PASS" : "FAIL"}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
