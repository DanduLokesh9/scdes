/* Does the reporter find out when someone acts on their bug?

   The loop the panel opens and this closes: report a fault, it goes quiet, and
   without the bell the only way to learn whether anybody looked is to go
   hunting for the ticket.

   Walks it end to end — file a report, have the team reply, check the bell
   lights for the right person and stays dark for everyone else, then reopen
   from the notification.

   Usage:  node tools/check_notify.js
           GAIUS_BASE=https://app.staging.governingai.us node tools/check_notify.js
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";
const REPORTER = "notify.check@iiac.ai";
const STRANGER = "someone.else@iiac.ai";

/* Both the bell and the bug queue now want a proved address, so this harness
   has to hold real sessions — one for the reporter, one to play the team.

   Obtained the way a person obtains one: ask for a code, read it, verify. The
   first version minted them straight out of the tenancy store, which worked
   locally and produced tokens the *staging* server had never issued, so every
   run against a deployment failed at the reopen step with a null form and no
   hint why. Going through the real endpoints costs two extra requests and works
   against anything.

   It relies on SMTP being unconfigured, which is why the code comes back in the
   response at all. When email is finally wired up this check needs another way
   in — and that is the right moment to notice, because at that point the demo
   path has changed too. */
const SESSIONS = new Map();

async function sessionFor(email) {
  if (SESSIONS.has(email)) return SESSIONS.get(email);

  const post = async (p, body) => {
    const r = await fetch(BASE + p, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body) });
    return r.json();
  };

  // Already a member: a code is all that is needed. Otherwise join the shared
  // test container, which is what it exists for — every @iiac.ai address is a
  // tester, so this is the documented path rather than a way round anything.
  let asked = await post("/api/agency/signin", { email });
  if (!asked.ok || !asked.code) {
    asked = await post("/api/agency/register", {
      agency: "iia.test", name: "Notification check", title: "Harness",
      email, phone: "(843) 555 0100", attested: true });
  }
  if (!asked.code) {
    throw new Error(`could not get a code for ${email}: `
                    + (asked.error || JSON.stringify(asked).slice(0, 120)));
  }
  const done = await post("/api/agency/verify", { email, code: asked.code });
  if (!done.session) {
    throw new Error(`could not verify ${email}: ${done.error || "no session"}`);
  }
  SESSIONS.set(email, done.session);
  return done.session;
}

let ADMIN_TOKEN = "";

const api = async (p, body) => {
  const headers = { "Content-Type": "application/json",
                    "X-GAIUS-Session": ADMIN_TOKEN };
  const r = await fetch(BASE + p + (p.includes("?") ? "&" : "?") + "user=sean.ot",
    body ? { method: "POST", headers, body: JSON.stringify(body) }
         : { headers });
  return r.json();
};

function store(seed = {}) {
  const d = { ...seed };
  return { getItem: (k) => (k in d ? d[k] : null),
           setItem: (k, v) => { d[k] = String(v); },
           removeItem: (k) => { delete d[k]; } };
}

async function boot(email) {
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
      { email, name: "Check", verified: true,
        state: "SC", agency: "sc.des", abbrev: "SCDES" }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
      "scdes.portal": "government",
      // A real session, because the bell no longer answers to an address alone.
      // Seeding a fake string here would test the refusal, not the loop.
      "scdes.session": SESSIONS.get(email) || "" }), writable: true });
  Object.defineProperty(window, "sessionStorage", { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.performance = window.performance || { now: () => Date.now() };
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  window.onunhandledrejection = (e) => errors.push("unhandled: " + e.reason);
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
  await new Promise((r) => setTimeout(r, 800));
  return { window, errors };
}

const click = (el, w) =>
  el && el.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));

async function main() {
  // Sessions first: every boot below seeds one into localStorage, and the api()
  // helper needs the admin's before it can answer a ticket.
  ADMIN_TOKEN = await sessionFor("brett@iiac.ai");
  await sessionFor(REPORTER);
  await sessionFor(STRANGER);

  console.log("1. the reporter files something");
  const filed = await api("/api/bugs/report", {
    happened: "The gate review would not save.",
    expected: "It to save.",
    context: { view: "Lifecycle", version: "check" },
    events: [{ kind: "error", at: new Date().toISOString(),
               text: "TypeError: notify check" }],
    reporter: REPORTER, name: "Check", agency: "SCDES",
  });
  console.log(`   ${filed.id}`);
  if (filed.id) FILED.push(filed.id);

  console.log("\n2. before anyone answers, the bell is quiet");
  let { window, errors } = await boot(REPORTER);
  let doc = window.document;
  console.log("   bell present    :", !!doc.getElementById("notifyDock"));
  // jsdom does no layout, so the rendered position cannot be measured. Both
  // buttons now sit in one flex rail that drags as a unit (dock.js), so the
  // stylesheet's `order` is what decides which is on the left — and unlike the
  // old fixed `right` offsets, it survives the dock being moved.
  const css = await (await fetch(BASE + "/assets/app.css")).text();
  const order = (sel) =>
    (css.match(new RegExp(`\\${sel} \\{[^}]*order: (\\d)`)) || [])[1];
  console.log("   in the same rail:",
    !!doc.querySelector("#dockRail #notifyDock")
    && !!doc.querySelector("#dockRail #guideDock"));
  console.log("   left of the ?   :",
    Number(order(".notify-dock")) < Number(order(".guide-dock"))
      ? `yes (bell order ${order(".notify-dock")}, `
        + `help order ${order(".guide-dock")})`
      : `NO (bell ${order(".notify-dock")}, help ${order(".guide-dock")})`);
  await window.pollNotifications();
  // Measured as a change, not as an absolute. This harness files a real report
  // against whatever server it is pointed at and there is no way to delete one
  // afterward, so earlier runs are still in the store and "unread must be 0"
  // was only ever true the first time it ran. What it should prove is that
  // answering *this* report produced exactly one more notification.
  const before = window.notifyUnread();
  console.log("   unread          :", before, "(whatever earlier runs left)");
  console.log("   nothing yet for :", filed.id,
    !window.notifyItems || !window.notifyItems().some((i) => i.id === filed.id));

  console.log("\n3. the team replies and marks it fixed");
  await api("/api/bugs/respond", { id: filed.id, status: "fixed",
                                   message: "Fixed in this morning's deploy." });

  console.log("\n4. the reporter's bell lights");
  ({ window, errors } = await boot(REPORTER));
  doc = window.document;
  await window.pollNotifications();
  const nowUnread = window.notifyUnread();
  console.log("   unread          :", nowUnread,
    `(was ${before} — ${nowUnread === before + 1 ? "one more, correct"
                                                 : "WRONG, expected one more"})`);
  console.log("   newest is ours  :",
    (window.notifyItems()[0] || {}).id === filed.id);
  const badge = doc.querySelector("#notifyDock .n-badge");
  console.log("   badge shows     :", badge && !badge.hidden ? badge.textContent
                                                             : "nothing");

  click(doc.getElementById("notifyDock"), window);
  await new Promise((r) => setTimeout(r, 300));
  console.log("   panel opened    :", !!doc.getElementById("notifyPanel"));
  const item = doc.querySelector(".n-item");
  console.log("   says            :",
    item ? item.textContent.replace(/\s+/g, " ").trim().slice(0, 88) : "nothing");
  console.log("   offers reopen   :", !!doc.querySelector("[data-reopen]"));
  console.log("   marked read     :", window.notifyUnread() === 0);

  console.log("\n5. somebody else's bell stays dark");
  const other = await boot(STRANGER);
  await other.window.pollNotifications();
  console.log("   unread          :", other.window.notifyUnread(),
              "(must be 0)");

  console.log("\n6. reopening from the notification");
  click(doc.querySelector("[data-reopen]"), window);
  await new Promise((r) => setTimeout(r, 250));
  doc.getElementById("nReason").value = "Still will not save for me.";
  click(doc.getElementById("nSend"), window);
  await new Promise((r) => setTimeout(r, 700));
  console.log("   panel says      :",
    (doc.querySelector(".g-h") || {}).textContent);
  const after = await api(`/api/bugs?status=&q=${filed.id}`);
  const ticket = (after.tickets || []).find((t) => t.id === filed.id);
  console.log("   ticket status   :", ticket && ticket.status,
              "· reopened", ticket && ticket.reopened, "time(s)");

  console.log("\nerrors             :", errors.length || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));
}

/* Exit explicitly. Each booted page starts a 60-second polling interval that is
   never cleared — correct in a browser, and enough to keep Node alive forever
   once three of them exist. */
/* Tidy up after itself, including the ticket.

   This check files a genuine report every run — that is the point, it is
   testing the real path — and for a while it left one behind every time. A
   dozen "The gate review would not save." rows accumulated in the queue twice,
   next to reports from actual people, and each round had to be swept by hand
   with a shell on the server. That does not work against a deployment nobody
   has a shell on, so the queue grew a way to delete a ticket instead
   (/api/bugs/forget), and this uses it. */
const FILED = [];

const retire = async () => {
  for (const id of FILED) {
    try { await api("/api/bugs/forget", { id, why: "filed by check_notify.js" }); }
    catch (e) {}
  }
  for (const token of SESSIONS.values()) {
    try {
      await fetch(BASE + "/api/session/end", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session: token }) });
    } catch (e) {}
  }
};

main()
  .then(async () => { await retire(); process.exit(0); })
  .catch(async (e) => { console.error(e); await retire(); process.exit(1); });
