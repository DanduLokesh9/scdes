/* Does the Vision screen work as a screen?

     1. A goal records with only its one sentence and appears under its
        horizon heading, with its portfolio line in words.
     2. The planning-document upload is offered first, as the spec asks.
     3. Nothing on it is a progress figure, a pillar or a maturity table.

   Writes to the harness container; refuses anything but a local server.
       $env:IIA_SUBSCRIPTION = "1"; node tools/check_vision_ui.js
*/

const { boot, until, reporter, openView } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const said = () => doc.getElementById("view").textContent.replace(/\s+/g, " ");
  const q = (s) => doc.querySelector(s);

  console.log("the screen");
  check("it opens", await openView(window, "vision", /Goals recorded/), said().slice(0, 100));
  check("the document upload comes first", !!q("#vs-doc") && !!q("#vsRead"));
  for (const l of ["Being worked on", "Nothing against them", "Projects serving no goal",
                   "Reached, or no longer wanted"]) check(`counter: ${l}`, said().includes(l));
  check("the two halves are explained", /neither is a fault/.test(said()));
  check("no progress figure, pillar or maturity", !/pillar|maturity|%|Category 1/i.test(said()));

  console.log("\nwriting one");
  const text = `Harness goal ${Date.now().toString(36)}`;
  q("#vsNew").click();
  await until(() => q("#vs-goal"));
  q("#vs-goal").value = text;
  const h = q('[name="vs-horizon"][value="Within a year"]');
  h.checked = true;
  q("#vs-save").click();
  check("it lands on the list", await until(() => said().includes(text)));
  const group = [...doc.querySelectorAll(".vs-group")].find((g) => g.textContent.includes(text));
  check("under its horizon heading", group && /^Within a year, \d+ goals?/.test(group.querySelector("h3").textContent.trim()));
  check("with its portfolio said in words", group && /Nothing is being done about this one yet|project/.test(group.textContent));

  finish(errors, "goals record with one sentence, grouped by horizon, with no progress figure");
}

main().catch((e) => { console.error(e); process.exit(1); });
