/* Doccess: local, dependency-free access desk. All untrusted values enter the DOM as text. */
'use strict';
const app = document.getElementById('app');
const state = { requests: [], law: {}, dataset: null, selected: null, request: null, result: null, tab: 'applicant', epoch: 0, controller: null, played: new Set() };
const { chartModel, defaultMetric, exportName, formatValue, fullyShown, protectedCells, summary, toCsv } = window.DoccessDashboard;
const number = new Intl.NumberFormat('en-GB');
const $ = id => document.getElementById(id);
const SVG = 'http://www.w3.org/2000/svg';
const MARK = 'M2 1h10a11 11 0 0 1 0 22H2zM7.5 23V11.5a3.5 3.5 0 0 1 7 0V23z';
const ICONS = {
  check: 'M5 12.5l4.5 4.5L19 7.5',
  cross: 'M6 6l12 12M18 6L6 18',
  alert: 'M12 4l9 16H3zM12 10v4.5M12 17.4v.2',
  search: 'M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13zM15.5 15.5L20 20',
  lock: 'M6 11h12v9H6zM9 11V8a3 3 0 0 1 6 0v3',
  back: 'M19 12H5M11 6l-6 6 6 6',
  refresh: 'M19 9a7.5 7.5 0 0 0-13.5-1.5L4 9M4 4.5V9h4.5M5 15a7.5 7.5 0 0 0 13.5 1.5L20 15M20 19.5V15h-4.5',
  blocked: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM5.7 5.7l12.6 12.6',
  dash: 'M7 12h10'
};
const STATUS_ICON = { approved: 'check', rejected: 'cross', review: 'alert' };
const STATUS_TEXT = { approved: 'Approved', rejected: 'Rejected', review: 'Manual review required' };

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== null && text !== undefined) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function append(parent, ...children) { children.filter(Boolean).forEach(child => parent.append(child)); return parent; }
function vector(path, className) {
  const svg = document.createElementNS(SVG, 'svg'); svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('class', className); svg.setAttribute('aria-hidden', 'true');
  const shape = document.createElementNS(SVG, 'path'); shape.setAttribute('d', path); svg.append(shape); return svg;
}
function icon(name) { return vector(ICONS[name], 'icon'); }
function button(text, action, className = 'button') {
  const node = el('button', text, className); node.type = 'button'; node.addEventListener('click', action); return node;
}
function heading(parent, text, level = 2) { return append(parent, el(`h${level}`, text)); }
function para(parent, text, className) { return append(parent, el('p', text, className)); }
function list(parent, items) { const ul = el('ul'); items.forEach(item => ul.append(el('li', item))); parent.append(ul); }
function section(parent, title) { const node = el('section', null, 'section'); heading(node, title); parent.append(node); return node; }
function code(parent, value) { parent.append(el('pre', typeof value === 'string' ? value : JSON.stringify(value, null, 2))); }
function details(parent, title, value) { const node = el('details'); append(node, el('summary', title)); code(node, value); parent.append(node); }
function motionAllowed() { return matchMedia('(prefers-reduced-motion: no-preference)').matches; }
function wait(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
function restart(node, className) { node.classList.remove(className); void node.offsetWidth; node.classList.add(className); }
function protect(cell, value) {
  cell.classList.add('suppressed');
  cell.title = value === '<10' ? 'Fewer than 10 patients. Exact number hidden to prevent re-identification.' : 'Based on fewer than 10 patients, so not reliable or safe to show.';
  cell.replaceChildren(append(el('span', null, 'protected'), icon('lock'), el('span', value)));
}
function toast(text) {
  document.querySelector('.toast')?.remove();
  const node = el('p', text, 'toast'); node.setAttribute('role', 'status'); node.prepend(icon('alert')); document.body.append(node);
  setTimeout(() => node.remove(), 4200);
}
function facts(parent, rows) { const dl = el('dl', null, 'facts'); rows.forEach(([key, value]) => dl.append(append(el('div'), el('dt', key), el('dd', value)))); parent.append(dl); }
function sentenceCase(text) { const value = String(text).replaceAll('_', ' '); return value.charAt(0).toUpperCase() + value.slice(1); }
function table(parent, caption, columns, rows, wrapClass = '') {
  const wrap = el('div', null, `table-wrap ${wrapClass}`.trim()); wrap.tabIndex = 0; wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', caption);
  const node = el('table'); node.append(el('caption', caption));
  const head = el('tr'); columns.forEach(col => { const th = el('th', col.label, col.numeric ? 'num' : null); th.scope = 'col'; head.append(th); });
  append(node, append(el('thead'), head)); const body = el('tbody');
  rows.forEach((row, position) => {
    const tr = el('tr'); tr.style.setProperty('--row', Math.min(position, 12)); columns.forEach((col, index) => {
      const value = col.get(row); const cell = el(index === 0 ? 'th' : 'td');
      if (index === 0) cell.scope = 'row';
      if (col.numeric) cell.classList.add('num');
      if (value instanceof Node) cell.append(value); else cell.textContent = value === null || value === undefined ? '—' : String(value);
      if (value === '<10' || value === 'suppressed') protect(cell, value);
      tr.append(cell);
    }); body.append(tr);
  }); node.append(body); wrap.append(node); parent.append(wrap); return node;
}
async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Request could not be completed (HTTP ${response.status}).`);
  return data;
}
function articleChips(parent, articles) {
  const chips = el('div', null, 'article-chips');
  articles.forEach(article => {
    const law = state.law[article]; const chip = el('span', `Art. ${article}`, 'article-chip'); chip.tabIndex = 0;
    const help = el('span', law ? `${law.title}. ${law.summary}` : 'EHDS Regulation (EU) 2025/327', 'article-tooltip');
    chip.append(help); chips.append(chip);
  }); parent.append(chips);
}
function brand() {
  const link = el('a', null, 'brand'); link.href = '/'; link.setAttribute('aria-label', 'Doccess, back to the inbox');
  const mark = vector(MARK, 'brand-mark'); mark.firstChild.setAttribute('fill-rule', 'evenodd');
  return append(link, mark, el('span', 'Doccess', 'wordmark'));
}
function sidebarNote() {
  const note = el('p', null, 'sidebar-note');
  return append(note, el('span', 'Demo on synthetic data'), el('span', 'Reference date 31 December 2025'));
}
function invalidate() {
  state.epoch += 1; state.controller?.abort(); state.controller = new AbortController(); state.result = null; state.request = null;
  return { epoch: state.epoch, signal: state.controller.signal };
}
function status(text, bad = false, quiet = false) {
  const node = $('processing-status'); node.textContent = text; node.className = bad ? 'notice error' : quiet ? 'notice sr-only' : 'notice';
}
function activateTab(tab, focus = false) {
  state.tab = tab;
  ['applicant', 'staff'].forEach(name => {
    const active = name === tab; $(`${name}-tab`).setAttribute('aria-selected', String(active)); $(`${name}-tab`).tabIndex = active ? 0 : -1;
    $(`${name}-panel`).hidden = !active;
  });
  if (focus) $(`${tab}-tab`).focus();
}
function desk() {
  const layout = el('div', null, 'shell');
  const aside = el('aside', null, 'sidebar'); aside.setAttribute('aria-label', 'Request inbox'); const inner = el('div', null, 'sidebar-inner');
  const search = el('label', null, 'search-field'); const input = el('input'); input.type = 'search'; input.id = 'request-search'; input.placeholder = 'Search requests'; input.setAttribute('aria-label', 'Search requests'); input.addEventListener('input', () => filterInbox(input.value));
  append(search, icon('search'), input);
  const requestList = el('nav'); requestList.id = 'request-list'; requestList.className = 'request-list'; requestList.setAttribute('aria-label', 'Requests');
  append(inner, brand(), button('+ New request', newRequest, 'button new-request'), search, requestList, sidebarNote()); aside.append(inner);
  const main = el('main', null, 'case'); main.id = 'main'; main.tabIndex = -1;
  const editor = el('section', null, 'panel'); editor.id = 'request-editor'; editor.hidden = true; heading(editor, 'New request', 1); para(editor, 'Paste an EHDS request as JSON, then submit it for assessment.', 'muted');
  const label = el('label', 'Request JSON'); label.htmlFor = 'request-json'; const textarea = el('textarea'); textarea.id = 'request-json'; textarea.spellcheck = false; textarea.rows = 15;
  append(editor, label, textarea, button('Assess request', submitRequest, 'button primary')); main.append(editor);
  const head = el('header', null, 'case-head'); const summary = el('div'); summary.id = 'request-summary'; para(summary, 'Loading requests…', 'muted');
  const live = el('p', 'Select a request to begin.', 'notice'); live.id = 'processing-status'; live.setAttribute('role', 'status'); live.setAttribute('aria-live', 'polite');
  append(head, summary, live); main.append(head);
  const tabs = el('div', null, 'tabs'); tabs.id = 'assessment-tabs'; tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'Assessment views');
  ['applicant', 'staff'].forEach(name => {
    const tab = button(name === 'applicant' ? 'Applicant' : 'Staff', () => activateTab(name), 'tab'); tab.id = `${name}-tab`; tab.setAttribute('role', 'tab'); tab.setAttribute('aria-controls', `${name}-panel`);
    tab.addEventListener('keydown', event => { if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); activateTab(event.key === 'Home' ? 'applicant' : event.key === 'End' ? 'staff' : name === 'applicant' ? 'staff' : 'applicant', true); } }); tabs.append(tab);
  }); main.append(tabs);
  ['applicant', 'staff'].forEach(name => { const content = el('div'); content.id = `${name}-panel`; content.setAttribute('role', 'tabpanel'); content.setAttribute('aria-labelledby', `${name}-tab`); content.tabIndex = 0; main.append(content); });
  append(layout, aside, main); app.append(layout); activateTab('applicant'); loadInbox();
}
function inboxRow(request) {
  const item = button('', () => selectRequest(request.id), 'request-item'); item.dataset.requestId = request.id; item.title = request.purpose;
  const name = el('span', request.organisation, 'request-name');
  return append(item, el('span', request.id, 'request-id'), name, el('span', null, 'request-state'));
}
function renderInbox(requests) {
  const nav = $('request-list');
  [['Requests', requests.filter(request => request.source !== 'extra')], ['Test cases', requests.filter(request => request.source === 'extra')]].forEach(([title, rows]) => {
    if (!rows.length) return;
    const group = el('div', null, 'request-group'); group.append(append(el('p', null, 'request-group-title'), el('span', title), el('span', rows.length, 'request-group-count')));
    rows.forEach(request => group.append(inboxRow(request))); nav.append(group);
  });
  const none = el('p', 'No requests match.', 'no-match'); none.id = 'no-match'; none.hidden = true; nav.append(none);
  filterInbox($('request-search').value);
}
function filterInbox(query) {
  const term = query.trim().toLowerCase(); let visible = 0;
  document.querySelectorAll('.request-group').forEach(group => {
    let shown = 0;
    group.querySelectorAll('.request-item').forEach(item => {
      const request = state.requests.find(entry => entry.id === item.dataset.requestId);
      const match = !term || [request.id, request.organisation, request.purpose].join(' ').toLowerCase().includes(term);
      item.hidden = !match; if (match) shown += 1;
    });
    group.querySelector('.request-group-count').textContent = shown; group.hidden = !shown; visible += shown;
  });
  $('no-match').hidden = visible > 0;
}
async function loadInbox() {
  const initialEpoch = state.epoch;
  try {
    const [requests, law, dataset] = await Promise.all([api('/api/requests'), api('/api/law'), api('/api/health').catch(() => null)]); state.requests = requests; state.law = law; state.dataset = dataset;
    renderInbox(requests);
    if (state.epoch !== initialEpoch) return;
    if (requests.length) await selectRequest(requests[0].id); else { $('request-summary').replaceChildren(el('p', 'The inbox is empty.', 'muted')); status('No stored requests. Create a new request to begin.'); }
  } catch (error) { if (state.epoch === initialEpoch) { $('request-summary').replaceChildren(); status(error.message, true); } }
}
function selection(id) {
  state.selected = id;
  document.querySelectorAll('.request-item').forEach(item => {
    if (item.dataset.requestId === id) { item.setAttribute('aria-current', 'true'); item.scrollIntoView({ block: 'nearest', inline: 'center' }); } else item.removeAttribute('aria-current');
  });
}
function resetStage(root) { root.classList.remove('staged', 'revealed'); delete root.dataset.stage; }
function clearResult() { const root = $('applicant-panel'); root.replaceChildren(); resetStage(root); $('staff-panel').replaceChildren(); }
function showLoading() {
  const root = $('applicant-panel'); root.replaceChildren(); ['', '', 'short'].forEach(size => { const line = el('span', null, `skeleton ${size}`.trim()); line.setAttribute('aria-hidden', 'true'); root.append(line); });
}
function requestSummary(request) {
  const summary = $('request-summary'); summary.replaceChildren();
  const kicker = el('p', null, 'kicker'); append(kicker, el('span', request.id, 'request-ref'), document.createTextNode(` · ${sentenceCase(request.requested_as)} · ${request.applicant.organisation}`));
  const definition = el('details'); definition.append(el('summary', 'Purpose and definitions'), el('p', request.purpose, 'lead-purpose')); list(definition, request.definitions);
  append(summary, kicker, el('h1', request.question, String(request.question).length > 90 ? 'long' : null), definition);
}
async function selectRequest(id) {
  const task = invalidate(); selection(id); clearResult(); $('request-editor').hidden = true; $('request-summary').hidden = false; $('assessment-tabs').hidden = false;
  $('request-summary').replaceChildren(el('p', `Loading ${id}…`, 'muted')); showLoading(); status(`Assessing ${id}…`);
  try {
    const request = await api(`/api/requests/${encodeURIComponent(id)}`, { signal: task.signal });
    if (task.epoch !== state.epoch) return; state.request = request; requestSummary(request);
    const result = await api(`/api/process/${encodeURIComponent(id)}`, { method: 'POST', signal: task.signal });
    if (task.epoch !== state.epoch) return; showResult(result);
  } catch (error) { if (task.epoch === state.epoch && error.name !== 'AbortError') { clearResult(); if (!state.request) $('request-summary').replaceChildren(); status(error.message, true); } }
}
function newRequest() {
  const previous = state.request; invalidate(); selection(null); clearResult(); $('request-summary').hidden = true; $('assessment-tabs').hidden = true; $('request-editor').hidden = false;
  $('request-json').value = JSON.stringify(previous ? { ...previous, id: 'NEW-REQUEST' } : { id: 'NEW-REQUEST', applicant: { name: '', organisation: '' }, requested_as: 'health data request', purpose: '', question: '', definitions: [] }, null, 2);
  status('New request · ready for assessment.'); $('request-json').focus();
}
async function submitRequest() {
  let request;
  try { request = JSON.parse($('request-json').value); } catch { status('Invalid JSON. Check the syntax and try again.', true); return; }
  const task = invalidate(); clearResult(); status('Assessing your request…');
  try {
    const result = await api('/api/process', { method: 'POST', signal: task.signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) });
    if (task.epoch !== state.epoch) return; state.request = request; state.played.delete(result.applicant.request_id); requestSummary(request); $('request-editor').hidden = true; $('request-summary').hidden = false; $('assessment-tabs').hidden = false; showResult(result); $('main').focus({ preventScroll: true });
  } catch (error) { if (task.epoch === state.epoch && error.name !== 'AbortError') status(error.message, true); }
}
function outcomeOf(result) {
  const { applicant, staff } = result;
  if (applicant.decision === 'REJECT') return 'rejected';
  return !staff.parse_report.complete || (!applicant.statistics && !applicant.spe) ? 'review' : 'approved';
}
function showResult(result) {
  state.result = result; const outcome = outcomeOf(result);
  const animate = motionAllowed() && !state.played.has(result.applicant.request_id); state.played.add(result.applicant.request_id);
  renderApplicant(result.applicant, result.staff, outcome, animate); renderStaff(result.staff, result.applicant, outcome);
  const row = state.selected === result.applicant.request_id ? document.querySelector(`.request-item[data-request-id="${CSS.escape(state.selected)}"] .request-state`) : null;
  if (row) { row.className = `request-state ${outcome}`; row.replaceChildren(icon(STATUS_ICON[outcome]), el('span', STATUS_TEXT[outcome], 'sr-only')); }
  status(outcome === 'review' ? `${result.applicant.request_id} · Manual review required. No data released.` : `${result.applicant.request_id} · Assessment complete.`, false, true);
}
function releaseOf(answer, outcome) {
  if (outcome !== 'approved') return 'No data released';
  return answer.decision === 'APPROVE_SPE' ? 'Secure processing environment' : 'Anonymised statistics';
}
function ladder(parent, trace, outcome) {
  const band = el('section', null, 'ladder-band'); band.append(el('h2', 'How this was decided', 'sr-only'));
  const steps = el('ol', null, 'ladder'); steps.setAttribute('role', 'list');
  const decided = { approved: ['decided', 'Decided here', 'check'], rejected: ['stopped', 'Stopped here', 'cross'], review: ['held', 'Held for staff review', 'alert'] }[outcome];
  trace.forEach((step, index) => {
    const [kind, note, glyph] = step.status === 'matched' ? decided : step.status === 'not_matched' ? ['passed', 'Checked, no match', 'check'] : ['skipped', 'Not needed', 'dash'];
    const mark = el('span', null, 'step-mark'); mark.dataset.step = index + 1; mark.append(icon(glyph));
    steps.append(append(el('li', null, kind), mark, el('span', step.title, 'step-title'), el('span', note, 'step-note')));
  });
  band.append(steps);
  if (outcome !== 'approved') band.append(el('p', outcome === 'rejected' ? 'Rejected before any data was touched' : 'Held for staff review before any data was released', 'ladder-chip'));
  parent.append(band); return [...steps.children];
}
function tile(parent, title, className = '') {
  const node = el('section', null, `tile ${className}`.trim()); if (title) node.append(el('h2', title, 'tile-label')); parent.append(node); return node;
}
function bigNumber(parent, value, display = number.format(value)) {
  const node = el('p', display, 'tile-number'); if (typeof value === 'number') node.dataset.count = value; parent.append(node); return node;
}
function downloadStatistics(answer) {
  const url = URL.createObjectURL(new Blob(['﻿', toCsv(answer.statistics)], { type: 'text/csv;charset=utf-8' }));
  const link = el('a'); link.href = url; link.download = exportName(answer.request_id); document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function decisionTile(parent, answer, outcome) {
  const node = tile(parent, null, `tile-decision decision-banner ${outcome}`); node.dataset.decision = answer.decision;
  append(node, el('h2', `Decision · ${answer.request_id}`, 'tile-label'), append(el('div', null, 'decision-title'), icon(STATUS_ICON[outcome]), append(el('div'), el('strong', STATUS_TEXT[outcome]), el('span', releaseOf(answer, outcome)))));
  para(node, outcome === 'review' ? 'This request needs a staff check before any data can be released.' : answer.headline, 'decision-lead');
  if (outcome === 'approved' && answer.statistics) {
    const action = el('div', null, 'decision-action'); append(action, button('Download anonymised statistics (CSV)', () => downloadStatistics(answer), 'button primary'), el('span', 'Aggregated table only, no patient records.', 'action-hint')); node.append(action);
  }
}
function privacyTile(parent, stats) {
  const { shown, total } = fullyShown(stats); const node = tile(parent, 'Privacy', 'tile-privacy');
  const ring = el('div', null, 'ring'); ring.style.setProperty('--p', total ? Math.round((shown / total) * 100) : 0); ring.setAttribute('role', 'img'); ring.setAttribute('aria-label', `${shown} of ${total} groups fully shown`);
  ring.append(el('span', `${shown}/${total}`)); append(node, ring, el('p', 'groups fully shown', 'tile-note'));
}
function patientsTile(parent) {
  const node = tile(parent, 'Consented patients'); const count = state.dataset?.patients;
  if (typeof count === 'number') bigNumber(node, count); else bigNumber(node, null, '—');
  para(node, 'Patients who opted out are excluded.', 'tile-note');
}
function timeTile(parent, staff) {
  const node = tile(parent, 'Answer time', 'tile-dark'); const ms = staff.timings_ms.total; bigNumber(node, null, ms < 1000 ? `${number.format(ms)} ms` : `${(ms / 1000).toFixed(2)} s`);
}
function legalTile(parent, answer) {
  const node = tile(parent, 'Legal basis'); const label = el('p', `Art. ${answer.articles.join(' · ')}`, 'tile-number tile-small');
  label.title = answer.articles.map(article => `Art. ${article}: ${answer.article_titles[article] || 'EHDS Regulation'}`).join('\n'); append(node, label, el('p', 'EHDS Regulation', 'tile-note'));
}
function recordsTile(parent, answer) {
  const node = tile(parent, 'Records released'); bigNumber(node, null, '0');
  if (answer.spe) para(node, 'No downloads. Records stay in the secure workspace.', 'tile-note');
}
function drawChart(canvas, model) {
  canvas.className = `chart ${model.horizontal ? 'horizontal' : 'vertical'}`; canvas.replaceChildren();
  canvas.setAttribute('aria-label', `${model.metric.label}: ${model.bars.map(bar => `${bar.label} ${bar.display}`).join(', ')}`);
  model.bars.forEach((bar, index) => {
    const item = el('div', null, `bar ${bar.masked ? 'masked' : ''}`.trim()); item.title = `${bar.label}: ${bar.display}`; item.style.setProperty('--h', `${bar.heightPct}%`); item.style.setProperty('--i', Math.min(index, 16));
    const value = el('span', bar.display, 'bar-value'); const track = el('span', null, 'bar-track'); const fill = el('span', null, 'bar-fill'); if (bar.masked) fill.append(icon('lock')); track.append(value, fill);
    canvas.append(append(item, track, el('span', model.horizontal ? bar.label : bar.shortLabel, 'bar-label')));
  });
}
function chartTile(parent, stats) {
  const node = tile(parent, null, 'tile-chart'); const title = el('h2', null, 'tile-label'); const controls = el('div', null, 'chart-controls'); const sentence = el('p', null, 'chart-summary');
  const canvas = el('div'); canvas.setAttribute('role', 'img'); sentence.setAttribute('aria-live', 'polite'); append(node, title, controls, sentence, canvas);
  const view = { metric: defaultMetric(stats), selection: {} };
  const render = () => {
    const model = chartModel(stats, view.metric, view.selection);
    title.textContent = model.axis ? `${model.metric.label} · per ${model.axis.replaceAll('_', ' ')}` : model.metric.label;
    controls.querySelectorAll('.chip-button').forEach(choice => choice.setAttribute('aria-pressed', String(choice.dataset.metric === view.metric)));
    sentence.textContent = summary(model); drawChart(canvas, model);
  };
  if (stats.metrics.length > 1) stats.metrics.forEach(metric => { const choice = button(metric.label, () => { view.metric = metric.name; render(); }, 'chip-button'); choice.dataset.metric = metric.name; controls.append(choice); });
  chartModel(stats, view.metric).filters.forEach(filter => {
    const select = el('select'); select.setAttribute('aria-label', sentenceCase(filter.dimension)); filter.options.forEach(option => { const entry = el('option', option); entry.value = option; select.append(entry); }); select.value = filter.selected;
    select.addEventListener('change', () => { view.selection[filter.dimension] = select.value; render(); }); controls.append(select);
  });
  render();
}
function secureTile(parent, spe) {
  const node = tile(parent, 'Your secure workspace', 'tile-full'); const lead = el('div', null, 'spe-lead');
  const count = el('div', null, 'metric'); const figure = el('strong', number.format(spe.patient_count)); figure.dataset.count = spe.patient_count; append(count, figure, el('span', 'patients in the permitted cohort'));
  const link = el('a', 'Open secure workspace →', 'button primary'); link.href = `/spe/${encodeURIComponent(spe.permit_id)}`; node.append(append(lead, count, link));
  para(node, 'Access is limited to the permitted records. Patients who opted out are excluded. Pseudonymised records must stay inside the secure workspace.', 'muted');
  table(node, 'Permitted tables', [{ label: 'Table', get: row => row[0] }, { label: 'Rows', numeric: true, get: row => number.format(row[1]) }], Object.entries(spe.tables));
  node.append(append(el('p', null, 'badge blocked'), document.createTextNode('Downloads blocked (HTTP 403)')));
}
function emptyTile(parent, title, text, className = '') { para(tile(parent, title, className), text); }
function countUp(node, alive) {
  const target = Number(node.dataset.count); const started = performance.now();
  return new Promise(resolve => {
    const tick = now => {
      if (!alive()) { resolve(); return; }
      const progress = Math.min(1, (now - started) / 600); node.textContent = number.format(Math.round(target * (1 - (1 - progress) ** 3)));
      if (progress < 1) requestAnimationFrame(tick); else resolve();
    };
    requestAnimationFrame(tick);
  });
}
async function playStage(root, steps) {
  const epoch = state.epoch; const alive = () => epoch === state.epoch;
  root.dataset.stage = 'running'; root.classList.add('staged');
  for (const step of steps) {
    step.classList.add('is-active');
    await wait(step.classList.contains('skipped') ? 160 : 340);
    if (!alive()) return;
    step.classList.replace('is-active', 'is-shown');
  }
  root.classList.add('revealed');
  await Promise.race([wait(2500), Promise.all([wait(1300), ...[...root.querySelectorAll('[data-count]')].map(node => countUp(node, alive))])]);
  if (!alive()) return;
  resetStage(root); root.dataset.stage = 'done';
}
function renderApplicant(answer, staff, outcome, animate) {
  const root = $('applicant-panel'); root.replaceChildren(); resetStage(root);
  const steps = ladder(root, staff.trace, outcome); const bento = el('div', null, 'bento'); root.append(bento);
  decisionTile(bento, answer, outcome);
  if (outcome === 'approved' && answer.statistics) { privacyTile(bento, answer.statistics); patientsTile(bento); timeTile(bento, staff); if (answer.statistics.rows.length && answer.statistics.metrics.length) chartTile(bento, answer.statistics); legalTile(bento, answer); recordsTile(bento, answer); }
  else if (outcome === 'approved' && answer.spe) { patientsTile(bento); timeTile(bento, staff); legalTile(bento, answer); recordsTile(bento, answer); secureTile(bento, answer.spe); }
  else { legalTile(bento, answer); recordsTile(bento, answer); timeTile(bento, staff); if (outcome === 'rejected') emptyTile(bento, 'Patient data', 'No patient data was queried.'); else emptyTile(bento, 'Next step', 'Staff will review the parts of your request that could not be interpreted. No statistics or secure workspace have been released.', 'tile-full'); }
  if (outcome === 'approved' && answer.statistics) {
    const stats = answer.statistics; const results = section(root, 'Anonymised results'); const hidden = protectedCells(stats);
    para(results, `All ${number.format(stats.rows.length)} requested groups are shown, including groups with no matching records.`, 'muted');
    if (hidden) results.append(append(el('p', null, 'protected-legend'), append(el('span', null, 'protected'), icon('lock')), document.createTextNode(`${number.format(hidden)} ${hidden === 1 ? 'cell' : 'cells'} protected by the small-cell rule`)));
    const columns = [...stats.dimensions.map(key => ({ label: sentenceCase(key), get: row => row.group[key] })), ...stats.metrics.map(metric => ({ numeric: true, label: metric.kind === 'percent' ? `${metric.label} (%)` : metric.label, get: row => { const value = row.values[metric.name]; return typeof value === 'number' ? formatValue(value, metric.kind) : value; } }))];
    table(results, 'Results by requested group', columns, stats.rows);
    para(results, 'Privacy safeguard: counts below 10 (including zero) appear as <10. Percentages with a numerator or denominator below 10, and means based on fewer than 10 patients, are suppressed. Values are rounded to one decimal place where applicable.', 'footnote');
  }
  const rationale = section(root, 'Why this decision');
  articleChips(rationale, answer.articles); list(rationale, answer.reasons); answer.notes.forEach(note => para(rationale, note, 'notice warning'));
  if (animate) playStage(root, steps); else root.dataset.stage = 'done';
}
function evidence(parent, items) {
  if (!items.length) { para(parent, 'No matching evidence.', 'muted'); return; }
  const grouped = new Map();
  items.forEach(item => { const key = `${item.source}\n${item.quote}`; if (!grouped.has(key)) grouped.set(key, { ...item, categories: new Set() }); grouped.get(key).categories.add(item.category); });
  grouped.forEach(item => { const quote = el('blockquote', item.quote); append(quote, el('cite', `${[...item.categories].join(', ')} · source: ${item.source}`)); parent.append(quote); });
}
function renderStaff(staff, answer, outcome) {
  const root = $('staff-panel'); root.replaceChildren();
  const grid = el('div', null, 'case-grid fade-in'); const body = el('div', null, 'case-body'); const rail = el('div', null, 'case-rail staff-rail'); const nav = el('nav', null, 'staff-nav'); nav.setAttribute('aria-label', 'Staff sections');
  rail.append(el('h2', 'On this page', 'rail-title'), nav); grid.append(rail, body); root.append(grid);
  const staffSection = title => {
    const node = section(body, title); node.id = `staff-${title.toLowerCase().replaceAll(' ', '-')}`;
    const link = el('a', title); link.href = `#${node.id}`; nav.append(link); return node;
  };
  const overview = staffSection('Assessment overview');
  facts(overview, [['Decision', `${STATUS_TEXT[outcome]} · ${releaseOf(answer, outcome)}`], ['Request type', sentenceCase(staff.request_kind)], ['Parser source', staff.parser_source], ['Interpretation', staff.parse_report.complete ? 'Complete' : 'Needs manual review'], ['Opt-out exclusions · Art. 71', staff.opt_out_excluded === null ? 'Not computed' : typeof staff.opt_out_excluded === 'number' ? number.format(staff.opt_out_excluded) : staff.opt_out_excluded]]);
  staff.warnings.forEach(warning => para(overview, warning, 'notice warning'));
  const trace = staffSection('Decision ladder'); const steps = el('ol', null, 'trace');
  staff.trace.forEach(step => { const item = el('li'); const label = { matched: 'Matched', not_matched: 'Not matched', not_evaluated: 'Not evaluated' }[step.status] || step.status; append(item, el('h3', step.title), el('span', label, `badge ${step.status}`), el('p', step.condition)); if (step.evidence.length) evidence(item, step.evidence); steps.append(item); }); trace.append(steps);
  const purpose = staffSection('Recognised purpose'); [['Permitted use · Art. 53', staff.purpose.permitted], ['Prohibited use · Art. 54', staff.purpose.prohibited], ['Need for pseudonymised access', staff.purpose.spe_justification]].forEach(([title, items]) => { heading(purpose, title, 3); evidence(purpose, items); });
  const spec = staffSection('Query specification'); if (staff.spec_summary.length) list(spec, staff.spec_summary); else para(spec, 'No complete specification is available.', 'muted'); details(spec, 'View specification JSON', staff.spec);
  const coverage = staffSection('Interpretation coverage');
  if (staff.parse_report.not_understood.length) { heading(coverage, 'Needs manual review', 3); list(coverage, staff.parse_report.not_understood); } else para(coverage, 'All request definitions were interpreted.', 'muted');
  if (staff.parse_report.notes.length) list(coverage, staff.parse_report.notes); const understood = el('details'); understood.append(el('summary', 'Understood definitions')); list(understood, staff.parse_report.understood); coverage.append(understood);
  const terminology = staffSection('Terminology mapping');
  if (staff.parse_report.mappings.length) {
    table(terminology, 'Request terms mapped to codes found in the data', [
      { label: 'Term / table', get: mapping => `${mapping.term} · ${mapping.table}` },
      { label: 'System / prefixes', get: mapping => `${mapping.codes.system.toUpperCase()} · ${mapping.codes.prefixes.join(', ')}` },
      { label: 'Source', get: mapping => mapping.codes.source },
      { label: 'Verified codes / description / rows', get: mapping => { const node = el('div'); mapping.matches.forEach(match => para(node, `${match.code} · ${match.description} · ${number.format(match.rows)} rows`)); if (!mapping.matches.length) para(node, 'No codes found.'); if (mapping.warning) para(node, mapping.warning, 'notice warning'); return node; } }
    ], staff.parse_report.mappings);
  } else para(terminology, 'No terminology mappings required.', 'muted');
  const query = staffSection('Generated query'); if (staff.sql) details(query, 'View SQL', staff.sql); else para(query, 'No query executed.', 'muted');
  const disclosure = staffSection('Disclosure safeguards');
  if (staff.disclosure_notes.length) table(disclosure, 'Suppression log', [{ label: 'Group', get: note => Object.entries(note.group).map(([key, value]) => `${key}: ${value}`).join(' · ') || 'All' }, { label: 'Metric', get: note => note.metric }, { label: 'Reason', get: note => note.reason }], staff.disclosure_notes);
  else para(disclosure, 'No cells required suppression, or no statistical results were computed.', 'muted');
  const timing = staffSection('Processing time'); facts(timing, Object.entries(staff.timings_ms).map(([stage, ms]) => [stage, `${number.format(ms)} ms`]));
}
async function workspace(permit) {
  document.title = 'Secure workspace · Doccess';
  const layout = el('div', null, 'shell'); const aside = el('aside', null, 'sidebar'); aside.setAttribute('aria-label', 'Secure workspace'); const inner = el('div', null, 'sidebar-inner');
  const back = el('a', null, 'back-link'); back.href = '/'; append(back, icon('back'), document.createTextNode('Back to inbox'));
  const note = el('div', null, 'secure-note'); append(note, append(el('strong'), icon('lock'), document.createTextNode('Controlled access')), el('p', 'Every preview and download attempt is recorded.'));
  append(inner, brand(), back, note, sidebarNote()); aside.append(inner);
  const main = el('main', null, 'case'); main.id = 'main'; main.tabIndex = -1; append(layout, aside, main); app.append(layout);
  const band = el('header', null, 'secure-band'); append(band, icon('lock'), append(el('div'), el('p', 'Controlled access · Art. 73', 'kicker'), el('h1', 'Secure processing environment'), el('p', 'Permitted records stay inside this workspace.'))); main.append(band);
  const alert = el('div'); alert.id = 'workspace-message'; alert.setAttribute('role', 'status'); alert.setAttribute('aria-live', 'polite'); main.append(alert);
  try {
    const manifest = await api(`/api/spe/${encodeURIComponent(permit)}`); const summary = section(main, 'Permit overview');
    const count = el('div', null, 'metric'); append(count, el('strong', number.format(manifest.patient_count)), el('span', 'patients · opt-outs excluded')); summary.append(count); para(summary, `Permit ${manifest.permit_id}`, 'permit-id');
    const tableSection = section(main, 'Permitted tables');
    const preview = section(main, 'Record preview'); preview.id = 'preview-section'; para(preview, 'Select a table to preview up to 20 rows. Pseudonymised records remain within this secure workspace.', 'muted');
    const audit = section(main, 'Workspace audit'); const auditContent = el('div'); auditContent.id = 'audit-log';
    let auditEpoch = 0; let previewEpoch = 0; let auditSeen = null; let blockedAttempts = 0; let downloading = false;
    async function refreshAudit() {
      const current = ++auditEpoch;
      try {
        const events = await api(`/api/spe/${encodeURIComponent(permit)}/audit`); if (current !== auditEpoch) return; auditContent.replaceChildren();
        const when = value => el('span', String(value).replace('T', ' ').replace('+00:00', ''), 'mono nowrap');
        const action = value => el('span', value, `badge ${value === 'download_blocked' ? 'blocked' : ''}`.trim());
        table(auditContent, 'Recorded workspace events', [{ label: 'Time (UTC)', get: event => when(event.timestamp) }, { label: 'Action', get: event => action(event.action) }, { label: 'Table', get: event => event.table }, { label: 'Actor / detail', get: event => `${event.actor} · ${event.detail}` }], [...events].reverse(), 'scroll');
        blockedAttempts = events.filter(event => event.action === 'download_blocked').length;
        if (auditSeen !== null && events.length > auditSeen) auditContent.querySelector('tbody tr').classList.add('row-in'); auditSeen = events.length;
      } catch (error) { if (current === auditEpoch) { auditContent.replaceChildren(); para(auditContent, error.message, 'notice error'); } }
    }
    async function previewTable(name) {
      const current = ++previewEpoch; preview.replaceChildren(el('h2', 'Record preview'), el('p', 'Loading preview…', 'muted'));
      try { const rows = await api(`/api/spe/${encodeURIComponent(permit)}/preview/${encodeURIComponent(name)}`); if (current !== previewEpoch) return;
        preview.replaceChildren(el('h2', 'Record preview')); para(preview, `${name} · ${rows.length} rows shown · maximum 20`, 'muted');
        if (rows.length) table(preview, `${name} · secure preview`, Object.keys(rows[0]).map(key => ({ label: key.replaceAll('_', ' '), get: row => row[key] })), rows); else para(preview, 'This table contains no rows.', 'muted');
        await refreshAudit();
      } catch (error) { if (current === previewEpoch) { preview.replaceChildren(el('h2', 'Record preview')); para(preview, error.message, 'notice error'); } }
    }
    function blockedMoment(reason) {
      const dismiss = button('', () => { alert.className = ''; alert.replaceChildren(); tableSection.classList.remove('is-blocked'); main.focus({ preventScroll: true }); }, 'banner-dismiss'); dismiss.setAttribute('aria-label', 'Dismiss'); dismiss.append(icon('cross'));
      const counter = el('div', null, 'blocked-counter'); append(counter, el('strong', number.format(blockedAttempts)), el('span', blockedAttempts === 1 ? 'blocked attempt' : 'blocked attempts'));
      alert.replaceChildren(icon('blocked'), append(el('div'), el('strong', 'Download blocked · HTTP 403 · Art. 73'), el('p', `${reason} This attempt has been logged.`)), counter, dismiss);
      restart(alert, 'blocked-banner'); restart(tableSection, 'is-blocked'); toast('Incident logged to the audit trail');
    }
    async function downloadTable(name) {
      if (downloading) return;
      downloading = true;
      try {
        const [response] = await Promise.all([fetch(`/api/spe/${encodeURIComponent(permit)}/download/${encodeURIComponent(name)}`), wait(motionAllowed() ? 400 : 0)]); const data = await response.json().catch(() => ({}));
        const reason = typeof data.reason === 'string' ? data.reason : 'Records cannot be downloaded from this secure workspace.';
        await refreshAudit();
        if (response.status === 403 && data.blocked) { blockedMoment(reason); return; }
        tableSection.classList.remove('is-blocked'); alert.className = 'notice error'; alert.replaceChildren(el('strong', 'Download unavailable')); para(alert, reason);
      } catch { tableSection.classList.remove('is-blocked'); alert.className = 'notice error'; alert.textContent = 'Download unavailable. Check the connection and try again.'; await refreshAudit(); }
      finally { downloading = false; }
    }
    table(tableSection, 'Tables in this permit', [{ label: 'Table', get: row => row[0] }, { label: 'Rows', numeric: true, get: row => number.format(row[1]) }, { label: 'Actions', get: row => { const actions = el('div', null, 'actions'); append(actions, button('Preview', () => previewTable(row[0])), button('Download', () => downloadTable(row[0]))); return actions; } }], Object.entries(manifest.tables), 'align-middle');
    const reload = button('Reload audit', refreshAudit); reload.prepend(icon('refresh')); append(audit, reload, auditContent); await refreshAudit();
  } catch (error) { alert.className = 'notice error'; alert.textContent = error.message; }
}
const workspaceRoute = /^\/spe\/([^/]+)\/?$/.exec(location.pathname);
if (workspaceRoute) workspace(workspaceRoute[1]); else desk();
