/* Does the Audit trail screen work as a screen?

     1. It shows this organization's own trail, with the five counters, the
        seal check and what the trail cannot see.
     2. Something recorded from elsewhere lands on the trail and says so.
     3. A correction lands beside the entry it corrects, and the entry is
        unchanged.
     4. Nothing on it is a count of anybody's activity or a reading log.

   Writes to the harness container; refuses anything but a local server.
       node tools/check_audit_ui.js
*/

const { boot, settle, until, reporter, openView } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const said = () => doc.getElementById("view").textContent.replace(/\s+/g, " ");
  const q = (s) => doc.querySelector(s);

  console.log("the screen");
  check("it opens", await openView(window, "audit", /Entries in the trail/), said().slice(0, 100));
  for (const l of ["Recorded after it happened", "Nothing said about why", "Corrections recorded",
                   "Versions of your framework in this trail"]) check(`counter: ${l}`, said().includes(l));
  check("the seal check is on the page", /Every entry carries a fingerprint/.test(said()));
  check("and what it cannot prove", /It is not a notarization/.test(said()));
  check("reading is not logged, and it says so", /A log of reading is a trap/.test(said()));

  console.log("\nrecording something from elsewhere");
  const what = `Harness board vote ${Date.now().toString(36)}`;
  q("#atElsewhere").click();
  await until(() => q("#at-what"));
  q("#at-save").click();
  await settle(200);
  check("the one line is asked for in words", /Say what happened/.test(q("#at-what-err").textContent));
  q("#at-what").value = what;
  q("#at-happened").value = "2026-01-05";
  q("#at-save").click();
  check("it lands on the trail", await until(() => said().includes(what)));
  const row = () => [...doc.querySelectorAll("#atList tr")].find((r) => r.textContent.includes(what));
  check("marked as recorded by a person from elsewhere", /Recorded by a person, from somewhere else/.test(row().textContent));
  check("with both dates", /happened 2026-01-05/.test(row().textContent));

  console.log("\ncorrecting it");
  row().querySelector("[data-at-correct]").click();
  await until(() => q("#at-wrong"));
  check("the consequence is stated before the button", /does not remove or alter the entry above/.test(q("#atForm").textContent));
  q("#at-wrong").value = "The date was the fifth of February";
  q("#at-corrsave").click();
  const landed = await until(() => /correction was recorded against an earlier entry/i.test(said()));
  check("the correction lands beside it", landed,
    landed ? "" : ((q("#at-correrr") || {}).textContent || said().slice(0, 120)));
  check("and the entry itself is still there, unchanged", /happened 2026-01-05/.test(row().textContent));

  finish(errors, "the trail is this organization's own, records from elsewhere, and corrects without editing");
}

main().catch((e) => { console.error(e); process.exit(1); });
