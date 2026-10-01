/* Does pressing "Download the draft document" actually hand over a file?

   The document itself is covered by tests/test_export.py. What that cannot
   reach is the last few feet: base64 arrives inside JSON, the browser has to
   turn it back into bytes, wrap it in a Blob and trigger a download. Every step
   there fails silently — a wrong MIME type, a revoked URL, an anchor never
   clicked — and the button looks like it worked.

   So this intercepts the download rather than trusting it: it records what the
   page tried to save, and checks the bytes are a real .docx.

   Usage:  node tools/check_export_button.js       (server must be running)
*/

const { JSDOM } = require("jsdom");
const fs = require("fs");
const path = require("path");

const WEB = path.join(__dirname, "..", "app", "web");
const read = (p) => fs.readFileSync(path.join(WEB, p), "utf8");
const BASE = process.env.GAIUS_BASE || "http://127.0.0.1:8765";

function store(seed = {}) {
  const d = { ...seed };
  return { getItem: (k) => (k in d ? d[k] : null),
           setItem: (k, v) => { d[k] = String(v); },
           removeItem: (k) => { delete d[k]; } };
}

async function boot() {
  const dom = new JSDOM(read("index.html"), {
    runScripts: "outside-only", pretendToBeVisual: true, url: BASE + "/",
  });
  const { window } = dom;
  window.fetch = async (url, opts) => {
    const r = await fetch(url.startsWith("http") ? url : BASE + url, opts);
    return { json: () => r.json(), ok: r.ok, status: r.status };
  };
  window.matchMedia = () => ({ matches: false, addEventListener() {} });
  Object.defineProperty(window, "localStorage", {
    value: store({ "scdes.registration": JSON.stringify(
      { email: "lokesh@iiac.ai", name: "Check", verified: true,
        state: "SC", agency: "sc.des", abbrev: "SCDES" }),
      "scdes.welcomeSeen": "1", "scdes.tour": "seen",
      "scdes.portal": "government" }), writable: true });
  Object.defineProperty(window, "sessionStorage",
    { value: store(), writable: true });
  window.confirm = () => true;
  window.alert = () => {};
  window.scrollTo = () => {};
  window.performance = window.performance || { now: () => Date.now() };
  window.Element.prototype.scrollIntoView = () => {};
  window.SVGElement.prototype.getBBox = () => ({ x: 0, y: 0, width: 10, height: 10 });

  // jsdom has no Blob URLs and no atob in older builds. Provide both, and
  // record what the page hands over instead of pretending to download it.
  const saved = [];
  window.atob = (s) => Buffer.from(s, "base64").toString("binary");
  const blobs = new Map();
  window.URL.createObjectURL = (blob) => {
    const key = "blob:probe/" + blobs.size;
    blobs.set(key, blob);
    return key;
  };
  window.URL.revokeObjectURL = (key) => blobs.delete(key);
  // The anchor click is what triggers the save; jsdom would try to navigate.
  window.HTMLAnchorElement.prototype.click = function click() {
    saved.push({ name: this.download, href: this.getAttribute("href"),
                 blob: blobs.get(this.getAttribute("href")) });
  };

  const errors = [];
  window.addEventListener("error", (e) => errors.push(e.message));
  for (const f of ["bugs.js", "dock.js", "guide.js", "notify.js", "onboard.js",
                   "welcome.js", "tour.js", "launcher.js", "speech.js",
                   "builder.js", "app.js"]) {
    try { window.eval(read(path.join("assets", f))); }
    catch (e) { errors.push(`${f}: ${e.message}`); }
  }
  window.dispatchEvent(new window.Event("DOMContentLoaded"));
  for (let i = 0; i < 80; i++) {
    if (!window.document.body.classList.contains("booting")) break;
    await new Promise((r) => setTimeout(r, 200));
  }
  if (window.closeLauncher) window.closeLauncher();
  await new Promise((r) => setTimeout(r, 900));
  return { window, errors, saved };
}

async function main() {
  const failures = [];
  const check = (label, ok, detail = "") => {
    console.log(`  ${ok ? "ok  " : "FAIL"}  ${label.padEnd(42)} ${detail}`);
    if (!ok) failures.push(label);
  };

  const { window, errors, saved } = await boot();
  const doc = window.document;

  console.log("finding the button");
  await window.go("framework");
  await new Promise((r) => setTimeout(r, 1400));
  const btn = doc.getElementById("fbExport");
  check("present in the builder", !!btn);
  if (!btn) { console.log("\nFAIL"); process.exit(1); }
  check("says what it does", /Download the draft/i.test(btn.textContent),
        btn.textContent.trim());
  check("not gated on saving a version first", !btn.disabled,
        "the framework is the free offering");

  console.log("\npressing it");
  btn.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  // The request is a round trip plus a few tens of KB of base64.
  for (let i = 0; i < 40 && !saved.length; i++) {
    await new Promise((r) => setTimeout(r, 200));
  }
  check("a file was handed over", saved.length === 1, `${saved.length}`);
  if (!saved.length) {
    const note = (doc.getElementById("fbExportNote") || {}).textContent;
    console.log("     the page says:", note);
    console.log("\nFAIL");
    process.exit(1);
  }

  const file = saved[0];
  check("named for the agency and marked draft",
        /-AI-Governance-Framework-DRAFT-\d{4}-\d{2}-\d{2}\.docx$/.test(file.name),
        file.name);
  check("carries a blob, not a bare link", !!file.blob);

  const bytes = Buffer.from(await file.blob.arrayBuffer());
  check("the bytes are a real zip", bytes.slice(0, 2).toString() === "PK",
        `${bytes.length.toLocaleString()} bytes`);

  /* Decompressed, not scanned raw. The first version of this searched the
     buffer as latin1 and reported the watermark missing from a document that
     had one — a .docx is a *deflated* zip, so only the filenames in the
     central directory are legible in the raw bytes. That is why
     "word/document.xml" was found and "GaiusWatermark" was not. */
  const { execFileSync } = require("child_process");
  const tmp = path.join(require("os").tmpdir(), "gaius-export-probe.docx");
  fs.writeFileSync(tmp, bytes);
  let inflated = "";
  try {
    inflated = execFileSync("python", ["-c",
      "import sys,zipfile;z=zipfile.ZipFile(sys.argv[1]);"
      + "print(''.join(z.read(n).decode('utf8','replace') "
      + "for n in z.namelist() if n.endswith('.xml')))", tmp],
      { encoding: "utf8", maxBuffer: 40 * 1024 * 1024 });
  } catch (e) {
    inflated = "";
  }
  check("it is a Word document, not an empty zip",
        inflated.includes("<w:document") || inflated.includes("w:body"));
  check("the watermark traveled with it",
        inflated.includes("GaiusWatermark"));
  /* Our own section titles, not somebody else's.

     This asserted "Risk Management Policy" — which is a section of the
     *reference* framework, from the dead `discretion` register. The document
     this application generates names its sections out of `prose.SECTIONS`
     ("Levels of scrutiny", "Information and records"), so the assertion was
     either vacuous or, if it had ever passed on content, evidence of the one
     leak the client has drawn the hardest line around. */
  for (const title of ["Definitions", "Levels of scrutiny", "Procurement",
                       "Adoption"]) {
    check(`the section "${title}" traveled with it`,
          inflated.includes(title));
  }
  check("and no section of anybody else's did",
        !inflated.includes("Risk Management Policy"));
  check("declared as a Word document",
        /wordprocessingml\.document/.test(file.blob.type), file.blob.type);
  fs.unlinkSync(tmp);

  console.log("\nand it reports back on screen");
  const note = (doc.getElementById("fbExportNote") || {}).textContent || "";
  check("names the file it saved", note.includes(".docx"), note.slice(0, 56));

  console.log("\nerrors             :", errors.length || "none");
  if (errors.length) console.log("  " + errors.join("\n  "));

  console.log();
  if (failures.length || errors.length) {
    console.log(`FAIL — ${failures.join("; ") || "errors on the page"}`);
    process.exit(1);
  }
  console.log("PASS — the button hands over a real Word document");
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
