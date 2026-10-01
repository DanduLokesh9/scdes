/* Does pressing "Enter <agency>" actually open the sign-in?

   It did not. Wiring the NDA in replaced `finishSignin(access)` with
   `showNda(entry, email, access)` at three call sites, and at two of them there
   is no `email` in scope — the address lives on `saved`. The ReferenceError
   killed the click handler silently, so the button did nothing at all.

   Errors are collected and printed here, because "nothing happened" and "it
   threw" look identical from outside.

   149 entries, all beginning "South Carolina Department of…", so the ranking
   matters more than the filtering: typing "DES" matches eleven of them and
   SCDES has to come first. This types real queries into the real combobox and
   prints what comes back.

   Usage:  node tools/check_agency_search.js       (server must be running)
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = "http://127.0.0.1:8765";

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
  window.fetch = async (url) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url);
    return { json: () => r.json(), ok: r.ok };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage", {
    value: store({ "scdes.registration": JSON.stringify(
      { email: "lokesh@iiac.ai", verified: true, tester: true }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen" }), writable: true });
  Object.defineProperty(window, "sessionStorage", { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  window.onunhandledrejection = (e) => errors.push("unhandled: " + e.reason);
  for (const f of ["onboard.js", "welcome.js", "tour.js", "launcher.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f}: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 50; i++) {
    const l = window.document.getElementById("launcher");
    if (l && !l.hidden) break;
    await new Promise((r) => setTimeout(r, 150));
  }
  await new Promise((r) => setTimeout(r, 400));
  return { window, errors };
}

async function main() {
  const { window, errors } = await boot();
  const doc = window.document;

  const sc = doc.querySelector('.st[data-code="SC"]') || doc.querySelector(".st");
  if (sc) sc.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 400));

  // Pick the DEMO agency through the combobox, as a person would.
  const input = doc.getElementById("agencyPick");
  input.focus();
  input.value = "demo";
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 200));
  input.dispatchEvent(new window.KeyboardEvent("keydown",
    { key: "Enter", bubbles: true }));
  await new Promise((r) => setTimeout(r, 250));

  const go = doc.getElementById("lnchEnter");
  console.log("button reads   :", go && go.textContent);
  console.log("button enabled :", go && !go.disabled);

  const before = errors.length;
  go.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 1400));

  const panel = doc.getElementById("signinPanel");
  console.log("sign-in shown  :", panel && !panel.hidden);
  const lede = doc.querySelector(".signin-lede");
  console.log("screen says    :", lede ? lede.textContent.trim().slice(0, 70)
                                       : "(nothing rendered)");
  console.log("NDA embedded   :", !!doc.querySelector(".nda-doc object"));
  const buttons = [...doc.querySelectorAll(".signin-actions .btn")]
    .map((b) => b.textContent.trim());
  console.log("buttons        :", buttons.join("  |  ") || "(none)");
  console.log("new errors     :", errors.length - before || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));
}

main().catch((e) => { console.error(e); process.exit(1); });
