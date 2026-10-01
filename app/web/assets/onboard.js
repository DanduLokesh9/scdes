/* Onboarding — the first thing a new user sees.

   Three steps, in order: which kind of organization you are, then your work
   email, then the map. The map does not appear until the first two are done,
   which is the point: choosing an agency to govern is not the first question to
   ask someone.

   The email rule is enforced by app/onboarding.py as well as here. This copy
   exists to give an answer as you type; the server's copy is the one that
   decides. A gate that lives only in the browser is a suggestion. */

const ONB = { portals: [], suffixes: [], portal: null, notice: "" };

/* ------------------------------------------------------------ tester access

   Testing the platform meant completing onboarding first, because the tester
   check keys off the address stored during registration. That is circular when
   the thing you want to test is everything *after* onboarding.

   So the address can be set directly:

       http://…/?tester=lokesh@iiac.ai      once, from the address bar
       becomeTester("lokesh@iiac.ai")       any time, from the console
       clearTester()                        back to a normal session

   This is not a way in. It only says *which* address to present; the server
   still checks it against the allowlist in app/tenancy.py, which is locked to
   the iiac.ai domain and emptied by IIA_TESTERS=none. Naming an address that is
   not on that list unlocks nothing. */

function becomeTester(email) {
  const address = String(email || "").trim().toLowerCase();
  if (!address) { console.warn("becomeTester needs an email"); return; }
  try {
    localStorage.setItem("scdes.registration", JSON.stringify({
      email: address, portal: "government", domain: address.split("@")[1] || "",
      evidence: "tester", tester: true,
    }));
    // Skip the parts that only get in the way of repeated testing.
    localStorage.setItem("scdes.welcomeSeen", "1");
    localStorage.setItem("scdes.portal", "government");
  } catch (e) { console.warn(e); }
  location.replace(location.pathname);      // drop the query, reload clean
}

function clearTester() {
  try {
    localStorage.removeItem("scdes.registration");
    localStorage.removeItem("scdes.signin");
    localStorage.removeItem("scdes.welcomeSeen");
    // A full reset for a fresh demo, so the portal question comes back too.
    localStorage.removeItem("scdes.portal");
  } catch (e) {}
  location.replace(location.pathname);
}

// Runs before anything reads the stored registration, which is why this lives
// at the top of the first script rather than in app.js.
(function readTesterParam() {
  const asked = new URLSearchParams(location.search).get("tester");
  if (asked) becomeTester(asked);
})();

window.becomeTester = becomeTester;
window.clearTester = clearTester;

const onbEsc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function onbStored() {
  try { return JSON.parse(localStorage.getItem("scdes.registration") || "null"); }
  catch (e) { return null; }
}

function onbRemember(entry) {
  try {
    localStorage.setItem("scdes.registration", JSON.stringify(entry));
  } catch (e) { /* private mode: they re-register next visit, which is fine */ }
}

/* ------------------------------------------------------------ step 1: who */

function onbPortals() {
  const host = document.getElementById("onboard");
  host.innerHTML = `
    <div class="onb-card">
      <p class="onb-eyebrow">AI Governance</p>
      <h1>Which of these are you?</h1>
      <p class="onb-lede">The obligations are not the same, so the two paths are
        not the same. Pick the one that describes your organization.</p>

      <div class="onb-choices">
        ${ONB.portals.map((p) => `
          <button class="onb-choice${p.open ? "" : " soon"}" type="button"
                  data-portal="${onbEsc(p.key)}" ${p.open ? "" : "disabled"}>
            <span class="onb-choice-head">
              <b>${onbEsc(p.label)}</b>
              ${p.open ? "" : `<span class="onb-soon">Coming soon</span>`}
            </span>
            <span class="onb-choice-body">${onbEsc(p.blurb)}</span>
          </button>`).join("")}
      </div>
    </div>`;

  host.querySelectorAll(".onb-choice[data-portal]").forEach((b) => {
    b.onclick = () => {
      ONB.portal = b.dataset.portal;
      // Durable, and deliberately separate from the registration. "Which kind
      // of organization is this" is a property of the machine, not of the
      // person signed in — so signing out must not ask it again, and neither
      // must a refresh.
      try { localStorage.setItem("scdes.portal", ONB.portal); } catch (e) {}
      onbEmail();
    };
  });
  const first = host.querySelector(".onb-choice:not([disabled])");
  if (first) first.focus();
}

/* ---------------------------------------------------------- step 2: email */

/** Same rule as the server's, so the message arrives before the round trip. */
function onbLocalCheck(email) {
  const address = (email || "").trim().toLowerCase();
  if (!address) return "Enter your work email address.";
  if (!/^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/.test(address))
    return "That does not look like an email address.";
  const domain = address.split("@")[1];
  // "Other public body" takes an organization's own address on any domain —
  // the server still refuses personal mailboxes, and a code proves the rest.
  if (ONB.portal === "other") return "";
  if (!ONB.suffixes.some((s) => domain.endsWith(s)))
    return `This option needs an address ending in ${ONB.suffixes.join(", ")}. `
      + "If your public body uses another kind of address, go Back and choose Other public body.";
  return "";
}

function onbEmail() {
  const host = document.getElementById("onboard");
  const portal = ONB.portals.find((p) => p.key === ONB.portal) || {};

  host.innerHTML = `
    <div class="onb-card">
      <p class="onb-eyebrow">${onbEsc(portal.label || "")}</p>
      <h1>Register your work email</h1>
      ${ONB.portal === "other"
        ? `<p class="onb-lede">The email address you use for your organization's work,
            on any domain. Next you add your organization yourself, using
            <b>Create your framework anyway</b> on the map, and a code sent to this
            address confirms it is yours.</p>`
        : `<p class="onb-lede">Public-sector and non-profit domains only —
            ${onbEsc(ONB.suffixes.join(", "))}. This is how the portal knows which
            path you are on. If your public body uses another kind of address, go
            Back and choose Other public body.</p>`}

      <label class="onb-field">
        <span>Work email</span>
        <input id="onbEmail" type="email" autocomplete="email" spellcheck="false"
               placeholder="${ONB.portal === "other" ? "you@cityofexample.net" : "you@agency.gov"}">
      </label>
      <label class="onb-field">
        <span>Organization <em>(optional)</em></span>
        <input id="onbOrg" type="text" autocomplete="organization"
               placeholder="${ONB.portal === "other" ? "City of Example" : "Department of Environmental Services"}">
      </label>

      <p class="onb-error" id="onbError" hidden></p>

      <p class="onb-warn">${onbEsc(ONB.notice)}</p>

      <div class="onb-actions">
        <button class="btn ghost" id="onbBack" type="button">Back</button>
        <button class="btn" id="onbGo" type="button">Continue</button>
      </div>
    </div>`;

  const field = document.getElementById("onbEmail");
  const error = document.getElementById("onbError");
  const submit = document.getElementById("onbGo");

  const fail = (message) => {
    error.textContent = message;
    error.hidden = !message;
  };

  // Clear the complaint as soon as they start fixing it, rather than leaving a
  // stale error under a field they have already corrected.
  field.oninput = () => fail("");
  field.onkeydown = (e) => { if (e.key === "Enter") submit.click(); };

  submit.onclick = async () => {
    const email = field.value.trim();
    const local = onbLocalCheck(email);
    if (local) { fail(local); field.focus(); return; }

    submit.disabled = true;
    submit.textContent = "Checking…";
    try {
      const r = await fetch("/api/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email, portal: ONB.portal,
          organisation: (document.getElementById("onbOrg") || {}).value || "",
        }),
      }).then((x) => x.json());

      if (!r.ok) { fail(r.reason || "That address cannot be used here."); return; }
      onbRemember({ email, portal: ONB.portal, domain: r.domain,
                    evidence: r.evidence });
      onbFinish();
    } catch (e) {
      // The server is the authority, so a failed call must not wave them
      // through — say so plainly instead of pretending it worked.
      fail("Could not reach the server to register. Try again.");
    } finally {
      submit.disabled = false;
      submit.textContent = "Continue";
    }
  };

  document.getElementById("onbBack").onclick = () => onbPortals();
  field.focus();
}

/* -------------------------------------------------------------- step 3: map */

function onbFinish() {
  const host = document.getElementById("onboard");
  host.hidden = true;
  host.innerHTML = "";
  document.body.classList.remove("onboarding");
  if (window.openLauncher) window.openLauncher();   // now the map appears
}

/** True when onboarding is needed. Called by app.js before opening the map. */
async function initOnboarding() {
  const host = document.getElementById("onboard");
  if (!host) return false;

  if (onbStored()) return false;                    // already registered

  /* The portal question is asked once per machine, not once per session.

     It was a one-shot marker in sessionStorage, set by sign-out. That got
     someone from Sign out back to the map, and then the very next refresh
     consumed the marker and dropped them on "Which of these are you?" again —
     a question they had already answered, standing between them and the map
     they were looking at a second earlier.

     Answering it is not identity, so it survives signing out. A genuinely new
     browser still gets asked. */
  try {
    if (localStorage.getItem("scdes.portal")) return false;
    if (sessionStorage.getItem("scdes.justSignedOut")) {
      // Legacy path: a session that signed out before the durable flag existed.
      sessionStorage.removeItem("scdes.justSignedOut");
      localStorage.setItem("scdes.portal", "government");
      return false;
    }
  } catch (e) { /* private mode: they get onboarding, which still works */ }

  try {
    const info = await fetch("/api/portals").then((r) => r.json());
    ONB.portals = info.portals || [];
    ONB.suffixes = info.eligible_suffixes || [];
    ONB.notice = info.notice || "";
  } catch (e) {
    // Without the portal list there is nothing to choose between. Let the map
    // open rather than trapping someone behind a screen that cannot render.
    console.warn("[onboard] portal list unavailable; skipping onboarding", e);
    return false;
  }

  document.body.classList.add("onboarding");
  host.hidden = false;
  onbPortals();
  return true;
}

window.initOnboarding = initOnboarding;
window.onboardingDone = () => !!onbStored();
/** For testing and for a fresh demo: clear the registration and start over. */
window.resetOnboarding = () => {
  try { localStorage.removeItem("scdes.registration"); } catch (e) {}
  location.reload();
};
