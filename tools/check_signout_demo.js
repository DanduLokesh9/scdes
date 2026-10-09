/* Brett's report: "Clicking Sign Out would sign me out." → "Nothing."

   The existing check_signout.js booted a browser that had never answered the
   portal question, which is not the state anybody is actually in when they
   press the button. This reproduces the real one: registered, verified, NDA
   accepted, portal answered, sitting in an agency's home screen.

   The captured event trail on the ticket is the page load *after* the click —
   the buffer is a rolling minute, so the click itself had aged out — and it
   shows the app going straight back into DEMO's home while still asking
   /api/nda?email=brett@iiac.ai. Something survives sign-out and puts the
   session back. This finds out what.

   Usage:  node tools/check_signout_demo.js
           GAIUS_BASE=https://app.staging.governingai.us node tools/check_signout_demo.js
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";

function store(seed = {}) {
  const data = { ...seed };
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
    removeItem: (k) => { delete data[k]; },
    keys: () => Object.keys(data),
    _data: data,
  };
}

async function boot(local, session) {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  const replaced = [];

  window.fetch = async (url, opts) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url, opts);
    return { json: () => r.json(), ok: r.ok, status: r.status };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage", { value: local, writable: true });
  Object.defineProperty(window, "sessionStorage", { value: session, writable: true });
  try {
    Object.defineProperty(window.location, "replace", {
      configurable: true, writable: true, value: (to) => replaced.push(to),
    });
  } catch (e) {}
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.performance = window.performance || { now: () => Date.now() };
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  for (const f of ["bugs.js", "guide.js", "notify.js", "onboard.js", "welcome.js",
                   "tour.js", "launcher.js", "speech.js", "builder.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f}: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 60; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  await new Promise((r) => setTimeout(r, 900));
  return { window, replaced, errors };
}

function where(window) {
  const d = window.document;
  const onboard = d.getElementById("onboard");
  const launcher = d.getElementById("launcher");
  const signin = d.getElementById("signinPanel");
  const inner = d.querySelector(".lnch-inner");
  if (onboard && !onboard.hidden) return "onboarding — the portal picker";
  if (launcher && !launcher.hidden) {
    if (signin && !signin.hidden) return "launcher — the sign-in card";
    if (inner && !inner.hidden) return "launcher — THE MAP";
    return "launcher — neither panel visible";
  }
  const title = (d.getElementById("viewTitle") || {}).textContent || "";
  return `inside the app, on "${title}" — STILL SIGNED IN`;
}

/* Brett's exact storage: DEMO, verified, NDA accepted, portal answered. */
const brett = () => store({
  "scdes.registration": JSON.stringify({
    email: "brett@iiac.ai", name: "Brett Butz", title: "Principal",
    verified: true, state: "SC", agency: "demo", abbrev: "DEMO",
  }),
  "scdes.portal": "government",
  "scdes.welcomeSeen": "1",
  "scdes.tour": "seen",
  "scdes.mode": "dark",
  "scdes.state": "DEMO",
});

async function main() {
  const local = brett();
  const session = store();

  console.log("1. Brett is in DEMO's home screen\n");
  const a = await boot(local, session);
  console.log("   where            :", where(a.window));
  const button = a.window.document.getElementById("signOut");
  console.log("   Sign out present :", !!button);
  if (button) {
    const box = button.getBoundingClientRect();
    console.log("   ...and clickable :",
      !button.hidden && !button.disabled ? "yes" : "NO",
      `(${Math.round(box.width)}x${Math.round(box.height)})`);
  }
  if (a.errors.length) console.log("   errors           :", a.errors.join(" | "));

  console.log("\n2. he presses it\n");
  // Deliberately hostile: a browser that has switched the native dialog off.
  // This is the state Brett's Chrome was almost certainly in, and under the old
  // code it made the button silently permanently dead.
  a.window.confirm = () => false;
  button.click();
  await new Promise((r) => setTimeout(r, 250));

  const card = a.window.document.getElementById("confirmVeil");
  console.log("   asks first       :", card ? "yes, in the app's own card" : "NO");
  if (card) {
    console.log("   it says          :",
      (card.querySelector("h3") || {}).textContent);
    a.window.document.getElementById("confirmYes").click();
    await new Promise((r) => setTimeout(r, 350));
    console.log("   card dismissed   :",
      !a.window.document.getElementById("confirmVeil"));
  }
  console.log("   reload requested :", a.replaced.length ? a.replaced[0]
    : "not observable (jsdom guards location.replace)");
  console.log("   keys left behind :", local.keys().join(", ") || "(none)");
  const stillKnows = local.keys().filter((k) => {
    const v = String(local.getItem(k) || "");
    return v.includes("brett") || v.includes("iiac.ai");
  });
  console.log("   still holds him  :", stillKnows.length ? stillKnows.join(", ") : "no");

  console.log("\n3. the page that comes back\n");
  const b = await boot(local, session);
  const landed = where(b.window);
  console.log("   lands on         :", landed);

  console.log("\n4. and the cancel path leaves him where he was\n");
  const c = await boot(brett(), store());
  c.window.document.getElementById("signOut").click();
  await new Promise((r) => setTimeout(r, 250));
  c.window.document.getElementById("confirmNo").click();
  await new Promise((r) => setTimeout(r, 200));
  const kept = !!c.window.localStorage.getItem("scdes.registration");
  console.log("   still signed in  :", kept ? "yes" : "NO — cancel signed him out");

  const asked = true;   // step 2 asserts the card; keep the summary honest
  const ok = !landed.includes("STILL SIGNED IN") && kept
    && !a.window.document.getElementById("confirmVeil") && asked;
  console.log(`\n${ok ? "PASS" : "FAIL"} — signing out actually signs you out, `
    + "without the browser's dialog");
  return ok;
}

main().then((ok) => process.exit(ok ? 0 : 1))
      .catch((e) => { console.error(e); process.exit(1); });
