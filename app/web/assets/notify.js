/* The bell — what the team said about something you reported.

   Closes the loop the bug panel opens. Somebody reports a fault, it goes quiet,
   and without this the only way to find out whether anyone looked at it is to
   go hunting for the ticket. So a reply arrives here instead, and from here it
   can be reopened if the answer is not right.

   Notifications are derived, not stored. The team's replies on a ticket *are*
   the notifications — a separate table would be a second copy of something the
   ticket already holds, and the two would drift the first time a reply was
   edited. The only extra fact is "have I read this", which lives in the
   browser, because it is a property of a person at a screen rather than of the
   record.

   Polling, not pushing. This is a stdlib HTTP server with no socket layer, and
   a bug reply is not urgent — a minute's delay costs nothing, and the check
   pauses entirely when the tab is in the background rather than waking a laptop
   to ask whether anybody has answered yet. */

const NOTIFY = { items: [], seen: 0, open: false, timer: null };

const nEsc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function notifyWho() {
  try {
    const saved = JSON.parse(localStorage.getItem("scdes.registration") || "{}");
    return (saved.email || "").toLowerCase();
  } catch (e) { return ""; }
}

/** When they last opened the bell. Everything newer counts as unread. */
function lastSeen() {
  try { return localStorage.getItem("scdes.notifySeen") || ""; }
  catch (e) { return ""; }
}

function markSeen() {
  const newest = NOTIFY.items[0];
  try {
    localStorage.setItem("scdes.notifySeen",
                         newest ? newest.at : new Date().toISOString());
  } catch (e) {}
  paintBell();
}

function unreadCount() {
  const since = lastSeen();
  return NOTIFY.items.filter((i) => !since || i.at > since).length;
}

/* ------------------------------------------------------------------ polling */

async function pollNotifications() {
  const email = notifyWho();
  if (!email) { NOTIFY.items = []; paintBell(); return; }
  try {
    // The token, where there is one. The server prefers it over the address in
    // the query string — otherwise knowing somebody's work email is enough to
    // read the replies on their reports.
    const headers = {};
    try {
      const token = localStorage.getItem("scdes.session");
      if (token) headers["X-GAIUS-Session"] = token;
    } catch (e) {}
    const r = await fetch("/api/notifications?email=" + encodeURIComponent(email),
                          { headers })
      .then((res) => res.json());
    const before = unreadCount();
    NOTIFY.items = r.items || [];
    // Recorded so the panel can say "sign in again" rather than "nothing yet".
    // The server no longer accepts an address as proof of who is asking, and a
    // browser from before tokens shipped has none — an empty bell and a bell
    // that cannot ask are different things and must not look the same.
    NOTIFY.signedIn = r.signed_in !== false;
    NOTIFY.note = r.note || "";
    paintBell();
    // Announced once, when it arrives, rather than every poll. A badge that
    // reappears every minute is a badge people learn to ignore.
    const now = unreadCount();
    if (now > before && !NOTIFY.open && window.toast) {
      const newest = NOTIFY.items[0];
      window.toast(`${newest.id} — ${newest.status}. ${newest.by} replied.`);
    }
  } catch (e) { /* offline: the bell simply does not update */ }
}

function startPolling() {
  if (NOTIFY.timer) clearInterval(NOTIFY.timer);
  NOTIFY.timer = setInterval(() => {
    // Nothing while the tab is hidden. Waking a laptop once a minute to ask
    // whether anybody has answered a bug report is not a good trade.
    if (document.visibilityState === "visible") pollNotifications();
  }, 60000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") pollNotifications();
  });
  pollNotifications();
}

/* -------------------------------------------------------------------- the UI */

function paintBell() {
  const bell = document.getElementById("notifyDock");
  if (!bell) return;
  const n = unreadCount();
  bell.classList.toggle("has-unread", n > 0);
  const badge = bell.querySelector(".n-badge");
  if (badge) {
    badge.textContent = n > 9 ? "9+" : String(n);
    badge.hidden = n === 0;
  }
  bell.title = n
    ? `${n} update${n === 1 ? "" : "s"} on what you reported`
    : "Updates on what you reported";
  bell.setAttribute("aria-label", bell.title);
}

function notifyPanel(inner) {
  const body = document.getElementById("notifyBody");
  if (body) body.innerHTML = inner;
  if (window.placeDockPanel) {
    window.placeDockPanel(document.getElementById("notifyPanel"));
  }
}

function openNotify() {
  if (NOTIFY.open) return;
  NOTIFY.open = true;

  const host = document.createElement("div");
  host.id = "notifyPanel";
  host.className = "guide-panel notify-panel";
  host.innerHTML = `
    <div class="g-head">
      <span class="g-badge" aria-hidden="true">🔔</span>
      <span class="g-title"><b>Updates</b><span>On what you reported</span></span>
      <button class="g-close" id="nClose" type="button" aria-label="Close">×</button>
    </div>
    <div class="g-body" id="notifyBody"></div>`;
  document.body.appendChild(host);
  document.getElementById("nClose").onclick = closeNotify;

  notifyHome();
  // Read on open, not on close: they have seen the list by the time it renders,
  // and a badge that clears only when you remember to close properly is a badge
  // that stays lit.
  markSeen();
}

function closeNotify() {
  NOTIFY.open = false;
  const host = document.getElementById("notifyPanel");
  if (host) host.remove();
}

function notifyHome() {
  const since = lastSeen();
  if (!notifyWho()) {
    notifyPanel(`<p class="g-sub">Sign in and anything you report will be
      answered here.</p>`);
    return;
  }
  // Cannot ask, as opposed to nothing to say.
  if (NOTIFY.signedIn === false) {
    notifyPanel(`
      <div class="g-hero" aria-hidden="true">🔔</div>
      <h3 class="g-h">Sign in again to see replies</h3>
      <p class="g-sub">${nEsc(NOTIFY.note
        || "This browser has no proof of who it belongs to.")}</p>`);
    return;
  }
  if (!NOTIFY.items.length) {
    notifyPanel(`
      <div class="g-hero" aria-hidden="true">🔔</div>
      <h3 class="g-h">Nothing yet</h3>
      <p class="g-sub">When someone looks at a bug you reported, their reply
        appears here.</p>`);
    return;
  }

  notifyPanel(NOTIFY.items.map((item, i) => `
    <div class="n-item${!since || item.at > since ? " fresh" : ""}">
      <div class="n-top">
        <span class="bug-id">${nEsc(item.id)}</span>
        <span class="pill ${item.status === "fixed" ? "ok"
          : item.status === "wont_fix" ? "neutral" : "warn"}">${
          nEsc(item.status.replace("_", " "))}</span>
        <span class="n-when">${nEsc((item.at || "").slice(0, 16))}</span>
      </div>
      <p class="n-about">You reported: ${nEsc(item.about)}</p>
      <p class="n-msg"><b>${nEsc(item.by)}</b> ${nEsc(item.message)}</p>
      ${item.can_reopen ? `
        <button class="btn ghost n-reopen" data-reopen="${nEsc(item.id)}"
          data-i="${i}" type="button">That did not fix it</button>` : ""}
    </div>`).join(""));

  document.querySelectorAll("[data-reopen]").forEach((b) => {
    b.onclick = () => reopenForm(b.dataset.reopen);
  });
}

/* The other half of the loop. "If they aren't satisfied, they can reopen the
   ticket with additional feedback" — so the button asks for the feedback rather
   than silently flipping a status. */
function reopenForm(id) {
  notifyPanel(`
    <button class="g-back" id="nBack" type="button">← Back</button>
    <h3 class="g-h" style="text-align:left">Reopen ${nEsc(id)}</h3>
    <p class="g-sub" style="text-align:left">Say what is still wrong. It goes
      back to the team with everything already on the ticket.</p>
    <label class="g-field"><span>What is still happening?</span>
      <textarea id="nReason" rows="3"
        placeholder="In your own words"></textarea></label>
    <p class="signin-error" id="nError" hidden></p>
    <div class="row"><button class="btn" id="nSend" type="button">Reopen</button></div>`);

  document.getElementById("nBack").onclick = () => notifyHome();
  document.getElementById("nSend").onclick = async () => {
    const message = document.getElementById("nReason").value.trim();
    const err = document.getElementById("nError");
    if (!message) {
      err.textContent = "Say what is still wrong — reopening with nothing new "
        + "leaves the team where they started.";
      err.hidden = false;
      return;
    }
    let r;
    try {
      const response = await fetch("/api/bugs/reopen", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, message, email: notifyWho() }),
      });
      r = await response.json();
    } catch (e) { r = { ok: false, error: "Could not reach the server." }; }

    if (!r.ok) { err.textContent = r.error; err.hidden = false; return; }
    await pollNotifications();
    notifyPanel(`
      <div class="g-hero" aria-hidden="true">↩</div>
      <h3 class="g-h">${nEsc(id)} is open again</h3>
      <p class="g-sub">The team will see what you added. You will get a reply
        here.</p>`);
  };
  document.getElementById("nReason").focus();
}

/* ------------------------------------------------------------------- init */

function initNotify() {
  if (document.getElementById("notifyDock")) return;
  const bell = document.createElement("button");
  bell.id = "notifyDock";
  bell.className = "notify-dock";
  bell.type = "button";
  bell.innerHTML = `<span aria-hidden="true">🔔</span>
    <span class="n-badge" hidden>0</span>`;
  // Shared rail, so the two move as one dock. CSS `order` keeps the bell to the
  // left of the "?" regardless of which of these initialized first.
  (window.dockRail ? window.dockRail() : document.body).appendChild(bell);

  bell.onclick = () => {
    // One panel at a time — the two would otherwise sit on top of each other
    // in the same corner.
    if (window.closeGuide) window.closeGuide();
    NOTIFY.open ? closeNotify() : openNotify();
  };
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && NOTIFY.open) closeNotify();
  });

  paintBell();
  startPolling();
}

window.initNotify = initNotify;
window.pollNotifications = pollNotifications;
window.openNotify = openNotify;
window.closeNotify = closeNotify;
window.notifyUnread = unreadCount;
window.notifyItems = () => NOTIFY.items.slice();   // for the checks
