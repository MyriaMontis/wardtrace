// WardTrace frontend: plain JS + Cytoscape.js (PLAN.md 10章)

const $ = (sel) => document.querySelector(sel);
let cy = null;
let persons = [];

// ---------------------------------------------------------------- helpers

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* ignore */ }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function badge(status) {
  const label = { fever_negative: "fever, negative" }[status] || status;
  return `<span class="badge ${esc(status)}">${esc(label)}</span>`;
}

function shortDate(d) {
  return d ? d.slice(5).replace("-", "/") : "";
}

function personById(id) {
  return persons.find((p) => p.id === id);
}

function setStatus(text) {
  $("#status").textContent = text || "";
}

async function busy(button, label, fn) {
  const old = button.innerHTML;  // 日本語の <span class="ja"> も含めて戻す
  button.disabled = true;
  button.textContent = label;
  try {
    await fn();
  } catch (e) {
    setStatus(`Error: ${e.message}`);
    console.error(e);
  } finally {
    button.disabled = false;
    button.innerHTML = old;
  }
}

function showTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) =>
    t.classList.toggle("active", t.id === `tab-${name}`));
}

// ---------------------------------------------------------------- graph

const STYLE = [
  { selector: "node", style: {
    "label": "data(label)", "font-size": 9, "color": "#1f2937",
    "text-valign": "bottom", "text-margin-y": 2,
    "width": 20, "height": 20, "background-color": "#94a3b8",
    "border-width": 0, "transition-property": "opacity, background-color",
    "transition-duration": "250ms",
  } },
  { selector: "node[kind = 'staff']", style: { "shape": "round-rectangle", "background-color": "#64748b" } },
  { selector: "node.gen1", style: { "background-color": "#f97316", "width": 26, "height": 26, "font-size": 11, "font-weight": "bold" } },
  { selector: "node.gen2", style: { "background-color": "#facc15", "width": 22, "height": 22 } },
  { selector: "node[status = 'positive']", style: { "background-color": "#dc2626" } },
  { selector: "node[status = 'fever_negative']", style: {
    "background-color": "#d1d5db", "border-width": 2, "border-style": "dashed", "border-color": "#6b7280",
  } },
  { selector: "node.index", style: { "width": 36, "height": 36, "font-size": 13, "font-weight": "bold" } },
  { selector: "node.candidate", style: {
    "border-width": 7, "border-color": "#b91c1c", "border-style": "solid",
    "width": 40, "height": 40, "font-size": 14, "font-weight": "bold",
    "underlay-color": "#fca5a5", "underlay-opacity": 0.45, "underlay-padding": 8,
  } },
  { selector: "node.hit", style: { "border-width": 4, "border-color": "#2563eb", "width": 28, "height": 28, "font-weight": "bold" } },
  { selector: "node:selected", style: { "overlay-color": "#2563eb", "overlay-opacity": 0.18, "overlay-padding": 6 } },
  { selector: "edge", style: {
    "width": 1, "line-color": "#cbd5e1", "opacity": 0.55, "curve-style": "haystack",
    "line-style": "solid",
  } },
  { selector: "edge.trace1", style: { "width": 3, "line-color": "#f97316", "opacity": 1 } },
  { selector: "edge.trace2", style: { "width": 1.6, "line-color": "#eab308", "opacity": 0.9 } },
  { selector: "edge.source-edge", style: { "width": 3.5, "line-color": "#dc2626", "opacity": 1 } },
  { selector: ".dim", style: { "opacity": 0.12 } },
  { selector: "edge.dim", style: { "opacity": 0.04 } },
];

function initGraph(graph) {
  if (cy) cy.destroy();
  cy = cytoscape({
    container: $("#cy"),
    elements: [...graph.nodes, ...graph.edges],
    style: STYLE,
    wheelSensitivity: 0.25,
    minZoom: 0.3,
    maxZoom: 3,
  });
  runCose(false);
  cy.on("tap", "node", (evt) => showPersonContacts(evt.target.id()));
}

function runCose(animate) {
  cy.layout({
    name: "cose", animate, animationDuration: 500, randomize: !animate,
    nodeRepulsion: () => 9000, idealEdgeLength: () => 60, padding: 30,
  }).run();
}

function clearHighlights() {
  cy.elements().removeClass("gen1 gen2 index candidate hit dim trace1 trace2 source-edge");
}

function updateNodeData(p) {
  const n = cy.getElementById(p.id);
  if (n.nonempty()) n.data("status", p.status);
}

// ---------------------------------------------------------------- 1. mark positive

function fillPersonSelect() {
  const sel = $("#person");
  const current = sel.value || "P12";
  sel.innerHTML = persons.map((p) =>
    `<option value="${esc(p.id)}">${esc(p.id)} ${esc(p.name)} · ${esc(p.kind === "staff" ? p.role : "room " + p.room_id)} · ${esc(p.status)}</option>`).join("");
  sel.value = current;
}

function prefillDates() {
  // 記録済みの検査日・発症日があれば入れる（デモの P12 は untested だが 10/16 検査・10/15 発症が記録済み）。
  // なければ検査日 10/16・発症日は空
  const p = personById($("#person").value);
  $("#test-date").value = (p && p.test_date) || "2026-10-16";
  $("#onset-date").value = (p && p.onset_date) || "";
}

async function markPositive() {
  const id = $("#person").value;
  const body = { id, test_date: $("#test-date").value };
  if (!body.test_date) throw new Error("Set a test date");
  if ($("#onset-date").value) body.onset_date = $("#onset-date").value;
  const p = await api("/api/positive", body);
  const i = persons.findIndex((x) => x.id === id);
  if (i >= 0) Object.assign(persons[i], { status: p.status, test_date: p.test_date, onset_date: p.onset_date });
  fillPersonSelect();
  updateNodeData(p);
  setStatus(`${id} marked positive (test ${shortDate(p.test_date)}${p.onset_date ? ", onset " + shortDate(p.onset_date) : ""})`);
  await trace();
}

// ---------------------------------------------------------------- 2. trace

function depth() {
  return Number(document.querySelector("input[name=depth]:checked").value);
}

async function trace() {
  const indexId = $("#person").value;
  const res = await api("/api/trace", { index_id: indexId, depth: depth() });
  renderTraceGraph(res);
  renderTraceTable(res);
  showTab("contacts");
  const ignored = res.second_gen_if_time_ignored;
  setStatus(`Traced ${indexId}: ${res.first_gen.length} first-gen, ${res.second_gen.length} second-gen` +
    (ignored === null || ignored === undefined ? "" : ` (${ignored} if time order ignored)`));
}

function renderTraceGraph(res) {
  clearHighlights();
  const gen = {};
  res.graph.nodes.forEach((n) => { gen[n.data.id] = n.data.gen; });
  res.graph.nodes.forEach((n) => updateNodeData(n.data));
  const index = res.index.id;
  const trace1 = new Set(res.first_gen.map((p) => [index, p.id].sort().join("-")));
  const trace2 = new Set(res.second_gen.map((p) => [p.via, p.id].sort().join("-")));

  cy.batch(() => {
    cy.nodes().forEach((n) => {
      const g = gen[n.id()];
      if (g === 0) n.addClass("index");
      else if (g === 1) n.addClass("gen1");
      else if (g === 2) n.addClass("gen2");
      else n.addClass("dim");
    });
    cy.edges().forEach((e) => {
      if (trace1.has(e.id())) e.addClass("trace1");
      else if (trace2.has(e.id())) e.addClass("trace2");
      else e.addClass("dim");
    });
  });

  // 起点を中心に、1段目・2段目・無関係の順に外側へ広がる配置。関係者にズームする
  const related = cy.nodes().filter((n) => gen[n.id()] !== null && gen[n.id()] !== undefined);
  const layout = cy.layout({
    name: "concentric",
    concentric: (n) => ({ 0: 3, 1: 2, 2: 1 }[gen[n.id()]] ?? 0),
    levelWidth: () => 1,
    minNodeSpacing: 14,
    animate: true,
    animationDuration: 600,
    fit: false,
  });
  layout.one("layoutstop", () => cy.animate({ fit: { eles: related, padding: 50 }, duration: 400 }));
  layout.run();
}

function contactSummary(contacts, withRoom = true) {
  const byType = {};
  contacts.forEach((c) => {
    (byType[c.type] = byType[c.type] || []).push(c);
  });
  return Object.entries(byType).map(([type, cs]) => {
    const dates = cs.map((c) => shortDate(c.date)).join(", ");
    const room = withRoom && cs[0].room_id ? ` <span class="muted">(${esc(cs[0].room_id)})</span>` : "";
    return `${esc(type.replace("_", " "))}: ${esc(dates)}${room}`;
  }).join("<br>");
}

// 2段目の人数。depth 2 なら時間順を無視した場合の人数も並べる（例：26 (34 if time order ignored)）
function secondGenCount(res) {
  const n = res.second_gen.length;
  if (res.second_gen_if_time_ignored === null || res.second_gen_if_time_ignored === undefined) {
    return `(${n}, depth 1)`;
  }
  return `<b>${n}</b> time-respecting <span class="ignored">(${res.second_gen_if_time_ignored} if time order ignored)</span>`;
}

function renderTraceTable(res) {
  const w = res.window;
  const end = w.end === "2099-12-31" ? "not isolated" : shortDate(w.end);
  const first = res.first_gen.map((p) => `
    <tr data-id="${esc(p.id)}">
      <td class="id">${esc(p.id)}</td><td>${esc(p.name)}</td>
      <td>${esc(p.kind)}</td><td>${badge(p.status)}</td>
      <td>${contactSummary(p.contacts)}</td>
    </tr>`).join("");
  const second = res.second_gen.map((p) => `
    <tr data-id="${esc(p.id)}">
      <td class="id">${esc(p.id)}</td><td>${badge(p.status)}</td>
      <td>via <b>${esc(p.via)}</b></td>
      <td>${contactSummary(p.contacts, false)}</td>
    </tr>`).join("");
  $("#tab-contacts").innerHTML = `
    <p class="summary">Index <b>${esc(res.index.id)}</b> ${esc(res.index.name)} ${badge(res.index.status)}
      · infectious window <b>${shortDate(w.start)} → ${end}</b></p>
    <div class="cols">
      <div>
        <h3>1st generation <span class="count">(${res.first_gen.length})</span></h3>
        <table><thead><tr><th>ID</th><th>Name</th><th>Kind</th><th>Status</th><th>Close contacts</th></tr></thead>
        <tbody>${first || `<tr><td colspan="5" class="muted">None</td></tr>`}</tbody></table>
      </div>
      <div>
        <h3>2nd generation <span class="count">${secondGenCount(res)}</span></h3>
        <table><thead><tr><th>ID</th><th>Status</th><th>Via</th><th>Contact (≥ 1 day after)</th></tr></thead>
        <tbody>${second || `<tr><td colspan="4" class="muted">${depth() === 1 ? "Set depth 2 to see the second generation." : "None"}</td></tr>`}</tbody></table>
      </div>
    </div>`;
  bindRowClicks("#tab-contacts");
}

function bindRowClicks(root) {
  document.querySelectorAll(`${root} tbody tr[data-id]`).forEach((tr) => {
    tr.addEventListener("click", () => focusNode(tr.dataset.id));
  });
}

function focusNode(id) {
  const n = cy.getElementById(id);
  if (n.empty()) return;
  cy.elements().unselect();
  n.select();
  cy.animate({ center: { eles: n }, duration: 300 });
}

// ---------------------------------------------------------------- node click

function showPersonContacts(id) {
  const n = cy.getElementById(id);
  const p = personById(id) || n.data();
  const rows = n.connectedEdges().map((e) => {
    const other = e.source().id() === id ? e.target() : e.source();
    return { id: other.id(), status: other.data("status"), types: e.data("types"), dates: e.data("dates") };
  }).sort((a, b) => a.id.localeCompare(b.id));
  $("#tab-contacts").innerHTML = `
    <p class="summary"><b>${esc(id)}</b> ${esc(p.name)} · ${esc(p.kind === "staff" ? p.role : "room " + p.room_id)} ${badge(n.data("status"))}
      · ${rows.length} people with close contact (Oct 10–16)</p>
    <table><thead><tr><th>ID</th><th>Status</th><th>Type</th><th>Dates</th></tr></thead>
    <tbody>${rows.map((r) => `
      <tr data-id="${esc(r.id)}"><td class="id">${esc(r.id)}</td><td>${badge(r.status)}</td>
      <td>${esc(r.types.join(", ").replaceAll("_", " "))}</td><td>${esc(r.dates.map(shortDate).join(", "))}</td></tr>`).join("")}
    </tbody></table>`;
  bindRowClicks("#tab-contacts");
  showTab("contacts");
}

// ---------------------------------------------------------------- 3. source

async function findSource() {
  const rows = await api("/api/source");
  clearHighlights();
  const keep = new Set();
  cy.batch(() => {
    rows.forEach((r) => {
      cy.getElementById(r.person.id).addClass("candidate");
      keep.add(r.person.id);
      r.linked_positive_ids.forEach((pid) => {
        keep.add(pid);
        cy.getElementById([r.person.id, pid].sort().join("-")).addClass("source-edge");
      });
    });
    cy.nodes().forEach((n) => { if (!keep.has(n.id())) n.addClass("dim"); });
    cy.edges().forEach((e) => { if (!e.hasClass("source-edge")) e.addClass("dim"); });
  });
  if (rows.length) {
    cy.animate({ fit: { eles: cy.nodes().filter((n) => keep.has(n.id())), padding: 120 }, duration: 500 });
  }
  renderSourceTable(rows);
  showTab("source");
  setStatus(rows.length ? `Top source candidate: ${rows[0].person.id} (linked to ${rows[0].n} positives)` : "No source candidate");
}

function renderSourceTable(rows) {
  const fever = persons.filter((p) => p.status === "fever_negative").map((p) => p.id);
  const positives = persons.filter((p) => p.status === "positive").map((p) => p.id);
  const body = rows.map((r, i) => {
    const byPos = {};
    r.contacts.forEach((c) => { (byPos[c.positive_id] = byPos[c.positive_id] || []).push(c); });
    const detail = Object.entries(byPos).map(([pid, cs]) =>
      `<b>${esc(pid)}</b>: ${esc(cs.map((c) => `${shortDate(c.date)} ${c.type.replace("_", " ")}`).join(", "))}`).join("<br>");
    const p = r.person;
    return `<tr data-id="${esc(p.id)}">
      <td>${i + 1}</td><td class="id">${esc(p.id)}</td><td>${esc(p.name)}</td>
      <td>${esc(p.kind === "staff" ? p.role : "room " + p.room_id)}</td><td>${badge(p.status)}</td>
      <td><b>${r.n}</b> / ${positives.length}</td><td>${detail}</td></tr>`;
  }).join("");
  $("#tab-source").innerHTML = `
    <p class="summary">Positives: <b>${esc(positives.join(", "))}</b>.
      Fever but test-negative (${esc(fever.join(", ") || "none")}) are neither starting points nor candidates.
      <span class="ja">（発熱したが検査陰性の人は、起点にも候補にも入れません）</span></p>
    <table><thead><tr><th>#</th><th>ID</th><th>Name</th><th>Role</th><th>Status</th><th>Positives linked</th><th>Contacts within incubation window</th></tr></thead>
    <tbody>${body || `<tr><td colspan="7" class="muted">No one is linked to 2+ positives.</td></tr>`}</tbody></table>`;
  bindRowClicks("#tab-source");
}

// ---------------------------------------------------------------- 4. ask

function idsIn(value, out = new Set()) {
  if (typeof value === "string" && /^[PNDR]\d{2}$/.test(value)) out.add(value);
  else if (Array.isArray(value)) value.forEach((v) => idsIn(v, out));
  else if (value && typeof value === "object") Object.values(value).forEach((v) => idsIn(v, out));
  return out;
}

function cell(v) {
  if (Array.isArray(v)) return v.map((x) => (typeof x === "object" ? JSON.stringify(x) : x)).join(", ");
  if (v && typeof v === "object") return JSON.stringify(v);
  return v ?? "";
}

async function ask() {
  const question = $("#question").value.trim() || $("#question").placeholder;
  $("#question").value = question;
  showTab("ask");
  $("#tab-ask").innerHTML = `<p class="question">Q: ${esc(question)}</p><p class="muted">Asking ai&amp;… <span class="ja">（ai&amp; に問い合わせ中…）</span></p>`;
  const res = await api("/api/ask", { question });

  const ids = idsIn(res.rows);
  (question.toUpperCase().match(/\b[PNDR]\d{2}\b/g) || []).forEach((id) => ids.add(id));
  clearHighlights();
  if (ids.size) {
    cy.batch(() => {
      cy.nodes().forEach((n) => n.addClass(ids.has(n.id()) ? "hit" : "dim"));
      cy.edges().forEach((e) => {
        if (!(ids.has(e.source().id()) && ids.has(e.target().id()))) e.addClass("dim");
      });
    });
  }

  const cols = res.rows.length ? Object.keys(res.rows[0]) : [];
  const table = res.rows.length ? `
    <table><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${res.rows.map((r) => {
      const id = idsIn(r).values().next().value;
      return `<tr ${id ? `data-id="${esc(id)}"` : ""}>${cols.map((c) => `<td>${esc(cell(r[c]))}</td>`).join("")}</tr>`;
    }).join("")}</tbody></table>` : "";
  $("#tab-ask").innerHTML = `
    <p class="question">Q: ${esc(question)}</p>
    <p class="answer">${esc(res.answer)}</p>
    ${res.cypher ? `<details><summary>Cypher run by ai&amp; (read-only) · ${res.rows.length} rows</summary><pre>${esc(res.cypher)}</pre></details>` : ""}
    ${table}`;
  bindRowClicks("#tab-ask");
  setStatus(res.cypher ? `ai& answered with ${res.rows.length} rows` : res.answer);
}

// ---------------------------------------------------------------- reset / init

async function reset() {
  await api("/api/reset", {});
  persons = await api("/api/persons");
  fillPersonSelect();
  initGraph(await api("/api/graph"));
  prefillDates();
  $("#tab-contacts").innerHTML = `<p class="empty">Data reset. Mark a positive or trace contacts.<br><span class="ja">（初期データに戻しました。陽性者を登録するか、接触者を追跡してください）</span></p>`;
  $("#tab-source").innerHTML = `<p class="empty">Click “Find source”.<br><span class="ja">（左の「Find source」を押してください）</span></p>`;
  $("#tab-ask").innerHTML = `<p class="empty">Ask a question in English or Japanese.<br><span class="ja">（英語か日本語で質問してください）</span></p>`;
  showTab("contacts");
  setStatus("Data reset");
}

async function init() {
  persons = await api("/api/persons");
  fillPersonSelect();
  initGraph(await api("/api/graph"));
  prefillDates();

  $("#person").addEventListener("change", prefillDates);
  $("#mark").addEventListener("click", (e) => busy(e.target, "Marking…", markPositive));
  $("#trace").addEventListener("click", (e) => busy(e.target, "Tracing…", trace));
  $("#source").addEventListener("click", (e) => busy(e.target, "Searching…", findSource));
  $("#ask").addEventListener("click", (e) => busy(e.target, "Asking…", ask));
  $("#reset").addEventListener("click", (e) => busy(e.target, "Resetting…", reset));
  $("#question").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) $("#ask").click();
  });
  document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => {
    $("#question").value = c.dataset.q;
    $("#ask").click();
  }));
  document.querySelectorAll(".tabs button").forEach((b) =>
    b.addEventListener("click", () => showTab(b.dataset.tab)));
}

init().catch((e) => {
  setStatus(`Error: ${e.message}`);
  console.error(e);
});
