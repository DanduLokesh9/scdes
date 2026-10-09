/* Does Enter do what the main button does on the sign-in and register cards?

   Reported: typing the work email and pressing Enter on "Sign in to …" did
   nothing — only clicking "Send me a code" worked. The buttons are not
   inside a <form>, so the browser's own Enter-submits never applied.

   Records what the page asks the server for and never lets it through, so
   nothing is sent and no code is issued.
       node tools/check_enter_sends.js
*/

const { boot, settle, reporter } = require("./_jsdom_boot");

async function main() {
  const { check, finish } = reporter();
  const { window, errors } = await boot();
  const doc = window.document;
  const asked = [];
  const real = window.fetch;
  window.fetch = async (url, opts) => {
    if (/\/api\/agency\/(signin|register)/.test(String(url))) {
      asked.push(String(url));
      return { ok: true, status: 200, json: async () => ({ ok: false, error: "held by the check" }) };
    }
    return real(url, opts);
  };
  const enter = (el) => el.dispatchEvent(new window.KeyboardEvent("keydown",
    { key: "Enter", bubbles: true, cancelable: true }));
  const entry = { agency: "gaius.harness", state: "SC" };

  console.log("sign in");
  window.showReturning(entry, "someone@example.gov");
  await settle(200);
  const box = doc.getElementById("siEmail");
  check("the sign-in card is showing", !!box);
  enter(box);
  await settle(400);
  check("Enter in the email box sends the code", asked.some((u) => u.includes("/signin")), asked.join(", "));
  check("and says why when the server refuses", !doc.getElementById("siError").hidden);

  console.log("\nan empty email");
  asked.length = 0;
  window.showReturning(entry, "");
  await settle(200);
  enter(doc.getElementById("siEmail"));
  await settle(300);
  check("Enter with no email asks for one instead of sending",
    !asked.length && /work email/.test(doc.getElementById("siError").textContent));

  console.log("\nregister");
  asked.length = 0;
  window.showRegister(entry, {});
  await settle(200);
  // Since Oct 2026 the register card is Brett's agreement form. Accepting a
  // legal agreement is a deliberate press of Accept, once the text has been
  // read — so Enter in a field must not do it, and sends nothing.
  const name = doc.getElementById("tcName");
  check("the register card is showing", !!name && !!doc.getElementById("termsBody"));
  enter(name);
  await settle(300);
  check("Enter on the agreement card does not accept it, and sends nothing",
    doc.getElementById("tcGo").disabled && !asked.some((u) => /terms\/accept|register/.test(u)),
    asked.join(", "));

  console.log("\nthe agency picker");
  window.showMap();
  await settle(300);
  const sc = doc.querySelector('.st[data-code="SC"]');
  if (sc) sc.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
  await settle(500);
  const pick = doc.getElementById("agencyPick");
  const go = doc.getElementById("lnchEnter");
  check("the picker is showing", !!pick && !!go);
  let pressed = 0;
  // Counted, and stopped before it navigates anywhere.
  go.addEventListener("click", (e) => { pressed += 1; e.stopImmediatePropagation(); }, true);
  pick.focus();
  pick.value = "Department of Environmental Services";
  pick.dispatchEvent(new window.Event("input", { bubbles: true }));
  await settle(250);
  enter(pick);
  await settle(250);
  check("first Enter chooses the highlighted agency",
    /Environmental Services/.test(pick.value) && !go.disabled && pressed === 0, pick.value);
  enter(pick);
  await settle(250);
  check("second Enter presses the Enter button", pressed === 1, `pressed ${pressed}`);

  console.log("\nthe code: auto-verify");
  let verifyAnswer = { ok: false, error: "That code is not right. Check the latest email and try again." };
  const verified = [];
  const before = window.fetch;
  window.fetch = async (url, opts) => {
    if (String(url).includes("/api/agency/verify")) {
      verified.push(JSON.parse(opts.body).code);
      return { ok: true, status: 200, json: async () => verifyAnswer };
    }
    return before(url, opts);
  };
  window.showVerify(entry, "someone@example.gov", "", 30, "", false);
  await settle(200);
  const code = doc.getElementById("verCode");
  const verify = doc.getElementById("verGo");
  const type = (v) => { code.value = v; code.dispatchEvent(new window.Event("input", { bubbles: true })); };
  type("12345");
  await settle(300);
  check("five digits send nothing", verified.length === 0);
  type("123 456");
  await settle(400);
  check("the sixth digit sends it, spaces dropped", verified.join() === "123456", verified.join());
  check("a wrong code empties the box", code.value === "");
  check("and shakes the Verify button", verify.classList.contains("signin-shake"));
  check("and says so in words a screen reader hears",
    !doc.getElementById("verError").hidden && doc.getElementById("verError").getAttribute("role") === "alert");
  check("focus stays in the box for the next try", doc.activeElement === code);
  check("the buttons are unchanged", verify.textContent.trim() === "Verify" &&
    doc.getElementById("verBack").textContent.trim() === "Back");
  verifyAnswer = { ok: true, status: "active", session: "" };
  let wentIn = false;
  // A right code goes on to afterVerify — the Terms check, then in (it was
  // the NDA step before the Terms replaced it).
  const nda = window.afterVerify;
  window.afterVerify = () => { wentIn = true; };
  type("654321");
  await settle(400);
  check("a right code goes straight in", verified.join() === "123456,654321" && wentIn, verified.join());
  window.afterVerify = nda;

  finish(errors, "Enter presses the main button everywhere, and the code verifies itself");
}

main().catch((e) => { console.error(e); process.exit(1); });
