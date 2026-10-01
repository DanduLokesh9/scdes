/* The four things asked for on 24 September, driven in a real page.

   1. "Don't see your governmental unit?" on the state panel, through
      registration with no email domain, to a header naming the unit itself.
   2. The beta notice after signing in: shown, read, recorded, reopenable.
   3. The Subscriptions admin screen renders, and asks for a reference.
   4. The Framework screen no longer tells anybody to switch capacity in a
      header control that does not exist.

   The registration check creates a real, self-described organization in the
   local server's tenancy store, so this refuses to run against anything but
   a local server. Every run uses a fresh address, so reruns do not collide.

   Usage:  node tools/check_brett_requests.js      (local server must be running)
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";
if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(BASE)) {
  console.error("Refusing to run against " + BASE + " — this registers a " +
                "real organization. Local servers only.");
  process.exit(2);
}

const failures = [];
function check(label, ok, detail) {
  console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(54)} ${detail || ""}`);
  if (!ok) failures.push(label);
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

async function boot(extraFetch) {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  window.fetch = async (u, o) => {
    const url = u.startsWith("http") ? u : BASE + u;
    if (extraFetch) {
      const faked = extraFetch(url, o);
      if (faked) return { json: async () => faked, ok: true };
    }
    const r = await fetch(url, o);
    return { json: () => r.json(), ok: r.ok };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  const mem = {};
  Object.defineProperty(window, "localStorage", { value: {
    getItem: (k) => (k in mem ? mem[k] : null),
    setItem: (k, v) => { mem[k] = String(v); },
    removeItem: (k) => { delete mem[k]; } } });
  const thrown = [];
  window.addEventListener("error", (e) => thrown.push(String(e.message)));
  // One evaluation, not one per file. In a browser every classic script
  // shares one global scope, and launcher.js calls app.js's `post` — which
  // is invisible across separate `eval`s, so the launcher's fetches failed
  // here with "Could not reach the server" while working in a real page.
  const files = ["assets/launcher.js", "assets/tour.js", "assets/bugs.js",
                 "assets/guide.js", "assets/builder.js", "assets/app.js"];
  try { window.eval(files.map(read).join("\n;\n")); }
  catch (e) { thrown.push(`the scripts threw at load: ${e.message}`); }
  const doc = window.document;
  for (let i = 0; i < 60 && !doc.querySelector(".st[data-code]"); i++) {
    await wait(150);
  }
  // Boot navigates on its own and finishes when its last request returns;
  // wait for the view to stop changing so it does not paint over ours.
  let last = null;
  for (let i = 0; i < 24; i++) {
    const now = text(doc.getElementById("view"));
    if (now && now === last) break;
    last = now;
    await wait(250);
  }
  return { window, doc, thrown };
}

const text = (n) => ((n && n.textContent) || "").replace(/\s+/g, " ").trim();
const click = (window, n) =>
  n.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));

async function main() {
  /* ------------------------------------------------ 1. the unlisted door */

  console.log("\n=== Don't see your governmental unit? ===");
  const a = await boot();
  const { window, doc } = a;

  const tx = doc.querySelector('.st[data-code="TX"]');
  click(window, tx);
  await wait(500);
  const door = doc.getElementById("lnchUnlisted");
  check("the state panel offers the door", !!door, text(door));
  check("it is worded as an invitation", /Create your framework anyway/
        .test(text(door)));

  click(window, door);
  await wait(300);
  const heading = text(doc.getElementById("signinTitle"));
  check("the form opens", !!doc.getElementById("unUnit"));
  check("its heading is not the state's own agency",
        !/Texas Commission/.test(heading), heading);
  const hint = doc.getElementById("unUnit").getAttribute("aria-describedby");
  check("the name field's help is tied to it", hint === "unUnitHint");
  check("it says plainly that no domain is checked",
        /no\s+email domain is required/.test(text(doc.getElementById("signinPanel"))));

  // A listed agency's name is refused and pointed at the list.
  const fill = (id, v) => { doc.getElementById(id).value = v; };
  fill("unUnit", "Texas Commission on Environmental Quality");
  fill("unName", "Jane Doe"); fill("unTitle", "General Manager");
  const email = `jane.doe.${Date.now()}@example.test`;
  fill("unEmail", email); fill("unPhone", "713-555-0100");
  doc.getElementById("unAttest").checked = true;
  click(window, doc.getElementById("unGo"));
  await wait(700);
  const refusal = text(doc.getElementById("unError"));
  check("a listed agency's name is refused", /on our list/.test(refusal),
        refusal.slice(0, 70));

  // A real unlisted unit goes through, to the code screen.
  const unit = `Harris County MUD No. ${String(Date.now()).slice(-4)}`;
  fill("unUnit", unit);
  click(window, doc.getElementById("unGo"));
  await wait(900);
  const codeBox = doc.getElementById("verCode");
  check("it reaches the verification code", !!codeBox,
        text(doc.querySelector(".signin-lede")).slice(0, 60));
  const shown = text(doc.querySelector(".signin-code b"));
  check("the local server shows the code (no mail here)", /^\d{6}$/.test(shown),
        shown);

  if (codeBox && /^\d{6}$/.test(shown)) {
    codeBox.value = shown;
    click(window, doc.getElementById("verGo"));
    await wait(1200);
    // The NDA stands between verifying and the product, for everybody.
    const accept = doc.getElementById("ndaYes");
    if (accept) {
      click(window, accept);
      await wait(1500);
    }
    const short = text(doc.getElementById("agencyShort"));
    const crumb = text(doc.getElementById("agencyCrumb"));
    check("the header names the unit, not the state's agency",
          crumb === unit, `${short} / ${crumb}`);
    check("and never Texas's environmental agency",
          !/Texas Commission|TCEQ/.test(short + " " + crumb));

    // 2. The beta notice appears after signing in.
    console.log("\n=== the beta notice ===");
    const veil = doc.getElementById("betaVeil");
    check("it appears after signing in", !!veil);
    if (veil) {
      const card = veil.querySelector(".beta-card");
      check("it is a labeled dialog",
            card.getAttribute("role") === "dialog"
            && card.getAttribute("aria-labelledby") === "betaTitle");
      check("the dialog takes focus, not the button",
            doc.activeElement === card);
      check("it says it is a beta", /beta/i.test(text(card)));
      check("it points at the real reporting control",
            /Report an issue/.test(text(card))
            && !/Report a bug/.test(text(card)));
      click(window, doc.getElementById("betaOk"));
      await wait(600);
      check("pressing I understand closes it", !doc.getElementById("betaVeil"));

      // A reload in the same session does not bring it back.
      await window.showBetaNotice();
      await wait(300);
      check("the same session is not asked twice",
            !doc.getElementById("betaVeil"));

      // The chip reopens it on purpose.
      click(window, doc.getElementById("betaChip"));
      await wait(400);
      check("the Beta chip reopens it", !!doc.getElementById("betaVeil"));
      const again = doc.getElementById("betaOk");
      if (again) click(window, again);
      await wait(300);
    }
  }
  if (a.thrown.length) {
    console.log("  errors:", a.thrown.join(" | "));
    failures.push("the sign-in page threw");
  }

  /* ------------------------------------------ 3. the Subscriptions screen */

  console.log("\n=== the Subscriptions admin screen ===");
  const FIXTURE = {
    ok: true, pending: 1, override: true, findings: [],
    plan: { amount_set: false },
    orders: [{ id: "ORD-abc123", state: "pending", route: "invoice",
               route_label: "Purchase order and invoice", amount: 0,
               amount_set: false, currency: "USD", term_months: 12,
               raised_at: "2026-09-24T10:00:00+00:00",
               raised_by: "Brett Butz", reference: "", agency: "iia.test",
               agency_label: "DEMO agency — Innovative Infrastructure Advising",
               note: "" }],
    entitlements: [],
  };
  const b = await boot((url) =>
    url.includes("/api/billing/admin") ? FIXTURE : null);
  for (let tries = 0; tries < 3; tries++) {
    try { await b.window.go("subscriptions"); } catch (e) {
      b.thrown.push("go(subscriptions): " + e.message);
    }
    await wait(700);
    if (text(b.doc.getElementById("viewTitle")) === "Subscriptions") break;
  }
  const view = text(b.doc.getElementById("view"));
  check("it renders the waiting order", /DEMO agency/.test(view));
  check("it says the modules are forced open here",
        /forced open on this installation/.test(view));
  const settle = b.doc.querySelector('[data-settle="ORD-abc123"]');
  check("each order has a Mark paid button", !!settle);
  const label = b.doc.querySelector('label[for="ref-ORD-abc123"]');
  check("the reference field is labeled", !!label, text(label));
  if (settle) {
    click(b.window, settle);
    await wait(200);
    const toast = text(b.doc.getElementById("toast"));
    check("marking paid without a reference is stopped on screen",
          /payment reference is required/.test(toast), toast.slice(0, 60));
  }
  if (b.thrown.length) {
    console.log("  errors:", b.thrown.join(" | "));
    failures.push("the admin page threw");
  }

  /* --------------------------------- 4. no dead capacity-switch instruction */

  console.log("\n=== the Framework screen ===");
  const source = read("assets/app.js");
  check("no screen tells anybody to switch capacity in the header",
        !/Switch capacity\s+in the header/.test(source));

  console.log(failures.length
    ? `\n${failures.length} problem(s): ${failures.join(", ")}`
    : "\nall good");
  process.exit(failures.length ? 1 : 0);
}

main();
