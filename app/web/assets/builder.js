/* The Framework Builder — the click-through that writes an agency's framework.

   The Framework screen used to describe what was in the corpus folder: four
   layers, which files were present, whether an adoption had been recorded. That
   is a status page. It is useful once you already have a framework and useless
   on the day you are trying to write one, which is the day almost every agency
   will be on.

   So this is the screen now: Module One, from app/module_one.py — ten steps
   plus orientation and assembly, taking somebody with no AI background from a
   blank page to an adopted framework in their own words.

   It replaced a version that rendered a register mined from SCDES's own
   framework document and quoted the SCDES sentence above every question. That
   was built as a virtue — "someone answering deserves to see what in the
   document they are being asked about" — and it was the client's hardest rule
   broken in the most direct way available: *do not reference other agencies,
   users, or frameworks*. Nothing here quotes anybody else, and there is no
   field that could.

   Four rules from the spec that this screen exists to honour:

   · **Nothing is ever disabled.** A recommended-against answer gets one line of
     consequence and is then accepted. "The moment the module refuses
     something, it becomes someone else's framework."

   · **"We don't know" is always available**, and produces a named gap with an
     owner rather than a blank.

   · **The offices you do not have are never mentioned again.** Answering 1.4
     removes them from every later list — see `fbAfterAnswer`.

   · **Show the document building.** A persistent panel of which parts of the
     framework are filling in, so this reads as progress toward something real
     rather than a form.

   Answering writes to the working draft and moves no version number. Cutting a
   version is a separate, deliberate act — see app/versions.py. */

const FB = { data: null, answers: {}, versions: null, open: null };

const fbEsc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* Its own helpers, not app.js's.

   The first version called `el`, `api`, `post`, `$`, `go` and `reason`
   directly. Those are `const` declarations at the top level of app.js — global
   *lexical* bindings, which two classic scripts do share in a browser, so it
   worked there and threw "el is not defined" the moment anything evaluated the
   files independently. Depending on that is depending on load order and on one
   particular way of running the page.

   The DOM and fetch helpers are duplicated here because they are four lines
   each. The genuinely shared ones — navigation, the reason rail, toasts — are
   read off `window` at call time, so a missing one degrades rather than
   throws. */
const fbEl = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const fbGet = (sel) => document.querySelector(sel);

/* Its own fetch, not app.js's — this module is a separate script and must not
   depend on sharing app.js's lexical scope.

   It has to carry the same four things app.js's `api()` carries, and for a
   while it carried only the first. The capacity went, and the address did not,
   so every request from the builder reached the server with no way to tell
   which agency it came from. Since agencies were separated that resolves to
   "unidentified", which has its own directory — so the framework builder, the
   one free thing in the product, was reading and writing answers into a
   dead-end bucket instead of the agency's own. It looked like it worked: you
   could answer a question, see it saved, and find it again, because the
   dead-end was consistent with itself. */
/* Not `fbWho` — this file already has one of those, for which reviewer group a
   row belongs to. Two function declarations of the same name in one script is
   not an error, it is a silent replacement: the second won, and `fbApi` began
   calling the row version with no row. */
function fbEmail() {
  try {
    return (JSON.parse(localStorage.getItem("scdes.registration") || "{}")
            || {}).email || "";
  } catch (e) { return ""; }
}

async function fbApi(path, opts = {}) {
  const user = window.SCDES_USER || "sean.ot";
  const sep = path.includes("?") ? "&" : "?";
  const headers = { "Content-Type": "application/json",
                    "X-SCDES-User": user,
                    // Where this person is; see app/clock.py.
                    "X-GAIUS-UTC-Offset": String(-new Date().getTimezoneOffset()) };
  if (window.SCDES_NAME) headers["X-SCDES-Name"] = window.SCDES_NAME;
  if (window.SCDES_TITLE) headers["X-SCDES-Title"] = window.SCDES_TITLE;
  const email = fbEmail();
  if (email) headers["X-SCDES-Email"] = email;
  try {
    const token = localStorage.getItem("scdes.session");
    if (token) headers["X-GAIUS-Session"] = token;
  } catch (e) {}
  const query = "user=" + encodeURIComponent(user)
    + (email ? "&email=" + encodeURIComponent(email) : "");
  const r = await fetch(path + sep + query, { headers, ...opts });
  return r.json();
}

const fbPost = (path, body) =>
  fbApi(path, { method: "POST", body: JSON.stringify(body) });

const fbGo = (view) => window.go && window.go(view);
const fbReason = (blocks) => window.reason && window.reason(blocks);
const fbToast = (m, bad) => window.toast && window.toast(m, bad);

/* ------------------------------------------------------------------ loading */

async function fbLoad() {
  const [mod, ver, intake] = await Promise.all([
    fbApi("/api/module"),
    fbApi("/api/versions"),
    fbApi("/api/intake"),
  ]);
  FB.data = mod;
  FB.versions = ver;
  FB.intake = intake;
  // The raw answers, kept as stored. Some are a bare value and some are a
  // record carrying the owner of a gap or the detail a "yes" opened up, so the
  // shape is preserved rather than flattened — flattening lost the owner, which
  // is the one thing that makes a gap auditable.
  FB.answers = { ...((ver && ver.working) || {}) };
  return mod;
}

/* An answer is wrapped twice, and each wrapper does a different job: the
   versions store records who answered and when, and the endpoint records the
   owner of a gap or the detail a "yes" opened up. Unwrapping one level returned
   the inner record where a value was expected, so a "we don't know" never read
   back as one and the owner field came up empty on reload. Mirrors
   `module_one._unwrap`. */
function fbUnwrap(raw) {
  const extras = {};
  let depth = 0;
  while (raw && typeof raw === "object" && !Array.isArray(raw)
         && "value" in raw && depth < 4) {
    for (const name of ["owner", "detail", "from_document"]) {
      if (raw[name]) extras[name] = raw[name];
    }
    raw = raw.value;
    depth += 1;
  }
  return { value: raw, extras };
}

function fbValue(key) {
  return fbUnwrap(FB.answers[key]).value;
}

function fbExtra(key, field) {
  return fbUnwrap(FB.answers[key]).extras[field] || "";
}

function fbIsAnswered(key) {
  const v = fbValue(key);
  if (v === undefined || v === null) return false;
  if (Array.isArray(v)) return v.length > 0;
  if (typeof v === "object") return Object.keys(v).length > 0;
  return String(v).trim() !== "";
}

function fbTotals() {
  return (FB.data && FB.data.totals) || { questions: 0, answered: 0 };
}

/* ------------------------------------------------------------------ the view */

async function renderBuilder(root) {
  await fbLoad();
  const t = fbTotals();
  const total = t.questions;
  const done = t.answered;
  const v = FB.versions || {};

  const head = fbEl("div", "panel");
  head.innerHTML = `
    <div class="spread">
      <div>
        <h2 class="sub3" style="margin-top:0">${fbEsc(FB.data.title || "")}</h2>
        <p class="intro" style="margin:0">${fbEsc(FB.data.blurb || "")}</p>
      </div>
      <div class="fb-count"><b>${done}</b><span>of ${total} answered</span></div>
    </div>
    <div class="fb-bar"><i style="width:${
      total ? Math.round((done / total) * 100) : 0}%"></i></div>
    <p class="small muted" style="margin-top:10px">
      ${fbEsc(v.export_label || "Nothing saved yet")}${
        v.unsaved ? ` · ${v.unsaved} unsaved change(s)` : ""}</p>`;
  root.appendChild(head);

  root.appendChild(fbIntakePanel());

  root.appendChild(fbDocumentBuilding());

  const list = fbEl("div", "panel");
  list.innerHTML = `<h2 class="sub3" style="margin-top:0">The steps</h2>`;

  (FB.data.steps || []).forEach((s) => {
    const complete = s.asks && s.question_count > 0
      && s.answered === s.question_count;
    const item = fbEl("button", "fb-section" + (complete ? " done" : ""));
    item.type = "button";
    item.innerHTML = `
      <span class="fb-no">${fbEsc(s.number)}</span>
      <span class="fb-main">
        <span class="fb-title">${fbEsc(s.title)}</span>
        <span class="fb-purpose">${fbEsc(s.strapline)}</span>
      </span>
      <span class="fb-state">${
        !s.asks ? `<em>read this first</em>`
        : complete ? `<b class="ok">complete</b>`
        : `${s.answered} / ${s.question_count}`}</span>`;
    item.onclick = () => openStep(s.number);
    list.appendChild(item);
  });

  /* The steps still to build, shown rather than hidden.
     A path you can see the end of is worth the greyed rows. */
  (FB.data.pending || []).forEach((s) => {
    const item = fbEl("div", "fb-section pending");
    item.innerHTML = `
      <span class="fb-no">${fbEsc(s.number)}</span>
      <span class="fb-main">
        <span class="fb-title">${fbEsc(s.title)}</span>
        <span class="fb-purpose">${fbEsc(s.writes)}</span>
      </span>
      <span class="fb-state"><em>not yet available</em></span>`;
    list.appendChild(item);
  });

  const built = FB.data.totals || {};
  if (built.steps_total > built.steps_built) {
    list.appendChild(fbEl("p", "small muted",
      `Steps ${built.steps_built} of ${built.steps_total} are ready to answer.
       The rest are listed so you can see the whole path before you start.`));
  }
  root.appendChild(list);
  root.appendChild(fbVersionPanel());
  root.appendChild(fbYourContentPanel());
}

/* Which parts of the framework are filling in.

   "Show the document building. A persistent indicator of which sections are
   filling in as they go. It converts a form into visible progress toward
   something real." — and it is the difference between answering a form and
   watching a document appear. Assembled from what each answered question
   declares it writes, so it cannot drift from the questions. */
function fbDocumentBuilding() {
  const filling = {};
  (FB.data.steps || []).forEach((s) => {
    (s.questions || []).forEach((q) => {
      (q.writes || []).forEach((part) => {
        filling[part] = filling[part] || { total: 0, done: 0 };
        filling[part].total += 1;
        if (fbIsAnswered(q.key)) filling[part].done += 1;
      });
    });
  });

  const parts = Object.entries(filling).sort((a, b) => b[1].total - a[1].total);
  const box = fbEl("div", "panel");
  box.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Your document, so far</h2>
    <p class="intro">These are the parts of your framework. They fill in as you
      answer — nothing here is written for you.</p>
    <div class="fb-parts">${parts.map(([name, n]) => `
      <span class="fb-part${n.done ? (n.done === n.total ? " full" : " part")
        : ""}">${fbEsc(name)}<i>${n.done}/${n.total}</i></span>`).join("")}</div>`;
  return box;
}

/* What the agency already has.

   Placed above the sections, because it changes what the sections ask. An
   agency with an acceptable use policy and a data governance standard in effect
   should not be retyping what is already written down — every question is
   checked against these, and where a passage answers one it is offered with the
   file it came from.

   Nothing is answered automatically. The matching is lexical and will sometimes
   be wrong, so a suggestion arrives quoted and attributed, and a person
   confirms it. A wrong suggestion you can see is recoverable; a wrong answer
   absorbed into the document is not. */
function fbIntakePanel() {
  const info = FB.intake || {};
  const docs = info.documents || [];
  const box = fbEl("div", "panel fb-intake");
  box.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Start with what you already have</h2>
    <p class="intro">${fbEsc(info.why || "")}</p>
    <p class="small muted">${fbEsc(info.how || "")}</p>

    ${docs.length ? `<div class="fb-docs">${docs.map((d) => `
      <div class="fb-doc">
        <span class="fb-doc-icon" aria-hidden="true">▤</span>
        <span class="fb-doc-main">
          <b>${fbEsc(d.file)}</b>
          <span>${fbEsc(d.kind || d.type)} · ${
            (d.words || 0).toLocaleString()} words · uploaded by ${
            fbEsc(d.uploaded_by || "")}</span>
        </span>
        <button class="btn ghost" data-drop="${fbEsc(d.file)}"
                type="button">Remove</button>
      </div>`).join("")}</div>` : ""}

    ${info.can_upload ? `
      <div class="fb-upload">
        <label class="small"><b>Add a policy or standard</b></label>
        <div class="row" style="margin-top:8px">
          <input id="fbKind" type="text" placeholder="What is it? e.g. Acceptable use policy"
                 style="flex:1;min-width:220px">
          <input id="fbFile" type="file"
                 accept=".docx,.pdf,.txt,.md">
        </div>
        <p class="small muted" style="margin-top:8px">
          ${fbEsc((info.accepts || []).join(", "))} · up to ${
            fbEsc(String(info.max_mb || 12))} MB.
          Your originals stay yours; nothing is published.</p>
        <p class="signin-error" id="fbUpErr" hidden></p>
        <p class="fb-saved" id="fbUpOk" hidden></p>
      </div>` : `
      <div class="locked" style="margin-top:12px">Uploading is the Office of
        Technology's to do.</div>`}`;

  setTimeout(() => {
    const file = document.getElementById("fbFile");
    if (file) file.onchange = async () => {
      const chosen = file.files && file.files[0];
      if (!chosen) return;
      const err = document.getElementById("fbUpErr");
      const ok = document.getElementById("fbUpOk");
      err.hidden = true; ok.hidden = true;
      ok.textContent = `Reading ${chosen.name}…`;
      ok.hidden = false;

      // Base64 inside the JSON body: this server is a stdlib JSON router, and a
      // multipart parser for one screen is more to get wrong than it is worth.
      const buffer = await chosen.arrayBuffer();
      let binary = "";
      const bytes = new Uint8Array(buffer);
      for (let i = 0; i < bytes.length; i += 8192) {
        binary += String.fromCharCode.apply(
          null, bytes.subarray(i, i + 8192));
      }
      const r = await fbPost("/api/intake/upload", {
        filename: chosen.name,
        kind: (document.getElementById("fbKind") || {}).value || "",
        content: btoa(binary),
      });
      if (!r.ok) {
        ok.hidden = true;
        err.textContent = r.error || "Could not read that file.";
        err.hidden = false;
        return;
      }
      if (!r.readable) {
        ok.hidden = true;
        err.textContent = r.note;
        err.hidden = false;
        return;
      }
      fbToast(`${r.file} read — ${r.paragraphs} passages indexed.`);
      fbGo("framework");
    };

    document.querySelectorAll("[data-drop]").forEach((b) => {
      b.onclick = async () => {
        await fbPost("/api/intake/remove", { filename: b.dataset.drop });
        fbToast(`${b.dataset.drop} removed.`);
        fbGo("framework");
      };
    });
  }, 0);
  return box;
}

/* ================================================================ one step */

async function openStep(number) {
  const step = await fbApi("/api/module?step=" + encodeURIComponent(number));
  FB.open = number;

  /* The read-back has to be of what they actually said, right now. `FB.data`
     is only refreshed when an answer changes a later *question*, and most
     answers do not — so arriving at the assembly step showed a review built
     from whatever the summary happened to hold when the page loaded, with
     contradictions and gaps from several answers ago. */
  if (number === "—") FB.data = await fbApi("/api/module");
  const root = fbEl("div");

  const head = fbEl("div", "panel");
  head.innerHTML = `
    <button class="btn ghost" id="fbBack" type="button">← All steps</button>
    <h2 class="sub3">${fbEsc(step.number)} — ${fbEsc(step.title)}</h2>
    <p class="fb-strap">${fbEsc(step.strapline)}
      <span>writes ${fbEsc(step.writes)}</span></p>
    ${(step.opening || []).map((p) =>
      `<p class="intro">${fbEsc(p)}</p>`).join("")}`;
  root.appendChild(head);

  /* Step 06 arrives in eight blocks — "each is presented the same way: the
     rule in plain words, one line on why it exists, then the choices that
     genuinely are theirs". Every other step has no groups and falls straight
     through to the flat list. */
  const groups = step.groups || [];
  if (groups.length) {
    groups.forEach((g) => {
      root.appendChild(fbGroupHead(g));
      (step.questions || []).filter((q) => q.group === g.key)
        .forEach((q) => root.appendChild(fbQuestion(q)));
    });
    // Anything the server sent that claims no block still gets shown.
    (step.questions || []).filter((q) => !groups.some((g) => g.key === q.group))
      .forEach((q) => root.appendChild(fbQuestion(q)));
  } else {
    (step.questions || []).forEach((q) => root.appendChild(fbQuestion(q)));
  }

  /* The assembly step reads the whole thing back before anything is signed.
     Placed above the four remaining fields, because "which of these two
     answers wins" has to be settled before "who signs it". */
  if (step.number === "—") root.appendChild(fbReview());

  if (step.own_words) root.appendChild(fbOwnWords(step.own_words));
  if (step.closing) root.appendChild(fbClosing(step.closing));

  /* Orientation asks nothing, so it needs a way onward that is not "answer
     something". Without this the first screen of the module is a dead end. */
  const foot = fbEl("div", "panel");
  const next = fbNextStep(step.number);
  /* "Wanted to go back to 03, but only can go forward. Add a 'Return to __'
     or 'Back' button to the left of Continue to ___." His words, and his
     placement — the module is explicit that people should be able to go back
     and change an answer without losing later work. */
  const previous = fbPreviousStep(step.number);
  foot.innerHTML = `
    <div class="row">
      ${previous ? `<button class="btn ghost" id="fbPrev" type="button">
        ← Back to ${fbEsc(previous.number)} — ${fbEsc(previous.title)}</button>`
      : ""}
      ${next ? `<button class="btn" id="fbNext" type="button">
        Continue to ${fbEsc(next.number)} — ${fbEsc(next.title)}</button>` : ""}
      <button class="btn ghost" id="fbBack2" type="button">All steps</button>
    </div>
    ${!step.asks ? `<p class="small muted" style="margin-top:10px">Nothing to
      answer here. It is worth three minutes before the questions start.</p>` : ""}`;
  root.appendChild(foot);

  fbGet("#view").innerHTML = "";
  fbGet("#view").appendChild(root);
  fbToTheTop();

  /* Leaving a step accepts what is on it.

     His ticket: "If the pre-checked boxes are not un-selected and re-selected
     (at least once) by the user, it is registering as 'incomplete', but to me
     I answered all of the questions and just accepted the recommendations. If
     the user saves the page and there is an input (even if the input is just
     the pre-selected answer), then that gets logged as answered."

     Quite right, and the progress display was lying because of it. Committed
     on the way out rather than on the way in, deliberately: opening step 05
     should not silently answer five questions nobody has read, but clicking
     Continue past them is a person saying "yes, that". */
  const leave = async (go) => {
    await fbCommitStep(step);
    await go();
  };
  const back = () => { FB.open = null; fbGo("framework"); };
  root.querySelector("#fbBack").onclick = () => leave(async () => back());
  root.querySelector("#fbBack2").onclick = () => leave(async () => back());
  const nextBtn = root.querySelector("#fbNext");
  if (nextBtn) nextBtn.onclick = () => leave(() => openStep(next.number));
  const prevBtn = root.querySelector("#fbPrev");
  if (prevBtn) prevBtn.onclick = () => leave(() => openStep(previous.number));

  (step.questions || []).forEach((q) => wireQuestion(q));
}

/* The rule in plain words, and one line on why it exists.

   The badge says "Required" and means it — the choice underneath is how strict,
   not whether. Saying so out loud is the client's instruction: "The one place
   the module is directive, and it should say so out loud rather than sneaking
   it in." */
function fbGroupHead(group) {
  const box = fbEl("div", "panel fb-floor");
  box.innerHTML = `
    <p class="fb-floor-no">${fbEsc(group.number)}
      ${group.badge ? `<span class="fb-floor-badge${
        /law/i.test(group.badge) ? " law" : ""
      }">${fbEsc(group.badge)}</span>` : ""}</p>
    <h2 class="sub3" style="margin:0">${fbEsc(group.title)}</h2>
    <p class="intro">${fbEsc(group.why)}</p>`;
  return box;
}

/* What comes back, and when. Shown after the questions rather than before,
   because it only means anything once they have answered them. */
function fbClosing(closing) {
  const box = fbEl("div", "panel");
  const t = closing.table || {};
  box.innerHTML = `
    <h2 class="sub3" style="margin-top:0">${fbEsc(closing.title || "")}</h2>
    ${(closing.body || []).map((p) =>
      `<p class="intro">${fbEsc(p)}</p>`).join("")}
    ${(t.rows || []).length ? `<table class="fb-when">
      <thead><tr>${(t.head || []).map((h) =>
        `<th scope="col">${fbEsc(h)}</th>`).join("")}</tr></thead>
      <tbody>${t.rows.map((r) => `<tr>
        <th scope="row">${fbEsc(r[0])}</th>
        ${r.slice(1).map((c) => `<td>${fbEsc(c)}</td>`).join("")}
      </tr>`).join("")}</tbody></table>` : ""}
    ${closing.after ? `<p class="small muted" style="margin-top:12px">${
      fbEsc(closing.after)}</p>` : ""}`;
  return box;
}

/* Their paragraph, on every section that records a decision.

   Deliberately not a question: it is never counted, never required, and never
   interpreted. "Text goes in verbatim." */
function fbOwnWords(own) {
  const box = fbEl("div", "panel fb-mine");
  box.innerHTML = `
    <label class="g-field">
      <span>${fbEsc(own.prompt)}</span>
      <textarea id="mine-${cssKey(own.key)}" rows="3"></textarea>
    </label>
    <p class="small muted">${fbEsc(own.note)}</p>
    <span class="fb-ok" id="mineok-${cssKey(own.key)}" hidden>saved</span>`;
  const field = box.querySelector("textarea");
  field.value = own.value || "";
  field.onchange = async () => {
    const r = await fbPost("/api/versions/answer",
      { key: own.key, value: field.value.trim() });
    if (r && r.ok) {
      const ok = box.querySelector(".fb-ok");
      ok.hidden = false;
      setTimeout(() => { ok.hidden = true; }, 1800);
    }
  };
  return box;
}

/* The whole framework read back, before anybody signs it.

   Four things, in the order the client set them out: what it says, what is
   still unanswered, what disagrees with itself, and how strictly the floor was
   set. Every line traced to the question that produced it, "so nothing appears
   that they can't account for". */
function fbReview() {
  const d = FB.data || {};
  const gaps = d.gaps || [];
  const clashes = d.contradictions || [];
  const floor = d.floor || [];
  const box = fbEl("div", "panel");

  box.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Your framework, read back</h2>
    <p class="intro">Every line here came from an answer you gave. Click any
      section to go back to it.</p>

    ${clashes.length ? `<div class="fb-clash">
      <h3 class="sub4">${clashes.length} answer${
        clashes.length === 1 ? "" : "s"} disagree${
        clashes.length === 1 ? "s" : ""} with ${
        clashes.length === 1 ? "another" : "each other"}</h3>
      <p class="small">Nothing is blocked. These are places where two answers
        cannot both be followed, and somebody has to choose.</p>
      <ul>${clashes.map((c) => `<li>${fbEsc(c.line)}
        <span class="muted">See ${fbEsc((c.at || []).join(", "))}</span>
      </li>`).join("")}</ul>
    </div>` : `<p class="fb-clear">Nothing you answered contradicts anything
      else you answered.</p>`}

    ${gaps.length ? `<div class="fb-gaps">
      <h3 class="sub4">${gaps.length} thing${
        gaps.length === 1 ? "" : "s"} you don't know yet</h3>
      <p class="small">These go into the document as stated gaps with an owner,
        not as blanks.</p>
      <ul>${gaps.map((g) => `<li>
        <b>${fbEsc(g.number)}</b> ${fbEsc(g.question)}
        <span class="${g.needs_owner ? "fb-noowner" : "muted"}">${
          g.needs_owner ? "nobody named yet" : fbEsc(g.owner)}</span>
      </li>`).join("")}</ul>
    </div>` : ""}

    ${floor.length ? `<h3 class="sub4">The floor, as you set it</h3>
    <ul class="fb-floorlist">${floor.map((f) => `<li>
      <span class="fb-tick${f.settled ? " on" : ""}"
            aria-hidden="true">${f.settled ? "✓" : "·"}</span>
      <span><b>${fbEsc(f.title)}</b>
        <i>${f.settled ? "set" : `${f.answered} of ${f.asked} answered`}</i>
        ${f.weakened ? `<em class="fb-weak">Made less strict: ${
          fbEsc(f.weakened_note)}</em>` : ""}</span>
    </li>`).join("")}</ul>` : ""}

    <h3 class="sub4">Section by section</h3>
    <div class="fb-readback">${(d.review || []).map((s) => `
      <section>
        <h4><button type="button" class="linky" data-step="${fbEsc(s.number)}">
          ${fbEsc(s.number)} — ${fbEsc(s.title)}</button>
          <span class="muted">${s.answered} of ${s.asked}</span></h4>
        ${s.rows.filter((r) => r.state === "answered").map((r) => `
          <p><b>${fbEsc(r.prompt)}</b><br>${
            r.lines.map(fbEsc).join("<br>")}</p>`).join("")
          || `<p class="muted">Nothing answered here yet.</p>`}
        ${s.own_words ? `<p class="fb-verbatim">${
          fbEsc(s.own_words)}</p>` : ""}
      </section>`).join("")}</div>`;

  box.querySelectorAll("button[data-step]").forEach((b) => {
    b.onclick = () => openStep(b.dataset.step);
  });
  return box;
}

function fbNextStep(number) {
  const steps = FB.data.steps || [];
  const at = steps.findIndex((s) => s.number === number);
  return at >= 0 && at + 1 < steps.length ? steps[at + 1] : null;
}

function fbPreviousStep(number) {
  const steps = FB.data.steps || [];
  const at = steps.findIndex((s) => s.number === number);
  return at > 0 ? steps[at - 1] : null;
}

/* ------------------------------------------------------------ one question */

function fbQuestion(q) {
  const box = fbEl("div", "panel fb-q" + (fbIsAnswered(q.key) ? " answered" : ""));
  box.dataset.key = q.key;
  const unknown = fbValue(q.key) === "unknown";

  box.innerHTML = `
    ${/* The number sits on the same line as the question it numbers.
          "5.1 — adjust question to be in line with number." It was stacked
          above, which read as a label floating over an unrelated sentence. */""}
    <div class="fb-qhead">
      ${/* The space is not decoration. Without it the heading's text content
            is "5.1How much does each of these matter", which is what a screen
            reader announces — the visual gap is a CSS margin and carries no
            pause. */""}
      <h3 class="fb-ask"><span class="fb-qno">${fbEsc(q.number)}</span> ${
        fbEsc(q.prompt)}</h3>
      ${q.optional ? `<span class="fb-tag">optional</span>` : ""}
      <span class="fb-ok" hidden>saved</span>
    </div>
    ${q.above ? `<p class="intro">${fbEsc(q.above)}</p>` : ""}
    ${/* Context comes before the answers, not after them.

          "The explanatory text about averaging would be better served
          directly below the question and before the answers are displayed.
          This is a context point." Underneath the options it was a footnote
          to a decision already made. */
      q.help ? `<p class="small muted fb-help">${fbEsc(q.help)}</p>` : ""}
    ${fbEvidence(q)}
    ${/* A question that has nothing to ask yet says so, and does not pretend
          to be fillable. "If someone says in 5.2 'We don't know', then 5.3
          cannot be filled out. Gray out boxes, do not allow for editing." */
      q.waiting_on ? `<p class="fb-waiting">${
        fbEsc(q.waiting_on.say)}</p>` : ""}
    <div class="fb-control${q.waiting_on ? " fb-greyed" : ""}"${
      q.waiting_on ? ' aria-disabled="true"' : ""}>${fbControl(q)}</div>
    ${/* A second field on the same question, where he asked two things at
          once — "who writes it, and who approves it". Splitting them into two
          numbered questions would renumber his document. */
      q.also ? `<label class="g-field fb-also">
        <span>${fbEsc(q.also.label)}</span>
        <input type="text" id="also-${cssKey(q.key)}"
               placeholder="${fbEsc(q.also.placeholder || "")}"
               value="${fbEsc(fbExtra(q.key, q.also.key))}"></label>` : ""}
    ${/* Guidance that only appears when it applies. Shown always it is noise;
          shown at the moment they admit the gap it is the advice. */
      q.advice ? `<div class="fb-advice">
        <h4>${fbEsc(q.advice.title)}</h4>
        ${(q.advice.body || []).map((p) =>
          `<p>${fbEsc(p)}</p>`).join("")}
        ${q.advice.close ? `<p class="fb-advice-close">${
          fbEsc(q.advice.close)}</p>` : ""}
      </div>` : ""}
    ${/* On a question with a response set the unknown is one of the choices —
          his own "Not sure" where he wrote one. Only a bare text field needs
          it offered separately, because there is no list to put it in. */
      q.unknown_ok && !(q.options || []).length ? `
      <label class="fb-unknown">
        <input type="checkbox" id="unk-${cssKey(q.key)}"${unknown ? " checked" : ""}>
        <span>${fbEsc(q.unknown_label || "We don't know")}</span>
      </label>` : ""}
    ${q.unknown_ok ? `
      <div class="fb-owner" id="own-${cssKey(q.key)}"${unknown ? "" : " hidden"}>
        <label class="g-field"><span>Who will find out?</span>
          <input type="text" id="ownin-${cssKey(q.key)}"
                 placeholder="A role title"
                 value="${fbEsc(fbExtra(q.key, "owner"))}"></label>
        <p class="small muted">This becomes a named gap in your framework
          rather than a blank. A framework that says where its holes are is
          auditable; one that hides them is not.</p>
      </div>` : ""}
    <p class="fb-consequence" id="csq-${cssKey(q.key)}" hidden></p>
    <p class="signin-error" id="err-${cssKey(q.key)}" hidden></p>`;
  return box;
}

/* What the organization's own uploaded documents appear to say about this
   question. Shown with the file it came from; never filled in on its own.
   "Use this" makes it the answer, recorded with its source. */
function fbEvidence(q) {
  const from = fbExtra(q.key, "from_document");
  const used = from && from.file ? `<p class="fb-from small">Answered from your
    document <b>${fbEsc(from.file)}</b>. Change the answer and it is simply
    yours.</p>` : "";
  const hits = q.evidence || [];
  if (!hits.length) return used;
  const kind = q.kind;
  const id = `ev-${cssKey(q.key)}`;
  return `${used}<section class="fb-evidence" aria-labelledby="${id}">
    <h4 id="${id}">From your documents</h4>
    ${hits.map((e, i) => {
      const s = e.suggest;
      const what = !s ? (["single", "multi"].includes(kind)
          ? `<p class="small muted">It does not clearly point to one of the
              choices below. Read it and choose.</p>`
          : `<p class="small muted">This kind of question is not filled in from
              a passage. Use it to answer below.</p>`)
        : (kind === "short" || kind === "long")
        ? `<button type="button" class="btn ghost" data-use="${i}">Use this
             passage as the answer</button>${s.trimmed ? `<span class="small muted">
             Only the first part fits this answer.</span>` : ""}`
        : `<p class="small">This reads like: <b>${fbEsc(s.labels.join("; "))}</b></p>
           <button type="button" class="btn ghost" data-use="${i}">Use this
             answer</button>`;
      return `<div class="fb-ev">
        <blockquote>${fbEsc(e.quote)}</blockquote>
        <p class="small muted">${fbEsc(e.file)}${e.kind ? ` · ${fbEsc(e.kind)}` : ""}${
          (e.matched || []).length ? ` · shares the words ${fbEsc(e.matched.join(", "))}` : ""}</p>
        ${what}</div>`;
    }).join("")}
    <p class="small muted">Nothing is answered for you. The match looks for your
      own words, not their meaning, so read the passage before you use it.</p>
  </section>`;
}

/* Redraw one question after it was answered from a passage, so its choices
   show the new answer, and keep focus on it. */
async function fbRedrawOne(key) {
  const step = await fbApi("/api/module?step=" + encodeURIComponent(FB.open));
  const q = (step.questions || []).find((x) => x.key === key);
  const old = document.querySelector(`.fb-q[data-key="${key}"]`);
  if (!q || !old) return;
  old.replaceWith(fbQuestion(q));
  wireQuestion(q);
  const head = document.querySelector(`.fb-q[data-key="${key}"] .fb-ask`);
  if (head) { head.setAttribute("tabindex", "-1"); head.focus(); }
}

function fbControl(q) {
  // Dots out, here and in every lookup that pairs with it — see cssKey().
  const key = cssKey(q.key);
  const val = fbValue(q.key);

  if (q.kind === "single") {
    return `<div class="fb-cards">${(q.options || []).map((o) => `
      <label class="fb-card${val === o.value ? " on" : ""}">
        <input type="radio" name="q-${key}" value="${fbEsc(o.value)}"
               ${val === o.value ? "checked" : ""}>
        <span class="fb-card-main">
          <b>${fbEsc(o.label)}</b>
          ${o.value === q.recommended
            ? `<span class="fb-rec">recommended</span>` : ""}
          ${o.note ? `<span class="fb-note">${fbEsc(o.note)}</span>` : ""}
        </span>
      </label>
      ${o.then_text ? `
        <div class="fb-then" data-for="${fbEsc(o.value)}"
             ${val === o.value ? "" : "hidden"}>
          <label class="g-field"><span>${fbEsc(o.then_text)}</span>
            <input type="text" id="det-${key}"
                   value="${fbEsc(fbExtra(q.key, "detail"))}"></label>
          ${o.then_upload ? `
            <div class="g-field fb-then-upload">
              <label for="up-${key}">Or upload the file</label>
              <input type="file" id="up-${key}" accept=".docx,.pdf,.txt,.md"
                     aria-describedby="up-${key}-help">
              <span class="small muted" id="up-${key}-help">Word, PDF, text or
                Markdown, up to 12 MB. It is kept with your organization's own
                documents, and nothing is published.</span>
              <span class="small" id="up-${key}-said" role="status" aria-live="polite"></span>
            </div>` : ""}
        </div>` : ""}`).join("")}</div>`;
  }

  if (q.kind === "multi") {
    // Pre-checked where the spec says the default should already be on, but
    // only until they have answered once — after that their answer wins, empty
    // or not.
    const chosen = Array.isArray(val) ? val
      : (fbIsAnswered(q.key) ? [] : (q.options || [])
          .filter((o) => o.recommended).map((o) => o.value));
    return `<div class="fb-cards">${(q.options || []).map((o) => `
      <label class="fb-card${chosen.includes(o.value) ? " on" : ""}${
        o.exclusive ? " fb-only" : ""}">
        <input type="checkbox" name="q-${key}" value="${fbEsc(o.value)}"
               ${chosen.includes(o.value) ? "checked" : ""}>
        <span class="fb-card-main">
          <b>${fbEsc(o.label)}</b>
          ${o.recommended && o.because
            ? `<span class="fb-because">${fbEsc(o.because)}</span>` : ""}
          ${o.note ? `<span class="fb-note">${fbEsc(o.note)}</span>` : ""}
        </span>
      </label>
      ${/* A multi-select can have a follow-up too. 6.2d is his: "must be
            registered within ___ days" is one of several things that can be
            true at once, and the blank has to be fillable whichever else
            they ticked. */
        o.then_text ? `
        <div class="fb-then" data-for="${fbEsc(o.value)}"
             ${chosen.includes(o.value) ? "" : "hidden"}>
          <label class="g-field"><span>${fbEsc(o.then_text)}</span>
            <input type="text" class="fb-detail"
                   data-for="${fbEsc(o.value)}"
                   value="${fbEsc(fbExtra(q.key, "detail_" + o.value))}">
          </label>
        </div>` : ""}`).join("")}</div>${fbAddYourOwn(q)}`;
  }

  if (q.kind === "matrix") {
    const given = (val && typeof val === "object") ? val : {};
    if (!(q.rows || []).length) {
      return `<p class="small muted">Nothing to answer here — which is a good
        answer.</p>`;
    }
    /* A row can arrive already weighted: for a water district, "it touches
       safety-critical operations" is the factor that matters most, and
       defaulting it low would be a serious miss. Their own answer always wins
       — the pre-set only shows until they touch the row. */
    const pick = (r) => (r.value in given ? given[r.value] : (r.preset || ""));
    // The column count follows the question. It was fixed at five for 1.4, so
    // 5.1's three choices were laid out across five columns' worth of space.
    return `<div class="fb-matrix" style="--mcols:${(q.row_options || []).length}">
      <div class="fb-mrow fb-mhead">
        <span></span>${(q.row_options || []).map((o) =>
          `<span>${fbEsc(o.label)}</span>`).join("")}
      </div>
      ${(q.rows || []).map((r) => `
        <div class="fb-mrow${r.preset && !(r.value in given) ? " fb-preset" : ""}">
          <span class="fb-mlabel">${fbEsc(r.label)}${
            r.note ? `<i>${fbEsc(r.note)}</i>` : ""}</span>
          ${(q.row_options || []).map((o) => `
            <span><input type="radio" name="m-${key}-${fbEsc(r.value)}"
              value="${fbEsc(o.value)}" data-row="${fbEsc(r.value)}"
              aria-label="${fbEsc(r.label)}: ${fbEsc(o.label)}"
              ${pick(r) === o.value ? "checked" : ""}></span>`).join("")}
        </div>`).join("")}
    </div>${fbAddYourOwn(q)}`;
  }

  /* One block per level of scrutiny, asking the same few things about each.

     Rendered as stacked blocks rather than a grid on purpose: the four things
     asked about each level are different kinds of answer — two are sentences,
     two are a choice — and a grid with mixed controls in one column reads as a
     puzzle. Stacked, it is a short form repeated, which is what it is. */
  if (q.kind === "tiers") {
    const given = (val && typeof val === "object") ? val : {};
    return `<div class="fb-tiers">${(q.rows || []).map((tier) => {
      const held = given[tier.value] || {};
      return `<section class="fb-tier">
        <h4>${fbEsc(tier.label)}</h4>
        ${(q.tier_fields || []).map((f) => {
          const id = `t-${key}-${tier.value}-${f.key}`;
          const now = (f.key in held) ? held[f.key]
            : ((f.defaults || {})[tier.value] || "");
          if (f.kind === "single") {
            return `<fieldset class="fb-tf">
              <legend>${fbEsc(f.label)}</legend>
              <div class="fb-chips">${(f.options || []).map((o) => `
                <label class="fb-chip${now === o.value ? " on" : ""}">
                  <input type="radio" name="${id}" value="${fbEsc(o.value)}"
                    data-tier="${fbEsc(tier.value)}" data-field="${fbEsc(f.key)}"
                    ${now === o.value ? "checked" : ""}>
                  <span>${fbEsc(o.label)}</span></label>`).join("")}</div>
            </fieldset>`;
          }
          return `<label class="g-field"><span>${fbEsc(f.label)}</span>
            <input type="text" id="${id}" class="fb-tfield"
              data-tier="${fbEsc(tier.value)}" data-field="${fbEsc(f.key)}"
              aria-describedby="${id}-ask" value="${fbEsc(now)}">
            <small id="${id}-ask" class="muted">${fbEsc(f.ask)}</small></label>`;
        }).join("")}
      </section>`;
    }).join("")}</div>`;
  }

  if (q.kind === "rows") {
    const rows = Array.isArray(val) && val.length ? val : [{ role: "" }];
    return `<div class="fb-rows" id="rows-${key}">
      ${rows.map((r, i) => fbSeatRow(key, r, i)).join("")}
      <button class="btn ghost" id="add-${key}" type="button">Add another</button>
    </div>`;
  }

  if (q.kind === "long") {
    return `<label class="g-field"><textarea id="in-${key}" rows="4"
      placeholder="${fbEsc(q.placeholder)}">${fbEsc(val || "")}</textarea></label>`;
  }

  return `<label class="g-field"><input type="text" id="in-${key}"
    placeholder="${fbEsc(q.placeholder)}" value="${fbEsc(val || "")}"></label>`;
}

/* Record whatever the step is showing but has not yet stored.

   A question can display an answer without owning one: a multi-select whose
   recommended options arrive ticked, or a grid pre-filled from an earlier
   step. Until this ran, the user saw six ticks at 5.5, accepted them, and the
   module counted the question unanswered — so the sidebar said "incomplete"
   about a step they had read end to end, and the exported framework left it
   out. See BUG-F4DAE83E and BUG-3F2B4446.

   Only questions with nothing stored are touched. An answer they gave is
   never overwritten, and an empty control is left empty — a blank is a real
   state and this must not fill it in. */
async function fbCommitStep(step) {
  const pending = [];
  for (const q of step.questions || []) {
    if (fbIsAnswered(q.key)) continue;
    const box = document.querySelector(`.fb-q[data-key="${q.key}"]`);
    if (!box || box.querySelector(".fb-greyed")) continue;

    let value = null;
    if (q.kind === "multi") {
      const ticked = [...box.querySelectorAll(`input[name="q-${cssKey(q.key)}"]`)]
        .filter((b) => b.checked).map((b) => b.value);
      if (ticked.length) value = ticked;
    } else if (q.kind === "single") {
      const picked = box.querySelector(`input[name="q-${cssKey(q.key)}"]:checked`);
      if (picked) value = picked.value;
    } else if (q.kind === "tiers") {
      const grid = {};
      box.querySelectorAll(".fb-tfield").forEach((f) => {
        if (!f.value.trim()) return;
        grid[f.dataset.tier] = grid[f.dataset.tier] || {};
        grid[f.dataset.tier][f.dataset.field] = f.value.trim();
      });
      box.querySelectorAll("input[type=radio][data-tier]:checked")
        .forEach((r) => {
          grid[r.dataset.tier] = grid[r.dataset.tier] || {};
          grid[r.dataset.tier][r.dataset.field] = r.value;
        });
      if (Object.keys(grid).length) value = grid;
    } else if (q.kind === "matrix") {
      const given = {};
      box.querySelectorAll("input[type=radio][data-row]:checked")
        .forEach((r) => { given[r.dataset.row] = r.value; });
      if (Object.keys(given).length) value = given;
    }
    // Free text is not pre-filled by anything, so there is nothing to accept.
    if (value !== null) pending.push({ key: q.key, value });
  }

  if (!pending.length) return 0;
  for (const { key, value } of pending) {
    const r = await fbPost("/api/versions/answer", { key, value });
    if (r && r.ok) FB.answers[key] = value;
  }
  FB.data = await fbApi("/api/module");
  fbToast(`${pending.length} answer${pending.length === 1 ? "" : "s"} you `
        + `accepted ${pending.length === 1 ? "was" : "were"} recorded.`);
  return pending.length;
}

/* Open a step at the top of it.

   This called `window.scrollTo(0, 0)`, which does nothing here: the page does
   not scroll, `main.record` does. So the scroll position carried over from
   wherever they were on the previous step, and on a longer one that offset
   landed part-way down — "when I selected continue at the bottom of S 3.0 to
   go to 4, it drops down to 4.4 immediately".

   Resets the real scroller and the window both, rather than hard-coding one:
   the next layout change should not silently bring this back. */
function fbToTheTop() {
  const scroller = document.getElementById("record");
  if (scroller) scroller.scrollTop = 0;
  for (let el = fbGet("#view"); el; el = el.parentElement) {
    if (el.scrollTop) el.scrollTop = 0;
  }
  if (window.scrollTo) window.scrollTo(0, 0);
}

/* A way to add a choice we did not think of.

   Four of the client's tickets are this request in four places — 3.1/3.2 "add
   Other and a fillable line", 5.1 "let them add their own risks", 6.2b "add
   rows", 6.6 "self-add fields". A response set that cannot be extended tells
   an organization that its business is one of the eight things we thought of.

   What they add is stored as the answer itself, behind a prefix, so it comes
   back ticked and can be un-ticked like anything else. */
function fbAddYourOwn(q) {
  if (!q.can_add) return "";
  const key = cssKey(q.key);
  return `<div class="fb-addown">
    <label class="g-field">
      <span>${fbEsc(q.can_add)}</span>
      <input type="text" id="add-${key}" maxlength="120"
             placeholder="In your own words">
    </label>
    <button class="btn ghost" type="button" id="addbtn-${key}">Add</button>
  </div>`;
}

/* One field, not two.

   This offered an optional name beside the role. The client's ruling: "Workflow
   process will be the operational component which covers the names. Framework
   sets rules meant to outlast individual people." A document written to outlast
   the people in it should not have somewhere to write their names — an optional
   field is an invitation, and the framework would have gone stale the first
   time somebody left. */
function fbSeatRow(key, row, i) {
  return `<div class="fb-seat" data-i="${i}">
    <label class="g-field"><span>Role title</span>
      <input type="text" class="seat-role" value="${fbEsc(row.role || "")}"
             placeholder="Deputy Director, IT Manager, Town Clerk…"></label>
  </div>`;
}

/* --------------------------------------------------------------- the wiring */

function wireQuestion(q) {
  const box = document.querySelector(`.fb-q[data-key="${q.key}"]`);
  if (!box) return;
  const key = q.key;

  /* Waiting on another answer: shown, explained, and genuinely not editable.
     Greying it in CSS alone would still let a keyboard user tab in and type
     into a grid built against levels nobody has chosen. */
  if (q.waiting_on) {
    box.querySelectorAll(".fb-greyed input, .fb-greyed textarea,"
                         + " .fb-greyed button, .fb-greyed select")
      .forEach((el) => { el.disabled = true; });
    return;
  }

  const save = async (value, extra = {}) => {
    const err = box.querySelector(`#err-${cssKey(key)}`);
    const ok = box.querySelector(".fb-ok");
    err.hidden = true;
    const r = await fbPost("/api/versions/answer", { key, value, ...extra });
    if (!r || !r.ok) {
      err.textContent = (r && r.error) || "That could not be saved.";
      err.hidden = false;
      return;
    }
    FB.answers[key] = Object.keys(extra).length
      ? { value, ...extra } : value;
    box.classList.add("answered");
    ok.hidden = false;
    setTimeout(() => { ok.hidden = true; }, 1800);
    fbSpelling(box, q, r, save, extra);
    fbAfterAnswer(q);
    return true;
  };

  // "Use this" on a passage from the organization's own documents.
  box.querySelectorAll("[data-use]").forEach((b) => b.onclick = async () => {
    const e = (q.evidence || [])[Number(b.dataset.use)];
    if (!e || !e.suggest) return;
    b.disabled = true;
    const ok = await save(e.suggest.value,
      { from_document: { file: e.file, paragraph: e.paragraph } });
    if (ok) {
      await fbRedrawOne(key);
      fbToast(`Answered from ${e.file}. You can still change it.`);
    } else {
      b.disabled = false;
    }
  });

  const owner = () => {
    const field = box.querySelector(`#ownin-${cssKey(key)}`);
    return field ? field.value.trim() : "";
  };

  // "We don't know" — available on almost everything, and never a blank.
  const unk = box.querySelector(`#unk-${cssKey(key)}`);
  if (unk) {
    unk.onchange = () => {
      const panel = box.querySelector(`#own-${cssKey(key)}`);
      panel.hidden = !unk.checked;
      if (unk.checked) save("unknown", { owner: owner() });
    };
  }

  /* The owner field, however the unknown was reached — his "Not sure" in the
     response set, or the tick-box on a bare text field. Wired outside the
     `unk` block because on most questions there is no tick-box to hang it on. */
  const ownerField = box.querySelector(`#ownin-${cssKey(key)}`);
  if (ownerField) {
    ownerField.onchange = () => {
      if (fbValue(key) === "unknown"
          || (Array.isArray(fbValue(key)) && fbValue(key).includes("unknown"))) {
        save(fbValue(key), { owner: owner() });
      }
    };
  }

  if (q.kind === "single") {
    box.querySelectorAll(`input[name="q-${cssKey(key)}"]`).forEach((radio) => {
      radio.onchange = () => {
        box.querySelectorAll(".fb-card").forEach((c) =>
          c.classList.toggle("on", c.contains(radio) && radio.checked));
        box.querySelectorAll(".fb-then").forEach((t) => {
          t.hidden = t.dataset.for !== radio.value;
        });
        // "Not sure" is one of his options, so picking it is what opens the
        // owner field — there is no separate tick-box to keep in step.
        const owned = box.querySelector(`#own-${cssKey(key)}`);
        if (owned) owned.hidden = radio.value !== "unknown";
        if (unk) unk.checked = false;
        fbConsequence(q, radio.value, box);
        const detail = box.querySelector(`#det-${cssKey(key)}`);
        const extra = {};
        if (detail && !detail.closest(".fb-then").hidden) {
          extra.detail = detail.value.trim();
        }
        if (radio.value === "unknown") extra.owner = owner();
        save(radio.value, extra);
      };
    });
    const detail = box.querySelector(`#det-${cssKey(key)}`);
    if (detail) {
      detail.onchange = () => {
        const picked = box.querySelector(`input[name="q-${cssKey(key)}"]:checked`);
        if (picked) save(picked.value, { detail: detail.value.trim() });
      };
    }
    // 2.3's "Or upload the file". The same upload the documents panel uses,
    // so the file joins the organization's own documents; the answer then
    // records which file it was, in the box beside it.
    const upload = box.querySelector(`#up-${cssKey(key)}`);
    if (upload) {
      upload.onchange = async () => {
        const chosen = upload.files && upload.files[0];
        const said = box.querySelector(`#up-${cssKey(key)}-said`);
        if (!chosen) return;
        said.textContent = `Reading ${chosen.name}…`;
        const bytes = new Uint8Array(await chosen.arrayBuffer());
        let binary = "";
        for (let i = 0; i < bytes.length; i += 8192) {
          binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 8192));
        }
        const r = await fbPost("/api/intake/upload", {
          filename: chosen.name, kind: q.prompt.slice(0, 80), content: btoa(binary) });
        if (!r || !r.ok || !r.readable) {
          said.textContent = (r && (r.error || r.note)) || "Could not read that file.";
          return;
        }
        if (detail) {
          detail.value = `Uploaded: ${r.file}`;
          detail.onchange();
        }
        said.textContent = `${r.file} uploaded — ${r.paragraphs} passages read.`;
      };
    }
  }

  if (q.kind === "multi") {
    const boxes = [...box.querySelectorAll(`input[name="q-${cssKey(key)}"]`)];
    const exclusive = new Set((q.options || [])
      .filter((o) => o.exclusive).map((o) => o.value));

    /* Everything the follow-up blanks currently hold, keyed by the option
       they belong to. A multi can have several — 6.2d has two — so one shared
       `detail` would let the last one typed overwrite the other. */
    const details = () => {
      const out = {};
      box.querySelectorAll(".fb-detail").forEach((f) => {
        const said = f.value.trim();
        if (said && !f.closest(".fb-then").hidden) {
          out["detail_" + f.dataset.for] = said;
        }
      });
      return out;
    };

    const apply = (chosen) => {
      boxes.forEach((b) => {
        b.checked = chosen.includes(b.value);
        b.closest(".fb-card").classList.toggle("on", b.checked);
        // Nothing else can be picked alongside an exclusive answer, so the
        // rest stop being clickable rather than being left to argue with it
        // four steps later. His instruction: "if they click nothing, then
        // gray out and make all others un-clickable."
        const locked = chosen.some((v) => exclusive.has(v))
          && !exclusive.has(b.value);
        b.disabled = locked;
        b.closest(".fb-card").classList.toggle("fb-locked", locked);
      });
      box.querySelectorAll(".fb-then").forEach((t) => {
        t.hidden = !chosen.includes(t.dataset.for);
      });
      const owned = box.querySelector(`#own-${cssKey(key)}`);
      if (owned) owned.hidden = !chosen.includes("unknown");
    };

    boxes.forEach((cb) => {
      cb.onchange = () => {
        let chosen = boxes.filter((b) => b.checked).map((b) => b.value);
        // Ticking an exclusive answer clears the rest; ticking anything else
        // clears the exclusive one. Either way the answer stays coherent.
        if (cb.checked && exclusive.has(cb.value)) {
          chosen = [cb.value];
        } else if (cb.checked) {
          chosen = chosen.filter((v) => !exclusive.has(v));
        }
        apply(chosen);
        if (unk) unk.checked = false;
        save(chosen, {
          ...(chosen.includes("unknown") ? { owner: owner() } : {}),
          ...details(),
        });
      };
    });

    box.querySelectorAll(".fb-detail").forEach((f) => {
      f.onchange = () => {
        const chosen = boxes.filter((b) => b.checked).map((b) => b.value);
        save(chosen, {
          ...(chosen.includes("unknown") ? { owner: owner() } : {}),
          ...details(),
        });
      };
    });

    // Reflect whatever is already ticked, so an exclusive answer restored
    // from storage arrives with the others already locked.
    apply(boxes.filter((b) => b.checked).map((b) => b.value));
  }

  if (q.kind === "matrix") {
    box.querySelectorAll(`input[type="radio"][data-row]`).forEach((radio) => {
      radio.onchange = () => {
        const given = {};
        box.querySelectorAll(`input[type="radio"][data-row]:checked`)
          .forEach((r) => { given[r.dataset.row] = r.value; });
        if (unk) { unk.checked = false; box.querySelector(`#own-${cssKey(key)}`).hidden = true; }
        save(given);
      };
    });
  }

  /* The whole grid saves on every change, pre-fills included. Saving only the
     fields they touched would put a framework in front of them showing levels
     of scrutiny with nothing written against them — when the screen they
     approved plainly had words in every box. */
  if (q.kind === "tiers") {
    const collect = () => {
      const out = {};
      const put = (el, value) => {
        const t = el.dataset.tier;
        out[t] = out[t] || {};
        out[t][el.dataset.field] = value;
      };
      box.querySelectorAll(".fb-tfield").forEach(
        (f) => put(f, f.value.trim()));
      box.querySelectorAll("input[type=radio][data-tier]:checked").forEach(
        (r) => put(r, r.value));
      return out;
    };
    box.querySelectorAll(".fb-tfield, input[type=radio][data-tier]")
      .forEach((el) => {
        el.onchange = () => {
          const chip = el.closest(".fb-chip");
          if (chip) {
            chip.closest(".fb-chips").querySelectorAll(".fb-chip")
              .forEach((c) => c.classList.toggle("on", c === chip));
          }
          box.querySelectorAll(".fb-preset").forEach(
            (row) => row.classList.remove("fb-preset"));
          if (unk) {
            unk.checked = false;
            box.querySelector(`#own-${cssKey(key)}`).hidden = true;
          }
          save(collect());
        };
      });
  }

  if (q.kind === "rows") {
    const collect = () => [...box.querySelectorAll(".fb-seat")]
      .map((s) => ({ role: s.querySelector(".seat-role").value.trim() }))
      .filter((r) => r.role);
    const wire = () => box.querySelectorAll(".fb-seat input").forEach((i) => {
      i.onchange = () => save(collect());
    });
    wire();
    const add = box.querySelector(`#add-${cssKey(key)}`);
    if (add) {
      add.onclick = () => {
        const holder = box.querySelector(`#rows-${cssKey(key)}`);
        const i = holder.querySelectorAll(".fb-seat").length;
        holder.insertAdjacentHTML("afterbegin", fbSeatRow(cssKey(key), {}, i));
        wire();
      };
    }
  }

  if (q.kind === "short" || q.kind === "long") {
    const field = box.querySelector(`#in-${cssKey(key)}`);
    if (field) {
      field.onchange = () => {
        if (unk) { unk.checked = false; box.querySelector(`#own-${cssKey(key)}`).hidden = true; }
        save(field.value.trim(), alsoExtra());
      };
    }
  }

  /* Adding a choice of their own.

     It saves immediately and the question redraws, because the thing they
     just typed has to appear in the list as chosen — a text box that empties
     itself and shows nothing else looks like it failed. On a grid the new row
     arrives unweighted, so the next thing they do is say how much it matters,
     which is the point of adding it. */
  const adder = box.querySelector(`#addbtn-${cssKey(key)}`);
  if (adder) {
    const field = box.querySelector(`#add-${cssKey(key)}`);
    const add = async () => {
      const said = field.value.trim();
      if (!said) return;
      const value = "custom:" + said;
      const held = fbValue(key);
      let next;
      if (q.kind === "matrix") {
        next = { ...(held && typeof held === "object" ? held : {}) };
        if (value in next) { field.value = ""; return; }
        next[value] = "";
      } else {
        const chosen = Array.isArray(held) ? held.slice()
          : (q.options || []).filter((o) => o.recommended && !fbIsAnswered(key))
              .map((o) => o.value);
        if (chosen.includes(value)) { field.value = ""; return; }
        next = chosen.concat([value]);
      }
      field.value = "";
      // Let go of the field first: the redraw deliberately skips whatever the
      // user is typing into, and without this that is the box we just used —
      // so the new choice saved but never appeared.
      field.blur();
      adder.blur();
      await save(next);
      await fbRedrawStep(null);
    };
    adder.onclick = add;
    field.onkeydown = (e) => {
      // Enter adds it. Without this the form feels broken to anyone who
      // types and presses return, which is most people.
      if (e.key === "Enter") { e.preventDefault(); add(); }
    };
  }

  /* The paired field travels with the answer rather than as its own record,
     so "who writes it" and "who approves it" cannot drift apart in the store
     the way they would as two keys. */
  function alsoExtra() {
    const second = q.also && box.querySelector(`#also-${cssKey(key)}`);
    return second && second.value.trim()
      ? { [q.also.key]: second.value.trim() } : {};
  }
  const second = q.also && box.querySelector(`#also-${cssKey(key)}`);
  if (second) {
    second.onchange = () => {
      const main = box.querySelector(`#in-${cssKey(key)}`);
      save(main ? main.value.trim() : fbValue(key), alsoExtra());
    };
  }
}

/** A key that is safe in an id and in a selector.

    Question keys are dotted — `org.functions` — and a dot inside an id makes
    `#err-org.functions` parse as "the element with id err-org that also has
    class functions", which matches nothing. This was a stub returning the key
    unchanged with a comment describing exactly that hazard, and every
    id-based lookup silently returned null until the first save threw. */
function cssKey(key) {
  return String(key).replace(/\./g, "--");
}

/* One line, then accept it.

   "Never disable a recommended-against answer. Show one line of consequence,
   accept the choice, and record the rationale. The moment the module refuses
   something, it becomes someone else's framework, which is the one thing it
   must never be."

   So this is a sentence, not a dialog, and nothing is blocked. The only case in
   steps 01–04 that earns one is picking a governance shape heavier than the
   organization's size suggests — and the spec is explicit that it gets one
   gentle note and then no further argument. */
function fbConsequence(q, value, box) {
  const line = box.querySelector(`#csq-${cssKey(q.key)}`);
  if (!line) return;
  let text = "";

  /* The lines the module declares, checked against what was just chosen.

     This function used to know about 4.1 and nothing else, so his "an
     untested fallback is a document, not a plan" at 6.5b never appeared and
     he raised a ticket for it. The lines now travel with the questions. */
  for (const rule of q.consequences || []) {
    const cond = rule.if || {};
    const hit = cond.is !== undefined ? value === cond.is
      : cond.in !== undefined ? (cond.in || []).includes(value)
      : cond.not !== undefined ? value !== cond.not
      : false;
    if (hit && rule.say) { text = rule.say; break; }
  }

  if (!text && q.key === "who.shape" && q.recommended
      && value !== q.recommended) {
    const heavier = { one: 0, existing: 1, group: 2, council: 3 };
    if ((heavier[value] || 0) > (heavier[q.recommended] || 0)) {
      text = "Heavier than your size suggests. Worth a thought about who "
           + "sustains it — a group that stops convening is worse than one "
           + "person who shows up. Your answer stands either way.";
    }
  }

  line.textContent = text;
  line.hidden = !text;
}

/* A possible typo, shown under the field they typed it into.

   "11.1 - Noting to test this. I intentionally mis-spelled 'the' to 'teh' to
   see if the system notices and correct."

   It notices. It does not correct on its own, and that is deliberate: the
   framework this module builds says no tool finalizes anything without a
   person, and an application that quietly rewrites what somebody typed into a
   policy they are about to adopt is not holding to the rule it is asking them
   to adopt. `prose.py` carries these answers into the document word for word,
   so a silent substitution would be a silent change to an adopted instrument.

   So the line says what it thinks and the button applies it. One click, their
   decision, and the correction goes back through the same save path as
   anything else — so it is recorded, audited and visible in the version
   history like every other edit. */
function fbSpelling(box, q, reply, save, extra) {
  const key = cssKey(q.key);
  let line = box.querySelector(`#spell-${key}`);
  const spellings = (reply && reply.spelling) || [];

  if (!spellings.length) {
    if (line) line.remove();
    return;
  }
  if (!line) {
    line = fbEl("div", "fb-spell");
    line.id = `spell-${key}`;
    const ok = box.querySelector(".fb-ok");
    (ok && ok.parentNode ? ok.parentNode : box).appendChild(line);
  }
  line.innerHTML = `<span>${fbEsc(reply.spelling_note)}</span>
    <button class="btn ghost" type="button" data-fixspell>Use ${
      spellings.length === 1 ? "it" : "them"}</button>
    <button class="btn ghost" type="button" data-keepspell>Leave as typed</button>`;

  line.querySelector("[data-keepspell]").onclick = () => line.remove();
  line.querySelector("[data-fixspell]").onclick = () => {
    /* Applied to whichever field holds the text, so the correction is visible
       in the box before it is saved. Whole words only, and the replacement
       carries the original's capitalization — the server decided that, and
       this uses what it sent rather than deciding again. */
    const fields = [...box.querySelectorAll('input[type="text"], textarea')];
    let touched = false;
    for (const field of fields) {
      let next = field.value;
      for (const s of spellings) {
        next = next.replace(
          new RegExp(`\\b${s.word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`,
                     "g"),
          s.suggest);
      }
      if (next !== field.value) { field.value = next; touched = true; }
    }
    line.remove();
    if (!touched) return;
    const box2 = box.querySelector('textarea, input[type="text"]');
    save(box2 ? box2.value.trim() : "", extra || {});
  };
}

/* An answer changes what later questions ask, so the module is reloaded rather
   than left showing questions that no longer apply.

   Some of those questions are on the *same screen*. 5.2 asks how many levels of
   scrutiny you want and 5.3, directly beneath it, asks what has to happen at
   each one — so answering 5.2 has to redraw 5.3 where it stands. Reloading the
   summary behind the screen was enough while every dependency crossed a step
   boundary and the user re-opened the step on the way. It is not enough now.

   And the list is no longer written here.

   It was: seven keys, by hand. The client reported what that costs — "--2b
   did not populate until after I saved. Is that the only way? Can it show up
   before saving and proceeding? Creates a feeling of rework. (happens in
   other places, too)" — and he was right about the other places. A question
   gated by an answer nobody remembered to add to this array stayed stale
   until something else forced a reload.

   So the server derives it from the questions themselves and sends it. Two
   more had just been added without noticing: `why.has_units`, which reveals
   11.5a and 11.5b, and `floor.plain_scope`, which hides 6.8b. Both would
   have shipped with exactly the fault the ticket describes.

   The hand-written list stays only as a fallback for a cached script talking
   to an older response. */
const FB_DRIVERS_FALLBACK = ["org.kind", "org.size", "org.adopter",
                             "org.functions", "org.delegated", "who.shape",
                             "risk.levels"];

function fbDrivers() {
  const sent = FB.data && FB.data.drivers;
  return Array.isArray(sent) && sent.length ? sent : FB_DRIVERS_FALLBACK;
}

async function fbAfterAnswer(q) {
  if (!fbDrivers().includes(q.key)) return;
  FB.data = await fbApi("/api/module");
  if (FB.open !== null) await fbRedrawStep(q.key);
  fbToast("Saved. Later questions have been adjusted to match.");
}

/* Redraw the questions on the open step, in place.

   Everything except the question just answered — which holds focus — and
   anything the user is currently typing into, because replacing a field
   mid-sentence loses what they were writing. */
async function fbRedrawStep(answeredKey) {
  const step = await fbApi("/api/module?step=" + encodeURIComponent(FB.open));
  const active = document.activeElement;
  for (const q of step.questions || []) {
    const old = document.querySelector(`.fb-q[data-key="${q.key}"]`);
    if (!old || q.key === answeredKey) continue;
    if (active && old.contains(active)) continue;
    old.replaceWith(fbQuestion(q));
    wireQuestion(q);
  }
}
/* -------------------------------------------------------------- versioning */

/* Keep a copy, and start fresh.

   The client wanted to wipe his tenant so he could demo from zero and test
   from a clean start — and then, on being offered the alternative: "Great
   idea. Didn't know it was even possible." So the wipe is here, and beside it
   the thing that makes wiping repeatable rather than final.

   The endpoints for the wipe already existed and nothing in the browser had
   ever called them, so it was unreachable as well as mis-scoped. */
function fbYourContentPanel() {
  const box = fbEl("div", "panel");
  box.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Your content</h2>
    <p class="intro">Everything you have answered lives in your own space and
      is yours to keep, copy or clear. Your audit trail is separate and is
      never touched by anything on this panel.</p>

    <h3 class="sub4">Keep a copy</h3>
    <p class="small muted">Take a snapshot before you demo or experiment, and
      put your work back afterward.</p>
    <div class="row" style="margin-top:10px">
      <input id="snapLabel" type="text" maxlength="80" style="flex:1;min-width:200px"
             placeholder="What is this copy for? e.g. Before the board demo">
      <button class="btn" id="snapTake" type="button">Take a snapshot</button>
    </div>
    <div id="snapList" class="fb-snaps"></div>

    <h3 class="sub4">Start fresh</h3>
    <p class="small muted">Clears every answer, version and decision you have
      recorded. It cannot be undone — take a snapshot first if you might want
      any of it back.</p>
    <div id="resetWhat" class="small muted" style="margin-top:8px"></div>
    <div class="row" style="margin-top:10px">
      <input id="resetPhrase" type="text" style="flex:1;min-width:200px"
             placeholder="Type START OVER to confirm">
      <button class="btn ghost" id="resetGo" type="button">Start over</button>
    </div>
    <p class="signin-error" id="contentErr" hidden></p>`;

  const err = box.querySelector("#contentErr");
  const fail = (message) => {
    err.textContent = message;
    err.hidden = false;
  };

  const drawSnaps = (state) => {
    const list = box.querySelector("#snapList");
    const held = (state && state.snapshots) || [];
    if (!held.length) {
      list.innerHTML = `<p class="small muted" style="margin-top:10px">No
        copies kept yet.</p>`;
      return;
    }
    list.innerHTML = held.map((s) => `
      <div class="fb-snap">
        <span class="fb-snap-main">
          <b>${fbEsc(s.label)}</b>
          <i>${fbEsc(whenLocal(s.taken_at))}
             · ${fbEsc(s.taken_by || "")}</i>
        </span>
        <button class="btn ghost" type="button" data-restore="${fbEsc(s.id)}">
          Put this back</button>
        <button class="btn ghost" type="button" data-forget="${fbEsc(s.id)}">
          Delete</button>
      </div>`).join("")
      + `<p class="small muted" style="margin-top:8px">${held.length} of ${
        state.limit} kept.</p>`;

    list.querySelectorAll("[data-restore]").forEach((b) => {
      b.onclick = () => askConfirmish({
        title: "Put this copy back?",
        body: "Everything you have answered since this snapshot was taken "
            + "will be replaced by what it holds. Your audit trail keeps "
            + "both, and records the replacement.",
        onYes: async () => {
          const r = await fbPost("/api/snapshots/restore",
                                 { id: b.dataset.restore });
          if (!r || !r.ok) return fail((r && r.error) || "That did not work.");
          fbToast("Your work has been put back.");
          window.location.reload();
        },
      });
    });
    list.querySelectorAll("[data-forget]").forEach((b) => {
      b.onclick = async () => {
        const r = await fbPost("/api/snapshots/forget",
                               { id: b.dataset.forget });
        if (!r || !r.ok) return fail((r && r.error) || "That did not work.");
        drawSnaps(r.state);
      };
    });
  };

  const load = async () => {
    drawSnaps(await fbApi("/api/snapshots"));
    const plan = await fbApi("/api/reset");
    const has = ((plan && plan.clears) || []).filter((c) => c.present);
    box.querySelector("#resetWhat").textContent = has.length
      ? "Would clear: " + has.map((c) => c.label).join(" · ")
      : "There is nothing recorded to clear.";

    /* Wiping is irreversible and needs the authority it has always needed.
       Saying which, and where to change it, rather than letting them type the
       phrase and then be told an operator cannot reset configuration. */
    if (plan && plan.can_reset === false) {
      box.querySelector("#resetGo").disabled = true;
      box.querySelector("#resetPhrase").disabled = true;
      const note = fbEl("p", "small muted");
      note.textContent = plan.why_not || "";
      note.style.marginTop = "8px";
      box.querySelector("#resetPhrase").closest(".row").after(note);
    }
  };
  load();

  box.querySelector("#snapTake").onclick = async () => {
    err.hidden = true;
    const label = box.querySelector("#snapLabel").value.trim();
    const r = await fbPost("/api/snapshots", { label });
    if (!r || !r.ok) return fail((r && r.error) || "That did not work.");
    box.querySelector("#snapLabel").value = "";
    fbToast("Copy kept.");
    drawSnaps(r.state);
  };

  box.querySelector("#resetGo").onclick = async () => {
    err.hidden = true;
    const phrase = box.querySelector("#resetPhrase").value;
    const r = await fbPost("/api/reset", { confirm: phrase, reason: "" });
    if (!r || !r.ok) return fail((r && r.error) || "That did not work.");
    window.location.reload();
  };

  return box;
}

/* The in-app confirmation, if the shell has one. Never `confirm()` — Chrome
   disables those permanently once anybody ticks "prevent additional dialogs",
   which is how Sign Out came to do nothing at all. */
function askConfirmish(spec) {
  if (window.askConfirm) return window.askConfirm(spec);
  return spec.onYes();
}

function fbVersionPanel() {
  const v = FB.versions || {};
  const box = fbEl("div", "panel");
  box.innerHTML = `
    <h2 class="sub3" style="margin-top:0">Versions and adoption</h2>
    <p class="intro">${fbEsc(v.how_to_adopt || "")}</p>
    <div class="row" style="margin-top:12px">
      <input id="fbNote" type="text" placeholder="What changed (optional)"
             style="flex:1;min-width:200px">
      <button class="btn" id="fbSave" type="button"${
        v.can_save ? "" : " disabled"}>Save a version</button>
    </div>
    <p class="signin-error" id="fbErr" hidden></p>

    <!-- Never disabled, and deliberately available before anything is saved.
         The offer is that the framework is theirs; a download that waits for a
         version would make the free thing conditional on understanding the
         versioning. What it hands over says on its face how much is answered
         and that nobody has adopted it. -->
    <!-- The reminder belongs here, at the moment the document leaves.

         The client: "I think this point is a good time to remind the user
         that we require a human in authority. So now the user needs to
         download the version and review it carefully."

         It is also the framework's own first rule applied to itself — the
         document requires that decisions affecting the public rest with a
         person, and its own adoption is the first place that has to be
         true. -->
    <div class="fb-handoff">
      <p class="fb-handoff-h">Read it before anyone signs it</p>
      <p>This framework was assembled from your answers. Nobody has reviewed
        it, and nothing in it is binding until a person with the authority to
        adopt it has read it and said so.</p>
      <p>Download it, read it through, and change any wording that is not how
        your organization would put it. The document is yours to edit — it is
        drafted to be adoptable as it stands, not to be final.</p>
      <div class="row" style="margin-top:12px">
        <button class="btn" id="fbExport" type="button">
          Download the draft document</button>
      </div>
      <!-- Under the button, not beside it. Beside it, this wrapped at 361px
           in an 818px card — a stub of text with half a line of empty space
           after it, which is the same complaint in miniature. -->
      <p class="small muted" id="fbExportNote" style="margin-top:8px">Word
        format, with every decision recorded so far and the gaps marked.</p>
    </div>
    ${(v.history || []).length ? `
      <h2 class="sub3">History</h2>
      ${v.history.map((h) => `
        <div class="entry"><time>${fbEsc(whenLocal(h.created_at))}</time>
          <span class="k ${h.is_draft ? "deny" : "allow"}">${fbEsc(h.label)}</span>
          <p>${fbEsc(h.note || "No note.")}<br>
          <span class="small muted">${fbEsc(h.created_by || "")}${
            h.created_title ? `, ${fbEsc(h.created_title)}` : ""}</span>
          ${h.is_draft && v.can_adopt ? `
            <br><button class="btn" data-adopt="${h.number}" type="button"
              style="margin-top:6px">Record adoption of version ${h.number}</button>` : ""}
          </p></div>`).join("")}` : ""}`;
  // The trailing note about the DRAFT stamp is gone, at the client's
  // instruction: "Delete the bottom The DRAFT stamp text completely." The
  // document itself carries the mark and explains it on its own page, which
  // is where the explanation belongs — repeating it under the history was
  // the third time one screen said the same thing.

  setTimeout(() => {
    const save = document.getElementById("fbSave");
    if (save) save.onclick = async () => {
      const err = document.getElementById("fbErr");
      err.hidden = true;
      const r = await fbPost("/api/versions/save",
        { note: (document.getElementById("fbNote") || {}).value || "" });
      if (!r.ok) { err.textContent = r.error; err.hidden = false; return; }
      fbToast(`Saved ${r.version.label}.`);
      fbGo("framework");
    };

    /* The document arrives base64-encoded inside JSON — see
       api_framework_export — so the browser reassembles it and hands it to the
       download the way it would any other file. A blob URL rather than a data:
       URL because Chrome caps data: navigations at a couple of megabytes and a
       long framework will pass that. */
    const exportBtn = document.getElementById("fbExport");
    if (exportBtn) exportBtn.onclick = async () => {
      const note = document.getElementById("fbExportNote");
      const before = note ? note.textContent : "";
      exportBtn.disabled = true;
      if (note) note.textContent = "Building it…";
      let r;
      try {
        r = await fbApi("/api/framework/export");
      } catch (e) {
        r = { ok: false, error: "Could not reach the server." };
      }
      exportBtn.disabled = false;
      if (!r || !r.ok) {
        if (note) note.textContent = (r && r.error) || "It could not be built.";
        return;
      }
      try {
        const bytes = Uint8Array.from(atob(r.content), (c) => c.charCodeAt(0));
        const url = URL.createObjectURL(new Blob([bytes], {
          type: "application/vnd.openxmlformats-officedocument."
                + "wordprocessingml.document",
        }));
        const a = document.createElement("a");
        a.href = url;
        a.download = r.filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        // Released on a timer: revoking it in the same tick cancels the
        // download in Safari before it has started reading.
        setTimeout(() => URL.revokeObjectURL(url), 30000);
        if (note) note.textContent = `${r.filename} — ${r.label}`;
      } catch (e) {
        if (note) note.textContent = "The file could not be saved: " + e.message;
        return;
      }
      setTimeout(() => { if (note) note.textContent = before; }, 8000);
    };
    document.querySelectorAll("[data-adopt]").forEach((b) => {
      b.onclick = async () => {
        const r = await fbPost("/api/versions/adopt",
          { version: Number(b.dataset.adopt) });
        if (!r.ok) return fbToast(r.error, true);
        fbToast(`Version ${r.version.number} recorded as adopted.`);
        if (window.refreshFramework) await window.refreshFramework();
        fbGo("framework");
      };
    });
  }, 0);
  return box;
}

/* The Framework screen gates "record the adoption" on this. Exported rather
   than recomputed there, so there is one definition of "complete". */
window.frameworkProgress = () => {
  const t = fbTotals();
  return { done: t.answered || 0, total: t.questions || 0 };
};

window.renderBuilder = renderBuilder;
window.fbOpenStep = openStep;


