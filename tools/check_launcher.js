/* Run the launcher against a real DOM and report what actually happens.

   Written because the flag pop-up "not working" was diagnosed three times by
   reading the code and guessing, each time wrongly. This loads the real page,
   the real scripts and the real registry, clicks a state, and prints the
   resulting state of the DOM — so a claim about the cause can be checked.

   Usage:  node tools/check_launcher.js            (server must be running)
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");

const BASE = "http://127.0.0.1:8765";

async function main() {
  const html = read("index.html");
  const dom = new JSDOM(html, {
    runScripts: "outside-only",
    pretendToBeVisual: true,
    url: BASE + "/",
  });
  const { window } = dom;

  // Serve fetches out of the running server so the registry and map are real.
  window.fetch = async (url) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url);
    return { json: () => r.json(), ok: r.ok };
  };
  // jsdom does not lay anything out, so every box is 0×0. Give the elements the
  // app measures a plausible geometry, or positioning cannot be exercised.
  const rect = (x, y, w, h) => () => ({
    x, y, width: w, height: h, top: y, left: x,
    right: x + w, bottom: y + h, toJSON() {},
  });

  // jsdom implements neither of these; the launcher uses both.
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  if (!window.localStorage) {
    window.localStorage = { getItem: () => null, setItem() {} };
  }

  // Collect anything the page throws, rather than letting it vanish the way it
  // does in a browser console nobody has open.
  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  window.onunhandledrejection = (e) => errors.push("unhandled: " + e.reason);

  for (const file of ["assets/launcher.js", "assets/tour.js", "assets/app.js"]) {
    try {
      window.eval(read(file));
    } catch (e) {
      errors.push(`${file} threw at load: ${e.message}`);
    }
  }
  // Let app.js's boot finish; it initialises the launcher itself. Generous,
  // because boot now makes several round trips (registry, map, roster, state).
  for (let i = 0; i < 40 && !window.document.getElementById("flagPop"); i++) {
    await new Promise((r) => setTimeout(r, 150));
  }
  await new Promise((r) => setTimeout(r, 300));

  const doc = window.document;
  const report = {};
  const pop = doc.getElementById("flagPop");
  const wrap = doc.getElementById("mapWrap");
  report["#flagPop exists"] = !!pop;
  report["#mapWrap exists"] = !!wrap;
  report["states rendered"] = doc.querySelectorAll(".st").length;

  if (!pop) {
    console.log(report);
    console.log("\n=== errors thrown by the page ===");
    console.log(errors.length ? errors.map((e) => "  " + e).join("\n") : "  none");
    return;
  }

  // Geometry: map area 1000×600 at (40, 200); the target state a box inside it.
  wrap.getBoundingClientRect = rect(40, 200, 1000, 600);
  Object.defineProperty(pop, "offsetWidth", { value: 144, configurable: true });
  Object.defineProperty(pop, "offsetHeight", { value: 96, configurable: true });

  const sc = doc.querySelector('.st[data-code="SC"]');
  if (sc) sc.getBoundingClientRect = rect(700, 480, 60, 45);

  report["flag hidden before click"] = pop.hidden;

  if (sc) sc.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));

  report["flag hidden after click"] = pop.hidden;
  report["flag img src"] = (pop.querySelector("img") || {}).getAttribute
    ? pop.querySelector("img").getAttribute("src") : "(no img)";
  report["flag caption"] = (pop.querySelector("figcaption") || {}).textContent;
  report["flag style.left"] = pop.style.left || "(unset)";
  report["flag style.top"] = pop.style.top || "(unset)";
  report["flag classes"] = pop.className;

  // Click the same state a second time — the reported failure.
  if (sc) sc.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  report["hidden after 2nd click"] = pop.hidden;
  report["left after 2nd click"] = pop.style.left || "(unset)";

  // Double-click must lead to the sign-in step, not straight into the record.
  const launcher = doc.getElementById("launcher");
  report["map open before dblclick"] = !launcher.hidden;
  if (sc) sc.dispatchEvent(new window.MouseEvent("dblclick", { bubbles: true }));

  const signin = doc.getElementById("signinPanel");
  report["sign-in shown"] = signin && !signin.hidden;
  report["map still open"] = !launcher.hidden;
  report["people offered"] = signin
    ? signin.querySelectorAll(".signin-who").length : 0;
  report["names honest about auth"] =
    (signin && signin.textContent.includes("does not verify identity")) || false;

  // Signing in closes the picker and enters the application.
  const go = doc.getElementById("signinGo");
  if (go) go.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  // Signing in refreshes state and re-renders a view before closing, so give it
  // longer than a single tick.
  for (let i = 0; i < 20 && !launcher.hidden; i++) {
    await new Promise((r) => setTimeout(r, 150));
  }
  report["closed after signing in"] = launcher.hidden;
  report["signed in as"] = (doc.getElementById("userPick") || {}).value || "(none)";

  // Apply the real stylesheets and read back what the flag actually computes
  // to. The logic can be perfect and the element still invisible.
  const style = doc.createElement("style");
  style.textContent = read("assets/brand/tokens.css") + "\n" +
                      read("assets/app.css") + "\n" +
                      read("assets/launcher.css");
  doc.head.appendChild(style);

  const cs = window.getComputedStyle(pop);
  for (const prop of ["display", "position", "z-index", "opacity",
                      "visibility", "pointer-events"]) {
    report[`computed ${prop}`] = cs[prop] || "(empty)";
  }
  const wrapCs = window.getComputedStyle(wrap);
  report["mapwrap position"] = wrapCs.position || "(empty)";

  // Paint order between the flag and the map: with equal z-index the later
  // sibling wins, so DOM order matters.
  const kids = [...wrap.children].map((n) => n.tagName.toLowerCase() +
    (n.id ? "#" + n.id : ""));
  report["mapwrap children"] = kids.join(" then ");

  console.log("\n=== launcher check ===");
  for (const [k, v] of Object.entries(report)) {
    console.log(`  ${k.padEnd(28)} ${v}`);
  }
  console.log("\n=== errors thrown by the page ===");
  console.log(errors.length ? errors.map((e) => "  " + e).join("\n")
                            : "  none");
}

main().catch((e) => { console.error("HARNESS ERROR:", e.message); process.exit(1); });
