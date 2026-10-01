/* Does the Projects write-up work as a screen?

     1. The list shows what it flags, and "the list is accurate today" records.
     2. A project opens with every write-up section: the nine questions, the
        nine categories, the six steps, the pressure-test, the tool record,
        the Identify summary, Procure, Versions and the retirement record.
     3. An answer to the nine questions saves and reads back in the summary.
     4. A version record opens with the vendor's own words.
     5. Nothing on it says model, algorithm or deployment.

   Writes to the harness container; refuses anything but a local server.
       $env:IIA_SUBSCRIPTION = "1"; node tools/check_projects_ui.js
*/

const { boot, until, settle, reporter, openView } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const said = () => doc.getElementById("view").textContent.replace(/\s+/g, " ");
  const q = (s) => doc.querySelector(s);
  // Projects waits for an adopted framework, deliberately, and the harness
  // organization has none. The gate is the browser's alone and is walked
  // elsewhere; here the page is told it is past it, so the write-up can be
  // walked.
  const real = window.fetch;
  window.fetch = async (url, opts) => {
    const r = await real(url, opts);
    if (!String(url).startsWith("/api/framework")) return r;
    const body = await r.json();
    return { ...r, json: async () => ({ ...body, usable: true }) };
  };
  await window.refreshFramework();

  console.log("the list");
  check("it opens", await openView(window, "projects", /Start a project/), said().slice(0, 100));
  check("what the list shows is said", said().includes("What this list shows"));
  q("#pjListChecked").click();
  check("the list check records", await until(() => /last confirmed this list is accurate on \d{4}-\d{2}-\d{2}/.test(said())));

  console.log("\na project");
  const name = `Harness project ${Date.now().toString(36)}`;
  await until(() => q("#pjName"));
  q("#pjName").value = name;
  q("#pjStart").click();
  check("it starts and opens", await until(() => q("#pjOne") && !q("#pjOne").hidden && q("#pb-happening")));
  for (const h of ["What is going wrong", "Is the answer a tool at all?", "Where the technology comes from",
                   "Before it leaves Identify", "The tool record", "What Identify produced",
                   "Procure — the business case", "Versions", "Retiring the tool"])
    check(`section: ${h}`, said().includes(h));
  check("nine categories, each with a verdict", doc.querySelectorAll('[id^="cv-"]').length === 9);
  check("six steps, each with a verdict", doc.querySelectorAll('[id^="hv-"]').length === 6);
  check("the parked idea is offered", said().includes("Did you already have something in mind?"));

  console.log("\nanswering");
  q("#pb-happening").value = "Applications wait three weeks in a shared inbox";
  q('[name="pb-conf"][value="Fairly confident"]').checked = true;
  q("#pbSave").click();
  check("it saves and reads back in the summary",
    await until(() => said().includes("Problem statement") && q("#pb-happening") &&
      q("#pb-happening").value.includes("three weeks") && said().includes("Applications wait three weeks")));

  const catSave = q("#catSave");
  q("#cv-process").value = "Taken";
  q("#cw-process").value = "Reorder the inbox";
  catSave.click();
  check("a verdict saves", await until(() => q("#cv-process") && q("#cv-process").value === "Taken"));
  await settle();

  console.log("\na version");
  await until(() => q("#vn-what"));
  q("#vn-what").value = "They moved the export button.";
  q("#vnOpen").click();
  check("a version record opens", await until(() => /V-[A-Z0-9]{5}/.test(said()) && said().includes("They moved the export button.")));

  // 4.1.2 on the open project: every control has a name a screen reader says.
  const unnamed = [...q("#pjOne").querySelectorAll("input, select, textarea, button")].filter((c) =>
    c.type !== "hidden" && !c.getAttribute("aria-label") && !c.closest("label") &&
    !(c.id && doc.querySelector(`label[for="${c.id}"]`)) && !(c.tagName === "BUTTON" && c.textContent.trim()));
  check("every control on the write-up has a name", unnamed.length === 0,
    unnamed.slice(0, 3).map((c) => c.id || c.name || c.tagName).join(", "));
  const levels = [...q("#pjOne").querySelectorAll("h2, h3, h4")].map((h) => +h.tagName[1]);
  check("heading levels do not skip", levels.every((l, i) => i === 0 || l - levels[i - 1] <= 1),
    levels.join(""));

  check("no banned words", !/\bmodel\b|algorithm|deployment|machine learning/i.test(said()));
  finish(errors, "the write-up sections render, save and read back");
}

main().catch((e) => { console.error(e); process.exit(1); });
