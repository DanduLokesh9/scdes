/* Voice navigation — say where you want to go.

   "Open the framework." "Take me to the audit trail." "Show me who decides."

   Runs entirely on this machine. Chrome ships `webkitSpeechRecognition`, which
   is two lines and sends the audio to Google; a user two screens earlier signed
   a confidentiality agreement covering these materials, and a microphone in an
   open-plan office picks up more than the command. So the same Whisper model
   that was here for dictation stays, transcribing locally, and only the *use*
   has changed: the transcript is matched against the places you can go rather
   than typed into a box.

   Three rules, and the first is the one that matters
   --------------------------------------------------

   **It always says what it heard.** A voice control that acts silently is a
   voice control you cannot trust, because the failure mode is not "nothing
   happened" — it is "something else happened". Every command shows the
   transcript and the destination before it moves.

   **It refuses rather than guesses.** Two destinations scoring close together
   means the command was ambiguous, and going to the wrong screen is worse than
   going nowhere. Below the threshold it lists what it can do instead.

   **It respects the locks.** Saying "registry" when the registry is behind the
   subscription says so. Voice is a faster way to reach what you already have,
   never a way round a gate. */

const VOICE = {
  base: "/assets/speech",
  ready: false,
  loading: null,
  pipe: null,
  recorder: null,
  chunks: [],
};

/* Held back, not removed.

   Voice navigation works and is staying in the build, but it is not on show:
   there is no switch in the interface and no microphone in the header unless
   somebody deliberately turns it on. Nothing is downloaded either — the 60 MB
   is fetched on first use, and first use cannot happen by accident.

   To try it:  add ?voice=1 to the address, once. It sticks.
   To put it away again:  ?voice=0

   Same pattern as ?tester= in onboard.js, and for the same reason: a thing that
   is finished but not yet ready to be seen needs a way in for the people
   evaluating it and no way in for anyone else. */
function voiceOn() {
  try { return localStorage.getItem("scdes.voice") === "1"; }
  catch (e) { return false; }
}

(function readVoiceParam() {
  const asked = new URLSearchParams(location.search).get("voice");
  if (asked === null) return;
  try { localStorage.setItem("scdes.voice", asked === "0" ? "0" : "1"); }
  catch (e) {}
  // Drop the query so a shared link does not carry it, and so a refresh does
  // not keep re-applying something the person may have since turned off.
  history.replaceState(null, "", location.pathname + location.hash);
})();

function setVoice(on) {
  try { localStorage.setItem("scdes.voice", on ? "1" : "0"); } catch (e) {}
  paintVoiceChip();
}

function voiceSupported() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia
            && window.WebAssembly && window.MediaRecorder);
}

/* ---------------------------------------------------------- where you can go

   Read off the rail rather than kept as a second list here — the rail is where
   a human decides what exists and what it is called, and a duplicate set in
   JavaScript is a thing that drifts. The synonyms are what people actually say
   out loud, which is rarely the label: nobody asks for "workflow", they ask for
   the lifecycle or the gates. */
const VOICE_SYNONYMS = {
  home: ["home", "welcome", "start", "the lifecycle overview", "seven steps",
         "seven step", "overview", "front page"],
  framework: ["framework", "the framework", "builder", "framework builder",
              "questions", "build the framework", "sections"],
  agency: ["agency profile", "profile", "my agency", "the agency"],
  vision: ["vision", "the vision", "roadmap", "where we are going"],
  registry: ["registry", "the registry", "systems", "system registry",
             "inventory", "projects"],
  workflow: ["lifecycle", "the lifecycle", "gates", "gate review", "workflow",
             "stages"],
  budget: ["budget", "the budget", "money", "cost", "costs", "spend"],
  oversight: ["oversight", "incidents", "monitoring", "drift"],
  process: ["process", "the process", "decision levels", "risk bands"],
  setup: ["terminology", "vocabulary", "naming", "terms", "wording"],
  configure: ["configure", "configuration", "parameters", "settings",
              "risk model", "thresholds", "appendices"],
  council: ["council", "who decides", "decisions", "leadership", "authority",
            "the decider"],
  integrity: ["integrity", "corpus integrity", "findings"],
  audit: ["audit", "audit trail", "the log", "the record", "history"],
};

/* Reachable, but not in the rail.

   Terminology, Configure and who-decides were taken out of the sidebar because
   they are steps inside the framework rather than places to visit. They are
   still real screens, and someone who says "terminology" means it — so voice
   knows about them even though nothing lists them. Being able to ask for
   something you cannot see is the one thing voice is genuinely better at. */
const VOICE_UNLISTED = [
  { view: "setup", label: "Terminology" },
  { view: "configure", label: "Configure" },
  { view: "council", label: "Who decides" },
];

/* The name of a room, without the sidebar's furniture.

   `textContent` on a rail button picks up the icon glyph and the status tag
   along with the words, so messages read "⛓Audit trail needs a subscription"
   and "Framework DRAFT". Both are the button's contents; neither is the name of
   the place. */
function railLabel(button) {
  return [...button.childNodes]
    .filter((n) => n.nodeType === 3 ||
                   (n.nodeType === 1 && !["I", "SPAN"].includes(n.tagName)))
    .map((n) => n.textContent)
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Every destination, with its live/locked state. */
function voiceDestinations() {
  const rail = [...document.querySelectorAll(".rail-item[data-view]")].map((b) => ({
    view: b.dataset.view,
    label: railLabel(b),
    locked: b.disabled,
    say: VOICE_SYNONYMS[b.dataset.view] || [b.dataset.view],
  }));
  const seen = new Set(rail.map((d) => d.view));
  const extra = VOICE_UNLISTED
    .filter((d) => !seen.has(d.view))
    .map((d) => ({ ...d, locked: false,
                   say: VOICE_SYNONYMS[d.view] || [d.view] }));
  return rail.concat(extra);
}

/* -------------------------------------------------------------- matching */

const voiceWords = (s) =>
  String(s || "").toLowerCase().replace(/[^a-z\s]/g, " ").split(/\s+/)
    .filter(Boolean);

/* Filler that carries no destination. Stripped so "take me to the audit trail"
   and "audit trail" score the same — otherwise a politely-phrased command
   scores worse than a curt one. */
const VOICE_FILLER = new Set([
  "go", "to", "the", "a", "an", "open", "show", "me", "take", "please", "can",
  "you", "i", "want", "would", "like", "see", "view", "screen", "page", "let",
  "us", "lets", "now", "and", "then", "of", "my", "our", "for", "on", "in",
]);

/** Best destination for what was said, or null when it is not clear enough. */
function matchDestination(said) {
  const words = voiceWords(said).filter((w) => !VOICE_FILLER.has(w));
  if (!words.length) return null;
  const heard = words.join(" ");

  const scored = voiceDestinations().map((d) => {
    let best = 0;
    for (const phrase of d.say) {
      const target = voiceWords(phrase).filter((w) => !VOICE_FILLER.has(w));
      if (!target.length) continue;
      const hits = target.filter((w) => words.includes(w)).length;
      if (!hits) continue;
      // Proportion of the phrase that was said, with an exact-substring bonus:
      // "audit trail" beats "audit" for the same destination, and "budget"
      // does not beat "audit trail" just by being one short word.
      let score = hits / target.length;
      if (heard.includes(target.join(" "))) score += 0.35;
      best = Math.max(best, score);
    }
    return { ...d, score: best };
  }).filter((d) => d.score > 0).sort((a, b) => b.score - a.score);

  if (!scored.length) return null;
  const [first, second] = scored;
  // Too weak, or too close to call. Going to the wrong screen is worse than
  // going nowhere, and "did you mean" for fifteen destinations is a menu.
  if (first.score < 0.5) return null;
  if (second && first.score - second.score < 0.15) return null;
  return first;
}

/* ------------------------------------------------------------- the engine */

function loadVoiceEngine(onProgress) {
  if (VOICE.ready) return Promise.resolve(VOICE.pipe);
  if (VOICE.loading) return VOICE.loading;

  VOICE.loading = (async () => {
    const { pipeline, env } = await import(`${VOICE.base}/transformers.min.js`);
    // Everything from this origin. `allowRemoteModels = false` is what makes
    // "nothing leaves the machine" a guarantee rather than an intention: a
    // missing file fails loudly instead of quietly fetching from Hugging Face.
    env.allowRemoteModels = false;
    env.allowLocalModels = true;
    env.localModelPath = `${VOICE.base}/models/`;
    env.backends.onnx.wasm.wasmPaths = `${VOICE.base}/ort/`;
    env.backends.onnx.wasm.numThreads = 1;

    VOICE.pipe = await pipeline(
      "automatic-speech-recognition", "Xenova/whisper-tiny.en",
      { quantized: true, progress_callback: onProgress });
    VOICE.ready = true;
    return VOICE.pipe;
  })();
  VOICE.loading.catch(() => { VOICE.loading = null; });
  return VOICE.loading;
}

/* ------------------------------------------------------------- listening */

async function startVoice() {
  const chip = document.getElementById("voiceChip");
  const say = (m, kind) => showVoiceStatus(m, kind);

  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    say(e && e.name === "NotAllowedError"
      ? "Microphone access was declined. Allow it in the address bar."
      : "No microphone was available.", "bad");
    return;
  }

  say("Preparing — about 60 MB, once.");
  try {
    await loadVoiceEngine((p) => {
      if (p && p.status === "progress" && p.total) {
        say(`Preparing — ${Math.round(p.progress)}% of `
            + `${Math.round(p.total / 1024 / 1024)} MB.`);
      }
    });
  } catch (e) {
    stream.getTracks().forEach((t) => t.stop());
    say("Voice could not start on this browser.", "bad");
    return;
  }

  VOICE.chunks = [];
  VOICE.recorder = new MediaRecorder(stream);
  VOICE.recorder.ondataavailable = (e) => {
    if (e.data && e.data.size) VOICE.chunks.push(e.data);
  };
  VOICE.recorder.onstop = async () => {
    stream.getTracks().forEach((t) => t.stop());
    if (chip) chip.classList.remove("on");
    say("Listening…");
    let said = "";
    try {
      said = await transcribeVoice(VOICE.chunks);
    } catch (e) {
      say("Could not make that out.", "bad");
      return;
    }
    handleCommand(said);
  };
  VOICE.recorder.start();
  if (chip) chip.classList.add("on");
  say("Listening — say where you want to go.");

  // Stopped automatically. A command is a few words, and a mic that stays live
  // until you remember to press it again is a mic that stays live.
  setTimeout(() => stopVoice(), 4000);
}

function stopVoice() {
  if (VOICE.recorder && VOICE.recorder.state === "recording") {
    VOICE.recorder.stop();
  }
  VOICE.recorder = null;
}

async function transcribeVoice(chunks) {
  const blob = new Blob(chunks, { type: "audio/webm" });
  const Ctx = window.AudioContext || window.webkitAudioContext;
  const ctx = new Ctx({ sampleRate: 16000 });
  const audio = await ctx.decodeAudioData(await blob.arrayBuffer());
  const samples = audio.getChannelData(0);
  await ctx.close();
  const out = await VOICE.pipe(samples);
  return ((out && out.text) || "").trim();
}

/* ------------------------------------------------------- acting on it */

function handleCommand(said) {
  if (!said) { showVoiceStatus("Nothing was heard.", "bad"); return; }

  const hit = matchDestination(said);
  if (!hit) {
    // Named, not swallowed. "Nothing happened" and "it misheard you" look
    // identical from the outside, and only one of them is worth repeating.
    const open = voiceDestinations().filter((d) => !d.locked)
      .map((d) => d.label.replace(/DRAFT|LIVE|SET UP|—/g, "").trim());
    showVoiceStatus(`Heard "${said}" — no match. Try: ${open.join(", ")}.`,
                    "bad");
    return;
  }

  if (hit.locked) {
    showVoiceStatus(`Heard "${said}" — ${hit.label} needs a subscription.`,
                    "bad");
    return;
  }

  showVoiceStatus(`Heard "${said}" → ${hit.label}`, "ok");
  if (window.go) window.go(hit.view);
}

/* ------------------------------------------------------------------ the UI */

function showVoiceStatus(message, kind) {
  let box = document.getElementById("voiceStatus");
  if (!box) {
    box = document.createElement("div");
    box.id = "voiceStatus";
    box.className = "voice-status";
    box.setAttribute("role", "status");
    document.body.appendChild(box);
  }
  box.textContent = message;
  box.className = "voice-status show" + (kind ? " " + kind : "");
  clearTimeout(box._t);
  // Long enough to read a transcript, which is the point of showing it.
  box._t = setTimeout(() => { box.className = "voice-status"; }, 5200);
}

function paintVoiceChip() {
  const chip = document.getElementById("voiceChip");
  if (!chip) return;
  // Hidden outright unless switched on, rather than dimmed. A greyed control
  // is an invitation to ask what it does; an absent one is not there.
  const on = voiceOn() && voiceSupported();
  chip.hidden = !on;
  chip.classList.toggle("off", false);
  chip.title = "Say where you want to go";
  chip.setAttribute("aria-label", chip.title);
}

function initVoice() {
  const chip = document.getElementById("voiceChip");
  if (!chip) return;
  paintVoiceChip();
  chip.onclick = () => {
    if (!voiceOn()) return;            // the chip is not shown in that case
    if (VOICE.recorder) { stopVoice(); return; }
    startVoice();
  };
}

window.initVoice = initVoice;
window.voiceOn = voiceOn;
window.setVoice = setVoice;
window.voiceSupported = voiceSupported;
window.matchDestination = matchDestination;      // for the checks
