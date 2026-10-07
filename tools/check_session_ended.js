/* "Your session ended — sign in again."

     1. When the server refuses a change because it cannot tie it to an
        organization, the screen says the session ended — it does not look
        as if the change was saved.
     2. Signing out in another tab ends this tab too, with the same message.
     3. The one button takes them back to sign in.

   Every server answer is held here; nothing is written.
       node tools/check_session_ended.js
*/

const { boot, settle, reporter } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const real = window.fetch;

  console.log("a refused change");
  window.fetch = async (url, opts) => (opts && opts.method === "POST")
    ? { ok: false, status: 401, json: async () => ({ ok: false, session_ended: true,
        error: "Your session ended — sign in again. That change was not saved." }) }
    : real(url, opts);
  // The shell's request function, as every screen's save goes through it.
  const out = await window.api("/api/versions/answer",
    { method: "POST", body: JSON.stringify({ key: "org.size", value: "u25" }) });
  await settle(100);
  const veil = doc.getElementById("sessionEndedVeil");
  check("the screen says the session ended", !!veil && /Your session ended/.test(veil.textContent));
  check("and that the change was not saved", /not saved/.test(veil.textContent));
  check("it is an alert dialog, with focus on the way back",
    veil.querySelector('[role="alertdialog"]') && doc.activeElement === doc.getElementById("seGo"));
  check("the caller still learns it failed", out && out.ok === false && out.session_ended);
  veil.remove();

  console.log("\nthe Framework builder's saves");
  // builder.js has its own request function; it reports the same way.
  const viaBuilder = window.fbApi("/api/versions/answer",
    { method: "POST", body: JSON.stringify({ key: "org.size", value: "u25" }) });
  await viaBuilder;
  await settle(50);
  check("a refused answer in the builder is not shown as saved", (await viaBuilder).session_ended === true);
  window.fetch = real;

  console.log("\nsigning out in another tab");
  const left = doc.getElementById("sessionEndedVeil");
  if (left) left.remove();
  doc.getElementById("home").hidden = true;
  doc.body.classList.remove("launcher-open");
  const ev = new window.StorageEvent("storage", { key: "scdes.session", oldValue: "tok-123", newValue: null });
  window.dispatchEvent(ev);
  await settle(50);
  const veil2 = doc.getElementById("sessionEndedVeil");
  check("this tab notices", !!veil2 && /signed out in another tab/.test(veil2.textContent));
  veil2.remove();

  window.dispatchEvent(new window.StorageEvent("storage", { key: "scdes.session", oldValue: null, newValue: "tok-9" }));
  await settle(50);
  check("but a sign-in elsewhere, from nobody, does not interrupt", !doc.getElementById("sessionEndedVeil"));

  console.log("\nnothing typed is lost");
  window.localStorage.removeItem("gaius.outbox");
  const answered = [];
  let signedBackIn = false;
  window.fetch = async (url, opts) => {
    const u = String(url);
    if (u.includes("/api/agency/signin")) return { ok: true, status: 200, json: async () => ({ ok: true, code: "246810" }) };
    if (u.includes("/api/agency/verify")) { signedBackIn = true;
      return { ok: true, status: 200, json: async () => ({ ok: true, session: "tok-new", status: "active" }) }; }
    if (u.includes("/api/agency/access")) {
      const me = JSON.parse(window.localStorage.getItem("scdes.registration") || "{}");
      return { ok: true, status: 200, json: async () => ({ allowed: true, state: me.agency }) };
    }
    if (opts && opts.method === "POST" && u.includes("/api/versions/answer")) {
      if (!signedBackIn) return { ok: false, status: 401, json: async () => ({ ok: false, session_ended: true,
        error: "Your session ended — sign in again. That change was not saved." }) };
      answered.push(JSON.parse(opts.body).key);
      return { ok: true, status: 200, json: async () => ({ ok: true }) };
    }
    return real(url, opts);
  };
  for (const key of ["org.size", "org.kind", "org.size"]) {
    await window.api("/api/versions/answer", { method: "POST", body: JSON.stringify({ key, value: "x" }) });
  }
  const kept = JSON.parse(window.localStorage.getItem("gaius.outbox") || "[]");
  check("refused answers are kept, the same question once", kept.length === 2
    && kept.map((k) => k.key).sort().join() === "org.kind,org.size", JSON.stringify(kept.map((k) => k.key)));
  const box = doc.getElementById("sessionEndedVeil");
  check("the message says they are kept", !!box && /2 changes are kept/.test(box.textContent));
  check("and offers to sign back in right here", /Send me a code/.test(doc.getElementById("seGo").textContent));
  doc.getElementById("seGo").click();
  await settle(150);
  check("a code is asked for, in the same box", !doc.getElementById("seCodeRow").hidden
    && /246810/.test(doc.getElementById("seShown").textContent));
  doc.getElementById("seCode").value = "246810";
  doc.getElementById("seGo").click();
  await settle(600);
  check("signing back in sends what was kept", answered.sort().join() === "org.kind,org.size", answered.join());
  check("the box closes, and nothing is left waiting", !doc.getElementById("sessionEndedVeil")
    && JSON.parse(window.localStorage.getItem("gaius.outbox") || "[]").length === 0);
  check("the new sign-in is kept", window.localStorage.getItem("scdes.session") === "tok-new");
  window.fetch = real;

  // jsdom cannot navigate; the real browser does.
  finish(errors.filter((e) => !/Not implemented: navigation/.test(e)),
         "a change with nowhere to go says so, is kept, and is saved after signing back in");
}

main().catch((e) => { console.error(e); process.exit(1); });
