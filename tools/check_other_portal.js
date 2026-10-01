/* Can a public body without a .gov-style address get in?

   Reported: a city clerk on cityofmonticello.net could not get past the
   first-visit "Register your work email" step, which took only .gov, .mil,
   .edu, .us, .org and .int. These walk a fresh browser through it.

     1. The first screen offers "Other public body" beside the government one.
     2. The government option's refusal of a .net address points to it.
     3. Other takes the city address and opens the map.
     4. The map says "Create your framework anyway" is the way in.

   The registration answer is held, so nothing is written.
       node tools/check_other_portal.js
*/

const { boot, settle, until, reporter } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot({ storage: { "scdes.welcomeSeen": "1", "scdes.tour": "seen" } });
  const doc = window.document;
  const onb = () => doc.getElementById("onboard");
  const sent = [];
  const real = window.fetch;
  window.fetch = async (url, opts) => {
    if (String(url).includes("/api/register") && !String(url).includes("register-unlisted")) {
      const body = JSON.parse(opts.body);
      sent.push(body);
      const other = body.portal === "other";
      const netAddr = /\.net$/.test(body.email);
      const ok = other || !netAddr;
      return { ok: true, status: 200, json: async () => ok
        ? { ok: true, domain: body.email.split("@")[1], evidence: other ? "other" : "restricted" }
        : { ok: false, reason: "This option needs an address ending in .gov, .mil, .edu, .us, .org, .int. "
            + "If you work for a public body whose email is on another address, go Back and choose Other public body." } };
    }
    return real(url, opts);
  };

  console.log("the first screen");
  check("it asks which kind of organization", await until(() => onb() && !onb().hidden
    && /Other public body/.test(onb().textContent)), (onb() || {}).textContent?.slice(0, 80));
  const choice = (key) => onb().querySelector(`.onb-choice[data-portal="${key}"]`);
  check("Other public body is open", !!choice("other") && !choice("other").disabled);

  console.log("\nthe government option, with a city address");
  choice("government").click();
  await until(() => doc.getElementById("onbEmail"));
  doc.getElementById("onbEmail").value = "mju@cityofmonticello.net";
  doc.getElementById("onbGo").click();
  await settle(300);
  check("it is refused, and pointed to Other public body",
    /choose Other public body/.test(doc.getElementById("onbError").textContent), doc.getElementById("onbError").textContent);
  check("the browser did not even ask the server", sent.length === 0);
  doc.getElementById("onbBack").click();
  await until(() => choice("other"));

  console.log("\nOther public body");
  choice("other").click();
  await until(() => doc.getElementById("onbEmail"));
  check("it explains the way in", /Create your framework anyway/.test(onb().textContent)
    && /on any domain/.test(onb().textContent));
  doc.getElementById("onbEmail").value = "mju@cityofmonticello.net";
  doc.getElementById("onbGo").click();
  check("the city address is accepted", await until(() => sent.length === 1 && sent[0].portal === "other"),
    JSON.stringify(sent));
  check("and the map opens", await until(() => onb().hidden));
  await until(() => doc.querySelector('.st[data-code="SC"]'));
  doc.querySelector('.st[data-code="SC"]').dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  const shown = await until(() => doc.getElementById("lnchUnlisted"));
  const card = shown ? doc.getElementById("lnchUnlisted").parentElement.textContent.replace(/\s+/g, " ") : "";
  check("the map points to Create your framework anyway",
    /You chose Other public body, so this is your way in/.test(card), card.slice(0, 120)
      + ` | portal=${window.localStorage.getItem("scdes.portal")}`);
  window.fetch = real;
  finish(errors, "a public body on any address can choose Other and reach Create your framework anyway");
}

main().catch((e) => { console.error(e); process.exit(1); });
