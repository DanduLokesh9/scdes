/* Does Next move you through the intro?

   The button there said Skip and called endWelcome() — the same thing Continue
   does. Two controls, one behavior, and no way to read at your own pace. This
   clicks Next through every segment and checks the slide actually changes, that
   the last one disables it, and that Continue still exits.

   Usage:  node tools/check_welcome.js
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");

function main() {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true,
    url: "http://127.0.0.1:8765/",
  });
  const { window } = dom;
  const data = {};
  Object.defineProperty(window, "localStorage", {
    value: { getItem: (k) => (k in data ? data[k] : null),
             setItem: (k, v) => { data[k] = String(v); },
             removeItem: (k) => { delete data[k]; } },
    writable: true,
  });

  const errors = [];
  try {
    window.eval(read(path.join("assets", "welcome.js")));
  } catch (e) {
    console.log("welcome.js threw at load:", e.message);
    return 1;
  }

  let done = false;
  window.startWelcome(() => { done = true; });

  const doc = window.document;
  const click = (id) => {
    const b = doc.getElementById(id);
    if (b) b.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    return !!b;
  };
  const title = () =>
    (doc.querySelector(".wel-card h2, .wel-card h1, .wel-title") || {})
      .textContent || (doc.querySelector(".wel-card") || {}).textContent
      .slice(0, 40);
  const dot = () => [...doc.querySelectorAll(".wel-dots i")]
    .findIndex((n) => n.classList.contains("on"));

  console.log("controls          :",
    [...doc.querySelectorAll(".wel-actions button")]
      .map((b) => b.textContent.trim().split(/\s+/)[0]).join(", "));
  console.log("no Skip button    :", !doc.getElementById("welSkip"));

  const seen = [];
  for (let i = 0; i < 8; i++) {
    seen.push(dot());
    const btn = doc.getElementById("welNext");
    if (!btn || btn.disabled) break;
    click("welNext");
  }
  console.log("segments visited  :", seen.join(" → "));
  console.log("advanced properly :",
    seen.length > 1 && seen.every((v, i) => i === 0 || v === seen[i - 1] + 1));

  const last = doc.getElementById("welNext");
  console.log("Next on last slide:", last ? (last.disabled ? "disabled" : "STILL LIVE")
                                          : "missing");

  console.log("intro ended early :", done, "(should be false)");
  click("welGo");
  console.log("Continue exits    :", done);
  if (errors.length) console.log("errors:", errors.join(" | "));
  return 0;
}

process.exit(main());
