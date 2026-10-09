/* Can a signed-in user reach a different agency?

   They could. Signed in as the DEMO agency, opening Vision showed the
   no-corpus screen, which carried a "Choose another agency" button. It opened
   the map, and picking a different agency took you into it.

   Every other guard in this application is about not *rendering* another
   agency's records. That button was a door straight into them, and it defeats
   the rule it was surrounded by: a user "should not be able to ever see another
   agency or switch agencies/governmental units".

   This walks the exact path — signed in, Vision, look for a way out — and then
   tries the two programmatic routes as well.

   Usage:  node tools/check_no_switch.js
           GAIUS_BASE=https://app.staging.governingai.us node tools/...
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

async function boot(local) {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  window.fetch = async (url, opts) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url, opts);
    return { json: () => r.json(), ok: r.ok };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage", { value: local, writable: true });
  Object.defineProperty(window, "sessionStorage", { value: store(), writable: true });
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
  await new Promise((r) => setTimeout(r, 700));
  return { window, errors };
}

const DEMO = {
  "scdes.registration": JSON.stringify({
    email: "lokesh@iiac.ai", verified: true, tester: true,
    state: "SC", agency: "iia.test", abbrev: "DEMO",
    agencyName: "DEMO agency — Innovative Infrastructure Advising",
  }),
  "scdes.welcomeSeen": "1", "scdes.tour": "seen", "scdes.portal": "government",
};

async function main() {
  /* Accept the NDA first.

     Without it `resumeSession` legitimately opens the launcher to show the NDA
     over the map, and the first run of this check read that as the switching
     hole still being open. A check that cannot tell a correct open from an
     incorrect one is worse than no check.
  */
  await fetch(BASE + "/api/nda/accept?user=sean.ot", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "lokesh@iiac.ai", name: "Switch check",
                           agency: "iia.test" }),
  });

  console.log("signed in as DEMO, opening Vision\n");
  const { window, errors } = await boot(store({ ...DEMO }));
  const doc = window.document;

  window.go("vision");
  await new Promise((r) => setTimeout(r, 900));

  console.log("  view              :", doc.getElementById("viewTitle").textContent);
  const text = doc.getElementById("view").textContent || "";
  console.log("  offers a switch   :",
    /choose another agency/i.test(text) ? "YES — the hole is open" : "no");
  console.log("  says what to do   :",
    /sign out and register it separately/i.test(text) ? "yes" : "no");
  console.log("  header still      :",
    (doc.getElementById("agencyShort") || {}).textContent);

  console.log("\ntrying the programmatic routes\n");
  const launcher = doc.getElementById("launcher");
  console.log("  launcher at rest  :", launcher.hidden ? "shut" : "OPEN");
  console.log("  NDA on screen     :", !!doc.querySelector(".nda-doc"));

  if (window.openLauncher) window.openLauncher();
  await new Promise((r) => setTimeout(r, 300));
  console.log("  openLauncher()    :",
    launcher.hidden ? "refused" : "OPENED — hole");

  window.location.hash = "#agency";
  window.dispatchEvent(new window.Event("hashchange"));
  await new Promise((r) => setTimeout(r, 400));
  console.log("  #agency hash      :",
    launcher.hidden ? "refused" : "OPENED — hole");

  console.log("\nand after signing out the map must come back\n");
  const cleared = store({ "scdes.portal": "government", "scdes.tour": "seen" });
  const after = await boot(cleared);
  const l2 = after.window.document.getElementById("launcher");
  console.log("  map available     :", !l2.hidden ? "yes" : "NO — locked out");

  console.log("\nerrors              :", errors.length || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));
}

main().catch((e) => { console.error(e); process.exit(1); });
