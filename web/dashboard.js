/* Doccess dashboard logic: pure functions over released values only. A masked cell stays a label and never becomes a number. */
(function (root) {
  'use strict';
  const MASKED = new Set(['<10', 'suppressed']);
  const MIN_HEIGHT = 6;
  const MASKED_HEIGHT = 14;
  const HORIZONTAL_FROM = 13;
  const number = new Intl.NumberFormat('en-GB');

  const isMasked = value => MASKED.has(value);
  const formatValue = (value, kind) => (typeof value !== 'number' ? String(value) : kind === 'count' ? number.format(value) : value.toFixed(1));
  const unique = values => [...new Set(values)];

  function defaultMetric(table) {
    const percent = table.metrics.filter(metric => metric.kind === 'percent').pop();
    return (percent || table.metrics.find(metric => metric.kind === 'count') || table.metrics[0])?.name ?? null;
  }

  function chartModel(table, metricName, selection = {}) {
    const metric = table.metrics.find(entry => entry.name === metricName);
    const [axis, ...others] = table.dimensions;
    const filters = others.map(dimension => {
      const options = unique(table.rows.map(row => String(row.group[dimension])));
      return { dimension, options, selected: options.includes(selection[dimension]) ? selection[dimension] : options[0] };
    });
    const rows = table.rows.filter(row => filters.every(filter => String(row.group[filter.dimension]) === filter.selected));
    const numbers = rows.map(row => row.values[metric.name]).filter(value => typeof value === 'number');
    const largest = numbers.length ? Math.max(...numbers) : 0;
    const bars = rows.map(row => {
      const raw = row.values[metric.name]; const masked = isMasked(raw); const label = axis === undefined ? metric.label : String(row.group[axis]);
      const scaled = largest > 0 && typeof raw === 'number' ? Math.round((raw / largest) * 1000) / 10 : MIN_HEIGHT;
      return { label, shortLabel: label.slice(0, 3), value: masked ? null : raw, display: formatValue(raw, metric.kind), masked, heightPct: masked ? MASKED_HEIGHT : Math.max(MIN_HEIGHT, scaled) };
    });
    return { metric, axis, filters, bars, horizontal: bars.length >= HORIZONTAL_FROM };
  }

  function summary(model) {
    const hidden = model.bars.filter(bar => bar.masked).length; const total = model.bars.length;
    if (!total) return 'No groups to show.';
    if (hidden) return `${hidden} of ${total} ${total === 1 ? 'group' : 'groups'} ${hidden === 1 ? 'is' : 'are'} partly hidden because fewer than 10 patients were involved.`;
    const top = model.bars.reduce((best, bar) => (bar.value > best.value ? bar : best), model.bars[0]);
    const unit = model.metric.kind === 'percent' ? '%' : '';
    return `Highest: ${top.label} (${top.display}${unit}). All ${total} ${total === 1 ? 'group is' : 'groups are'} shown in full.`;
  }

  function fullyShown(table) {
    const shown = table.rows.filter(row => table.metrics.every(metric => !isMasked(row.values[metric.name]))).length;
    return { shown, total: table.rows.length };
  }

  function protectedCells(table) {
    return table.rows.reduce((count, row) => count + table.metrics.filter(metric => isMasked(row.values[metric.name])).length, 0);
  }

  /* Numbers stay numeric. Text starting with a formula character is neutralised for spreadsheets; a leading space is not evaluated. */
  function csvCell(value) {
    if (value === null || value === undefined) return '';
    if (typeof value === 'number') return String(value);
    let text = String(value);
    if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
    return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  }

  function toCsv(table) {
    const header = [...table.dimensions, ...table.metrics.map(metric => (metric.kind === 'percent' ? `${metric.label} (%)` : metric.label))];
    const rows = table.rows.map(row => [
      ...table.dimensions.map(key => row.group[key]),
      ...table.metrics.map(metric => { const value = row.values[metric.name]; return typeof value === 'number' && metric.kind !== 'count' ? { number: value.toFixed(1) } : value; })
    ]);
    const cell = value => (value && typeof value === 'object' ? value.number : csvCell(value));
    return [header, ...rows].map(line => line.map(cell).join(',')).join('\r\n') + '\r\n';
  }

  function exportName(requestId) {
    return `doccess-${String(requestId).replace(/[^A-Za-z0-9_-]/g, '')}-statistics.csv`;
  }

  const api = { chartModel, csvCell, defaultMetric, exportName, formatValue, fullyShown, isMasked, protectedCells, summary, toCsv };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.DoccessDashboard = api;
}(globalThis));
