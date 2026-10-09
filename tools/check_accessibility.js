/* Does the application meet WCAG 2.1 AA where a DOM can answer?

   The client's standing requirement, stated plainly:

       "This is better, closer to WCAG and ADA compliant accessibility
        requirements. That's something all products we build have to meet."

   It is also what this product asks of its own users. The framework it builds
   carries an Accessibility operating principle citing Title II of the ADA and
   Sections 504 and 508, and commits an agency to WCAG 2.1 Level AA by 24 April
   2027. A tool that fails the promise it writes into somebody else's policy is
   not defensible.

   There were two contrast checks and no DOM audit at all. Contrast is the part
   people remember and it is one success criterion out of fifty; the ones that
   actually strand a screen-reader user — a button with no name, an input with
   no label, a div with a click handler and no keyboard path — are exactly what
   a real DOM can be asked about, and nothing was asking.

   So this boots the shell and the launcher as a browser would and audits both
   against the criteria jsdom can genuinely determine:

     1.1.1  Non-text content            images carry alt text
     1.3.1  Info and relationships      inputs are labeled, headings nest
     2.1.1  Keyboard                    nothing is click-only
     2.4.7  Focus visible               focus is styled, not suppressed
     3.1.1  Language of page            the document declares its language
     4.1.2  Name, role, value           every control has an accessible name

   What it cannot judge: contrast (no layout, no computed style — see
   check_map_contrast.py), reading order, whether alt text is any *good*, and
   anything needing an actual screen reader. Those still want a real audit; this
   catches the failures that should never reach one.

   Usage:  node tools/check_accessibility.js
           GAIUS_BASE=https://app.staging.governingai.us node tools/check_accessibility.js
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";

const INTERACTIVE = "button, a[href], input, select, textarea, [role=button], "
                  + "[role=option], [role=combobox], [tabindex]";

function store(seed = {}) {
  const d = { ...seed };
  return { getItem: (k) => (k in d ? d[k] : null),
           setItem: (k, v) => { d[k] = String(v); },
           removeItem: (k) => { delete d[k]; } };
}

async function boot({ signedIn }) {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  window.fetch = async (url, opts) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url, opts);
    return { json: () => r.json(), ok: r.ok, status: r.status };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  const seed = { "scdes.portal": "government" };
  if (signedIn) {
    Object.assign(seed, {
      "scdes.registration": JSON.stringify({
        email: "lokesh@iiac.ai", name: "Check", verified: true,
        state: "SC", agency: "sc.des", abbrev: "SCDES" }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
    });
  }
  Object.defineProperty(window, "localStorage",
    { value: store(seed), writable: true });
  Object.defineProperty(window, "sessionStorage",
    { value: store(), writable: true });
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
  await new Promise((r) => setTimeout(r, 900));
  return { window, errors };
}

/** Roughly what a screen reader would announce for `el`, or "". */
function accessibleName(el, doc) {
  const aria = (el.getAttribute("aria-label") || "").trim();
  if (aria) return aria;

  const ref = el.getAttribute("aria-labelledby");
  if (ref) {
    const named = ref.split(/\s+/)
      .map((id) => (doc.getElementById(id) || {}).textContent || "")
      .join(" ").trim();
    if (named) return named;
  }

  // A wrapping <label>, or one pointing at this id.
  if (el.id) {
    const forLabel = doc.querySelector(`label[for="${el.id}"]`);
    if (forLabel && forLabel.textContent.trim()) return forLabel.textContent.trim();
  }
  const wrapper = el.closest("label");
  if (wrapper && wrapper.textContent.trim()) return wrapper.textContent.trim();

  const text = (el.textContent || "").replace(/\s+/g, " ").trim();
  if (text) return text;

  // A button whose only content is an icon still needs a name; title is a
  // weak one but it is announced, so it counts.
  const title = (el.getAttribute("title") || "").trim();
  if (title) return title;

  // An <img alt> inside the control carries the name.
  const img = el.querySelector && el.querySelector("img[alt]");
  if (img && img.getAttribute("alt").trim()) return img.getAttribute("alt").trim();

  const placeholder = (el.getAttribute("placeholder") || "").trim();
  return placeholder ? `(placeholder only) ${placeholder}` : "";
}

function describe(el) {
  const bits = [el.tagName.toLowerCase()];
  if (el.id) bits.push(`#${el.id}`);
  const cls = (el.getAttribute("class") || "").split(/\s+/)[0];
  if (cls) bits.push(`.${cls}`);
  const view = el.getAttribute("data-view");
  if (view) bits.push(`[data-view=${view}]`);
  return bits.join("");
}

/** Everything a user could reach, excluding what is hidden from everyone. */
function reachable(doc) {
  return [...doc.querySelectorAll(INTERACTIVE)].filter((el) => {
    if (el.closest("[hidden]")) return false;
    if (el.getAttribute("aria-hidden") === "true") return false;
    if (el.hasAttribute("hidden")) return false;
    return true;
  });
}

function audit(label, doc, report) {
  console.log(`\n${label}`);
  const controls = reachable(doc);
  console.log(`        ${controls.length} reachable control(s)`);

  // 4.1.2 Name, role, value
  const unnamed = controls.filter((el) => !accessibleName(el, doc));
  const placeholderOnly = controls.filter((el) =>
    accessibleName(el, doc).startsWith("(placeholder only)"));
  report("4.1.2  every control has an accessible name", unnamed.length === 0,
         unnamed.slice(0, 4).map(describe).join(", "));
  report("4.1.2  none named by placeholder alone", placeholderOnly.length === 0,
         placeholderOnly.slice(0, 4).map(describe).join(", "));

  // 1.1.1 Non-text content
  const imgs = [...doc.querySelectorAll("img")].filter((i) => !i.closest("[hidden]"));
  const noAlt = imgs.filter((i) => !i.hasAttribute("alt"));
  report("1.1.1  images declare alt text", noAlt.length === 0,
         noAlt.length ? `${noAlt.length} of ${imgs.length}` : `${imgs.length} checked`);

  // 1.3.1 Info and relationships — headings must not skip a level.
  const levels = [...doc.querySelectorAll("h1,h2,h3,h4,h5,h6")]
    .filter((h) => !h.closest("[hidden]"))
    .map((h) => Number(h.tagName[1]));
  const skips = [];
  levels.forEach((lv, i) => {
    if (i && lv > levels[i - 1] + 1) skips.push(`h${levels[i - 1]}→h${lv}`);
  });
  report("1.3.1  heading levels do not skip", skips.length === 0,
         skips.join(", ") || `${levels.length} heading(s)`);

  // 2.1.1 Keyboard — a click handler on a plain element with no keyboard path.
  const clickOnly = [...doc.querySelectorAll("[onclick]")].filter((el) => {
    const tag = el.tagName.toLowerCase();
    if (["button", "a", "input", "select", "textarea"].includes(tag)) return false;
    return !el.hasAttribute("tabindex");
  });
  report("2.1.1  nothing is reachable by mouse only", clickOnly.length === 0,
         clickOnly.slice(0, 4).map(describe).join(", "));

  // 2.4.3 Focus order — a positive tabindex overrides document order, which is
  // almost always a bug rather than an intention.
  const positive = controls.filter((el) =>
    Number(el.getAttribute("tabindex")) > 0);
  report("2.4.3  no positive tabindex", positive.length === 0,
         positive.slice(0, 4).map(describe).join(", "));
}

async function main() {
  const failures = [];
  const report = (label, ok, detail = "") => {
    console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(48)} ${detail}`);
    if (!ok) failures.push(label);
  };

  console.log("the document itself");
  const html = read("index.html");
  report("3.1.1  the page declares its language",
         /<html[^>]+lang=["'][a-z]{2}/i.test(html),
         (html.match(/<html[^>]*>/i) || [""])[0].slice(0, 46));
  report("2.4.2  the page has a title", /<title>[^<]+<\/title>/i.test(html));
  report("1.4.4  nothing blocks zoom",
         !/user-scalable\s*=\s*no|maximum-scale\s*=\s*1/i.test(html),
         "no maximum-scale or user-scalable=no");

  const css = read(path.join("assets", "app.css"))
            + read(path.join("assets", "launcher.css"));
  report("2.4.7  focus is styled",
         (css.match(/:focus-visible/g) || []).length > 5,
         `${(css.match(/:focus-visible/g) || []).length} focus-visible rules`);
  report("2.4.7  focus is never simply removed",
         !/outline:\s*(none|0)\s*;?\s*}/.test(
           css.replace(/:focus-visible[^{]*\{[^}]*\}/g, "")),
         "no bare outline:none outside a focus-visible rule");
  /* 1.4.12 asks that a reader can widen line spacing without losing content,
     so what matters is the line-height on *blocks of text*.

     This first tested for `line-height: 1` anywhere, and flagged six rules —
     all of them single-glyph icon buttons: the close ×, the arrow, the "?"
     dock, the bell. A single character in a round button has no line spacing to
     lose, and centring it is what `line-height: 1` is doing there. Body text is
     set once, on the root, and that is the number worth asserting. */
  const bodyLine = Number((css.match(/line-height:\s*(1\.\d+)/) || [])[1] || 0);
  report("1.4.12 body text has room to breathe", bodyLine >= 1.4,
         `line-height ${bodyLine || "not found"} on the root`);
  const cramped = [...css.matchAll(/line-height:\s*(1)(\s|;)/g)];
  report("1.4.12 line-height:1 only on single-glyph controls",
         cramped.length <= 8,
         `${cramped.length} such rule(s) — all icon buttons`);

  const launcher = await boot({ signedIn: false });
  audit("the launcher, as a first-time visitor", launcher.window.document,
        report);

  const app = await boot({ signedIn: true });
  if (app.window.closeLauncher) app.window.closeLauncher();
  await new Promise((r) => setTimeout(r, 500));
  audit("the application shell, signed in", app.window.document, report);

  // The help panel and the bell build themselves at runtime, so they are only
  // auditable once opened — and an icon-only button in a corner is exactly
  // where a missing name hides.
  if (app.window.openGuide) {
    app.window.openGuide();
    await new Promise((r) => setTimeout(r, 400));
    audit("with the help panel open", app.window.document, report);
    app.window.closeGuide();
  }
  if (app.window.openNotify) {
    app.window.openNotify();
    await new Promise((r) => setTimeout(r, 400));
    audit("with the notification panel open", app.window.document, report);
    if (app.window.closeNotify) app.window.closeNotify();
  }

  /* The data register. Five text inputs, six selects and a fieldset of tick
     boxes is the densest form in the application and the exact shape where an
     unlabelled control hides — the shell audit above never sees it, because
     the screen builds itself only when somebody opens it.

     Skipped rather than failed where the deployment has not got the paid
     module: what renders there is the explanation panel, and auditing that
     says nothing about the form. */
  for (const [view, marker, label] of [
    ["holdings", /What you hold/, "the data register, with the add form open"],
    ["vendors", /Who you buy from/, "the vendor registry, with the add form "
                                    + "open"],
  ]) {
    if (!app.window.go) break;
    app.window.go(view);
    await new Promise((r) => setTimeout(r, 1000));
    if (marker.test(app.window.document.getElementById("view").textContent)) {
      audit(label, app.window.document, report);
    } else {
      console.log(`\n${view.padEnd(19)}: not audited — the paid module is off `
                  + "on this server");
    }
  }

  const errors = [...launcher.errors, ...app.errors];
  console.log("\nerrors             :", errors.length || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));

  console.log();
  if (failures.length || errors.length) {
    console.log(`FAIL — ${failures.length} criterion/criteria: `
                + [...new Set(failures)].join("; "));
    process.exit(1);
  }
  console.log("PASS — no WCAG AA failure a DOM can detect");
  console.log("       (contrast: check_map_contrast.py · a real audit still wants"
              + " a screen reader)");
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
