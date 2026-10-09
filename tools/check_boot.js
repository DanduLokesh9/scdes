/* What does a returning visitor actually land on?

   Reported: opening app.staging.governingai.us drops you straight into the
   record — no map, no sign-in, no NDA — with the rail live and the view empty.
   That is the gate being bypassed, not a cosmetic fault, so this boots the real
   page with a stored registration and reports what is on screen.

   Usage:  node tools/check_boot.js
           GAIUS_BASE=https://app.staging.governingai.us node tools/check_boot.js
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
  window.fetch = async (url) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url);
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
  // The boot sequence wraps initLauncher() in try/catch and reports through
  // console.error, so a failure there never reaches the window error handler.
  // The first run of this harness said "errors: none" while the launcher was
  // plainly not opening.
  window.console = {
    ...console,
    error: (...a) => errors.push("console.error: " + a.map(String).join(" ")),
    warn: (...a) => errors.push("console.warn: " + a.map(String).join(" ")),
    log: () => {},
  };
  for (const f of ["onboard.js", "welcome.js", "tour.js", "launcher.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f} threw at load: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  // Snapshot early: the hole was a live shell during the seconds before the
  // locks were painted, which a report taken only at the end cannot see.
  await new Promise((r) => setTimeout(r, 60));
  const early = {
    booting: window.document.body.classList.contains("booting"),
    unlocked: [...window.document.querySelectorAll(".rail-item[data-view]")]
      .filter((b) => !b.disabled).length,
  };
  // Poll rather than guess. A fixed wait cannot tell "still loading" apart from
  // "never going to load", and that is the exact question here.
  for (let i = 0; i < 80; i++) {
    const l = window.document.getElementById("launcher");
    const o = window.document.getElementById("onboard");
    if ((l && !l.hidden) || (o && !o.hidden)) break;
    await new Promise((r) => setTimeout(r, 250));
  }
  // The veil is removed at the very end of boot. If it never lifts, closing the
  // launcher would reveal an invisible application — so wait for it and report
  // how long it took rather than sampling at an arbitrary moment.
  const t0 = Date.now();
  let lifted = 0;
  for (let i = 0; i < 60; i++) {
    if (!window.document.body.classList.contains("booting")) {
      lifted = Date.now() - t0; break;
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  return { window, errors, early, lifted };
}

function report(label, { window, errors, early, lifted }) {
  const doc = window.document;
  const launcher = doc.getElementById("launcher");
  const onboard = doc.getElementById("onboard");
  const panel = doc.getElementById("signinPanel");
  console.log(`\n--- ${label} ---`);
  console.log("  veil lifted     :", doc.body.classList.contains("booting")
    ? "NO — the shell would be invisible" : `yes, ${lifted}ms after the launcher`);
  console.log("  launcher open   :", !!(launcher && !launcher.hidden));
  console.log("  onboarding open :", !!(onboard && !onboard.hidden));
  console.log("  sign-in card    :", !!(panel && !panel.hidden));
  console.log("  NDA on screen   :", !!doc.querySelector(".nda-doc"));
  console.log("  agency shown    :",
    (doc.getElementById("agencyShort") || {}).textContent);
  const view = doc.getElementById("view");
  console.log("  record shows    :",
    doc.getElementById("viewTitle").textContent, "|",
    (view.textContent || "").trim().slice(0, 55) || "(EMPTY)");
  /* Not disabled *and* not inside a hidden section. This counted DOM nodes,
     so it reported `bugs` as clickable for every user — that row moved into the
     Admin section, which is `hidden` for anyone who is not one of the three
     GAIUS admins. A row nobody can see is not a row anybody can click, and
     saying otherwise made this look like the access fix had not landed. */
  const live = [...doc.querySelectorAll(".rail-item[data-view]")]
    .filter((b) => !b.disabled && !b.closest("[hidden]"))
    .map((b) => b.dataset.view);
  console.log("  rail clickable  :", live.join(", ") || "none");
  console.log("  60ms after load : veil=" + early.booting +
              ", rail items live=" + early.unlocked);
  console.log("  errors          :", errors.length || "none");
  errors.forEach((e) => console.log("    " + e));
}

async function main() {
  console.log("base:", BASE);

  report("a returning visitor (registration already stored)",
    await boot(store({
      "scdes.registration": JSON.stringify(
        { email: "lokesh@iiac.ai", verified: true, tester: true }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
    })));

  report("a brand new browser (nothing stored)", await boot(store()));

  /* The reported behaviour: signed in, refresh, and you are back on the map
     being asked to pick an agency you already picked. The client's rule is that
     a user goes straight to their own agency and is never offered another. */
  const session = (email) => ({
    "scdes.registration": JSON.stringify({
      email, verified: true, tester: true,
      state: "SC", agency: "iia.test", abbrev: "DEMO",
      agencyName: "DEMO agency — Innovative Infrastructure Advising",
    }),
    "scdes.welcomeSeen": "1", "scdes.tour": "seen",
    "scdes.portal": "government",
  });

  /* Two different addresses, deliberately.

     Using one meant the run accepted the NDA for it partway through, so the
     *next* run found the "still outstanding" case already accepted and reported
     a gate bypass that was not there. A check whose result depends on whether
     the last run cleaned up is a check that will cry wolf, and the one time it
     matters nobody will believe it. */
  const fresh = "nda.outstanding.check@iiac.ai";
  report("signed in, NDA still outstanding", await boot(store(session(fresh))));

  const accepted = "nda.accepted.check@iiac.ai";
  await fetch(BASE + "/api/nda/accept?user=sean.ot", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: accepted, name: "Boot check",
                           agency: "iia.test" }),
  });
  report("signed in, NDA accepted", await boot(store(session(accepted))));

  report("after signing out", await boot(store({
    "scdes.portal": "government", "scdes.tour": "seen",
  })));

  // The reported bug: on the map, press refresh, get asked "Which of these are
  // you?" again. This is that browser — portal answered, signed out.
  report("signed out, portal already answered", await boot(store({
    "scdes.portal": "government", "scdes.tour": "seen",
  })));

  report("refreshed again (same browser)", await boot(store({
    "scdes.portal": "government", "scdes.tour": "seen",
  })));
}

main().catch((e) => { console.error(e); process.exit(1); });
