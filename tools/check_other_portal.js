/* Can a public body without a .gov-style address get in?

   Reported: a city clerk on cityofmonticello.net could not get past the
   first-visit "Register your work email" step, which took only .gov, .mil,
   .edu, .us, .org and .int.

   That step was retired in Oct 2026 for Brett's flow — the home page, Begin,
   the map, and the agreement card — so this walks the same clerk through
   what replaced it:

     1. A fresh browser lands on the home page, not on the old email step.
     2. Begin opens the map, and the state's list ends with Other.
     3. Other opens the agreement card with no email domain asked for.
     4. The city's .net address is accepted there: Accept and continue
        becomes available once the agreement is read and the fields filled.

   Every write is held here, so nothing is recorded.
       node tools/check_other_portal.js
*/

const { boot, settle, until, reporter } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot({ storage: {} });
  const doc = window.document;
  const posts = [];
  const real = window.fetch;
  window.fetch = async (url, opts) => {
    if (opts && opts.method === "POST") {
      posts.push(String(url));
      return { ok: true, status: 200, json: async () => ({ ok: true }) };
    }
    return real(url, opts);
  };

  console.log("a fresh browser");
  check("lands on the home page", await until(() => !doc.getElementById("home").hidden));
  check("not on the retired email step", doc.getElementById("onboard").hidden);

  doc.getElementById("homeBegin").click();
  await settle(200);
  doc.querySelector('.st[data-code="SC"]').dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  check("the map opens on Begin", await until(() => doc.getElementById("lnchUnlisted")));

  console.log("\nOther");
  doc.getElementById("lnchUnlisted").click();
  check("the agreement card opens", await until(() => doc.getElementById("tcUnit")));
  check("with no email domain asked for", !/must end in @/.test(doc.getElementById("signinPanel").textContent));
  const set = (id, v) => { const f = doc.getElementById(id); f.value = v; f.dispatchEvent(new window.Event("input")); };
  set("tcName", "Matthew Utley"); set("tcTitle", "City Clerk");
  set("tcEmail", "mju@cityofmonticello.net"); set("tcUnit", "City of Monticello");
  const body = doc.getElementById("termsBody");
  body.scrollTop = 1; body.dispatchEvent(new window.Event("scroll"));
  doc.getElementById("tcAuth").click();
  await settle(50);
  check("the city's .net address is accepted by the form", !doc.getElementById("tcGo").disabled
    && doc.getElementById("tcError").hidden);
  check("and nothing was sent before Accept", posts.length === 0, posts.join(" "));

  window.fetch = real;
  finish(errors, "a public body on any address gets in through Begin, Other and the agreement");
}

main().catch((e) => { console.error(e); process.exit(1); });
