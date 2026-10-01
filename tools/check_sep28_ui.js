/* Brett's screen tickets, Sep 24 and 28.

     Data page (BUG-A7022EEE, BUG-98855006)
       1. "Which units use it": the box for new units is a real text area,
          not squeezed to the width of a tick-box.
       2. An ⓘ beside "What system holds it" (and the other terms) opens a
          plain explanation, announced and tied to the field.
     Framework 2.3 (BUG-0081CD67)
       3. "Yes, a formally adopted policy" offers an upload beside the paste box.
     Search (BUG-C1496D1E)
       4. The search box says it searched this organization's own documents.

   Read-only: nothing is saved.
       node tools/check_sep28_ui.js
*/

const { boot, settle, until, reporter, openView } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;

  console.log("the Data page");
  check("it opens", await openView(window, "holdings", /Add a holding/));
  const units = doc.getElementById("dh-unitsnew");
  check("the new-units box is a text area", units && units.tagName === "TEXTAREA");
  const css = require("fs").readFileSync(require("path").join(__dirname, "..", "app", "web", "assets", "app.css"), "utf8");
  check("tick-box sizing no longer applies to text boxes",
    !/\.vr-tri input \{ width: 16px/.test(css) && /\.vr-tri input\[type="checkbox"\]/.test(css));

  const sys = doc.querySelector('button.info-i[aria-controls="dh-system-info"]');
  check("an ⓘ sits beside What system holds it", !!sys && /What system holds it/.test(sys.getAttribute("aria-label")));
  const text = doc.getElementById("dh-system-info");
  check("its explanation starts closed", text && text.hidden && sys.getAttribute("aria-expanded") === "false");
  sys.click();
  check("pressing it opens the explanation", !text.hidden && sys.getAttribute("aria-expanded") === "true"
    && /permit system/.test(text.textContent));
  check("and the field is described by it", (doc.getElementById("dh-system").getAttribute("aria-describedby") || "").includes("dh-system-info"));
  sys.click();
  check("pressing again closes it", text.hidden && sys.getAttribute("aria-expanded") === "false");
  check("several fields have one", doc.querySelectorAll("#dhForm .info-i").length >= 5);

  console.log("\nFramework 2.3");
  const html = window.fbControl({ kind: "single", key: "have.policy", options: [
    { value: "adopted", label: "Yes, a formally adopted policy", then_text: "Paste it, or its title", then_upload: true },
    { value: "nothing", label: "Nothing written" }] });
  const host = doc.createElement("div"); host.innerHTML = html;
  const file = host.querySelector('input[type="file"]');
  check("an upload sits beside the paste box", !!file && !!host.querySelector(`label[for="${file.id}"]`)
    && /Or upload the file/.test(host.textContent));
  check("it takes the same files as the documents panel", file && file.getAttribute("accept") === ".docx,.pdf,.txt,.md");

  console.log("\nsearch");
  const real = window.fetch;
  window.fetch = async (url, opts) => String(url).includes("/api/chat")
    ? { ok: true, status: 200, json: async () => ({ mode: "query", provider: "local", citations: [],
        in_scope: false, answer: "Nothing in your organization's own documents matches that." }) }
    : real(url, opts);
  doc.getElementById("cmdkBtn").click();
  const input = doc.getElementById("paletteInput");
  input.value = "Center of Excellence";
  input.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await until(() => /own documents/.test(doc.getElementById("paletteOut").textContent));
  check("it says only this organization's documents were searched",
    /Searched your organization's own documents only/.test(doc.getElementById("paletteOut").textContent));
  window.fetch = real;

  console.log("\nVision, from the framework (BUG-BE30FBD3)");
  const posted = [];
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (u.includes("/api/goals") && opts && opts.method === "POST") {
      posted.push(JSON.parse(opts.body));
      return { ok: true, status: 200, json: async () => ({ ok: true, goal: { ref: "GL-X" } }) };
    }
    if (u.includes("/api/goals")) {
      return { ok: true, status: 200, json: async () => ({
        goals: [], grouped: [], portfolio: [], counters: {}, raised: [], proposals: [], projects: [],
        inputs: {}, horizons: ["Within a year", "Within five years"], standings: ["Open"],
        from_framework: [
          { goal: "Answer permit questions faster", horizon: "Within a year", from: "Framework 11.1a" },
          { goal: "Plain-language answers at any hour", horizon: "Within five years", from: "Framework 11.1b" }],
        from_framework_says: "From your framework, 11.1a and 11.1b.", upload_first: "Upload a plan",
        only_the_goal: "Only the goal itself is required.", empty_state: "No goals yet." }) };
    }
    return real(url, opts);
  };
  check("Vision opens", await openView(window, "vision", /From your framework/));
  const fwText = doc.getElementById("vsFromFramework").textContent.replace(/\s+/g, " ");
  check("it offers the framework's goals with their horizons",
    /Answer permit questions faster Within a year · Framework 11\.1a/.test(fwText), fwText.slice(0, 160));
  doc.querySelector("[data-vs-fw='0']").click();
  await settle(100);
  check("Use this one opens the form already filled",
    (doc.getElementById("vs-goal") || {}).value === "Answer permit questions faster");
  doc.getElementById("vsFwAll").click();
  check("Add all adds each one, with its horizon", await until(() => posted.length === 2)
    && posted[1].goal === "Plain-language answers at any hour" && posted[1].horizon === "Within five years",
    JSON.stringify(posted));
  window.fetch = real;

  finish(errors, "the Data page, 2.3's upload, search and Vision behave as Brett asked");
}

main().catch((e) => { console.error(e); process.exit(1); });
