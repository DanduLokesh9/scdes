/* Does the Integrity screen work as a screen?

   What this asserts that a unit test cannot:

     1. A person can record a check and write down an incident from the
        screen, and both land on the one list.
     2. The one refusal on the check form fires in the browser: a check
        cannot be marked complete with "what was not tested" empty and the box
        unticked — and ticking the box is enough.
     3. The recommendation renders in its own block, apart from the findings,
        says nothing has to be done, and can be declined.
     4. Nothing on it names another organization or its documents. The screen
        it replaced audited one agency's corpus by name.

   Writes to the harness container, so it refuses anything but a local server.
       $env:IIA_SUBSCRIPTION = "1"; node tools/check_integrity_ui.js
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(BASE)) {
  console.error(`\n  Refusing to run against ${BASE} — this walk writes records.\n`);
  process.exit(2);
}

const HARNESS_AGENCY = "gaius.harness";
const HARNESS_EMAIL = "walk@harness.gaius.test";

async function demandScratchContainer() {
  const url = `${BASE}/api/whose-container?email=${encodeURIComponent(HARNESS_EMAIL)}`;
  let found = await (await fetch(url)).json();
  if (!found.safe_to_overwrite) {
    await fetch(`${BASE}/api/agency/register`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agency: HARNESS_AGENCY, name: "Automated walk",
        title: "Harness", email: HARNESS_EMAIL,
        phone: "(843) 555 0100", attested: true }) });
    found = await (await fetch(url)).json();
  }
  if (!found.safe_to_overwrite) {
    console.error(`\n  Refusing to run — writes would land in ${found.agency}.\n`);
    process.exit(2);
  }
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
      { email: HARNESS_EMAIL, name: "Automated walk", verified: true,
        state: "SC", agency: HARNESS_AGENCY, abbrev: "HARNESS" }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
      "scdes.portal": "government" }), writable: true });
  Object.defineProperty(window, "sessionStorage", { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });
  if (!window.CSS) window.CSS = {};
  if (!window.CSS.escape) window.CSS.escape = (s) => String(s).replace(/["\\]/g, "\\$&");

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  // One evaluation, so the scripts share one scope the way a page does.
  const all = ["bugs.js", "dock.js", "guide.js", "notify.js", "onboard.js",
               "welcome.js", "tour.js", "launcher.js", "speech.js",
               "builder.js", "app.js"].map((f) => read(path.join("assets", f)));
  try { window.eval(all.join("\n;\n")); } catch (e) { errors.push(e.message); }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 80; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  if (window.closeLauncher) window.closeLauncher();
  await new Promise((r) => setTimeout(r, 800));
  return { window, errors };
}

const settle = (ms = 500) => new Promise((r) => setTimeout(r, ms));
async function until(condition, ms = 12000) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    try { if (await condition()) return true; } catch { /* not yet */ }
    await settle(150);
  }
  return false;
}

async function main() {
  const failures = [];
  const check = (label, ok, detail = "") => {
    console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(56)} ${detail}`);
    if (!ok) failures.push(label);
  };

  await demandScratchContainer();
  const { window, errors } = await boot();
  const doc = window.document;
  const said = () => doc.getElementById("view").textContent.replace(/\s+/g, " ");
  const q = (s) => doc.querySelector(s);
  const choose = (name, value) => {
    const r = doc.querySelector(`[name="${name}"][value="${value}"]`);
    if (r) { r.checked = true; r.dispatchEvent(new window.Event("change")); }
    return !!r;
  };
  const open = async () => {
    for (let i = 0; i < 6; i++) {
      await window.go("integrity");
      if (await until(() => /Checks recorded/.test(said()), 4000)) return true;
    }
    return false;
  };

  console.log("the screen");
  const rail = [...doc.querySelectorAll(".rail-item")].map((b) => b.dataset.view);
  check("there is a rail entry for it", rail.includes("integrity"));
  const opened = await open();
  check("it opens", opened, opened ? "" : said().slice(0, 160));
  check("the title is the specification's",
    /Does it work, and is it still working/.test(doc.body.textContent));
  for (const label of ["Checks recorded", "Looked at this cycle", "Never checked",
                       "Past due for a look"]) {
    check(`counter: ${label}`, said().includes(label));
  }
  check("the findings line is permanent",
    /comparison between your own framework and your own records/.test(said()));
  check("the watches say what they cannot do",
    /They do not watch the tool/.test(said()));
  check("it names no other organization's documents",
    !/SCDES|Appendix [A-Z]\b|Operations Manual/.test(said()), "");

  console.log("\nrecording a check");
  const name = `Harness triage ${Date.now().toString(36)}`;
  q("#igNewCheck").click();
  await until(() => q("#ck-project"));
  const sel = q("#ck-project");
  sel.value = "__new"; sel.dispatchEvent(new window.Event("change"));
  q("#ck-newname").value = name;
  choose("ck-occasion", "The first look, before it goes live");
  choose("ck-where", "We have no staging or testing environment");
  q("#ck-found").value = "It got about a third of the March files wrong.";
  choose("ck-complete", "Complete");
  q("#ck-save").click();
  await settle(600);
  check("complete with the limits empty is refused",
    /Say what was not tested, or tick the box/.test(q("#ck-limits-refusal").textContent));
  check("and focus goes to the field", doc.activeElement === q("#ck-limits"));
  check("the refusal is tied to the field",
    (q("#ck-limits").getAttribute("aria-describedby") || "").includes("ck-limits-refusal"));
  q("#ck-nolimits").checked = true;
  q("#ck-save").click();
  check("ticking the box is enough", await until(() =>
    /Added and marked complete/.test(said())), said().match(/Added[^.]*\./)?.[0] || "");
  check("the confirmation thanks nobody", !/thank/i.test(q("#igForm")?.textContent || ""));
  q("#igDone")?.click();
  await until(() => /Checks recorded/.test(said()));
  check("it is on the list", said().includes(name));
  check("the ticked box is a finding",
    /Nobody wrote down what was not tested/.test(said()));
  check("the recommendation sits in its own block",
    /nothing here has to be done/.test(said()));

  console.log("\nthe recommendation");
  const decline = [...doc.querySelectorAll("[data-rec]")]
    .find((b) => b.dataset.state === "declined");
  check("it can be declined", !!decline);
  if (decline) {
    decline.click();
    await until(() => /Declined/.test(said()));
    check("and the answer is recorded without comment", /Declined/.test(said()));
    await settle(1500);   // let that navigation finish before opening a form
  }

  console.log("\nwriting down an incident");
  q("#igNewIncident").click();
  await until(() => q("#in-what"));
  check("anyone can write one, it says", /including somebody with no login/.test(said()));
  check("the visibility line sits above the button",
    /visible to everyone in your organization/.test(said()));
  q("#in-what").value = "It told a resident the wrong permit fee.";
  q("#in-atunsure").checked = true;
  q("#in-save").click();
  const written = await until(() => /Written down/.test(said()));
  check("it is written down", written,
    written ? "" : (q("#in-err")?.textContent || said().slice(0, 120)));
  q("#igDone")?.click();
  await until(() => /Checks recorded/.test(said()));
  check("the incident is on the same list", /An incident/.test(said()));
  check("an unknown date is said to be unknown, not today",
    /when it happened is not known/.test(said()));

  console.log("\nchanging, correcting, attaching");
  choose("igGroup", "flat");
  choose("igSort", "Most recent first");
  await until(() => /by date/.test(q("#igList caption")?.textContent || ""));
  const change = [...doc.querySelectorAll("[data-edit]")][0];
  check("a record still being written offers Change it", !!change);
  if (change) {
    change.click();
    check("the change opens with focus on its heading",
      await until(() => q("#igAct") && doc.activeElement === q("#igActH")));
    const cause = q("#ed-cause") || q("#ed-found");
    cause.value = "Nobody knows yet.";
    q("#igAct [data-save]").click();
    check("the change saves", await until(() => !q("#igAct") && /Checks recorded/.test(said())));
  }
  const correct = [...doc.querySelectorAll("[data-correct]")][0];
  check("a complete check offers Correct it, not Change it", !!correct);
  if (correct) {
    const ref = correct.dataset.correct;
    correct.click();
    check("the correction names the one it corrects",
      await until(() => q("#igForm h2") && q("#igForm h2").textContent.includes(`corrects ${ref}`)));
    check("the check form offers an attachment", !!q("#ck-files") && q("#ck-files").type === "file");
    check("with the security note beside it", /never the credential/.test(q("#igForm").textContent));
    q("#ck-cancel").click();
  }

  console.log("\nthe list");
  choose("igGroup", "flat");
  await until(() => /by date/.test(q("#igList caption")?.textContent || ""));
  check("straight down the page by date", /by date/.test(q("#igList caption")?.textContent || ""));
  check("the table is a keyboard-reachable region",
    q("#igList .vr-scroll")?.getAttribute("tabindex") === "0");
  choose("igGroup", "grouped");

  console.log(`\nerrors             : ${errors.length ? errors.join("; ") : "none"}`);
  if (errors.length) failures.push("script errors");
  console.log();
  if (failures.length) {
    console.log(`FAIL — ${failures.length}: ${failures.slice(0, 4).join("; ")}`);
    process.exit(1);
  }
  console.log("PASS — checks and incidents record, refuse the one thing, and recommend without requiring");
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
