/* ============================================================
   charts.js — Chart.js factories. Every chart reads its colors
   from the live CSS custom props, so they re-theme on direction
   and light/dark switches. app.js destroys + rebuilds on change.
   ============================================================ */

const CHART_REGISTRY = {};

function cvar(name, fallback) {
  const el = document.querySelector('.appwrap');
  const v = getComputedStyle(el).getPropertyValue(name).trim();
  return v || fallback || '';
}
function withAlpha(hex, a) {
  const h = hex.replace('#', '');
  const n = h.length === 3 ? h.split('').map(c => c + c).join('') : h;
  const r = parseInt(n.slice(0, 2), 16), g = parseInt(n.slice(2, 4), 16), b = parseInt(n.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}
const CAT_PALETTE = ['#c4623f', '#7aa589', '#cda43f', '#a8442a', '#6f8f9e',
  '#9b7bb0', '#4f7a5f', '#d98b6a', '#8a8175', '#b8966a'];

function baseScales(opts = {}) {
  const grid = cvar('--line', '#ddd');
  const tick = cvar('--muted', '#666');
  const font = cvar('--font-num', 'monospace').split(',')[0].replace(/'/g, '');
  return {
    x: {
      grid: { color: withAlpha2(grid, 0.6), drawTicks: false, display: opts.xGrid !== false },
      border: { color: grid },
      ticks: { color: tick, font: { family: font, size: 9 }, maxRotation: opts.rotate ? 60 : 0,
        autoSkip: true, maxTicksLimit: opts.xTicks || 14,
        ...(opts.xFmt ? { callback: opts.xFmt } : {}) },
      stacked: !!opts.stacked,
    },
    y: {
      grid: { color: withAlpha2(grid, 0.6), drawTicks: false },
      border: { display: false },
      ticks: { color: tick, font: { family: font, size: 9 },
        ...(opts.yFmt ? { callback: opts.yFmt } : {}) },
      stacked: !!opts.stacked,
      beginAtZero: true,
    },
  };
}
function withAlpha2(color, a) {
  if (color.startsWith('#')) return withAlpha(color, a);
  // rgb/rgba/oklch fall back to as-is
  return color;
}
function legendCfg(show, font) {
  return {
    display: show,
    position: 'bottom',
    labels: { color: cvar('--muted', '#666'), boxWidth: 9, boxHeight: 9, padding: 12,
      font: { family: font, size: 10 }, usePointStyle: true, pointStyle: 'rect' },
  };
}
function fam() { return cvar('--font-num', 'monospace').split(',')[0].replace(/'/g, ''); }

/* ---------------- HERO ---------------- */
function buildApiByDay(ctx) {
  const font = fam();
  const datasets = MODEL_ORDER.map(m => ({
    label: m, data: DAILY.series[m], backgroundColor: MODEL_COLORS[m],
    borderWidth: 0, barPercentage: 0.92, categoryPercentage: 0.9,
  }));
  return new Chart(ctx, {
    type: 'bar',
    data: { labels: DAILY.labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: legendCfg(true, font), tooltip: { mode: 'index', intersect: false } },
      scales: baseScales({ stacked: true, rotate: true, xTicks: 16, yFmt: v => '$' + v }),
    },
  });
}
function buildCumulative(ctx) {
  const accent = cvar('--accent', '#b04a2f');
  return new Chart(ctx, {
    type: 'line',
    data: { labels: DAILY.labels, datasets: [{
      data: DAILY.cumulative, borderColor: accent, backgroundColor: withAlpha2(accent, 0.12),
      borderWidth: 2, fill: true, pointRadius: 0, tension: 0.25,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: baseScales({ rotate: true, xTicks: 16, yFmt: v => '$' + (v / 1000).toFixed(0) + 'k' }),
    },
  });
}
function buildTokenType(ctx) {
  const accent = cvar('--accent', '#b04a2f');
  const colors = [withAlpha2(accent, 0.55), accent, '#a59a86', '#7d756385'];
  return new Chart(ctx, {
    type: 'bar',
    data: { labels: TOKEN_TYPE.labels, datasets: [{
      data: TOKEN_TYPE.values,
      backgroundColor: [withAlpha2(accent, 0.4), accent, cvar('--muted'), withAlpha2(cvar('--muted'), 0.5)],
      borderWidth: 0, barPercentage: 0.7,
    }] },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: baseScales({ xFmt: v => '$' + v }),
    },
  });
}

/* ---------------- INSIGHTS ---------------- */
function doughnut(ctx, data, opts = {}) {
  const font = fam();
  return new Chart(ctx, {
    type: 'doughnut',
    data: { labels: data.labels, datasets: [{
      data: data.values, backgroundColor: opts.colors || CAT_PALETTE,
      borderColor: cvar('--panel', '#fff'), borderWidth: 2,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false, cutout: '62%',
      plugins: { legend: legendCfg(true, font) },
    },
  });
}
function hbar(ctx, data, opts = {}) {
  const accent = cvar('--accent', '#b04a2f');
  return new Chart(ctx, {
    type: 'bar',
    data: { labels: data.labels, datasets: [{
      data: data.values, backgroundColor: opts.color || accent, borderWidth: 0, barPercentage: 0.82,
    }] },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: baseScales({ xTicks: 6 }),
    },
  });
}
function buildOutputByTool(ctx) { return doughnut(ctx, OUTPUT_BY_TOOL); }
function buildOutputByActivity(ctx) { return doughnut(ctx, OUTPUT_BY_ACTIVITY); }
function buildToolUsage(ctx) { return hbar(ctx, TOOL_USAGE); }
function buildStorage(ctx) { return doughnut(ctx, STORAGE); }
function buildSubagentTypes(ctx) { return doughnut(ctx, SUBAGENT_TYPES); }
function buildAgentDescriptions(ctx) { return hbar(ctx, AGENT_DESCRIPTIONS); }
function buildErrorsByCategory(ctx) { return doughnut(ctx, ERRORS_BY_CATEGORY); }
function buildErrorsByTool(ctx) { return hbar(ctx, ERRORS_BY_TOOL, { color: '#b8503a' }); }
function buildCacheEff(ctx) {
  const accent = cvar('--accent', '#b04a2f');
  return new Chart(ctx, {
    type: 'line',
    data: { labels: DAILY.labels, datasets: [{
      data: CACHE_EFF, borderColor: accent, backgroundColor: withAlpha2(accent, 0.10),
      borderWidth: 1.5, fill: true, pointRadius: 0, tension: 0.3,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: baseScales({ rotate: true, xTicks: 14, yFmt: v => v + '%' }),
    },
  });
}
function buildErrorRate(ctx) {
  const c = '#b8503a';
  return new Chart(ctx, {
    type: 'line',
    data: { labels: DAILY.labels, datasets: [{
      data: ERROR_RATE, borderColor: c, backgroundColor: withAlpha2(c, 0.10),
      borderWidth: 1.5, fill: true, pointRadius: 0, tension: 0.3,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: baseScales({ rotate: true, xTicks: 14, yFmt: v => v + '%' }),
    },
  });
}

const CHART_BUILDERS = {
  'c-apiByDay': buildApiByDay,
  'c-cumulative': buildCumulative,
  'c-tokenType': buildTokenType,
  'c-outputByTool': buildOutputByTool,
  'c-outputByActivity': buildOutputByActivity,
  'c-cacheEff': buildCacheEff,
  'c-toolUsage': buildToolUsage,
  'c-storage': buildStorage,
  'c-subagentTypes': buildSubagentTypes,
  'c-agentDescriptions': buildAgentDescriptions,
  'c-errorRate': buildErrorRate,
  'c-errorsByCategory': buildErrorsByCategory,
  'c-errorsByTool': buildErrorsByTool,
};

function buildCharts(ids) {
  Chart.defaults.font.family = fam();
  Chart.defaults.color = cvar('--muted', '#666');
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    if (CHART_REGISTRY[id]) { CHART_REGISTRY[id].destroy(); delete CHART_REGISTRY[id]; }
    CHART_REGISTRY[id] = CHART_BUILDERS[id](el.getContext('2d'));
  });
  // Throttled iframes don't reliably fire rAF/ResizeObserver, so Chart.js can
  // construct against a 0px container and never self-correct. Force resizes via
  // setTimeout (which DOES fire here) until the container width is measured.
  [30, 120, 350, 800].forEach(t => setTimeout(() => {
    ids.forEach(id => { if (CHART_REGISTRY[id]) CHART_REGISTRY[id].resize(); });
  }, t));
}
function destroyAllCharts() {
  Object.keys(CHART_REGISTRY).forEach(id => { CHART_REGISTRY[id].destroy(); delete CHART_REGISTRY[id]; });
}
