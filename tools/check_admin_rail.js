/* Does the Admin section appear for admins and nobody else?

   The server side is covered by tools/check_admin.py, which is where the actual
   boundary is. This is the other half: that an ordinary user never sees a
   heading called Admin, and that an admin does — with Reported bugs inside it
   rather than sitting in Authoring next to Agency profile, which is where it
   used to be for everyone.

   The token is a real one rather than a faked string, because a fake would
   prove only that the harness can set a localStorage key. What is being tested
   is that the server accepts it and the shell believes the answer.

   Usage:  node tools/check_admin_rail.js
           GAIUS_BASE=https://app.staging.governingai.us node tools/check_admin_rail.js
*/

const { JSDOM } = require("jsdom");

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const WEB = path.join(ROOT, "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";

/* A real session, obtained the way a person obtains one.

   This minted straight out of the tenancy store, which works only where this
   process and the server share a filesystem. Pointed at staging it produced a
   token that server had never issued, so the Admin section correctly did not
   draw and the check reported three failures that were its own fault. Going
   through the real endpoints works against anything.

   Depends on SMTP being unconfigured, which is the only reason the code comes
   back in the response. */
async function post(path, body) {
  const r = await fetch(BASE + path, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body) });
  return r.json();
}

async function mint(email) {
  let asked = await post("/api/agency/signin", { email });
  if (!asked.code) {
    asked = await post("/api/agency/register", {
      agency: "iia.test", name: "Rail check", title: "Harness",
      email, phone: "(843) 555 0100", attested: true });
  }
  if (!asked.code) {
    throw new Error(`no code for ${email}: ${asked.error || "refused"}`);
  }
  const done = await post("/api/agency/verify", { email, code: asked.code });
  if (!done.session) {
    throw new Error(`could not verify ${email}: ${done.error || "no session"}`);
  }
  return done.session;
}

async function retire(token) {
  await post("/api/session/end", { session: token });
}

function store(seed = {}) {
  const d = { ...seed };
  return { getItem: (k) => (k in d ? d[k] : null),
           setItem: (k, v) => { d[k] = String(v); },
           removeItem: (k) => { delete d[k]; } };
}

async function boot(email, token) {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  window.fetch = async (url, opts) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url, opts);
    return { json: () => r.json(), ok: r.ok, status: r.status };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  const seed = {
    "scdes.registration": JSON.stringify({ email, name: "Check",
      verified: true, state: "SC", agency: "sc.des", abbrev: "SCDES" }),
    "scdes.welcomeSeen": "1", "scdes.tour": "seen", "scdes.portal": "government",
  };
  if (token) seed["scdes.session"] = token;
  Object.defineProperty(window, "localStorage",
    { value: store(seed), writable: true });
  Object.defineProperty(window, "sessionStorage",
    { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.performance = window.performance || { now: () => Date.now() };
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  for (const f of ["bugs.js", "dock.js", "guide.js", "notify.js", "onboard.js",
                   "welcome.js", "tour.js", "launcher.js", "speech.js",
                   "builder.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f}: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 80; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  if (window.closeLauncher) window.closeLauncher();
  await new Promise((r) => setTimeout(r, 800));
  return { window, errors };
}

function railReport(window) {
  const doc = window.document;
  const section = doc.getElementById("adminRail");
  const items = [...doc.querySelectorAll(".rail-item[data-view]")]
    .filter((b) => b.offsetParent !== null || true)      // jsdom has no layout
    .map((b) => b.dataset.view);
  return {
    sectionExists: !!section,
    sectionShown: !!section && !section.hidden,
    // Reachable means: in the rail AND not inside a hidden section.
    bugsReachable: !!doc.querySelector(
      "#adminRail:not([hidden]) .rail-item[data-view='bugs']"),
    bugsAnywhereVisible: items.includes("bugs")
      && !!doc.querySelector(".rail-item[data-view='bugs']")
      && !doc.querySelector("#adminRail[hidden] .rail-item[data-view='bugs']"),
    heading: (doc.querySelector("#adminRail .rail-eyebrow") || {}).textContent,
  };
}

async function main() {
  let failures = [];
  const check = (label, got, want) => {
    const ok = got === want;
    console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(44)} ${got}`);
    if (!ok) failures.push(label);
  };

  console.log("an ordinary user\n");
  const plain = await boot("jane.smith@des.sc.gov", "");
  let r = railReport(plain.window);
  check("Admin section drawn", r.sectionShown, false);
  check("Reported bugs reachable", r.bugsReachable, false);
  check("no stray bugs item elsewhere", r.bugsAnywhereVisible, false);
  if (plain.errors.length) console.log("  errors:", plain.errors.join(" | "));

  console.log("\nan admin\n");
  const token = await mint("brett@iiac.ai");
  const boss = await boot("brett@iiac.ai", token);
  r = railReport(boss.window);
  check("Admin section drawn", r.sectionShown, true);
  check("Reported bugs reachable", r.bugsReachable, true);
  console.log(`        heading                              ${
    (r.heading || "").replace(/\s+/g, " ").trim()}`);
  if (boss.errors.length) console.log("  errors:", boss.errors.join(" | "));

  console.log("\nand the queue actually loads for them\n");
  await boss.window.go("bugs");
  await new Promise((r2) => setTimeout(r2, 700));
  const heading = (boss.window.document.querySelector("#view .sub3") || {})
    .textContent || "";
  check("shows the team queue", /Reported bugs/.test(heading), true);

  console.log("\nthe same screen without the token\n");
  await plain.window.go("bugs");
  await new Promise((r2) => setTimeout(r2, 700));
  const theirs = (plain.window.document.querySelector("#view .sub3") || {})
    .textContent || "";
  check("falls back to their own", /Your reports/.test(theirs), true);

  await retire(token);

  console.log();
  if (failures.length) {
    console.log(`FAIL — ${failures.length}: ${failures.join("; ")}`);
    process.exit(1);
  }
  console.log("PASS — Admin is its own section, and only admins have it");
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
