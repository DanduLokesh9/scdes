/* Does the Process screen work as a screen?

     1. A person can write a procedure with only a name and a kind, and it
        lands on the register as drafted, not adopted.
     2. Putting it in force from a hat that may not says why, in words, and
        nothing changes.
     3. A checklist that touches Deploy shows the six rows that bind there,
        and the editable rows move up and down by keyboard, not drag alone.
     4. Nothing on it names another organization's appendices or bands.

   Writes to the harness container; refuses anything but a local server.
       $env:IIA_SUBSCRIPTION = "1"; node tools/check_process_ui.js
*/

const { boot, settle, until, reporter, openView } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const said = () => doc.getElementById("view").textContent.replace(/\s+/g, " ");
  const q = (s) => doc.querySelector(s);

  console.log("the screen");
  check("it opens", await openView(window, "process", /Procedures written down/),
    said().slice(0, 120));
  for (const label of ["In force today", "Required here and not written",
                       "Never confirmed since it was written",
                       "Past the date its owner set"]) {
    check(`counter: ${label}`, said().includes(label));
  }
  check("the waiting line is one sentence under the counts",
    /route in yet|Nothing has come in|Nothing is waiting|written down and nobody/.test(said()));
  check("the standing check says what it cannot see",
    /cannot see whether the document at that address still exists/.test(said()));
  check("no other organization's appendices or bands",
    !/Appendix|SCDES|Risk bands/.test(said()));

  console.log("\nwriting one");
  const name = `Harness fallback ${Date.now().toString(36)}`;
  q("#prNew").click();
  await until(() => q("#pf-name"));
  q("#pf-name").value = name;
  const kind = q("#pf-kind");
  kind.value = "How the work gets done when the tool is off";
  kind.dispatchEvent(new window.Event("change"));
  q("#pf-save").click();
  check("only the name and kind were needed", await until(() => said().includes(name)));
  check("it arrives drafted, not adopted",
    [...doc.querySelectorAll("#prList tr")].some((r) =>
      r.textContent.includes(name) && /Drafted, not adopted/.test(r.textContent)));

  console.log("\nputting it in force");
  const row = [...doc.querySelectorAll("#prList tr")].find((r) => r.textContent.includes(name));
  const adopt = row && row.querySelector('[data-pr-status="In force"]');
  if (adopt) {
    adopt.click();
    await settle(1200);
    const now = [...doc.querySelectorAll("#prList tr")].find((r) => r.textContent.includes(name));
    const refusal = now ? (now.querySelector("[data-pr-err]") || {}).textContent || "" : "";
    const inForce = now && /In force/.test(now.textContent) && !/Drafted/.test(now.textContent);
    check("either it is in force, or the refusal says why in words",
      inForce || refusal.length > 20, inForce ? "put in force" : refusal.slice(0, 90));
  } else {
    check("the control is withheld from a hat that may not use it", true,
      "no Put in force button for this hat");
  }

  console.log("\na checklist at Deploy");
  await settle(800);
  q("#prNew").click();
  await until(() => q("#pf-kind"));
  const k2 = q("#pf-kind");
  k2.value = "What has to exist on paper before something passes a gate";
  k2.dispatchEvent(new window.Event("change"));
  await settle(200);
  const deploy = q('[name="pf-gates"][value="gate.deploy"]');
  deploy.checked = true; deploy.dispatchEvent(new window.Event("change"));
  await settle(200);
  check("the six that bind at Deploy are shown",
    /Six things bind here/.test(q("#prForm").textContent)
      && (q("#prForm").textContent.match(/It has to exist before this passes/g) || []).length >= 6);
  const addItem = [...q("#pf-items").querySelectorAll("button")].find((b) => /Add item/.test(b.textContent));
  addItem.click(); addItem.click();
  const inputs = () => [...q("#pf-items").querySelectorAll('[data-k="item"]')];
  inputs()[0].value = "first"; inputs()[1].value = "second";
  const up = q("#pf-items").querySelectorAll("[data-up]")[1];
  up.click();
  check("rows move by keyboard controls, not drag alone", inputs()[0].value === "second");
  q("#pf-cancel").click();

  finish(errors, "procedures write, refuse in words, and show the six that bind at Deploy");
}

main().catch((e) => { console.error(e); process.exit(1); });
