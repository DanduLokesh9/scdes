/* The map, after the client's two instructions.

     "Make the map of the US just a base map of a single, neutral color, then
      coming out of the DC area should be a line to a USA flag to the side
      which says 'Federal Login'."

   Two things to prove, and they fail differently. The base map is a styling
   change that could silently leave the old flag layer behind. The federal link
   is a control, and a control that draws but does nothing is worse than one
   that is missing — so this clicks it and checks the picker fills with real
   federal agencies rather than merely that the flag is on screen.

   Usage:  node tools/check_federal_map.js
           GAIUS_BASE=https://app.staging.governingai.us node tools/check_federal_map.js
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
    return { json: () => r.json(), ok: r.ok, status: r.status,
             text: () => r.text() };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage",
    { value: store({ "scdes.portal": "government" }), writable: true });
  Object.defineProperty(window, "sessionStorage",
    { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.performance = window.performance || { now: () => Date.now() };
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  const errors = [];
  const warnings = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  const realWarn = console.warn;
  console.warn = (...a) => { warnings.push(a.map(String).join(" ")); };

  for (const f of ["bugs.js", "dock.js", "guide.js", "notify.js", "onboard.js",
                   "welcome.js", "tour.js", "launcher.js", "speech.js",
                   "builder.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f}: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 90; i++) {
    if (window.document.getElementById("fedLink")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  await new Promise((r) => setTimeout(r, 600));
  console.warn = realWarn;
  return { window, errors, warnings };
}

const click = (el, w, type = "click") =>
  el && el.dispatchEvent(new w.MouseEvent(type, { bubbles: true,
                                                  cancelable: true }));

async function main() {
  const failures = [];
  const check = (label, ok, detail = "") => {
    console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(42)} ${detail}`);
    if (!ok) failures.push(label);
  };

  const { window, errors, warnings } = await boot();
  const doc = window.document;

  console.log("the base map");
  const svg = doc.querySelector(".usmap");
  check("map drawn", !!svg);
  check("one neutral base", !!doc.querySelector(".usmap .mapbase"));
  // The old treatment built thirteen stripe rects clipped to the outline.
  const stripes = doc.querySelectorAll('.usmap .flag rect').length;
  check("the flag no longer fills the country", stripes === 0,
        stripes ? `${stripes} stripe rects still drawn` : "");
  const css = read(path.join("assets", "launcher.css"));
  check("a base color is defined", /\.mapbase\s*\{[^}]*fill:/.test(css));

  console.log("\nthe federal link");
  const fed = doc.getElementById("fedLink");
  check("present", !!fed);
  if (!fed) { console.log("\nFAIL"); process.exit(1); }
  const label = (fed.querySelector(".fedlink-label") || {}).textContent;
  check("says Federal Login", label === "Federal Login", `“${label}”`);
  check("has a leader line from DC", !!fed.querySelector(".fedlink-line"),
        (fed.querySelector(".fedlink-line") || {}).getAttribute
          ? (fed.querySelector(".fedlink-line").getAttribute("d") || "").slice(0, 26)
          : "");
  check("the line starts at the District",
        /^M749\.5,209\.5/.test(
          (fed.querySelector(".fedlink-line") || {}).getAttribute?.("d") || ""));
  check("draws a flag, not just a label",
        fed.querySelectorAll(".fedlink-flag rect").length >= 13);
  check("reachable by keyboard", fed.getAttribute("tabindex") === "0");
  check("announced to a screen reader",
        !!(fed.getAttribute("aria-label") || "").match(/federal/i),
        fed.getAttribute("aria-label"));

  console.log("\nclicking it");
  click(fed, window);
  await new Promise((r) => setTimeout(r, 500));
  check("marks itself selected", fed.classList.contains("active"));
  const pickText = (doc.getElementById("lnchPick") || {}).textContent || "";
  check("the picker fills", pickText.length > 0);
  check("it names the jurisdiction", /Federal/.test(pickText));

  // The picker is a combobox: 334 agencies is far too many to render as a list,
  // so nothing appears until something is typed. Search it the way a person
  // would rather than asserting on an empty <ul>.
  const box = doc.getElementById("agencyPick");
  check("a searchable agency box", !!box,
        box ? box.getAttribute("placeholder") : "missing");
  check("offering the federal list",
        /334/.test((box && box.getAttribute("placeholder")) || ""));

  box.value = "environmental protection";
  box.dispatchEvent(new window.Event("input", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 300));
  const options = doc.querySelectorAll("#agencyList [role=option]");
  const names = [...options].map((o) => o.textContent).join(" | ");
  check("searching finds a real agency",
        /Environmental Protection Agency/i.test(names),
        `${options.length} match(es)`);

  box.value = "action";
  box.dispatchEvent(new window.Event("input", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 300));
  const defunct = [...doc.querySelectorAll("#agencyList [role=option]")]
    .map((o) => o.textContent.trim());
  check("no defunct agency is offered",
        !defunct.some((n) => n === "ACTION"),
        defunct.length ? defunct.slice(0, 3).join(", ") : "nothing matched");

  console.log("\nand it does not warn about a missing state flag");
  check("no flag warning", !warnings.some((w) => /cannot show flag/.test(w)),
        warnings.filter((w) => /cannot show flag/.test(w))[0] || "");

  console.log("\nerrors             :", errors.length || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));

  console.log();
  if (failures.length || errors.length) {
    console.log(`FAIL — ${failures.join("; ") || "errors on the page"}`);
    process.exit(1);
  }
  console.log("PASS — neutral map, and Federal Login reaches the federal list");
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
