/* Measure the real layout in a real browser (headless Edge), which jsdom
   cannot do. Opens the local app signed in as the harness container, goes to
   a view, reports what occupies the page height, and saves a screenshot.
       node tools/_layout_probe.js [view] [width] [height] [out.png]
   Local only; reads nothing from staging. */

const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");

const BASE = "http://127.0.0.1:8765";
const view = process.argv[2] || "home";
const W = Number(process.argv[3] || 2000), H = Number(process.argv[4] || 790);
const OUT = process.argv[5] || path.join(os.tmpdir(), `layout-${view}.png`);
const EDGE = ["C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
              "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe"].find((p) => fs.existsSync(p));

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "edge-probe-"));
  const port = 9300 + Math.floor(Math.random() * 400);
  const edge = spawn(EDGE, ["--headless=new", `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`, `--window-size=${W},${H}`, "--no-first-run",
    "--disable-gpu", "about:blank"], { stdio: "ignore" });
  let targets = [];
  for (let i = 0; i < 40 && !targets.length; i++) {
    await sleep(250);
    try { targets = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).filter((t) => t.type === "page"); } catch { /* not up yet */ }
  }
  const ws = new WebSocket(targets[0].webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r, { once: true }));
  let id = 0;
  const pending = new Map();
  ws.addEventListener("message", (m) => {
    const msg = JSON.parse(m.data);
    if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg); pending.delete(msg.id); }
  });
  const send = (method, params = {}) => new Promise((r) => {
    const n = ++id; pending.set(n, r); ws.send(JSON.stringify({ id: n, method, params }));
  });
  const js = async (expr) => (await send("Runtime.evaluate",
    { expression: expr, awaitPromise: true, returnByValue: true })).result?.result?.value;

  await send("Emulation.setDeviceMetricsOverride", { width: W, height: H, deviceScaleFactor: 1, mobile: false });
  await send("Page.enable");
  await send("Page.navigate", { url: BASE + "/" });
  await sleep(1500);
  await js(`localStorage.setItem("scdes.registration", JSON.stringify({ email: "walk@harness.gaius.test",
      name: "Automated walk", verified: true, state: "SC", agency: "gaius.harness", abbrev: "HARNESS" }));
    localStorage.setItem("scdes.welcomeSeen", "1"); localStorage.setItem("scdes.tour", "seen");
    localStorage.setItem("scdes.portal", "government"); true`);
  await send("Page.reload");
  await sleep(3500);
  await js(`window.closeLauncher && window.closeLauncher(); true`);
  await js(`window.go && window.go(${JSON.stringify(view)}); true`);
  await sleep(2500);
  if (process.env.INJECT === "people") await js(`(() => {
    const panel = window.peoplePanel({ ok: true, is_admin: true, me: "", domain: "iiac.ai", admin_names: ["Brett Butz"],
      people: [{ name: "Brett Butz", title: "CEO", role: "Owner", email: "brett@iiac.ai", added_at: "2026-09-22T17:35:00+00:00" },
               { name: "lokesh dandu", title: "op", role: "Member", email: "lokesh@iiac.ai", added_at: "2026-08-28T10:31:00+00:00" }] },
      "DEMO agency — Innovative Infrastructure Advising");
    document.getElementById("view").appendChild(panel); return true; })()`);
  if (process.env.SCROLL) await js(`document.getElementById("record").scrollTop = 1e6; true`);
  await sleep(300);

  const report = await js(`(() => {
    const r = (el) => { const b = el.getBoundingClientRect(); return [Math.round(b.top), Math.round(b.height)]; };
    const out = { viewport: [innerWidth, innerHeight],
      docHeight: document.documentElement.scrollHeight, bodyHeight: document.body.scrollHeight };
    out.bodyChildren = [...document.body.children].map((c) => {
      const cs = getComputedStyle(c);
      return { tag: c.tagName.toLowerCase(), id: c.id, cls: c.className, display: cs.display,
        position: cs.position, rect: r(c) };
    }).filter((x) => x.display !== "none" && x.position !== "fixed" && x.position !== "absolute");
    const shell = document.querySelector(".shell");
    out.shell = shell && { rect: r(shell), rows: getComputedStyle(shell).gridTemplateRows,
      children: [...shell.children].map((c) => ({ tag: c.tagName.toLowerCase(), id: c.id, cls: c.className,
        display: getComputedStyle(c).display, rect: r(c) })) };
    return out;
  })()`);
  console.log(JSON.stringify(report, null, 1));
  const shot = await send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync(OUT, Buffer.from(shot.result.data, "base64"));
  console.log("screenshot:", OUT);
  ws.close(); edge.kill();
  try { fs.rmSync(profile, { recursive: true, force: true }); } catch { /* Edge may still hold it */ }
}

main().catch((e) => { console.error(e); process.exit(1); });
