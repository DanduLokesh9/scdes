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

  // Select South Carolina so the picker renders.
  const sc = doc.querySelector('.st[data-code="SC"]') || doc.querySelector(".st");
  if (sc) sc.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 500));

  const input = doc.getElementById("agencyPick");
  const list = doc.getElementById("agencyList");
  console.log(`combobox present : ${!!input}`);
  if (!input) { console.log(errors.join("\n")); return; }
  console.log(`placeholder      : ${input.placeholder}`);

  const type = async (q) => {
    input.focus();
    input.value = q;
    input.dispatchEvent(new window.Event("input", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 120));
    return [...list.querySelectorAll("li[data-id]")].map((li) =>
      li.querySelector("b").textContent);
  };

  console.log("\nevery agency reachable:");
  input.focus();
  input.value = "";
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 200));
  // Every agency, plus the "Other" row every list ends with.
  const rows = [...list.querySelectorAll("li[data-id]")];
  const all = rows.filter((li) => !li.classList.contains("combo-other")).length;
  console.log(`  ends with Other: ${rows.length && rows[rows.length - 1].classList.contains("combo-other") ? "OK" : "MISSING"}`);
  const offered = (await (await fetch(BASE + "/api/states")).json())
    .states.find((s) => s.code === "SC").agencies.length;
  console.log(`  server offers  : ${offered}`);
  console.log(`  list renders   : ${all}   ${all === offered ? "OK" : "TRUNCATED"}`);

  console.log("\ntyping:");
  for (const q of ["DES", "environmental", "education", "revenue", "demo",
                   "motor", "zzz"]) {
    const hits = await type(q);
    console.log(`  "${q}"`.padEnd(18) + `-> ${hits.slice(0, 5).join(", ") || "(no match)"}`
                + (hits.length > 5 ? `  (+${hits.length - 5})` : ""));
  }

  console.log("\nkeyboard:");
  await type("environmental");
  input.dispatchEvent(new window.KeyboardEvent("keydown",
    { key: "Enter", bubbles: true }));
  await new Promise((r) => setTimeout(r, 250));
  console.log(`  Enter picks    : ${input.value}`);
  const go = doc.getElementById("lnchEnter");
  console.log(`  button reads   : ${go && go.textContent}`);
  console.log(`  button enabled : ${go && !go.disabled}`);
  const hint = doc.getElementById("agencyHint");
  console.log(`  hint           : ${hint && hint.textContent.trim()}`);

  await type("education");
  input.dispatchEvent(new window.KeyboardEvent("keydown",
    { key: "ArrowDown", bubbles: true }));
  input.dispatchEvent(new window.KeyboardEvent("keydown",
    { key: "Enter", bubbles: true }));
  await new Promise((r) => setTimeout(r, 250));
  console.log(`  arrow+Enter    : ${input.value}`);
  console.log(`  button reads   : ${doc.getElementById("lnchEnter").textContent}`);

  if (errors.length) console.log(`\nerrors:\n  ${errors.join("\n  ")}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
