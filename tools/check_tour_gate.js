/* The walkthrough waits until the person is registered and signed in.

   Reported (BUG-F379A222): on a first visit "step 1 of 8" appeared over the
   welcome and registration cards, before the person could register or see
   the application it was explaining.

     1. A first-time visitor, not registered: no tour, however long they wait
        or wherever they click.
     2. Signed in, nothing covering the application: the tour is offered.

   jsdom has no layout, so the tour cannot draw its spotlight here; this
   watches whether it is *started*, which is the decision being fixed.
       node tools/check_tour_gate.js
*/

const { boot, settle, until, reporter, harnessSession } = require("./_jsdom_boot");

async function walk(storage) {
  // jsdom lays nothing out, so every element measures 0×0 and the tour — which
  // skips steps whose target is not visible — would have nothing to show.
  // Giving elements a size lets the real tour run; whether it opened is then
  // read off the page, and counted each time it goes from shut to open.
  const before = (window) => {
    window.Element.prototype.getBoundingClientRect = () =>
      ({ x: 0, y: 0, top: 0, left: 0, width: 120, height: 24, right: 120, bottom: 24 });
    // "First use" is remembered per person on the server, and the harness has
    // had the tour in earlier runs — so this walk presents somebody who has
    // not, and holds the note that they now have.
    const real = window.fetch;
    window.fetch = async (url, opts) => {
      const u = String(url);
      if (u.includes("/api/me/tour-seen")) return { ok: true, status: 200, json: async () => ({ ok: true }) };
      const r = await real(url, opts);
      if (!u.includes("/api/state")) return r;
      const body = await r.json();
      return { ok: r.ok, status: r.status, json: async () => ({ ...body, tour_seen: false }) };
    };
  };
  const { window, errors } = await boot({ storage, before });
  let opened = 0, was = false;
  const tick = setInterval(() => {
    const t = window.document.getElementById("tour");
    const now = !!t && !t.hidden;
    if (now && !was) opened += 1;
    was = now;
  }, 50);
  return { window, errors, started: () => opened, stop: () => clearInterval(tick) };
}

async function main() {
  const { check, finish } = reporter();

  console.log("a first-time visitor");
  const fresh = await walk({});
  await settle(2500);
  const doc = fresh.window.document;
  doc.body.dispatchEvent(new fresh.window.MouseEvent("click", { bubbles: true }));
  const onb = doc.getElementById("onboard"), wel = doc.getElementById("welcome");
  if (onb) onb.hidden = true;
  if (wel) wel.hidden = true;
  doc.getElementById("launcher").hidden = true;
  doc.body.classList.remove("launcher-open");
  await settle(2500);
  check("no tour before registering, even with nothing covering the screen",
    fresh.started() === 0, `started ${fresh.started()}`);

  console.log("\nsigned in");
  const SESSION = await harnessSession();
  const inside = await walk({
    // The harness's own container, as every other walk signs in — minus the
    // "tour already seen" the default storage carries.
    "scdes.registration": JSON.stringify({ email: "walk@harness.gaius.test",
      name: "Automated walk", verified: true, state: "SC", agency: "gaius.harness",
      abbrev: "HARNESS",
      // The harness is on no state's list, so it is described the way an
      // unlisted unit is — otherwise resuming the session cannot place it and
      // the home page is shown instead, which is right for a real person.
      unlisted: true, agencyName: "GAIUS harness" }),
    "scdes.welcomeSeen": "1", "scdes.portal": "government",
    // Signed in for real: a remembered address alone now goes to Log in.
    "scdes.session": SESSION,
    // And this sign-in has acknowledged the disclaimer, which comes first.
    "gaius.beta": `${SESSION}|seen` });
  const d2 = inside.window.document;
  d2.getElementById("launcher").hidden = true;
  d2.body.classList.remove("launcher-open");
  ["onboard", "welcome"].forEach((id) => { const n = d2.getElementById(id); if (n) n.hidden = true; });
  check("the tour is offered once they are in", await until(() => inside.started() === 1, 5000),
    `started ${inside.started()}`);
  await settle(2500);
  const esc = new inside.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true });
  d2.dispatchEvent(esc);
  await settle(2500);
  check("and only once", inside.started() === 1, `started ${inside.started()}`);
  fresh.stop(); inside.stop();

  finish([...fresh.errors, ...inside.errors], "the walkthrough waits until the person is signed in");
}

main().catch((e) => { console.error(e); process.exit(1); });
