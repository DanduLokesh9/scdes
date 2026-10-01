/* The corner dock — the "?" and the bell, and where they sit.

   Reported as: "I want to drag this help icon anywhere on the screen" → "It's
   fixed and not moving."

   It used to drag, and that was removed deliberately when reporting moved into
   the help panel. The argument was that the panel opens and closes, so it no
   longer covers the thing you are trying to report, and a help button that has
   wandered off somewhere is a help button nobody finds.

   The first half of that stopped being true. There are two buttons in that
   corner now, and the panel above them is 392px wide by up to 620px tall —
   a large part of a laptop screen, landing exactly where this application puts
   its record column. Someone reporting a fault in the bottom right cannot see
   it while they are describing it.

   So it drags again, with the original objection answered rather than ignored:

   - **The two move together.** They are one dock, not two things to reposition
     separately. Order comes from CSS rather than from which script initialized
     first, so the bell stays to the left of the "?" wherever it ends up.
   - **It cannot be lost.** Every position is clamped to the viewport on the way
     in and again on resize, so a spot saved on a wide monitor lands on screen
     on a laptop instead of just off the edge of it.
   - **A drag is told from a click by distance.** Five pixels of travel while
     pressing is still a press, so the buttons keep working and nothing needs a
     separate grip handle to drag by — which is what the old bug dock had, and
     it was one more thing to explain.

   The panels follow the dock, choosing the side with more room and taking the
   height that is actually there. A panel with a fixed 620px height would run
   off the top of the window as soon as the dock was dragged upwards. */

const DOCK = { rail: null, moved: false, down: false };
const DOCK_KEY = "scdes.dock";
const DOCK_EDGE = 12;        // never closer than this to any edge

/** The container both buttons live in. Created on first use. */
function dockRail() {
  if (DOCK.rail && document.body.contains(DOCK.rail)) return DOCK.rail;
  const rail = document.createElement("div");
  rail.id = "dockRail";
  rail.className = "dock-rail";
  rail.title = "Drag to move";
  document.body.appendChild(rail);
  DOCK.rail = rail;
  restoreDock();
  wireDockDrag(rail);
  return rail;
}

/* ------------------------------------------------------------- positioning */

/** Put the rail at a viewport coordinate, clamped so it stays reachable. */
function placeRail(x, y) {
  const rail = DOCK.rail;
  if (!rail) return;
  const w = rail.offsetWidth || 112;
  const h = rail.offsetHeight || 50;
  const left = Math.min(Math.max(DOCK_EDGE, x),
                        Math.max(DOCK_EDGE, window.innerWidth - w - DOCK_EDGE));
  const top = Math.min(Math.max(DOCK_EDGE, y),
                       Math.max(DOCK_EDGE, window.innerHeight - h - DOCK_EDGE));
  rail.style.left = `${left}px`;
  rail.style.top = `${top}px`;
  rail.style.right = "auto";
  rail.style.bottom = "auto";
}

function saveDock() {
  const rail = DOCK.rail;
  if (!rail) return;
  const box = rail.getBoundingClientRect();
  try {
    localStorage.setItem(DOCK_KEY, JSON.stringify({ x: box.left, y: box.top }));
  } catch (e) { /* private mode: it simply does not persist */ }
}

function restoreDock() {
  let at = null;
  try { at = JSON.parse(localStorage.getItem(DOCK_KEY) || "null"); }
  catch (e) { return; }
  if (!at || typeof at.x !== "number" || typeof at.y !== "number") return;
  // Deferred one frame: the buttons have not been appended yet, so the rail
  // still measures 0x0 and would clamp against its own empty width.
  setTimeout(() => placeRail(at.x, at.y), 0);
}

/** Back to the bottom-right corner the stylesheet puts it in. */
function resetDock() {
  const rail = DOCK.rail;
  if (!rail) return;
  ["left", "top", "right", "bottom"].forEach((p) => rail.style.removeProperty(p));
  try { localStorage.removeItem(DOCK_KEY); } catch (e) {}
  placeDockPanels();
}

/* ----------------------------------------------------------------- dragging */

function wireDockDrag(rail) {
  let startX = 0, startY = 0, originX = 0, originY = 0;

  const begin = (e) => {
    const p = e.touches ? e.touches[0] : e;
    const box = rail.getBoundingClientRect();
    DOCK.down = true;
    DOCK.moved = false;
    startX = p.clientX; startY = p.clientY;
    originX = box.left; originY = box.top;
  };

  const move = (e) => {
    if (!DOCK.down) return;
    const p = e.touches ? e.touches[0] : e;
    const dx = p.clientX - startX, dy = p.clientY - startY;
    // A few pixels of travel while pressing a button is a press, not a drag.
    // Without this the dock would move under anyone with an unsteady hand and
    // the buttons would stop opening.
    if (!DOCK.moved && Math.abs(dx) + Math.abs(dy) < 5) return;
    DOCK.moved = true;
    rail.classList.add("dragging");
    placeRail(originX + dx, originY + dy);
    placeDockPanels();
    if (e.cancelable) e.preventDefault();
  };

  const end = () => {
    if (!DOCK.down) return;
    DOCK.down = false;
    rail.classList.remove("dragging");
    if (DOCK.moved) saveDock();
  };

  rail.addEventListener("mousedown", begin);
  rail.addEventListener("touchstart", begin, { passive: true });
  document.addEventListener("mousemove", move);
  document.addEventListener("touchmove", move, { passive: false });
  document.addEventListener("mouseup", end);
  document.addEventListener("touchend", end);

  // Swallow the click that ends a drag, so letting go over the "?" does not
  // also open the panel. Capture phase, because the buttons' own handlers are
  // on the buttons themselves.
  rail.addEventListener("click", (e) => {
    if (!DOCK.moved) return;
    e.stopPropagation();
    e.preventDefault();
    DOCK.moved = false;
  }, true);
}

/* ------------------------------------------------------------- the panels */

/** Place one panel beside the dock, on whichever side has more room. */
function placeDockPanel(panel) {
  const rail = DOCK.rail;
  if (!rail || !panel) return;
  const r = rail.getBoundingClientRect();
  if (!r.width && !r.height) return;          // not laid out yet
  const gap = 12;

  const roomAbove = r.top - gap - DOCK_EDGE;
  const roomBelow = window.innerHeight - r.bottom - gap - DOCK_EDGE;
  const above = roomAbove >= roomBelow;
  panel.style.maxHeight =
    `${Math.max(220, Math.floor(above ? roomAbove : roomBelow))}px`;

  const w = panel.offsetWidth, h = panel.offsetHeight;
  const top = above ? r.top - gap - h : r.bottom + gap;
  const left = r.right - w;                   // right edges aligned

  panel.style.left = `${Math.min(Math.max(DOCK_EDGE, left),
    Math.max(DOCK_EDGE, window.innerWidth - w - DOCK_EDGE))}px`;
  panel.style.top = `${Math.min(Math.max(DOCK_EDGE, top),
    Math.max(DOCK_EDGE, window.innerHeight - h - DOCK_EDGE))}px`;
  panel.style.right = "auto";
  panel.style.bottom = "auto";
}

/** Both of them, wherever they are — only one is ever open, but this is called
    from the drag loop and must not care which. */
function placeDockPanels() {
  ["guidePanel", "notifyPanel"].forEach((id) => {
    const panel = document.getElementById(id);
    if (panel) placeDockPanel(panel);
  });
}

// A window that shrinks can strand the dock off the edge, which is the one
// state it must never be in.
window.addEventListener("resize", () => {
  const rail = DOCK.rail;
  if (rail && rail.style.left) {
    const box = rail.getBoundingClientRect();
    placeRail(box.left, box.top);
  }
  placeDockPanels();
});

window.dockRail = dockRail;
window.placeDockPanel = placeDockPanel;
window.placeDockPanels = placeDockPanels;
window.resetDock = resetDock;
