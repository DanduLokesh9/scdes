/* Does the Framework screen actually let you build a framework?

   It used to open on a status page — four layers, which files are present,
   record an adoption when it happens. Useful once you have a framework, useless
   on the day you are writing one. This drives the real screen: opens Framework,
   walks into a section, answers a question, and checks it stuck.

   Usage:  node tools/check_builder.js
           GAIUS_BASE=https://app.staging.governingai.us node tools/check_builder.js
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
    return { json: () => r.json(), ok: r.ok };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage", {
    value: store({ "scdes.registration": JSON.stringify(
      { email: "lokesh@iiac.ai", verified: true, tester: true }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
      "scdes.portal": "government" }), writable: true });
  Object.defineProperty(window, "sessionStorage", { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  window.onunhandledrejection = (e) => errors.push("unhandled: " + e.reason);
  window.console = { ...console, log: () => {},
    error: (...a) => errors.push(a.map(String).join(" ")),
    warn: () => {} };

  for (const f of ["onboard.js", "welcome.js", "tour.js", "launcher.js",
                   "builder.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f} threw at load: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 80; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  if (window.closeLauncher) window.closeLauncher();
  // Sign in, as the real flow does. An agency's first registrant holds the
  // Office of Technology capacity — framework answers are OT's to give, and
  // without this the harness posts as an operator and every save is refused.
  if (window.signInAs) await window.signInAs("sean.ot", "Test Person", "CTO");
  await new Promise((r) => setTimeout(r, 900));
  return { window, errors };
}

const click = (el, w) =>
  el && el.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));

async function main() {
  const { window, errors } = await boot();
  const doc = window.document;

  click(doc.querySelector('.rail-item[data-view="framework"]'), window);
  await new Promise((r) => setTimeout(r, 1500));

  console.log("view              :", doc.getElementById("viewTitle").textContent);
  console.log("upload panel      :", !!doc.querySelector(".fb-intake"),
              "| file input:", !!doc.getElementById("fbFile"));
  console.log("docs listed       :", doc.querySelectorAll(".fb-doc").length);
  const sections = [...doc.querySelectorAll(".fb-section")];
  console.log("sections listed   :", sections.length);
  console.log("available now     :",
    sections.filter((s) => !s.disabled).map((s) =>
      s.querySelector(".fb-title").textContent).join(", ") || "none");
  console.log("progress shown    :",
    (doc.querySelector(".fb-count") || {}).textContent);
  console.log("save-a-version    :", !!doc.getElementById("fbSave"));

  /* The first section that actually asks something, not simply the first
     enabled one. Step 00 is an explainer — "What governance actually is",
     `asks: False`, no questions at all — so opening it yielded an empty list
     and this harness then crashed reading `.fb-ask` off `questions[0]`. The
     failure looked like a builder fault and was a fault in the check. */
  const asking = sections.filter((s) => !s.disabled
    && !/what governance actually is/i.test(
      (s.querySelector(".fb-title") || {}).textContent || ""));
  const open = asking[0] || sections.find((s) => !s.disabled);
  if (!open) {
    console.log("\nFAIL — no section can be opened");
    console.log("renderBuilder exported:", typeof window.renderBuilder);
    console.log("view HTML head:",
      (doc.getElementById("view").innerHTML || "").slice(0, 200));
    console.log("errors:", errors.length ? errors.join(" | ") : "none");
    return;
  }
  click(open, window);
  await new Promise((r) => setTimeout(r, 1200));

  console.log("\ninside section 1:");
  const questions = [...doc.querySelectorAll(".fb-q")];
  console.log("  questions       :", questions.length);
  console.log("  fixed rows      :", doc.querySelectorAll(".fb-fixed-row").length);
  console.log("  source quoted   :",
    doc.querySelectorAll(".fb-source").length, "of",
    questions.length + doc.querySelectorAll(".fb-fixed-row").length);
  const first = questions[0];
  if (!first) {
    console.log("  FAIL — the opened section rendered no questions");
    console.log("  errors:", errors.length ? errors.join(" | ") : "none");
    return;
  }
  console.log("  first asks      :",
    (first.querySelector(".fb-ask") || {}).textContent
      ? first.querySelector(".fb-ask").textContent.slice(0, 62)
      : "(no .fb-ask)");
  console.log("  default shown   :",
    !!first.querySelector(".fb-default, .fb-option"));

  // Answer it and check it persists.
  const box = first.querySelector('input[type="text"], textarea');
  const key = first.dataset.key;
  const btn = first.querySelector("[data-save]");
  console.log("  key             :", key);
  console.log("  input found     :", !!box, box && box.id);
  console.log("  save button     :", !!btn, "onclick=" + typeof (btn || {}).onclick);
  if (box) {
    box.value = "Anderson County · ACO · county government";
    click(first.querySelector("[data-save]"), window);
    await new Promise((r) => setTimeout(r, 900));
    const saved = await (await fetch(BASE + "/api/versions")).json();
    const errSpan = first.querySelector(".signin-error");
    console.log("  error shown     :",
      errSpan && !errSpan.hidden ? errSpan.textContent : "none");
    const stored = saved.working && saved.working[key];
    console.log("  answered & saved:",
      stored ? JSON.stringify(stored.value).slice(0, 50) : "NOT SAVED");
    console.log("  version moved   :",
      saved.current ? saved.current.label : "no — correct, saving is separate");
    console.log("  unsaved count   :", saved.unsaved);
  }

  console.log("evidence blocks   :", doc.querySelectorAll(".fb-evidence").length,
              "| use-this buttons:", doc.querySelectorAll("[data-use]").length);

  console.log("\nreviewer grouping :",
    [...doc.querySelectorAll(".fb-group-name")].map((n) => n.textContent)
      .join(" | ") || "none");
  console.log("fill-in-your-own  :",
    doc.querySelectorAll('input[value="__own__"]').length, "option(s)");
  console.log("authoring rail    :",
    [...doc.querySelectorAll('.rail-item[data-view]')].slice(0, 3)
      .map((b) => b.dataset.view).join(", "));

  window.go("framework");
  await new Promise((r) => setTimeout(r, 1400));
  /* Start Here is a pitch for somebody who has just arrived, and the client
     asked for it to go once they have started: "Once framework created and
     I'm on the save a version, no reason to still have the Start Here
     section." So whether it should be on screen depends on whether any
     question has been answered, and this asserts the pairing rather than
     printing a bare true/false that reads as correct either way. */
  const begun = ((window.frameworkProgress && window.frameworkProgress())
    || { done: 0 }).done > 0;
  const pitch = !!doc.getElementById("fwBegin");
  console.log("Start Here button :", pitch,
    pitch === begun
      ? `WRONG — ${begun ? "work in progress, it should be gone"
                         : "nothing answered, it should be shown"}`
      : `correct — ${begun ? "hidden, work in progress"
                           : "shown, nothing answered yet"}`);
  const lock = [...doc.querySelectorAll(".locked")]
    .find((n) => /after the framework is complete/i.test(n.textContent));
  console.log("adoption gated    :", !!lock);
  console.log("upgrade ask       :",
    /Subscribe to access the\s+workflow management/.test(doc.body.textContent));

  console.log("\nerrors            :", errors.length || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));
}

main().catch((e) => { console.error(e); process.exit(1); });
