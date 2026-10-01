/* Does the Oversight screen work as a screen?

     1. A decision records with only its one line, and lands on the list.
     2. The kind cards change the questions, not the list.
     3. The two views are a real tablist that arrow keys move between.
     4. It names no other organization's incident levels.

   Writes to the harness container; refuses anything but a local server.
       $env:IIA_SUBSCRIPTION = "1"; node tools/check_oversight_ui.js
*/

const { boot, settle, until, reporter, openView } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const said = () => doc.getElementById("view").textContent.replace(/\s+/g, " ");
  const q = (s) => doc.querySelector(s);

  console.log("the screen");
  check("it opens", await openView(window, "oversight", /Decisions recorded/), said().slice(0, 100));
  for (const l of ["Asked for, not yet decided", "Conditions still open",
                   "Conditions past their date", "Roles held by one person"]) {
    check(`counter: ${l}`, said().includes(l));
  }
  check("the adoption line is there", /Adopted|No framework adopted yet/.test(said()));
  check("the watch says what it cannot do", /cannot tell whether a meeting happened/.test(said()));
  check("no other organization's incident levels", !/Level 2|SCDES|Monitoring register/.test(said()));
  check("the concentration tile is not a link",
    ![...doc.querySelectorAll("[data-ov-go]")].some((b) => /Roles held/.test(b.textContent)));

  console.log("\nrecording one");
  const line = `Harness decided ${Date.now().toString(36)}`;
  q("#ovNew").click();
  await until(() => q("#ov-what"));
  q("#ov-save").click();
  await settle(300);
  check("the one required line is asked for in words",
    /Say what was decided/.test(q("#ov-what-err").textContent));
  const fw = q('[name="ov-kind"][value="kind.framework"]');
  fw.checked = true; fw.dispatchEvent(new window.Event("change"));
  check("a kind card opens its own questions", !!q('[name="ov-fw"]'));
  const tool = q('[name="ov-kind"][value="kind.tool"]');
  tool.checked = true; tool.dispatchEvent(new window.Event("change"));
  q("#ov-what").value = line;
  q("#ov-save").click();
  check("it lands on the list", await until(() => said().includes(line)));
  check("with no outcome it reads Not decided yet",
    [...doc.querySelectorAll("#ovList tr")].some((r) => r.textContent.includes(line)
      && /Not decided yet/.test(r.textContent)));

  console.log("\nthe two views");
  const tab = q("#ovTab-decisions");
  check("the views are a tablist", q('[role="tablist"]') && tab.getAttribute("role") === "tab");
  tab.dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
  check("the arrow key moves to Conditions", await until(() =>
    q("#ovTab-conditions") && q("#ovTab-conditions").getAttribute("aria-selected") === "true"));
  check("and its panel shows", !q("#ovPanel-conditions").hidden);

  finish(errors, "decisions record with one line, the views are a tablist, nothing borrowed");
}

main().catch((e) => { console.error(e); process.exit(1); });
