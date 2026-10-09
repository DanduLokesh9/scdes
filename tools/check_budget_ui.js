/* Does the Budget screen work as a screen?

     1. A cost line records with only its first line, and arrives open and
        not committed — the add form commits nothing.
     2. Committing from a hat that may not says why, in words.
     3. The money strip always carries its three sentences, and the screen
        says there is no lifetime total.
     4. Nothing on it is the reference agency's budget pools.

   Writes to the harness container; refuses anything but a local server.
       $env:IIA_SUBSCRIPTION = "1"; node tools/check_budget_ui.js
*/

const { boot, settle, until, reporter, openView } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const said = () => doc.getElementById("view").textContent.replace(/\s+/g, " ");
  const q = (s) => doc.querySelector(s);

  console.log("the screen");
  check("it opens", await openView(window, "budget", /Cost lines recorded/), said().slice(0, 100));
  for (const l of ["Projects with the full cost estimated", "No number against it",
                   "No cost of leaving recorded", "Costing more than estimated"]) {
    check(`counter: ${l}`, said().includes(l));
  }
  check("the three money sentences", /committed on everything you are running or trialling/.test(said())
    && /committed or not/.test(said()) && /what it would cost to leave/.test(said()));
  check("it says there is no lifetime total", /There is no lifetime total here/.test(said()));
  check("it says it is not connected to your accounting", /not connected to your accounting system/.test(said()));
  check("not the reference agency's pools", !/pool|Foundations first|SCDES/i.test(said()));

  console.log("\nrecording one");
  const line = `Harness license ${Date.now().toString(36)}`;
  q("#bgNew").click();
  await until(() => q("#bg-for"));
  q("#bg-save").click();
  await settle(300);
  check("the first line is asked for in words", /Say what this cost is for/.test(q("#bg-for-err").textContent));
  q("#bg-for").value = line;
  q("#bg-est").value = "twelve hundred";
  q("#bg-save").click();
  await settle(600);
  check("a word is refused as a number, and kept in the box",
    /could not be read as a number/.test(q("#bg-est-err").textContent) && q("#bg-est").value === "twelve hundred");
  q("#bg-est").value = "1200";
  const basis = q('[name="bg-basis"][value="year"]');
  basis.checked = true; basis.dispatchEvent(new window.Event("change", { bubbles: true }));
  q("#bg-programme").checked = true;
  q("#bg-save").click();
  check("it lands on the list", await until(() => said().includes(line)));
  const row = () => [...doc.querySelectorAll("#bgList tr")].find((r) => r.textContent.includes(line));
  check("open and not committed", /Not committed/.test(row().textContent) && /Open/.test(row().textContent));

  console.log("\ncommitting it");
  row().querySelector("[data-bg-commit]").click();
  await settle(1200);
  const now = row();
  const refusal = (now.querySelector("[data-bg-err]") || {}).textContent || "";
  check("either it commits, or the refusal says why in words",
    refusal.length > 30 || /Committed \d/.test(now.textContent),
    refusal.slice(0, 80) || "committed");
  row().querySelector('[data-bg-status="ended"]').click();
  check("an end date is a fact any hat records", await until(() => /Ended/.test(row().textContent)));

  finish(errors, "cost lines record with one line, commit is its own act, the strip says what it leaves out");
}

main().catch((e) => { console.error(e); process.exit(1); });
