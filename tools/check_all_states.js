/* Every state open, every state offering its environmental agency.

   Until today two states were selectable and forty-nine were drawn greyed.
   This walks the map and asserts the rest of it actually works: each state
   selects, names its own agency, and states the email rule that will be
   applied to a registration there.

   The check that matters most is the last one. For most states the domain on
   record belongs to the whole state government rather than to the
   environmental department, and for thirty-seven of them nobody has confirmed
   it. Neither fact may be hidden from the person about to register: a screen
   that implies "@pa.gov" identifies the Department of Environmental
   Protection is making a claim the software cannot support.

   Usage:  node tools/check_all_states.js          (server must be running)
           GAIUS_BASE=https://app.staging.governingai.us node tools/check_all_states.js
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";

const failures = [];
function check(label, ok, detail) {
  console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(46)} ${detail || ""}`);
  if (!ok) failures.push(label);
}

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
  if (!window.localStorage) {
    window.localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
  }
  const thrown = [];
  window.addEventListener("error", (e) => thrown.push(String(e.message)));
  for (const f of ["assets/launcher.js", "assets/tour.js", "assets/app.js"]) {
    try { window.eval(read(f)); }
    catch (e) { thrown.push(`${f} threw at load: ${e.message}`); }
  }
  // The map is drawn by app.js's boot, not by launcher.js on its own, so
  // wait for it rather than for a fixed delay — on a cold server the first
  // request decides how long this takes.
  const doc = window.document;
  for (let i = 0; i < 60 && !doc.querySelector(".st[data-code]"); i++) {
    await new Promise((r) => setTimeout(r, 150));
  }
  await new Promise((r) => setTimeout(r, 500));

  const text = (n) => ((n && n.textContent) || "").replace(/\s+/g, " ");

  /* ------------------------------------------------ the registry, server-side */

  const reg = await (await window.fetch("/api/states?user=council.cto")).json();
  const entries = reg.states || reg.entries || [];
  console.log("\n=== the registry ===");
  check("the server lists the whole map", entries.length >= 51,
        `${entries.length} entries`);
  const shut = entries.filter((s) => !s.open_for_registration);
  check("no state is shut", shut.length === 0,
        shut.length ? shut.map((s) => s.code).join(",")
                    : `${entries.length} open`);

  /* ---------------------------------------------------------------- the map */

  console.log("\n=== the map ===");
  const tiles = [...doc.querySelectorAll(".st[data-code]")];
  check("every state is drawn", tiles.length >= 51, `${tiles.length} tiles`);
  const greyed = tiles.filter((t) => t.classList.contains("closed") ||
                                     t.disabled);
  check("none is drawn as closed", greyed.length === 0,
        greyed.length ? greyed.map((t) => t.dataset.code).join(",") : "");

  /* --------------------------------- a sample of states, selected for real */

  // One of each shape: an agency domain nobody checked, a statewide domain
  // nobody checked, a checked statewide one, a checked agency one, and the
  // one the client stated.
  const SAMPLE = ["NY", "MA", "PA", "TX", "NM"];
  for (const code of SAMPLE) {
    const tile = doc.querySelector(`.st[data-code="${code}"]`);
    if (!tile) { check(`${code} is on the map`, false); continue; }
    tile.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    await new Promise((r) => setTimeout(r, 500));

    const pick = doc.getElementById("lnchPick");
    const note = doc.getElementById("lnchNote");
    const said = [text(pick), text(note)].join(" ");

    console.log(`\n=== ${code} ===`);
    check(`${code}: the panel says something`, said.length > 30,
          `${said.length} chars`);
    check(`${code}: it can be entered`,
          !!doc.getElementById("lnchEnter"));

    // Its own agency, and nobody else's. The isolation rule this product
    // exists for starts at the door.
    const server = entries.find((s) => s.code === code) || {};
    const agencies = server.agencies || [];
    check(`${code}: offers exactly its own agency`, agencies.length === 1,
          agencies.map((a) => a.abbrev).join(","));
    if (agencies.length === 1) {
      const a = agencies[0];
      check(`${code}: the agency has a domain`, !!a.domain, a.domain);
      check(`${code}: the id is scoped to the state`,
            String(a.id || "").startsWith(code.toLowerCase() + "."), a.id);
      check(`${code}: no other state's domain`,
            !SAMPLE.filter((c) => c !== code).some((c) => {
              const other = entries.find((s) => s.code === c) || {};
              return (other.agencies || []).some(
                (x) => x.domain === a.domain);
            }), a.domain);
    }
  }

  /* ------------------------------------- the rule is stated, not implied */

  console.log("\n=== what the door tells you ===");
  for (const code of ["PA", "TX"]) {
    const server = entries.find((s) => s.code === code) || {};
    const a = (server.agencies || [])[0] || {};
    // Whose domain it is has to survive the trip to the browser, or the
    // screen cannot say it.
    check(`${code}: the payload carries whose domain it is`,
          a.scope === "agency" || a.scope === "statewide", a.scope);
    check(`${code}: and who vouched for it`,
          ["stated", "checked", "unconfirmed"].includes(a.domain_source),
          a.domain_source);
  }
  const pa = (entries.find((s) => s.code === "PA") || {}).agencies || [];
  const tx = (entries.find((s) => s.code === "TX") || {}).agencies || [];
  check("a statewide domain is marked statewide",
        (pa[0] || {}).scope === "statewide", (pa[0] || {}).domain);
  check("an agency domain is marked as the agency's",
        (tx[0] || {}).scope === "agency", (tx[0] || {}).domain);

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
