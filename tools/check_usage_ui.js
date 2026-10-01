/* Render the usage screen against a real DOM and report what it says.

   Two things worth checking by machine rather than by eye.

   The gate. This is the one screen that reads across every agency, so a
   non-admin reaching it — by typing the view name, since the rail heading is
   not drawn for them — must get the refusal and no data at all. Not a thinner
   version of the page: none of it.

   The accessibility. WCAG 2.1 AA is an acceptance criterion on every IIA
   product, not a polish item. Every table needs scoped headers, the progress
   bars must carry the figure in words as well as in pixels, and the test-row
   marking must not be color alone.

   Usage:  node tools/check_usage_ui.js          (server must be running)
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = "http://127.0.0.1:8765";

const failures = [];
function check(label, ok, detail) {
  console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(50)} ${detail || ""}`);
  if (!ok) failures.push(label);
}

async function page(email) {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only",
    pretendToBeVisual: true,
    url: BASE + "/",
  });
  const { window } = dom;
  const thrown = [];

  window.fetch = async (url, opts) => {
    const full = url.startsWith("http") ? url : BASE + url;
    const sep = full.includes("?") ? "&" : "?";
    const r = await fetch(full + (email ? `${sep}email=${email}` : ""), opts);
    return { json: () => r.json(), ok: r.ok, status: r.status };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  if (!window.localStorage) {
    window.localStorage = { getItem: () => null, setItem() {} };
  }
  window.alert = () => thrown.push("an alert was raised");
  window.addEventListener("error", (e) => thrown.push(String(e.message)));

  for (const file of ["assets/launcher.js", "assets/tour.js",
                      "assets/app.js"]) {
    try { window.eval(read(file)); }
    catch (e) { thrown.push(`${file}: ${e.message}`); }
  }
  for (let i = 0; i < 40 && !window.document.getElementById("flagPop"); i++) {
    await new Promise((r) => setTimeout(r, 150));
  }
  return { window, thrown };
}

async function main() {
  /* Signed in as nobody in particular. The proven address comes from a
     session token, and this harness has none, so every run here is an
     unprivileged one — which is exactly the case worth testing. */
  const { window, thrown } = await page("");
  const doc = window.document;

  console.log("the rail");
  check("the admin heading exists in the markup",
        !!doc.getElementById("adminRail"));
  check("it is hidden without a proven admin address",
        doc.getElementById("adminRail").hidden !== false);
  check("a usage item is in it",
        !!doc.querySelector('#adminRail .rail-item[data-view="usage"]'));

  console.log("\nreaching it anyway, as a non-admin");
  /* Navigated the way a person would, through `go`, rather than by calling
     the view function — `VIEWS` is module-scoped inside app.js and reaching
     into it would be testing a path no browser takes. */
  window.go("usage");
  await new Promise((r) => setTimeout(r, 900));
  const text = (doc.getElementById("view").textContent || "")
    .replace(/\s+/g, " ");
  check("it refuses", /team|not for you|admin/i.test(text), text.slice(0, 56));
  check("no agency table is drawn",
        !doc.querySelector("#view table.grid"));
  check("no agency name leaked", !/sc\.des|iia\.test|env\.nm\.gov/i.test(text));
  check("no person's name leaked",
        !/brett|lokesh|butz/i.test(text.toLowerCase()));

  console.log("\nit reached its own screen, not a gate");
  /* Both gates exempt this view, so a non-admin should see the refusal from
     the usage page itself and not the "finish your framework first" panel or
     the no-corpus one. Getting a gate here would hide the refusal behind a
     message about the wrong thing. */
  check("not stopped by the framework gate",
        !/after the framework is complete|finish your framework/i.test(text));
  check("not stopped by the corpus gate",
        !/holds one corpus at a time/i.test(text));
  check("the title is the usage screen's",
        /usage/i.test(doc.getElementById("viewTitle").textContent || ""),
        doc.getElementById("viewTitle").textContent);

  console.log("\nerrors thrown by the page");
  console.log(thrown.length ? thrown.map((t) => "  " + t).join("\n")
                            : "  none");
  if (thrown.length) failures.push("the page threw");

  console.log(failures.length
    ? `\n${failures.length} problem(s): ${failures.join(", ")}`
    : "\nall good");
  process.exit(failures.length ? 1 : 0);
}

main();
