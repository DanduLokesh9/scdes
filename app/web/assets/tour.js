/* Guided tour.

   The application puts a lot on screen at once — a command bar, a lifecycle
   spine, three columns, a mode that changes what everyone is allowed to do —
   and none of it announces itself. Someone opening this for the first time has
   no way to know that Ctrl-K takes plain English, or that "Tuning open" is a
   governance state rather than a status light.

   So this spotlights the real interface, step by step, rather than showing a
   video or a screenshot: what is being explained is the thing in front of you,
   and it stays correct when the interface changes.

   Steps whose target is missing are skipped rather than shown pointing at
   nothing — the spine only exists when a project is loaded, and the whole rail
   is empty for an agency with no corpus. */

const TOUR = { at: 0, steps: [], onDone: null };

/* Its own escape rather than reaching for the launcher's, so the tour still
   works if launcher.js failed to load — which is exactly when someone is most
   likely to want help. */
const tourEsc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const TOUR_STEPS = [
  {
    target: ".tb-brand",
    title: "Whose record you are in",
    body: "The agency's own shorthand, with its full name in the breadcrumb " +
          "below. Every figure on every screen is read from that agency's " +
          "adopted documents — nothing here is invented.",
  },
  {
    target: "#cmdkBtn",
    title: "Ask in plain English",
    body: "Ctrl-K opens this anywhere. Three things live here: a cited answer " +
          "from the adopted documents, a what-if that changes nothing, and " +
          '"describe a problem" which drafts a project from a sentence.',
  },
  {
    target: "#tourChip",
    title: "This button",
    body: "The tour is always here if you want it again. Esc leaves at any " +
          "point, and arrow keys step back and forward.",
  },
  {
    target: "#railLaunch",
    title: "Switch agency",
    body: "Opens the map. The application is not South Carolina's — point it " +
          "at any state's adopted corpus and the name, instruments, lifecycle " +
          "and vocabulary all come from those documents.",
  },
  {
    target: "#modeToggle",
    title: "Light and dark",
    body: "A display preference, remembered between visits. It follows your " +
          "operating system until you choose for yourself.",
  },
  {
    target: "#modeChip",
    title: "The governance mode",
    body: '"Tuning open" means the Office of Technology can still move ' +
          'parameters. Once the Council adopts them it becomes "Guardrails ' +
          'live", and from then on even OT must route a change through the ' +
          "Council. This is a one-way door.",
  },
  {
    target: "#integrityChip",
    title: "What is wrong with the record",
    body: "A standing audit of the corpus itself: citations that do not " +
          "resolve, dates left blank, duties assigned to roles the framework " +
          "never established. It reports and proposes — correcting an adopted " +
          "instrument is a Council amendment.",
  },
  {
    target: "#spine",
    title: "Where the project stands",
    body: "The six lifecycle gates. The filled pip is the current one; click " +
          "any gate to open its checklist, which is read straight from " +
          "Appendix H rather than restated.",
  },
  {
    target: ".rail",
    title: "The sections",
    body: "Operating is the live record, Authoring is where it gets " +
          "configured, Assurance is how you check it. Arrow keys move here, " +
          "and typing a letter jumps. OT and GATED tags mark who may act.",
  },
  {
    target: "#record",
    title: "The record",
    body: "What the governed record says. Every number traces to a document, " +
          "and where a value was derived rather than stated, it says so.",
  },
  {
    target: "#reason",
    title: "…and why",
    body: "Always the reason for what is on the left, with the section it " +
          "cites. Explainability is part of the frame rather than a panel you " +
          "go looking for.",
  },
];

function tourVisible(sel) {
  const n = document.querySelector(sel);
  if (!n || n.hidden) return null;
  const r = n.getBoundingClientRect();
  return r.width > 0 && r.height > 0 ? n : null;
}

function startTour(force) {
  TOUR.steps = TOUR_STEPS.filter((s) => tourVisible(s.target));
  if (!TOUR.steps.length) return;
  TOUR.at = 0;
  document.getElementById("tour").hidden = false;
  document.getElementById("tourCard").hidden = false;   // now a separate element
  document.body.classList.add("tour-open");
  drawTour();
  if (force) { try { localStorage.setItem("scdes.tour", "seen"); } catch (e) {} }
}

function endTour() {
  document.getElementById("tour").hidden = true;
  document.getElementById("tourCard").hidden = true;
  document.body.classList.remove("tour-open");
  document.querySelectorAll(".tour-lit").forEach((n) =>
    n.classList.remove("tour-lit"));
  try { localStorage.setItem("scdes.tour", "seen"); } catch (e) {}
  const chip = document.getElementById("tourChip");
  if (chip) chip.focus();
}

function stepTour(by) {
  const next = TOUR.at + by;
  if (next < 0) return;
  if (next >= TOUR.steps.length) { endTour(); return; }
  TOUR.at = next;
  drawTour();
}

function drawTour() {
  const step = TOUR.steps[TOUR.at];
  const node = tourVisible(step.target);
  if (!node) { stepTour(1); return; }

  document.querySelectorAll(".tour-lit").forEach((n) =>
    n.classList.remove("tour-lit"));
  node.classList.add("tour-lit");

  // The mask is four panels around the target rather than one box with a hole,
  // so the spotlit element stays fully interactive and keeps its own colours.
  const r = node.getBoundingClientRect();
  const pad = 6;
  const box = { top: r.top - pad, left: r.left - pad,
                width: r.width + pad * 2, height: r.height + pad * 2 };
  const mask = document.getElementById("tourMask");
  mask.style.setProperty("--lit-top", `${box.top}px`);
  mask.style.setProperty("--lit-left", `${box.left}px`);
  mask.style.setProperty("--lit-width", `${box.width}px`);
  mask.style.setProperty("--lit-height", `${box.height}px`);

  const card = document.getElementById("tourCard");
  const last = TOUR.at === TOUR.steps.length - 1;
  card.innerHTML = `
    <p class="tour-count">${TOUR.at + 1} of ${TOUR.steps.length}</p>
    <h3 id="tourTitle">${tourEsc(step.title)}</h3>
    <p>${tourEsc(step.body)}</p>
    <div class="tour-actions">
      <button class="btn ghost" id="tourSkip" type="button">Skip</button>
      <span class="tour-spacer"></span>
      <button class="btn ghost" id="tourBack" type="button"
        ${TOUR.at === 0 ? "disabled" : ""}>Back</button>
      <button class="btn" id="tourNext" type="button">${
        last ? "Done" : "Next"}</button>
    </div>`;

  placeTourCard(card, box);
  document.getElementById("tourSkip").onclick = endTour;
  document.getElementById("tourBack").onclick = () => stepTour(-1);
  document.getElementById("tourNext").onclick = () => stepTour(1);
  document.getElementById("tourNext").focus();
}

/** Put the card next to the target without covering it.

    Below, then above, then beside. The "beside" case is what the left-hand rail
    needs: it is nearly the full height of the window, so there is no room above
    or below, and centring the card vertically drops it straight on top of the
    thing being explained. */
function placeTourCard(card, box) {
  const W = window.innerWidth, H = window.innerHeight;
  const gap = 12, edge = 12;
  const cw = Math.min(340, W - edge * 2);
  card.style.width = `${cw}px`;

  // Measure after sizing, since the height depends on how the body wraps.
  card.style.visibility = "hidden";
  card.style.top = "0px"; card.style.left = "0px";
  const ch = card.getBoundingClientRect().height;

  const fitsBelow = box.top + box.height + gap + ch < H - edge;
  const fitsAbove = box.top - gap - ch > edge;
  const fitsRight = box.left + box.width + gap + cw < W - edge;
  const fitsLeft = box.left - gap - cw > edge;

  let top, left;
  if (fitsBelow || fitsAbove) {
    top = fitsBelow ? box.top + box.height + gap : box.top - gap - ch;
    left = box.left + box.width / 2 - cw / 2;
  } else if (fitsRight || fitsLeft) {
    left = fitsRight ? box.left + box.width + gap : box.left - gap - cw;
    // Align near the top of a tall target rather than its centre, so the card
    // sits beside the part of it the reader is looking at.
    top = Math.min(box.top, H - ch - edge);
  } else {
    // Nowhere clear: centre it and accept the overlap. The card is above the
    // spotlight in the stacking order, so it stays readable.
    top = (H - ch) / 2;
    left = (W - cw) / 2;
  }

  card.style.left = `${Math.max(edge, Math.min(left, W - cw - edge))}px`;
  card.style.top = `${Math.max(edge, Math.min(top, H - ch - edge))}px`;
  card.style.visibility = "visible";
}

document.addEventListener("keydown", (e) => {
  if (document.getElementById("tour").hidden) return;
  if (e.key === "Escape") { e.preventDefault(); endTour(); }
  else if (e.key === "ArrowRight") { e.preventDefault(); stepTour(1); }
  else if (e.key === "ArrowLeft") { e.preventDefault(); stepTour(-1); }
});

// Re-anchor rather than leaving the spotlight behind when the page reflows.
window.addEventListener("resize", () => {
  if (!document.getElementById("tour").hidden) drawTour();
});

window.startTour = startTour;
window.tourSeen = () => {
  try { return localStorage.getItem("scdes.tour") === "seen"; }
  catch (e) { return true; }
};
