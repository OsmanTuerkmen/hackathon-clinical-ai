/* Local, dependency-free EHDS desk. All untrusted values enter the DOM as text. */
'use strict';
const app = document.getElementById('app');
const state = { requests: [], law: {}, selected: null, request: null, result: null, tab: 'applicant', epoch: 0, controller: null };
const number = new Intl.NumberFormat('en-GB');
const $ = id => document.getElementById(id);
function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== null && text !== undefined) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function append(parent, ...children) { children.filter(Boolean).forEach(child => parent.append(child)); return parent; }
function button(text, action, className = 'button secondary') {
  const node = el('button', text, className); node.type = 'button'; node.addEventListener('click', action); return node;
}
function heading(parent, text, level = 2) { return append(parent, el(`h${level}`, text)); }
function para(parent, text, className) { return append(parent, el('p', text, className)); }
function list(parent, items) { const ul = el('ul'); items.forEach(item => ul.append(el('li', item))); parent.append(ul); }
function panel(parent, title) { const section = el('section', null, 'card'); heading(section, title); parent.append(section); return section; }
function code(parent, value) { parent.append(el('pre', typeof value === 'string' ? value : JSON.stringify(value, null, 2))); }
function details(parent, title, value) { const node = el('details'); append(node, el('summary', title)); code(node, value); parent.append(node); }
function table(parent, caption, columns, rows) {
  const wrap = el('div', null, 'table-wrap'); wrap.tabIndex = 0; wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', caption);
  const node = el('table'); node.append(el('caption', caption));
  const head = el('tr'); columns.forEach(col => { const th = el('th', col.label); th.scope = 'col'; head.append(th); });
  append(node, append(el('thead'), head)); const body = el('tbody');
  rows.forEach(row => {
    const tr = el('tr'); columns.forEach((col, index) => {
      const value = col.get(row); const cell = el(index === 0 ? 'th' : 'td');
      if (index === 0) cell.scope = 'row';
      if (value instanceof Node) cell.append(value); else cell.textContent = value === null || value === undefined ? '—' : String(value);
      if (value === '<10' || value === 'suppressed') cell.classList.add('suppressed');
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
function shell() {
  const header = el('header', null, 'site-header');
  const brand = el('a', null, 'brand'); brand.href = '/';
  append(brand, el('span', '+', 'brand-mark'), append(el('span'), el('strong', 'EHDS Access Desk'), el('span', 'Health Data Access Body', 'brand-subtitle')));
  append(header, brand, el('span', 'Demo on synthetic data', 'demo-tag'));
  app.append(header);
  const footer = el('footer', null, 'site-footer');
  append(footer, el('span', 'Purpose-led access. Privacy by design.'), el('span', 'Reference date · 31 December 2025'));
  return footer;
}
function invalidate() {
  state.epoch += 1; state.controller?.abort(); state.controller = new AbortController(); state.result = null; state.request = null;
  return { epoch: state.epoch, signal: state.controller.signal };
}
function status(text, bad = false) {
  const node = $('processing-status'); node.textContent = text; node.className = bad ? 'notice error' : 'notice';
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
  const footer = shell();
  const layout = el('div', null, 'desk-layout'); const aside = el('aside', null, 'inbox'); aside.setAttribute('aria-label', 'Request inbox');
  const inboxHead = el('div', null, 'inbox-heading'); append(inboxHead, el('h2', 'Inbox'), el('span', '…', 'count')); append(aside, inboxHead);
  const add = button('+ New request', newRequest, 'button primary new-request'); aside.append(add);
  const requestList = el('nav', null, 'request-list'); requestList.id = 'request-list'; requestList.setAttribute('aria-label', 'Requests'); aside.append(requestList);
  const asideNote = el('div', null, 'inbox-note'); append(asideNote, el('strong', 'A clear path to access'), el('p', 'Every request is checked against the EHDS purpose and data minimisation rules.')); aside.append(asideNote);
  const main = el('main', null, 'desk-main'); main.id = 'main';
  const intro = el('div', null, 'page-intro'); append(intro, el('p', 'REQUEST ASSESSMENT', 'eyebrow'), el('h1', 'From purpose to permission'), el('p', 'Understand the decision, the safeguards and the next step.', 'subtitle')); main.append(intro);
  const requestCard = el('section', null, 'card request-card'); requestCard.id = 'request-summary'; para(requestCard, 'Loading requests…'); main.append(requestCard);
  const editor = el('section', null, 'card'); editor.id = 'request-editor'; editor.hidden = true; heading(editor, 'New request'); para(editor, 'Paste an EHDS request as JSON, then submit it for assessment.');
  const label = el('label', 'Request JSON'); label.htmlFor = 'request-json'; const input = el('textarea'); input.id = 'request-json'; input.spellcheck = false; input.rows = 15;
  append(editor, label, input, button('Assess request', submitRequest, 'button primary')); main.append(editor);
  const live = el('p', 'Select a request to begin.', 'notice'); live.id = 'processing-status'; live.setAttribute('role', 'status'); live.setAttribute('aria-live', 'polite'); main.append(live);
  const tabs = el('div', null, 'tabs'); tabs.setAttribute('role', 'tablist'); tabs.setAttribute('aria-label', 'Assessment views');
  ['applicant', 'staff'].forEach(name => {
    const tab = button(name === 'applicant' ? 'Applicant' : 'Staff', () => activateTab(name), 'tab'); tab.id = `${name}-tab`; tab.setAttribute('role', 'tab'); tab.setAttribute('aria-controls', `${name}-panel`);
    tab.addEventListener('keydown', event => { if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) { event.preventDefault(); activateTab(event.key === 'Home' ? 'applicant' : event.key === 'End' ? 'staff' : name === 'applicant' ? 'staff' : 'applicant', true); } }); tabs.append(tab);
  }); main.append(tabs);
  ['applicant', 'staff'].forEach(name => { const content = el('div'); content.id = `${name}-panel`; content.setAttribute('role', 'tabpanel'); content.setAttribute('aria-labelledby', `${name}-tab`); content.tabIndex = 0; main.append(content); });
  append(layout, aside, main); app.append(layout, footer); activateTab('applicant'); loadInbox();
}
async function loadInbox() {
  const initialEpoch = state.epoch;
  try {
    const [requests, law] = await Promise.all([api('/api/requests'), api('/api/law')]); state.requests = requests; state.law = law;
    document.querySelector('.inbox-heading .count').textContent = requests.length;
    requests.forEach(request => {
      const item = button('', () => selectRequest(request.id), 'request-item'); item.dataset.requestId = request.id;
      append(item, append(el('span', null, 'request-line'), el('strong', request.id), el('span', request.source === 'extra' ? 'Additional' : 'Request', 'request-type')), el('span', request.organisation, 'organisation'), el('span', request.purpose, 'request-purpose')); $('request-list').append(item);
    });
    if (state.epoch !== initialEpoch) return;
    if (requests.length) await selectRequest(requests[0].id); else status('No stored requests. Create a new request to begin.');
  } catch (error) { if (state.epoch === initialEpoch) status(error.message, true); }
}
function selection(id) {
  state.selected = id; document.querySelectorAll('.request-item').forEach(item => { if (item.dataset.requestId === id) item.setAttribute('aria-current', 'true'); else item.removeAttribute('aria-current'); });
}
function clearResult() { $('applicant-panel').replaceChildren(); $('staff-panel').replaceChildren(); }
function requestSummary(request) {
  const summary = $('request-summary'); summary.replaceChildren();
  append(summary, el('p', `${request.id} · ${request.requested_as}`, 'eyebrow'), el('h2', request.question), el('p', request.applicant.organisation, 'organisation-title'), el('p', request.purpose));
  const definition = el('details'); definition.append(el('summary', 'Request details')); list(definition, request.definitions); summary.append(definition);
}
async function selectRequest(id) {
  const task = invalidate(); selection(id); clearResult(); $('request-editor').hidden = true; $('request-summary').hidden = false; $('request-summary').replaceChildren(el('p', `Loading ${id}…`)); status(`Assessing ${id}…`);
  try {
    const request = await api(`/api/requests/${encodeURIComponent(id)}`, { signal: task.signal });
    if (task.epoch !== state.epoch) return; state.request = request; requestSummary(request);
    const result = await api(`/api/process/${encodeURIComponent(id)}`, { method: 'POST', signal: task.signal });
    if (task.epoch !== state.epoch) return; showResult(result);
  } catch (error) { if (task.epoch === state.epoch && error.name !== 'AbortError') status(error.message, true); }
}
function newRequest() {
  const previous = state.request; invalidate(); selection(null); clearResult(); $('request-summary').hidden = true; $('request-editor').hidden = false;
  $('request-json').value = JSON.stringify(previous ? { ...previous, id: 'NEW-REQUEST' } : { id: 'NEW-REQUEST', applicant: { name: '', organisation: '' }, requested_as: 'health data request', purpose: '', question: '', definitions: [] }, null, 2);
  status('New request · ready for assessment.'); $('request-json').focus();
}
async function submitRequest() {
  let request;
  try { request = JSON.parse($('request-json').value); } catch { status('Invalid JSON. Check the syntax and try again.', true); return; }
  const task = invalidate(); clearResult(); status('Assessing your request…');
  try {
    const result = await api('/api/process', { method: 'POST', signal: task.signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) });
    if (task.epoch !== state.epoch) return; state.request = request; requestSummary(request); $('request-summary').hidden = false; showResult(result);
  } catch (error) { if (task.epoch === state.epoch && error.name !== 'AbortError') status(error.message, true); }
}
function showResult(result) {
  state.result = result; renderApplicant(result.applicant, result.staff); renderStaff(result.staff);
  const review = result.applicant.decision !== 'REJECT' && (!result.staff.parse_report.complete || (!result.applicant.statistics && !result.applicant.spe));
  status(review ? `${result.applicant.request_id} · Manual review required. No data released.` : `${result.applicant.request_id} · Assessment complete.`);
}
function renderApplicant(answer, staff) {
  const root = $('applicant-panel'); root.replaceChildren();
  const rejected = answer.decision === 'REJECT';
  const review = !rejected && (!staff.parse_report.complete || (!answer.statistics && !answer.spe));
  const outcome = review ? 'Manual review required' : rejected ? 'Rejected' : answer.decision === 'APPROVE_SPE' ? 'Approved – secure processing environment' : 'Approved – anonymised statistics';
  const banner = el('section', null, `decision-banner ${review ? 'review' : rejected ? 'rejected' : 'approved'}`); banner.dataset.decision = answer.decision;
  append(banner, el('span', review ? '!' : rejected ? '×' : '✓', 'decision-symbol'), append(el('div'), el('p', 'ACCESS DECISION', 'eyebrow'), el('h2', outcome), el('p', review ? 'This request needs a staff check before any data can be released.' : answer.headline))); root.append(banner);
  const rationale = panel(root, 'Why this decision'); articleChips(rationale, answer.articles); list(rationale, answer.reasons); answer.notes.forEach(note => para(rationale, note, 'notice warning'));
  if (review) { const next = panel(root, 'Next step'); para(next, 'Staff will review the parts of your request that could not be interpreted. No statistics or secure workspace have been released.'); return; }
  if (answer.statistics) {
    const stats = answer.statistics; const section = panel(root, 'Anonymised results');
    para(section, `All ${number.format(stats.rows.length)} requested groups are shown, including groups with no matching records.`, 'muted');
    const columns = [...stats.dimensions.map(key => ({ label: key.replaceAll('_', ' '), get: row => row.group[key] })), ...stats.metrics.map(metric => ({ label: metric.kind === 'percent' ? `${metric.label} (%)` : metric.label, get: row => { const value = row.values[metric.name]; return typeof value === 'number' && metric.kind !== 'count' ? value.toFixed(1) : value; } }))];
    table(section, 'Results by requested group', columns, stats.rows);
    para(section, 'Privacy safeguard: counts below 10 (including zero) appear as <10. Percentages with a numerator or denominator below 10, and means based on fewer than 10 patients, are suppressed. Values are rounded to one decimal place where applicable.', 'footnote');
  }
  if (answer.spe) {
    const section = panel(root, 'Your secure workspace'); const count = el('div', null, 'metric'); append(count, el('strong', number.format(answer.spe.patient_count)), el('span', 'patients in the permitted cohort')); section.append(count);
    para(section, 'Access is limited to the permitted records. Patients who opted out are excluded. Pseudonymised records must stay inside the secure workspace.');
    table(section, 'Permitted tables', [{ label: 'Table', get: row => row[0] }, { label: 'Rows', get: row => number.format(row[1]) }], Object.entries(answer.spe.tables));
    const link = el('a', 'Open secure workspace →', 'button primary'); link.href = `/spe/${encodeURIComponent(answer.spe.permit_id)}`; section.append(link);
  }
}
function evidence(parent, items) {
  if (!items.length) { para(parent, 'No matching evidence.', 'muted'); return; }
  items.forEach(item => { const quote = el('blockquote', item.quote); append(quote, el('cite', `${item.category} · source: ${item.source}`)); parent.append(quote); });
}
function renderStaff(staff) {
  const root = $('staff-panel'); root.replaceChildren();
  const overview = panel(root, 'Assessment overview'); const facts = el('dl', null, 'facts');
  [['Request type', staff.request_kind.replaceAll('_', ' ')], ['Parser source', staff.parser_source], ['Interpretation', staff.parse_report.complete ? 'Complete' : 'Needs manual review'], ['Opt-out exclusions · Art. 71', staff.opt_out_excluded === null ? 'Not computed' : staff.opt_out_excluded]].forEach(([key, value]) => append(facts, el('dt', key), el('dd', value))); overview.append(facts);
  staff.warnings.forEach(warning => para(overview, warning, 'notice warning'));
  const trace = panel(root, 'Decision ladder'); const steps = el('ol', null, 'trace');
  staff.trace.forEach(step => { const item = el('li'); const label = { matched: 'Matched', not_matched: 'Not matched', not_evaluated: 'Not evaluated' }[step.status] || step.status; append(item, el('span', label, `badge ${step.status}`), el('h3', step.title), el('p', step.condition)); if (step.evidence.length) evidence(item, step.evidence); steps.append(item); }); trace.append(steps);
  const purpose = panel(root, 'Recognised purpose'); [['Permitted use · Art. 53', staff.purpose.permitted], ['Prohibited use · Art. 54', staff.purpose.prohibited], ['Need for pseudonymised access', staff.purpose.spe_justification]].forEach(([title, items]) => { heading(purpose, title, 3); evidence(purpose, items); });
  const spec = panel(root, 'Query specification'); if (staff.spec_summary.length) list(spec, staff.spec_summary); else para(spec, 'No complete specification is available.'); details(spec, 'View specification JSON', staff.spec);
  const coverage = panel(root, 'Interpretation coverage'); heading(coverage, 'Needs manual review', 3); if (staff.parse_report.not_understood.length) list(coverage, staff.parse_report.not_understood); else para(coverage, 'All request definitions were interpreted.', 'muted');
  if (staff.parse_report.notes.length) list(coverage, staff.parse_report.notes); const understood = el('details'); understood.append(el('summary', 'Understood definitions')); list(understood, staff.parse_report.understood); coverage.append(understood);
  const terminology = panel(root, 'Terminology mapping');
  table(terminology, 'Request terms mapped to codes found in the data', [
    { label: 'Term / table', get: mapping => `${mapping.term} · ${mapping.table}` },
    { label: 'System / prefixes', get: mapping => `${mapping.codes.system.toUpperCase()} · ${mapping.codes.prefixes.join(', ')}` },
    { label: 'Source', get: mapping => mapping.codes.source },
    { label: 'Verified codes / description / rows', get: mapping => { const node = el('div'); mapping.matches.forEach(match => para(node, `${match.code} · ${match.description} · ${number.format(match.rows)} rows`)); if (!mapping.matches.length) para(node, 'No codes found.'); if (mapping.warning) para(node, mapping.warning, 'notice warning'); return node; } }
  ], staff.parse_report.mappings);
  if (!staff.parse_report.mappings.length) para(terminology, 'No terminology mappings required.', 'muted');
  const query = panel(root, 'Generated query'); if (staff.sql) details(query, 'View SQL', staff.sql); else para(query, 'No query executed.');
  const disclosure = panel(root, 'Disclosure safeguards');
  table(disclosure, 'Suppression log', [{ label: 'Group', get: note => Object.entries(note.group).map(([key, value]) => `${key}: ${value}`).join(' · ') || 'All' }, { label: 'Metric', get: note => note.metric }, { label: 'Reason', get: note => note.reason }], staff.disclosure_notes);
  if (!staff.disclosure_notes.length) para(disclosure, 'No cells required suppression, or no statistical results were computed.', 'muted');
  const timing = panel(root, 'Processing time'); table(timing, 'Elapsed time by stage', [{ label: 'Stage', get: row => row[0] }, { label: 'Time', get: row => `${number.format(row[1])} ms` }], Object.entries(staff.timings_ms));
}
async function workspace(permit) {
  const footer = shell(); const main = el('main', null, 'workspace-main'); main.id = 'main'; app.append(main, footer);
  const back = el('a', '← Back to access desk', 'back-link'); back.href = '/'; main.append(back);
  append(main, el('p', 'CONTROLLED ACCESS · ART. 73', 'eyebrow'), el('h1', 'Secure processing environment'), el('p', 'Permitted records stay inside this workspace. Every preview and download attempt is recorded.', 'subtitle'));
  const alert = el('div'); alert.id = 'workspace-message'; alert.setAttribute('role', 'status'); alert.setAttribute('aria-live', 'polite'); main.append(alert);
  try {
    const manifest = await api(`/api/spe/${encodeURIComponent(permit)}`); const summary = panel(main, 'Permit overview'); para(summary, `Permit ${manifest.permit_id}`, 'permit-id');
    const count = el('div', null, 'metric'); append(count, el('strong', number.format(manifest.patient_count)), el('span', 'patients · opt-outs excluded')); summary.append(count);
    const tableSection = panel(main, 'Permitted tables');
    const preview = panel(main, 'Record preview'); preview.id = 'preview-section'; para(preview, 'Select a table to preview up to 20 rows. Pseudonymised records remain within this secure workspace.', 'muted');
    const audit = panel(main, 'Workspace audit'); const auditContent = el('div'); auditContent.id = 'audit-log';
    let auditEpoch = 0; let previewEpoch = 0;
    async function refreshAudit() {
      const current = ++auditEpoch;
      try { const events = await api(`/api/spe/${encodeURIComponent(permit)}/audit`); if (current !== auditEpoch) return; auditContent.replaceChildren(); table(auditContent, 'Recorded workspace events', [{ label: 'Time (UTC)', get: event => event.timestamp }, { label: 'Action', get: event => event.action }, { label: 'Table', get: event => event.table }, { label: 'Actor / detail', get: event => `${event.actor} · ${event.detail}` }], events); }
      catch (error) { if (current === auditEpoch) { auditContent.replaceChildren(); para(auditContent, error.message, 'notice error'); } }
    }
    async function previewTable(name) {
      const current = ++previewEpoch; preview.replaceChildren(el('h2', 'Record preview'), el('p', 'Loading preview…'));
      try { const rows = await api(`/api/spe/${encodeURIComponent(permit)}/preview/${encodeURIComponent(name)}`); if (current !== previewEpoch) return;
        preview.replaceChildren(el('h2', 'Record preview')); para(preview, `${name} · ${rows.length} rows shown · maximum 20`, 'muted');
        if (rows.length) table(preview, `${name} · secure preview`, Object.keys(rows[0]).map(key => ({ label: key.replaceAll('_', ' '), get: row => row[key] })), rows); else para(preview, 'This table contains no rows.');
        await refreshAudit();
      } catch (error) { if (current === previewEpoch) { preview.replaceChildren(el('h2', 'Record preview')); para(preview, error.message, 'notice error'); } }
    }
    async function downloadTable(name) {
      try {
        const response = await fetch(`/api/spe/${encodeURIComponent(permit)}/download/${encodeURIComponent(name)}`); const data = await response.json();
        alert.className = 'notice error'; alert.replaceChildren(el('strong', response.status === 403 && data.blocked ? 'Download blocked · HTTP 403' : 'Download unavailable'));
        para(alert, typeof data.reason === 'string' ? data.reason : 'Records cannot be downloaded from this secure workspace.');
      } catch { alert.className = 'notice error'; alert.textContent = 'Download unavailable. Check the connection and try again.'; }
      await refreshAudit();
    }
    table(tableSection, 'Tables in this permit', [{ label: 'Table', get: row => row[0] }, { label: 'Rows', get: row => number.format(row[1]) }, { label: 'Actions', get: row => { const actions = el('div', null, 'actions'); append(actions, button('Preview', () => previewTable(row[0])), button('Download', () => downloadTable(row[0]))); return actions; } }], Object.entries(manifest.tables));
    append(audit, button('Reload audit', refreshAudit), auditContent); await refreshAudit();
  } catch (error) { alert.className = 'notice error'; alert.textContent = error.message; }
}
const workspaceRoute = /^\/spe\/([^/]+)\/?$/.exec(location.pathname);
if (workspaceRoute) workspace(workspaceRoute[1]); else desk();
