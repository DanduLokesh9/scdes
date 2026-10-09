/* Does the agency search find the agency?

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
  if (window.closeLauncher) window.closeLauncher();
  await window.signInAs("sean.ot", "Test", "CTO");
  await new Promise((r) => setTimeout(r, 1200));

  console.log("view          :", doc.getElementById("viewTitle").textContent);
  console.log("columns       :", doc.querySelectorAll(".lc-col").length);
  console.log("arrows        :", doc.querySelectorAll(".lc-arrow").length);
  console.log("steps         :", [...doc.querySelectorAll(".lc-title")]
    .map((n) => n.textContent).join(" > "));
  console.log("why panels    :", doc.querySelectorAll(".lc-why").length);
  console.log("deliverables  :", doc.querySelectorAll(".lc-gives li").length);
  console.log("cross-cutting :", doc.querySelectorAll(".lc-cross-grid > div").length);
  console.log("claims        :", doc.querySelectorAll(".lc-claims > div").length);
  const here = doc.querySelector(".lc-col.lc-now .lc-title");
  console.log("you are here  :", here && here.textContent);
  if (errors.length) console.log("errors:", errors.join(" | "));
}

main().catch((e) => { console.error(e); process.exit(1); });
