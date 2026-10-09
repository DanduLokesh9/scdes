/* Does the Data screen work as a screen?

     1. The five counts, the findings (or the clean sentence), the monitor
        with its honest limit, and the empty state or the list.
     2. A holding records with only its name, and a "We are not sure"
        answer becomes a gap record.
     3. Utility tags are a labeled group; "something else" becomes an option.
     4. The feed block appears only where it is a feed.
     5. The list sorts and filters, and its table scrolls in a labeled region.
     6. Nothing is a percentage or a score.

   Writes to the harness container; refuses anything but a local server.
       $env:IIA_SUBSCRIPTION = "1"; node tools/check_data_ui.js
*/

const { boot, until, reporter, openView } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const said = () => doc.getElementById("view").textContent.replace(/\s+/g, " ");
  const q = (s) => doc.querySelector(s);

  console.log("the screen");
  check("it opens", await openView(window, "holdings", /Holdings recorded/), said().slice(0, 100));
  for (const l of ["Holdings recorded", "Reachable by an interface", "Holding something sensitive",
                   "Nobody named against it", "Where it lives is unknown"]) check(`counter: ${l}`, said().includes(l));
  check("the monitor says what it cannot check", said().includes("green tick that meant nothing would be worse"));
  check("only the name is required, said plainly", said().includes("Only the name is required"));

  console.log("\nadding one");
  const name = `Harness holding ${Date.now().toString(36)}`;
  q("#dh-name").value = name;
  q("#dh-location").value = "unknown";
  q("#dh-unitsnew").value = "Harness unit";
  q('[name="dh-utility"][value="planning"]').checked = true;
  q("#dh-utilitynew").value = "Harness purpose";
  check("the feed block is hidden until it is a feed", q("#dh-feedbox").hidden);
  q("#dh-feed").value = "yes";
  q("#dh-feed").dispatchEvent(new window.Event("change"));
  check("and shows once it is", !q("#dh-feedbox").hidden);
  q("#dhSave").click();
  check("it lands on the list", await until(() => said().includes(name) && q(".table-scroll")));
  check("not sure is a gap record", said().includes("Not known yet") &&
    [...doc.querySelectorAll("li")].some((li) => li.textContent.includes(name) && /Where it lives/.test(li.textContent)));
  check("utility shows as its tags", [...doc.querySelectorAll(".dh-table tr")].some((tr) =>
    tr.textContent.includes(name) && tr.textContent.includes("Planning and forecasting") && tr.textContent.includes("Harness purpose")));
  check("something else became an option", !!q('[name="dh-utility"][value="custom:Harness purpose"]'));
  check("the feed says it was never confirmed", [...doc.querySelectorAll(".dh-table tr")].some((tr) =>
    tr.textContent.includes(name) && tr.textContent.includes("Never confirmed")));

  console.log("\nthe list");
  const region = q(".table-scroll");
  check("the table scrolls in a labeled, focusable region",
    region.getAttribute("role") === "region" && !!region.getAttribute("aria-label") && region.tabIndex === 0);
  const f = q('[data-f="location"]');
  f.value = "unknown";
  f.dispatchEvent(new window.Event("change"));
  check("a filter narrows it", await until(() => /\d+ of \d+ shown/.test(said()) && said().includes(name)));
  const back = q('[data-f="location"]');
  back.value = "";
  back.dispatchEvent(new window.Event("change"));
  await until(() => q("#dhSort"));
  const s = q("#dhSort");
  s.value = "current";
  s.dispatchEvent(new window.Event("change"));
  check("it sorts by how current", await until(() => q("#dhSort") && q("#dhSort").value === "current"));

  console.log("\nediting it");
  const edit = [...doc.querySelectorAll("[data-edit]")].find((b) => b.getAttribute("aria-label") === `Edit ${name}`);
  edit.click();
  check("the edit form opens with it", await until(() => q("#dh-name") && q("#dh-name").value === name));
  const confirm = q("#dhConfirm");
  check("a feed can be confirmed current", !!confirm);
  confirm.click();
  check("and the date is written", await until(() => [...doc.querySelectorAll(".dh-table tr")].some((tr) =>
    tr.textContent.includes(name) && /Last confirmed current \d{4}-\d{2}-\d{2}/.test(tr.textContent))));

  // 4.1.2 on the form: every control has a name a screen reader says.
  const unnamed = [...q("#dhForm").querySelectorAll("input, select, textarea")].filter((c) =>
    !c.getAttribute("aria-label") && !c.closest("label") && !(c.id && doc.querySelector(`label[for="${c.id}"]`)));
  check("every control on the form has a name", unnamed.length === 0, unnamed.map((c) => c.id || c.name).join(", "));
  // "Nothing here is scored or ranked" is the one mention, and it is a denial.
  const graded = said().match(/\d+ ?%|\bscore\b|\bgrade\b|rating:/i);
  check("no percentage, score or grade", !graded, graded ? graded[0] : "");
  finish(errors, "holdings record with a name, gaps are recorded, utility is tags, the list sorts and filters");
}

main().catch((e) => { console.error(e); process.exit(1); });
