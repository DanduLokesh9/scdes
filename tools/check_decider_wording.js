/* Does the interface use the agency's own word, or SCDES's?

   The client's ruling: a Council is one agency's *answer* to a framework
   question, not a fixture of the product. app/decider.py has modeled that from
   the start and the rail label followed it — but the prose did not. Screens went
   on saying "every governed change routes through the Council" while the sidebar
   beside them said whatever the agency had actually chosen.

   Checked two ways, because neither alone is enough.

   **At runtime** — that the helpers exist, are shared with the other scripts,
   and follow the answer when it changes.

   **At source** — that no sentence asserts a Council. This half is here because
   the surfaces that carry most of those sentences cannot be rendered in this
   harness: the reason rail lives on Configure, Oversight, Integrity and
   Lifecycle, all of which are behind the subscription and correctly refuse to
   draw, and `startTour` filters its steps by `getBoundingClientRect()`, which
   in jsdom returns zeros for everything — so the tour yields no steps at all.
   Asserting only what renders would have passed a build with every one of those
   sentences still hardcoded.

   It is not a search for the word "Council". That word is legitimate in
   `Role.COUNCIL`, in `COUNCIL_LOG`, in the module name, and in citations to
   SCDES's own documents — rewording a citation would be falsifying a reference.
   What is checked is the set of sentences that made a claim *about this agency*.

   Usage:  node tools/check_decider_wording.js       (server must be running)
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const WEB = path.join(ROOT, "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";

/* The claims that used to be hardcoded, as they appeared. Each is a sentence
   about what happens in *this* agency, which is the thing that cannot be
   assumed. */
const CLAIMS = [
  /routes? through the Council/,
  /route a change through the Council/,
  /is a Council amendment/,
  /the Council adopts it/,
  /decision is the Council's/,
  /The Council adopted the appendices/,
  /Council Chair is notified/,
  /gate decision is the Council/,
];

/** Comments stripped, so a note explaining the old wording is not a finding. */
function code(file) {
  return read(path.join("assets", file))
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .split("\n")
    .map((line) => line.replace(/(^|[^:])\/\/.*$/, "$1"))
    .join("\n");
}

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
      { email: "lokesh@iiac.ai", name: "Check", verified: true,
        state: "SC", agency: "sc.des", abbrev: "SCDES" }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
      "scdes.portal": "government" }), writable: true });
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

async function main() {
  const failures = [];
  const check = (label, ok, detail = "") => {
    console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(46)} ${detail}`);
    if (!ok) failures.push(label);
  };

  console.log("at source — no sentence asserts a Council");
  const FILES = ["app.js", "tour.js", "welcome.js", "builder.js",
                 "launcher.js"];
  for (const file of FILES) {
    const body = code(file);
    const hits = CLAIMS.filter((re) => re.test(body)).map((re) => re.source);
    check(file, !hits.length, hits.length ? hits.join(", ") : "clean");
  }

  console.log("\nand the approval prose interpolates instead");
  const appjs = code("app.js");
  check("app.js calls whoDecides()", /\$\{whoDecides\(\)\}/.test(appjs),
        `${(appjs.match(/whoDecides\(\)/g) || []).length} call(s)`);
  check("the risk-gate line is derived",
        /gate decision is \$\{whoDecidesPossessive\(\)\}/.test(appjs));
  const tourjs = code("tour.js");
  check("tour.js resolves it when drawn",
        /tourWhoDecides\(\)/.test(tourjs)
        && /typeof step\.body === "function"/.test(tourjs),
        "its copy is built per step, not at load");
  check("the welcome diagram is labeled from it",
        /whoDecidesLabel/.test(code("welcome.js")));

  console.log("\nnothing pre-fills the word into the answer");
  check("the noun field starts empty",
        /value="\$\{esc\(q\.noun \|\| ""\)\}"/.test(appjs),
        "an agency saves it only by typing it");

  console.log("\nat runtime");
  const { window, errors } = await boot();
  for (const name of ["whoDecides", "whoDecidesPossessive", "whoDecidesLabel",
                      "paintDecider"]) {
    check(`window.${name} is shared`, typeof window[name] === "function");
  }
  const state = await (await window.fetch("/api/state?user=sean.ot")).json();
  check("it starts from the agency's own answer",
        window.whoDecides() === state.decider.body,
        `"${window.whoDecides()}"`);

  window.paintDecider({
    shape: "individual", noun: "Chief AI Officer", decided: true,
    is_group: false, rail_label: "Chief AI Officer",
    body: "the Chief AI Officer", possessive: "the Chief AI Officer's",
    capacity_label: "Chief AI Officer", levels: {}, sentence: "",
  });
  check("and follows a different answer",
        window.whoDecides() === "the Chief AI Officer"
        && window.whoDecidesPossessive() === "the Chief AI Officer's",
        `"${window.whoDecides()}"`);
  check("the label follows too",
        window.whoDecidesLabel() === "Chief AI Officer",
        `"${window.whoDecidesLabel()}"`);
  /* Not asserted against a rail item any more. `paintDecider` still relabels
     `.rail-item[data-view="council"]`, and that row no longer exists — who
     decides moved inside the builder when the four authoring destinations were
     collapsed into one. The lookup is guarded, so it is dead rather than
     broken, and the label it would have written is checked above instead. */
  const stale = window.document.querySelector('.rail-item[data-view="council"]');
  check("no orphaned rail row is expected", !stale,
        "who decides lives in the builder now");

  console.log("\nerrors             :", errors.length || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));

  console.log();
  if (failures.length || errors.length) {
    console.log(`FAIL — ${failures.join("; ") || "errors on the page"}`);
    process.exit(1);
  }
  console.log("PASS — the interface says what the agency chose, not what SCDES did");
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
