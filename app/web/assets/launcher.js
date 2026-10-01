/* Agency launcher — a real US map, filled with the flag, themed per state.

   The map is genuine geography: Census cartographic boundaries projected with
   Albers equal-area conic (Alaska and Hawaii as insets), built offline by
   tools/build_map.py into us-map.json. No network, no map library.

   The flag is clipped to the country outline rather than laid behind it, so
   the map *is* the flag. Selecting a state lifts it out of the flag and fills
   it with that agency's color. */

/* Bumped whenever this file changes in a way worth confirming reached the
   browser. Printed on load so "is the page running the current code?" is a
   question that can be answered in one look rather than argued about. */
const LNCH_BUILD = "2026-08-28-module-one";

const LNCH = { data: null, map: null, active: null };

console.log(`[launcher] build ${LNCH_BUILD} — state flags enabled`);

/* On `window` as well, because a lexical const in a classic script is not a
   property of it. bugs.js reads `window.LNCH_BUILD` to stamp every ticket, so
   until now every report arrived saying "Build: unknown" — which is the one
   field that answers "was this fixed in the version they were running?", and
   it was blank on the first real report that needed it. */
window.LNCH_BUILD = LNCH_BUILD;

/* ------------------------------------------------------------ color mode */

/* Light and dark are a *display* preference, independent of which agency is
   loaded — switching agency must not reset it, and switching mode must not
   disturb the brand. They meet in one place only: --accent-text, which needs a
   different lightness on a dark canvas, and tokens.css swaps that itself.

   index.html sets data-theme before first paint; this keeps it in sync after. */

function colorMode() {
  return document.documentElement.getAttribute("data-theme") === "dark"
    ? "dark" : "light";
}

function savedMode() {
  try { return localStorage.getItem("scdes.mode"); } catch (e) { return null; }
}

/* `persist` matters: only an actual click writes a preference. Merely rendering
   the buttons must not, or the app would silently stop following the OS the
   first time it loads. */
function applyMode(mode, persist) {
  document.documentElement.setAttribute("data-theme", mode);
  if (persist) {
    try { localStorage.setItem("scdes.mode", mode); } catch (e) {}
  }
  const dark = mode === "dark";
  document.querySelectorAll(".mode-chip").forEach((b) => {
    // The label names what a click will do, not the state you are already in.
    b.textContent = dark ? "☀ Light" : "☾ Dark";
    b.title = dark ? "Switch to light mode" : "Switch to dark mode";
    b.setAttribute("aria-pressed", String(dark));
    b.setAttribute("aria-label", b.title);
  });
}

function toggleColorMode() {
  applyMode(colorMode() === "dark" ? "light" : "dark", true);
}

let modeWired = false;

function initColorMode() {
  applyMode(colorMode(), false);            // label only; no preference written
  // Idempotent: callers may retry this if the launcher failed to initialize, and
  // binding the click twice would toggle twice and appear to do nothing.
  if (modeWired) return;
  modeWired = true;

  document.addEventListener("click", (e) => {
    const chip = e.target.closest && e.target.closest(".mode-chip");
    if (chip) { e.preventDefault(); toggleColorMode(); }
  });
  // Keep following the OS for as long as the user has not chosen for themselves.
  window.matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", (ev) => {
      if (!savedMode()) applyMode(ev.matches ? "dark" : "light", false);
    });
}

/* ---------------------------------------------------------------- theming */

/* The theme is computed server-side by app/theme.py and arrives ready to apply:
   brand roles filled by reusing the agency's own colors, foregrounds chosen for
   contrast, and status colors left alone. Nothing is calculated here, so there
   is one implementation of the rules rather than two that can drift apart.

   Status colors are deliberately absent from what gets overwritten — Low,
   Moderate and High risk are the same in every state. */
const THEMED_ONLY = /^--(chrome|chrome-2|chrome-line|accent|accent-2|highlight|action|on-chrome|on-action|accent-text-light|accent-text-dark|brand-bands|brand-sweep|sidebar|sidebar-2|sidebar-line)$/;

/* The shell's agency labels were static markup, so picking Ohio retuned every
   color and still said SCDES in the header and the breadcrumb. They follow the
   selection now. The corpus is what makes a name authoritative — until one is
   loaded this is the seeded label, which is why it is marked unverified in the
   picker rather than presented as fact. */
/* The identity the shell should be showing, built in one place.

   A state is not an agency. `selectState` handed the raw state entry straight
   to `applyAgencyLabels`, so the header, the breadcrumb and — worst —
   `corpus_loaded` all described South Carolina's default agency no matter which
   agency the person had chosen. Clicking the map was enough to put SCDES's name
   on every screen and unlock SCDES's project register.

   `corpus_loaded` belongs to the one agency that owns the documents, which the
   server names in `loaded_agency`. Everyone else gets false, and the screens
   that read it show their own empty state rather than another agency's
   records. */
function agencyEntryFor(state, chosen) {
  if (!chosen) {
    /* Nothing chosen, so the shell names nothing.

       Previewing a state on the map used to put that state's default agency in
       the header — SCDES, before anyone had picked anything. No records leaked,
       because `corpus_loaded` is false, but the name did: sign out, and the
       shell behind the map still said SCDES. */
    return { ...state, agency_id: "", abbrev: "—", agency: "",
             corpus_loaded: false };
  }
  const owner = LNCH.data && LNCH.data.loaded_agency;
  return {
    ...state,
    agency_id: chosen.id,
    abbrev: chosen.abbrev,
    agency: chosen.name,
    domain: chosen.domain,
    corpus_loaded: !!owner && chosen.id === owner,
  };
}

function applyAgencyLabels(entry) {
  const short = document.getElementById("agencyShort");
  const crumb = document.getElementById("agencyCrumb");
  // The department's own shorthand, exactly as it publishes it: SCDES, TCEQ,
  // Ecology, MoDNR. The full agency name sits below it in the breadcrumb.
  if (short) short.textContent = entry.abbrev;
  if (crumb) crumb.textContent = entry.agency;
  document.title = `${entry.abbrev} — AI Governance`;

  // Tell the application which agency is on screen, so it can refuse to show
  // another agency's records under this one's name.
  window.SCDES_AGENCY = entry;
  document.dispatchEvent(new CustomEvent("agencychange", { detail: entry }));
}

function applyTheme(entry) {
  const root = document.documentElement;
  Object.entries(entry.theme || {}).forEach(([k, v]) => {
    if (THEMED_ONLY.test(k)) root.style.setProperty(k, v);
  });
  root.style.setProperty("--sidebar", entry.theme["--chrome"]);
  root.style.setProperty("--sidebar-2", entry.theme["--chrome-2"]);
  try { localStorage.setItem("scdes.state", entry.code); } catch (e) {}
}

function hexToRgb(h) {
  const n = parseInt(String(h).replace("#", ""), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const clamp = (v) => Math.max(0, Math.min(255, Math.round(v)));
function shade(hex, amt) {
  const [r, g, b] = hexToRgb(hex);
  const f = amt < 0 ? 1 + amt : 1;
  return `rgb(${clamp(r * f)}, ${clamp(g * f)}, ${clamp(b * f)})`;
}
function tint(hex, amt) {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r}, ${g}, ${b}, ${(1 - amt).toFixed(2)})`;
}

const escHtml = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ------------------------------------------------------------- the flag */

/* Official colors, from the specification the flag is actually made to:
   Old Glory Red and Old Glory Blue (Pantone 193 C and 281 C). The previous
   values were the application's own alert red and a guessed navy, which is part
   of why the map read as dull — it wasn't quite the flag. */
const FLAG_RED = "#b31942";
const FLAG_BLUE = "#0a3161";
const FLAG_WHITE = "#ffffff";

/** A five-pointed star. Inner radius is the pentagram ratio, so the points are
    the proportions of a real star rather than a rounded blob. */
function starPath(cx, cy, outer) {
  const inner = outer * 0.38197;          // 1/φ² — the pentagram constant
  let d = "";
  for (let i = 0; i < 10; i++) {
    const r = i % 2 ? inner : outer;
    const a = (-90 + i * 36) * Math.PI / 180;
    d += (i ? "L" : "M") + (cx + r * Math.cos(a)).toFixed(2) +
         "," + (cy + r * Math.sin(a)).toFixed(2);
  }
  return d + "Z";
}

/* The oceans, the compass, and the tint each state carries.

   Modeled on a reference the client supplied: a printed push-pin travel map on
   parchment, states in muted earth tones, oceans named in small caps, a compass
   in the top right.

   Worth stating the tension. The instruction before this was "just a base map
   of a single, neutral color", and this is not one color. It is still neutral
   in the sense that matters — nothing here is a brand, a flag, or any agency's
   identity — and the reason for the original instruction survives intact: a
   selected agency's palette is saturated, everything under it is not, so the
   one colored thing on screen is still the agency you picked. Against flat
   slate that contrast was there; against these it is stronger, because the
   ground is warmer and further from any agency's colors than a blue-gray was.

   The tints are assigned from the state's own code, so they are stable between
   visits — a map whose colors shuffle on reload reads as broken. Seven of
   them, which is enough that neighbors rarely match and few enough that the
   whole thing still reads as one palette. Where two neighbors do land on the
   same tint the outline carries the border, which is what outlines are for. */
const TINTS = 7;

function tintOf(code) {
  // A small deterministic hash. Not random: the same state gets the same tint
  // on every machine and every reload.
  let n = 0;
  for (const ch of String(code)) n = (n * 31 + ch.charCodeAt(0)) % 9973;
  return n % TINTS;
}

function oceanLabels() {
  const label = (x, y, lines, cls = "sea") => lines.map((line, i) =>
    `<text class="${cls}" x="${x}" y="${y + i * 19}"
       text-anchor="middle">${line}</text>`).join("");
  return `
    <g class="seas" aria-hidden="true">
      ${label(63, 356, ["PACIFIC", "OCEAN"])}
      ${label(902, 372, ["ATLANTIC", "OCEAN"])}
      ${label(586, 512, ["Gulf of", "Mexico"], "sea sea-minor")}
    </g>`;
}

/* A compass rose, in the corner the reference puts one. Decoration, and it
   earns its place: it fills the emptiest part of the canvas and it tells you
   the thing off the east coast is deliberate rather than stray. */
function compassRose() {
  const cx = 904, cy = 158, r = 26;
  const spoke = (angle, length, wide) => {
    const a = (angle - 90) * Math.PI / 180;
    const p = (t, w) => `${cx + t * Math.cos(a) - w * Math.sin(a)},`
                      + `${cy + t * Math.sin(a) + w * Math.cos(a)}`;
    return `<path d="M${p(length, 0)} L${p(0, wide)} L${p(0, -wide)} Z"/>`;
  };
  return `
    <g class="compass" aria-hidden="true">
      <circle cx="${cx}" cy="${cy}" r="${r}" class="compass-ring"/>
      <circle cx="${cx}" cy="${cy}" r="${r - 7}" class="compass-ring faint"/>
      <g class="compass-minor">
        ${[45, 135, 225, 315].map((a) => spoke(a, r - 9, 2.6)).join("")}
      </g>
      <g class="compass-major">
        ${[0, 90, 180, 270].map((a) => spoke(a, r - 2, 3.6)).join("")}
      </g>
      <text class="compass-n" x="${cx}" y="${cy - r - 5}"
            text-anchor="middle">N</text>
    </g>`;
}

/* The way in for federal agencies.

   Asked for exactly: "Make the map of the US just a base map of a single,
   neutral color, then coming out of the DC area should be a line to a USA flag
   to the side which says 'Federal Login'."

   The line starts at the District — the real path in the map data, around
   x=748 y=209 — and runs out over the Atlantic, which is the only part of the
   canvas with nothing in it. Maine occupies the top right and Florida the
   bottom right, so the flag sits between them at the latitude it leaves from,
   and the line stays short enough to read as a leader rather than a border. */
const DC_AT = { x: 749.5, y: 209.5 };
const FED_FLAG = { x: 852, y: 236, w: 92, h: 58 };

function federalLink() {
  const f = FED_FLAG;
  const midX = (DC_AT.x + f.x) / 2;
  // 13 stripes over the flag's own box, canton across the top-left quadrant,
  // drawn small rather than detailed: at 92px wide a field of fifty stars is
  // gray mush, so the canton carries nine suggested stars instead.
  const stripe = f.h / 13;
  let stripes = "";
  for (let i = 0; i < 13; i++) {
    stripes += `<rect x="${f.x}" y="${(f.y + i * stripe).toFixed(2)}" ` +
      `width="${f.w}" height="${(stripe + 0.4).toFixed(2)}" ` +
      `fill="${i % 2 ? FLAG_WHITE : FLAG_RED}"/>`;
  }
  const cantonW = f.w * 0.4, cantonH = stripe * 7;
  let stars = "";
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) {
      stars += `<path d="${starPath(
        f.x + cantonW * (0.22 + c * 0.28),
        f.y + cantonH * (0.24 + r * 0.26), 2.6)}" fill="${FLAG_WHITE}"/>`;
    }
  }

  return `
    <g class="fedlink" id="fedLink" role="button" tabindex="0"
       aria-label="Federal Login — 334 federal agencies">
      <title>Federal Login</title>
      <path class="fedlink-line"
            d="M${DC_AT.x},${DC_AT.y} Q${midX},${DC_AT.y - 26} ${f.x},${f.y + f.h / 2}"/>
      <circle class="fedlink-dot" cx="${DC_AT.x}" cy="${DC_AT.y}" r="3.4"/>
      <g class="fedlink-flag">
        ${stripes}
        <rect x="${f.x}" y="${f.y}" width="${cantonW}" height="${cantonH}"
              fill="${FLAG_BLUE}"/>
        ${stars}
        <rect x="${f.x}" y="${f.y}" width="${f.w}" height="${f.h}"
              fill="none" class="fedlink-edge"/>
      </g>
      <text class="fedlink-label" x="${f.x + f.w / 2}" y="${f.y + f.h + 17}"
            text-anchor="middle">Federal Login</text>
    </g>`;
}

function flagLayer() {
  // 13 stripes across the whole canvas, canton over the north-west quadrant.
  const H = 600, W = 960, stripe = H / 13;
  let out = "";
  for (let i = 0; i < 13; i++) {
    out += `<rect x="0" y="${(i * stripe).toFixed(1)}" width="${W}" ` +
           `height="${(stripe + 0.5).toFixed(1)}" ` +
           `fill="${i % 2 ? FLAG_WHITE : FLAG_RED}"/>`;
  }
  // Canton: two fifths of the length, seven stripes deep — the real proportion.
  const cw = W * 0.40, ch = stripe * 7;
  out += `<rect x="0" y="0" width="${cw.toFixed(1)}" height="${ch.toFixed(1)}" ` +
         `fill="${FLAG_BLUE}"/>`;

  // The union as it is actually laid out: 9 rows alternating 6 and 5 stars,
  // on an 11-column grid, which is what makes the offset rows line up.
  const hSpace = cw / 12, vSpace = ch / 10;
  const radius = vSpace * 0.46;
  for (let row = 0; row < 9; row++) {
    const count = row % 2 === 0 ? 6 : 5;
    const y = vSpace * (row + 1);
    for (let col = 0; col < count; col++) {
      const x = hSpace * (row % 2 === 0 ? 2 * col + 1 : 2 * col + 2);
      out += `<path d="${starPath(x, y, radius)}" fill="${FLAG_WHITE}"/>`;
    }
  }
  return out;
}

/* ------------------------------------------------------- the state flag */

/* The selected state's own flag, shown over the map beside it.

   The artwork is real: US state flags rendered by Wikimedia Commons and
   bundled by tools/fetch_flags.py, so this works with no network. Fifty are
   public domain; Mississippi's 2020 design is copyrighted with free use
   granted, which the manifest records separately.

   Anchored to the state's own bounding box so the flag appears next to the
   thing you clicked, and clamped inside the map so Florida and Maine do not
   push it off the edge. */
/** Place the pop-up beside `shape`, clamped inside the map. */
function positionFlag(pop, wrap, shape) {
  const box = shape.getBoundingClientRect();
  const area = wrap.getBoundingClientRect();
  // Fall back to the element's own CSS size rather than bailing out. Returning
  // early here left `left`/`top` unset, which drops the pop-up at its static
  // position — an invisible failure that looks identical to "nothing happened".
  const w = pop.offsetWidth || 144, h = pop.offsetHeight || 96;

  // Prefer above the state; drop below when it would leave the map.
  let top = box.top - area.top - h - 12;
  if (top < 4) top = box.top - area.top + box.height + 12;
  let left = box.left + box.width / 2 - area.left - w / 2;
  left = Math.max(4, Math.min(left, area.width - w - 4));
  top = Math.max(4, Math.min(top, area.height - h - 4));

  pop.style.left = `${left}px`;
  pop.style.top = `${top}px`;
}

function showFlag(code, entry) {
  const pop = document.getElementById("flagPop");
  const wrap = document.getElementById("mapWrap");
  const shape = document.querySelector(`.st[data-code="${code}"]`);
  // Say which piece is missing instead of returning in silence — three separate
  // causes previously presented as the same nothing.
  if (!pop || !wrap || !shape) {
    console.warn("[launcher] cannot show flag for", code,
                 { pop: !!pop, wrap: !!wrap, shape: !!shape });
    return;
  }
  pop.dataset.state = code;

  pop.innerHTML =
    `<img src="/assets/flags/${encodeURIComponent(code)}.png" alt="Flag of ${
      escHtml(entry.state)}">` +
    `<figcaption>${escHtml(entry.state)}</figcaption>`;
  pop.hidden = false;

  const img = pop.querySelector("img");
  /* A failed image used to hide the whole pop-up. That was the wrong call: it
     turned a missing file into "the feature does nothing", which is
     indistinguishable from a bug and impossible to report usefully. Keep the
     caption, mark it, and say so in the console. */
  img.onerror = () => {
    pop.classList.add("noimg");
    console.warn("[launcher] flag image failed to load:", img.getAttribute("src"));
  };

  /* Position twice, and the second time is the one that matters.

     Measuring straight away gives the height of a caption and no picture,
     because the image has not loaded yet. The pop-up was then clamped against
     the wrong height, which put it low enough to be cut off by the launcher's
     overflow — visible on some selections, missing on others, depending on
     whether that flag happened to be in the browser cache. So: place it now so
     it never appears at 0,0, and place it again once the real height is known.

     `loading="lazy"` is deliberately absent — a lazily-loaded image reports no
     size until it decides to fetch, which is exactly the race above. */
  positionFlag(pop, wrap, shape);
  if (img.complete && img.naturalWidth) positionFlag(pop, wrap, shape);
  else img.onload = () => positionFlag(pop, wrap, shape);

  // Restart the entrance animation on every selection, so re-picking a state
  // reads as the flag arriving rather than nothing happening.
  pop.classList.remove("in");
  void pop.offsetWidth;                      // force reflow so the class re-applies
  pop.classList.add("in");
}

/* A state is not one governmental unit. Once a state is picked, the person says
   which agency they belong to — environmental services and education each run
   their own governance and use their own email convention, so the choice decides
   which rules the registration is checked against. */
function agencyPicker(s) {
  if (!s.open_for_registration) {
    return `<span class="lnch-closed">Not open for registration yet. ` +
           `${escHtml(s.state)} opens once its agencies and their email ` +
           `conventions have been confirmed.</span>`;
  }
  const list = s.agencies || [];
  if (!list.length) {
    return `<span class="lnch-closed">No agencies recorded for ` +
           `${escHtml(s.state)} yet.</span>`;
  }
  // A native <select> was fine for three agencies and is unusable for 149:
  // no typing, no filtering, and a list that runs off the screen. This is a
  // combobox — an input you type into, with a filtered list under it.
  return `
    <label class="lnch-agency" for="agencyPick">
      <span>Select your agency</span>
    </label>
    <div class="combo" id="agencyCombo">
      <input id="agencyPick" type="text" role="combobox" autocomplete="off"
             spellcheck="false" aria-expanded="false" aria-controls="agencyList"
             aria-autocomplete="list" aria-label="Search agencies"
             placeholder="Type to search ${list.length} agencies…">
      <button type="button" class="combo-clear" id="agencyClear" hidden
              aria-label="Clear">×</button>
      <ul class="combo-list" id="agencyList" role="listbox" hidden></ul>
    </div>
    <span class="lnch-agency-hint" id="agencyHint">
      Your work email must be on that agency's domain.</span>`;
}

/* Matching, in the order people actually type.

   Someone reaching for the Department of Environmental Services types "SCDES",
   or "DES", or "environmental" — rarely "South Carolina Department of…", which
   is how every entry in this list begins. So the shared prefix is stripped
   before matching, abbreviations are ranked above names, and a match anywhere
   still counts. Ranking matters more than filtering here: "DES" matches eleven
   agencies, and SCDES has to be the first of them. */
function agencyMatches(list, query) {
  const q = query.trim().toLowerCase();
  if (!q) return list.map((a) => ({ a, score: 0 }));

  const scored = [];
  for (const a of list) {
    const abbrev = (a.abbrev || "").toLowerCase();
    // Every SC agency name starts the same way; matching on it is noise.
    const name = (a.name || "").toLowerCase().replace(/^south carolina /, "");
    const domain = (a.domain || "").toLowerCase();

    let score = -1;
    if (abbrev === q) score = 100;
    else if (abbrev.startsWith(q)) score = 90;
    else if (name.startsWith(q)) score = 80;
    // A word start inside the name — "environmental" finding "Department of
    // Environmental Services".
    else if (new RegExp("\\b" + q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).test(name))
      score = 70;
    // Above a name substring, not below it. Someone typing three letters is
    // almost always typing an acronym — and "DES" was finding Building Codes
    // Council, on the "des" inside "Codes", ahead of SCDES.
    else if (abbrev.includes(q)) score = 55;
    else if (name.includes(q)) score = 45;
    else if (domain.includes(q)) score = 30;
    if (score >= 0) scored.push({ a, score: score + agencyWeight(a) });
  }
  scored.sort((x, y) => y.score - x.score ||
                        x.a.name.localeCompare(y.a.name));
  return scored;
}

/* A department outranks a licensing board.

   Thirty-seven of the 149 are small professional boards, and their names
   collide constantly with the departments people are actually looking for:
   "environmental" found the Environmental Certification Board before the
   Department of Environmental Services, and "education" found the Education
   Lottery Commission before the Department of Education. Both were correct by
   string-matching and useless in practice.

   Read off the category the client's own spreadsheet supplies, so this is their
   classification rather than a judgment invented here. */
function agencyWeight(a) {
  const c = (a.category || "").toLowerCase();
  if (c.includes("cabinet") || c.includes("elected constitutional")) return 20;
  if (c.includes("professional board")) return -10;
  return 0;
}

/* The note describes the agency about to be entered, not the state.
   A state holds several governmental units and only one of them has a corpus
   loaded, so a state-level sentence was claiming things about agencies it did
   not apply to. */
function agencyNote(state, chosen) {
  if (!chosen) {
    return `${state.state} has ${(state.agencies || []).length} governmental `
      + `unit(s) available. Choose yours — each one governs its own AI `
      + `separately, with its own rules and its own people.`;
  }
  const loaded = state.corpus_loaded && chosen.abbrev === state.abbrev;
  if (loaded) {
    return `${chosen.name} is confirmed by its own adopted documents, which are `
      + `loaded. The instruments, lifecycle and vocabulary on every screen are `
      + `read from that corpus rather than built in.`;
  }
  return `No documents have been loaded for ${chosen.name} yet. You will build `
    + `its framework here, and everything downstream is then read from what you `
    + `write — not from any other agency's.`;
}

/* Everything below the picker follows the *chosen agency*, not the state's
   default one. The button previously read "Enter SCDES" while a different
   agency was selected — a label naming a different organization from the one
   you are about to enter erodes trust in everything else on the screen.

   One function applies a choice, whatever made it: a click, Enter, or the
   restore on reopening. */
function applyAgencyChoice(s, chosen) {
  LNCH.agency = chosen ? chosen.id : "";
  const other = !!(chosen && chosen.other);

  const hint = document.getElementById("agencyHint");
  if (hint) {
    hint.textContent = other
      ? "Any work email. You will name your organization on the next screen."
      : chosen
      ? `Your work email must end in @${chosen.domain}`
      : "Your work email must be on that agency's domain.";
  }
  const go = document.getElementById("lnchEnter");
  if (go) {
    go.disabled = !chosen;
    go.textContent = other ? "Continue as Other"
      : chosen ? `Enter ${chosen.abbrev}` : "Select an agency";
  }
  // Names the agency being entered, and only claims a corpus is loaded when one
  // actually is — true for one agency, not for the whole state.
  const note = document.getElementById("lnchNote");
  if (note) {
    note.textContent = other
      ? `Your organization is not on the ${s.state} list. You will name it on `
        + `the next screen, and it gets its own framework, separate from every `
        + `other organization.`
      : agencyNote(s, chosen);
  }
  const clear = document.getElementById("agencyClear");
  if (clear) clear.hidden = !chosen;
  // The shell behind the launcher follows the choice as it is made, so it is
  // never showing one agency's name under another's selection.
  applyAgencyLabels(agencyEntryFor(s, other ? null : chosen));
}

/* "Other" — the last row of every state's list, for an organization that is
   not on it. The same way in as "Create your framework anyway" under the
   button, put where people actually look: in the list they are scrolling.
   Its id is per state and never sent anywhere — enterUnlisted() clears it. */
function otherEntry(s) {
  return { id: `other.${s.code}`, other: true, abbrev: "Other",
           name: "My organization is not listed", domain: "" };
}

function wireAgencyPicker(s) {
  const input = document.getElementById("agencyPick");
  const listBox = document.getElementById("agencyList");
  if (!input || !listBox) return;

  const all = s.agencies || [];
  const other = otherEntry(s);
  let shown = [];
  let active = -1;

  const selected = () => (LNCH.agency === other.id ? other
    : all.find((a) => a.id === LNCH.agency) || null);

  const close = () => {
    listBox.hidden = true;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
    active = -1;
  };

  const paint = () => {
    // "Other" is always the last row, so a search that finds nothing still
    // leaves a way in rather than a dead end.
    const none = shown.length === 1
      ? `<li class="combo-none">No agency matches that. Try the short name,
           or part of the department — or choose Other.</li>` : "";
    listBox.innerHTML = none + shown.map(({ a }, i) => `
          <li id="ag-${i}" role="option" data-id="${escHtml(a.id)}"
              aria-selected="${a.id === LNCH.agency}"
              class="${[i === active ? "on" : "", a.other ? "combo-other" : ""].join(" ").trim()}">
            <b>${escHtml(a.abbrev)}</b>
            <span>${escHtml(a.name.replace(/^South Carolina /, ""))}</span>
            ${a.test_only ? `<em>demo</em>` : ""}
          </li>`).join("");
    if (active >= 0) {
      input.setAttribute("aria-activedescendant", `ag-${active}`);
      const node = document.getElementById(`ag-${active}`);
      if (node && node.scrollIntoView) node.scrollIntoView({ block: "nearest" });
    }
  };

  const open = (query) => {
    // Every match, always. An earlier version capped this at fifty rows on a
    // performance argument that does not survive being checked: 149 list items
    // is nothing for a browser, and the cap meant someone scrolling for their
    // agency could reach the bottom without it being there. A picker that
    // silently stops short is worse than a slightly longer list.
    shown = [...agencyMatches(all, query), { a: other, score: -1 }];
    listBox.hidden = false;
    input.setAttribute("aria-expanded", "true");
    active = shown.length ? 0 : -1;
    paint();
    placeList();
  };

  /* Open upward when there is no room below.

     The agency panel sits at the bottom of the launcher, so a list anchored
     under the input ran straight off the screen — you could not see a single
     agency without scrolling the page, which is not obvious when the thing you
     are trying to scroll is a dropdown.

     Measured per open rather than fixed: the panel moves with the viewport, and
     a list hardcoded to open upward would run off the top on a short window. */
  function placeList() {
    const box = input.getBoundingClientRect();
    const below = window.innerHeight - box.bottom - 16;
    const above = box.top - 16;
    const wanted = Math.min(264, (shown.length || 1) * 34 + 12);

    const up = below < wanted && above > below;
    listBox.classList.toggle("up", up);
    // Never taller than the space it actually has. Capping here rather than in
    // CSS keeps the last row reachable on a laptop instead of clipped by the
    // window edge.
    listBox.style.maxHeight =
      Math.max(120, Math.min(264, up ? above : below)) + "px";
  }

  const choose = (entry) => {
    applyAgencyChoice(s, entry);
    input.value = entry ? entry.name : "";
    close();
  };

  input.addEventListener("input", () => open(input.value));
  input.addEventListener("focus", () => open(""));
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (listBox.hidden) return open(input.value);
      if (!shown.length) return;
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + shown.length)
               % shown.length;
      paint();
    } else if (e.key === "Enter") {
      if (e.isComposing) return;
      const cur = selected();
      const settled = cur && input.value.trim() === cur.name;
      if (!listBox.hidden && shown[active] && !settled) {
        // Still picking: Enter takes the highlighted agency.
        e.preventDefault(); choose(shown[active].a);
      } else if (settled) {
        // An agency is chosen and showing: Enter goes in, exactly as the
        // "Enter …" button beside it does.
        e.preventDefault(); close();
        const go = document.getElementById("lnchEnter");
        if (go && !go.disabled && !go.hidden) go.click();
      }
    } else if (e.key === "Escape") {
      // Back to whatever was already chosen, rather than leaving half-typed
      // text sitting under a button that says "Enter SCDES".
      const cur = selected();
      input.value = cur ? cur.name : "";
      close();
    }
  });

  listBox.addEventListener("mousedown", (e) => {
    const li = e.target.closest("li[data-id]");
    if (!li) return;
    e.preventDefault();                    // beat the blur
    const hit = li.dataset.id === other.id ? other
      : all.find((a) => a.id === li.dataset.id);
    if (hit) choose(hit);
  });

  input.addEventListener("blur", () => {
    // Typed text that matches nothing is not a selection. Snap back so the
    // input never disagrees with the button underneath it.
    setTimeout(() => {
      const cur = selected();
      input.value = cur ? cur.name : "";
      close();
    }, 120);
  });

  window.addEventListener("resize", () => {
    if (!listBox.hidden) placeList();
  });

  const clear = document.getElementById("agencyClear");
  if (clear) clear.onclick = () => { choose(null); input.focus(); };

  const cur = selected();
  input.value = cur ? cur.name : "";
  applyAgencyChoice(s, cur);
}

/** Re-show the flag for whatever is selected — after reopening or a resize. */
function refreshFlag() {
  const code = LNCH.active;
  if (!code || !LNCH.data) return;
  const entry = LNCH.data.states.find((s) => s.code === code);
  if (entry) showFlag(code, entry);
}

/* --------------------------------------------------------------- render */

function buildLauncher() {
  const host = document.getElementById("launcher");
  const d = LNCH.data, map = LNCH.map;
  const byCode = Object.fromEntries(d.states.map((s) => [s.code, s]));

  const codes = Object.keys(map.states);
  const clip = codes.map((c) => `<path d="${map.states[c].d}"/>`).join("");
  /* Only states open for registration are selectable. The rest are drawn — so
     the reach is visible — but greyed and not focusable, because letting someone
     start a registration the platform cannot honor is worse than showing them
     it is not their turn yet. A state opens once its agencies and their email
     conventions have actually been confirmed. */
  const shapes = codes.map((c) => {
    const s = byCode[c];
    const open = s && s.open_for_registration;
    const title = !s ? (map.states[c].name || c)
      : open ? `${s.state} — ${(s.agencies || []).length} agenc${
                 (s.agencies || []).length === 1 ? "y" : "ies"} available`
             : `${s.state} — not open yet`;
    return `<path class="st tint-${tintOf(c)}${open ? "" : " st-closed"}` +
           `${s && s.corpus_loaded ? " has-corpus" : ""}" ` +
           `data-code="${c}" d="${map.states[c].d}" ` +
           (open ? `tabindex="0" role="button" ` : `aria-disabled="true" `) +
           `aria-label="${escHtml(title)}"><title>${escHtml(title)}</title></path>`;
  }).join("");

  host.innerHTML = `
    <div class="lnch-inner">
      <header class="lnch-head">
        <p class="lnch-eyebrow">AI Governance · operating the framework</p>
        <h1>Choose an agency</h1>
        <p>One application, pointed at any state's adopted corpus.
           <span class="keys">Click a state to preview it ·
           <kbd>double-click</kbd> or <kbd>Enter</kbd> to open it</span></p>
      </header>

      <div class="mapwrap" id="mapWrap">
        <figure class="flagpop" id="flagPop" hidden></figure>
        <svg class="usmap" viewBox="${map.viewBox}" role="group"
             aria-label="Map of the United States — select a state">
          <defs>
            <clipPath id="usClip">${clip}</clipPath>
            <!-- The selected state is filled with a sweep through the agency's
                 own colors rather than one flat fill. Stop count follows the
                 agency, so two colors give two stops. Set in selectState(). -->
            <linearGradient id="agencyFill" x1="0" y1="0" x2="1" y2="1"></linearGradient>
            <!-- A light raking across the flag and a shadow gathering bottom
                 right. Flat color reads as a printed chart; a little modeling
                 reads as cloth. -->
            <!-- Was modeling for cloth, when the country was the flag. Softened
                 to a paper vignette: enough to lift the landmass off the page,
                 not enough to look like fabric. -->
            <linearGradient id="flagSheen" x1="0.1" y1="0" x2="0.85" y2="1">
              <stop offset="0%"   stop-color="#ffffff" stop-opacity="0.14"/>
              <stop offset="45%"  stop-color="#ffffff" stop-opacity="0.02"/>
              <stop offset="100%" stop-color="#2a2013" stop-opacity="0.10"/>
            </linearGradient>
            <filter id="mapShadow" x="-12%" y="-12%" width="126%" height="126%">
              <feDropShadow dx="0" dy="7" stdDeviation="11"
                            flood-color="#000814" flood-opacity="0.5"/>
            </filter>
          </defs>

          <!-- One neutral color, at the client's instruction: "Make the map of
               the US just a base map of a single, neutral color." The flag used
               to be clipped to the country outline so the map *was* the flag.
               It looked good and it competed with the thing the map is for —
               every state read as already colored, so a selected state was a
               change of hue rather than the only color on screen. The flag has
               moved to where it now means something: the federal entry. -->
          <g filter="url(#mapShadow)">
            <g clip-path="url(#usClip)">
              <rect x="0" y="0" width="960" height="600" class="mapbase"/>
              <rect x="0" y="0" width="960" height="600" fill="url(#flagSheen)"/>
            </g>
          </g>
          ${oceanLabels()}
          <g class="states">${shapes}</g>
          ${compassRose()}
          ${federalLink()}
          <!-- The national outline last, so the country reads as one shape and
               state borders do not fray at the coast. -->
          <g class="outline" aria-hidden="true">${
            codes.map((c) => `<path d="${map.states[c].d}"/>`).join("")}</g>
        </svg>
      </div>

      <div class="lnch-pick" id="lnchPick"></div>
      <p class="lnch-note" id="lnchNote"></p>
    </div>
    <div class="signin" id="signinPanel" hidden></div>`;

  /* The federal flag behaves like a state, because behind it everything is a
     state: the picker, the theme and the sign-in card all key off a code, and
     `FED` is one. Click previews, double-click and Enter go in — the same three
     gestures the map already teaches. */
  const fed = host.querySelector("#fedLink");
  if (fed) {
    fed.addEventListener("click", () => selectState("FED"));
    fed.addEventListener("dblclick", (e) => {
      e.preventDefault();
      enterAgency("FED");
    });
    fed.addEventListener("keydown", (e) => {
      if (e.key === " " || e.key === "Spacebar") {
        e.preventDefault();
        selectState("FED");
      } else if (e.key === "Enter") {
        e.preventDefault();
        enterAgency("FED");
      }
    });
    fed.addEventListener("focus", () => {
      if (LNCH.active !== "FED") selectState("FED", false);
    });
  }

  host.querySelectorAll(".st:not(.st-closed)").forEach((p) => {
    p.addEventListener("click", () => selectState(p.dataset.code));

    // Double-click opens the agency and closes the map — the same thing Enter
    // does, and what double-click means everywhere else. Without it the only
    // ways in were the keyboard or the button below the map, so double-clicking
    // a state looked like a dead control.
    p.addEventListener("dblclick", (e) => {
      e.preventDefault();
      enterAgency(p.dataset.code);
    });

    // Tabbing to a state previews it, so moving through the map shows each
    // agency's theme as you arrive rather than requiring a second keystroke.
    p.addEventListener("focus", () => {
      if (LNCH.active !== p.dataset.code) selectState(p.dataset.code, false);
    });

    p.addEventListener("keydown", (e) => {
      if (e.key === " " || e.key === "Spacebar") {
        // Space previews — the same thing a click does, and stops the page
        // scrolling, which is Space's default on a focused element.
        e.preventDefault();
        selectState(p.dataset.code);
      } else if (e.key === "Enter") {
        // Enter commits: take this agency and move on to signing in.
        e.preventDefault();
        enterAgency(p.dataset.code);
      }
    });
  });

  selectState(d.loaded || "SC", false);
}

function selectState(code, announce = true) {
  const d = LNCH.data;
  const s = d.states.find((x) => x.code === code);
  if (!s) return;
  LNCH.active = code;

  // Fill the selected state with a sweep through the agency's own colors. The
  // stop count follows the agency: two colors give two stops, not two real and
  // two invented.
  const grad = document.getElementById("agencyFill");
  if (grad) {
    const picks = s.colors.slice(0, 5);
    const step = 100 / Math.max(picks.length - 1, 1);
    grad.innerHTML = picks.map((c, i) =>
      `<stop offset="${(i * step).toFixed(1)}%" stop-color="${c}"/>`).join("");
  }

  document.querySelectorAll(".st").forEach((p) => {
    const on = p.dataset.code === code;
    p.classList.toggle("active", on);
    p.style.fill = on ? "url(#agencyFill)" : "";
  });
  // Federal is not a path on the map, so it carries the selected state itself.
  const fedLink = document.getElementById("fedLink");
  if (fedLink) fedLink.classList.toggle("active", code === "FED");
  applyTheme(s);
  // Preview only: until an agency is chosen this claims nothing about whose
  // records these are. See agencyEntryFor().
  applyAgencyLabels(agencyEntryFor(
    s, (s.agencies || []).find((a) => a.id === LNCH.agency)));
  // Federal has no path on the map to anchor a pop-up to, and no state flag to
  // show — the flag it would show is the one already drawn beside the coast.
  if (code === "FED") {
    const pop = document.getElementById("flagPop");
    if (pop) pop.hidden = true;
  } else {
    showFlag(code, s);
  }

  // The note was a fixed paragraph, so it read as boilerplate and said the same
  // thing whichever state you were on. It now names the agency in front of you,
  // which is the only way the "this name is unverified" caveat lands.
  const note = document.getElementById("lnchNote");
  if (note) note.textContent = agencyNote(s, null);

  // The swatches show the theme, nothing more. Where the colors came from and
  // how many there are is not surfaced in the interface at all — no badge, no
  // paragraph, no tooltip. It remains on the API response (`provenance`,
  // `palette_source`, `brand_count`, `caveat`) and in the README for anyone
  // auditing the build.
  const swatches = s.colors.map((c) =>
    `<i style="background:${c}"></i>`).join("");

  document.getElementById("lnchPick").innerHTML = `
    <div class="who">
      <small>${escHtml(s.state)}</small>
      <div class="who-line">
        <b>${escHtml(s.state)}</b>
        <button class="mode-chip" type="button" aria-pressed="false"></button>
      </div>
      ${agencyPicker(s)}
      <div class="lnch-swatches">${swatches}</div>
    </div>
    <div class="lnch-actions">
      <button class="btn" id="lnchEnter" disabled>Select an agency</button>
    </div>
    <!-- The door for everybody not on the list: counties, towns, special
         districts, school boards. Always present once a state is chosen, and
         worded as an invitation rather than an error, because not being on
         the list is the ordinary case for most governmental units. -->
    <div class="lnch-unlisted">
      ${(() => { try { return localStorage.getItem("scdes.portal") === "other"; } catch (e) { return false; } })()
        ? `<p class="small" style="margin:0 0 6px">You chose <b>Other public body</b>, so this is
            your way in — the agencies listed above each need their own email domain.</p>` : ""}
      <button class="linkish" id="lnchUnlisted" type="button">Don't see your
        governmental unit? <b>Create your framework anyway</b></button>
    </div>`;

  // The panel is rebuilt on every selection, so its toggle needs relabelling.
  applyMode(colorMode(), false);

  // Remember the agency and tell the reader which domain it expects, so the
  // email rule is visible before they hit it rather than after.
  /* Everything below the dropdown follows the *chosen agency*, not the state's
     default one. The button previously read "Enter SCDES" while TEST agency was
     selected — the label naming a different organization from the one you are
     about to enter is the kind of thing that erodes trust in everything else on
     the screen. */
  wireAgencyPicker(s);

  document.getElementById("lnchEnter").onclick = () => enterAgency(code);
  document.getElementById("lnchUnlisted").onclick = () => enterUnlisted(code);

  /* There was a "No corpus — what does that mean?" button here, and an alert
     behind it explaining that the agency name was "a seed from public
     knowledge, not a verified fact" and that operating the state for real
     meant dropping documents "into corpus/".

     Removed on the client's instruction, and it should never have been on
     this screen. Three things were wrong with it. It spoke to a developer:
     "corpus" is a directory on our server, not a word anybody registering an
     agency has reason to know. It cast doubt on the agency's own name at the
     moment somebody was selecting their own employer from a list. And it
     announced a missing thing that is not required for anything they are
     about to do — a loaded corpus matters to the paid modules that read an
     agency's existing documents, and the framework builder reads nothing but
     the answers they give it.

     What a reader needs here is already said properly by `agencyNote`: "No
     documents have been loaded for X yet. You will build its framework here,
     and everything downstream is then read from what you write — not from
     any other agency's." That is the same fact without the jargon or the
     doubt, so nothing was lost by deleting this.

     `corpus_loaded` itself stays. The theme, the agency resolution and the
     admin view all use it; it simply is not narrated at the door. */

  if (announce && window.toast) window.toast(`${s.abbrev} theme applied.`);
}

/* ---------------------------------------------------------------- sign in */

/* Choosing an agency and choosing who you are are two different acts, and the
   second one matters: every governed action is recorded against the actor, and
   what you are allowed to do — tune a parameter, approve a gate — follows from
   their role. Making that a deliberate step rather than a dropdown in the
   corner puts the identity on the record at the moment you enter.

   What this is NOT is authentication. It identifies you against the agency's
   local roster and takes your word for it. There is no password, no session,
   no verification, and the panel says so rather than implying otherwise — a
   sign-in screen that looks like security but isn't is worse than none, most
   of all in an application whose output is meant to stand up as a record. */

/* ------------------------------------------------- registration and access

   Choosing an agency is not the same as being allowed into it. What happens
   after the agency dropdown depends entirely on the state of that agency's
   container, so this asks the server rather than guessing:

     unregistered      → register: name, title, work email, phone, attestation
     pending_code      → enter the code sent to that address
     pending_approval  → wait; a named reviewer confirms delegated authority
     active + member   → in
     active + stranger → refused, and told who to ask

   `pending_approval` only happens when the deployment has IIA_REVIEW_REQUIRED
   set. The client turned the queue off — "if they register and verify, that's
   enough for today" — so on a default deployment verification goes straight to
   active. The copy on these screens is worded from `review_required`, not
   restated here, because for a while it promised a reviewer who was never
   coming.

   Nothing is pre-filled. Every governed action is recorded against the name
   entered here, so it has to be the person's own. */

/** Whether this deployment queues a first registrant for human review. */
function reviewRequired() {
  return !!(LNCH.data && LNCH.data.review_required);
}

async function agencyAccess(email) {
  if (!email) return { allowed: false, status: "unregistered" };
  try {
    return await fetch("/api/agency/access?email=" + encodeURIComponent(email))
      .then((r) => r.json());
  } catch (e) { return { allowed: false, status: "unregistered" }; }
}

function storedRegistration() {
  try { return JSON.parse(localStorage.getItem("scdes.registration") || "{}") || {}; }
  catch (e) { return {}; }
}

function rememberRegistration(patch) {
  const next = { ...storedRegistration(), ...patch };
  try { localStorage.setItem("scdes.registration", JSON.stringify(next)); }
  catch (e) {}
  return next;
}

/* Kept apart from the registration rather than folded into it, because it is a
   credential and the registration is a description. They have different rules:
   the registration can be re-read and re-shown, this one is written once, sent
   on every request and destroyed on sign-out. */
function rememberSession(token) {
  if (!token) return;
  try { localStorage.setItem("scdes.session", token); } catch (e) {}
}

function signinShell(entry, inner) {
  const panel = document.getElementById("signinPanel");
  const outer = document.querySelector(".lnch-inner");
  panel.innerHTML = `
    <div class="signin-card" role="dialog" aria-modal="true"
         aria-labelledby="signinTitle">
      <p class="signin-eyebrow">${escHtml(entry.state)}</p>
      <h2 id="signinTitle">${escHtml(LNCH.agencyName || entry.agency)}</h2>
      ${inner}
    </div>`;
  if (outer) outer.hidden = true;
  panel.hidden = false;
}

/** Decide which of the five screens to show, from the server's answer. */
async function showSignin(entry) {
  const saved = storedRegistration();
  const access = await agencyAccess(saved.email);

  // saved.email, not a bare `email` — there is no such variable in this scope,
  // and the ReferenceError it threw killed the click silently. Pressing "Enter
  // DEMO" simply did nothing.
  if (access.allowed) return showNda(entry, saved.email, access);
  if (access.status === "pending_approval") return showWaiting(entry, saved, access);
  if (access.status === "pending_code") return showVerify(entry, saved.email);
  return showRegister(entry, saved);
}

/* ------------------------------------------------------------ 1. register */

/* Enter in a text field presses the form's main button, as it would in any
   sign-in form. These buttons are not inside a <form>, so without this the
   key did nothing. Ignored mid-composition (an IME) and while the button is
   busy, so a second press never sends twice. */
function enterClicks(e, buttonId) {
  if (e.key !== "Enter" || e.isComposing) return;
  e.preventDefault();
  const go = document.getElementById(buttonId);
  if (go && !go.disabled) go.click();
}

function showRegister(entry, saved) {
  const domain = LNCH.agencyDomain || "";
  signinShell(entry, `
    <p class="signin-lede">Register to govern AI for this agency. Every action
      you take is recorded against the name and title you enter, so please use
      your own.</p>

    <label class="signin-field"><span>Your full name</span>
      <input id="regName" type="text" autocomplete="name" spellcheck="false"
             value="${escHtml(saved.name || "")}"></label>
    <label class="signin-field"><span>Your job title</span>
      <input id="regTitle" type="text" autocomplete="organization-title"
             spellcheck="false" value="${escHtml(saved.title || "")}"></label>
    <label class="signin-field"><span>Work email${
        domain ? ` <em>— must end in @${escHtml(domain)}</em>` : ""}</span>
      <input id="regEmail" type="email" autocomplete="email" spellcheck="false"
             value="${escHtml(saved.email || "")}"></label>
    <label class="signin-field"><span>Contact phone</span>
      <input id="regPhone" type="tel" autocomplete="tel"
             value="${escHtml(saved.phone || "")}"></label>

    <label class="signin-attest">
      <input id="regAttest" type="checkbox">
      <span>I hold delegated authority to register on behalf of this agency,
        and I understand this is recorded.</span>
    </label>

    <p class="signin-error" id="regError" hidden></p>
    <p class="signin-warn">Registering claims this agency. Nobody else will be
      able to register it — only you will be able to add colleagues. Your
      mailbox is verified with a code${reviewRequired()
        ? "; your authority is confirmed by a reviewer."
        : ". Nobody checks your authority — what you build stays a draft until "
          + "whoever holds it adopts your framework."}</p>

    <div class="signin-actions">
      <button class="btn ghost" id="regBack" type="button">Back to map</button>
      <button class="btn" id="regGo" type="button">Register</button>
    </div>
    <p class="signin-alt">Already registered?
      <button class="linkish" id="regSignin" type="button">Sign in
        instead</button></p>`);

  const toSignin = document.getElementById("regSignin");
  if (toSignin) toSignin.onclick = () => showReturning(entry, saved.email || "");

  const err = document.getElementById("regError");
  const fail = (m) => { err.textContent = m; err.hidden = !m; };
  ["regName", "regTitle", "regEmail", "regPhone"].forEach((id) => {
    document.getElementById(id).oninput = () => fail("");
    document.getElementById(id).onkeydown = (e) => enterClicks(e, "regGo");
  });

  document.getElementById("regBack").onclick = () => showMap();
  document.getElementById("regGo").onclick = async () => {
    const body = {
      agency: LNCH.agency,
      name: document.getElementById("regName").value.trim(),
      title: document.getElementById("regTitle").value.trim(),
      email: document.getElementById("regEmail").value.trim(),
      phone: document.getElementById("regPhone").value.trim(),
      attested: document.getElementById("regAttest").checked,
    };
    const go = document.getElementById("regGo");
    go.disabled = true; go.textContent = "Checking…";
    let r;
    try {
      r = await fetch("/api/agency/register", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }).then((x) => x.json());
    } catch (e) {
      r = { ok: false, error: "Could not reach the server. Try again." };
    }
    go.disabled = false; go.textContent = "Register";
    if (!r.ok) {
      // It is them. Sending them round the same form again would be the third
      // time the product told them to ask themselves for access.
      if (r.is_you) return showReturning(entry, body.email);
      return fail(r.error || "That registration was refused.");
    }

    rememberRegistration({ ...body, agency: LNCH.agency });
    showVerify(entry, body.email, r.code, r.expires_in_minutes,
               r.delivery_note, r.mail_failed);
  };
  document.getElementById("regName").focus();
}

/* ---------------------------------------------- 1b. not on the list

   "Don't see your governmental unit? Click here to create your framework —
   and then walk them through the onboarding anyway. There just won't be an
   @ domain requirement."

   The same registration as a listed agency — name, title, phone, the
   attestation, a code to the mailbox — plus one field for the organization's
   name, and no domain rule. What that proves is said on the form, before
   anybody submits it. */

function showUnlisted(entry, saved = storedRegistration()) {
  // The heading would otherwise fall back to the state's own environmental
  // agency, putting another organization's name at the top of this form.
  LNCH.agencyName = "Your governmental unit";
  signinShell(entry, `
    <p class="signin-lede">Not on our list? You can still build your
      framework. Tell us what your organization is called, and register the
      same way everyone else does.</p>

    <label class="signin-field"><span>Your organization's name</span>
      <input id="unUnit" type="text" autocomplete="organization"
             spellcheck="false" aria-describedby="unUnitHint"
             value="${escHtml(saved.unlisted
               ? (saved.agencyName || "") : "")}"></label>
    <p class="signin-hint" id="unUnitHint">As it appears on your letterhead —
      for example, "Harris County Municipal Utility District No. 12".</p>

    <label class="signin-field"><span>Your full name</span>
      <input id="unName" type="text" autocomplete="name" spellcheck="false"
             value="${escHtml(saved.name || "")}"></label>
    <label class="signin-field"><span>Your job title</span>
      <input id="unTitle" type="text" autocomplete="organization-title"
             spellcheck="false" value="${escHtml(saved.title || "")}"></label>
    <label class="signin-field"><span>Email</span>
      <input id="unEmail" type="email" autocomplete="email" spellcheck="false"
             value="${escHtml(saved.email || "")}"></label>
    <label class="signin-field"><span>Contact phone</span>
      <input id="unPhone" type="tel" autocomplete="tel"
             value="${escHtml(saved.phone || "")}"></label>

    <label class="signin-attest">
      <input id="unAttest" type="checkbox">
      <span>I hold delegated authority to register on behalf of this
        organization, and I understand this is recorded.</span>
    </label>

    <p class="signin-error" id="unError" role="alert" hidden></p>
    <p class="signin-warn">Because your organization is not on our list, no
      email domain is required, and nobody checks the name you enter. We send
      a code to your address to confirm it is yours. Your organization and its
      framework are visible only to you and the colleagues you add, and the
      framework stays marked DRAFT until whoever holds the authority adopts
      it.</p>

    <div class="signin-actions">
      <button class="btn ghost" id="unBack" type="button">Back to map</button>
      <button class="btn" id="unGo" type="button">Register</button>
    </div>
    <p class="signin-alt">Already registered your organization?
      <button class="linkish" id="unSignin" type="button">Sign in
        instead</button></p>`);

  const err = document.getElementById("unError");
  const fail = (m) => { err.textContent = m; err.hidden = !m; };
  ["unUnit", "unName", "unTitle", "unEmail", "unPhone"].forEach((id) => {
    document.getElementById(id).oninput = () => fail("");
    document.getElementById(id).onkeydown = (e) => enterClicks(e, "unGo");
  });

  document.getElementById("unBack").onclick = () => showMap();
  document.getElementById("unSignin").onclick = () =>
    showReturning(entry, saved.email || "");

  document.getElementById("unGo").onclick = async () => {
    const body = {
      state: entry.code,
      unit: document.getElementById("unUnit").value.trim(),
      name: document.getElementById("unName").value.trim(),
      title: document.getElementById("unTitle").value.trim(),
      email: document.getElementById("unEmail").value.trim(),
      phone: document.getElementById("unPhone").value.trim(),
      attested: document.getElementById("unAttest").checked,
    };
    if (!body.unit) {
      document.getElementById("unUnit").focus();
      return fail("Enter your organization's name.");
    }
    const go = document.getElementById("unGo");
    go.disabled = true; go.textContent = "Checking…";
    let r;
    try {
      r = await post("/api/agency/register-unlisted", body);
    } catch (e) {
      r = { ok: false, error: "Could not reach the server. Try again." };
    }
    go.disabled = false; go.textContent = "Register";
    if (!r.ok) {
      if (r.is_you) return showReturning(entry, body.email);
      return fail(r.error || "That registration was refused.");
    }

    // From here it is the ordinary path. The unit's own id, name and
    // shorthand are kept with the registration, because the dropdown will
    // never list it and every later screen needs its name.
    LNCH.agency = r.agency.id;
    LNCH.agencyName = r.agency.name;
    LNCH.agencyDomain = "";
    rememberRegistration({
      name: body.name, title: body.title, email: body.email,
      phone: body.phone, state: entry.code, agency: r.agency.id,
      agencyName: r.agency.name, abbrev: r.agency.abbrev, unlisted: true,
    });
    showVerify(entry, body.email, r.code, r.expires_in_minutes,
               r.delivery_note, r.mail_failed);
  };
  document.getElementById("unUnit").focus();
}

/* The agency to put on screen for an id, including one that is not on the
   list. A listed agency comes from the dropdown data as before. An unlisted
   unit comes from the server's answer about this address where there is one
   — a new browser has nothing stored — and from the registration this
   browser kept, otherwise. `null` where neither knows it, so the caller asks
   again rather than guessing. */
function chosenFor(entry, id, access) {
  const listed = entry && (entry.agencies || []).find((a) => a.id === id);
  if (listed) return listed;
  if (!id) return null;
  const saved = storedRegistration();
  const name = (access && access.unlisted && access.state === id
                  && access.agency_label)
    || (saved.unlisted && saved.agency === id && saved.agencyName) || "";
  if (!name) return null;
  return {
    id, name,
    abbrev: (access && access.agency_abbrev) || saved.abbrev || name,
    domain: "", unlisted: true,
  };
}

/* -------------------------------------------------------------- 2. verify */

/* Three states, not two.

   This knew "the code is on screen" and "we emailed it", and a failed send on
   a deployment that withholds the code fell into the second — so the screen
   said "We have emailed a six-digit code, check your inbox" about a message
   that was never sent, and then waited for a code nobody would ever receive.
   See `mailer.may_show_code` for when the code is withheld and why. */
function showVerify(entry, email, shownCode, ttl, deliveryNote, mailFailed) {
  const lede = shownCode
    ? `A six-digit code was issued for <b>${escHtml(email)}</b>. Enter it to
       prove the mailbox is yours.`
    : mailFailed
    ? `A six-digit code was issued for <b>${escHtml(email)}</b>, but we could
       not send it.`
    : `We have emailed a six-digit code to <b>${escHtml(email)}</b>. Check
       your inbox — and your spam folder, since this may be the first message
       you have had from us. Enter it to prove the mailbox is yours.`;

  signinShell(entry, `
    <p class="signin-lede">${lede}</p>

    ${shownCode ? `
      <div class="signin-code">
        <span>${escHtml(deliveryNote || "No email was sent, so the code is " +
          "shown here instead.")}</span>
        <b>${escHtml(shownCode)}</b>
      </div>` : ""}

    ${mailFailed ? `
      <div class="signin-undelivered">
        <b>The code could not be sent</b>
        <span>${escHtml(deliveryNote || "The mail provider refused the "
          + "message.")}</span>
        <span>Use <b>Back</b> to try again. If a code does arrive later, it
          will still work for ${ttl || 30} minutes.</span>
      </div>` : ""}

    <label class="signin-field"><span>Verification code</span>
      <input id="verCode" type="text" inputmode="numeric" maxlength="6"
             autocomplete="one-time-code" spellcheck="false"></label>

    <p class="signin-error" id="verError" hidden></p>
    <p class="signin-warn">${ttl ? `The code lasts ${ttl} minutes. ` : ""}Verifying
      proves the address is yours. It does not prove you may act for the
      agency${reviewRequired()
        ? " — a reviewer confirms that next."
        : ", and nobody checks. Entering the code opens your agency."}</p>

    <div class="signin-actions">
      <button class="btn ghost" id="verBack" type="button">Back</button>
      <button class="btn" id="verGo" type="button">Verify</button>
    </div>`);

  const err = document.getElementById("verError");
  err.setAttribute("role", "alert");
  const box = document.getElementById("verCode");
  // Auto-verify: the sixth digit sends it — typed, pasted or filled in from
  // the email by the phone. Anything that is not a digit is dropped, so a
  // pasted "123 456" still counts. Verify and Enter still work as before.
  let sentFor = "";
  box.oninput = () => {
    err.hidden = true;
    const digits = box.value.replace(/\D/g, "").slice(0, 6);
    if (box.value !== digits) box.value = digits;
    const go = document.getElementById("verGo");
    if (digits.length === 6 && digits !== sentFor && go && !go.disabled) {
      sentFor = digits;
      go.click();
    }
    if (digits.length < 6) sentFor = "";
  };
  box.onkeydown = (e) => enterClicks(e, "verGo");

  document.getElementById("verBack").onclick = () => {
    const saved = storedRegistration();
    // Back to the form they came from. The unlisted form has the
    // organization's name on it, which the listed one does not.
    if (saved.unlisted) return showUnlisted(entry, saved);
    showRegister(entry, saved);
  };

  document.getElementById("verGo").onclick = async () => {
    const go = document.getElementById("verGo");
    go.disabled = true; go.textContent = "Checking…";
    let r;
    try {
      r = await fetch("/api/agency/verify", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code: box.value.trim() }),
      }).then((x) => x.json());
    } catch (e) { r = { ok: false, error: "Could not reach the server." }; }
    go.disabled = false; go.textContent = "Verify";

    if (!r.ok) {
      // Wrong code: empty the box for the next try, shake the button, and
      // say so in words — the words are what a screen reader hears.
      err.textContent = r.error || "That code was not accepted.";
      err.hidden = false;
      box.value = "";
      sentFor = "";
      go.classList.remove("signin-shake");
      void go.offsetWidth;                 // restart the animation
      go.classList.add("signin-shake");
      go.addEventListener("animationend",
        () => go.classList.remove("signin-shake"), { once: true });
      if (navigator.vibrate) { try { navigator.vibrate(120); } catch (_) { /* not offered */ } }
      box.focus();
      return;
    }
    rememberRegistration({ email, verified: true });
    // The one moment this browser proves whose mailbox it is. Everything the
    // server will not take on the browser's word — reading reports filed from
    // other agencies, above all — is decided from this token rather than from
    // the address in the query string. See app/admin.py.
    rememberSession(r.session);
    if (r.status === "active") return showNda(entry, email);
    showWaiting(entry, storedRegistration(), r);
  };
  box.focus();
}

/* ------------------------------------------------------------- 3. waiting */

function showWaiting(entry, saved, info) {
  signinShell(entry, `
    <p class="signin-lede">Your mailbox is verified. The agency is not open
      yet.</p>
    <p class="signin-warn" style="border-left-color:var(--warn)">
      ${escHtml((info && info.next) || "A reviewer confirms that you hold " +
        "delegated authority before the agency opens. Verifying your mailbox " +
        "proved the address is yours, not that you may act for the agency.")}
    </p>
    <p class="signin-lede" style="margin-top:12px">Registered as
      <b>${escHtml(saved.name || saved.email || "")}</b>${
        saved.title ? `, ${escHtml(saved.title)}` : ""}. Nobody else can now
      register this agency — when you are approved you will be able to add
      colleagues yourself.</p>
    <div class="signin-actions">
      <button class="btn ghost" id="waitBack" type="button">Back to map</button>
      <button class="btn" id="waitCheck" type="button">Check again</button>
    </div>`);

  document.getElementById("waitBack").onclick = () => showMap();
  document.getElementById("waitCheck").onclick = async () => {
    const access = await agencyAccess(saved.email);
    if (access.allowed) return showNda(entry, saved.email, access);
    toast("Still waiting on the reviewer.");
  };
}

/* ------------------------------------------------------ 2b. already in

   Register was the only door. It claims an agency and refuses if that agency is
   taken, so someone who registered, signed out and came back was told "this
   agency has already been registered by <their own name> — ask them to add
   you", with nothing else on the screen to click.

   This asks for the address and sends a code. It proves the same thing
   registration proves — control of the mailbox — and nothing more: no container
   is created and no agency claimed, because both already exist. */

function showReturning(entry, prefill) {
  signinShell(entry, `
    <p class="signin-lede">Sign in to ${escHtml(LNCH.agencyName || entry.agency)}</p>
    <p class="signin-warn">A six-digit code goes to the work email you
      registered with. Nothing else is needed — your name and title are already
      on the record.</p>

    <label class="signin-field"><span>Work email</span>
      <input id="siEmail" type="email" autocomplete="email" spellcheck="false"
             value="${escHtml(prefill || "")}"></label>

    <p class="signin-error" id="siError" hidden></p>
    <div class="signin-actions">
      <button class="btn ghost" id="siBack" type="button">Back</button>
      <button class="btn" id="siGo" type="button">Send me a code</button>
    </div>
    <p class="signin-alt">Not registered yet?
      <button class="linkish" id="siRegister" type="button">Register this
        agency</button></p>`);

  const box = document.getElementById("siEmail");
  const err = document.getElementById("siError");
  const fail = (m) => { err.textContent = m; err.hidden = !m; };
  box.oninput = () => fail("");
  // Enter sends the code, as it would in any sign-in form. The button is not
  // inside a <form>, so without this the key did nothing.
  box.onkeydown = (e) => enterClicks(e, "siGo");

  document.getElementById("siBack").onclick = () => showMap();
  document.getElementById("siRegister").onclick = () => showRegister(entry);

  document.getElementById("siGo").onclick = async () => {
    const email = (box.value || "").trim().toLowerCase();
    if (!email.includes("@")) {
      return fail("Enter the work email you registered with.");
    }
    const go = document.getElementById("siGo");
    go.disabled = true; go.textContent = "Sending…";
    let r;
    try {
      // The agency picked on the map goes with it, so an address registered
      // to a different one is told so instead of being signed in there.
      r = await post("/api/agency/signin", { email, agency: LNCH.agency || "" });
    } catch (e) { r = { ok: false, error: "Could not reach the server." }; }
    go.disabled = false; go.textContent = "Send me a code";

    if (!r.ok) return fail(r.error || "Could not send a code.");
    rememberRegistration({ email });
    showVerify(entry, email, r.code, r.expires_in_minutes, r.delivery_note,
               r.mail_failed);
  };
  box.focus();
}

/* ------------------------------------------------------------- 3b. the NDA

   Everything inside is IIA's confidential product material, so the agreement
   comes between proving the mailbox and seeing any of it. The client's rule:
   Accept goes to the home screen; Decline notifies IIA immediately and asks
   "Are you sure?"; declining again locks the account until IIA lifts it.

   The first decline deliberately does not lock. People misclick, and people
   read a legal document and want a moment — making an unrecoverable state one
   accidental click away would be a poor trade for a demo platform. */

async function showNda(entry, email, access) {
  let state;
  try {
    state = await fetch("/api/nda?email=" + encodeURIComponent(email))
      .then((r) => r.json());
  } catch (e) {
    // The gate failing open would hand out the materials the gate exists to
    // protect, so it fails closed and says why.
    return signinShell(entry, `
      <p class="signin-lede">Could not load the confidentiality agreement.</p>
      <p class="signin-warn">Nothing is accessible until it has been read and
        accepted, so this is a stop rather than a warning. Try again in a
        moment.</p>
      <div class="signin-actions">
        <button class="btn ghost" id="ndaBack" type="button">Back</button>
      </div>`) || wireBack();
  }

  if (state.status === "accepted") return finishSignin(access
    || await agencyAccess(email));

  if (state.status === "locked") return showNdaLocked(entry, state);

  const confirming = state.status === "declined_once";
  const saved = storedRegistration();

  signinShell(entry, `
    <p class="signin-lede">${escHtml(state.headline || "")}</p>
    <p class="signin-warn"${confirming
      ? ' style="border-left-color:var(--alert)"' : ""}>${escHtml(state.note || "")}</p>

    <div class="nda-doc">
      <object data="${escHtml(state.document.url)}#view=FitH"
              type="application/pdf" aria-label="One-Way Non-Disclosure Agreement">
        <p class="nda-fallback">Your browser will not display the PDF inline.
          <a href="${escHtml(state.document.url)}" target="_blank"
             rel="noopener">Open the agreement in a new tab</a> to read it.</p>
      </object>
    </div>
    <p class="nda-meta">
      <a href="${escHtml(state.document.url)}" target="_blank" rel="noopener">
        Open in a new tab</a> ·
      <a href="${escHtml(state.document.url)}" download>Download a copy</a> ·
      <span class="mono" title="The exact version you are accepting"
        >${escHtml((state.document.sha256 || "").slice(0, 12))}</span>
    </p>

    <p class="signin-error" id="ndaError" hidden></p>
    <div class="signin-actions">
      <button class="btn ghost" id="ndaNo" type="button">${
        confirming ? "Decline — I understand this locks my account"
                   : "Decline"}</button>
      <button class="btn" id="ndaYes" type="button">Accept and continue</button>
    </div>
    <p class="small muted" style="margin-top:8px">Your name, address and the
      time of acceptance are recorded, along with the version above. That record
      is what the agreement refers to as evidence.</p>`);

  const err = document.getElementById("ndaError");
  const fail = (m) => { err.textContent = m; err.hidden = !m; };

  document.getElementById("ndaYes").onclick = async () => {
    const go = document.getElementById("ndaYes");
    go.disabled = true; go.textContent = "Recording…";
    let r;
    try {
      r = await post("/api/nda/accept", {
        email, name: saved.name || "", title: saved.title || "",
        agency: LNCH.agency || "",
      });
    } catch (e) { r = { ok: false, error: "Could not reach the server." }; }
    if (!r.ok) {
      go.disabled = false; go.textContent = "Accept and continue";
      return fail(r.error || "Could not record your acceptance.");
    }
    finishSignin(access || await agencyAccess(email));
  };

  document.getElementById("ndaNo").onclick = async () => {
    let r;
    try {
      r = await post("/api/nda/decline", {
        email, name: saved.name || "", title: saved.title || "",
        agency: LNCH.agency || "",
      });
    } catch (e) { return fail("Could not reach the server."); }
    if (r.status === "locked") return showNdaLocked(entry, r.state);
    // Re-render into the confirming state, which is where "Are you sure?" and
    // the harder-worded Decline button come from.
    showNda(entry, email, access);
  };

  function wireBack() {
    const back = document.getElementById("ndaBack");
    if (back) back.onclick = () => showMap();
  }
}

function showNdaLocked(entry, state) {
  signinShell(entry, `
    <p class="signin-lede">${escHtml((state && state.headline)
      || "This account is locked.")}</p>
    <p class="signin-warn" style="border-left-color:var(--alert)">
      ${escHtml((state && state.note) || "")}</p>
    <p class="small muted">Nothing you built is lost. The lock is on entry, not
      on the record — when it is lifted, everything is where you left it.</p>
    <div class="signin-actions">
      <button class="btn ghost" id="lockBack" type="button">Back to map</button>
    </div>`);
  document.getElementById("lockBack").onclick = () => showMap();
}

/* ---------------------------------------------------------------- 4. in */

async function finishSignin(access) {
  const saved = storedRegistration();

  /* Hand the shell the agency they actually registered with.

     Until now it was handed the *state* entry, so every screen took South
     Carolina's default agency: registering with the DEMO agency produced a
     header reading SCDES, a breadcrumb reading "South Carolina Department of
     Environmental Services", the PermitPro project spine, and a Framework page
     listing SCDES's own documents. One agency looking at another's record is
     the single thing this application must never do.

     `corpus_loaded` is the other half. It was a property of the state, so every
     agency in South Carolina inherited SCDES's documents. It belongs to the one
     agency that owns them, which the server now names in `loaded_agency`. */
  const entry = (LNCH.data && LNCH.data.states || [])
    .find((s) => s.code === LNCH.active);
  // An unlisted unit is not in the dropdown, so it is looked up by the
  // container the server says this address belongs to. Without this the
  // header fell back to the state's environmental agency — another
  // organization's name over this one's work.
  const id = (access && access.unlisted && access.state) || LNCH.agency;
  const chosen = chosenFor(entry, id, access);
  if (entry) applyAgencyLabels(agencyEntryFor(entry, chosen));

  /* Persist the agency, not just the fact of being verified.

     Only `verified: true` was stored, so a reload had no idea which of 149
     agencies had been chosen and had to ask again — sending a signed-in user
     back to the map every time they refreshed. The client's rule is the
     opposite: a user goes straight to the home page for THEIR agency and never
     sees the picker again unless they sign out. */
  rememberRegistration({
    verified: true,
    state: entry ? entry.code : "",
    agency: chosen ? chosen.id : "",
    abbrev: chosen ? chosen.abbrev : "",
    agencyName: chosen ? chosen.name : "",
    unlisted: !!(chosen && chosen.unlisted),
  });
  if (window.signInAs) {
    // Capacity is fixed for now: an agency's first user owns their container.
    // Titles do not grant powers, so nothing is chosen here.
    try {
      await window.signInAs("sean.ot", access.name || saved.name || "",
                            access.title || saved.title || "");
    } catch (e) { console.warn(e); }
  }
  showMap();
  closeLauncher();
  // The beta notice, after signing in — see `showBetaNotice` in app.js. It
  // decides for itself whether this session has already read it, so a
  // reload does not bring it back.
  if (window.showBetaNotice) window.showBetaNotice();
}

/** Return the picker to the map — used by Back, and whenever it reopens. */
function showMap() {
  const panel = document.getElementById("signinPanel");
  const inner = document.querySelector(".lnch-inner");
  if (panel) panel.hidden = true;
  if (inner) inner.hidden = false;
}

/** Selecting an agency leads to signing in, not straight into the record. */
function enterAgency(code) {
  selectState(code, false);
  const entry = LNCH.data.states.find((s) => s.code === code);
  if (!entry) return;
  if (!entry.open_for_registration) {
    toast(`${entry.state} is not open for registration yet.`);
    return;
  }
  // "Other" from the list is the unlisted way in, not an agency.
  if (LNCH.agency === otherEntry(entry).id) {
    enterUnlisted(code);
    return;
  }
  // The agency, not just the state, decides the email rule and the container.
  const chosen = (entry.agencies || []).find((a) => a.id === LNCH.agency);
  if (!chosen) {
    toast("Choose your agency first.");
    const pick = document.getElementById("agencyPick");
    if (pick) pick.focus();
    return;
  }
  LNCH.agencyName = chosen.name;
  LNCH.agencyDomain = chosen.domain;
  showSignin(entry);
}

/* The same way in, for a governmental unit that is not on the list. See
   app/unlisted.py for what that door does and does not check. */
function enterUnlisted(code) {
  selectState(code, false);
  const entry = LNCH.data.states.find((s) => s.code === code);
  if (!entry) return;
  if (!entry.open_for_registration) {
    toast(`${entry.state} is not open for registration yet.`);
    return;
  }
  LNCH.agency = "";
  LNCH.agencyName = "";
  LNCH.agencyDomain = "";
  showUnlisted(entry);
}

/* ------------------------------------------------------------------ open */

function openLauncher() {
  /* Checked here as well as in app.js's showLauncher().

     Two callers is two chances to forget, and what is being guarded is the one
     thing this application must never do — put another agency's records in
     front of someone. A guard at the door is worth more than a guard on each
     path to it. `resumeSession` calls this deliberately to show the NDA over
     the map, so it passes `force`. */
  if (!arguments[0]) {
    let saved = {};
    try {
      saved = JSON.parse(localStorage.getItem("scdes.registration") || "{}") || {};
    } catch (e) { saved = {}; }
    if (saved.verified && saved.agency) return;
  }
  const host = document.getElementById("launcher");
  host.hidden = false;
  document.body.classList.add("launcher-open");

  // Reopening left focus wherever it was in the application behind — usually a
  // rail button. Because #launcher is the first element in the body, tabbing on
  // from there walks the rest of the page and only reaches the map after a full
  // cycle, so it read as "Tab does nothing". Put focus on the current state.
  showMap();          // reopening always lands on the map, never mid-sign-in

  const target = host.querySelector(".st.active") || host.querySelector(".st");
  if (target) target.focus();

  // Reopening does not re-select — focusing the already-active state is a no-op
  // by design — so the flag would otherwise sit wherever it was last placed,
  // against a map that may have been laid out at a different size since.
  refreshFlag();
}

/* While the picker is open it is the only thing on screen, so Tab should cycle
   within it rather than wander through the application underneath — which is
   still in the document and still focusable. */
function trapFocus(e) {
  if (e.key !== "Tab") return;
  const host = document.getElementById("launcher");
  if (host.hidden) return;
  const items = [...host.querySelectorAll(
    '.st, button, [href], input, select, [tabindex]:not([tabindex="-1"])')]
    .filter((n) => n.offsetParent !== null || n.classList.contains("st"));
  if (!items.length) return;

  const first = items[0], last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault(); last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault(); first.focus();
  } else if (!host.contains(document.activeElement)) {
    e.preventDefault(); first.focus();
  }
}
function closeLauncher() {
  document.getElementById("launcher").hidden = true;
  document.body.classList.remove("launcher-open");
  if (location.hash === "#agency") history.replaceState(null, "", location.pathname);

  // Focus was on a state in a map that is now hidden. Hand it to the first item
  // in the rail so keyboard use continues from a sensible place instead of
  // restarting at the top of the document.
  const first = document.querySelector(".rail-item");
  if (first) first.focus();
}

async function initLauncher() {
  // Before the fetches, so the toggle works even if the registry call fails.
  initColorMode();

  const user = encodeURIComponent(window.SCDES_USER || "liz.operator");
  const [reg, map] = await Promise.all([
    fetch("/api/states?user=" + user).then((r) => r.json()),
    fetch("/assets/us-map.json").then((r) => r.json()),
  ]);
  LNCH.data = reg;
  LNCH.map = map;
  window.LNCH_DATA = reg;      // app.js reads `loaded` from this

  // The roster for the sign-in step. Failing to load it must not take the map
  // down with it — a picker that still works is better than a blank page.
  try {
    const state = await fetch("/api/state?user=" + user).then((r) => r.json());
    LNCH.capacities = state.capacities || [];
    LNCH.actor = state.actor || null;
  } catch (e) {
    LNCH.capacities = [];
    console.warn("[launcher] capacities unavailable; sign-in will be empty", e);
  }
  buildLauncher();

  /* Who sees the map.

     Only someone who has not yet chosen an agency. Anyone already signed in
     goes straight into their own agency — the picker is a front door, not a
     lobby to pass through on every visit, and the client's rule is that a user
     should never be offered another agency once theirs is settled.

     Signing out clears the stored agency, which is what brings the map back. */
  if (await resumeSession()) return;

  const onboarding = window.initOnboarding ? await window.initOnboarding() : false;
  if (!onboarding) openLauncher();
}

/** Pick up where they left off. True if the map should stay shut. */
async function resumeSession() {
  const saved = storedRegistration();
  if (!saved.verified || !saved.agency || !saved.state) return false;

  const entry = (LNCH.data.states || []).find((s) => s.code === saved.state);
  // Includes a unit that is not on the list, from what this browser kept.
  const chosen = chosenFor(entry, saved.agency, null);
  // The agency list can change under a stored session — an id that no longer
  // exists means asking again is the only honest option.
  if (!entry || !chosen) return false;

  // The NDA still stands between them and the product. Resuming a session must
  // not be a way around a gate that a fresh sign-in has to pass.
  try {
    const nda = await fetch("/api/nda?email=" + encodeURIComponent(saved.email))
      .then((r) => r.json());
    if (nda.status !== "accepted") {
      LNCH.agency = saved.agency;
      selectState(saved.state, false);
      openLauncher(true);          // their own agency, to show the NDA over
      showNda(entry, saved.email);
      return true;
    }
  } catch (e) {
    return false;                      // cannot confirm the gate: ask again
  }

  LNCH.agency = saved.agency;
  LNCH.active = saved.state;
  applyTheme(entry);
  applyAgencyLabels(agencyEntryFor(entry, chosen));
  if (window.signInAs) {
    try {
      await window.signInAs("sean.ot", saved.name || "", saved.title || "");
    } catch (e) { console.warn(e); }
  }
  closeLauncher();
  return true;
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !document.getElementById("launcher").hidden)
    closeLauncher();
  trapFocus(e);
});

// The map scales with the window, so the flag's anchor moves with it.
window.addEventListener("resize", () => {
  if (!document.getElementById("launcher").hidden) refreshFlag();
});

window.openLauncher = openLauncher;
window.initLauncher = initLauncher;
// The application needs to know which agency is on screen and which one owns
// the corpus, so it can refuse to render one's records under the other's name.
window.selectAgency = (code) => selectState(code, false);
window.initColorMode = initColorMode;
window.applyColorModeLabels = () => applyMode(colorMode(), false);
