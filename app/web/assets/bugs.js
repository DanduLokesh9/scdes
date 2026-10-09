/* Report a bug — with the evidence already collected.

   Most faults cannot be reproduced on demand. Asking somebody to make it happen
   again is asking them to lose the one recording of it that existed, so this
   runs a rolling buffer of the last minute of technical activity from the
   moment the page loads. Pressing "Report a bug" attaches what already
   happened; the person is asked two questions and nothing else.

   What is captured, exactly
   -------------------------

   Console errors and warnings · uncaught exceptions and rejected promises ·
   network calls as method, address and status code · which screen you moved to
   · which control you pressed, by its label.

   What is not, and cannot be turned on later without changing this file:

   **No page contents.** Nothing reads the DOM. A framework answer half-typed
   into a textarea is not in the buffer because nothing ever looks at it.

   **No bodies.** A network entry records that a POST to /api/versions/answer
   returned 200 in 34ms. Not what was answered.

   **No keystrokes, no screen recording.** Session replay is Phase 2 and is a
   different conversation, because it records whatever is on screen.

   Redaction happens on the way *in*
   ---------------------------------

   Email addresses and codes are stripped before an event enters the buffer,
   not before it is sent. The difference matters: this application puts
   `?email=` on every API call, so a buffer that redacted on send would hold a
   government employee's address in memory for the whole session and only clean
   it up if a report happened to be filed. The server scrubs again on arrival,
   because a rule that depends on the client behaving is not a rule.

   Nothing is transmitted until the person presses Send. The form used to list
   the whole payload above the button; the client had that removed, so the
   statement of what is attached is now the line under the heading rather than
   a manifest. The capture rules above are unchanged — they are enforced here
   and again on arrival, not by what the form happens to display. */

const BUGS = {
  events: [],
  max: 120,
  windowMs: 60000,
  open: false,
  wired: false,
};

const bugEsc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ------------------------------------------------------------- redaction */

const BUG_EMAIL = /[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/g;
const BUG_SECRET = /([?&](?:code|token|key|secret|password|auth|session)=)[^&\s]+/gi;
const BUG_DIGITS = /\b\d{7,}\b/g;

function bugScrub(text) {
  return String(text ?? "")
    .replace(BUG_EMAIL, "[email removed]")
    .replace(BUG_SECRET, "$1[removed]")
    .replace(BUG_DIGITS, "[number removed]")
    .slice(0, 600);
}

/* --------------------------------------------------------------- the buffer */

function bugPush(kind, text, extra) {
  BUGS.events.push({
    kind,
    at: new Date().toISOString(),
    text: bugScrub(text),
    ...(extra || {}),
  });
  const cutoff = Date.now() - BUGS.windowMs;
  // Bounded twice: by age, so it is genuinely the last minute, and by count, so
  // a page throwing an error in a loop cannot grow it without limit.
  BUGS.events = BUGS.events
    .filter((e) => new Date(e.at).getTime() >= cutoff)
    .slice(-BUGS.max);
}

function startCapture() {
  if (BUGS.wired) return;
  BUGS.wired = true;

  const realError = console.error.bind(console);
  const realWarn = console.warn.bind(console);
  console.error = (...a) => { bugPush("error", a.map(String).join(" ")); realError(...a); };
  console.warn = (...a) => { bugPush("warn", a.map(String).join(" ")); realWarn(...a); };

  window.addEventListener("error", (e) => {
    bugPush("error", `${e.message} (${e.filename || "?"}:${e.lineno || 0})`);
  });
  window.addEventListener("unhandledrejection", (e) => {
    bugPush("error", "unhandled rejection: " + String(e.reason));
  });

  // Method, address and status. Never the body — see the header comment.
  const realFetch = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const started = performance.now();
    const url = typeof input === "string" ? input : (input && input.url) || "";
    const method = (init && init.method) || "GET";
    try {
      const response = await realFetch(input, init);
      bugPush("network", url, { method, status: String(response.status),
                                ms: String(Math.round(performance.now() - started)) });
      return response;
    } catch (err) {
      bugPush("network", url, { method, status: "failed",
                                ms: String(Math.round(performance.now() - started)) });
      throw err;
    }
  };

  // Which screen, and which control — by its label, not its contents.
  document.addEventListener("click", (e) => {
    const el = e.target && e.target.closest &&
      e.target.closest("button, a, .rail-item, [role=option]");
    if (!el) return;
    const label = (el.getAttribute("aria-label") || el.textContent || "")
      .replace(/\s+/g, " ").trim().slice(0, 60);
    if (label) bugPush("click", label);
  }, true);
}

/** Called by the shell when the view changes. */
function bugNoteView(view) {
  bugPush("nav", "moved to " + view);
}

/* ------------------------------------------------------------- the context */

function bugContext() {
  const agency = window.SCDES_AGENCY || {};
  return {
    view: (document.getElementById("viewTitle") || {}).textContent || "",
    url: bugScrub(location.pathname + location.search + location.hash),
    browser: navigator.userAgent.slice(0, 200),
    screen: `${window.innerWidth}x${window.innerHeight}`,
    version: window.LNCH_BUILD || "unknown",
    agency: agency.abbrev || "",
  };
}

function bugWho() {
  try {
    const saved = JSON.parse(localStorage.getItem("scdes.registration") || "{}");
    return { email: saved.email || "", name: saved.name || "" };
  } catch (e) { return { email: "", name: "" }; }
}

/* The standalone "Report a bug" dock used to be built here, with its own drag
   handling and its own saved position. Reporting moved into the help panel and
   the dock went with it; dragging came back as dock.js, which moves the "?"
   and the bell together rather than a third floating thing. What is left in
   this file is capture and the form, which is all it should ever have been. */

/* ---------------------------------------------------------------- the form */

/* The form, rendered wherever it is asked to be.

   It used to build its own full-screen overlay. Now that every route to it goes
   through the help panel, a second floating layer on top of the first was one
   layer too many — and the panel is where the person already is.

   `renderBugForm` fills a container and wires it; the caller owns the frame.
   That also means the two questions and the send button have one
   implementation rather than one per surface.

   It used to end with a "What gets sent with this" disclosure listing every
   captured event. The client asked for it to go — "people don't care what gets
   sent to us" — and he is right that a reader who has decided to report
   something does not want a manifest first. The consent it existed to obtain
   now rides on the one line under the heading, which says plainly that the
   technical detail is already attached. What is captured has not changed, and
   the answer in full is still one question away in the help panel; it is no
   longer in the way of the two questions that matter. */

function bugFormMarkup() {
  return `
    <button class="g-back" id="bugBack" type="button">← Back</button>
    <h3 class="g-h" style="text-align:left">Report an issue</h3>
    <p class="g-sub" style="text-align:left">Two questions. Everything technical
      is already attached — you do not need to make it happen again.</p>

    <label class="g-field"><span>What did you expect to happen?</span>
      <textarea id="bugExpected" rows="2"
        placeholder="Optional, but it usually explains the report"></textarea></label>

    <label class="g-field"><span>What happened instead?</span>
      <textarea id="bugHappened" rows="3"
        placeholder="In your own words"></textarea></label>

    <p class="signin-error" id="bugError" hidden></p>
    <div class="row" style="margin-top:14px">
      <button class="btn" id="bugSend" type="button">Send report</button>
    </div>`;
}

/** Fill `host` with the form and wire it. `onBack` and `onSent` are the frame's. */
function renderBugForm(host, { onBack, onSent } = {}) {
  // Frozen at the moment of asking. Anything that happens while the form is
  // open — including clicking around inside it — is not the bug.
  const captured = BUGS.events.slice();
  const context = bugContext();
  const who = bugWho();

  host.innerHTML = bugFormMarkup();

  const back = document.getElementById("bugBack");
  if (back) back.onclick = () => onBack && onBack();
  const box = document.getElementById("bugHappened");
  if (box) box.focus();

  document.getElementById("bugSend").onclick = async () => {
    const happened = document.getElementById("bugHappened").value.trim();
    const err = document.getElementById("bugError");
    if (!happened) {
      err.textContent = "Say what happened — without that there is nothing to "
        + "look into.";
      err.hidden = false;
      return;
    }
    const send = document.getElementById("bugSend");
    send.disabled = true; send.textContent = "Sending…";

    let r;
    try {
      const response = await fetch("/api/bugs/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected: document.getElementById("bugExpected").value.trim(),
          happened, context, events: captured,
          reporter: who.email, name: who.name, agency: context.agency,
        }),
      });
      r = await response.json();
    } catch (e) {
      r = { ok: false, error: "Could not reach the server." };
    }

    if (!r.ok) {
      send.disabled = false; send.textContent = "Send report";
      err.textContent = r.error || "Could not send that.";
      err.hidden = false;
      return;
    }
    if (onSent) onSent(r);
  };
}

/** Kept as the way in from anywhere: opens the panel and shows the form. */
function openBugForm() {
  if (window.openGuide) window.openGuide();
  if (window.guideShowBugForm) window.guideShowBugForm();
}

/* ------------------------------------------------------------------- init */

function initBugs() {
  /* Capture still starts with the page — that is the whole point of it, and it
     has nothing to do with where the button lives.

     The button itself is gone: "Report an issue" is the first item in the help
     launcher (guide.js) now. Four help surfaces in four corners was a scavenger
     hunt, and the one people looked for was the question mark. */
  startCapture();
}

window.initBugs = initBugs;
window.bugNoteView = bugNoteView;
window.bugBuffer = () => BUGS.events.slice();      // for the checks
window.openBugForm = openBugForm;
window.renderBugForm = renderBugForm;
