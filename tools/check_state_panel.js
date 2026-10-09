/* Select a state and report what the panel under the map actually says.

   Written for two things at once, both reported from a screenshot.

   The client marked a button reading "No corpus — what does that mean?" and
   asked why it was there. It was there for every state without loaded
   documents, which after New Mexico opened meant every state but one — and
   it spoke to a developer, cast doubt on the agency's own name, and announced
   a missing thing that the framework builder does not need. So this asserts
   the phrase is gone from the panel, in the state where it used to appear.

   And New Mexico is the first state opened after South Carolina, so this also
   checks its panel renders at all: the agency, the domain rule, and a note
   that reads as English.

   Usage:  node tools/check_state_panel.js         (server must be running)
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = "http://127.0.0.1:8765";

const failures = [];
function check(label, ok, detail) {
  console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(46)} ${detail || ""}`);
  if (!ok) failures.push(label);
}

async function main() {
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
  if (!window.localStorage) {
    window.localStorage = { getItem: () => null, setItem() {} };
  }
  window.alert = () => { failures.push("the page raised an alert"); };
  const thrown = [];
  window.addEventListener("error", (e) => thrown.push(String(e.message)));

  // All three, in this order: it is app.js's boot that initializes the
  // launcher and renders the map, so loading launcher.js alone leaves the
  // page with no states on it and every check failing for the wrong reason.
  for (const file of ["assets/launcher.js", "assets/tour.js",
                      "assets/app.js"]) {
    try {
      window.eval(read(file));
    } catch (e) {
      thrown.push(`${file} threw at load: ${e.message}`);
    }
  }
  for (let i = 0; i < 40 && !window.document.getElementById("flagPop"); i++) {
    await new Promise((r) => setTimeout(r, 150));
  }
  await new Promise((r) => setTimeout(r, 400));

  for (const code of ["NM", "SC"]) {
    const state = window.document.querySelector(`.st[data-code="${code}"]`);
    if (!state) { check(`${code} is on the map`, false); continue; }
    state.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 400));

    // The panel under the map, not the whole document. Scanning the body
    // swept in the page subtitle and every other screen's copy, and reported
    // a failure for wording nobody asked about.
    const pick = window.document.getElementById("lnchPick");
    const note = window.document.getElementById("lnchNote");
    const text = [pick, note].map((n) => (n && n.textContent) || "")
      .join(" ").replace(/\s+/g, " ");

    console.log(`\n=== ${code} ===`);
    check(`${code}: the panel says something`, text.length > 40,
          `${text.length} chars`);
    // The point of the exercise.
    check(`${code}: no "No corpus" button`, !/No corpus/i.test(text));
    check(`${code}: no developer path on screen`, !/corpus\//.test(text));
    check(`${code}: the enter button is present`,
          !!window.document.getElementById("lnchEnter"));
    check(`${code}: the old handler is gone`,
          !window.document.getElementById("lnchWhy"));
  }

  console.log("\n=== errors thrown by the page ===");
  console.log(thrown.length ? thrown.map((t) => "  " + t).join("\n")
                            : "  none");
  if (thrown.length) failures.push("the page threw");

  console.log(failures.length
    ? `\n${failures.length} problem(s): ${failures.join(", ")}`
    : "\nall good");
  process.exit(failures.length ? 1 : 0);
}

main();
