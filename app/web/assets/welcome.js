/* The 60-second welcome.

   Shown once, immediately after signing in, before any other screen is
   reachable. Its whole job is to land one idea: **the framework comes first, and
   everything else is read out of it.**

   This is a timed animated explainer, not a video file. Deliberately:
     · it needs no hosting, no bandwidth and no player, and works offline;
     · the text is real text — searchable, translatable, and readable by a screen
       reader, which a burned-in video caption is not;
     · when a real 60-second film exists it drops straight in here, because the
       surrounding flow does not care what fills this screen.

   Six segments, ten seconds each. Skippable at any point — a welcome that
   cannot be skipped is an obstacle, and someone returning for the fifth time
   should not have to sit through it. */

const WELCOME_SEGMENTS = [
  {
    at: 0,
    kicker: "Welcome",
    title: "This is your governance framework, running.",
    body: "Not a summary of it. Not a form that mimics it. The adopted " +
          "documents themselves, read and executed.",
    art: "doc",
  },
  {
    at: 10,
    kicker: "The idea",
    title: "The framework is the brain.",
    body: "Your risk model, your approval gates, your vocabulary, your required " +
          "forms — every one of them is read out of the framework you adopt. " +
          "Nothing here is invented.",
    art: "brain",
  },
  {
    at: 20,
    kicker: "Why it comes first",
    title: "You cannot have a process without a framework.",
    body: "A registry with no categories to sort into. A lifecycle with no " +
          "gates. A budget with no thresholds. Each one would be structure " +
          "your agency never agreed to.",
    art: "blocked",
  },
  {
    at: 30,
    kicker: "So the app waits",
    title: "Everything else stays closed until the framework is in.",
    body: "Not to be awkward — because an empty screen is honest and a " +
          "confidently-wrong screen is not. Load your framework and the rest " +
          "opens up, shaped by what it says.",
    art: "lock",
  },
  {
    at: 40,
    kicker: "Two ways in",
    title: "Upload what you have adopted, or start from the reference.",
    body: "If your agency has a framework, operations manual and appendices, " +
          "bring them. If you are starting out, begin from the reference " +
          "framework and amend it into your own.",
    art: "paths",
  },
  {
    at: 50,
    kicker: "Then everything follows",
    title: "Every figure traces back to a document somebody signed.",
    body: "Ask a question, get the section that answers it. Score a project, " +
          "see which factor drove the band. That is the point of all of it.",
    art: "trace",
  },
];

const WELCOME_TOTAL = 60;      // seconds
const WELCOME_SEEN = "scdes.welcomeSeen";

const WEL = { t: 0, timer: null, playing: false, onDone: null };

const welEsc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ------------------------------------------------------------------ artwork */

/* Simple, legible diagrams rather than decoration — each one is the sentence
   beside it, drawn. */
function welcomeArt(kind) {
  const box = (x, y, w, h, cls) =>
    `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="4" class="${cls}"/>`;
  switch (kind) {
    case "doc":
      return `<svg viewBox="0 0 260 150">
        ${box(20, 18, 78, 104, "wa-paper")}
        <line x1="32" y1="38" x2="84" y2="38" class="wa-line"/>
        <line x1="32" y1="50" x2="84" y2="50" class="wa-line"/>
        <line x1="32" y1="62" x2="70" y2="62" class="wa-line"/>
        <path d="M104 70 L146 70" class="wa-arrow"/>
        ${box(152, 30, 88, 80, "wa-screen")}
        <line x1="164" y1="48" x2="228" y2="48" class="wa-line-lit"/>
        <line x1="164" y1="62" x2="212" y2="62" class="wa-line-lit"/>
        <line x1="164" y1="76" x2="222" y2="76" class="wa-line-lit"/>
      </svg>`;
    case "brain":
      return `<svg viewBox="0 0 260 150">
        <circle cx="130" cy="72" r="34" class="wa-core"/>
        <text x="130" y="77" class="wa-core-t">FRAMEWORK</text>
        ${["Registry", "Lifecycle", "Budget", "Council"].map((l, i) => {
          const a = (-135 + i * 90) * Math.PI / 180;
          const x = 130 + 92 * Math.cos(a), y = 72 + 52 * Math.sin(a);
          return `<line x1="${130 + 34 * Math.cos(a)}" y1="${72 + 34 * Math.sin(a)}"
                        x2="${x}" y2="${y}" class="wa-spoke"/>
                  <text x="${x}" y="${y + 4}" class="wa-spoke-t"
                        text-anchor="${x < 130 ? "end" : "start"}">${l}</text>`;
        }).join("")}
      </svg>`;
    case "blocked":
      return `<svg viewBox="0 0 260 150">
        ${box(18, 30, 62, 44, "wa-empty")}
        ${box(18, 84, 62, 44, "wa-empty")}
        ${box(98, 30, 62, 44, "wa-empty")}
        <text x="49" y="57" class="wa-q">?</text>
        <text x="49" y="111" class="wa-q">?</text>
        <text x="129" y="57" class="wa-q">?</text>
        <circle cx="205" cy="72" r="30" class="wa-void"/>
        <line x1="188" y1="55" x2="222" y2="89" class="wa-strike"/>
      </svg>`;
    case "lock":
      return `<svg viewBox="0 0 260 150">
        ${box(30, 24, 96, 100, "wa-paper")}
        <text x="78" y="80" class="wa-tick">✓</text>
        ${box(150, 24, 88, 30, "wa-locked")}
        ${box(150, 60, 88, 30, "wa-locked")}
        ${box(150, 96, 88, 28, "wa-locked")}
        <text x="194" y="44" class="wa-lock-t">closed</text>
        <text x="194" y="80" class="wa-lock-t">closed</text>
        <text x="194" y="115" class="wa-lock-t">closed</text>
      </svg>`;
    case "paths":
      return `<svg viewBox="0 0 260 150">
        ${box(16, 20, 100, 46, "wa-screen")}
        <text x="66" y="48" class="wa-opt">Upload yours</text>
        ${box(16, 84, 100, 46, "wa-screen")}
        <text x="66" y="112" class="wa-opt">Start from reference</text>
        <path d="M124 43 L168 66" class="wa-arrow"/>
        <path d="M124 107 L168 78" class="wa-arrow"/>
        <circle cx="204" cy="72" r="30" class="wa-core"/>
        <text x="204" y="77" class="wa-core-t">YOURS</text>
      </svg>`;
    default:
      return `<svg viewBox="0 0 260 150">
        ${box(16, 52, 70, 42, "wa-screen")}
        <text x="51" y="78" class="wa-opt">A figure</text>
        <path d="M94 73 L132 73" class="wa-arrow"/>
        ${box(140, 52, 46, 42, "wa-paper")}
        <path d="M194 73 L216 73" class="wa-arrow"/>
        <text x="228" y="78" class="wa-sig">§</text>
      </svg>`;
  }
}

/* -------------------------------------------------------------------- render */

function welcomeSegment() {
  let seg = WELCOME_SEGMENTS[0];
  for (const s of WELCOME_SEGMENTS) if (WEL.t >= s.at) seg = s;
  return seg;
}

function drawWelcome() {
  const host = document.getElementById("welcome");
  const seg = welcomeSegment();
  const index = WELCOME_SEGMENTS.indexOf(seg);
  const pct = Math.min(100, (WEL.t / WELCOME_TOTAL) * 100);
  const left = Math.max(0, WELCOME_TOTAL - Math.floor(WEL.t));

  host.innerHTML = `
    <div class="wel-card" role="dialog" aria-modal="true"
         aria-labelledby="welTitle">
      <div class="wel-art" aria-hidden="true">${welcomeArt(seg.art)}</div>
      <div class="wel-body">
        <p class="wel-kicker">${welEsc(seg.kicker)}</p>
        <h2 id="welTitle">${welEsc(seg.title)}</h2>
        <p class="wel-text">${welEsc(seg.body)}</p>
      </div>
      <div class="wel-foot">
        <div class="wel-dots">
          ${WELCOME_SEGMENTS.map((_, i) =>
            `<i class="${i === index ? "on" : ""}"></i>`).join("")}
        </div>
        <div class="wel-bar"><span style="width:${pct}%"></span></div>
        <div class="wel-actions">
          <button class="btn ghost" id="welPlay" type="button">${
            WEL.playing ? "Pause" : "Play"}</button>
          <button class="btn ghost" id="welSkip" type="button">Skip</button>
          <button class="btn" id="welGo" type="button">${
            left > 0 ? `Continue &nbsp;<small>${left}s</small>` : "Continue"}</button>
        </div>
      </div>
    </div>`;

  document.getElementById("welPlay").onclick = () =>
    WEL.playing ? pauseWelcome() : playWelcome();
  document.getElementById("welSkip").onclick = () => endWelcome();
  document.getElementById("welGo").onclick = () => endWelcome();
}

/* --------------------------------------------------------------- transport */

function playWelcome() {
  if (WEL.timer) clearInterval(WEL.timer);
  WEL.playing = true;
  WEL.timer = setInterval(() => {
    WEL.t += 0.5;
    if (WEL.t >= WELCOME_TOTAL) {
      WEL.t = WELCOME_TOTAL;
      pauseWelcome();
    }
    drawWelcome();
  }, 500);
  drawWelcome();
}

function pauseWelcome() {
  WEL.playing = false;
  if (WEL.timer) { clearInterval(WEL.timer); WEL.timer = null; }
  drawWelcome();
}

function endWelcome() {
  pauseWelcome();
  const host = document.getElementById("welcome");
  host.hidden = true;
  host.innerHTML = "";
  document.body.classList.remove("welcome-open");
  try { localStorage.setItem(WELCOME_SEEN, "1"); } catch (e) {}
  if (typeof WEL.onDone === "function") { const f = WEL.onDone; WEL.onDone = null; f(); }
}

/** Show it. `onDone` runs whether they watched it or skipped. */
function startWelcome(onDone) {
  WEL.t = 0;
  WEL.onDone = onDone || null;
  const host = document.getElementById("welcome");
  host.hidden = false;
  document.body.classList.add("welcome-open");
  drawWelcome();
  playWelcome();
}

document.addEventListener("keydown", (e) => {
  const host = document.getElementById("welcome");
  if (!host || host.hidden) return;
  if (e.key === "Escape") { e.preventDefault(); endWelcome(); }
  else if (e.key === " ") {
    e.preventDefault();
    WEL.playing ? pauseWelcome() : playWelcome();
  }
});

window.startWelcome = startWelcome;
window.welcomeSeen = () => {
  try { return localStorage.getItem(WELCOME_SEEN) === "1"; }
  catch (e) { return true; }
};
/** So it can be watched again from inside the app. */
window.replayWelcome = () => startWelcome(null);
