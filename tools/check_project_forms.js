/* The Projects forms, driven in a real page.

   Starts a project, is refused leaving Identify with nobody named (in the
   spine's own words), names who is accountable, passes to Procure, and
   sets where it stands — the whole path that could not be walked before,
   because nothing could satisfy the one rule Identify enforces.

   Creates projects, so it runs against a local server only. It signs in as
   a tester address, which the application lets past the framework gate.

   Usage:  node tools/check_project_forms.js      (local server must be running)
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(BASE)) {
  console.error("Refusing to run against " + BASE + " — this creates " +
                "projects. Local servers only.");
  process.exit(2);
}

const failures = [];
function check(label, ok, detail) {
  console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(56)} ${detail || ""}`);
  if (!ok) failures.push(label);
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const text = (n) => ((n && n.textContent) || "").replace(/\s+/g, " ").trim();

async function main() {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  window.fetch = async (u, o) => {
    const r = await fetch(u.startsWith("http") ? u : BASE + u, o);
    return { json: () => r.json(), ok: r.ok };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  const mem = { "scdes.registration":
                JSON.stringify({ email: `forms.check.${Date.now()}@iiac.ai` }) };
  Object.defineProperty(window, "localStorage", { value: {
    getItem: (k) => (k in mem ? mem[k] : null),
    setItem: (k, v) => { mem[k] = String(v); },
    removeItem: (k) => { delete mem[k]; } } });
  const thrown = [];
  window.addEventListener("error", (e) => thrown.push(String(e.message)));
  const files = ["assets/launcher.js", "assets/tour.js", "assets/bugs.js",
                 "assets/guide.js", "assets/builder.js", "assets/app.js"];
  try { window.eval(files.map(read).join("\n;\n")); }
  catch (e) { thrown.push("load: " + e.message); }
  const doc = window.document;
  const $ = (s) => doc.querySelector(s);
  let last = null;
  for (let i = 0; i < 30; i++) {
    const now = text($("#view"));
    if (now && now === last) break;
    last = now; await wait(250);
  }

  async function open() {
    for (let t = 0; t < 3; t++) {
      await window.go("projects"); await wait(800);
      if ($("#pjStart")) return true;
    }
    return false;
  }
  const click = (n) =>
    n.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));

  console.log("\n=== starting a project ===");
  check("the start form is on the screen", await open(),
        text($("#view")).slice(0, 60));
  if (!$("#pjStart")) return finish(thrown);
  check("its fields are labeled",
        !!$("#pjName").closest("label") && !!$("#pjRunning").closest("label"));
  click($("#pjStart"));
  await wait(300);
  check("an empty name is stopped", /Give it a name/.test(text($("#toast"))));

  const name = "Permit triage " + String(Date.now()).slice(-4);
  $("#pjName").value = name;
  $("#pjRunning").value = "yes";
  click($("#pjStart"));
  await wait(1500);
  const panel = $("#pjOne");
  check("the new project opens beneath the list",
        !!panel && !panel.hidden && text(panel).includes(name));
  const opener = [...doc.querySelectorAll("[data-open]")]
    .find((b) => /Open Permit triage/.test(b.getAttribute("aria-label") || ""));
  check("each row opens from a keyboard-reachable button", !!opener);

  console.log("\n=== leaving Identify ===");
  const to = $("#pjTo");
  check("the passage offers gate names, not numbers",
        !!to && [...to.options].every((o) => !/\d/.test(o.textContent)),
        to ? [...to.options].map((o) => o.textContent.trim()).join(", ") : "");
  click($("#pjMove"));
  await wait(900);
  const said = $("#pjSaid");
  check("with nobody named, the spine's refusal is shown word for word",
        !!said && !said.hidden
        && /cannot be recorded as past Identify yet/.test(text(said)),
        text(said).slice(0, 70));
  check("it is announced", said && said.getAttribute("role") === "alert");

  $("#pjRole").value = "General Manager";
  click($("#pjNameIt"));
  await wait(1500);
  check("naming who is accountable is recorded",
        /General Manager/.test(text($("#pjOne"))));

  click($("#pjMove"));
  await wait(1500);
  const here = [...doc.querySelectorAll("#pjOne .pj-gate")]
    .find((g) => /Here now/.test(text(g)));
  check("it passes to Procure", !!here && /Procure/.test(text(here)),
        here ? text(here) : "");
  const passed = [...doc.querySelectorAll("#pjOne .pj-gate")]
    .find((g) => /Identify/.test(text(g)));
  check("Identify now reads as passed, in words",
        !!passed && /Passed \d{4}-\d{2}-\d{2}/.test(text(passed)),
        passed ? text(passed) : "");

  console.log("\n=== where it stands ===");
  const state = $("#pjState");
  check("Retired is not offered from the menu",
        !!state && ![...state.options].some((o) => o.value === "state.retired"));
  state.value = "state.waiting_person";
  state.dispatchEvent(new window.Event("change"));
  check("choosing 'waiting on somebody' asks who", !$("#pjWhoWrap").hidden);
  $("#pjWaitingFor").value = "the Clerk";
  click($("#pjSetState"));
  await wait(1500);
  check("the tracker says who it is waiting on",
        /Waiting on the Clerk/.test(text($("#pjOne .pj-waiting"))),
        text($("#pjOne .pj-waiting")));

  finish(thrown);
}

function finish(thrown) {
  console.log("\n=== errors thrown by the page ===");
  console.log(thrown.length ? "  " + thrown.join("\n  ") : "  none");
  if (thrown.length) failures.push("the page threw");
  console.log(failures.length
    ? `\n${failures.length} problem(s): ${failures.join(", ")}`
    : "\nall good");
  process.exit(failures.length ? 1 : 0);
}

main();
