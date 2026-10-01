/* Does signing out actually land on the map?

   The first attempt did not. Clearing the registration makes a browser look
   brand new, and a brand new browser gets the "which kind of organization are
   you?" onboarding screen — right for a first visit, wrong for someone who just
   signed out of the agency they were working in.

   Diagnosing that from the source is exactly the mistake this repo has a jsdom
   harness for, so this runs the real page against a real DOM twice: once as a
   signed-in user pressing Sign out, and once as the reload that follows. It
   reports which screen is actually on top.

   Usage:  node tools/check_signout.js            (server must be running)
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = "http://127.0.0.1:8765";

/** A localStorage/sessionStorage that behaves like the real thing. */
function store(seed = {}) {
  const data = { ...seed };
  return {
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
    removeItem: (k) => { delete data[k]; },
    _data: data,
  };
}

async function boot({ local, session, replaced }) {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only",
    pretendToBeVisual: true,
    url: BASE + "/",
  });
  const { window } = dom;

  window.fetch = async (url) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url);
    return { json: () => r.json(), ok: r.ok };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage", { value: local, writable: true });
  Object.defineProperty(window, "sessionStorage", { value: session, writable: true });
  // jsdom refuses to navigate. `location.replace` is not a plain property, so
  // it has to be redefined rather than assigned — assigning silently does
  // nothing, which made the first run of this harness report "no reload
  // requested" when one had been.
  try {
    Object.defineProperty(window.location, "replace", {
      configurable: true, writable: true,
      value: (to) => { replaced.push(to); },
    });
  } catch (e) {
    window.__navFallback = replaced;
  }
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  for (const f of ["onboard.js", "welcome.js", "tour.js", "launcher.js", "app.js"]) {
    try {
      window.eval(read(path.join("assets", f)));
    } catch (e) {
      console.log(`  ! ${f}: ${e.message}`);
    }
  }
  // app.js boots itself and calls initLauncher(), which makes four round trips
  // to the server. Poll for the map rather than guessing at a delay — a fixed
  // 1200ms was too short, and the harness reported "no launcher" for every
  // case including the ones that work.
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 50; i++) {
    const host = window.document.getElementById("launcher");
    const onboard = window.document.getElementById("onboard");
    if ((host && !host.hidden) || (onboard && !onboard.hidden)) break;
    await new Promise((r) => setTimeout(r, 150));
  }
  await new Promise((r) => setTimeout(r, 400));
  return window;
}

function whatIsOnScreen(window) {
  const onboard = window.document.getElementById("onboard");
  const launcher = window.document.getElementById("launcher");
  const signin = window.document.getElementById("signinPanel");
  const inner = window.document.querySelector(".lnch-inner");
  if (onboard && !onboard.hidden) return "onboarding — the portal picker";
  if (launcher && !launcher.hidden) {
    if (signin && !signin.hidden) return "launcher — the sign-in card";
    if (inner && !inner.hidden) return "launcher — THE MAP";
    return "launcher — neither panel visible";
  }
  return "the application record (no launcher)";
}

async function main() {
  console.log("1. signed in, pressing Sign out\n");
  const local = store({
    "scdes.registration": JSON.stringify({ email: "lokesh@iiac.ai",
      verified: true, tester: true }),
    "scdes.welcomeSeen": "1",
    "scdes.mode": "dark",
    "scdes.tour": "seen",
    // Anyone signed in has already answered the portal question, and this
    // harness was asserting against a browser that had not. It failed for a
    // state no signed-in user can be in: no portal answer meant the reload
    // correctly showed onboarding, and the check called that a regression.
    "scdes.portal": "government",
  });
  const session = store();
  const replaced = [];
  const w1 = await boot({ local, session, replaced });

  const button = w1.document.getElementById("signOut");
  console.log(`   sign-out button present : ${!!button}`);
  if (!button) return console.log("\n   FAIL — nothing to click.");
  button.click();
  await new Promise((r) => setTimeout(r, 200));
  // Sign out asks in the application's own card now rather than through the
  // browser's confirm(), which Chrome lets people switch off permanently.
  const yes = w1.document.getElementById("confirmYes");
  console.log(`   asks in-app first       : ${!!yes}`);
  if (yes) { yes.click(); await new Promise((r) => setTimeout(r, 200)); }

  console.log(`   registration cleared    : ${!local.getItem("scdes.registration")}`);
  console.log(`   marker set              : ${session.getItem("scdes.justSignedOut") === "1"}`);
  console.log(`   theme kept              : ${local.getItem("scdes.mode") === "dark"}`);
  console.log(`   tour-seen kept          : ${local.getItem("scdes.tour") === "seen"}`);
  // jsdom hard-guards location.replace against redefinition, so this cannot be
  // observed here. Step 2 covers what actually matters — that the state after a
  // reload is right — and the reload itself is one line with no branches.
  console.log(`   reload requested        : not observable under jsdom`);

  console.log("\n2. the reload that follows\n");
  const w2 = await boot({ local, session, replaced: [] });
  const screen = whatIsOnScreen(w2);
  console.log(`   lands on                : ${screen}`);
  console.log(`   marker consumed         : ${!session.getItem("scdes.justSignedOut")}`);

  console.log("\n3. a genuinely new visitor still gets onboarding\n");
  const fresh = await boot({ local: store(), session: store(), replaced: [] });
  console.log(`   lands on                : ${whatIsOnScreen(fresh)}`);

  console.log(`\n${screen.includes("THE MAP") ? "PASS" : "FAIL"} — sign-out lands on the map`);
}

main().catch((e) => { console.error(e); process.exit(1); });
