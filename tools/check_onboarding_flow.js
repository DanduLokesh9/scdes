/* Brett's onboarding, Oct 2026 — the home page, the agreement, the code.

     1. A new visitor lands on the home page, with Begin and Log in.
     2. Begin opens the map.
     3. Registering shows the Terms of Use word for word. Accept stays disabled
        until the text is scrolled, the four fields are filled and the
        authority box is ticked — and Escape cannot close it.
     4. Accept records the acceptance first, and only then asks for the code.
     5. "Our counsel requires a signed agreement" asks for the signed form and
        pauses.
     6. Log in, from the home page, asks for an email and sends a code.

   Every write is held here, so nothing is recorded.
       node tools/check_onboarding_flow.js
*/

const { boot, settle, until, reporter } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot({ storage: {} });
  const doc = window.document;
  const posts = [];
  const real = window.fetch;
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (opts && opts.method === "POST") {
      const path = u.replace(/^.*\/api/, "/api").split("?")[0];
      const body = JSON.parse(opts.body || "{}");
      posts.push([path, body]);
      const reply = path === "/api/terms/accept" ? { ok: true, record: {} }
        : path === "/api/agency/register-unlisted" ? { ok: true, code: "123456", expires_in_minutes: 30,
            agency: { id: "sc.u-test-unit-ab12", name: body.unit, abbrev: "TU", state: "SC" } }
        : path === "/api/terms/signed" ? { ok: true, awaiting_signed: true, says: "The signed form has been emailed to you and to IIA." }
        : path === "/api/agency/signin" ? { ok: true, code: "654321", expires_in_minutes: 30 }
        : { ok: true };
      return { ok: true, status: 200, json: async () => reply };
    }
    return real(url, opts);
  };

  console.log("the home page");
  const home = doc.getElementById("home");
  check("a new visitor sees the home page", await until(() => home && !home.hidden));
  check("with Begin, and Log in at the top", !!doc.getElementById("homeBegin")
    && !!doc.querySelector(".home-top #homeLogin"));
  check("and not the map, or the old email screen", doc.getElementById("launcher").hidden
    && doc.getElementById("onboard").hidden);
  check("it has one main heading", doc.querySelectorAll("#home h1").length === 1);
  check("the header shows the GoverningAI.US logo, inside a named link",
    !!doc.querySelector('#home .home-brand[aria-label] .gaius-logo-word[aria-hidden="true"]'));

  doc.getElementById("homeBegin").click();
  await settle(200);
  check("Begin opens the map", home.hidden && !doc.getElementById("launcher").hidden);

  console.log("\nregistering — the agreement");
  doc.querySelector('.st[data-code="SC"]').dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await until(() => doc.getElementById("lnchUnlisted"));
  doc.getElementById("lnchUnlisted").click();
  check("the agreement card opens", await until(() => doc.getElementById("termsBody")));
  check("the agreement's heading carries the logo's G, not the old drawn one (BUG-A5DE3CCC)",
    !!doc.querySelector(".terms-head .gaius-logo-g") && !doc.querySelector(".terms-head svg"));
  const box = doc.getElementById("termsBody");
  check("the Terms are shown, word for word", /TERMS OF USE AND LICENSE AGREEMENT/.test(box.textContent)
    && /programme/.test(box.textContent) && /Attn: Brett Butz/.test(box.textContent));
  const go = doc.getElementById("tcGo");
  check("Accept starts disabled", go.disabled);
  const set = (id, v) => { const f = doc.getElementById(id); f.value = v; f.dispatchEvent(new window.Event("input")); };
  set("tcName", "Pat Lee"); set("tcTitle", "Clerk"); set("tcEmail", "pat@cityofx.net"); set("tcUnit", "City of X");
  doc.getElementById("tcAuth").click();
  check("still disabled before the agreement is scrolled", go.disabled);
  box.scrollTop = 1; box.dispatchEvent(new window.Event("scroll"));
  await settle(50);
  check("scrolling to the end says so", /read to the end/.test(doc.getElementById("termsNote").textContent));
  check("and then Accept works", !go.disabled);
  doc.getElementById("tcAuth").click();
  check("unticking authority disables it again", go.disabled);
  doc.getElementById("tcAuth").click();

  doc.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  await settle(50);
  check("Escape does not close it", !doc.getElementById("launcher").hidden && !!doc.getElementById("termsBody"));

  go.click();
  check("Accept records the acceptance, then asks for the code", await until(() => posts.length >= 2)
    && posts[0][0] === "/api/terms/accept" && posts[1][0] === "/api/agency/register-unlisted",
    JSON.stringify(posts.map((p) => p[0])));
  const accepted = posts[0][1];
  check("with every field, authority and the scroll", accepted.name === "Pat Lee" && accepted.unit === "City of X"
    && accepted.authority === true && accepted.scrolled === true && accepted.sha256 && accepted.sha256.length === 64);
  check("and the code screen follows", await until(() => doc.getElementById("verCode")));

  console.log("\nthe signed form");
  doc.getElementById("verBack").click();
  await until(() => doc.getElementById("tcSigned"));
  set("tcName", "Pat Lee"); set("tcTitle", "Clerk"); set("tcEmail", "pat@cityofx.net"); set("tcUnit", "City of X");
  doc.getElementById("tcSigned").click();
  check("it asks for the signed form", await until(() => posts.some((p) => p[0] === "/api/terms/signed")));
  check("and says the registration waits", await until(() => /on its way/.test(doc.getElementById("signinPanel").textContent)));

  console.log("\nlog in");
  window.showHome();
  doc.getElementById("homeLogin").click();
  check("Log in opens the log-in card", await until(() => doc.getElementById("liEmail")) && home.hidden);
  const logo = doc.querySelector("#signinPanel .signin-logo");
  check("it opens with the whole logo and its tagline, named for a screen reader",
    !!logo && logo.classList.contains("gaius-logo-full") && logo.getAttribute("role") === "img"
    && /Making Your Rules Authoritative/.test(logo.getAttribute("aria-label")));
  doc.getElementById("liEmail").value = "brett.butz@des.sc.gov";
  doc.getElementById("liGo").click();
  check("it sends a code with no agency picked", await until(() => posts.some((p) => p[0] === "/api/agency/signin"
    && p[1].email === "brett.butz@des.sc.gov" && !p[1].agency)));
  check("and asks for it", await until(() => doc.getElementById("verCode")));

  console.log("\nsigning in from another agency's map entry (BUG-25E4892D)");
  // Picked one thing on the map (here, "not on the list" in SC, which sets
  // the launcher's name to "Your governmental unit"); the address belongs to
  // a listed SC agency. The card's heading must name the one in the
  // Governmental unit box.
  const named = await window.eval(`(async () => {
    const reg = await fetch("/api/states?user=sean.ot").then((r) => r.json());
    const sc = reg.states.find((s) => s.code === "SC");
    await showTermsCard(sc, "gate", { email: "someone@example.gov" },
      { state: sc.agencies[0].id, agency_label: "Their own unit", allowed: true });
    return { title: document.getElementById("signinTitle").textContent,
             unit: document.getElementById("tcUnit").value,
             eyebrow: document.querySelector(".signin-eyebrow").textContent };
  })()`);
  check("the heading names their own organization, not the map pick",
    named.title === "Their own unit" && named.unit === "Their own unit",
    `heading "${named.title}", unit "${named.unit}"`);
  check("and the state above it is that organization's", named.eyebrow === "South Carolina", named.eyebrow);

  console.log("\nafter signing in");
  await window.signInAs("sean.ot", "Pat Lee", "Clerk");
  await settle(300);
  check("the 60-second welcome does not play by itself", doc.getElementById("welcome").hidden);

  window.fetch = real;
  finish(errors, "home page, agreement, code and log in behave as Brett asked");
}

main().catch((e) => { console.error(e); process.exit(1); });
