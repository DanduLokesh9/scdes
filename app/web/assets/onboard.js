/* Onboarding — the first thing a new user sees.

   Three steps, in order: which kind of organisation you are, then your work
   email, then the map. The map does not appear until the first two are done,
   which is the point: choosing an agency to govern is not the first question to
   ask someone.

   The email rule is enforced by app/onboarding.py as well as here. This copy
   exists to give an answer as you type; the server's copy is the one that
   decides. A gate that lives only in the browser is a suggestion. */

const ONB = { portals: [], suffixes: [], portal: null, notice: "" };

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
        not the same. Pick the one that describes your organisation.</p>

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
    b.onclick = () => { ONB.portal = b.dataset.portal; onbEmail(); };
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
  if (!ONB.suffixes.some((s) => domain.endsWith(s)))
    return `Needs an address ending in ${ONB.suffixes.join(", ")}.`;
  return "";
}

function onbEmail() {
  const host = document.getElementById("onboard");
  const portal = ONB.portals.find((p) => p.key === ONB.portal) || {};

  host.innerHTML = `
    <div class="onb-card">
      <p class="onb-eyebrow">${onbEsc(portal.label || "")}</p>
      <h1>Register your work email</h1>
      <p class="onb-lede">Public-sector and non-profit domains only —
        ${onbEsc(ONB.suffixes.join(", "))}. This is how the portal knows which
        path you are on.</p>

      <label class="onb-field">
        <span>Work email</span>
        <input id="onbEmail" type="email" autocomplete="email" spellcheck="false"
               placeholder="you@agency.gov">
      </label>
      <label class="onb-field">
        <span>Organisation <em>(optional)</em></span>
        <input id="onbOrg" type="text" autocomplete="organization"
               placeholder="Department of Environmental Services">
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
