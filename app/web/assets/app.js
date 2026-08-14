/* SCDES AI Governance — shell.

   Two ideas drive the layout:
   · the record (centre) is what the governed record says; the reason (right
     rail) is always why, with the section it cites. Explainability is part of
     the frame rather than a panel you go looking for.
   · the command bar (Ctrl/Cmd-K) carries query, what-if and intake, so asking
     is available everywhere instead of living on one page. */

const S = { user: "liz.operator", view: "vision", project: "AI-001",
            gate: null, state: null, vocab: {} };

const $ = (s) => document.querySelector(s);
const el = (t, c, h) => { const n = document.createElement(t);
  if (c) n.className = c; if (h !== undefined) n.innerHTML = h; return n; };
const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const money = (n) => "$" + Number(n || 0).toLocaleString("en-US", { maximumFractionDigits: 0 });
const cls = (b) => String(b || "").toLowerCase();

/* vocabulary-aware labels — the configured term, not a hardcoded one */
const vlabel = (concept, key) =>
  (S.vocab[concept] && S.vocab[concept][String(key).toLowerCase()]) || String(key);

async function api(p, opts = {}) {
  const sep = p.includes("?") ? "&" : "?";
  const r = await fetch(p + sep + "user=" + encodeURIComponent(S.user), {
    headers: { "Content-Type": "application/json", "X-SCDES-User": S.user }, ...opts });
  return r.json();
}
const post = (p, b) => api(p, { method: "POST", body: JSON.stringify(b) });

let tt;
function toast(msg, bad = false) {
  const t = $("#toast"); t.textContent = msg;
  t.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(tt); tt = setTimeout(() => (t.className = "toast"), 5600);
}

/* ----------------------------------------------------------- reason rail */

function reason(blocks) {
  const body = $("#reasonBody");
  body.innerHTML = "";
  if (!blocks || !blocks.length) {
    body.innerHTML = `<p class="reason-empty">Nothing selected.</p>`;
    return;
  }
  blocks.forEach((b) => {
    const w = el("div", "reason-block");
    w.innerHTML =
      (b.title ? `<h4>${esc(b.title)}</h4>` : "") +
      (b.body ? `<p>${esc(b.body)}</p>` : "") +
      (b.quote ? `<div class="reason-quote">${esc(b.quote)}</div>` : "") +
      (b.cite ? `<div class="reason-cite">${esc(b.cite)}</div>` : "");
    body.appendChild(w);
  });
}

/* ---------------------------------------------------------------- shell */

const META = {
  vision:    ["Vision", "Where the agency intends to get to, and how the pipeline gets there."],
  registry:  ["Registry", "Every AI system as a tracked project — stage, owners, risk and review schedule."],
  workflow:  ["Lifecycle", "The gate's checklist, the instruments due, and the form that writes the real workbook."],
  budget:    ["Budget", "Pools, cost-typed quotes and the weighted recommendation."],
  oversight: ["Oversight", "Risk re-scoring, monitoring obligations and incident response."],
  process:   ["Process", "What each gate requires and how a decision routes."],
  setup:     ["Terminology", "One vocabulary, chosen once, applied everywhere after."],
  configure: ["Configure", "The operational model beneath the Framework."],
  council:   ["Council", "The gated room where the governance changes."],
  agency:    ["Agency profile", "Who this corpus belongs to, and how it is structured — all of it discovered."],
  integrity: ["Integrity", "Is the governance trail tight enough to rely on?"],
  audit:     ["Audit trail", "Every governed attempt, granted and refused, hash-chained."],
};

async function refreshState() {
  const st = await api("/api/state");
  S.state = st;
  S.vocab = st.vocabulary || {};

  const mode = $("#modeChip");
  mode.textContent = st.mode === "operating" ? "Guardrails live" : "Tuning open";
  mode.className = "tb-chip " + (st.mode === "operating" ? "live" : "tuning");

  const ig = $("#integrityChip");
  const c = st.integrity.counts || {};
  const crit = (c.critical || 0) + (c.serious || 0);
  ig.textContent = st.integrity.total
    ? `Integrity ${st.integrity.total}${crit ? " · " + crit + " to fix" : ""}`
    : "Integrity clear";
  ig.className = "tb-chip" + (crit ? " bad" : " live");

  $("#avatar").textContent = st.actor.name.split(" ").map((w) => w[0]).join("").slice(0, 2);
  const pick = $("#userPick");
  if (!pick.options.length)
    st.roster.forEach((r) => {
      const o = el("option"); o.value = r.id; o.textContent = r.role; pick.appendChild(o);
    });
  pick.value = st.actor.id;
  await renderSpine();
}

async function renderSpine() {
  const spine = $("#spine");
  // PermitPro belongs to the loaded corpus. Showing it above another agency's
  // name is the same fabrication as showing their registry, so the spine goes
  // with the rest of the record.
  if (!agencyHasCorpus()) { spine.hidden = true; return; }
  const d = await api("/api/project?id=" + encodeURIComponent(S.project));
  if (d.error) { spine.hidden = true; return; }
  spine.hidden = false;
  const p = d.project;
  $("#projName").textContent = p.name;
  $("#projMeta").textContent =
    `${vlabel("use_case_grouping", p.category)} · ${vlabel("risk_band", d.risk.band)} · ${p.stage}`;

  const names = ["Concept", "Readiness", "Pilot", "Deployment", "Scaling", "Annual review"];
  const track = $("#spineTrack"); track.innerHTML = "";
  for (let g = 0; g <= 5; g++) {
    if (g) track.appendChild(el("li", "gate-link"));
    const li = el("li");
    const b = el("button", "gate " + (g < p.gate ? "done" : g === p.gate ? "now" : "ahead"));
    b.type = "button";
    b.innerHTML = `<span class="pip"></span>${g}. ${esc(names[g])}`;
    b.onclick = () => { S.gate = g; go("workflow"); };
    li.appendChild(b); track.appendChild(li);
  }
}

/* Every record in this application — PermitPro, the 25 tracked systems, the
   budget pools, the integrity findings — comes from the one corpus that is
   actually loaded. Selecting a state on the map changes the theme and the name;
   it does not and cannot conjure that state's documents.

   So when the selected agency is not the loaded one, the views must not run.
   Rendering South Carolina's project register under "Texas Commission on
   Environmental Quality" would be a fabricated record, and this is the app whose
   whole claim is that its trail can be relied on. */
function agencyHasCorpus() {
  const a = window.SCDES_AGENCY;
  return !a || a.corpus_loaded;      // no selection yet == the loaded default
}

/** Abbreviation of the agency whose corpus is actually on disk. */
function loadedAgencyName() {
  const reg = window.LNCH_DATA;
  if (!reg) return null;
  const hit = reg.states.find((s) => s.code === reg.loaded);
  return hit ? hit.abbrev : null;
}

function noCorpusPanel() {
  const a = window.SCDES_AGENCY || {};
  const loaded = loadedAgencyName() || "the loaded agency";
  const root = el("div", "panel empty-agency");
  root.innerHTML = `
    <h3 class="sub3" style="margin-top:0">No ${esc(a.abbrev || "agency")} corpus loaded</h3>
    <p class="intro">This screen would show ${esc(a.agency || "this agency")}'s own
      records. None have been loaded, and the records that <em>are</em> loaded
      belong to ${esc(loaded)} — showing those here, under this name, would be a
      fabricated register rather than an empty one.</p>
    <p class="intro">Drop ${esc(a.abbrev || "the agency")}'s adopted framework,
      operations manual and appendices into <span class="mono">corpus/</span>.
      The registry, lifecycle, budget, terminology and citations are all read
      from those documents.</p>
    <div class="row" style="margin-top:14px">
      <button class="btn" id="emptyPickAgency" type="button">Choose another agency</button>
      <button class="btn ghost" id="emptyUseLoaded" type="button">Open ${esc(loaded)}</button>
    </div>`;
  return root;
}

function go(view) {
  S.view = view;
  // Only items that name a view can be the current one. Matching on the whole
  // rail meant "Choose agency" — which has no data-view — went active whenever
  // `view` was undefined, marking the front door as the page you are on.
  document.querySelectorAll(".rail-item[data-view]").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === view));
  const [t, s] = META[view] || ["", ""];
  $("#viewTitle").textContent = t; $("#viewSub").textContent = s;

  if (!agencyHasCorpus()) {
    $("#spine").hidden = true;            // the project spine is corpus data too
    $("#view").innerHTML = "";
    $("#view").appendChild(noCorpusPanel());
    $("#emptyPickAgency").onclick = () => showLauncher();
    $("#emptyUseLoaded").onclick = () => {
      const reg = window.LNCH_DATA;
      if (reg && window.selectAgency) window.selectAgency(reg.loaded);
    };
    reason([{ title: "Why this is empty",
      body: "The application holds one corpus at a time. Every figure on every screen traces to a document in it, so an agency without one has nothing to show — and borrowing another agency's records would break the only guarantee this tool makes.",
      cite: "README — theming across fifty agencies" }]);
    return;
  }

  $("#view").innerHTML = `<p class="muted">Loading…</p>`;
  (VIEWS[view] || VIEWS.vision)();
}

// Re-render when the agency changes, so switching states on the map takes effect
// immediately. Guarded on S.state: the launcher makes its first selection during
// boot, before /api/state has returned, and the views cannot render without it.
document.addEventListener("agencychange", () => {
  if (S.state && S.view) go(S.view);
});

/* --------------------------------------------------------------- palette */

function openPalette() {
  $("#palette").hidden = false;
  $("#paletteInput").value = "";
  $("#paletteOut").innerHTML = "";
  $("#paletteInput").focus();
}
const closePalette = () => ($("#palette").hidden = true);

document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
    e.preventDefault(); openPalette();
  } else if (e.key === "Escape") closePalette();
});
$("#cmdkBtn").onclick = openPalette;
$("#paletteClose").onclick = closePalette;
$("#palette").addEventListener("click", (e) => {
  if (e.target.id === "palette") closePalette();
});
$("#paletteInput").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  const msg = e.target.value.trim();
  if (!msg) return;
  $("#paletteOut").innerHTML = `<div class="answer"><p class="muted">Searching the corpus…</p></div>`;
  const r = await post("/api/chat", { message: msg });
  renderAnswer(r);
});

function renderAnswer(r) {
  const label = { query: "Cited answer", scenario: "What-if · nothing changed",
    intake: "Draft project · not on the record" }[r.mode] || r.mode;
  const box = el("div", "answer");
  box.innerHTML =
    `<div class="amode">${esc(label)} · ${esc(r.provider)}</div>` +
    `<p>${esc(r.answer)}</p>` +
    (r.citations && r.citations.length
      ? `<div class="cites">` + r.citations.slice(0, 4).map((c) =>
          `<div class="cite"><b>[${c.n}] ${esc(c.citation)}</b>${esc((c.snippet || "").slice(0, 190))}…</div>`
        ).join("") + `</div>` : "") +
    `<div class="foot">${r.mode === "query"
      ? "Answered from the governed corpus. Nothing was written."
      : "Computed live. The record of authority is unchanged."}</div>`;
  $("#paletteOut").innerHTML = ""; $("#paletteOut").appendChild(box);

  if (r.citations && r.citations.length)
    reason(r.citations.slice(0, 3).map((c) =>
      ({ title: c.citation, quote: (c.snippet || "").slice(0, 240) })));
}

/* ----------------------------------------------------------------- views */

const VIEWS = {};

VIEWS.vision = async () => {
  const v = await api("/api/vision");
  const st = S.state, pf = st.portfolio;
  const root = el("div");

  const tiles = el("div", "tiles");
  const tile = (n, cap, view) => {
    const b = el("button", "tile click", `<div class="num">${n}</div><div class="cap">${cap}</div>`);
    b.onclick = () => go(view); return b;
  };
  tiles.appendChild(tile(pf.count, "systems tracked", "registry"));
  tiles.appendChild(tile(pf.council_gated, "Council-gated", "process"));
  tiles.appendChild(tile(v.roadmap.foundations.length, "foundations first", "budget"));
  tiles.appendChild(tile(st.integrity.total, "integrity findings", "integrity"));
  root.appendChild(tiles);

  const vis = el("div", "panel");
  vis.innerHTML = `<h3 class="sub3" style="margin-top:0">The vision</h3>
    <p style="font-size:14px;margin:0 0 14px">${esc(v.vision)}</p>` +
    Object.entries(v.pillars).map(([k, t]) =>
      `<div class="step-row"><span class="step-dot" style="background:var(--accent-2)"></span>
       <div class="step-main"><div class="step-name">${esc(k)}</div>
       <div class="step-why">${esc(t)}</div></div></div>`).join("");
  root.appendChild(vis);

  const wp = el("div", "panel");
  wp.innerHTML = `<h3 class="sub3" style="margin-top:0">Whole of process</h3>
    <p class="intro">${esc(v.roadmap.narrative)}</p>
    <table><thead><tr><th>${esc(S.vocab.use_case_grouping ? "Grouping" : "Category")}</th>
    <th class="num">Projects</th><th class="num">Delivered</th>
    <th class="num">In pilot</th><th class="num">Maturity</th></tr></thead><tbody>` +
    [1, 2, 3].map((n) => { const c = v.category_maturity[n];
      return `<tr><td>${esc(vlabel("use_case_grouping", n))}</td>
        <td class="num">${c.count}</td><td class="num">${c.delivered}</td>
        <td class="num">${c.in_flight}</td><td class="num">${c.maturity}%</td></tr>`;
    }).join("") + `</tbody></table>` +
    (v.gaps.length ? `<h3 class="sub3">Gaps</h3><ul class="small muted">` +
      v.gaps.map((g) => `<li>${esc(g)}</li>`).join("") + `</ul>` : "");
  root.appendChild(wp);

  const pp = el("div", "panel");
  pp.innerHTML = `<h3 class="sub3" style="margin-top:0">Each project's contribution</h3>
    <table><thead><tr><th>Project</th><th>Pillar</th><th>Gate</th><th>Risk</th>
    <th>Contribution</th></tr></thead><tbody>` +
    v.per_project.slice(0, 10).map((p) =>
      `<tr class="click" data-id="${p.registry_id}"><td><b>${esc(p.registry_id)}</b><br>
       <span class="small muted">${esc(p.name.slice(0, 34))}</span></td>
       <td>${esc(p.pillar)}</td><td>${p.gate}</td>
       <td><span class="pill ${cls(p.risk)}">${esc(vlabel("risk_band", p.risk))}</span></td>
       <td class="small">${esc(p.contribution)}</td></tr>`).join("") + `</tbody></table>`;
  pp.querySelectorAll("tr[data-id]").forEach((tr) =>
    tr.onclick = () => { S.project = tr.dataset.id; S.gate = null; renderSpine(); go("workflow"); });
  root.appendChild(pp);

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "Why this is the home", body: "The strategic map is what you land on: the vision, how the pipeline climbs toward it, and the gaps between.", cite: v.citation },
    { title: "How maturity is read", body: "The portfolio climbs Category 1 → 2 → 3. Internal competence first, then public and economic benefit, then new capability.", cite: "SCDES AI Governance Framework §5" },
  ]);
};

VIEWS.registry = async () => {
  const d = await api("/api/registry");
  const cal = d.calibration;
  const p = el("div", "panel");
  p.innerHTML =
    `<p class="intro">${d.summary.count} systems · ${d.summary.council_gated} Council-gated.
     Seeded from Appendix A and the PermitPro analysis. Derived starting scores
     reproduce Appendix A's stated band in ${cal.agreed}/${cal.compared} cases —
     the differences mark the projects most worth confirming at Gate 0.</p>
     <table><thead><tr><th>ID</th><th>Project</th><th>Grouping</th><th>Stage</th>
     <th>Gate</th><th class="num">Composite</th><th>Risk</th></tr></thead><tbody>` +
    d.projects.map((x) =>
      `<tr class="click" data-id="${x.registry_id}"><td><b>${esc(x.registry_id)}</b></td>
       <td>${esc(x.name.slice(0, 40))}${x.scores_are_derived
         ? ' <span class="pill neutral">derived</span>' : ""}</td>
       <td>${esc(vlabel("use_case_grouping", x.category))}</td>
       <td>${esc(x.stage)}</td><td>${x.gate}</td><td class="num">${x.risk.total}</td>
       <td><span class="pill ${cls(x.risk.band)}">${esc(vlabel("risk_band", x.risk.band))}</span></td></tr>`
    ).join("") + `</tbody></table>`;
  p.querySelectorAll("tr[data-id]").forEach((tr) =>
    tr.onclick = () => { S.project = tr.dataset.id; S.gate = null; renderSpine(); go("workflow"); });
  $("#view").innerHTML = ""; $("#view").appendChild(p);
  reason([
    { title: "What this is", body: "Appendix C, the living inventory. Entries are submitted at intake and updated within ten business days of any status change.", cite: "SCDES AI Operations Manual §7 (AI System Registry Procedure)" },
    { title: "Why some scores say 'derived'", body: "Appendix A records a typical risk classification, not the six factor ratings. Those are proposed from its own columns and confirmed by an owner at Gate 0.", cite: "Appendix A — Instructions: risk levels are starting guidance only" },
  ]);
};

VIEWS.workflow = async () => {
  const q = "/api/workflow?id=" + encodeURIComponent(S.project) +
    (S.gate !== null ? "&gate=" + S.gate : "");
  const d = await api(q); const s = d.step;
  const root = el("div");

  const head = el("div", "panel");
  head.innerHTML = `<div class="spread"><div>
    <h3 class="sub3" style="margin-top:0">${esc(s.project_name)}</h3>
    <p class="intro" style="margin:0">Gate ${s.gate} — ${esc(s.gate_name)}</p></div>
    <div><span class="pill ${cls(s.risk_band)}">${esc(vlabel("risk_band", s.risk_band))}</span>
    ${s.council_required ? `<span class="pill info">${esc(vlabel("council_decision", "c"))} decision</span>` : ""}</div></div>
    <h3 class="sub3">Instruments due at this gate</h3>` +
    s.due_appendices.map((a) => `<span class="pill neutral">Appendix ${esc(a.letter)}</span> `).join("");
  root.appendChild(head);

  const chk = el("div", "panel");
  chk.innerHTML = `<h3 class="sub3" style="margin-top:0">Checklist — ${s.requirements.length} requirements</h3>` +
    (s.requirements.map((r) =>
      `<div class="req"><span class="n">${esc(r.number)}</span><span class="t">${esc(r.text)}</span></div>`
    ).join("") || `<p class="muted">No checklist parsed for this gate.</p>`);
  root.appendChild(chk);

  const form = el("div", "panel");
  form.innerHTML = `<h3 class="sub3" style="margin-top:0">Appendix ${esc(s.form_appendix)} —
    ${s.form.length} fields, ${Object.keys(s.prefilled).length} pre-filled</h3>`;
  const fields = el("div");
  s.form.slice(0, 20).forEach((f) => {
    const w = el("div", "ff");
    let c;
    if (f.control === "select" && f.options.length)
      c = `<select data-key="${f.key}"><option value=""></option>` +
        f.options.map((o) => `<option ${o === f.value ? "selected" : ""}>${esc(o)}</option>`).join("") + `</select>`;
    else if (f.control === "long_text")
      c = `<textarea rows="2" data-key="${f.key}">${esc(f.value || "")}</textarea>`;
    else c = `<input type="${f.control === "date" ? "date" : "text"}" data-key="${f.key}" value="${esc(f.value || "")}">`;
    w.innerHTML = `<label>${esc(f.label)}<span class="cell">${esc(f.cell)}</span></label>${c}` +
      (f.help ? `<div class="hint">${esc(f.help)}</div>` : "");
    fields.appendChild(w);
  });
  form.appendChild(fields);

  const row = el("div", "row");
  const save = el("button", "btn", `Save & request Gate ${s.gate + 1}`);
  save.onclick = async () => {
    const values = {};
    fields.querySelectorAll("[data-key]").forEach((i) => { if (i.value) values[i.dataset.key] = i.value; });
    save.disabled = true;
    const r = await post("/api/workflow/save", { registry_id: s.project_id,
      appendix: s.form_appendix, values, advance_to: s.gate + 1,
      note: `Gate ${s.gate} pack completed` });
    save.disabled = false;
    if (!r.written) return toast(r.decision || "Refused", true);
    toast(`${r.count} cells written. ${r.message || ""}`);
    await refreshState(); go("workflow");
  };
  row.appendChild(save);
  row.appendChild(el("span", "note", "The adopted template is copied into this project's folder and filled there — the master is never modified."));
  form.appendChild(row);
  root.appendChild(form);

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "Where this gate comes from", body: "The checklist is Appendix H, read directly. The instruments due are derived from its own requirement text plus the project's risk band.", cite: "Appendix H — Gate Review Checklists; SCDES AI Operations Manual §15" },
    { title: "Why it may not advance", body: s.council_required
        ? `At ${vlabel("risk_band", s.risk_band)} risk the gate decision is the Council's. Saving routes it rather than self-approving.`
        : "At Low risk bureau-level approval is sufficient, so saving advances the stage directly.",
      cite: "SCDES AI Operations Manual §6.2; Appendix N" },
  ]);
};

VIEWS.setup = async () => {
  const d = await api("/api/vocabulary");
  const root = el("div");

  if (!d.can_edit) {
    root.appendChild(el("div", "locked", `<b>Terminology is the Office of Technology's to set.</b>
      You are signed in as ${esc(S.state.actor.role)}. The vocabulary below is what
      the adopted documents actually use.`));
  }

  const intro = el("div", "panel");
  intro.innerHTML = `<p class="intro">Agencies name the same concepts differently —
    bucket or category, tier or level, A/B/C or 1/2/3. SCDES settled its naming in
    the Governance Framework; that fixed the Council Operating Procedures, which
    fixed the Operations Manual, which fixed all fourteen appendices. So this is
    <b>one choice made once</b>, and it cascades. The defaults below were read out
    of the adopted corpus, not assumed.</p>`;
  root.appendChild(intro);

  d.concepts.forEach((c) => {
    const w = el("div", "panel");
    const alt = Object.entries(c.alternatives_in_corpus || {})
      .map(([k, n]) => `${k} ×${n}`).join(", ");
    w.innerHTML =
      `<div class="field"><h4>${esc(c.title)}</h4>
       <p class="governs">${esc(c.governs)}</p>
       <div class="ctrl">
         <select data-role="noun" ${d.can_edit ? "" : "disabled"}>` +
           c.options.map((o) => `<option ${o === c.noun ? "selected" : ""}>${esc(o)}</option>`).join("") +
         `</select>
         <span class="val">${esc(Object.values(c.labels).join(" · "))}</span>
       </div>
       <div class="impact quiet"><b>In the corpus:</b> ${esc(c.evidence)}${alt ? " — " + esc(alt) : ""}.
         Applies to ${esc((c.surfaces || []).join(", "))}.</div></div>`;

    const sel = w.querySelector("[data-role=noun]");
    const box = w.querySelector(".impact");
    const val = w.querySelector(".val");
    sel.onchange = async () => {
      const p = await post("/api/vocabulary/preview", { concept: c.concept, noun: sel.value });
      val.textContent = Object.values(p.new_labels).join(" · ");
      box.className = "impact";
      box.innerHTML = `<b>Impact of this change:</b> ${esc(p.summary)}`;
    };

    if (d.can_edit) {
      const row = el("div", "row");
      const b = el("button", "btn", "Apply");
      b.onclick = async () => {
        const r = await post("/api/vocabulary/set", { concept: c.concept, noun: sel.value });
        if (!r.committed) return toast(r.reason, true);
        toast(`Terminology updated: ${r.impact.old_noun} → ${r.impact.new_noun}`);
        await refreshState(); go("setup");
      };
      row.appendChild(b);
      row.appendChild(el("span", "note", `Implements ${c.citation}`));
      w.appendChild(row);
    }
    root.appendChild(w);
  });

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "Why terminology comes first", body: "The Framework fixes the naming; everything downstream inherits it. Choosing here before the risk model or the budget means every later screen, checklist and cited answer speaks one language.", cite: "SCDES AI Governance Framework §5, §6" },
    { title: "What it does not do", body: "The app re-labels its own surfaces. It does not rewrite the adopted documents — those remain exactly as signed.", cite: "Appendix N — Framework and Appendix Amendments" },
  ]);
};

VIEWS.agency = async () => {
  const d = await api("/api/profile");
  const root = el("div");

  const head = el("div", "panel");
  head.innerHTML =
    `<p class="intro">Everything below was read out of the corpus on first run —
     no agency, instrument set, checkpoint structure or programme list is written
     into this application. Point it at another agency's documents and it
     re-derives all of it.</p>
     <table><tbody>
     <tr><th>Agency</th><td><b>${esc(d.name || "—")}</b>
       ${d.short_name ? `<span class="pill neutral">${esc(d.short_name)}</span>` : ""}</td></tr>
     <tr><th>Jurisdiction</th><td>${esc(d.jurisdiction || "—")}</td></tr>
     <tr><th>Adopted</th><td>${esc(d.adoption_date || "not stated in the corpus")}
       <br><span class="small muted">${esc(d.adoption_source || "")}</span></td></tr>
     <tr><th>Naming rule</th><td class="small">${esc(d.naming_rule || "—")}</td></tr>
     <tr><th>Discovered</th><td class="mono">${esc(d.discovered_at || "")}</td></tr>
     </tbody></table>`;
  root.appendChild(head);

  const inst = el("div", "panel");
  inst.innerHTML = `<h3 class="sub3" style="margin-top:0">Instruments —
    this agency calls them “${esc(d.instrument_noun)}”, and there are
    ${d.instruments.length}</h3>
    <table><thead><tr><th>Key</th><th>Title</th><th>Recognised as</th>
    <th class="num">Fields</th></tr></thead><tbody>` +
    d.instruments.map((i) => `<tr><td><b>${esc(i.key)}</b></td>
      <td>${esc(i.title || "—")}</td>
      <td>${i.role ? `<span class="pill info">${esc(i.role.replace(/_/g, " "))}</span>`
        : '<span class="pill neutral">unrecognised</span>'}</td>
      <td class="num">${i.fields || "—"}</td></tr>`).join("") + `</tbody></table>`;
  root.appendChild(inst);

  const life = el("div", "panel");
  life.innerHTML = `<h3 class="sub3" style="margin-top:0">Lifecycle —
    called “${esc(d.gate_noun)}”, ${d.gates.length} of them</h3>` +
    (d.gates.length ? d.gates.map((g) =>
      `<div class="req"><span class="n">${esc(g.key)}</span>
       <span class="t">${esc(g.name)}</span>
       <span class="small muted">${g.requirements} requirements</span></div>`).join("")
      : `<p class="muted">None discovered.</p>`);
  root.appendChild(life);

  const who = el("div", "panel");
  who.innerHTML = `<h3 class="sub3" style="margin-top:0">Read from the corpus</h3>
    <p class="gh">Roles named in the governing documents</p>
    ${d.roles.map((r) => `<span class="pill neutral">${esc(r)}</span> `).join("") || "—"}
    <p class="gh" style="margin-top:14px">Operating units (from the intake form's own picker)</p>
    ${d.org_units.map((u) => `<span class="pill neutral">${esc(u)}</span> `).join("") || "—"}
    <p class="gh" style="margin-top:14px">Statutory programmes referenced</p>
    ${d.statutory_programmes.map((p) => `<span class="pill info">${esc(p)}</span> `).join("") || "—"}`;
  if (d.notes && d.notes.length)
    who.innerHTML += `<div class="impact" style="margin-top:14px"><b>Gaps in discovery:</b><ul>` +
      d.notes.map((n) => `<li>${esc(n)}</li>`).join("") + `</ul></div>`;

  if (d.can_edit) {
    const row = el("div", "row");
    const b = el("button", "btn ghost", "Re-read the corpus");
    b.onclick = async () => {
      const r = await post("/api/profile/rediscover", {});
      toast(r.rediscovered ? "Profile re-derived from the corpus." : r.reason,
            !r.rediscovered);
      await refreshState(); go("agency");
    };
    row.appendChild(b);
    row.appendChild(el("span", "note",
      "Run this after the agency amends or replaces a document."));
    who.appendChild(row);
  }
  root.appendChild(who);

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "Why this exists", body: "The application is not built for one agency. It is pointed at an adopted corpus and works out whose it is, what the instruments are called, how many there are, and what the lifecycle looks like.", cite: "Discovered from the corpus; confirmed by OT" },
    { title: "What is never assumed", body: "That instruments are lettered A–N, that there are six gates, that the agency is environmental, or that a charter exists with a legible date. Each is read, and reported as a gap when it cannot be.", cite: "app/profile.py" },
  ]);
};

VIEWS.integrity = async () => {
  const d = await api("/api/integrity");
  const root = el("div");
  const c = d.counts || {};

  const tiles = el("div", "tiles");
  [["critical", "critical"], ["serious", "serious"], ["moderate", "moderate"]]
    .forEach(([k, cap]) => tiles.appendChild(
      el("div", "tile", `<div class="num">${c[k] || 0}</div><div class="cap">${cap}</div>`)));
  tiles.appendChild(el("div", "tile",
    `<div class="num">${d.stats.manual_sections || 0}</div><div class="cap">Manual sections</div>`));
  root.appendChild(tiles);

  const p = el("div", "panel");
  p.innerHTML = `<p class="intro">The Framework fixes naming and authority; that informs
    the Council Operating Procedures, then the Operations Manual, then every appendix.
    This walks that chain and reports where it does not hold. Nothing is corrected
    silently — this is the record that has to stand up later.</p>`;
  d.findings.forEach((f) => {
    const w = el("div", "finding " + f.severity);
    w.innerHTML = `<h4>${esc(f.title)}</h4><p>${esc(f.detail)}</p>` +
      (f.evidence || []).map((q) => `<div class="quote">${esc(q)}</div>`).join("") +
      (f.fix ? `<div class="fix">Fix: ${esc(f.fix)}</div>` : "") +
      (f.where && f.where.length
        ? `<div class="where">${esc(f.where.slice(0, 6).join(" · "))}${f.where.length > 6 ? " …" : ""}</div>` : "");
    p.appendChild(w);
  });
  root.appendChild(p);
  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "Why this exists", body: "The governance trail becomes a legally binding record. A citation that does not resolve, a date left blank, or a duty assigned to a role the Framework never established are all defects that surface at the worst moment.", cite: "SCDES AI Governance Adoption Directive" },
    { title: "What it will not do", body: "It reports and proposes. Correcting an adopted instrument is a Council amendment — propose, diff, approve, commit.", cite: "Appendix N — Framework and Appendix Amendments" },
  ]);
};

VIEWS.configure = async () => {
  const d = await api("/api/config");
  const root = el("div");
  if (S.state.actor.role !== "ot") {
    root.appendChild(el("div", "locked", `<b>Configure is the Office of Technology's room.</b>
      You are signed in as ${esc(S.state.actor.role)}. Switch to the OT user to tune parameters.`));
    $("#view").innerHTML = ""; $("#view").appendChild(root);
    reason([{ title: "Who may change this", body: "OT owns the operational configuration. In Operating Mode even OT must route a change through the Council.", cite: "SCDES AI Governance Framework §6" }]);
    return;
  }

  const intro = el("div", "panel");
  intro.innerHTML = `<p class="intro">The Council adopted the appendices as
    <em>templates</em>. This is where OT sets what SCDES actually needs. Move a
    control to preview its consequence before saving.
    <span class="mono">parameter set ${esc(d.parameter_set_hash)}</span></p>`;
  root.appendChild(intro);

  const panel = el("div", "panel");
  d.fields.forEach((f) => {
    const w = el("div", "field");
    const slider = f.control === "slider";
    w.innerHTML = `<h4>${esc(f.label)}</h4><p class="governs">${esc(f.governs)}</p>
      <div class="ctrl">` +
      (slider ? `<input type="range" min="${f.min}" max="${f.max}" step="${f.step}" value="${f.value}">`
              : `<input type="number" min="${f.min ?? 0}" step="${f.step ?? 1}" value="${f.value}">`) +
      `<span class="val">${f.key.includes("weight") ? "×" : ""}${f.value}</span></div>
       <div class="impact quiet"><b>Impact:</b> move the control to preview.</div>`;
    const inp = w.querySelector("input"), out = w.querySelector(".val"), box = w.querySelector(".impact");
    let timer;
    inp.oninput = () => {
      out.textContent = (f.key.includes("weight") ? "×" : "") + inp.value;
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const cq = await post("/api/config/preview", { key: f.key, value: inp.value });
        if (!cq.affected) { box.className = "impact quiet";
          box.innerHTML = `<b>Impact:</b> ${esc(cq.summary)}`; return; }
        box.className = "impact";
        box.innerHTML = `<b>Impact:</b> ${esc(cq.summary)}<ul>` +
          cq.reclassified.slice(0, 5).map((r) =>
            `<li>${esc(r.name.slice(0, 42))} — <b>${esc(vlabel("risk_band", r.from))} → ${esc(vlabel("risk_band", r.to))}</b>
             (${r.score_before} → ${r.score_after})</li>`).join("") + `</ul>`;
      }, 170);
    };
    const row = el("div", "row");
    const b = el("button", "btn", "Review & save");
    b.onclick = async () => {
      const r = await post("/api/config/edit", { key: f.key, value: inp.value });
      if (!r.committed) return toast(r.reason, true);
      toast(`Saved. ${r.consequence.summary}`); await refreshState(); go("configure");
    };
    row.appendChild(b); row.appendChild(el("span", "note", `Implements ${esc(f.citation)}`));
    w.appendChild(row);
    panel.appendChild(w);
  });
  root.appendChild(panel);
  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "Why previewing matters", body: "The point is not to guess a number on paper. Moving a weight shows which projects reclassify, which gates newly trigger and which instruments become required — before anything is saved.", cite: "Appendix B — AI Risk Classification Matrix" },
    { title: "What happens next", body: "When the set is right, OT proposes it and the Council adopts it. The guardrails then activate and every later change routes through the Council.", cite: "SCDES AI Governance Framework §6; Appendix N" },
  ]);
};

VIEWS.budget = async () => {
  const d = await api("/api/budget"); const r = d.roadmap;
  const root = el("div");

  const tiles = el("div", "tiles");
  tiles.appendChild(el("div", "tile",
    `<div class="num">${money(d.pools.recurring_per_year)}</div><div class="cap">recurring / year</div>`));
  tiles.appendChild(el("div", "tile",
    `<div class="num">${money(d.pools.one_time)}</div><div class="cap">one-time</div>`));
  tiles.appendChild(el("div", "tile",
    `<div class="num">${money(r.totals.one_time)}</div><div class="cap">roadmap one-time need</div>`));
  root.appendChild(tiles);

  const recs = el("div", "panel");
  recs.innerHTML = `<h3 class="sub3" style="margin-top:0">Weighted recommendation</h3>
    <table><thead><tr><th>#</th><th>Vendor</th><th>Verdict</th><th class="num">Score</th>
    <th>Risk</th><th>Budget</th></tr></thead><tbody>` +
    d.detail.map((x, i) =>
      `<tr><td>${i + 1}</td><td><b>${esc(x.vendor)}</b><br>
       <span class="small muted">${esc(x.product)}</span></td>
       <td><span class="pill ${x.verdict === "buy" ? "ok" : x.verdict === "pass" ? "bad" : "neutral"}">${x.verdict}</span></td>
       <td class="num">${x.score}</td>
       <td><span class="pill ${cls(x.risk)}">${esc(vlabel("risk_band", x.risk))}</span></td>
       <td>${x.over_budget ? '<span class="pill bad">over</span>' : '<span class="pill ok">fits</span>'}</td></tr>
       <tr><td></td><td colspan="5" class="small muted">${x.rationale.map(esc).join("<br>")}</td></tr>`
    ).join("") + `</tbody></table>`;
  root.appendChild(recs);

  const sc = el("div", "panel");
  sc.innerHTML = `<h3 class="sub3" style="margin-top:0">Scenario</h3>
    <p class="intro">Delta Bravo quotes $1,880,000 as an annual licence, over the
    recurring pool. Re-typed one-time against a build pool it fits — and the
    ranking changes. The budget of record does not move.</p>`;
  const out = el("div");
  const b = el("button", "btn", "Run the Delta Bravo scenario");
  b.onclick = async () => {
    out.innerHTML = `<p class="muted">Running…</p>`;
    const s = await post("/api/budget/scenario", { preset: "delta_bravo" });
    out.innerHTML = `<div class="impact quiet" style="margin-bottom:10px"><b>Result:</b> ${esc(s.narrative)}</div>` +
      `<table><thead><tr><th>#</th><th>Vendor</th><th>Verdict</th><th class="num">Score</th><th>Budget</th></tr></thead><tbody>` +
      s.after.map((a, i) => `<tr><td>${i + 1}</td><td>${esc(a.vendor)}</td>
        <td><span class="pill ${a.verdict === "buy" ? "ok" : "neutral"}">${a.verdict}</span></td>
        <td class="num">${a.score}</td>
        <td>${a.over_budget ? '<span class="pill bad">over</span>' : '<span class="pill ok">fits</span>'}</td></tr>`).join("") +
      `</tbody></table>`;
  };
  sc.appendChild(b); sc.appendChild(out);
  root.appendChild(sc);

  const rm = el("div", "panel");
  rm.innerHTML = `<h3 class="sub3" style="margin-top:0">Vision → funded roadmap</h3>
    <p class="intro">${esc(r.narrative)}</p><p class="wave">Foundations — must exist first</p>` +
    r.foundations.map((f) => `<div class="step-row">
      <span class="step-dot" style="background:var(--accent-2)"></span>
      <div class="step-main"><div class="step-name">${esc(f.label)}</div>
      <div class="step-why">wave ${f.wave} · ${esc(f.why.slice(0, 78))}</div></div>
      <span class="pill neutral">${esc(f.status.replace("_", " "))}</span>
      <span class="step-cost">${money(f.one_time)}</span></div>`).join("") +
    `<p class="wave">Projects — unlocked once the foundations land</p>` +
    r.projects.map((p) => `<div class="step-row">
      <span class="step-dot" style="background:var(--accent)"></span>
      <div class="step-main"><div class="step-name">${esc(p.label)}</div>
      <div class="step-why">wave ${p.wave} · ${esc(p.why)}</div></div>
      <span class="pill ${p.status === "blocked" ? "bad" : "ok"}">${p.status}</span>
      <span class="step-cost">${money(p.one_time + p.recurring)}</span></div>`).join("");
  root.appendChild(rm);

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "Why pools, not a number", body: "A licence and a build are different money. Each quote is cost-typed and scored against the matching pool, which is why re-typing a quote can change the ranking without the budget moving.", cite: "SCDES AI Operations Manual §9–10" },
    { title: "Why foundations come first", body: "Projects declare the capabilities they need; foundations declare what they provide. The app computes the unmet set, orders it and costs it. The dependencies are OT's to author — the documents do not state them.", cite: "SCDES AI Operations Manual §8, §20" },
  ]);
};

VIEWS.oversight = async () => {
  const d = await api("/api/oversight");
  const root = el("div");
  const st = el("div", "panel");
  st.innerHTML = `<div class="spread"><div><h3 class="sub3" style="margin-top:0">
    ${d.status.standby ? "On standby" : d.status.active_incidents + " active incident(s)"}</h3>
    <p class="intro" style="margin:0">${d.status.monitored_systems} system(s) carry monitoring obligations.</p></div>
    <div>${d.status.standby ? '<span class="pill ok">Clear</span>'
      : `<span class="pill bad">${esc(vlabel("incident_severity", d.status.highest_level))}</span>`}</div></div>`;
  root.appendChild(st);

  const inc = el("div", "panel");
  inc.innerHTML = `<h3 class="sub3" style="margin-top:0">Incidents</h3>` +
    (d.incidents.length ? d.incidents.map((i) =>
      `<div class="entry"><time>${esc(i.detected_at.slice(0, 16))}</time>
       <span class="k ${i.level >= 2 ? "deny" : "dec"}">${esc(vlabel("incident_severity", i.level))}</span>
       <p><b>${esc(i.incident_id)}</b> — ${esc(i.summary)}<br>
       <span class="small muted">${esc(i.system_name)} · ${esc(i.status)} · ${i.obligations.length} obligations</span></p></div>`
    ).join("") : `<p class="muted">No incidents recorded.</p>`);
  root.appendChild(inc);

  const reg = el("div", "panel");
  reg.innerHTML = `<h3 class="sub3" style="margin-top:0">Monitoring register</h3>
    <p class="intro">No production telemetry is connected. This is the register of
    what is owed and when — not invented metrics.</p>` +
    (d.register.length ? `<table><thead><tr><th>System</th><th>Risk</th><th>Cadence</th>
      <th>Obligations</th></tr></thead><tbody>` + d.register.map((x) =>
      `<tr><td><b>${esc(x.registry_id)}</b></td>
       <td><span class="pill ${cls(x.risk)}">${esc(vlabel("risk_band", x.risk))}</span></td>
       <td>${esc(x.cadence)}</td>
       <td class="small">${x.obligations.map((o) => esc(o.what)).join("<br>")}</td></tr>`).join("") +
      `</tbody></table>` : `<p class="muted">Nothing in pilot or production.</p>`);
  root.appendChild(reg);

  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "What happens at Level 2", body: "The operational owner suspends the system immediately, the Council Chair is notified within 24 hours, and a root-cause analysis and lookback are required before resuming.", cite: "SCDES AI Operations Manual §22.4 (Level 2 Procedure)" },
    { title: "Why there are no charts", body: "No production model telemetry exists yet. Showing invented drift numbers would be worse than showing what is owed.", cite: "SCDES AI Operations Manual §6.5 (Model Drift Monitoring)" },
  ]);
};

VIEWS.process = async () => {
  const p = await api("/api/process");
  const root = el("div");
  const g = el("div", "panel");
  g.innerHTML = `<h3 class="sub3" style="margin-top:0">Gates</h3>
    <p class="intro">The gate → instrument map is derived by reading Appendix H's own
    requirement text, not hardcoded.</p>
    <table><thead><tr><th>Gate</th><th>Name</th><th class="num">Requirements</th>
    <th>Instruments</th></tr></thead><tbody>` +
    p.gates.map((x) => `<tr><td><b>${x.gate}</b></td><td>${esc(x.name)}</td>
      <td class="num">${x.requirements}</td>
      <td>${x.appendices.map((a) => `<span class="pill neutral">${a}</span>`).join(" ")}</td></tr>`).join("") +
    `</tbody></table>`;
  root.appendChild(g);

  const b = el("div", "panel");
  b.innerHTML = `<h3 class="sub3" style="margin-top:0">Risk bands</h3>
    <table><thead><tr><th>Band</th><th>Approval</th><th>Review</th><th>Instruments</th></tr></thead><tbody>` +
    Object.entries(p.bands).map(([band, x]) =>
      `<tr><td><span class="pill ${cls(band)}">${esc(vlabel("risk_band", band))}</span></td>
       <td class="small">${esc(x.approval)}</td><td>${esc(x.cadence)}</td>
       <td class="small">${x.appendices.join(", ")}</td></tr>`).join("") + `</tbody></table>
    <h3 class="sub3">Council decision levels</h3>` +
    Object.entries(p.tiers).map(([t, rule]) =>
      `<div class="req"><span class="n">${esc(vlabel("council_decision", t).split(" ").pop())}</span>
       <span class="t">${esc(rule)}</span></div>`).join("");
  root.appendChild(b);
  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "Where the gates come from", body: "Appendix H holds one checklist per gate. The app reads them rather than restating them, so a change to the appendix changes the app.", cite: "Appendix H; SCDES AI Operations Manual §15" },
  ]);
};

VIEWS.council = async () => {
  const d = await api("/api/council");
  const root = el("div");
  if (!d.is_member)
    root.appendChild(el("div", "locked", `<b>The Council is a gated room.</b>
      The decision log is readable for transparency, but only members amend the
      Framework, decide gates, or move the mode.`));

  const head = el("div", "panel");
  head.innerHTML = `<p class="intro">Append-only. Mode <b>${esc(d.mode)}</b> ·
    <span class="mono">parameter set ${esc(d.parameter_set_hash)}</span></p>`;
  if (d.is_member && d.mode === "configuration") {
    const b = el("button", "btn", "Adopt the tuned parameter set → activate guardrails");
    b.onclick = async () => {
      const r = await post("/api/council/adopt", {
        members_present: ["council.cto", "council.gc", "council.water"],
        summary: "Tuned parameter set adopted; change guardrails activated." });
      if (!r.adopted) return toast(r.reason, true);
      toast("Operating Mode. Every governed change now routes through the Council.");
      await refreshState(); go("council");
    };
    head.appendChild(b);
  }
  root.appendChild(head);

  const log = el("div", "panel");
  log.innerHTML = `<h3 class="sub3" style="margin-top:0">Decision log</h3>` +
    (d.decisions.length ? d.decisions.map((x) =>
      `<div class="entry"><time>${esc((x.at || "").slice(0, 16))}</time>
       <span class="k dec">${esc(vlabel("council_decision", (x.tier || "b").toLowerCase()))}</span>
       <p>${esc(x.summary)}${x.status === "awaiting_decision"
         ? ' <span class="pill neutral">awaiting</span>' : ""}
       <br><span class="mono">${esc(x.decision_id)}</span></p></div>`).join("")
      : `<p class="muted">No decisions recorded.</p>`);
  root.appendChild(log);

  const pending = d.decisions.filter((x) => x.status === "awaiting_decision");
  if (d.is_member && pending.length) {
    const p = el("div", "panel");
    p.innerHTML = `<h3 class="sub3" style="margin-top:0">Awaiting a decision</h3>`;
    pending.forEach((x) => {
      const w = el("div", "req");
      w.innerHTML = `<span class="t"><b>${esc(x.decision_id)}</b> — ${esc(x.summary)}</span>`;
      const ok = el("button", "btn", "Approve");
      ok.onclick = async () => {
        const r = await post("/api/council/decide", { decision_id: x.decision_id,
          outcome: "approved",
          members_present: ["council.cto", "council.gc", "council.water"],
          rationale: "Convened session — consensus." });
        toast(r.decided ? "Approved." : r.reason, !r.decided);
        await refreshState(); go("council");
      };
      w.appendChild(ok); p.appendChild(w);
    });
    root.appendChild(p);
  }
  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "The second adoption", body: "The Council adopted the appendices as templates. Adopting the tuned parameter set is a distinct act — it is what activates the change guardrails.", cite: "Appendix N — Adoption; SCDES AI Governance Framework §6" },
  ]);
};

VIEWS.audit = async () => {
  const d = await api("/api/audit");
  const root = el("div");
  const head = el("div", "panel");
  head.innerHTML = `<div class="spread"><div>
    <h3 class="sub3" style="margin-top:0">Hash-chained record</h3>
    <p class="intro" style="margin:0">Every governed attempt, granted and refused.</p></div>
    <div>${d.intact ? '<span class="pill ok">chain intact</span>' : '<span class="pill bad">BROKEN</span>'}</div></div>
    <p class="mono">${esc(d.message)}</p>`;
  root.appendChild(head);
  const log = el("div", "panel");
  log.innerHTML = d.entries.map((e) =>
    `<div class="entry"><time>${esc(e.at.slice(0, 16))}</time>
     <span class="k ${e.outcome === "denied" ? "deny" : "allow"}">${esc(e.outcome)}</span>
     <p><b>${esc(e.actor)}</b> ${esc(e.action)} → ${esc(e.target)}
     <br><span class="small muted">${esc((e.detail && e.detail.reason) || "")}</span>
     <br><span class="mono">#${e.seq} ${esc((e.hash || "").slice(0, 12))}</span></p></div>`).join("");
  root.appendChild(log);
  $("#view").innerHTML = ""; $("#view").appendChild(root);
  reason([
    { title: "What this proves", body: "Each entry hashes the one before it, so editing or removing a past entry breaks the chain and verification names the entry.", cite: "SCDES AI Operations Manual §7 (documentation and decision record)" },
    { title: "What it does not prove", body: "It is tamper-evident, not tamper-proof: anyone with file access could rewrite the chain from the start. A signed or append-only store would close that.", cite: "README — open decisions" },
  ]);
};

/* ------------------------------------------------------------------ init */

// Only items that name a view navigate. "Choose agency" is a .rail-item too but
// carries no data-view, and without this filter it also fired go(undefined),
// blanking the record behind the launcher.
document.querySelectorAll(".rail-item[data-view]").forEach((b) =>
  b.addEventListener("click", () => go(b.dataset.view)));
// Same for the chips; the agency chip has its own handler.
document.querySelectorAll(".tb-chip[data-view]").forEach((b) =>
  b.addEventListener("click", () => go(b.dataset.view)));

/* Keyboard navigation for the rail.
 *
 * These are ordinary <button>s in a <nav>, so Tab has always walked them but
 * arrow keys did nothing — browsers only move focus with arrows inside composite
 * widgets (radio groups, listboxes, toolbars), and that has to be implemented.
 *
 * Up/Down move focus and wrap, Home/End jump to the ends, and typing a letter
 * jumps to the next item starting with it. Enter or Space opens the focused
 * item. Focus moves without selecting on purpose: this is a navigation
 * landmark, and arrowing past six sections should not load six views.
 *
 * Tab stops are left intact rather than collapsed into a single roving one —
 * Tab walking a nav is what most people expect of a sidebar, so this is added
 * on top of that behaviour rather than replacing it.
 */
function railItems() {
  return [...document.querySelectorAll(".rail-item")]
    .filter((b) => b.offsetParent !== null && !b.disabled);
}

/** The item's own label, without its icon glyph or its OT/GATED tag. */
function railLabel(button) {
  const own = [...button.childNodes]
    .find((n) => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
  return (own ? own.textContent : button.textContent).trim().toLowerCase();
}

$(".rail").addEventListener("keydown", (e) => {
  if (e.altKey || e.ctrlKey || e.metaKey) return;
  const items = railItems();
  const at = items.indexOf(document.activeElement);
  if (at === -1) return;                 // focus is in the rail but not on an item

  let to = null;
  if (e.key === "ArrowDown") to = (at + 1) % items.length;
  else if (e.key === "ArrowUp") to = (at - 1 + items.length) % items.length;
  else if (e.key === "Home") to = 0;
  else if (e.key === "End") to = items.length - 1;
  else if (e.key.length === 1 && /\S/.test(e.key)) {
    // Search from the item after the current one, so repeats cycle matches.
    const key = e.key.toLowerCase();
    const order = [...items.slice(at + 1), ...items.slice(0, at + 1)];
    const hit = order.find((b) => railLabel(b).startsWith(key));
    if (hit) { e.preventDefault(); hit.focus(); }
    return;
  } else return;

  e.preventDefault();                    // otherwise Up/Down scrolls the page
  items[to].focus();
});
$("#spineProj").onclick = () => go("registry");
$("#reasonToggle").onclick = () => $(".shell").classList.toggle("no-reason");
$("#userPick").addEventListener("change", async (e) => {
  S.user = e.target.value; await refreshState(); go(S.view);
});

// Two ways in: the rail button, and the #agency URL so the picker can be linked
// to or bookmarked.
const showLauncher = () => {
  if (window.openLauncher) window.openLauncher();
  else location.reload();          // launcher.js failed to load — force a fetch
};
$("#railLaunch").onclick = showLauncher;
$("#tourChip").onclick = () => window.startTour && window.startTour(true);
window.addEventListener("hashchange", () => {
  if (location.hash === "#agency") showLauncher();
});
window.toast = toast;   // the launcher reports theme changes through the same toast

/* The sign-in step hands the chosen identity back here. Everything downstream —
   which rooms are writable, whose name lands in the audit entry — follows from
   this one value, so it is set in exactly one place. */
window.signInAs = async (id) => {
  if (!id) return;
  S.user = id;
  window.SCDES_USER = id;
  await refreshState();
  go(S.view || "vision");
  const who = (S.state && S.state.actor) || {};
  toast(`Signed in as ${who.name || id}${who.role ? " · " + who.role : ""}`);
};

(async () => {
  window.SCDES_USER = S.user;
  // Build the launcher first and independently: if the main app fails to
  // load, the agency picker should still work rather than open blank.
  try {
    if (window.initLauncher) await window.initLauncher();
  } catch (err) {
    console.error("launcher failed to initialise", err);
  }
  // Light/dark must work even if the launcher above threw. Idempotent, so this
  // is a no-op when initLauncher already wired it.
  if (window.initColorMode) window.initColorMode();
  await refreshState();
  go("vision");

  // Offer the tour once, and only after the launcher has been dismissed —
  // spotlighting the header while the map covers it would explain nothing.
  if (window.startTour && window.tourSeen && !window.tourSeen()) {
    const offer = () => {
      if (!$("#launcher").hidden) return;      // still on the map; wait
      document.removeEventListener("click", offer);
      setTimeout(() => window.startTour(true), 400);
    };
    if ($("#launcher").hidden) offer();
    else document.addEventListener("click", offer);
  }
})();
