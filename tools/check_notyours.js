/* Does a fail-closed room render an explanation, or a broken page?

   The endpoints answer `{available: false, why: ...}` to a tenant that does
   not own the corpus. `VIEWS.agency` read `d.name` and `d.instruments.length`,
   so the first version of that fix would have shown the client a page of
   dashes and then thrown — which looks like a broken product rather than a
   boundary being kept.

   A full app boot to prove three lines of early return was disproportionate,
   and hung. This loads app.js into a minimal document, calls the guard
   directly with the payload the server actually sends, and reads what comes
   back.

   Usage:  node tools/check_notyours.js
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const SOURCE = fs.readFileSync(path.join(WEB, "assets", "app.js"), "utf8");

/* Exactly what `server.NOT_YOURS` sends, copied rather than fetched so this
   runs without a server and fails loudly if the shape ever changes. */
const PAYLOAD = {
  available: false,
  why: "This section is built from a reference agency's own adopted "
     + "documents. It becomes yours once your framework is adopted and your "
     + "own records fill it — until then there is nothing here that belongs "
     + "to your organization, and nothing from anybody else's is shown.",
};

function main() {
  const failures = [];
  const check = (label, ok, detail = "") => {
    console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(46)} ${detail}`);
    if (!ok) failures.push(label);
  };

  const dom = new JSDOM(
    `<body><div id="view"></div></body>`,
    { runScripts: "outside-only", url: "http://127.0.0.1:8765/" });
  const { window } = dom;
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  window.fetch = async () => ({ json: async () => ({}), ok: true });
  Object.defineProperty(window, "localStorage",
    { value: { getItem: () => null, setItem() {}, removeItem() {} },
      writable: true });

  // The file ends by wiring up a page that is not here, so a throw during the
  // tail is expected and irrelevant — the declarations run first.
  try { window.eval(SOURCE); } catch (e) { /* no shell to attach to */ }

  const guard = window.notYours;
  check("the guard exists at all", typeof guard === "function",
    typeof guard);
  if (typeof guard !== "function") {
    console.log("\nFAIL — nothing to test");
    process.exit(1);
  }

  check("a normal payload is not intercepted",
    guard({ name: "Anderson County", instruments: [] }) === null);
  check("and neither is a missing one", guard(null) === null);

  const box = guard(PAYLOAD);
  check("a withheld room returns something to render", !!box);
  const said = box ? box.textContent : "";
  check("it says nothing here is theirs yet",
    /belongs to you yet/i.test(said));
  check("it says why, in the server's own words",
    said.includes("nothing from anybody else's is shown"));
  check("it names nobody else",
    !["SCDES", "South Carolina", "Environmental Services"]
      .some((n) => said.includes(n)));
  check("it points at the thing that IS theirs",
    /your framework/i.test(said)
    && !!box.querySelector('[data-go="framework"]'));
  /* "A page of dashes" means fields with nothing in them, not em-dashes in a
     sentence. Counting every "—" flagged the explanation's own punctuation,
     which is the check measuring the wrong thing: what matters is whether any
     cell holds a placeholder where a value should be. */
  const empties = [...box.querySelectorAll("td, th, span")]
    .filter((cell) => cell.textContent.trim() === "—");
  check("and it is not a page of empty fields", empties.length === 0,
    `${empties.length} placeholder cells`);
  check("because it renders no field table at all",
    !box.querySelector("table"));

  console.log();
  if (failures.length) {
    console.log(`FAIL — ${failures.length}: ${failures.join("; ")}`);
    process.exit(1);
  }
  console.log("PASS — a withheld room explains itself");
}

main();
