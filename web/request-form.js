/* Doccess new-request form: pure conversion between form answers and the request JSON the API expects. */
(function (root) {
  'use strict';
  const KINDS = {
    statistics: { requested_as: 'health data request', requested_format: 'anonymised statistics' },
    records: { requested_as: 'health data access application', requested_format: 'pseudonymised records' }
  };
  const TEMPLATES = [
    { label: 'Age', text: 'Adult = aged 18 or older on 31 December 2025.' },
    { label: 'Diagnosis', text: 'Type 2 diabetes = a diagnosis of type 2 diabetes.' },
    { label: 'Medication', text: 'Statin = an active prescription of a statin.' },
    { label: 'Age bands', text: 'Age bands on 31 December 2025: 18-49, 50-64, 65+.' },
    { label: 'Latest measurement', text: 'Use the latest HbA1c per patient; patients without a HbA1c are left out.' },
    { label: 'Hospital stays', text: 'Count inpatient stays in 2025.' },
    { label: 'Report', text: 'Report per region: adults, adults with type 2 diabetes.' }
  ];

  const clean = value => String(value ?? '').trim();
  const sentence = line => (/[.?!:]$/.test(line) ? line : `${line}.`);
  const lines = fields => (fields.definitions || []).map(clean).filter(Boolean);
  const record = value => (value !== null && typeof value === 'object' && !Array.isArray(value) ? value : {});
  const text = value => (typeof value === 'string' ? value : '');

  /* Answers from the form win; anything else in `base`, a request pasted as JSON, travels with them. */
  function buildRequest(fields, meta, base = {}) {
    const kind = KINDS[fields.kind] || KINDS.statistics; const country = clean(fields.country).toUpperCase();
    const applicant = { ...record(base.applicant), name: clean(fields.name), organisation: clean(fields.organisation) };
    if (country) applicant.country = country; else delete applicant.country;
    return { id: meta.id, submitted: meta.submitted, ...base, applicant, ...kind, purpose: clean(fields.purpose), question: clean(fields.question), definitions: lines(fields).map(sentence) };
  }

  function validateFields(fields) {
    const errors = {}; const country = clean(fields.country);
    if (!clean(fields.name)) errors.name = 'Enter your name.';
    if (!clean(fields.organisation)) errors.organisation = 'Enter your organisation.';
    if (country && !/^[A-Za-z]{2}$/.test(country)) errors.country = 'Use a two-letter country code, such as AT.';
    if (!clean(fields.purpose)) errors.purpose = 'Describe why you need the data.';
    if (!clean(fields.question)) errors.question = 'Enter your question.';
    if (!lines(fields).length) errors.definitions = 'Add at least one definition.';
    return errors;
  }

  /* Mirrors _classify in decision.py, so the form never shows another kind than the server decides on. */
  function requestKind(request) {
    const type = String(request.requested_as ?? '').toLowerCase().split(/\s+/).join(' ');
    if (type.includes('access application')) return 'records';
    if (type.includes('data request')) return 'statistics';
    return /record|pseudonym/i.test(String(request.requested_format ?? '')) ? 'records' : 'statistics';
  }

  function fieldsFromRequest(request) {
    const applicant = record(request.applicant);
    const stored = Array.isArray(request.definitions) ? request.definitions.filter(line => typeof line === 'string') : [];
    return { name: text(applicant.name), organisation: text(applicant.organisation), country: text(applicant.country), kind: requestKind(request), purpose: text(request.purpose), question: text(request.question), definitions: stored.length ? stored : [''] };
  }

  /* Names the parts of a pasted request that the form could not show without changing them. */
  function formProblems(request) {
    const shown = value => value === undefined || typeof value === 'string'; const { applicant, definitions } = request; const problems = [];
    if (applicant !== undefined && (record(applicant) !== applicant || ![applicant.name, applicant.organisation, applicant.country].every(shown))) problems.push('applicant');
    ['purpose', 'question'].filter(key => !shown(request[key])).forEach(key => problems.push(key));
    if (definitions !== undefined && (!Array.isArray(definitions) || !definitions.every(line => typeof line === 'string'))) problems.push('definitions');
    return problems;
  }

  function purposeHint(kind) {
    return kind === 'records' ? 'Explain why anonymised statistics are not enough for this purpose.' : 'Say what you want to find out and who benefits.';
  }

  function newRequestId(now) { return `NEW-${now.toString(36).toUpperCase()}`; }

  const api = { KINDS, TEMPLATES, buildRequest, fieldsFromRequest, formProblems, newRequestId, purposeHint, validateFields };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.DoccessRequestForm = api;
}(globalThis));
