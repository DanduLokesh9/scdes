/* Do the two new screens render, and do they keep the spine's rules?

   Projects and Lifecycle are the first screens built against the build
   specification, and they replace the retired Workflow Helper between them:
   the tracker that carries one project through the seven named gates, and a
   reference page that explains them and holds no record.

   Three things are worth a harness rather than a unit test, because all
   three are properties of the rendered page rather than of a function.

   No gate is ever a number. The spine forbids it anywhere, in code or in
   copy, and the board on the home screen was breaking that rule with a
   "STEP 03" eyebrow above every column. This reads the real DOM of every
   screen it can open and fails on any of the banned forms.

   The tracker carries its state in text. A reader who cannot see the tint
   has to get "passed", "here now" or "not yet" from the words, so this
   counts the state words rather than the classes.

   Lifecycle opens with nothing answered. It is the page somebody opens when
   they are stuck partway through authoring a framework, so it must render in
   full before any question has been answered — and it must not be greyed out
   by the gate that shuts the screens which need one.

   Usage:  node tools/check_new_screens.js         (server must be running)
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");

/* Points at a local server by default, and at whatever you give it
   otherwise:
     GAIUS_BASE=https://app.staging.governingai.us node tools/check_new_screens.js

   The markup and the script still come off this disk rather than off the
   server, so pointing this at staging tests the deployed *server* against
   the local client. That is the right pairing after a push only once the
   bytes are known to be the same — compare the hashes first:
     ssh ... sha256sum app/web/index.html app/web/assets/app.js
   otherwise a file that failed to upload passes this harness. */
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";

/* The banned forms, from `spine.BANNED_GATE_FORMS`. Kept in step with the
   Python by the test suite; repeated here because this harness reads a DOM
   rather than importing a module. */
const NUMBERED = [
  /\bgate\s*[1-7]\b/i, /\bstage\s*[1-7]\b/i, /\bstep\s*0?[1-7]\b/i,
  /\bphase\s*[1-7]\b/i, /\b[1-7]\s*of\s*7\b/i,
];

/* Words this product does not write in front of a user. From
   `spine.BANNED_IN_COPY`, less "deploy", which is a gate name. */
const BANNED = [/\bmodel\b/i, /\binference\b/i, /\btraining data\b/i,
                /\bllm\b/i, /\balgorithm\b/i, /\bdeployed\b/i,
                /\bmachine learning\b/i];

const failures = [];
function check(label, ok, detail) {
  console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(52)} ${detail || ""}`);
  if (!ok) failures.push(label);
}

async function main() {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;

  window.fetch = async (url, opts) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url, opts);
    return { json: () => r.json(), ok: r.ok };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  if (!window.localStorage) {
    window.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
  }
  window.alert = () => { failures.push("the page raised an alert"); };
  const thrown = [];
  window.addEventListener("error", (e) => thrown.push(String(e.message)));

  for (const file of ["assets/launcher.js", "assets/tour.js",
                      "assets/app.js"]) {
    try { window.eval(read(file)); }
    catch (e) { thrown.push(`${file} threw at load: ${e.message}`); }
  }
  const $ = (s) => window.document.querySelector(s);
  const view = () => $("#view");
  const text = (n) => ((n && n.textContent) || "").replace(/\s+/g, " ");
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));

  /* Boot does its own navigating, and it finishes whenever the last request
     it fired comes back. Navigating before that lands a screen which boot
     then paints over, and the check reads the wrong page — which is exactly
     what happened, and cost a while: Projects reported the home screen's
     copy and looked like an application bug rather than a harness one.

     So: wait until the view stops changing, then go. */
  async function settle(limit = 24) {
    let last = null;
    for (let i = 0; i < limit; i++) {
      const now = text(view());
      if (now && now === last) return;
      last = now;
      await wait(250);
    }
  }
  await settle();

  async function open(name) {
    const item = $(`.rail-item[data-view="${name}"]`);
    if (!item) return { item: null, body: "" };
    // Read the lock before navigating: a disabled button swallows the click
    // and the screen that comes back is whatever was already there.
    const locked = item.disabled || item.classList.contains("rail-locked");
    const want = text(item);
    for (let tries = 0; tries < 3; tries++) {
      try { await window.go(name); }
      catch (e) { thrown.push(`go(${name}) threw: ${e.message}`); }
      await wait(700);
      // `go` writes the title synchronously, so a title that no longer
      // matches means something else navigated after us.
      if (text($("#viewTitle")) && want.includes(text($("#viewTitle")))) break;
    }
    return { item, locked, body: text(view()) };
  }

  /* ------------------------------------------------ the rail carries both */

  console.log("\n=== the rail ===");
  for (const name of ["projects", "lifecycle"]) {
    const item = $(`.rail-item[data-view="${name}"]`);
    check(`${name} has a rail item`, !!item, item ? text(item) : "missing");
    check(`${name} is not behind the subscription`,
          !!item && item.dataset.paid !== "1");
  }

  /* ------------------------------------------------------- Lifecycle */

  console.log("\n=== Lifecycle ===");
  const lc = await open("lifecycle");
  check("it is not greyed out before a framework exists", !lc.locked,
        lc.locked ? "rail-locked" : "open");
  check("it renders something substantial", lc.body.length > 2000,
        `${lc.body.length} chars`);

  // Seven blocks, all expanded at rest: seven h2 headings inside the view.
  const heads = [...view().querySelectorAll("section.lcr-step > h2")]
    .map((h) => text(h));
  check("seven step blocks, all drawn", heads.length === 7,
        heads.join(" · "));
  check("in the spine's order",
        heads.join(",") === "Govern,Identify,Procure,Test,Deploy,Measure,Sunset",
        heads.join(","));

  // Each block carries the five parts. The first part is the plain sentence,
  // which has no heading of its own, so four headings is the right count.
  const parts = view().querySelectorAll("section.lcr-step .lcr-part > h3");
  check("every block carries its named parts", parts.length === 7 * 4,
        `${parts.length} of 28`);

  check("nothing is behind an accordion",
        view().querySelectorAll("details, summary").length === 0);

  // The floors table, with real semantics and its own scroll container.
  const floors = view().querySelector(".lcr-floors table");
  check("the floors table has row headers", !!floors &&
        floors.querySelectorAll('tbody th[scope="row"]').length === 8,
        floors ? `${floors.querySelectorAll('tbody th[scope="row"]').length} rows`
               : "no table");
  check("and column headers", !!floors &&
        floors.querySelectorAll('thead th[scope="col"]').length === 4);

  check("the loop is explained in text", /a circle, not a line/.test(lc.body));
  check("it says it holds no record",
        /does not hold a record/.test(lc.body));
  check("every link says where it goes",
        !/\bclick here\b/i.test(lc.body));

  /* -------------------------------------------------------- Projects */

  console.log("\n=== Projects ===");
  const pj = await open("projects");
  check("the screen renders", pj.body.length > 120,
        `${pj.body.length} chars`);

  if (pj.locked) {
    /* No framework is adopted on this deployment, which is a real state and
       the designed one: `projects` is deliberately not framework-exempt,
       because its levels and the paper each gate asks for are read out of
       the framework, and a tracker opened before any of that exists is a
       screen of blanks.

       So check that the gate explains itself rather than reporting a pass
       nobody earned. This panel used to throw — `$("#spine").hidden` on a
       node that had been removed from the markup — so every locked screen
       in the application rendered blank where its explanation belonged. */
    check("the locked screen names itself",
          /Projects needs the framework first/.test(pj.body), "gate panel");
    check("and says what to do about it",
          /Set up the framework/.test(pj.body));
  } else {
    const empty = !!view().querySelector(".pj-empty");
    const table = !!view().querySelector("table");
    check("it shows either a register or an empty state", empty || table,
          empty ? "empty state" : table ? "register" : "neither");
    // A harness that says a screen is wrong without showing what it saw is
    // half a harness.
    if (!empty && !table) {
      console.log("        saw: " + pj.body.slice(0, 200));
    }

    if (!empty) {
      const row = view().querySelector("tr[data-ref]");
      if (row) {
        row.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
        await new Promise((r) => setTimeout(r, 300));
        const gates = view().querySelectorAll(".pj-track .pj-gate");
        check("the tracker draws all seven gates", gates.length === 7,
              `${gates.length}`);
        // The point: the state is in the words, not only in the color.
        const words = [...gates].map((g) => text(g.querySelector(".g-was")));
        check("each gate carries its state as text",
              words.every((w) => /^(Here now|Passed |Not yet)/.test(w)),
              words.join(" · "));
        check("the waiting-on line is readable",
              !!view().querySelector(".pj-waiting"));
      } else {
        check("a row was available to open", false);
      }
    }
    check("it says nothing watches your vendors",
          /Nothing here watches your vendors/.test(pj.body));
  }

  /* The tracker itself, from a fixture.
   *
   * Whether a framework is adopted on this deployment decides whether the
   * register renders, and the tracker is the part that must be right either
   * way — so it is exercised directly, against the shape
   * `projects.tracker()` actually returns. The fixture below is one project
   * at Procure, waiting on a decision, with Identify passed and written up
   * four months after it happened. */
  console.log("\n=== the tracker ===");
  const FIXTURE = {
    gates: [
      { id: "gate.govern", name: "Govern", current: false, passed_on: "",
        recorded_after_the_fact: false },
      { id: "gate.identify", name: "Identify", current: false,
        passed_on: "2026-02-11", recorded_after_the_fact: true },
      { id: "gate.procure", name: "Procure", current: true,
        passed_on: "2026-03-02", recorded_after_the_fact: false },
      { id: "gate.test", name: "Test", current: false, passed_on: "",
        recorded_after_the_fact: false },
      { id: "gate.deploy", name: "Deploy", current: false, passed_on: "",
        recorded_after_the_fact: false },
      { id: "gate.measure", name: "Measure", current: false, passed_on: "",
        recorded_after_the_fact: false },
      { id: "gate.sunset", name: "Sunset", current: false, passed_on: "",
        recorded_after_the_fact: false },
    ],
    waiting_on: "Waiting on a decision",
    version_pending: false,
    version_pending_says: "The vendor says something is changing",
  };

  if (typeof window.trackerOf !== "function") {
    check("trackerOf is reachable", false, "not a global");
  } else {
    const ul = window.trackerOf(FIXTURE);
    const gates = ul.querySelectorAll(".pj-gate");
    check("all seven gates are drawn", gates.length === 7, `${gates.length}`);
    check("the list is labeled for a screen reader",
          !!ul.getAttribute("aria-label"), ul.getAttribute("aria-label"));

    const words = [...gates].map((g) => text(g.querySelector(".g-was")));
    // The point of the whole family: the state is in the words, so a reader
    // who cannot see the tint gets the same three facts.
    check("every gate carries its state as text",
          words.every((w) =>
            /^(Here now|Not yet|Passed \d{4}-\d{2}-\d{2})$/.test(w)),
          words.join(" · "));
    check("the gate it is at says so", words[2] === "Here now", words[2]);
    check("a passed gate carries its date", words[1] === "Passed 2026-02-11",
          words[1]);
    check("a gate not reached says not yet", words[6] === "Not yet",
          words[6]);
    check("recording late is shown in words, not flagged",
          text(gates[1]).includes("written up later") &&
          !/late!|overdue|missing/i.test(text(gates[1])));
    check("no gate is numbered in the tracker",
          !NUMBERED.some((re) => re.test(text(ul))), text(ul).slice(0, 60));
    check("and no count of how far along it is",
          !/\b[1-7]\s*\/\s*7\b|%/.test(text(ul)));
  }

  /* ------------------------------------- no numbered gate, anywhere */

  console.log("\n=== no gate is ever a number ===");
  const screens = ["home", "lifecycle", "projects", "process"];
  for (const name of screens) {
    const got = await open(name);
    if (!got.item && name !== "home") continue;
    const hit = NUMBERED.find((re) => re.test(got.body));
    check(`${name}: no numbered gate`, !hit, hit ? `matched ${hit}` : "");
    const word = BANNED.find((re) => re.test(got.body));
    check(`${name}: no banned word`, !word, word ? `matched ${word}` : "");
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
