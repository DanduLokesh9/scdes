/* Is the evidence already there when the form is opened?

   That is the whole design claim: capture runs from page load, so a report
   carries what actually happened rather than what someone re-performed. This
   provokes an error and a failed request, then opens the form and checks the
   buffer already holds them — and that it holds nothing it should not.

   This used to drive the standalone bug dock. That dock is gone — reporting
   moved inside the help panel — so it now renders the form the way the panel
   does. The capture assertions are the point and they are unchanged; only the
   surface they are reached through has moved. check_guide.js covers the route
   in from the "?" button.

   Usage:  node tools/check_bug_widget.js
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
    return { json: () => r.json(), ok: r.ok, status: r.status };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage", {
    value: store({ "scdes.registration": JSON.stringify(
      { email: "jane.smith@des.sc.gov", name: "Jane Smith", verified: true,
        state: "SC", agency: "sc.des", abbrev: "SCDES" }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
      "scdes.portal": "government" }), writable: true });
  Object.defineProperty(window, "sessionStorage", { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.performance = window.performance || { now: () => Date.now() };
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  for (const f of ["bugs.js", "dock.js", "guide.js", "notify.js", "onboard.js",
                   "welcome.js", "tour.js", "launcher.js", "speech.js",
                   "builder.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { console.log(`  ! ${f}: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 80; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  if (window.closeLauncher) window.closeLauncher();
  if (window.signInAs) await window.signInAs("sean.ot", "Jane Smith", "CTO");
  await new Promise((r) => setTimeout(r, 800));
  return window;
}

async function main() {
  const window = await boot();
  const doc = window.document;

  console.log("reachable from ? :", !!doc.getElementById("guideDock"));
  console.log("capture running  :", typeof window.bugBuffer === "function");

  // Something goes wrong, and something leaks an address into a URL — which is
  // what this application does on every API call.
  window.console.error("TypeError: cannot read 'gate' of undefined");
  try { await window.fetch("/api/nope?email=jane.smith@des.sc.gov"); } catch (e) {}
  await new Promise((r) => setTimeout(r, 400));

  const buffer = window.bugBuffer();
  console.log("\ncaptured before anyone pressed anything:");
  console.log("  events in buffer :", buffer.length);
  const kinds = [...new Set(buffer.map((e) => e.kind))];
  console.log("  kinds            :", kinds.join(", "));
  const blob = JSON.stringify(buffer);
  console.log("  caught the error :", /TypeError/.test(blob));
  console.log("  caught the call  :", /api\/nope/.test(blob));
  console.log("  address redacted :", !/jane\.smith@des\.sc\.gov/.test(blob),
              "(in the buffer, before anything is sent)");
  console.log("  no page contents :", !/textarea|innerHTML|value=/.test(blob));

  // Opened the way the help panel opens it.
  const host = doc.createElement("div");
  doc.body.appendChild(host);
  window.renderBugForm(host, { onBack: () => {}, onSent: () => {} });
  await new Promise((r) => setTimeout(r, 300));
  console.log("\nthe form:");
  console.log("  opened           :", !!doc.getElementById("bugHappened"));
  console.log("  asks two things  :",
    !!doc.getElementById("bugExpected") && !!doc.getElementById("bugHappened"));
  // The event manifest was removed at the client's request — "people don't care
  // what gets sent to us". The consent it carried now rides on the one line
  // under the heading, so that is what is checked. What is *captured* did not
  // change, and the assertions above still prove it.
  console.log("  no manifest      :", !doc.querySelector(".bug-attached"));
  const note = ((host.querySelector(".g-sub") || {}).textContent || "")
    .replace(/\s+/g, " ").trim();
  console.log("  still says why   :", /already attached/i.test(note));

  console.log("\nrefuses an empty report:");
  doc.getElementById("bugSend").dispatchEvent(
    new window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 300));
  const err = doc.getElementById("bugError");
  console.log("  ", err && !err.hidden ? err.textContent : "ACCEPTED — wrong");
}

/* Exit explicitly. notify.js starts a 60-second polling interval that is never
   cleared — right in a browser, and enough to keep Node alive forever. */
main().then(() => process.exit(0))
      .catch((e) => { console.error(e); process.exit(1); });
