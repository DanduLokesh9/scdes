/* Agency launcher — a real US map, filled with the flag, themed per state.

   The map is genuine geography: Census cartographic boundaries projected with
   Albers equal-area conic (Alaska and Hawaii as insets), built offline by
   tools/build_map.py into us-map.json. No network, no map library.

   The flag is clipped to the country outline rather than laid behind it, so
   the map *is* the flag. Selecting a state lifts it out of the flag and fills
   it with that agency's colour. */

/* Bumped whenever this file changes in a way worth confirming reached the
   browser. Printed on load so "is the page running the current code?" is a
   question that can be answered in one look rather than argued about. */
const LNCH_BUILD = "2026-08-14-flags";

const LNCH = { data: null, map: null, active: null };

console.log(`[launcher] build ${LNCH_BUILD} — state flags enabled`);

/* ------------------------------------------------------------ colour mode */

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
  // Idempotent: callers may retry this if the launcher failed to initialise, and
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
   brand roles filled by reusing the agency's own colours, foregrounds chosen for
   contrast, and status colours left alone. Nothing is calculated here, so there
   is one implementation of the rules rather than two that can drift apart.

   Status colours are deliberately absent from what gets overwritten — Low,
   Moderate and High risk are the same in every state. */
const THEMED_ONLY = /^--(chrome|chrome-2|chrome-line|accent|accent-2|highlight|action|on-chrome|on-action|accent-text-light|accent-text-dark|brand-bands|brand-sweep|sidebar|sidebar-2|sidebar-line)$/;

/* The shell's agency labels were static markup, so picking Ohio retuned every
   colour and still said SCDES in the header and the breadcrumb. They follow the
   selection now. The corpus is what makes a name authoritative — until one is
   loaded this is the seeded label, which is why it is marked unverified in the
   picker rather than presented as fact. */
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

/* Official colours, from the specification the flag is actually made to:
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
  const shapes = codes.map((c) => {
    const s = byCode[c];
    const title = s ? `${s.state} — ${s.agency}` : (map.states[c].name || c);
    return `<path class="st${s && s.corpus_loaded ? " has-corpus" : ""}" ` +
           `data-code="${c}" d="${map.states[c].d}" tabindex="0" role="button" ` +
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
                 own colours rather than one flat fill. Stop count follows the
                 agency, so two colours give two stops. Set in selectState(). -->
            <linearGradient id="agencyFill" x1="0" y1="0" x2="1" y2="1"></linearGradient>
            <!-- A light raking across the flag and a shadow gathering bottom
                 right. Flat colour reads as a printed chart; a little modelling
                 reads as cloth. -->
            <linearGradient id="flagSheen" x1="0.1" y1="0" x2="0.85" y2="1">
              <stop offset="0%"   stop-color="#ffffff" stop-opacity="0.20"/>
              <stop offset="38%"  stop-color="#ffffff" stop-opacity="0.03"/>
              <stop offset="72%"  stop-color="#000000" stop-opacity="0.06"/>
              <stop offset="100%" stop-color="#000018" stop-opacity="0.22"/>
            </linearGradient>
            <filter id="mapShadow" x="-12%" y="-12%" width="126%" height="126%">
              <feDropShadow dx="0" dy="7" stdDeviation="11"
                            flood-color="#000814" flood-opacity="0.5"/>
            </filter>
          </defs>

          <g filter="url(#mapShadow)">
            <g clip-path="url(#usClip)" class="flag">${flagLayer()}</g>
            <g clip-path="url(#usClip)">
              <rect x="0" y="0" width="960" height="600" fill="url(#flagSheen)"/>
            </g>
          </g>
          <g class="states">${shapes}</g>
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

  host.querySelectorAll(".st").forEach((p) => {
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

  // Fill the selected state with a sweep through the agency's own colours. The
  // stop count follows the agency: two colours give two stops, not two real and
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
  applyTheme(s);
  applyAgencyLabels(s);
  showFlag(code, s);

  // The note was a fixed paragraph, so it read as boilerplate and said the same
  // thing whichever state you were on. It now names the agency in front of you,
  // which is the only way the "this name is unverified" caveat lands.
  const note = document.getElementById("lnchNote");
  if (note) {
    note.textContent = s.corpus_loaded
      ? `${s.agency} is confirmed by its own adopted documents, which are `
        + `loaded. The instruments, lifecycle and vocabulary on every screen `
        + `are read from that corpus rather than built in.`
      : `"${s.agency}" is a seeded label, not a verified fact — agencies rename `
        + `themselves. Load ${s.abbrev}'s adopted documents and the name, `
        + `instruments, lifecycle and vocabulary are all replaced by what those `
        + `documents say.`;
  }

  // The swatches show the theme, nothing more. Where the colours came from and
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
        <b>${escHtml(s.agency)}</b>
        <button class="mode-chip" type="button" aria-pressed="false"></button>
      </div>
      <span>${escHtml(s.abbrev)} · ${s.corpus_loaded
          ? "corpus loaded — name confirmed by its own documents"
          : "no corpus loaded — agency name unverified"}</span>
      <div class="lnch-swatches">${swatches}</div>
    </div>
    <div class="lnch-actions">
      <button class="btn" id="lnchEnter">${
        s.corpus_loaded ? "Enter " + escHtml(s.abbrev) : "Use this theme"}</button>
      ${s.corpus_loaded ? "" :
        `<button class="btn ghost" id="lnchWhy">No corpus — what does that mean?</button>`}
    </div>`;

  // The panel is rebuilt on every selection, so its toggle needs relabelling.
  applyMode(colorMode(), false);

  document.getElementById("lnchEnter").onclick = () => enterAgency(code);
  const why = document.getElementById("lnchWhy");
  // Speaks to the corpus only. Nothing about where the colours came from.
  if (why) why.onclick = () => alert(
    `No corpus has been loaded for ${s.state}.\n\n` +
    `The agency name shown is a seed from public knowledge, not a verified ` +
    `fact, and nothing else about ${s.abbrev} is available yet.\n\n` +
    `To operate ${s.abbrev} for real, drop that agency's adopted documents ` +
    `into corpus/. The application then re-derives the identity, instruments, ` +
    `lifecycle and vocabulary from the documents themselves.`);

  if (announce && window.toast) window.toast(
    `${s.abbrev} theme applied.${s.corpus_loaded ? "" :
      " No corpus loaded for this state."}`);
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

function showSignin(entry) {
  const panel = document.getElementById("signinPanel");
  const inner = document.querySelector(".lnch-inner");
  if (!panel || !inner) return;

  const roster = (LNCH.roster || []);
  const current = LNCH.actor && LNCH.actor.id;

  panel.innerHTML = `
    <div class="signin-card" role="dialog" aria-modal="true"
         aria-labelledby="signinTitle">
      <p class="signin-eyebrow">${escHtml(entry.state)}</p>
      <h2 id="signinTitle">${escHtml(entry.agency)}</h2>
      <p class="signin-lede">Who is signing in? Every governed action is
        recorded against this person, and what you may do follows from their
        role.</p>

      <div class="signin-list" role="radiogroup" aria-label="Choose who you are">
        ${roster.map((r, i) => `
          <button class="signin-who${r.id === current || (!current && !i)
            ? " on" : ""}" type="button" role="radio"
            aria-checked="${r.id === current || (!current && !i)}"
            data-id="${escHtml(r.id)}">
            <span class="signin-ava">${escHtml(initials(r.name))}</span>
            <span class="signin-who-text">
              <b>${escHtml(r.name)}</b>
              <small>${escHtml(roleLabel(r.role))}</small>
            </span>
          </button>`).join("")}
      </div>

      <p class="signin-warn">This build identifies you against
        ${escHtml(entry.abbrev)}'s local roster. It does not verify identity —
        there is no password and no session. In production this step is the
        agency's own single sign-on.</p>

      <div class="signin-actions">
        <button class="btn ghost" id="signinBack" type="button">Back to map</button>
        <button class="btn" id="signinGo" type="button">Sign in</button>
      </div>
    </div>`;

  inner.hidden = true;
  panel.hidden = false;

  let chosen = (roster.find((r) => r.id === current) || roster[0] || {}).id;
  panel.querySelectorAll(".signin-who").forEach((b) => {
    b.onclick = () => {
      chosen = b.dataset.id;
      panel.querySelectorAll(".signin-who").forEach((o) => {
        o.classList.toggle("on", o === b);
        o.setAttribute("aria-checked", String(o === b));
      });
    };
  });

  document.getElementById("signinBack").onclick = () => showMap();
  document.getElementById("signinGo").onclick = () => finishSignin(chosen);

  const first = panel.querySelector(".signin-who.on") ||
                panel.querySelector(".signin-who");
  if (first) first.focus();
}

const initials = (name) => String(name || "?").split(/\s+/)
  .map((w) => w[0]).join("").slice(0, 2).toUpperCase();

/** The roster stores machine roles; people read titles. */
function roleLabel(role) {
  return ({ "operator": "Operator — submits and runs projects",
            "ot": "Office of Technology — owns the configuration",
            "council-member": "Council member — approves gated decisions",
          })[role] || role;
}

async function finishSignin(id) {
  if (id && window.signInAs) {
    try { await window.signInAs(id); } catch (e) { console.warn(e); }
  }
  showMap();
  closeLauncher();
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
  if (entry) showSignin(entry);
}

/* ------------------------------------------------------------------ open */

function openLauncher() {
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
    LNCH.roster = state.roster || [];
    LNCH.actor = state.actor || null;
  } catch (e) {
    LNCH.roster = [];
    console.warn("[launcher] roster unavailable; sign-in will be empty", e);
  }
  buildLauncher();

  // The map is the landing page only for someone already registered. A new user
  // chooses a portal and registers an email first, and onboarding opens the map
  // itself when it is done.
  const onboarding = window.initOnboarding ? await window.initOnboarding() : false;
  if (!onboarding) openLauncher();
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
