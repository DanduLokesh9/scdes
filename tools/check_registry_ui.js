/* Does the Registry screen work as a screen?

     1. The search returns its bands in the hierarchy's order, each headed and
        counted, and an empty band says so rather than closing up.
     2. A tool added with a holding unit is found by somebody in a different
        unit under "Another unit here has this", with what that unit uses it
        for — the sentence that stops a purchase.
     3. Nothing on it is the reference agency's systems register.

   Writes to the harness container; refuses anything but a local server.
       $env:IIA_SUBSCRIPTION = "1"; node tools/check_registry_ui.js
*/

const { boot, settle, until, reporter, openView } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const said = () => doc.getElementById("view").textContent.replace(/\s+/g, " ");
  const q = (s) => doc.querySelector(s);

  console.log("the screen");
  check("it opens", await openView(window, "registry", /Is there already something that does this/), said().slice(0, 100));
  const heads = [...doc.querySelectorAll(".rg-band h3")].map((h) => h.textContent.replace(/\s+/g, " "));
  check("the bands are headed, in hierarchy order",
    /^You already run this/.test(heads[0] || "") && /^Something you would buy/.test(heads[heads.length - 1] || ""),
    heads.map((h) => h.split(" ·")[0]).join(" > "));
  check("each band carries its count", heads.every((h) => /\d+ results?/.test(h)));
  check("not the reference agency's register", !/Appendix|Council-gated|Composite/.test(said()));

  console.log("\nadding one");
  const name = `Harness summarizer ${Date.now().toString(36)}`;
  q("#rgAdd").click();
  await until(() => q("#rg-name"));
  q("#rg-name").value = name;
  q("#rg-does").value = "Summarizes long permit files";
  const unitInputs = () => [...q("#rg-holders").querySelectorAll('[data-k="unit"]')];
  if (unitInputs().length) {
    unitInputs()[0].value = "Planning";
    q("#rg-holders").querySelector('[data-k="used_for"]').value = "permit summaries";
  }
  q("#rg-save").click();
  check("it lands in the catalog", await until(() => said().includes(name)));

  console.log("\nsearching from another unit");
  q("#rg-q").value = "permit files";
  const unit = q("#rg-unit");
  if (unit) unit.value = "Water";
  q("#rgSearch").dispatchEvent(new window.Event("submit", { cancelable: true }));
  await until(() => [...doc.querySelectorAll(".rg-band")].some((b) => b.textContent.includes(name)));
  const band = [...doc.querySelectorAll(".rg-band")].find((b) => b.textContent.includes(name));
  check("it is found under Another unit here has this",
    band && /Another unit here has this/.test(band.querySelector("h3").textContent),
    band ? band.querySelector("h3").textContent.split("·")[0].trim() : "not found");
  check("with what that unit uses it for", band && /Planning uses it for permit summaries/.test(band.textContent));

  finish(errors, "the catalog searches in hierarchy order and names who already has it");
}

main().catch((e) => { console.error(e); process.exit(1); });
