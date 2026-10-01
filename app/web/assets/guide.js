/* One place to ask for help.

   Four things had grown up in four corners: a "? Guide" chip in the header for
   the tour, a "Report a bug" dock at the bottom right, a sixty-second intro
   reachable only from the Welcome screen, and a command palette behind Ctrl-K
   that nobody discovers. Each was reasonable on its own and together they were
   a scavenger hunt.

   This is the launcher they all live in now. Nothing here is new behavior —
   the tour, the bug form, the intro and the destination search are the ones
   already built, gathered behind one button in the corner where people look
   for help.

   Two decisions worth stating:

   **It takes the agency's colors, not a fixed brand.** Every other surface in
   this application is themed from the agency's own palette, and a help panel in
   somebody else's orange would be the one thing on screen that belongs to a
   different product.

   **It is fixed to the corner and does not drag.** The bug dock was draggable
   because it sat over the page and could cover the thing being reported. This
   opens over the page and closes again, so the reason no longer applies, and a
   help button that has wandered off somewhere is a help button nobody finds. */

const GUIDE = { open: false };

const gEsc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* What the panel offers. Each one delegates to the thing that already exists,
   so there is one implementation of the tour and one of the bug form. */
function guideItems() {
  return [
    {
      icon: "⚑",
      title: "Report an issue",
      note: "Tell the team about a bug",
      go: () => guideShowBugForm(),
      when: () => !!window.renderBugForm,
    },
    {
      icon: "◷",
      title: "Getting started",
      note: "The sixty-second introduction",
      go: () => window.replayWelcome && window.replayWelcome(),
      when: () => !!window.replayWelcome,
    },
    {
      icon: "→",
      title: "Show me around",
      note: "A walkthrough of this screen",
      go: () => window.startTour && window.startTour(true),
      when: () => !!window.startTour,
    },
    {
      icon: "◆",
      title: "What is this screen?",
      note: "What is here and what to do next",
      go: () => explainScreen(),
      when: () => true,
    },
    {
      icon: "⌘",
      title: "Quick tips",
      note: "Shortcuts worth knowing",
      go: () => showTips(),
      when: () => true,
    },
  ].filter((i) => i.when());
}

/* --------------------------------------------------------- what is this screen

   Assembled from what the screen already declares about itself — its title, its
   subtitle and the reason rail — rather than a second description written here
   that would drift from the first. */
function explainScreen() {
  const title = (document.getElementById("viewTitle") || {}).textContent || "";
  const sub = (document.getElementById("viewSub") || {}).textContent || "";
  const reasons = [...document.querySelectorAll("#reasonBody .reason-block")]
    .map((b) => ({
      head: (b.querySelector("h4") || {}).textContent || "",
      body: (b.querySelector("p") || {}).textContent || "",
      cite: (b.querySelector(".reason-cite") || {}).textContent || "",
    }))
    .filter((r) => r.head || r.body);

  guidePanel(`
    <button class="g-back" id="gBack" type="button">← Back</button>
    <h3 class="g-h">${gEsc(title || "This screen")}</h3>
    <p class="g-sub">${gEsc(sub || "")}</p>
    ${reasons.length ? reasons.map((r) => `
      <div class="g-block">
        <b>${gEsc(r.head)}</b>
        <p>${gEsc(r.body)}</p>
        ${r.cite ? `<span class="g-cite">${gEsc(r.cite)}</span>` : ""}
      </div>`).join("")
      : `<p class="g-sub">This screen has not declared a reason. That is
         usually because nothing is selected yet.</p>`}`);
  wireBack();
}

function showTips() {
  const tips = [
    ["Ctrl K", "Ask a question, run a what-if, or describe a problem"],
    ["Arrow keys", "Move through the sidebar without the mouse"],
    ["Esc", "Close whatever is open"],
    ["Tab", "Move forward through a screen; Shift-Tab goes back"],
  ];
  guidePanel(`
    <button class="g-back" id="gBack" type="button">← Back</button>
    <h3 class="g-h">Quick tips</h3>
    <p class="g-sub">Shortcuts that save the most time.</p>
    ${tips.map(([key, what]) => `
      <div class="g-tip"><kbd>${gEsc(key)}</kbd><span>${gEsc(what)}</span></div>`)
      .join("")}`);
  wireBack();
}

/** The bug form, inside the panel. */
function guideShowBugForm() {
  const body = document.getElementById("guideBody");
  if (!body || !window.renderBugForm) return;
  window.renderBugForm(body, {
    onBack: () => guideHome(),
    onSent: (r) => {
      guidePanel(`
        <h3 class="g-h">Thank you — that is filed</h3>
        <p class="g-sub">${gEsc(r.thanks || "")}</p>
        ${r.seen_before ? `<p class="g-sub">${r.seen_before} other report(s)
          look like this one, so it is already known to be more than a
          one-off.</p>` : ""}
        <button class="g-item" id="gDone" type="button">
          <span class="g-ico" aria-hidden="true">←</span>
          <span class="g-item-main"><b>Back to the guide</b>
            <span>Or close this and carry on</span></span>
        </button>`);
      const done = document.getElementById("gDone");
      if (done) done.onclick = () => guideHome();
    },
  });
}

function wireBack() {
  const back = document.getElementById("gBack");
  if (back) back.onclick = () => guideHome();
}

/* ------------------------------------------------------------- the panel */

function guidePanel(inner) {
  const body = document.getElementById("guideBody");
  if (body) body.innerHTML = inner;
  // Its height changes with what is in it, and which side of the dock it opens
  // on depends on that height, so it is re-placed on every content change
  // rather than only on open.
  if (window.placeDockPanel) {
    window.placeDockPanel(document.getElementById("guidePanel"));
  }
}

function guideHome() {
  guidePanel(`
    <div class="g-hero" aria-hidden="true">?</div>
    <h3 class="g-h">Need help finding something?</h3>
    <p class="g-sub">Anything on this list, or type where you want to go.</p>
    <div class="g-eyebrow">Help</div>
    ${guideItems().map((item, i) => `
      <button class="g-item" data-item="${i}" type="button">
        <span class="g-ico" aria-hidden="true">${item.icon}</span>
        <span class="g-item-main">
          <b>${gEsc(item.title)}</b>
          <span>${gEsc(item.note)}</span>
        </span>
      </button>`).join("")}`);

  document.querySelectorAll("[data-item]").forEach((b) => {
    b.onclick = () => {
      const item = guideItems()[Number(b.dataset.item)];
      if (!item) return;
      // The tour and the intro take over the whole screen, so the panel gets
      // out of the way first. Everything else — including reporting a bug —
      // stays inside it: a second floating layer on top of this one is one
      // layer too many, and this is where the person already is.
      if (["Getting started", "Show me around"].includes(item.title)) {
        closeGuide();
      }
      item.go();
    };
  });
}

function openGuide() {
  if (GUIDE.open) return;
  GUIDE.open = true;
  const host = document.createElement("div");
  host.id = "guidePanel";
  host.className = "guide-panel";
  host.innerHTML = `
    <div class="g-head">
      <span class="g-badge" aria-hidden="true">?</span>
      <span class="g-title"><b>Platform guide</b><span id="gWho">How to use
        this</span></span>
      <button class="g-close" id="gClose" type="button"
        aria-label="Close">×</button>
    </div>
    <div class="g-body" id="guideBody"></div>
    <form class="g-ask" id="gAsk">
      <input id="gAskInput" type="text" autocomplete="off"
             placeholder="Type where you want to go…"
             aria-label="Type where you want to go">
      <button class="g-send" type="submit" aria-label="Go">➤</button>
    </form>`;
  document.body.appendChild(host);

  const agency = window.SCDES_AGENCY || {};
  const who = document.getElementById("gWho");
  if (who && agency.abbrev && agency.abbrev !== "—") {
    who.textContent = "How to use " + agency.abbrev;
  }

  document.getElementById("gClose").onclick = closeGuide;
  guideHome();
  wireAsk();
  document.getElementById("gAskInput").focus();
}

function closeGuide() {
  GUIDE.open = false;
  const host = document.getElementById("guidePanel");
  if (host) host.remove();
}

/* The typed twin of the voice command. Same matcher, so "audit trail" typed and
   "audit trail" spoken behave identically — and one of them can be tested. */
function wireAsk() {
  const form = document.getElementById("gAsk");
  const box = document.getElementById("gAskInput");
  if (!form || !box) return;

  form.onsubmit = (e) => {
    e.preventDefault();
    const said = box.value.trim();
    if (!said) return;

    const hit = window.matchDestination && window.matchDestination(said);
    if (!hit) {
      guidePanel(`
        <button class="g-back" id="gBack" type="button">← Back</button>
        <h3 class="g-h">Nothing matched “${gEsc(said)}”</h3>
        <p class="g-sub">Try one of these, or a word from the sidebar.</p>
        ${[...document.querySelectorAll(".rail-item[data-view]")]
          .filter((b) => !b.disabled)
          .map((b) => `<div class="g-tip"><span>${
            gEsc(b.textContent.replace(/\s+/g, " ").trim())}</span></div>`)
          .join("")}`);
      wireBack();
      return;
    }
    if (hit.locked) {
      guidePanel(`
        <button class="g-back" id="gBack" type="button">← Back</button>
        <h3 class="g-h">${gEsc(hit.label)}</h3>
        <p class="g-sub">That is part of the paid workflow management. Your
          framework is free and stays yours.</p>`);
      wireBack();
      return;
    }
    box.value = "";
    closeGuide();
    if (window.go) window.go(hit.view);
  };
}

/* ------------------------------------------------------------- the button */

function initGuide() {
  if (document.getElementById("guideDock")) return;
  const dock = document.createElement("button");
  dock.id = "guideDock";
  dock.className = "guide-dock";
  dock.type = "button";
  dock.setAttribute("aria-label", "Help and reporting");
  dock.innerHTML = `<span aria-hidden="true">?</span>`;
  dock.title = "Help, walkthrough, and reporting a bug";
  // Into the shared rail, which is what actually gets dragged. Falls back to
  // the body so the button still appears if dock.js failed to load — which is
  // exactly when someone wants the help panel.
  (window.dockRail ? window.dockRail() : document.body).appendChild(dock);
  dock.onclick = () => {
    // One panel at a time. Both live in the same corner, and two stacked on
    // each other is worse than either.
    if (window.closeNotify) window.closeNotify();
    GUIDE.open ? closeGuide() : openGuide();
  };

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && GUIDE.open) closeGuide();
  });
}

window.initGuide = initGuide;
window.guideShowBugForm = guideShowBugForm;
window.openGuide = openGuide;
window.closeGuide = closeGuide;
