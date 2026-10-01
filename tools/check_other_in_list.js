/* "Other" in every state's agency list.

   Asked for: the agency list under each state should end with an "Other"
   option, so somebody whose organization is not listed finds a way in where
   they are already looking. These walk it:

     1. Every state's list ends with Other — all of them, and Federal.
     2. A search that finds nothing still offers Other.
     3. Choosing Other: the button reads "Continue as Other" and the hint says
        any work email.
     4. The button — and Enter — open the "Not on our list?" sign-up, with
        nothing sent to the server.

   Read-only.  node tools/check_other_in_list.js
*/

const { boot, settle, until, reporter } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot({ storage: {
    "scdes.welcomeSeen": "1", "scdes.tour": "seen", "scdes.onboarded": "1",
    "scdes.portal": "government" } });
  const doc = window.document;
  const posts = [];
  const real = window.fetch;
  window.fetch = async (url, opts) => {
    if (opts && opts.method === "POST") posts.push(String(url));
    return real(url, opts);
  };

  const pickState = async (code) => {
    const onb = doc.getElementById("onboard");
    if (onb && !onb.hidden) onb.hidden = true;
    const find = () => doc.querySelector(`.st[data-code="${code}"]`)
      || (code === "FED" && doc.getElementById("fedLink"));
    await until(find);
    find().dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
    return until(() => doc.getElementById("agencyPick"));
  };
  const openList = async (text) => {
    const input = doc.getElementById("agencyPick");
    input.dispatchEvent(new window.Event("focus"));
    input.value = text;
    input.dispatchEvent(new window.Event("input"));
    await settle(30);
    return [...doc.querySelectorAll("#agencyList li[role=option]")];
  };

  console.log("every state's list ends with Other");
  await until(() => doc.querySelector(".st"));
  const codes = [...doc.querySelectorAll(".st:not(.st-closed)")].map((p) => p.dataset.code);
  const missing = [];
  for (const code of [...codes, "FED"]) {
    await pickState(code);
    const rows = await openList("");
    const last = rows[rows.length - 1];
    if (!last || !/Other/.test(last.textContent.trim())) missing.push(code);
  }
  check(`all ${codes.length} states and Federal have it`, codes.length >= 51 && !missing.length,
    `states=${codes.length} missing=${missing.join(",")}`);

  console.log("\na search that finds nothing");
  await pickState("SC");
  const none = await openList("zzzz nothing");
  check("still offers Other", none.length === 1 && /Other/.test(none[0].textContent),
    doc.getElementById("agencyList").textContent.replace(/\s+/g, " ").slice(0, 140));

  console.log("\nchoosing Other");
  const rows = await openList("");
  rows[rows.length - 1].dispatchEvent(new window.MouseEvent("mousedown", { bubbles: true }));
  await settle(30);
  const go = doc.getElementById("lnchEnter");
  check("the button reads Continue as Other", !go.disabled && go.textContent === "Continue as Other",
    go.textContent);
  check("the hint says any work email", /Any work email/.test(doc.getElementById("agencyHint").textContent));
  check("the box shows the choice", /not listed/.test(doc.getElementById("agencyPick").value));

  go.click();
  check("the button opens the Not on our list sign-up", await until(() => doc.getElementById("unUnit")));
  check("nothing was sent", posts.length === 0, posts.join(" "));

  console.log("\nEnter does the same");
  await pickState("TX");
  const tx = await openList("");
  tx[tx.length - 1].dispatchEvent(new window.MouseEvent("mousedown", { bubbles: true }));
  await settle(30);
  const input = doc.getElementById("agencyPick");
  input.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  check("Enter opens it too", await until(() => doc.getElementById("unUnit")));

  window.fetch = real;
  finish(errors, "every state's agency list ends with Other, and it leads to the Not on our list sign-up");
}

main().catch((e) => { console.error(e); process.exit(1); });
