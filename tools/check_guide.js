/* Is there one place to ask for help, and does everything still work from it?

   Four surfaces had grown up in four corners — a Guide chip in the header, a
   bug dock at the bottom, the intro reachable only from Welcome, and a command
   palette behind Ctrl-K. They are merged. The risk in a merge is that something
   is now unreachable rather than relocated, so this opens each item and checks
   the thing it used to do still happens.

   Usage:  node tools/check_guide.js
           GAIUS_BASE=https://app.staging.governingai.us node tools/check_guide.js
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
    return { json: () => r.json(), ok: r.ok, status: r.status };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage", {
    value: store({ "scdes.registration": JSON.stringify(
      { email: "jane.smith@des.sc.gov", name: "Jane Smith", verified: true,
        state: "SC", agency: "sc.des", abbrev: "SCDES" }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
      "scdes.portal": "government" }), writable: true });
  Object.defineProperty(window, "sessionStorage", { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.performance = window.performance || { now: () => Date.now() };
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  window.onunhandledrejection = (e) => errors.push("unhandled: " + e.reason);

  for (const f of ["bugs.js", "dock.js", "guide.js", "onboard.js", "welcome.js",
                   "tour.js", "launcher.js", "speech.js", "builder.js",
                   "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f}: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 80; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  if (window.closeLauncher) window.closeLauncher();
  if (window.signInAs) await window.signInAs("sean.ot", "Jane Smith", "CTO");
  await new Promise((r) => setTimeout(r, 800));
  return { window, errors };
}

const click = (el, w) =>
  el && el.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));

async function main() {
  const { window, errors } = await boot();
  const doc = window.document;

  console.log("one launcher      :", !!doc.getElementById("guideDock"));
  console.log("old bug dock gone :", !doc.getElementById("bugDock"));
  console.log("old Guide chip    :",
    doc.getElementById("tourChip") ? "STILL THERE" : "gone");

  click(doc.getElementById("guideDock"), window);
  await new Promise((r) => setTimeout(r, 300));

  console.log("");
  console.log("panel opened      :", !!doc.getElementById("guidePanel"));
  console.log("  header          :",
    (doc.querySelector(".g-title b") || {}).textContent);
  const items = [...doc.querySelectorAll(".g-item")];
  console.log("  offers          :", items.map((b) =>
    (b.querySelector("b") || {}).textContent).join(" | "));
  console.log("  ask box         :",
    JSON.stringify((doc.getElementById("gAskInput") || {}).placeholder));

  console.log("");
  console.log("report an issue, inside the panel:");
  click(items.find((b) => /Report an issue/.test(b.textContent)), window);
  await new Promise((r) => setTimeout(r, 400));
  console.log("  form is in the panel:",
    !!doc.querySelector("#guideBody #bugHappened"));
  console.log("  no second overlay   :", !doc.getElementById("bugModal"));
  // The "What gets sent with this" manifest was removed at the client's
  // request. What replaced it is the one line under the heading, so this now
  // checks that the form still says the technical detail is attached rather
  // than that it lists it.
  console.log("  no event manifest   :",
    !doc.querySelector("#guideBody .bug-attached"));
  console.log("  still says attached :",
    /already attached/.test(
      (doc.querySelector("#guideBody .g-sub") || {}).textContent || ""));
  console.log("  can go back         :", !!doc.getElementById("bugBack"));
  click(doc.getElementById("bugBack"), window);
  await new Promise((r) => setTimeout(r, 200));
  console.log("  back at the list    :", doc.querySelectorAll(".g-item").length > 0);

  console.log("");
  console.log("typing a locked destination:");
  window.closeGuide();
  window.openGuide();
  await new Promise((r) => setTimeout(r, 250));
  doc.getElementById("gAskInput").value = "audit trail";
  doc.getElementById("gAsk").dispatchEvent(
    new window.Event("submit", { bubbles: true, cancelable: true }));
  await new Promise((r) => setTimeout(r, 600));
  // Audit trail is behind the subscription, so the right outcome is a refusal
  // that names it — not navigation. The first version of this check printed the
  // view title, saw "Welcome", and reported a failure at correct behavior.
  console.log("  says            :", (doc.querySelector(".g-h") || {}).textContent);
  console.log("  did not navigate:",
    doc.getElementById("viewTitle").textContent !== "History");

  console.log("");
  console.log("typing an open destination:");
  window.closeGuide();
  window.openGuide();
  await new Promise((r) => setTimeout(r, 250));
  doc.getElementById("gAskInput").value = "framework";
  doc.getElementById("gAsk").dispatchEvent(
    new window.Event("submit", { bubbles: true, cancelable: true }));
  await new Promise((r) => setTimeout(r, 800));
  console.log("  went to         :", doc.getElementById("viewTitle").textContent);

  console.log("");
  console.log("what is this screen:");
  window.closeGuide();
  window.openGuide();
  await new Promise((r) => setTimeout(r, 250));
  click([...doc.querySelectorAll(".g-item")]
    .find((b) => /What is this screen/.test(b.textContent)), window);
  await new Promise((r) => setTimeout(r, 300));
  console.log("  explains        :", (doc.querySelector(".g-h") || {}).textContent);
  console.log("  reason blocks   :", doc.querySelectorAll(".g-block").length);
  console.log("  can go back     :", !!doc.getElementById("gBack"));

  console.log("");
  console.log("errors            :", errors.length || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));
}

main().catch((e) => { console.error(e); process.exit(1); });
