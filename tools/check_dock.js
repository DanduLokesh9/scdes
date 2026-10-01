/* Can the help dock be moved, and does it still work as a button?

   Asked for as "I want to drag this help icon anywhere on the screen" — "It's
   fixed and not moving." Dragging something that is also a button is the part
   that goes wrong: either the drag never starts, or every press moves it a
   pixel and stops opening the panel. So this drives both, plus the two failure
   modes that made the old draggable dock a liability — a position saved on a
   big monitor stranding it off the edge of a small one, and the panel staying
   in the corner after the dock has left.

   jsdom does no layout, so the rail and the panel are given real geometry by
   hand. That is the point rather than a workaround: it means the placement
   arithmetic is exercised with numbers instead of the zeros a headless DOM
   would otherwise feed it.

   Usage:  node tools/check_dock.js
           GAIUS_BASE=https://app.staging.governingai.us node tools/check_dock.js
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
           removeItem: (k) => { delete d[k]; }, _d: d };
}

async function boot(local) {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  window.fetch = async (url, opts) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url, opts);
    return { json: () => r.json(), ok: r.ok, status: r.status };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage", { value: local, writable: true });
  Object.defineProperty(window, "sessionStorage", { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.performance = window.performance || { now: () => Date.now() };
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  for (const f of ["bugs.js", "dock.js", "guide.js", "notify.js", "onboard.js",
                   "welcome.js", "tour.js", "launcher.js", "speech.js",
                   "builder.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f}: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 80; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  if (window.closeLauncher) window.closeLauncher();
  await new Promise((r) => setTimeout(r, 700));
  return { window, errors };
}

/** Give an element a real box, since jsdom gives everything zeros. */
function box(el, { w, h }) {
  Object.defineProperty(el, "offsetWidth", { value: w, configurable: true });
  Object.defineProperty(el, "offsetHeight", { value: h, configurable: true });
  el.getBoundingClientRect = () => {
    const left = parseFloat(el.style.left || "0");
    const top = parseFloat(el.style.top || "0");
    return { left, top, width: w, height: h,
             right: left + w, bottom: top + h, x: left, y: top };
  };
}

const at = (el) => `${Math.round(parseFloat(el.style.left || "0"))},`
                 + `${Math.round(parseFloat(el.style.top || "0"))}`;

function mouse(target, type, x, y, w) {
  target.dispatchEvent(new w.MouseEvent(type, {
    bubbles: true, cancelable: true, clientX: x, clientY: y }));
}

/** Press on `on`, travel to (x,y), let go — then the click the browser sends. */
function drag(on, x, y, w) {
  mouse(on, "mousedown", 0, 0, w);
  mouse(w.document, "mousemove", x, y, w);
  mouse(w.document, "mouseup", x, y, w);
  mouse(on, "click", x, y, w);
}

async function main() {
  const local = store({
    "scdes.registration": JSON.stringify({ email: "dev@iiac.ai", name: "Dev",
      verified: true, state: "SC", agency: "sc.des", abbrev: "SCDES" }),
    "scdes.welcomeSeen": "1", "scdes.tour": "seen", "scdes.portal": "government",
  });

  console.log("1. the dock");
  let { window, errors } = await boot(local);
  let doc = window.document;
  const rail = doc.getElementById("dockRail");
  console.log("   rail present     :", !!rail);
  console.log("   holds both       :",
    !!rail.querySelector("#notifyDock") && !!rail.querySelector("#guideDock"));
  const css = read(path.join("assets", "app.css"));
  const orderOf = (sel) =>
    (css.match(new RegExp(`\\${sel} \\{[^}]*order: (\\d)`)) || [])[1];
  console.log("   bell left of ?   :",
    Number(orderOf(".notify-dock")) < Number(orderOf(".guide-dock"))
      ? `yes (bell order ${orderOf(".notify-dock")}, `
        + `? order ${orderOf(".guide-dock")})` : "NO");

  console.log("\n2. a plain press still opens the panel");
  doc.getElementById("guideDock").dispatchEvent(
    new window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 250));
  console.log("   panel opened     :", !!doc.getElementById("guidePanel"));
  window.closeGuide();

  console.log("\n3. dragging moves it");
  box(rail, { w: 112, h: 50 });
  drag(doc.getElementById("guideDock"), 240, 180, window);
  await new Promise((r) => setTimeout(r, 120));
  console.log("   moved to         :", at(rail));
  console.log("   one element      :",
    rail.contains(doc.getElementById("notifyDock"))
      && rail.contains(doc.getElementById("guideDock")),
    "(both buttons are inside it, so they cannot separate)");
  console.log("   remembered       :", local.getItem("scdes.dock"));

  console.log("\n4. the press that ends a drag does not open the panel");
  console.log("   panel opened     :", !!doc.getElementById("guidePanel"),
              "(must be false)");

  console.log("\n5. it comes back where it was left");
  ({ window, errors } = await boot(local));
  doc = window.document;
  const again = doc.getElementById("dockRail");
  box(again, { w: 112, h: 50 });
  await new Promise((r) => setTimeout(r, 120));
  console.log("   restored to      :", at(again));

  console.log("\n6. a spot off the edge of a smaller screen is pulled back");
  local.setItem("scdes.dock", JSON.stringify({ x: 4000, y: 3000 }));
  const small = await boot(local);
  const sRail = small.window.document.getElementById("dockRail");
  box(sRail, { w: 112, h: 50 });
  small.window.dispatchEvent(new small.window.Event("resize"));
  await new Promise((r) => setTimeout(r, 120));
  const W = small.window.innerWidth, H = small.window.innerHeight;
  console.log(`   window is        : ${W}x${H}`);
  console.log("   saved at         : 4000,3000");
  console.log("   restored to      :", at(sRail),
    `(furthest allowed ${W - 112 - 12},${H - 50 - 12})`);
  const [rx, ry] = at(sRail).split(",").map(Number);
  console.log("   on screen        :",
    rx >= 12 && rx <= W - 112 - 12 && ry >= 12 && ry <= H - 50 - 12);

  console.log("\n7. the panel follows the dock");
  small.window.document.getElementById("guideDock").dispatchEvent(
    new small.window.MouseEvent("click", { bubbles: true }));
  await new Promise((r) => setTimeout(r, 250));
  const panel = small.window.document.getElementById("guidePanel");
  box(panel, { w: 392, h: 420 });
  // Dock low on the screen: the panel has to go above it.
  sRail.style.left = "600px"; sRail.style.top = "700px";
  small.window.placeDockPanel(panel);
  console.log("   dock at 600,700  → panel at", at(panel),
    Number(at(panel).split(",")[1]) < 700 ? "(above it)" : "(BELOW — wrong)");
  // Dock at the top: there is no room above, so it must go below.
  sRail.style.left = "600px"; sRail.style.top = "20px";
  small.window.placeDockPanel(panel);
  console.log("   dock at 600,20   → panel at", at(panel),
    Number(at(panel).split(",")[1]) > 20 ? "(below it)" : "(ABOVE — wrong)");
  console.log("   right edges align:",
    Math.round(parseFloat(panel.style.left)) + 392 === 600 + 112);

  console.log("\nerrors             :", errors.length || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));
}

main().then(() => process.exit(0))
      .catch((e) => { console.error(e); process.exit(1); });
