
const D = "__DATA_PLACEHOLDER__";

// ── Helpers ────────────────────────────────────────────────────────────
const fmt = n => n.toLocaleString(D.locale.locale_code);
const fmtUSD = n => '$' + n.toLocaleString(D.locale.locale_code, {minimumFractionDigits:2, maximumFractionDigits:2});
let planCurrencyMode = (D.plan && D.plan.currency_symbol) ? 'local' : 'usd';
let costMetricMode = 'usd'; // 'usd' | 'local' | 'tokens' — Costs tab metric toggle
function planCurrencySymbol() {
  return (D.plan && D.plan.currency_symbol) || '$';
}
function fmtPlanMoney(n) {
  if (n == null || isNaN(n)) return '–';
  const num = n.toLocaleString(D.locale.locale_code, {minimumFractionDigits:2, maximumFractionDigits:2});
  if (planCurrencyMode === 'local') return num + ' ' + planCurrencySymbol();
  return '$' + num;
}
function planMoneyValue(obj, base) {
  if (!obj) return null;
  // Local mode: no silent USD fallback. A period without a local price renders
  // as "-" (via fmtPlanMoney(null)) instead of a USD number posing as a local
  // amount, which made the local-mode column visibly disagree with its total.
  if (base === 'plan_cost') {
    if (planCurrencyMode === 'local') return obj.plan_cost_local != null ? obj.plan_cost_local : null;
    return obj.plan_cost_usd;
  }
  if (planCurrencyMode === 'local') {
    const localKey = base + '_local';
    return obj[localKey] != null ? obj[localKey] : null;
  }
  return obj[base];
}
function planTotal(base) {
  if (!D.plan) return 0;
  if (planCurrencyMode === 'local') {
    const localKey = 'total_' + base + '_local';
    if (D.plan[localKey] != null) return D.plan[localKey];
  }
  return D.plan['total_' + base] || 0;
}
function planMoneyUnitLabel() {
  return planCurrencyMode === 'local' ? planCurrencySymbol() : 'USD';
}
const fmtTokens = n => {
  if (n >= 1e9) return (n/1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n/1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n/1e3).toFixed(1) + 'K';
  return n.toString();
};

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// Cache efficiency: cache_read / (input + cache_read + cache_write).
// Returns null when the session has no input-side tokens recorded.
function sessionCacheEff(s) {
  const inputSum = (s.input_tokens||0) + (s.cache_read_tokens||0) + (s.cache_write_tokens||0);
  if (inputSum === 0) return null;
  return (s.cache_read_tokens||0) / inputSum * 100;
}
function effStyle(pct) {
  if (pct == null) return {color:'var(--text2)', emoji:'—', label:'—'};
  if (pct >= 80) return {color:'var(--green)', emoji:'✅', label:pct.toFixed(1)+'%'};
  if (pct >= 50) return {color:'var(--amber)', emoji:'⚠️', label:pct.toFixed(1)+'%'};
  return {color:'var(--red)', emoji:'❌', label:pct.toFixed(1)+'%'};
}

// Variant-C single-accent palette. Values mirror the CSS custom
// properties on .vc and are kept in sync with the dark/light theme
// via a refresh on theme toggle. Hardcoded fallback ensures chart
// dataset declarations at module-load time always have a real color.
const _VC_PALETTE_LIGHT = ['#b04a2f', '#4d4a42', '#918a7a', '#f1d9cd'];
const _VC_PALETTE_DARK  = ['#d97757', '#b3ad9b', '#76705f', '#2c1c14'];

// Single categorical palette for multi-series doughnut/bar charts. Earth-tone
// family (terracotta / sage / ochre / clay …) matching the SaaS reskin; replaces
// the old bright slate/rainbow/hsl() loops. Mirrors docs/design-handoff CAT_PALETTE.
const _VC_CAT = ['#c4623f', '#7aa589', '#cda43f', '#a8442a', '#6f8f9e',
  '#9b7bb0', '#4f7a5f', '#d98b6a', '#8a8175', '#b8966a'];

function vcCurrentPalette() {
  if (typeof document !== 'undefined') {
    const cls = document.documentElement.classList;
    if (cls.contains('theme-dark')) return _VC_PALETTE_DARK;
    if (cls.contains('theme-light')) return _VC_PALETTE_LIGHT;
    if (typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) return _VC_PALETTE_DARK;
  }
  return _VC_PALETTE_LIGHT;
}
// Live token reader: returns the currently-applied value of a --vc-* custom
// property (scoped to .vc, falling back to :root), or `fallback` if unreadable.
// Lets a custom.css accent override actually recolor the charts at runtime.
function _vcLiveVar(name, fallback) {
  if (typeof document === 'undefined' || typeof getComputedStyle === 'undefined') return fallback;
  try {
    const probe = document.querySelector('.vc') || document.documentElement;
    const val = getComputedStyle(probe).getPropertyValue(name).trim();
    return val || fallback;
  } catch { return fallback; }
}
// Live accent: prefer the runtime --vc-accent (so custom.css overrides win),
// fall back to the theme-aware hardcoded palette slot 0.
function vcAccentLive() {
  return _vcLiveVar('--vc-accent', vcCurrentPalette()[0]);
}
function vcColor(rank) {
  const p = vcCurrentPalette();
  // Slot 0 is the accent — read the live token so custom.css overrides apply.
  if (rank % p.length === 0) return vcAccentLive();
  return p[rank % p.length];
}
function vcRgba(rank, alpha) {
  return _vcHexRgba(vcColor(rank), alpha);
}
// Convert a #rrggbb (or #rgb) color to an rgba() string. Non-hex inputs
// (already rgb()/oklch/etc.) are returned unchanged.
function _vcHexRgba(color, alpha) {
  if (typeof color !== 'string' || color[0] !== '#') return color;
  let hex = color.slice(1);
  if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
  if (hex.length !== 6) return color;
  const r = parseInt(hex.substr(0,2), 16);
  const g = parseInt(hex.substr(2,2), 16);
  const b = parseInt(hex.substr(4,2), 16);
  return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
}

// MODEL_COLORS: explicit per-model palette built around three on-brand
// earth-tone hues (terracotta / sage / ochre) so families are clearly
// distinguishable, with three lightness steps per family for versions.
// Unknown / unmatched models fall back to a neutral warm gray.
const _VC_MODEL_LIGHT = {
  'Fable 5':    '#c46786',
  'Opus 4.8':   '#c95a3a',
  'Opus 4.7':   '#b04a2f',
  'Opus 4.6':   '#8e3b25',
  'Opus 4.5':   '#6e2d1c',
  'Sonnet 4.6': '#5b8a7a',
  'Sonnet 4.5': '#467267',
  'Sonnet 4.0': '#345b54',
  'Haiku 4.5':  '#c89a4a',
  'Haiku 3.5':  '#a37b35',
  'Unknown':    '#7a766b',
};
const _VC_MODEL_DARK = {
  'Fable 5':    '#d98fa8',
  'Opus 4.8':   '#e88a66',
  'Opus 4.7':   '#d97757',
  'Opus 4.6':   '#bb5e3f',
  'Opus 4.5':   '#9d4a30',
  'Sonnet 4.6': '#7eb09e',
  'Sonnet 4.5': '#629581',
  'Sonnet 4.0': '#487a67',
  'Haiku 4.5':  '#d4a55c',
  'Haiku 3.5':  '#b48742',
  'Unknown':    '#9e9a8c',
};
const _VC_FAMILY_FALLBACK_LIGHT = { fable: '#c46786', opus: '#b04a2f', sonnet: '#5b8a7a', haiku: '#c89a4a' };
const _VC_FAMILY_FALLBACK_DARK  = { fable: '#d98fa8', opus: '#d97757', sonnet: '#7eb09e', haiku: '#d4a55c' };
function vcModelColor(modelName) {
  const isDark = vcCurrentPalette() === _VC_PALETTE_DARK;
  const map = isDark ? _VC_MODEL_DARK : _VC_MODEL_LIGHT;
  const fam = isDark ? _VC_FAMILY_FALLBACK_DARK : _VC_FAMILY_FALLBACK_LIGHT;
  if (!modelName) return map['Unknown'];
  if (map[modelName]) return map[modelName];
  const lower = String(modelName).toLowerCase();
  if (lower.includes('fable'))  return fam.fable;
  if (lower.includes('opus'))   return fam.opus;
  if (lower.includes('sonnet')) return fam.sonnet;
  if (lower.includes('haiku'))  return fam.haiku;
  return map['Unknown'];
}
// Backwards-compat shim: MODEL_COLORS[m] still works for existing code.
const MODEL_COLORS = {
  get _proxy() { return true; },
};
['Fable 5', 'Opus 4.8', 'Opus 4.7', 'Opus 4.6', 'Opus 4.5', 'Sonnet 4.6', 'Sonnet 4.5', 'Sonnet 4.0', 'Haiku 4.5', 'Haiku 3.5', 'Unknown'].forEach(m => {
  Object.defineProperty(MODEL_COLORS, m, { get() { return vcModelColor(m); }, enumerable: true });
});

const SOURCE_COLORS = [
  {bg:vcRgba(1, 0.15), fg:vcColor(1)},
  {bg:'rgba(6,182,212,0.15)', fg:vcColor(2)},
  {bg:'rgba(168,85,247,0.15)', fg:'#a855f7'},
  {bg:'rgba(34,197,94,0.15)', fg:'#22c55e'},
  {bg:'rgba(239,68,68,0.15)', fg:'#ef4444'},
  {bg:'rgba(59,130,246,0.15)', fg:'#3b82f6'},
  {bg:'rgba(236,72,153,0.15)', fg:'#ec4899'},
];
const _sourceColorMap = {};
function sourceColor(label) {
  if (!_sourceColorMap[label]) {
    let h = 0; for (let i = 0; i < label.length; i++) h = ((h << 5) - h + label.charCodeAt(i)) | 0;
    _sourceColorMap[label] = SOURCE_COLORS[Math.abs(h) % SOURCE_COLORS.length];
  }
  return _sourceColorMap[label];
}
function makeSourceBadge(label) {
  const c = sourceColor(label);
  const span = document.createElement('span');
  span.className = 'source-badge';
  span.style.background = c.bg; span.style.color = c.fg;
  span.textContent = label;
  return span;
}

// Initial placeholders; setupVcChartDefaults() (called below) immediately
// overwrites these with the resolved --vc-fg-3 / --vc-grid tokens.
Chart.defaults.color = '#918a7a';
Chart.defaults.borderColor = '#d8d2c4';

// Variant-C Chart.js theming — overrides legacy defaults to match Terminal aesthetic
function setupVcChartDefaults() {
  if (typeof Chart === 'undefined') return;
  // Read live CSS vars; falls back to embedded defaults if .vc not present
  function v(name, fallback) {
    const probe = document.querySelector('.vc') || document.documentElement;
    const val = getComputedStyle(probe).getPropertyValue(name).trim();
    return val || fallback;
  }
  const fg = v('--vc-fg', '#1c1a17');
  const fg2 = v('--vc-fg-2', '#4d4a42');
  const fg3 = v('--vc-fg-3', '#918a7a');
  const grid = v('--vc-grid', '#d8d2c4');
  const grid2 = v('--vc-grid-2', '#e8e3d6');
  const accent = v('--vc-accent', '#b04a2f');
  const panel = v('--vc-panel', '#fbfaf6');
  // Font: read --vc-font-sans (SaaS 'Manrope'), take first family, strip quotes.
  // Mirrors the fam() helper in docs/design-handoff/js/charts.js.
  const fontFam = (v('--vc-font-sans', "'Manrope', system-ui, sans-serif").split(',')[0] || 'Manrope').replace(/['"]/g, '').trim() || 'Manrope';

  // Disable all chart animations (entrance, hover, update) — the
  // single-accent Terminal aesthetic feels snappier without them.
  Chart.defaults.animation = false;
  Chart.defaults.animations = { colors: false, x: false, y: false };
  Chart.defaults.transitions = {
    active: { animation: { duration: 0 } },
    resize: { animation: { duration: 0 } },
    show: { animations: { x: { from: 0 }, y: { from: 0 } } },
    hide: { animations: { x: { to: 0 }, y: { to: 0 } } },
  };

  Chart.defaults.font.family = fontFam;
  Chart.defaults.font.size = 11;
  Chart.defaults.color = fg3;
  Chart.defaults.borderColor = grid;
  Chart.defaults.elements.line.borderWidth = 1.5;
  Chart.defaults.elements.line.borderColor = accent;
  Chart.defaults.elements.point.radius = 0;
  Chart.defaults.elements.point.hoverRadius = 3;
  Chart.defaults.elements.bar.borderRadius = 0;
  // Doughnut/pie segment separators: Chart.js defaults to '#fff' for arc
  // borders, which leaks as a white ring on dark backgrounds. Match the
  // surrounding card so segments blend into the panel.
  if (Chart.defaults.elements.arc) {
    Chart.defaults.elements.arc.borderColor = panel;
    Chart.defaults.elements.arc.borderWidth = 2;
  }
  Chart.defaults.plugins.legend.labels = Chart.defaults.plugins.legend.labels || {};
  Chart.defaults.plugins.legend.labels.color = fg2;
  Chart.defaults.plugins.legend.labels.font = {family: fontFam, size: 10};
  Chart.defaults.plugins.tooltip.backgroundColor = panel;
  Chart.defaults.plugins.tooltip.titleColor = fg;
  Chart.defaults.plugins.tooltip.bodyColor = fg2;
  Chart.defaults.plugins.tooltip.borderColor = grid;
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.cornerRadius = 0;
  Chart.defaults.plugins.tooltip.titleFont = {family: fontFam, size: 11, weight: '500'};
  Chart.defaults.plugins.tooltip.bodyFont = {family: fontFam, size: 11};
  if (Chart.defaults.scale) {
    Chart.defaults.scale.grid = Chart.defaults.scale.grid || {};
    Chart.defaults.scale.grid.color = grid2;
    Chart.defaults.scale.grid.borderDash = [1, 3];
    Chart.defaults.scale.grid.drawTicks = false;
    Chart.defaults.scale.ticks = Chart.defaults.scale.ticks || {};
    Chart.defaults.scale.ticks.color = fg3;
    Chart.defaults.scale.ticks.font = {family: fontFam, size: 10};
  }
  // Mutate the per-chart scaleDefaults object in place so charts that spread
  // {...scaleDefaults.x} or reference scaleDefaults.x directly pick up the
  // theme's soft grid color instead of the legacy slate (#1e293b).
  if (typeof scaleDefaults !== 'undefined') {
    scaleDefaults.x.grid.color = grid2;
    scaleDefaults.y.grid.color = grid2;
    scaleDefaults.x.ticks.color = fg3;
    scaleDefaults.y.ticks.color = fg3;
  }
  // Expose resolved theme colors so chart configs built later (e.g. radar,
  // legacy doughnut/bar charts) can use them without re-reading CSS vars.
  window.__vcGrid2 = grid2;
  window.__vcFg2 = fg2;
  window.__vcFg3 = fg3;
  // Re-render existing charts (if any). Chart.js caches scale options on
  // each instance at creation, so updating Chart.defaults / scaleDefaults
  // alone does NOT recolor already-built charts on theme toggle. Mutate
  // each instance's scales/border colors explicitly before update().
  if (Chart.instances) {
    for (const id in Chart.instances) {
      try {
        const c = Chart.instances[id];
        if (c.options) {
          if (c.options.borderColor !== undefined) c.options.borderColor = grid;
          if (c.options.scales) {
            Object.keys(c.options.scales).forEach(k => {
              const s = c.options.scales[k];
              if (!s) return;
              if (s.grid)       s.grid.color       = grid2;
              if (s.ticks)      s.ticks.color      = fg3;
              if (s.angleLines) s.angleLines.color = grid2;
            });
          }
          // Legacy charts hardcode pale slate (#e2e8f0 / #94a3b8) for
          // legend labels — invisible on light bg. Force theme-aware fg2.
          const lbls = c.options.plugins && c.options.plugins.legend
            && c.options.plugins.legend.labels;
          if (lbls) lbls.color = fg2;
        }
        c.update('none');
      } catch {}
    }
  }
}
// scaleDefaults is shared by chart configs below. Declared *before* the
// first setupVcChartDefaults() call so the function can sync its grid/tick
// colors to the active --vc-grid-2 / --vc-fg-3 values (and re-sync on
// theme switch). Initial values are warm light-mode placeholders; they're
// immediately overwritten by setupVcChartDefaults().
const scaleDefaults = {
  x: { ticks: { color: '#918a7a' }, grid: { color: '#e8e3d6' } },
  y: { ticks: { color: '#918a7a' }, grid: { color: '#e8e3d6' } },
};

// Apply once at load (before any chart is built) and re-apply on theme changes
setupVcChartDefaults();

// ── Filtered Data & Time Filter ────────────────────────────────────────
let F = {};
const charts = {};
let currentDays = 0;
let anonMode = false;
let agentTypesChartInstance, agentDescsChartInstance, errorByCatChartInstance, errorByToolChartInstance,
    errorRateChartInstance, taskDonutChartInstance;
// Variant-C: 10-slot palette using accent + fg shades cycled.
// Plain array rebuilt on demand to avoid Proxy-array compat issues with Chart.js.
function buildVcChartColors(n) {
  n = n || 10;
  const out = [vcColor(0), vcColor(1), vcColor(2)];
  for (let i = 3; i < n; i++) out.push(vcRgba(0, Math.max(0.15, 1 - i * 0.1)));
  return out;
}
const chartColors = buildVcChartColors(13);
let currentProjectFilter = '';

function calcFilteredPlanCost(filteredDates, local) {
  // An empty range (or no configured plan) means nothing was paid in this
  // range. Falling back to the all-time plan total here made a filtered view
  // with zero usage show "API equivalent $0.00 / paid <all-time total>".
  if (!D.plan || !filteredDates.length) return 0;
  const minDate = filteredDates[0];
  const maxDate = filteredDates[filteredDates.length - 1];
  let cost = 0;
  // Sum plan costs for periods that overlap with the filtered date range
  const allPeriods = (D.plan.periods || []).concat(D.plan.current_billing ? [D.plan.current_billing] : []);
  allPeriods.forEach(p => {
    const pStart = p.start || p.period_start;
    const pEnd = p.end || p.period_end;
    if (!pStart || !pEnd) return;
    // Check overlap
    if (pEnd < minDate || pStart > maxDate) return;
    // Calculate overlap fraction
    const overlapStart = pStart > minDate ? pStart : minDate;
    const overlapEnd = pEnd < maxDate ? pEnd : maxDate;
    const totalDays = p.total_days || p.days_total || 30;
    const msPerDay = 86400000;
    const overlapDays = Math.round((new Date(overlapEnd) - new Date(overlapStart)) / msPerDay) + 1;
    const fraction = Math.min(1, overlapDays / totalDays);
    const usd = p.plan_cost_usd || 0;
    // local: what the user actually paid (plan_cost_local), falling back to
    // a current-rate conversion for USD-only periods
    const amount = local
      ? (p.plan_cost_local != null ? p.plan_cost_local : usd * (currentFx() || 0))
      : usd;
    cost += amount * fraction;
  });
  return Math.round(cost * 100) / 100;
}

// ── Costs tab metric toggle: FX helpers ────────────────────────────────
// Mirrors Plan & Billing per-cycle FX (extract_stats.py: plan_cost_local / plan_cost_usd).
function periodFx(p) {
  return (p && p.plan_cost_local && p.plan_cost_usd) ? p.plan_cost_local / p.plan_cost_usd : null;
}
function currentFx() {
  if (!D.plan) return null;
  let fx = periodFx(D.plan.current_billing);
  if (fx) return fx;
  const ps = D.plan.periods || [];
  for (let i = ps.length - 1; i >= 0; i--) {
    fx = periodFx(ps[i]);
    if (fx) return fx;
  }
  return null;
}
function fxForDate(dateStr) {
  if (!D.plan) return null;
  // periods use start/end, current_billing uses period_start/period_end
  const all = (D.plan.periods || []).concat(D.plan.current_billing ? [D.plan.current_billing] : []);
  for (const p of all) {
    const start = p.start || p.period_start;
    const end = p.end || p.period_end;
    if (start && end && start <= dateStr && dateStr <= end) {
      const fx = periodFx(p);
      if (fx) return fx;
      break; // matching period without a rate -> fallback chain
    }
  }
  return currentFx();
}

function filterData(days, projectFilter) {
  if (days !== undefined) currentDays = days;
  if (projectFilter !== undefined) currentProjectFilter = projectFilter;

  let cutoff = '';
  if (currentDays > 0) {
    const d = new Date();
    d.setDate(d.getDate() - currentDays);
    cutoff = d.toISOString().slice(0, 10);
  }

  const pf = currentProjectFilter.toLowerCase().trim();

  // Filter sessions by date AND project
  const hideEmpty = document.getElementById('hideEmptySessions')?.checked;
  let filteredSessions = D.sessions;
  if (hideEmpty) filteredSessions = filteredSessions.filter(s => s.messages > 0 || s.output_tokens > 0);
  if (cutoff) filteredSessions = filteredSessions.filter(s => (s.end ? s.end.slice(0, 10) : s.date) >= cutoff);
  if (pf) filteredSessions = filteredSessions.filter(s => (s.project || '').toLowerCase().includes(pf));
  F.sessions = filteredSessions;
  recomputeIdleGapAggregate(F.sessions);

  // Task counts respecting the date range. Tasks have no timestamp of their
  // own, so we date them by their owning session (via session_id). Tasks whose
  // session isn't in the dataset have no date and only count in the all-time
  // view (no cutoff), so the all-time total is preserved.
  const sessDate = {};
  D.sessions.forEach(s => { if (s.session_id) sessDate[s.session_id] = s.date; });
  const tcounts = { completed: 0, pending: 0, in_progress: 0, total: 0 };
  ((D.insights && D.insights.tasks && D.insights.tasks.tasks) || []).forEach(t => {
    const dt = sessDate[t.session_id];
    if (cutoff && !(dt && dt >= cutoff)) return;   // outside the selected range
    tcounts.total++;
    if (t.status === 'completed') tcounts.completed++;
    else if (t.status === 'in_progress') tcounts.in_progress++;
    else if (t.status === 'pending') tcounts.pending++;
  });
  F.insights = Object.assign({}, D.insights, { tasks: Object.assign({}, D.insights && D.insights.tasks, tcounts) });

  // Daily aggregates. Unfiltered default view: use the server-prepared
  // per-day series directly (no client recompute). Filtered view: rebuild
  // from sessions, distributing each multi-day session across its actual
  // activity days via s.per_day (single-day sessions fall back to s.date).
  const noFilter = currentDays === 0 && !pf && !hideEmpty;
  const _q = (sv, q) => {
    const n = sv.length;
    if (n === 0) return 0;
    if (n === 1) return sv[0];
    const pos = (n - 1) * q;
    const lo = Math.floor(pos);
    const hi = Math.min(lo + 1, n - 1);
    return sv[lo] * (1 - (pos - lo)) + sv[hi] * (pos - lo);
  };
  const _boxplot = (cacheEffByDate) => Object.keys(cacheEffByDate).sort().map(d => {
    const sv = cacheEffByDate[d].slice().sort((a, b) => a - b);
    const n = sv.length;
    const median = _q(sv, 0.5);
    const q1 = _q(sv, 0.25);
    const q3 = _q(sv, 0.75);
    const iqr = q3 - q1;
    const loFence = q1 - 1.5 * iqr;
    const hiFence = q3 + 1.5 * iqr;
    const inRange = sv.filter(v => v >= loFence && v <= hiFence);
    const whiskerLow = inRange.length ? inRange[0] : sv[0];
    const whiskerHigh = inRange.length ? inRange[inRange.length - 1] : sv[n - 1];
    const outliers = sv.filter(v => v < loFence || v > hiFence).map(v => +v.toFixed(2));
    const sum = sv.reduce((a, b) => a + b, 0);
    return {
      date: d, sessions: n,
      mean: +(sum / n).toFixed(2), median: +median.toFixed(2),
      q1: +q1.toFixed(2), q3: +q3.toFixed(2),
      whisker_low: +whiskerLow.toFixed(2), whisker_high: +whiskerHigh.toFixed(2),
      min: +sv[0].toFixed(2), max: +sv[n - 1].toFixed(2), outliers,
    };
  });

  if (noFilter) {
    F.daily_costs = D.daily_costs;
    F.daily_tokens = D.daily_tokens;
    F.daily_messages = D.daily_messages;
    F.daily_cache_efficiency = D.daily_cache_efficiency;
  } else {
    const dailyCostMap = {};
    const dailyTokenMap = {};
    const dailyMsgMap = {};
    const cacheEffByDate = {};
    F.sessions.forEach(s => {
      if (s.per_day) {
        Object.entries(s.per_day).forEach(([day, slice]) => {
          if (cutoff && day < cutoff) return;
          if (!dailyMsgMap[day]) dailyMsgMap[day] = {date: day, messages: 0, sessions: 0};
          dailyMsgMap[day].messages += slice.messages || 0;
          dailyMsgMap[day].sessions += 1;
          if (!dailyCostMap[day]) dailyCostMap[day] = {date: day, total: 0};
          if (!dailyTokenMap[day]) dailyTokenMap[day] = {date: day, total: 0};
          let dIn = 0, dCr = 0, dCw = 0;
          Object.entries(slice.models || {}).forEach(([model, d]) => {
            dailyCostMap[day].total += d.cost || 0;
            dailyCostMap[day][model] = (dailyCostMap[day][model] || 0) + (d.cost || 0);
            const tok = (d.input_tokens || 0) + (d.output_tokens || 0);
            dailyTokenMap[day][model] = (dailyTokenMap[day][model] || 0) + tok;
            dailyTokenMap[day].total += tok;
            dIn += d.input_tokens || 0; dCr += d.cache_read_tokens || 0; dCw += d.cache_write_tokens || 0;
          });
          const tot = dIn + dCr + dCw;
          if ((slice.messages || 0) >= 3 && tot > 0) {
            (cacheEffByDate[day] = cacheEffByDate[day] || []).push(dCr / tot * 100);
          }
        });
      } else {
        if (!s.date) return;
        if (!dailyMsgMap[s.date]) dailyMsgMap[s.date] = {date: s.date, messages: 0, sessions: 0};
        dailyMsgMap[s.date].messages += s.messages || 0;
        dailyMsgMap[s.date].sessions += 1;
        if (!dailyCostMap[s.date]) dailyCostMap[s.date] = {date: s.date, total: 0};
        if (!dailyTokenMap[s.date]) dailyTokenMap[s.date] = {date: s.date, total: 0};
        dailyCostMap[s.date].total += s.cost || 0;
        Object.entries(s.model_breakdown || {}).forEach(([model, d]) => {
          dailyCostMap[s.date][model] = (dailyCostMap[s.date][model] || 0) + (d.cost || 0);
          const tok = (d.input_tokens || 0) + (d.output_tokens || 0);
          dailyTokenMap[s.date][model] = (dailyTokenMap[s.date][model] || 0) + tok;
          dailyTokenMap[s.date].total += tok;
        });
        if ((s.messages || 0) >= 3) {
          const tot = (s.input_tokens || 0) + (s.cache_read_tokens || 0) + (s.cache_write_tokens || 0);
          if (tot > 0) (cacheEffByDate[s.date] = cacheEffByDate[s.date] || []).push((s.cache_read_tokens || 0) / tot * 100);
        }
      }
    });
    const allDates = [...new Set([...Object.keys(dailyCostMap), ...Object.keys(dailyMsgMap)])].sort();
    F.daily_costs = allDates.map(d => dailyCostMap[d] || {date: d, total: 0});
    F.daily_tokens = allDates.map(d => dailyTokenMap[d] || {date: d, total: 0});
    F.daily_messages = allDates.map(d => dailyMsgMap[d] || {date: d, messages: 0, sessions: 0});
    F.daily_cache_efficiency = _boxplot(cacheEffByDate);
  }

  // Cumulative series are built mode-aware inside renderCostCharts()
  // (convert each day first, then accumulate).

  // Recalculate model_summary from filtered sessions
  const modelMap = {};
  F.sessions.forEach(s => {
    Object.entries(s.model_breakdown || {}).forEach(([model, d]) => {
      if (!modelMap[model]) modelMap[model] = {model, cost:0, input_tokens:0, output_tokens:0, cache_read_tokens:0, calls:0};
      modelMap[model].cost += d.cost || 0;
      modelMap[model].input_tokens += d.input_tokens || 0;
      modelMap[model].output_tokens += d.output_tokens || 0;
      modelMap[model].cache_read_tokens += d.cache_read_tokens || 0;
      modelMap[model].calls += d.calls || 0;
    });
  });
  F.model_summary = Object.values(modelMap).sort((a, b) => b.cost - a.cost);

  // cost_by_token_type: scale by ratio of filtered cost to original cost
  const filteredTotalCost = F.model_summary.reduce((s, m) => s + m.cost, 0);
  const ratio = D.kpi.total_cost > 0 ? filteredTotalCost / D.kpi.total_cost : 0;
  F.cost_by_token_type = {
    input: D.cost_by_token_type.input * ratio,
    output: D.cost_by_token_type.output * ratio,
    cache_read: D.cost_by_token_type.cache_read * ratio,
    cache_write: D.cost_by_token_type.cache_write * ratio,
    cache_savings: (D.cost_by_token_type.cache_savings || 0) * ratio,
  };

  // Recalculate projects from filtered sessions
  const projMap = {};
  F.sessions.forEach(s => {
    if (!projMap[s.project]) projMap[s.project] = {name: s.project, sessions:0, messages:0, cost:0, output_tokens:0, file_size_mb: 0, sources: new Set()};
    const p = projMap[s.project];
    p.sessions++;
    p.messages += s.messages || 0;
    p.cost += s.cost || 0;
    p.output_tokens += s.output_tokens || 0;
    p.file_size_mb = Math.max(p.file_size_mb, s.file_size_mb || 0);
    if (s.source) p.sources.add(s.source);
  });
  F.projects = Object.values(projMap).map(p => { p.sources = [...p.sources].sort(); return p; }).sort((a, b) => b.cost - a.cost);

  // Hour/weekday distributions. Unfiltered: server distributions (per-message,
  // local-time) directly. Filtered: sum per-session hour_hist/weekday_hist
  // (same local-time buckets), reusing the server's labels/order for the
  // weekday axis so toggling a filter never changes labels.
  if (noFilter) {
    F.hourly_distribution = D.hourly_distribution;
    F.weekday_distribution = D.weekday_distribution;
  } else {
    const hourly = (D.hourly_distribution || []).map(r => ({hour: r.hour, messages: 0}));
    const wsum = [0, 0, 0, 0, 0, 0, 0];
    F.sessions.forEach(s => {
      const hh = s.hour_hist || {};
      for (const h in hh) { if (hourly[+h]) hourly[+h].messages += hh[h]; }
      const wh = s.weekday_hist || {};
      for (const w in wh) { wsum[+w] += wh[w]; }
    });
    F.hourly_distribution = hourly;
    F.weekday_distribution = (D.weekday_distribution || []).map((row, i) => ({day: row.day, messages: wsum[i]}));
  }

  // Recalculate tool_summary
  const toolMap = {};
  F.sessions.forEach(s => {
    Object.entries(s.tools || {}).forEach(([name, count]) => {
      toolMap[name] = (toolMap[name] || 0) + count;
    });
  });
  F.tool_summary = Object.entries(toolMap).map(([name, count]) => ({name, count})).sort((a, b) => b.count - a.count);

  // Recalculate tool_token_summary + reasoning_summary
  const toolTokenMap = {};
  let reasoningOut = 0, reasoningCost = 0;
  F.sessions.forEach(s => {
    Object.entries(s.tool_tokens || {}).forEach(([name, v]) => {
      const agg = toolTokenMap[name] || (toolTokenMap[name] = {calls: 0, output_tokens: 0, cost: 0});
      agg.calls += v.calls || 0;
      agg.output_tokens += v.output_tokens || 0;
      agg.cost += v.cost || 0;
    });
    reasoningOut += s.reasoning_output_tokens || 0;
    reasoningCost += s.reasoning_cost || 0;
  });
  F.tool_token_summary = Object.entries(toolTokenMap)
    .map(([name, v]) => ({name, ...v, cost: +v.cost.toFixed(4)}))
    .sort((a, b) => b.output_tokens - a.output_tokens);
  F.reasoning_summary = {output_tokens: reasoningOut, cost: +reasoningCost.toFixed(4)};

  // Recalculate write_categories_summary from filtered sessions.
  const WC_KEYS = ['screen_text','screen_text_narration','thinking','file_writes','bash_commands','tool_inputs'];
  const wcAgg = Object.fromEntries(WC_KEYS.map(k => [k, 0]));
  F.sessions.forEach(s => {
    const wc = s.write_categories || {};
    WC_KEYS.forEach(k => { wcAgg[k] += wc[k] || 0; });
  });
  const wcTotal = WC_KEYS.reduce((s,k) => s + wcAgg[k], 0) || 1;
  F.write_categories_summary = WC_KEYS.map(k => ({
    category: k,
    output_tokens: wcAgg[k],
    share: +(wcAgg[k] / wcTotal).toFixed(4),
  }));

  // Recalculate KPI. total_cost uses the day-slice basis (sum over F.daily_costs):
  // multi-day sessions count only their slices inside the selected range, so this
  // KPI, the daily chart and the local-currency conversion share one attribution
  // basis. (Summing whole sessions whose end falls in range overcounted at the
  // range edge by up to the full pre-range spend of a long-running session.)
  const totalCost = F.daily_costs.reduce((s, r) => s + (r.total || 0), 0);
  const totalSessions = F.sessions.length;
  const totalMessages = F.sessions.reduce((s, x) => s + (x.messages || 0), 0);
  const totalOutputTokens = F.sessions.reduce((s, x) => s + (x.output_tokens || 0), 0);
  const totalInputTokens = F.sessions.reduce((s, x) => s + (x.input_tokens || 0), 0);
  const totalCacheReadTokens = F.sessions.reduce((s, x) => s + (x.cache_read_tokens || 0), 0);
  const totalCacheWriteTokens = F.sessions.reduce((s, x) => s + (x.cache_write_tokens || 0), 0);
  const dates = F.sessions.map(s => s.date).filter(Boolean).sort();
  F.kpi = {
    total_cost: totalCost,
    actual_plan_cost: calcFilteredPlanCost(F.daily_costs.map(r => r.date)),
    total_sessions: totalSessions,
    total_messages: totalMessages,
    total_output_tokens: totalOutputTokens,
    total_input_tokens: totalInputTokens,
    total_cache_read_tokens: totalCacheReadTokens,
    total_cache_write_tokens: totalCacheWriteTokens,
    first_session: dates.length > 0 ? dates[0] : D.kpi.first_session,
    last_session: dates.length > 0 ? dates[dates.length - 1] : D.kpi.last_session,
  };

  // Recalculate agent_summary from filtered sessions
  const agentTypeMap = {};
  const agentDescMap = {};
  let totalDispatches = 0;
  F.sessions.forEach(s => {
    (s.agent_dispatches || []).forEach(ad => {
      totalDispatches++;
      const t = ad.type || 'general-purpose';
      agentTypeMap[t] = (agentTypeMap[t] || 0) + 1;
      const d = ad.description || ad.desc || '';
      if (d) agentDescMap[d] = (agentDescMap[d] || 0) + 1;
    });
  });
  F.agent_summary = {
    total_dispatches: totalDispatches,
    type_distribution: Object.entries(agentTypeMap).map(([type, count]) => ({type, count})).sort((a,b) => b.count - a.count),
    top_descriptions: Object.entries(agentDescMap).map(([desc, count]) => ({desc, count})).sort((a,b) => b.count - a.count).slice(0, 10),
  };

  // Recalculate error_summary from filtered sessions
  const fErrors = F.sessions.reduce((s, x) => s + (x.error_count || 0), 0);
  const fToolCalls = F.sessions.reduce((s, x) => s + (x.api_calls || 0), 0);
  const fErrByTool = {}, fErrByCat = {}, fErrBySrc = {};
  F.sessions.forEach(s => {
    (s.errors || []).forEach(e => {
      fErrByTool[e.tool || 'unknown'] = (fErrByTool[e.tool || 'unknown'] || 0) + 1;
      fErrByCat[e.category || 'other'] = (fErrByCat[e.category || 'other'] || 0) + 1;
      fErrBySrc[e.source || 'tool'] = (fErrBySrc[e.source || 'tool'] || 0) + 1;
    });
  });
  F.error_summary = {
    total_errors: fErrors,
    total_tool_calls: fToolCalls,
    error_rate: fToolCalls > 0 ? +(fErrors / fToolCalls * 100).toFixed(2) : 0,
    total_cancelled: F.sessions.reduce((s, x) => s + (x.cancelled_count || 0), 0),
    total_rejected: F.sessions.reduce((s, x) => s + (x.rejected_count || 0), 0),
    by_source: Object.entries(fErrBySrc).map(([source, count]) => ({source, count})).sort((a,b) => b.count - a.count),
    by_tool: Object.entries(fErrByTool).map(([tool, count]) => ({tool, count})).sort((a,b) => b.count - a.count),
    by_category: Object.entries(fErrByCat).map(([category, count]) => ({category, count})).sort((a,b) => b.count - a.count),
  };
}

function initTimeFilter() {
  const container = document.getElementById('timeFilter');
  const options = [{label:'All', days:0},{label:'7D', days:7},{label:'30D', days:30},{label:'90D', days:90},{label:'1Y', days:365}];
  options.forEach((opt, i) => {
    const btn = document.createElement('button');
    btn.textContent = opt.label;
    if (i === 0) btn.classList.add('active');
    btn.addEventListener('click', () => {
      container.querySelectorAll('button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      applyFilter(opt.days);
    });
    container.appendChild(btn);
  });
}

function applyFilter(days, projectFilter) {
  filterData(days, projectFilter);

  // Destroy all existing Chart.js instances
  Object.keys(charts).forEach(k => { if (charts[k]) { charts[k].destroy(); delete charts[k]; } });

  // Clear dynamic DOM containers
  document.getElementById('kpiGrid').textContent = '';
  document.getElementById('modelTableBody').textContent = '';
  document.getElementById('projectTableBody').textContent = '';

  // Re-render (but NOT renderPlan)
  renderKPI();
  renderCosts();
  renderActivity();
  renderProjects();
  renderSessions();
  renderToolUsageChart();
  renderToolTokenChart();
  renderWriteCategoriesChart();
  renderAgentsTab();
}

function renderToolUsageChart() {
  const tools = (F.tool_summary || []).slice(0, 20);
  if (tools.length > 0) {
    charts.toolUsage = new Chart(document.getElementById('chartToolUsage'), {
      type: 'bar',
      data: { labels: tools.map(t => t.name),
        datasets: [{ label: D.locale.insights.tool_calls, data: tools.map(t => t.count),
          backgroundColor: tools.map((_, i) => _VC_CAT[i % _VC_CAT.length]), borderRadius: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: { x: { ...scaleDefaults.x, title: { display: true, text: D.locale.insights.tool_calls, color: window.__vcFg2 || '#5b6473' } },
          y: { ...scaleDefaults.y, ticks: { font: { size: 11 } } } } }
    });
  }
}

const WC_LABELS = {
  screen_text: 'Final Answers',
  screen_text_narration: 'Pre-Tool Narration',
  thinking: 'Thinking',
  file_writes: 'File Writes',
  bash_commands: 'Bash Commands',
  tool_inputs: 'Other Tool Inputs',
};
// Stable per-category index into the earth-tone _VC_CAT palette (replaces the
// old bright slate/rainbow hex map so colors track the categorical theme).
const WC_CAT_ORDER = ['screen_text', 'screen_text_narration', 'thinking', 'file_writes', 'bash_commands', 'tool_inputs'];

function renderWriteCategoriesChart() {
  const canvas = document.getElementById('chartWriteCategories');
  if (!canvas) return;
  const summary = (F.write_categories_summary || []).filter(e => e.output_tokens > 0);
  if (summary.length === 0) return;

  if (charts.writeCategories) {
    try { charts.writeCategories.destroy(); } catch (e) { /* ignore */ }
  }
  charts.writeCategories = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels: summary.map(e => WC_LABELS[e.category] || e.category),
      datasets: [{
        data: summary.map(e => e.output_tokens),
        backgroundColor: summary.map((e, i) => {
          const idx = WC_CAT_ORDER.indexOf(e.category);
          return _VC_CAT[(idx >= 0 ? idx : i) % _VC_CAT.length];
        }),
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: {position: 'right'},
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const total = ctx.dataset.data.reduce((s,v)=>s+v,0);
              const pct = total > 0 ? ((ctx.raw / total) * 100).toFixed(1) : '0';
              return ctx.label + ': ' + ctx.raw.toLocaleString() + ' tokens (' + pct + '%)';
            },
          },
        },
      },
    },
  });
}

function renderToolTokenChart() {
  const data = (F.tool_token_summary || []).slice(0, 12);
  const reasoningOut = (F.reasoning_summary || {}).output_tokens || 0;

  const labels = data.map(t => t.name);
  const values = data.map(t => t.output_tokens);
  if (reasoningOut > 0) {
    labels.push('Reasoning');
    values.push(reasoningOut);
  }
  if (values.length === 0) return;

  const palette = _VC_CAT;

  const canvas = document.getElementById('chartToolTokens');
  if (!canvas) return;
  charts.toolTokens = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: labels.map((_, i) => palette[i % palette.length]),
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: {position: 'right'},
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const total = ctx.dataset.data.reduce((s,v)=>s+v,0);
              const pct = total > 0 ? ((ctx.raw / total) * 100).toFixed(1) : '0';
              return ctx.label + ': ' + ctx.raw.toLocaleString() + ' tokens (' + pct + '%)';
            },
          },
        },
      },
    },
  });
}

// ── KPI Cards ──────────────────────────────────────────────────────────
function renderKPI() {
  const k = F.kpi;
  const dispName = anonMode ? 'Anonymous' : D.account.name;
  document.getElementById('headerMeta').textContent =
    dispName + ' | ' + k.first_session + ' – ' + k.last_session +
    ' | ' + D.locale.header.generated + ': ' + new Date(D.generated_at).toLocaleString(D.locale.locale_code);

  const grid = document.getElementById('kpiGrid');
  const cards = [
    {cls:'cost', label:D.locale.kpi.api_equivalent, value:fmtUSD(k.total_cost), sub:D.locale.kpi.api_equivalent_sub + fmtUSD(k.actual_plan_cost), tip: D.locale.locale_code === 'de' ? 'Was diese Nutzung über die API kosten würde (ohne Abo). Darunter: tatsächlich bezahlter Abo-Preis im gewählten Zeitraum.' : 'What this usage would cost via the API (without subscription). Below: actual subscription cost paid in the selected period.'},
    {cls:'messages', label:D.locale.kpi.messages, value:fmt(k.total_messages), sub:D.locale.kpi.messages_sub_prefix+k.total_sessions+D.locale.kpi.messages_sub_suffix},
    {cls:'sessions', label:D.locale.kpi.sessions, value:fmt(k.total_sessions), sub:k.first_session+' - '+k.last_session},
    {cls:'tokens', label:'Tokens', value:'', sub:'', tip: D.locale.locale_code === 'de' ? 'Tokens sind die Texteinheiten die das Sprachmodell verarbeitet (ca. 0.75 Worte pro Token)' : 'Tokens are the text units processed by the language model (approx. 0.75 words per token)'},
  ];
  cards.forEach(c => {
    const div = document.createElement('div');
    div.className = 'kpi-card ' + c.cls;
    const lbl = document.createElement('div'); lbl.className = 'label'; lbl.textContent = c.label;
    if (c.tip) lbl.title = c.tip;
    const val = document.createElement('div'); val.className = 'value'; val.textContent = c.value;
    const sub = document.createElement('div'); sub.className = 'sub'; sub.textContent = c.sub;
    div.appendChild(lbl); div.appendChild(val); div.appendChild(sub);
    grid.appendChild(div);
  });

  // Token breakdown card — replace placeholder with detailed version
  const tokCard = grid.querySelector('.kpi-card.tokens');
  if (tokCard) {
    const totalIn = (k.total_input_tokens||0) + (k.total_cache_read_tokens||0) + (k.total_cache_write_tokens||0);
    const valEl = tokCard.querySelector('.value');
    valEl.textContent = fmtTokens(totalIn + (k.total_output_tokens||0));
    valEl.title = D.locale.locale_code === 'de' ? 'Summe aller Tokens (Input + Output + Cache)' : 'Total tokens (input + output + cache)';
    const sub = tokCard.querySelector('.sub');
    sub.style.cssText = 'line-height:1.6;font-size:0.78em';
    sub.textContent = '';
    const line1 = document.createElement('span');
    line1.textContent = 'Out: ' + fmtTokens(k.total_output_tokens||0) + ' · In: ' + fmtTokens(k.total_input_tokens||0);
    const br = document.createElement('br');
    const line2 = document.createElement('span');
    line2.textContent = 'Cache Read: ' + fmtTokens(k.total_cache_read_tokens||0) + ' · Write: ' + fmtTokens(k.total_cache_write_tokens||0);
    const ttOut = D.locale.locale_code === 'de' ? 'Von Claude generierter Text' : 'Text generated by Claude';
    const ttIn = D.locale.locale_code === 'de' ? 'Neue (nicht gecachte) Eingabe-Tokens pro Request' : 'New (non-cached) input tokens per request';
    const ttCR = D.locale.locale_code === 'de' ? 'Konversationskontext aus dem Cache gelesen \u2013 wird bei jedem Turn erneut gesendet, daher die hohe Zahl' : 'Conversation context read from cache \u2013 resent every turn, hence the large number';
    const ttCW = D.locale.locale_code === 'de' ? 'Tokens die in den Cache geschrieben wurden' : 'Tokens written to the prompt cache';
    line1.title = 'Out: ' + ttOut + '\nIn: ' + ttIn;
    line2.title = 'Cache Read: ' + ttCR + '\nWrite: ' + ttCW;
    sub.appendChild(line1);
    sub.appendChild(br);
    sub.appendChild(line2);
  }
}

// ── Tabs ───────────────────────────────────────────────────────────────
const TAB_NAMES = [
  {id:'costs', label:D.locale.tabs.costs},
  {id:'plan', label:D.locale.tabs.plan},
  {id:'activity', label:D.locale.tabs.activity},
  {id:'sessions', label:D.locale.tabs.sessions},
  {id:'insights', label:D.locale.tabs.insights},
];

function initTabs() {
  const bar = document.getElementById('tabBar');
  TAB_NAMES.forEach((t, i) => {
    const btn = document.createElement('button');
    btn.className = 'tab-btn' + (i === 0 ? ' active' : '');
    btn.textContent = t.label;
    btn.addEventListener('click', () => activateTabByName(t.id, true));
    bar.appendChild(btn);
  });
}

function switchTab(name, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
}

// Central tab activator + hash router. Activates the named tab across
// both UIs (legacy .tab-btn + Variant-C .vc-tab) and keeps location.hash
// in sync so deep links (#limits) and F5 reload preserve the visible tab.
function activateTabByName(name, updateHash) {
  const tab = TAB_NAMES.find(t => t.id === name);
  if (!tab) return false;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.vc-tab').forEach(b => b.classList.remove('active'));
  const legacy = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.textContent === tab.label);
  if (legacy) legacy.classList.add('active');
  const target = document.getElementById('tab-' + name);
  if (target) target.classList.add('active');
  const vc = document.querySelector('.vc-tab[data-tab="' + name + '"]');
  if (vc) vc.classList.add('active');
  // Plan & Billing is inherently full-period (driven by D.plan, not the
  // filtered set F), so the range filter has no effect there — grey it out and
  // disable clicks while that tab is active.
  const rangeEl = document.getElementById('vcRange');
  if (rangeEl) {
    const muted = name === 'plan';
    rangeEl.classList.toggle('is-muted', muted);
    rangeEl.title = muted ? 'Range filter does not apply to Plan & Billing (always full period)' : '';
  }
  if (updateHash) {
    const newHash = '#' + name;
    if (location.hash !== newHash) {
      // replaceState so tab clicks don't pollute browser history with
      // back-stack entries for every navigation flick.
      history.replaceState(null, '', newHash);
    }
  }
  return true;
}

function tabFromHash() {
  const h = (location.hash || '').slice(1).split('?')[0];
  if (!h) return null;
  return TAB_NAMES.find(t => t.id === h) ? h : null;
}

// ── Idle-gap aggregate card (Task 2) ────────────────────────────────────
function renderIdleGapAggregateCard() {
  const el = document.getElementById('idleGapAggregateCard');
  if (!el) return;
  const agg = (F && F.idle_gap_aggregate) || null;
  if (!agg || (!agg.total_overspend_tokens && !agg.nogap_flush_count)) {
    el.style.display = 'none';
    return;
  }
  const L = (D && D.locale && D.locale.idleGap) || {};
  const LF = (D && D.locale && D.locale.cacheFlush) || {};
  const T = {
    dashTitle: L.dashTitle || 'Idle-gap overhead (full range)',
    sessions:  L.sessions  || 'Sessions',
    nogapTitle: LF.cardTitle || 'Cache-flush anomalies (no gap)',
    events: LF.events || 'events',
  };
  const fmtTokensAgg = (n) => n >= 1_000_000 ? (n/1_000_000).toFixed(1) + 'M' : (n >= 1000 ? (n/1000).toFixed(0) + 'k' : String(n));
  let html = '';
  if (agg.total_overspend_tokens > 0) {
    html +=
      '<div class="vc-idle-row"><span class="vc-k">' + T.dashTitle + '</span> ' +
      '<span class="vc-v">≈ ' + fmtTokensAgg(agg.total_overspend_tokens) + ' Tokens · ≈ $' + (agg.total_overspend_usd || 0).toFixed(2) + ' · ' +
      (agg.session_count_with_overspend || 0) + ' ' + T.sessions + '</span></div>';
  }
  if (agg.nogap_flush_count > 0) {
    html +=
      '<div class="vc-idle-row"><span class="vc-k">' + T.nogapTitle + '</span> ' +
      '<span class="vc-v">' + agg.nogap_flush_count + ' ' + T.events + ' · ≈ ' + fmtTokensAgg(agg.nogap_rewrite_tokens) + ' Tokens · ≈ $' + (agg.nogap_rewrite_usd || 0).toFixed(2) + '</span></div>';
  }
  el.innerHTML = html;
  el.style.display = '';
}

// Sonnet 4.x cache_write_5m rate, used to estimate idle-gap overspend
// and no-gap cache-rewrite costs in USD. Update if Anthropic reprices
// the cache_write_5m tier.
const IDLE_GAP_OVERSPEND_USD_PER_M = 3.75;

function recomputeIdleGapAggregate(filteredSessions) {
  let totalOversp = 0;
  let withOversp = 0;
  let nogapFlushes = 0;
  let nogapRewrite = 0;
  for (const s of (filteredSessions || [])) {
    const igs = s.idle_gap_summary;
    if (igs && igs.estimated_overspend_tokens > 0) {
      totalOversp += igs.estimated_overspend_tokens;
      withOversp += 1;
    }
    nogapFlushes += s.cache_nogap_flush_count || 0;
    nogapRewrite += s.cache_nogap_rewrite_tokens || 0;
  }
  F.idle_gap_aggregate = {
    total_overspend_tokens: totalOversp,
    total_overspend_usd: Math.round(totalOversp * IDLE_GAP_OVERSPEND_USD_PER_M / 1_000_000 * 100) / 100,
    session_count_with_overspend: withOversp,
    nogap_flush_count: nogapFlushes,
    nogap_rewrite_tokens: nogapRewrite,
    nogap_rewrite_usd: Math.round(nogapRewrite * IDLE_GAP_OVERSPEND_USD_PER_M / 1_000_000 * 100) / 100,
  };
}

// ── Tab 1: Costs ───────────────────────────────────────────────────────
// ── Costs tab metric toggle (USD | local currency | Tokens) ───────────
// Owns #vcCostMeta (updateVcTabMetas leaves it alone). Pattern follows the
// Plan & Billing currency toggle in renderPlan().
function renderCostMetricToggle() {
  const meta = document.getElementById('vcCostMeta');
  if (!meta) return;
  meta.innerHTML = '';
  const activeRange = document.querySelector('.vc-range-btn.active');
  const range = activeRange ? (activeRange.dataset.days === '0' ? 'all' : activeRange.dataset.days + 'd') : 'all';
  meta.appendChild(document.createTextNode(range + ' · daily · '));
  const wrap = document.createElement('span');
  wrap.style.cssText = 'display:inline-flex;gap:4px;align-items:center;';
  const mkBtn = (mode, label) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = label;
    const on = costMetricMode === mode;
    b.style.cssText = 'padding:2px 8px;border:1px solid var(--border);background:' + (on ? 'var(--accent)' : 'transparent') + ';color:' + (on ? '#fff' : 'inherit') + ';cursor:pointer;font:inherit;border-radius:0;';
    b.onclick = () => {
      if (costMetricMode === mode) return;
      costMetricMode = mode;
      renderCostMetricToggle();
      renderCostCharts(); // does its own defensive chart destroy
      renderVcKpis();     // money KPI (API equivalent) follows the currency mode
    };
    return b;
  };
  wrap.appendChild(mkBtn('usd', 'USD'));
  if (D.plan && D.plan.currency_symbol && currentFx()) {
    wrap.appendChild(mkBtn('local', D.plan.currency_symbol));
  }
  wrap.appendChild(mkBtn('tokens', (D.locale.costs && D.locale.costs.toggle_tokens) || 'Tokens'));
  meta.appendChild(wrap);
}

// Format a value according to the active costs metric mode.
function costModeFmt(v) {
  if (costMetricMode === 'tokens') return fmtTokens(v);
  if (costMetricMode === 'local') {
    return v.toLocaleString(D.locale.locale_code, {minimumFractionDigits: 2, maximumFractionDigits: 2})
      + ' ' + ((D.plan && D.plan.currency_symbol) || '');
  }
  return fmtUSD(v);
}

// Dashed vertical markers at each weekly-limit reset. The anchor weekday is
// config-driven via D.week_anchor ("mon".."sun", default "mon") so the chart
// markers and the backend weekly-hit analysis share one week boundary. Reads
// the chart's category x labels (YYYY-MM-DD). The line is drawn on the
// boundary between the previous day and the anchor day, at the week start.
const _WEEK_ANCHOR_NUM = { sun: 0, mon: 1, tue: 2, wed: 3, thu: 4, fri: 5, sat: 6 };
function weekAnchorDayNum() {
  const a = String(D.week_anchor || 'mon').slice(0, 3).toLowerCase();
  return _WEEK_ANCHOR_NUM[a] !== undefined ? _WEEK_ANCHOR_NUM[a] : 1;
}
const weekResetMarkerPlugin = {
  id: 'weekResetMarker',
  afterDatasetsDraw(chart) {
    const xScale = chart.scales.x;
    const labels = chart.data.labels;
    if (!xScale || !labels || !labels.length) return;
    const { ctx, chartArea } = chart;
    const n = labels.length;
    const anchorDay = weekAnchorDayNum();
    ctx.save();
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1;
    ctx.strokeStyle = window.__vcFg3 || '#918a7a';
    ctx.globalAlpha = 0.55;
    for (let i = 0; i < n; i++) {
      const parts = String(labels[i]).split('-');
      if (parts.length !== 3) continue;
      // Construct in local time (not UTC) so getDay() matches the displayed date.
      const dt = new Date(+parts[0], +parts[1] - 1, +parts[2]);
      if (dt.getDay() !== anchorDay) continue;    // config-driven weekly reset anchor
      const cur = xScale.getPixelForValue(i);
      // Boundary = midpoint to the previous day; for i===0 mirror the step.
      let x = i > 0 ? (xScale.getPixelForValue(i - 1) + cur) / 2
                    : (n > 1 ? cur - (xScale.getPixelForValue(1) - cur) / 2 : cur);
      x = Math.round(x) + 0.5;                     // crisp 1px line
      if (x < chartArea.left || x > chartArea.right) continue;
      ctx.beginPath();
      ctx.moveTo(x, chartArea.top);
      ctx.lineTo(x, chartArea.bottom);
      ctx.stroke();
    }
    ctx.restore();
  }
};

// The two metric-switchable charts (daily by model + cumulative).
// Separate from renderCosts() so the toggle can rebuild just these two.
function renderCostCharts() {
  const mode = costMetricMode;
  // Defensive destroy: the metric toggle rebuilds these two without going
  // through applyFilter()'s bulk chart teardown.
  if (charts.dailyCost) { charts.dailyCost.destroy(); delete charts.dailyCost; }
  if (charts.cumCost) { charts.cumCost.destroy(); delete charts.cumCost; }
  const L = D.locale.costs;
  const models = D.models;
  const dates = F.daily_costs.map(d => d.date);
  const dailySrc = mode === 'tokens' ? F.daily_tokens : F.daily_costs;
  // Cumulative series: convert each day at its own FX rate first, then
  // accumulate. (Converting a running USD total with the current day's rate
  // rescaled all prior spending whenever the rate changed between periods.)
  const cumRows = mode === 'tokens' ? F.daily_tokens : F.daily_costs;
  const yTitle = mode === 'tokens' ? 'Tokens'
    : (mode === 'local' ? ((D.plan && D.plan.currency_symbol) || 'USD') : 'USD');
  // fxForDate() can't return null here: the local-mode button is gated on currentFx().
  const conv = (v, date) => mode === 'local' ? v * (fxForDate(date) || 0) : v;
  const yTicks = mode === 'tokens'
    ? { ...scaleDefaults.y.ticks, callback: v => fmtTokens(v) }
    : scaleDefaults.y.ticks;

  const dailyTitle = document.getElementById('chartDailyCostTitle');
  if (dailyTitle) dailyTitle.textContent = mode === 'tokens' ? L.daily_tokens : L.daily_cost;
  const cumTitle = document.getElementById('chartCumCostTitle');
  if (cumTitle) cumTitle.textContent = mode === 'tokens' ? L.cumulative_tokens : L.cumulative;

  charts.dailyCost = new Chart(document.getElementById('chartDailyCost'), {
    type: 'bar',
    plugins: [weekResetMarkerPlugin],
    data: {
      labels: dates,
      datasets: models.map(m => ({
        label: m,
        data: dailySrc.map(d => conv(d[m] || 0, d.date)),
        backgroundColor: vcModelColor(m),
        borderRadius: 0,
      }))
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: window.__vcFg2 || '#4d4a42' } },
        tooltip: { mode: 'index', intersect: false,
          callbacks: { label: ctx => ctx.dataset.label + ': ' + costModeFmt(ctx.parsed.y) } }
      },
      scales: { x: { ...scaleDefaults.x, stacked: true }, y: { ...scaleDefaults.y, ticks: yTicks, stacked: true, title: { display: true, text: yTitle, color: window.__vcFg2 || '#5b6473' } } }
    }
  });

  charts.cumCost = new Chart(document.getElementById('chartCumCost'), {
    type: 'line',
    plugins: [weekResetMarkerPlugin],
    data: {
      labels: cumRows.map(r => r.date),
      datasets: [{ label: mode === 'tokens' ? L.cumulative_tokens_label : L.cumulative_label,
        data: (() => { let acc = 0; return cumRows.map(r => { acc += conv(r.total || 0, r.date); return acc; }); })(),
        borderColor: vcColor(1), backgroundColor: 'rgba(245,158,11,0.1)', fill: true, tension: 0.3, pointRadius: 2 }]
    },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: ctx => costModeFmt(ctx.parsed.y) } } },
      scales: { x: scaleDefaults.x, y: { ...scaleDefaults.y, ticks: yTicks, title: { display: true, text: yTitle, color: window.__vcFg2 || '#5b6473' } } } }
  });

  // API value by token type — follows the same USD|local|Tokens toggle as the
  // two charts above. cost_by_token_type is an all-time aggregate (no per-date
  // FX), so local mode uses the blended currentFx(); tokens mode sums the raw
  // per-type token counts from the filtered sessions.
  if (charts.tokenType) { charts.tokenType.destroy(); delete charts.tokenType; }
  const ttTitle = document.getElementById('chartTokenTypeTitle');
  if (ttTitle) ttTitle.textContent = mode === 'tokens' ? (L.token_type_tokens || L.token_type) : L.token_type;
  const cbt = F.cost_by_token_type;
  let ttData, ttAxisTitle;
  if (mode === 'tokens') {
    const sumTok = field => F.sessions.reduce((s, se) => s + (se[field] || 0), 0);
    ttData = [sumTok('input_tokens'), sumTok('output_tokens'), sumTok('cache_read_tokens'), sumTok('cache_write_tokens')];
    ttAxisTitle = 'Tokens';
  } else {
    const fx = mode === 'local' ? (currentFx() || 1) : 1;
    ttData = [cbt.input * fx, cbt.output * fx, cbt.cache_read * fx, cbt.cache_write * fx];
    ttAxisTitle = mode === 'local' ? ((D.plan && D.plan.currency_symbol) || 'USD') : 'USD';
  }
  charts.tokenType = new Chart(document.getElementById('chartTokenType'), {
    type: 'bar',
    data: {
      labels: ['Input', 'Output', 'Cache Read', 'Cache Write'],
      datasets: [{ data: ttData,
        backgroundColor: [vcColor(0), vcRgba(0, 0.7), vcColor(1), vcColor(2)], borderRadius: 0 }]
    },
    options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: ctx => costModeFmt(ctx.parsed.x) } } },
      scales: { x: { ...scaleDefaults.x, ticks: mode === 'tokens' ? { ...scaleDefaults.x.ticks, callback: v => fmtTokens(v) } : scaleDefaults.x.ticks, title: { display: true, text: ttAxisTitle, color: window.__vcFg2 || '#5b6473' } }, y: scaleDefaults.y } }
  });
}

function renderCosts() {
  renderCostMetricToggle();
  renderCostCharts();

  // Pricing notice: Claude models seen in the data with no PRICING entry, so
  // their cost is only estimated. pricing_warnings is global (not filtered).
  const pricingNotice = document.getElementById('modelPricingNotice');
  if (pricingNotice) {
    const warnings = D.pricing_warnings || [];
    if (warnings.length) {
      const names = warnings.map(w => w.display).join(', ');
      const tmpl = (D.locale.costs && D.locale.costs.pricing_notice) || 'Estimated pricing for {models}: not in the price table.';
      const parts = tmpl.split('{models}');
      pricingNotice.className = 'model-pricing-notice';
      pricingNotice.textContent = '';
      pricingNotice.appendChild(document.createTextNode(parts[0]));
      const strong = document.createElement('strong');
      strong.textContent = names;
      pricingNotice.appendChild(strong);
      pricingNotice.appendChild(document.createTextNode(parts[1] || ''));
    } else {
      pricingNotice.className = '';
      pricingNotice.textContent = '';
    }
  }

  // Model table
  const tbody = document.getElementById('modelTableBody');
  F.model_summary.forEach(m => {
    const tr = document.createElement('tr');
    const cells = [m.model, fmtUSD(m.cost), fmtTokens(m.output_tokens), fmtTokens(m.input_tokens), fmtTokens(m.cache_read_tokens), fmt(m.calls)];
    const labels = ['Model', 'API Value', 'Output', 'Input', 'Cache Read', 'API Calls'];
    cells.forEach((val, i) => {
      const td = document.createElement('td');
      if (i > 0) td.className = 'num';
      else td.className = 'primary';
      td.setAttribute('data-label', labels[i]);
      td.textContent = val;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  // Cache Efficiency
  const ct = F.cost_by_token_type;
  const cacheKpi = document.getElementById('cacheKpi');
  if (cacheKpi && ct) {
    const cacheRead = F.sessions.reduce((s,se) => s + (se.cache_read_tokens || 0), 0);
    const cacheWrite = F.sessions.reduce((s,se) => s + (se.cache_write_tokens || 0), 0);
    cacheKpi.innerHTML = [
      '<div class="kpi-card"><div class="label">Cache Read Tokens</div>',
      '<div class="value" style="color:var(--cyan)">' + fmtTokens(cacheRead) + '</div></div>',
      '<div class="kpi-card"><div class="label">Cache Write Tokens</div>',
      '<div class="value" style="color:var(--blue)">' + fmtTokens(cacheWrite) + '</div></div>',
      '<div class="kpi-card savings"><div class="label">Estimated Cache Savings</div>',
      '<div class="value" style="color:var(--green)">' + fmtUSD(ct.cache_savings || 0) + '</div>',
      '<div class="sub">vs. full input pricing</div></div>'
    ].join('');
  }

  // Cache Efficiency per Day (box plot + median line, fallback whiskers for n<4)
  const ceCanvas = document.getElementById('chartCacheEffDaily');
  if (ceCanvas && F.daily_cache_efficiency && F.daily_cache_efficiency.length) {
    const ce = F.daily_cache_efficiency;
    const boxPlotPlugin = {
      id: 'cacheEffBoxPlot',
      beforeDatasetsDraw(chart) {
        const { ctx, chartArea, scales: { y } } = chart;
        const meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data || !meta.data.length) return;
        const stroke = (window.__vcFg3 || '#918a7a');
        const fill = vcRgba(2, 0.18);
        const fillEdge = vcColor(2);
        const medianColor = vcColor(0);
        const plotW = chartArea.right - chartArea.left;
        const boxW = Math.max(3, Math.min(10, (plotW / ce.length) * 0.55));
        const cap = Math.max(2, boxW * 0.35);
        ctx.save();
        ce.forEach((d, i) => {
          const pt = meta.data[i];
          if (!pt) return;
          const px = pt.x;
          const yMed = y.getPixelForValue(d.median);
          const yWl = y.getPixelForValue(d.whisker_low);
          const yWh = y.getPixelForValue(d.whisker_high);

          // Whisker line + caps (always drawn)
          ctx.strokeStyle = stroke;
          ctx.lineWidth = 1;
          ctx.globalAlpha = 0.6;
          ctx.beginPath();
          ctx.moveTo(px, yWl); ctx.lineTo(px, yWh);
          ctx.moveTo(px - cap, yWl); ctx.lineTo(px + cap, yWl);
          ctx.moveTo(px - cap, yWh); ctx.lineTo(px + cap, yWh);
          ctx.stroke();

          // Box: only if we have a meaningful distribution (n >= 4)
          if (d.sessions >= 4 && d.q3 > d.q1) {
            const yQ1 = y.getPixelForValue(d.q1);
            const yQ3 = y.getPixelForValue(d.q3);
            ctx.globalAlpha = 1;
            ctx.fillStyle = fill;
            ctx.strokeStyle = fillEdge;
            ctx.lineWidth = 1;
            ctx.fillRect(px - boxW / 2, yQ3, boxW, yQ1 - yQ3);
            ctx.strokeRect(px - boxW / 2, yQ3, boxW, yQ1 - yQ3);
            // Median bar inside box
            ctx.strokeStyle = medianColor;
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(px - boxW / 2, yMed);
            ctx.lineTo(px + boxW / 2, yMed);
            ctx.stroke();
          }

          // Outliers
          if (d.outliers && d.outliers.length) {
            ctx.globalAlpha = 0.7;
            ctx.fillStyle = stroke;
            d.outliers.forEach(v => {
              const yo = y.getPixelForValue(v);
              ctx.beginPath();
              ctx.arc(px, yo, 1.5, 0, Math.PI * 2);
              ctx.fill();
            });
          }
        });
        ctx.restore();
      },
    };
    charts.cacheEffDaily = new Chart(ceCanvas, {
      type: 'line',
      data: {
        labels: ce.map(d => d.date),
        datasets: [
          {
            label: 'Median',
            data: ce.map(d => d.median),
            borderColor: vcColor(0),
            backgroundColor: vcColor(0),
            pointRadius: 0,
            pointHoverRadius: 4,
            tension: 0.25,
            fill: false,
            borderWidth: 1.5,
          },
        ],
      },
      plugins: [boxPlotPlugin],
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            mode: 'index', intersect: false,
            callbacks: {
              label: ctx => {
                const d = ce[ctx.dataIndex];
                if (!d) return '';
                const parts = ['Median ' + d.median.toFixed(1) + '%'];
                if (d.sessions >= 4) {
                  parts.push('IQR ' + d.q1.toFixed(1) + '-' + d.q3.toFixed(1) + '%');
                }
                parts.push('Range ' + d.whisker_low.toFixed(1) + '-' + d.whisker_high.toFixed(1) + '%');
                if (d.outliers && d.outliers.length) {
                  parts.push(d.outliers.length + ' outlier' + (d.outliers.length > 1 ? 's' : ''));
                }
                parts.push(d.sessions + ' sess');
                return parts.join('  ·  ');
              },
            },
          },
        },
        scales: {
          x: scaleDefaults.x,
          y: {
            ...scaleDefaults.y,
            min: 0, max: 100,
            title: { display: true, text: '%', color: window.__vcFg2 || '#5b6473' },
            ticks: { ...scaleDefaults.y.ticks, callback: v => v + '%' },
          },
        },
      },
    });
  }

  // Cache flushes per day: gap = TTL victims (structural), no-gap = anomalies
  // (e.g. invalidation bugs) - loud color on the actionable series.
  const cfCanvas = document.getElementById('chartCacheFlushDaily');
  if (cfCanvas) {
    const flushByDate = {};
    F.sessions.forEach(s => {
      if (!s.date) return;
      if (!flushByDate[s.date]) flushByDate[s.date] = { gap: 0, nogap: 0 };
      flushByDate[s.date].gap += s.cache_flush_count || 0;
      flushByDate[s.date].nogap += s.cache_nogap_flush_count || 0;
    });
    const flushDates = Object.keys(flushByDate)
      .filter(d => flushByDate[d].gap || flushByDate[d].nogap)
      .sort();
    const LF = (D.locale && D.locale.cacheFlush) || {};
    charts.cacheFlushDaily = new Chart(cfCanvas, {
      type: 'bar',
      data: {
        labels: flushDates,
        datasets: [
          { label: LF.legend_gap || 'TTL/idle-gap flushes', data: flushDates.map(d => flushByDate[d].gap), backgroundColor: vcRgba(2, 0.45), borderRadius: 0 },
          { label: LF.legend_nogap || 'No-gap anomalies', data: flushDates.map(d => flushByDate[d].nogap), backgroundColor: vcColor(0), borderRadius: 0 },
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: window.__vcFg2 || '#4d4a42' } }, tooltip: { mode: 'index', intersect: false } },
        scales: { x: { ...scaleDefaults.x, stacked: true }, y: { ...scaleDefaults.y, stacked: true, ticks: { ...scaleDefaults.y.ticks, precision: 0 }, title: { display: true, text: 'Flushes', color: window.__vcFg2 || '#5b6473' } } }
      }
    });
  }

  renderIdleGapAggregateCard();
}

function _vcAccentRgb() {
  // Live accent (custom.css overrides win), theme-aware palette as fallback.
  let hex = vcAccentLive().replace('#', '');
  if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
  if (hex.length !== 6) return '176,74,47';
  const r = parseInt(hex.substr(0,2), 16);
  const g = parseInt(hex.substr(2,2), 16);
  const b = parseInt(hex.substr(4,2), 16);
  return r + ',' + g + ',' + b;
}

function renderHeatmap() {
  const container = document.getElementById('activityHeatmap');
  const monthsEl = document.getElementById('heatmapMonths');
  if (!container) return;
  const accentRgb = _vcAccentRgb();
  const msgMap = {};
  F.daily_messages.forEach(d => { msgMap[d.date] = d.messages; });
  // Backend day keys are UTC dates. Iterate the grid in UTC as well so a
  // cell's toISOString() key always names the same calendar day as the cell's
  // grid position (local-time iteration shifted every key by one day whenever
  // the local date differed from the UTC date at render time).
  const now = new Date();
  const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const startDate = new Date(today);
  startDate.setUTCDate(startDate.getUTCDate() - (24 * 7) + 1);
  while (startDate.getUTCDay() !== 1) startDate.setUTCDate(startDate.getUTCDate() - 1);
  let maxMsg = 0;
  const td = new Date(startDate);
  while (td <= today) { const k = td.toISOString().slice(0,10); maxMsg = Math.max(maxMsg, msgMap[k]||0); td.setUTCDate(td.getUTCDate()+1); }
  let html = '';
  const weeks = [];
  const d = new Date(startDate);
  let cw = [];
  while (d <= today) {
    const k = d.toISOString().slice(0,10);
    const m = msgMap[k]||0;
    // Variant-C heatmap: single-accent terracotta with opacity gradient
    let bg;
    if (m > 0 && maxMsg > 0) {
      const r = m / maxMsg;
      const opacity = (0.08 + r * 0.92).toFixed(3);
      bg = 'rgba(' + accentRgb + ',' + opacity + ')';
    } else {
      bg = 'color-mix(in srgb, var(--vc-fg-2) 9%, transparent)';
    }
    cw.push('<div class="heatmap-cell" style="background:'+bg+'" data-tip="'+k+': '+m+' messages" data-intensity="'+(maxMsg>0?(m/maxMsg).toFixed(2):0)+'"></div>');
    if (d.getUTCDay()===0) { while(cw.length<7) cw.push('<div class="heatmap-cell" style="background:transparent"></div>'); weeks.push(cw); cw=[]; }
    d.setUTCDate(d.getUTCDate()+1);
  }
  if (cw.length>0) { while(cw.length<7) cw.push('<div class="heatmap-cell" style="background:transparent"></div>'); weeks.push(cw); }
  weeks.forEach(w => { html += '<div class="heatmap-col">'+w.join('')+'</div>'; });
  container.innerHTML = html;
  if (monthsEl) {
    const months = [];
    const md = new Date(startDate);
    let lastMonth = -1, weekIdx = 0;
    while (md <= today) {
      if (md.getUTCDay()===1) { if(md.getUTCMonth()!==lastMonth) { months.push({idx:weekIdx,label:md.toLocaleString('default',{month:'short',timeZone:'UTC'})}); lastMonth=md.getUTCMonth(); } weekIdx++; }
      md.setUTCDate(md.getUTCDate()+1);
    }
    monthsEl.innerHTML = '';
    monthsEl.style.paddingLeft = '20px';
    months.forEach((m,i) => {
      const span = document.createElement('span');
      span.textContent = m.label;
      span.style.width = ((i<months.length-1 ? months[i+1].idx-m.idx : weekIdx-m.idx)*15)+'px';
      monthsEl.appendChild(span);
    });
  }
}

// ── Tab 2: Activity ────────────────────────────────────────────────────
function renderActivity() {
  // Dual-axis: daily messages (bars, left axis) + daily sessions (line, right axis).
  // Messages and sessions differ in magnitude, so each gets its own y-scale.
  charts.dailyMsgs = new Chart(document.getElementById('chartDailyMsgs'), {
    type: 'bar',
    data: { labels: F.daily_messages.map(d => d.date),
      datasets: [
        { label: D.locale.activity.messages_label, data: F.daily_messages.map(d => d.messages),
          backgroundColor: vcColor(0), borderRadius: 0, yAxisID: 'y', order: 2 },
        { type: 'line', label: D.locale.activity.sessions_label, data: F.daily_messages.map(d => d.sessions),
          borderColor: vcColor(2), backgroundColor: vcColor(2), pointRadius: 0, tension: 0.3, borderWidth: 1.5, yAxisID: 'y1', order: 1 },
      ] },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: true, labels: { color: window.__vcFg2 || '#4d4a42' } } },
      scales: {
        x: scaleDefaults.x,
        y: { ...scaleDefaults.y, position: 'left', title: { display: true, text: D.locale.activity.messages_label, color: window.__vcFg2 || '#5b6473' } },
        y1: { ...scaleDefaults.y, position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: D.locale.activity.sessions_label, color: window.__vcFg2 || '#5b6473' } },
      } }
  });

  const maxHourly = Math.max(...F.hourly_distribution.map(x => x.messages || 1));
  charts.hourly = new Chart(document.getElementById('chartHourly'), {
    type: 'polarArea',
    data: { labels: F.hourly_distribution.map(h => h.hour + ':00'),
      datasets: [{ data: F.hourly_distribution.map(h => h.messages),
        backgroundColor: F.hourly_distribution.map(h => vcRgba(0, 0.3 + 0.7 * (h.messages / maxHourly))),
        borderWidth: 0 }] },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { r: { ticks: { color: window.__vcFg3 || '#918a7a', backdropColor: 'transparent' }, grid: { color: window.__vcGrid2 || '#e8e3d6' }, angleLines: { color: window.__vcGrid2 || '#e8e3d6' } } } }
  });

  charts.weekday = new Chart(document.getElementById('chartWeekday'), {
    type: 'bar',
    data: { labels: F.weekday_distribution.map(d => d.day),
      datasets: [{ label: D.locale.activity.messages_label, data: F.weekday_distribution.map(d => d.messages),
        backgroundColor: F.weekday_distribution.map((d, i) => i >= 5 ? vcColor(1) : vcColor(0)), borderRadius: 0 }] },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } }, scales: scaleDefaults }
  });

  renderHeatmap();
}

// ── Tab 3: Projects ────────────────────────────────────────────────────
function renderProjects() {
  renderProjectTable('cost', 'desc');
}

function renderProjectTable(sortKey, sortDir) {
  const sorted = [...F.projects].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey];
    if (typeof va === 'string') return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
    return sortDir === 'asc' ? va - vb : vb - va;
  });
  const tbody = document.getElementById('projectTableBody');
  tbody.textContent = '';
  sorted.forEach(p => {
    const tr = document.createElement('tr');
    const slug = D.project_slugs && D.project_slugs[p.name];
    const dispPName = anonMode ? anonName(p.name) : p.name;
    const nameCell = (!anonMode && slug) ? '<a href="projects/'+slug+'.html">'+escHtml(dispPName)+'</a>' : escHtml(dispPName);
    const sourceCell = (p.sources || []).map(function(src) {
      const c = sourceColor(src);
      const lbl = anonMode ? anonSource(src) : src;
      return '<span class="source-badge" style="background:'+c.bg+';color:'+c.fg+'">'+escHtml(lbl)+'</span>';
    }).join(' ');
    const cells = [
      {html: nameCell, cls: 'primary', label: 'Project'},
      {html: sourceCell, cls: '', label: 'Source'},
      {val: p.sessions, cls: 'num', label: 'Sessions'},
      {val: fmt(p.messages), cls: 'num', label: 'Messages'},
      {val: fmtUSD(p.cost), cls: 'num', label: 'API Value'},
      {val: fmtTokens(p.output_tokens), cls: 'num', label: 'Output'},
      {val: String(p.file_size_mb), cls: 'num', label: 'File Size'},
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      td.setAttribute('data-label', c.label);
      if (c.html) { td.innerHTML = c.html; } else { td.textContent = c.val; }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

// ── Tab 4: Sessions ────────────────────────────────────────────────────
let sessionFilters = null;
let sessionTable = null;

// ─── Markdown export helpers ───────────────────────────────────────────
function sanitizeProjectSlug(p) {
  const s = (p || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
  return s || 'unknown';
}
function mdFilename(session) {
  const date = session.date || (session.start ? String(session.start).slice(0,10) : '0000-00-00');
  const slug = sanitizeProjectSlug(session.project);
  const id8 = (session.session_id || '').slice(0, 8);
  return date + '-' + slug + '-' + id8 + '.md';
}
function yamlEscape(v) {
  if (v == null) return '';
  const str = String(v);
  if (/[:#"\n]/.test(str)) return '"' + str.replace(/"/g, '\\"') + '"';
  return str;
}
function buildMarkdown(session, messages) {
  const lines = [];
  lines.push('---');
  lines.push('session_id: ' + yamlEscape(session.session_id));
  lines.push('project: ' + yamlEscape(session.project));
  lines.push('date: ' + yamlEscape(session.date));
  let startIso = '';
  if (session.start) {
    try { startIso = new Date(session.start).toISOString().replace(/\.\d{3}Z$/, 'Z'); } catch(e) { startIso = String(session.start); }
  }
  lines.push('start: ' + yamlEscape(startIso));
  lines.push('duration_min: ' + (session.duration_min != null ? session.duration_min : 0));
  lines.push('model: ' + yamlEscape(session.primary_model));
  lines.push('messages: ' + (session.messages != null ? session.messages : 0));
  lines.push('cost_usd: ' + (typeof session.cost === 'number' ? session.cost.toFixed(4) : '0.0000'));
  if (session.source) lines.push('source: ' + yamlEscape(session.source));
  lines.push('---');
  lines.push('');

  let title = ((session.first_prompt || '').split('\n')[0] || '').trim();
  if (title.length > 80) title = title.slice(0, 80) + '\u2026';
  if (!title) title = 'Session ' + ((session.session_id || '').slice(0, 8));
  lines.push('# ' + title);
  lines.push('');

  messages.forEach(m => {
    if (m.role !== 'user' && m.role !== 'assistant') return;
    if (!(m.content || '').trim()) return;
    let ts = '';
    if (m.timestamp) {
      try { ts = new Date(m.timestamp).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'}); } catch(e) {}
    }
    if (m.role === 'user') {
      lines.push('## User' + (ts ? ' \u2014 ' + ts : ''));
    } else {
      const model = m.model ? ' (' + m.model + ')' : '';
      lines.push('## Assistant' + model + (ts ? ' \u2014 ' + ts : ''));
    }
    lines.push('');
    lines.push(m.content || '');
    lines.push('');
  });
  return lines.join('\n');
}
function triggerDownload(filename, content, mimeType) {
  const blob = content instanceof Blob ? content : new Blob([content], {type: mimeType || 'text/markdown;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
}
function loadJSZip() {
  if (window.JSZip) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';
    s.onload = resolve;
    s.onerror = () => reject(new Error('Failed to load JSZip'));
    document.head.appendChild(s);
  });
}

function getFilteredSessions() {
  let list = [...F.sessions];
  const proj = document.getElementById('filterProject').value;
  const src = document.getElementById('filterSource').value;
  const search = document.getElementById('filterSearch').value.toLowerCase();

  if (proj) list = list.filter(s => s.project === proj);
  if (src) list = list.filter(s => s.source === src);
  if (search) list = list.filter(s =>
    (s.first_prompt || '').toLowerCase().includes(search) ||
    s.project.toLowerCase().includes(search));

  if (sessionFilters) {
    const active = sessionFilters.getActiveFiltersList();
    for (const f of active) list = list.filter(f.predicate);
  }

  return list;
}

function renderSessions() {
  const sel = document.getElementById('filterProject');
  const currentVal = sel.value;
  // Clear and rebuild options from filtered sessions
  while (sel.options.length > 1) sel.remove(1);
  const projects = [...new Set(F.sessions.map(s => s.project))].sort();
  projects.forEach(p => {
    const o = document.createElement('option');
    o.value = p; o.textContent = anonMode ? anonName(p) : p;
    sel.appendChild(o);
  });
  // Restore selection if still valid
  if (projects.includes(currentVal)) sel.value = currentVal;

  // Source filter
  const srcSel = document.getElementById('filterSource');
  const currentSrc = srcSel.value;
  while (srcSel.options.length > 1) srcSel.remove(1);
  const sources = [...new Set(F.sessions.map(s => s.source).filter(Boolean))].sort();
  sources.forEach(src => {
    const o = document.createElement('option');
    o.value = src; o.textContent = anonMode ? anonSource(src) : src;
    srcSel.appendChild(o);
  });
  if (sources.includes(currentSrc)) srcSel.value = currentSrc;

  if (!sessionFilters) {
    const fm = document.getElementById('sessionFiltersMount');
    sessionFilters = mountSessionFilters(fm, {
      context: 'dashboard',
      getPool: () => F.sessions,
      onChange: () => {
        const next = getFilteredSessions();
        if (sessionTable) sessionTable.update(next);
        updateBulkBtnLabel();
      },
    });
  } else {
    sessionFilters.onPoolChanged();
  }

  // Mount table on first call, update on subsequent calls.
  const filtered = getFilteredSessions();
  if (!sessionTable) {
    const mount = document.getElementById('sessionTableMount');
    sessionTable = mountSessionTable(mount, filtered, {
      context: 'dashboard',
      locale: D.locale.locale_code,
      anonName: anonName,
      anonSource: anonSource,
      hideChatInAnon: true,
      showExportButtons: true,
      onChange: updateBulkBtnLabel
    });
  } else {
    sessionTable.update(filtered);
  }
  updateBulkBtnLabel();
}

function updateBulkBtnLabel() {
  const btn = document.getElementById('bulkDownloadBtn');
  if (!btn) return;
  const n = sessionTable ? sessionTable.getFiltered().length : getFilteredSessions().length;
  if (!btn.dataset.busy) {
    btn.textContent = '⬇ Download Sessions (' + n + ')';
    btn.disabled = (n === 0);
  }
}

async function bulkDownloadSessions() {
  const btn = document.getElementById('bulkDownloadBtn');
  const source = sessionTable ? sessionTable.getFiltered() : getFilteredSessions();
  const sessions = source.filter(s => s.has_chat !== false);
  if (sessions.length === 0) return;
  if (sessions.length > 100 && !confirm(sessions.length + ' Sessions als ZIP herunterladen? Das kann einen Moment dauern.')) return;

  btn.dataset.busy = '1';
  btn.disabled = true;

  let errors = 0;
  try {
    try { await loadJSZip(); }
    catch (e) {
      alert('ZIP-Bibliothek konnte nicht geladen werden (offline?).');
      return;
    }

    const zip = new JSZip();
    const usedNames = new Set();

    for (let i = 0; i < sessions.length; i++) {
      btn.textContent = 'Loading ' + (i + 1) + '/' + sessions.length + '…';
      try {
        const resp = await fetch('sessions/' + sessions[i].session_id + '.html');
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const text = await resp.text();
        const startMarker = '\nconst S = ';
        const endMarker = '};\nconst FLOW';
        const startIdx = text.indexOf(startMarker);
        if (startIdx === -1) throw new Error('Session JSON not found in HTML');
        const jsonStart = startIdx + startMarker.length;
        const endIdx = text.indexOf(endMarker, jsonStart);
        if (endIdx === -1) throw new Error('Session JSON end marker not found');
        const data = JSON.parse(text.slice(jsonStart, endIdx + 1));
        const md = buildMarkdown(data.session, data.messages);
        let name = mdFilename(data.session);
        if (usedNames.has(name)) {
          let n = 2;
          let candidate;
          do { candidate = name.replace(/\.md$/, '-' + n + '.md'); n++; } while (usedNames.has(candidate));
          name = candidate;
        }
        usedNames.add(name);
        zip.file(name, md);
      } catch (e) {
        errors++;
        console.warn('Session ' + sessions[i].session_id + ' failed:', e);
      }
    }

    if (usedNames.size > 0) {
      btn.textContent = 'Zipping…';
      const blob = await zip.generateAsync({type: 'blob'});
      const today = new Date().toISOString().slice(0, 10);
      triggerDownload('claude-sessions-' + today + '.zip', blob, 'application/zip');
    }
  } finally {
    delete btn.dataset.busy;
    updateBulkBtnLabel();
  }

  if (errors > 0) {
    alert(errors + ' sessions konnten nicht geladen werden — siehe Konsole.');
  }
}

// ── Tab 5: Plan & Billing ──────────────────────────────────────────────
let _planChartSavings = null, _planChartCostPerDay = null;
function renderPlan() {
  const plan = D.plan;
  if (!plan) return;
  const cb = plan.current_billing;

  // Currency toggle in tab meta
  const meta = document.getElementById('vcPlanMeta');
  if (meta && plan.currency_symbol) {
    meta.innerHTML = '';
    const wrap = document.createElement('span');
    wrap.style.cssText = 'display:inline-flex;gap:4px;align-items:center;';
    const mkBtn = (mode, label) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = label;
      const active = planCurrencyMode === mode;
      b.style.cssText = 'padding:2px 8px;border:1px solid var(--border);background:' + (active ? 'var(--accent)' : 'transparent') + ';color:' + (active ? '#fff' : 'inherit') + ';cursor:pointer;font:inherit;border-radius:0;';
      b.onclick = () => { planCurrencyMode = mode; renderPlan(); };
      return b;
    };
    wrap.appendChild(mkBtn('usd', 'USD'));
    wrap.appendChild(mkBtn('local', plan.currency_symbol));
    meta.appendChild(wrap);
  }

  // KPI cards
  const grid = document.getElementById('planKpi');
  grid.innerHTML = '';
  const planSubMain = fmtPlanMoney(planMoneyValue(cb, 'plan_cost')) + D.locale.plan.monthly_suffix;
  let planSubAlt = '';
  if (planCurrencyMode === 'local' && cb.plan_cost_usd != null) {
    planSubAlt = ' ($' + cb.plan_cost_usd.toFixed(2) + ')';
  } else if (planCurrencyMode === 'usd' && cb.plan_cost_local != null) {
    planSubAlt = ' (' + cb.plan_cost_local.toFixed(2) + ' ' + planCurrencySymbol() + ')';
  }
  const totalSav = planTotal('savings'), totalApiCost = planTotal('api_cost');
  const savePct = totalApiCost > 0 ? Math.round(totalSav / totalApiCost * 1000) / 10 : 0;
  const kpis = [
    {cls:'plan-type', label:D.locale.plan.current_plan, value:cb.plan, sub: planSubMain + planSubAlt, badge:(D.locale.plan.active || 'Active')},
    {cls:'paid', label:D.locale.plan.paid_so_far, value:fmtPlanMoney(planTotal('plan_cost')), sub:D.locale.plan.paid_so_far_sub},
    {cls:'api-cost', label:D.locale.plan.total_api_cost, value:fmtPlanMoney(totalApiCost), sub:D.locale.plan.total_api_sub},
    {cls:'savings', label:D.locale.plan.total_savings, value:fmtPlanMoney(totalSav), sub:D.locale.plan.total_savings_sub, chip:{text:'▲ '+savePct+'%', cls:'pos'}},
    {cls:'roi', label:D.locale.plan.roi_factor, value:plan.overall_roi + 'x', sub:D.locale.plan.roi_sub, chip:{text:plan.overall_roi+'×', cls:'accent'}},
  ];
  kpis.forEach(c => {
    const div = document.createElement('div');
    div.className = 'plan-card ' + c.cls;
    const top = document.createElement('div'); top.className = 'plan-card-top';
    const lbl = document.createElement('div'); lbl.className = 'label'; lbl.textContent = c.label;
    top.appendChild(lbl);
    if (c.badge) { const bd = document.createElement('span'); bd.className = 'badge-live'; bd.textContent = c.badge; top.appendChild(bd); }
    else if (c.chip) { const ch = document.createElement('span'); ch.className = 'plan-delta ' + c.chip.cls; ch.textContent = c.chip.text; top.appendChild(ch); }
    const val = document.createElement('div'); val.className = 'value'; val.textContent = c.value;
    const sub = document.createElement('div'); sub.className = 'sub'; sub.textContent = c.sub;
    div.appendChild(top); div.appendChild(val); div.appendChild(sub);
    grid.appendChild(div);
  });

  // Billing progress
  const bp = document.getElementById('billingProgress');
  bp.innerHTML = '';
  const pct = Math.min(100, Math.round(cb.days_elapsed / cb.days_total * 100));

  const h3 = document.createElement('h3');
  h3.textContent = D.locale.plan.billing_period + ' (' + cb.period_start + ' – ' + cb.period_end + ')';
  bp.appendChild(h3);

  // Progress reveals a fixed green→amber→red scale up to the current point in
  // the cycle. clip-path keeps the gradient sized to the full track, so the
  // boundary color reflects how far through the period we are (green early,
  // red late). The unrevealed right portion shows the bare track.
  const outer = document.createElement('div'); outer.className = 'progress-bar-outer';
  const fill = document.createElement('div'); fill.className = 'progress-bar-fill';
  fill.style.clipPath = 'inset(0 ' + (100 - pct) + '% 0 0)';
  const marker = document.createElement('div'); marker.className = 'progress-bar-marker';
  marker.style.left = pct + '%';
  const label = document.createElement('div'); label.className = 'progress-bar-label';
  label.style.left = Math.min(92, Math.max(8, pct)) + '%';
  label.textContent = pct + '%';
  outer.appendChild(fill); outer.appendChild(marker); outer.appendChild(label);
  bp.appendChild(outer);

  const stats = document.createElement('div'); stats.className = 'progress-stats';
  const statItems = [
    {label:D.locale.plan.day, val:cb.days_elapsed + ' / ' + cb.days_total},
    {label:D.locale.plan.api_cost_so_far, val:fmtPlanMoney(planMoneyValue(cb, 'api_cost'))},
    {label:D.locale.plan.projected, val:fmtPlanMoney(planMoneyValue(cb, 'projected_cost'))},
    {label:D.locale.plan.savings_so_far, val:fmtPlanMoney(planMoneyValue(cb, 'savings')), cls:'good'},
    {label:D.locale.plan.roi, val:cb.roi_factor + 'x', cls:'accent'},
    {label:D.locale.plan.sessions, val:String(cb.sessions)},
    {label:D.locale.plan.messages, val:fmt(cb.messages)},
    {label:D.locale.plan.avg_per_day, val:fmtPlanMoney(planMoneyValue(cb, 'cost_per_day'))},
  ];
  statItems.forEach(s => {
    const item = document.createElement('div'); item.className = 'stat-item' + (s.cls ? ' ' + s.cls : '');
    const lbl = document.createElement('span'); lbl.textContent = s.label;
    const val = document.createElement('span'); val.className = 'stat-val'; val.textContent = s.val;
    item.appendChild(lbl); item.appendChild(val);
    stats.appendChild(item);
  });
  bp.appendChild(stats);

  // Charts
  const periodLabels = plan.periods.map(p => p.plan + ' (' + p.start.slice(5) + ')');
  const unitLabel = planMoneyUnitLabel();
  const perDayLabel = planCurrencyMode === 'local'
    ? planCurrencySymbol() + ' / ' + (D.locale.plan.usd_per_day || '').replace(/^.*\//, '').trim()
    : D.locale.plan.usd_per_day;

  if (_planChartSavings) _planChartSavings.destroy();
  _planChartSavings = new Chart(document.getElementById('chartPlanSavings'), {
    type: 'bar',
    data: {
      labels: periodLabels,
      datasets: [
        {label: D.locale.plan.api_cost_label, data: plan.periods.map(p => planMoneyValue(p, 'api_cost') || 0), backgroundColor: _vcHexRgba(_vcLiveVar('--vc-pos', '#1f9d63'), 0.82), borderRadius: 4},
        {label: D.locale.plan.plan_cost_label, data: plan.periods.map(p => planMoneyValue(p, 'plan_cost') || 0), backgroundColor: vcRgba(0, 0.82), borderRadius: 4},
      ]
    },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: window.__vcFg2 || '#4d4a42' } },
        tooltip: { callbacks: { label: ctx => ctx.dataset.label + ': ' + fmtPlanMoney(ctx.raw) } } },
      scales: { x: scaleDefaults.x, y: { ...scaleDefaults.y, title: { display: true, text: unitLabel, color: window.__vcFg2 || '#4d4a42' } } } }
  });

  if (_planChartCostPerDay) _planChartCostPerDay.destroy();
  _planChartCostPerDay = new Chart(document.getElementById('chartCostPerDay'), {
    type: 'bar',
    data: {
      labels: periodLabels,
      datasets: [{ label: D.locale.plan.api_cost_per_day_label, data: plan.periods.map(p => planMoneyValue(p, 'cost_per_day') || 0),
        backgroundColor: plan.periods.map(p => p.plan === 'Max' ? vcRgba(2, 0.7) : vcRgba(1, 0.7)),
        borderRadius: 0 }]
    },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false },
        tooltip: { callbacks: { label: ctx => fmtPlanMoney(ctx.raw) + ' / ' + (D.locale.plan.day || 'day') } } },
      scales: { x: scaleDefaults.x, y: { ...scaleDefaults.y, title: { display: true, text: perDayLabel, color: window.__vcFg2 || '#4d4a42' } } } }
  });

  // Period table
  const tbody = document.getElementById('planTableBody');
  tbody.innerHTML = '';
  plan.periods.forEach(p => {
    const tr = document.createElement('tr');
    const apiVal = planMoneyValue(p, 'api_cost');
    const planVal = planMoneyValue(p, 'plan_cost');
    const savingsVal = planMoneyValue(p, 'savings');
    // In-progress cycle: show the real period end + elapsed/total days + a
    // muted projected ROI alongside the actual (so-far) ROI.
    const cur = p.is_current;
    const periodEnd = (cur && p.period_end_full) ? p.period_end_full : p.end;
    const daysVal = (cur && p.days_total_full)
      ? (p.days_elapsed + ' / ' + p.days_total_full + ' (' + p.days_active + D.locale.plan.active_suffix + ')')
      : (p.total_days + ' (' + p.days_active + D.locale.plan.active_suffix + ')');
    const cells = [
      {val: p.start + ' \u2013 ' + periodEnd, cls:'primary', highlight:false, label:'Period',
       badge: cur ? (D.locale.plan.running || 'running') : null},
      {val: p.plan, cls:'', highlight:false, label:'Plan'},
      {val: daysVal, cls:'num', highlight:false, label:'Days'},
      {val: fmtPlanMoney(apiVal), cls:'num', label:'API Cost'},
      {val: fmtPlanMoney(planVal), cls:'num', label:'Plan Cost'},
      {val: fmtPlanMoney(savingsVal), cls:'num', color:'var(--vc-pos)', label:'Savings'},
      {val: p.roi_factor + 'x', cls:'num', color:'var(--vc-accent)', label:'ROI',
       sub: (cur && p.projected_roi != null) ? ('\u2192 ' + p.projected_roi + 'x') : null,
       subTitle: D.locale.plan.projected},
      {val: String(p.sessions), cls:'num', label:'Sessions'},
      {val: fmt(p.messages), cls:'num', label:'Messages'},
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      td.setAttribute('data-label', c.label);
      td.textContent = c.val;
      if (c.color) { td.style.color = c.color; td.style.fontWeight = '600'; }
      if (c.badge) {
        td.appendChild(document.createTextNode(' '));
        const b = document.createElement('span');
        b.className = 'period-running-badge';
        b.textContent = c.badge;
        td.appendChild(b);
      }
      if (c.sub) {
        td.appendChild(document.createTextNode(' '));
        const s = document.createElement('span');
        s.className = 'period-roi-proj';
        s.textContent = c.sub;
        if (c.subTitle) s.title = c.subTitle;
        td.appendChild(s);
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  // Total row
  const trTotal = document.createElement('tr');
  trTotal.setAttribute('data-nosort', '1');
  trTotal.style.fontWeight = '700';
  trTotal.style.borderTop = '2px solid var(--border)';
  const totalCells = [
    {val: D.locale.plan.total, cls:'primary', label:'Period'},
    {val: '', cls:'', label:'Plan'},
    {val: '', cls:'num', label:'Days'},
    {val: fmtPlanMoney(planTotal('api_cost')), cls:'num', label:'API Cost'},
    {val: fmtPlanMoney(planTotal('plan_cost')), cls:'num', label:'Plan Cost'},
    {val: fmtPlanMoney(planTotal('savings')), cls:'num', label:'Savings'},
    {val: plan.overall_roi + 'x', cls:'num', label:'ROI'},
    {val: '', cls:'num', label:'Sessions'},
    {val: '', cls:'num', label:'Messages'},
  ];
  totalCells.forEach(c => {
    const td = document.createElement('td');
    if (c.cls) td.className = c.cls;
    td.setAttribute('data-label', c.label);
    td.textContent = c.val;
    trTotal.appendChild(td);
  });
  tbody.appendChild(trTotal);
}

// ── Tab: Limits (Tasks 3+4) ────────────────────────────────────────
function renderLimits() {
  renderRecommendationCard();
  renderLimitsEventTimeline();
  renderPlanRecommendation();
}

// The recommendation headline, promoted to the top of the Limits section.
function renderRecommendationCard() {
  const el = document.getElementById('limitsRecCard');
  if (!el) return;
  const pr = D.plan_recommendation || null;
  if (!pr) { el.innerHTML = ''; return; }

  const L = (D.locale && D.locale.planRec) || {};
  const T = {
    rec:      L.rec      || 'Recommendation',
    current:  L.current  || 'Current tier',
    none:     L.none     || 'None — no tier holds without hits',
    optimal:  L.optimal  || 'optimal — no change needed',
    recBasis: L.recBasis || 'Basis: last {n} cycles ({w} 5h-windows) - tolerance: ≤{q}% of 5h-windows, ≤{a} weeks over cap',
  };

  const cur = pr.current_tier || '—';
  const rec = pr.recommended_tier;
  const basis = pr.rec_basis || null;
  const basisLine = basis
    ? T.recBasis.replace('{n}', basis.recent_cycles)
                .replace('{w}', basis.recent_window_total)
                .replace('{q}', Math.round((basis.hit_quota || 0) * 100))
                .replace('{a}', basis.weekly_allowance)
    : '';

  let mod = '', value = '', sub = '';
  if (!rec) {
    mod = 'rec-card--none';
    value = T.none;
    sub = T.current + ': ' + cur;
  } else if (rec === cur) {
    value = cur;
    sub = T.optimal + (basisLine ? ' · ' + basisLine : '');
  } else {
    value = rec;
    sub = T.current + ': ' + cur + (basisLine ? ' · ' + basisLine : '');
  }

  el.innerHTML =
    '<div class="rec-card ' + mod + '">' +
      '<span class="vc-tag acc">beta</span>' +
      '<div class="rec-card-label">' + T.rec + '</div>' +
      '<div class="rec-card-value">' + value + '</div>' +
      '<div class="rec-card-sub">' + sub + '</div>' +
    '</div>';
}

function renderLimitsEventTimeline() {
  const el = document.getElementById('limitsEventTimeline');
  if (!el) return;
  const L = (D.locale && D.locale.limits) || {};
  const T = {
    title:     L.eventsTitle || 'Limit Events',
    events:    L.events      || 'events',
    explicit:  L.explicit    || 'Explicit rate-limit error',
    heuristic: L.heuristic   || '5h-fingerprint (heuristic)',
    click:     L.click       || 'Click an event to open the session (when available)',
    noCycles:  L.noCycles    || 'No billing cycles found.',
  };
  const cycles = (D.plan && D.plan.periods) || [];
  if (!cycles.length) {
    el.innerHTML = '<p class="vc-empty">' + T.noCycles + '</p>';
    return;
  }

  const rows = cycles.map(cy => {
    const events = cy.limit_events || [];
    const cyStart = new Date(cy.start);
    const cyEnd = new Date(cy.end);
    const cyDurMs = Math.max(1, cyEnd - cyStart);
    const markers = events.map(ev => {
      const ts = new Date(ev.timestamp || ev.gap_end || cy.start);
      const pct = Math.max(0, Math.min(100, 100 * (ts - cyStart) / cyDurMs));
      const cls = ev.type === 'explicit'
        ? 'evt evt-explicit'
        : (ev.confidence === 'high' ? 'evt evt-heuristic-high' : 'evt evt-heuristic-med');
      const tooltip = (ev.type === 'explicit' ? T.explicit : T.heuristic) +
                      ' · ' + (ev.subtype || '') +
                      ' · ' + (ev.timestamp || ev.gap_end || '') +
                      (ev.merged_count > 1 ? ' · ×' + ev.merged_count : '');
      const titleAttr = tooltip.replace(/"/g, '&quot;');
      const style = 'left:' + pct.toFixed(1) + '%';
      if (ev.session_id) {
        // Anchor to the in-chat rate-limit marker (only meaningful for
        // explicit events). Slug form must match evtId() in session_detail.js.
        const frag = (ev.type === 'explicit' && ev.timestamp)
          ? '#evt-' + String(ev.timestamp).replace(/[^a-zA-Z0-9]/g, '-')
          : '';
        return '<a class="' + cls + '" style="' + style + '" title="' + titleAttr +
               '" href="sessions/' + ev.session_id + '.html' + frag + '"></a>';
      }
      // No session linkage — render a non-interactive marker (span avoids page-jump scroll-to-top).
      return '<span class="' + cls + '" style="' + style + '" title="' + titleAttr + '"></span>';
    }).join('');
    return (
      '<div class="lim-row">' +
        '<div class="lim-lbl">' + (cy.plan || '') + ' · ' + (cy.start || '').slice(0, 7) + '</div>' +
        '<div class="lim-bar">' + markers + '</div>' +
        '<div class="lim-cnt">' + events.length + ' ' + T.events + '</div>' +
      '</div>'
    );
  }).join('');

  el.innerHTML =
    '<h3>' + T.title + '</h3>' +
    '<div class="lim-rows">' + rows + '</div>' +
    '<div class="lim-legend">' +
      '<span class="evt evt-explicit"></span> ' + T.explicit + ' &nbsp; ' +
      '<span class="evt evt-heuristic-high"></span> ' + T.heuristic +
    '</div>' +
    '<div class="lim-tip">' + T.click + '</div>';
}

function renderPlanRecommendation() {
  const el = document.getElementById('limitsPlanRec');
  if (!el) return;
  const pr = D.plan_recommendation || null;
  if (!pr || !pr.cycles || !pr.cycles.length) {
    el.innerHTML = '';
    return;
  }

  const L = (D.locale && D.locale.planRec) || {};
  const T = {
    title:        L.title        || 'Plan Recommendation',
    cycle:        L.cycle        || 'Cycle',
    windows:      L.windows      || '5h-windows',
    weeks:        L.weeks        || 'Weeks',
    hitsTitle:    L.hitsTitle    || 'Limit Hits by Tier',
    fiveHHits:    L.fiveHHits    || '5h-limit hits',
    weeklyHits:   L.weeklyHits   || 'Weekly-limit hits',
    current:      L.current      || 'Current tier',
    rec:          L.rec          || 'Recommendation',
    none:         L.none         || 'None — no tier holds without hits',
    totals:       L.totals       || 'Total hits across all cycles',
    recTag:       L.recTag       || 'recommended',
    curTag:       L.curTag       || 'current',
    cal:          L.cal          || 'Calibration',
    calEmpirical: L.calEmpirical || 'empirical',
    calDefault:   L.calDefault   || 'default fallback',
    calOverride:  L.calOverride  || 'config override',
    calDerived:   L.calDerived   || 'derived from 5h cap',
    capPerWindow: L.capPerWindow || 'per 5h-window',
    capPerWeek:   L.capPerWeek   || 'per week',
    anchors:      L.anchors      || 'anchor windows',
    recBasis:     L.recBasis     || 'Basis: last {n} cycles ({w} 5h-windows) - tolerance: ≤{q}% of 5h-windows, ≤{a} weeks over cap',
    calFloor:     L.calFloor     || 'floored at the most expensive limit-free window',
    disclaimer:   L.disclaimer   || "Hit counts use empirical caps derived from windows that contained a limit event, floored at the most expensive limit-free window (USD is a rough proxy for Anthropic's limit units). Duplicate events from parallel sessions are merged. Anthropic does not publish exact token limits - the 1:5:20 tier ratio is approximate. Weekly cap is estimated as 7 x the 5h cap until a dedicated weekly-limit detector is added.",
  };

  const TIERS = ['Pro', 'Max 5x', 'Max 20x'];
  const rec = pr.recommended_tier;
  const cur = pr.current_tier;
  // Severity bucket for the heatmap tint: 0 / 1-2 / 3-9 / 10+.
  const sevClass = (n) => n <= 0 ? 'h0' : (n <= 2 ? 'h1' : (n <= 9 ? 'h2' : 'h3'));

  // Arrow lives in the gutter (index gi, between TIERS[gi] and TIERS[gi+1])
  // immediately adjacent to the active cell, pointing toward the recommended
  // column. switch_arrow ('down'|'up'|null) is computed server-side.
  const gutterArrow = (gi, active, arrow) => {
    if (!arrow) return '';
    const ai = TIERS.indexOf(active);
    if (arrow === 'down' && gi === ai - 1) return '<span class="ph-arrow down">←</span>';
    if (arrow === 'up'   && gi === ai)     return '<span class="ph-arrow up">→</span>';
    return '';
  };

  const renderHeat = (titleText, getHits, totals) => {
    let head = '<tr><th class="ph-cyc">' + T.cycle + '</th>';
    TIERS.forEach((t, i) => {
      const tags = [];
      if (t === rec) tags.push('<span class="ph-tag rec">' + T.recTag + '</span>');
      if (t === cur) tags.push('<span class="ph-tag cur">' + T.curTag + '</span>');
      head += '<th class="ph-th' + (t === rec ? ' rec' : '') + '">' + t +
              (tags.length ? '<br>' + tags.join(' ') : '') + '</th>';
      if (i < TIERS.length - 1) head += '<th class="ph-gut"></th>';
    });
    head += '</tr>';

    const body = pr.cycles.map(c => {
      const u = getHits(c) || {};
      const active = c.active_tier;
      const arrow = c.switch_arrow;
      let row = '<tr><td class="ph-cyc">' + (c.label || c.cycle_start) + '</td>';
      TIERS.forEach((t, i) => {
        const n = u[t] || 0;
        let cls = 'ph-cell ' + sevClass(n);
        if (t === rec) cls += ' rec';
        if (t === active) cls += ' active';
        row += '<td class="' + cls + '">' + (n > 0 ? n : '·') + '</td>';
        if (i < TIERS.length - 1) row += '<td class="ph-gut">' + gutterArrow(i, active, arrow) + '</td>';
      });
      return row + '</tr>';
    }).join('');

    let tot = '<tr class="ph-tot"><td class="ph-cyc">' + T.totals + '</td>';
    TIERS.forEach((t, i) => {
      const n = totals[t] || 0;
      tot += '<td class="ph-cell ' + sevClass(n) + '">' + n + '</td>';
      if (i < TIERS.length - 1) tot += '<td class="ph-gut"></td>';
    });
    tot += '</tr>';

    return '<div class="ph-block"><div class="ph-title">' + titleText + '</div>' +
           '<table class="ph-table"><thead>' + head + '</thead><tbody>' + body + tot + '</tbody></table></div>';
  };

  const cal5 = pr.calibration_5h || {};
  const calSrc5 = cal5.source === 'empirical' ? T.calEmpirical
    : cal5.source === 'config_override' ? T.calOverride
    : T.calDefault;
  const caps5 = cal5.caps_per_window || {};
  const cal5Line = T.cal + ' (5h): ' + calSrc5 + ' — Pro $' + (caps5.Pro || 0).toFixed(2) +
    ' / Max 5x $' + (caps5['Max 5x'] || 0).toFixed(2) +
    ' / Max 20x $' + (caps5['Max 20x'] || 0).toFixed(2) + ' ' + T.capPerWindow +
    ' (n=' + (cal5.anchor_window_count || 0) + ' ' + T.anchors + ')' +
    (cal5.floor_applied ? ' · ' + T.calFloor : '');

  const calW = pr.calibration_weekly || {};
  const capsW = calW.caps_per_week || {};
  const calWLine = T.cal + ' (' + T.weeks + '): ' + T.calDerived +
    ' × ' + (calW.ratio_vs_5h || 7) +
    ' — Pro $' + (capsW.Pro || 0).toFixed(0) +
    ' / Max 5x $' + (capsW['Max 5x'] || 0).toFixed(0) +
    ' / Max 20x $' + (capsW['Max 20x'] || 0).toFixed(0) + ' ' + T.capPerWeek;

  el.innerHTML =
    '<h3>' + T.hitsTitle + '</h3>' +
    '<div class="ph-tables">' +
      renderHeat(T.fiveHHits,  (c) => c.tier_5h_hits,     pr.tier_total_5h_hits || {}) +
      renderHeat(T.weeklyHits, (c) => c.tier_weekly_hits, pr.tier_total_weekly_hits || {}) +
    '</div>' +
    '<div class="plan-rec-fineprint">' +
      '<div class="plan-rec-cal">' + cal5Line + '</div>' +
      '<div class="plan-rec-cal">' + calWLine + '</div>' +
    '</div>' +
    '<div class="plan-rec-disclaimer">⚠ ' + T.disclaimer + '</div>';
}

// ── Tab 6: Insights ───────────────────────────────────────────────────
function renderInsights() {
  const ins = D.insights;
  if (!ins) return;

  // Tool usage chart
  renderToolUsageChart();
  renderToolTokenChart();
  renderWriteCategoriesChart();

  // Storage chart — show the top entries by size and fold the long tail into
  // "Other" so the slice count stays within the palette (no repeated colors /
  // indistinguishable slices in the legend).
  const storage = ins.storage || {};
  const allStorage = (storage.items || []).filter(s => s.size_mb >= 0.1)
    .slice().sort((a, b) => b.size_mb - a.size_mb);
  const TOP_STORAGE = 8;
  let storageItems = allStorage;
  if (allStorage.length > TOP_STORAGE + 1) {
    const otherSum = allStorage.slice(TOP_STORAGE).reduce((s, x) => s + x.size_mb, 0);
    storageItems = allStorage.slice(0, TOP_STORAGE)
      .concat([{ name: 'Other (' + (allStorage.length - TOP_STORAGE) + ')', size_mb: +otherSum.toFixed(1) }]);
  }
  if (storageItems.length > 0) {
    new Chart(document.getElementById('chartStorage'), {
      type: 'doughnut',
      data: { labels: storageItems.map(s => s.name),
        datasets: [{ data: storageItems.map(s => s.size_mb),
          backgroundColor: storageItems.map((_, i) => _VC_CAT[i % _VC_CAT.length]), borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'right', labels: { color: window.__vcFg2 || '#4d4a42', padding: 8, font: { size: 11 } } },
          tooltip: { callbacks: { label: ctx => ctx.label + ': ' + ctx.raw + ' MB' } } } }
    });
  }

  // Plugin table
  const plugins = ins.plugins || {};
  const installed = plugins.installed || [];
  const enabled = plugins.settings?.enabled_plugins || {};
  const mktStats = plugins.marketplace_stats || {};
  const tbody = document.getElementById('pluginTableBody');
  installed.forEach(p => {
    const tr = document.createElement('tr');
    const isEnabled = enabled[p.name] !== false;
    const globalInstalls = mktStats[p.name] || 0;
    const cells = [
      {val: p.short_name, cls: 'primary', label: 'Plugin'},
      {val: isEnabled ? D.locale.insights.active : D.locale.insights.inactive, cls: '', badge: isEnabled ? 'active' : 'inactive', label: 'Status'},
      {val: p.version, cls: '', label: 'Version'},
      {val: globalInstalls > 0 ? fmt(globalInstalls) : '-', cls: 'num', label: 'Global Installs'},
      {val: p.installed_at ? new Date(p.installed_at).toLocaleDateString(D.locale.locale_code) : '-', cls: '', label: 'Installed At'},
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      td.setAttribute('data-label', c.label);
      if (c.badge) {
        const span = document.createElement('span');
        span.className = 'plugin-status ' + c.badge;
        span.textContent = c.val;
        td.appendChild(span);
      } else {
        td.textContent = c.val;
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  // Config info
  // Storage rows intentionally omitted here — the chartStorage doughnut above is
  // the single source for the storage breakdown, so we don't duplicate it.
  const configDiv = document.getElementById('configInfo');
  const settings = plugins.settings || {};
  const configItems = [
    {label: D.locale.insights.permission_mode, value: settings.permission_mode || '-'},
    {label: D.locale.insights.auto_updates, value: settings.auto_updates || '-'},
    {label: D.locale.insights.plugins_installed, value: String(installed.length)},
    {label: D.locale.insights.plugins_active, value: String(Object.values(enabled).filter(v => v).length)},
  ];
  const grid = document.createElement('div'); grid.className = 'config-grid';
  configItems.forEach(c => {
    const item = document.createElement('div'); item.className = 'config-item';
    const lbl = document.createElement('div'); lbl.className = 'ci-label'; lbl.textContent = c.label;
    const val = document.createElement('div'); val.className = 'ci-value'; val.textContent = c.value;
    item.appendChild(lbl); item.appendChild(val);
    grid.appendChild(item);
  });
  if (configDiv) configDiv.appendChild(grid);   // Environment section was removed; guard the (now absent) target

  // Plans table
  const plans = ins.plans || [];
  const plansTbody = document.getElementById('plansTableBody');
  plans.forEach(p => {
    const tr = document.createElement('tr');
    const cells = [
      {val: p.title, cls: 'primary', anon: true, label: 'Title'},
      {val: new Date(p.created).toLocaleDateString(D.locale.locale_code), cls: '', label: 'Created'},
      {val: String(p.lines), cls: 'num', label: 'Lines'},
      {val: String(p.size_kb), cls: 'num', label: 'KB'},
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      td.setAttribute('data-label', c.label);
      if (c.anon) {
        const span = document.createElement('span');
        span.className = 'anon-blur';
        span.textContent = c.val;
        td.appendChild(span);
      } else {
        td.textContent = c.val;
      }
      tr.appendChild(td);
    });
    plansTbody.appendChild(tr);
  });

  // Misc stats (file history + todos)
  const fh = ins.file_history || {};
  const todos = ins.todos || {};
  const miscDiv = document.getElementById('miscStats');
  const miscGrid = document.createElement('div'); miscGrid.className = 'misc-stat-grid';
  const miscItems = [
    {val: String(fh.total_files || 0), label: D.locale.insights.file_snapshots},
    {val: String(fh.total_sessions || 0), label: D.locale.insights.sessions_with_snapshots},
    {val: (fh.total_size_mb || 0) + ' MB', label: D.locale.insights.snapshot_size},
    {val: String(todos.total || 0), label: D.locale.insights.todos_total},
    {val: String(todos.completed || 0), label: D.locale.insights.todos_completed},
    {val: todos.total > 0 ? Math.round(todos.completed / todos.total * 100) + '%' : '-', label: D.locale.insights.completion_rate},
  ];
  miscItems.forEach(m => {
    const div = document.createElement('div'); div.className = 'misc-stat';
    const val = document.createElement('div'); val.className = 'ms-val'; val.textContent = m.val;
    const lbl = document.createElement('div'); lbl.className = 'ms-label'; lbl.textContent = m.label;
    div.appendChild(val); div.appendChild(lbl);
    miscGrid.appendChild(div);
  });
  miscDiv.appendChild(miscGrid);

  // Skills
  const skillsEl = document.getElementById('skillsList');
  if (skillsEl && D.skill_summary && D.skill_summary.length > 0) {
    skillsEl.innerHTML = D.skill_summary.map(s =>
      '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--vc-grid-2,var(--border))">' +
      '<span class="anon-blur" style="font-size:13px;color:var(--vc-fg,var(--text))">' + escHtml(s.name) + '</span>' +
      '<span class="vc-tag acc">' + s.count + 'x</span>' +
      '</div>'
    ).join('');
  } else if (skillsEl) {
    skillsEl.innerHTML = '<p style="color:var(--text2);font-size:13px;padding:12px">No skills used yet</p>';
  }

  // Hooks
  const hooksEl = document.getElementById('hooksList');
  if (hooksEl && D.hook_summary && D.hook_summary.length > 0) {
    hooksEl.innerHTML = D.hook_summary.map(h => {
      const parts = h.name.split(':');
      const event = parts[0] || '';
      const name = parts.slice(1).join(':') || h.name;
      return '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--vc-grid-2,var(--border))">' +
        '<div><span class="vc-tag" style="font-size:10px;margin-right:6px">' + escHtml(event) + '</span><span class="anon-blur" style="font-size:13px;color:var(--vc-fg,var(--text))">' + escHtml(name) + '</span></div>' +
        '<span class="tool-tag">' + h.count + 'x</span>' +
        '</div>';
    }).join('');
  } else if (hooksEl) {
    hooksEl.innerHTML = '<p style="color:var(--text2);font-size:13px;padding:12px">No hooks fired yet</p>';
  }

  // System info
  const envInfo = D.insights?.telemetry?.env_info || {};
  const sysEl = document.getElementById('systemInfo');
  if (sysEl) {
    sysEl.innerHTML =
      '<div class="sidebar-row"><span class="label">Platform</span><span class="val">'+(envInfo.platform||'\u2014')+'</span></div>' +
      '<div class="sidebar-row"><span class="label">Node</span><span class="val">'+(envInfo.node_version||'\u2014')+'</span></div>' +
      '<div class="sidebar-row"><span class="label">Claude Code</span><span class="val">'+(envInfo.claude_version||'\u2014')+'</span></div>' +
      '<div class="sidebar-row"><span class="label">Terminal</span><span class="val">'+(envInfo.terminal||'\u2014')+'</span></div>' +
      '<div class="sidebar-row"><span class="label">Arch</span><span class="val">'+(envInfo.arch||'\u2014')+'</span></div>';
  }

  // Git ops
  const gs = D.git_summary || {};
  const gitEl = document.getElementById('gitOpsInfo');
  if (gitEl) {
    gitEl.innerHTML =
      '<div class="sidebar-row"><span class="label">__L_insights_commits__</span><span class="val" style="color:var(--green)">'+(gs.commits||0)+'</span></div>' +
      '<div class="sidebar-row"><span class="label">__L_insights_pushes__</span><span class="val" style="color:var(--blue)">'+(gs.pushes||0)+'</span></div>' +
      '<div class="sidebar-row"><span class="label">__L_insights_pull_requests__</span><span class="val" style="color:var(--purple)">'+(gs.prs||0)+'</span></div>';
  }

}

// ── Tab 7: Agents ──────────────────────────────────────────────────────

function renderAgentsTab() {
  const as = F.agent_summary || D.agent_summary || {};
  const es = F.error_summary || D.error_summary || {};

  // Subagent types donut
  const atd = as.type_distribution || [];
  if (agentTypesChartInstance) agentTypesChartInstance.destroy();
  if (atd.length > 0) {
    agentTypesChartInstance = new Chart(document.getElementById('agentTypesChart'), {
      type: 'doughnut',
      data: {
        labels: atd.map(d => d.type),
        datasets: [{ data: atd.map(d => d.count), backgroundColor: atd.map((_, i) => _VC_CAT[i % _VC_CAT.length]) }]
      },
      options: { responsive:true, maintainAspectRatio:false, plugins:{ legend:{ position:'right', labels:{color:window.__vcFg2||'#4d4a42',font:{size:11}} } } }
    });
  }

  // Top descriptions bar
  const tds = as.top_descriptions || [];
  if (agentDescsChartInstance) agentDescsChartInstance.destroy();
  if (tds.length > 0) {
    agentDescsChartInstance = new Chart(document.getElementById('agentDescsChart'), {
      type: 'bar',
      data: {
        labels: tds.map(d => d.desc.length > 30 ? d.desc.slice(0,30)+'...' : d.desc),
        datasets: [{ data: tds.map(d => d.count), backgroundColor: vcRgba(0, 0.7), borderRadius:4 }]
      },
      options: { indexAxis:'y', responsive:true, plugins:{legend:{display:false}}, scales:{ x:{ticks:{color:window.__vcFg3||'#918a7a'}}, y:{ticks:{color:window.__vcFg3||'#918a7a',font:{size:10}}} } }
    });
  }

  // KPI cards
  const kpiEl = document.getElementById('agentKpis');
  kpiEl.innerHTML = '';
  const agentKpis = [
    {val: as.total_dispatches || 0, color:'var(--purple)', label:'__L_agents_dispatches__'},
    {val: (F.insights?.tasks?.total || D.insights?.tasks?.total || 0), color:'var(--cyan)', label:'__L_agents_total_tasks__'},
    {val: (es.error_rate || 0) + '%', color:'var(--red)', label:'__L_agents_error_rate__'},
  ];
  agentKpis.forEach(k => {
    const div = document.createElement('div');
    div.className = 'kpi-card';
    div.innerHTML = '<div class="label">'+k.label+'</div><div class="value" style="color:'+k.color+'">'+k.val+'</div>';
    kpiEl.appendChild(div);
  });

  // Task overview (range-filtered via F.insights, falls back to all-time)
  const taskEl = document.getElementById('taskOverview');
  const tasks = F.insights?.tasks || D.insights?.tasks || {};
  // The canvas below is recreated via innerHTML on every render; destroy the
  // previous Chart instance so it does not accumulate in Chart.instances.
  if (taskDonutChartInstance) { taskDonutChartInstance.destroy(); taskDonutChartInstance = null; }
  if (tasks.total > 0) {
    const pct = Math.round((tasks.completed / tasks.total) * 100);
    taskEl.innerHTML =
      '<div style="display:flex;gap:16px;align-items:center;margin-bottom:12px">' +
        '<div style="width:80px;height:80px;position:relative"><canvas id="taskDonut"></canvas></div>' +
        '<div><div style="font-size:24px;font-weight:700">'+pct+'%</div><div style="color:var(--text2);font-size:12px">__L_agents_task_completion__</div></div>' +
      '</div>' +
      '<div style="display:flex;gap:8px;flex-wrap:wrap">' +
        '<span class="tag" style="background:rgba(34,197,94,0.15);color:var(--green)">\u2713 '+tasks.completed+' completed</span>' +
        '<span class="tag" style="background:rgba(99,102,241,0.15);color:var(--accent2)">\u25B6 '+(tasks.in_progress||0)+' in progress</span>' +
        '<span class="tag" style="background:rgba(148,163,184,0.15);color:var(--text2)">\u25CB '+(tasks.pending||0)+' pending</span>' +
      '</div>';
    const posCol = _vcLiveVar('--vc-pos', '#1f9d63');
    const mutedCol = _vcLiveVar('--vc-fg-3', '#918a7a');
    taskDonutChartInstance = new Chart(document.getElementById('taskDonut'), {
      type: 'doughnut',
      data: { labels:['Completed','Pending','In Progress'], datasets:[{data:[tasks.completed,tasks.pending||0,tasks.in_progress||0], backgroundColor:[posCol, mutedCol, vcColor(0)]}] },
      options: { cutout:'70%', responsive:true, plugins:{legend:{display:false}} }
    });
  } else {
    taskEl.innerHTML = '<div style="color:var(--text2)">No tasks found</div>';
  }

  // Error overview
  const errEl = document.getElementById('errorOverview');
  const catLabels = {'rejected':'Rejected','file_not_found':'File Not Found','edit_not_unique':'Edit Not Unique','edit_no_match':'Edit No Match','stale_read':'Stale Read','permission_denied':'Permission Denied','timeout':'Timeout','command_not_found':'Cmd Not Found','exit_code':'Exit Code Error','syntax_error':'Syntax Error','import_error':'Import Error','hook_error':'Hook Error','edit_failed':'Edit Failed','rate_limit':'Rate Limit','server_overload':'Server Overload','auth':'Auth','server_error':'Server Error','connection':'Connection','invalid_request':'Invalid Request','content_filter':'Content Filter','other':'Other'};
  const srcLabels = {'backend':'Backend','tool':'Tool','hook':'Hook','rejected':'Rejected','user':'User'};
  const srcColors = {'backend':_VC_CAT[5],'tool':_vcLiveVar('--vc-neg','#d24b3e'),'hook':_VC_CAT[2],'rejected':_VC_CAT[0],'user':_vcLiveVar('--vc-fg-3','#918a7a')};
  const bySrc = es.by_source || [];
  const srcLine = bySrc.length ? '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px">' + bySrc.map(s =>
      '<span style="font-size:12px"><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:'+(srcColors[s.source]||'#999')+';margin-right:4px"></span>'+(srcLabels[s.source]||s.source)+' <b>'+s.count+'</b></span>'
    ).join('') + '</div>' : '';
  const crNote = (es.total_cancelled||0) ? '<div style="font-size:11px;color:var(--text2);margin-bottom:8px">'+(es.total_cancelled||0)+' cancelled <span style="opacity:.7">(not counted as errors)</span></div>' : '';
  const topCats = (es.by_category || []).slice(0, 5);
  errEl.innerHTML =
    '<div style="margin-bottom:8px"><span style="font-size:20px;font-weight:700;color:var(--red)">'+(es.total_errors||0)+'</span> errors / <span style="font-weight:600">'+(es.total_tool_calls||0)+'</span> tool calls</div>' +
    '<div style="font-size:12px;color:var(--text2);margin-bottom:8px">__L_agents_error_rate__: '+(es.error_rate||0)+'%</div>' +
    srcLine + crNote +
    '<div style="margin-top:12px">' + topCats.map(c =>
      '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">' +
        '<span style="font-size:12px">'+(catLabels[c.category]||c.category)+'</span>' +
        '<span style="font-size:12px;font-weight:600;color:var(--red)">'+c.count+'</span></div>'
    ).join('') + '</div>';

  // Error by category doughnut
  const ebc = es.by_category || [];
  if (errorByCatChartInstance) errorByCatChartInstance.destroy();
  if (ebc.length > 0) {
    // Error categories: lead with the negative/error color, then cycle the
    // earth-tone categorical palette for the remaining slices.
    const errColors = ebc.map((_, i) => i === 0 ? _vcLiveVar('--vc-neg', '#d24b3e') : _VC_CAT[(i - 1) % _VC_CAT.length]);
    errorByCatChartInstance = new Chart(document.getElementById('errorByCategoryChart'), {
      type: 'doughnut',
      data: {
        labels: ebc.map(e => catLabels[e.category] || e.category),
        datasets: [{ data: ebc.map(e => e.count), backgroundColor: errColors }]
      },
      options: { responsive:true, maintainAspectRatio:false, plugins:{ legend:{ position:'right', labels:{color:window.__vcFg2||'#4d4a42',font:{size:11}} } } }
    });
  }

  // Error by tool bar chart
  const ebt = (es.by_tool || []).slice(0, 10);
  if (errorByToolChartInstance) errorByToolChartInstance.destroy();
  if (ebt.length > 0) {
    errorByToolChartInstance = new Chart(document.getElementById('errorByToolChart'), {
      type: 'bar',
      data: {
        labels: ebt.map(e => e.tool),
        datasets: [{ data: ebt.map(e => e.count), backgroundColor: _vcHexRgba(_vcLiveVar('--vc-neg', '#d24b3e'), 0.7), borderRadius:4 }]
      },
      options: { indexAxis:'y', responsive:true, plugins:{legend:{display:false}}, scales:{ x:{ticks:{color:window.__vcFg3||'#918a7a'}}, y:{ticks:{color:window.__vcFg3||'#918a7a',font:{size:11}}} } }
    });
  }

  // Error rate over time. Lives here (not renderInsights) so it re-renders on
  // every filter change like the other charts in this errors subsection.
  // Denominator: real tool invocations (sum of per-tool counters), matching
  // the error_rate/total_tool_calls semantics.
  const dailyErrors = {};
  F.sessions.forEach(s => {
    if (!s.date) return;
    if (!dailyErrors[s.date]) dailyErrors[s.date] = {errors:0, calls:0};
    dailyErrors[s.date].errors += s.error_count || 0;
    dailyErrors[s.date].calls += Object.values(s.tools || {}).reduce((a, b) => a + (b || 0), 0);
  });
  const errDates = Object.keys(dailyErrors).sort();
  const errRates = errDates.map(d => dailyErrors[d].calls > 0 ? +(dailyErrors[d].errors / dailyErrors[d].calls * 100).toFixed(1) : 0);
  if (errorRateChartInstance) { errorRateChartInstance.destroy(); errorRateChartInstance = null; }
  if (errDates.length > 0) {
    const negCol = _vcLiveVar('--vc-neg', '#d24b3e');
    errorRateChartInstance = new Chart(document.getElementById('errorRateChart'), {
      type: 'line',
      data: {
        labels: errDates,
        datasets: [{ label: 'Error Rate (%)', data: errRates, borderColor: negCol, backgroundColor: _vcHexRgba(negCol, 0.1), fill:true, tension:0.3 }]
      },
      options: { responsive:true, plugins:{legend:{display:false}}, scales:{ x:{ticks:{color:window.__vcFg3||'#918a7a',maxTicksLimit:15}}, y:{ticks:{color:window.__vcFg3||'#918a7a'}, beginAtZero:true} } }
    });
  }
}

// ── Sortable tables (universal) ────────────────────────────────────────
// Every .data-table is sortable by clicking a header. Sorting reorders the
// existing rows in the DOM, so it works for any table regardless of how it
// was rendered or whether its tab is currently visible. Values are parsed
// so formatted numbers ($8,725.39 · 35.7M · 61.2%), dates and plain text
// all sort correctly; a cell may also carry an explicit data-sort-value.
function cellSortKey(td) {
  if (!td) return { num: false, v: '' };
  if (td.dataset && td.dataset.sortValue !== undefined) {
    const v = parseFloat(td.dataset.sortValue);
    if (!isNaN(v)) return { num: true, v };
  }
  const txt = (td.textContent || '').trim();
  const cleaned = txt.replace(/[,$€%\s]/g, '');
  const m = cleaned.match(/^(-?\d*\.?\d+)([kmbgt]?)$/i);
  if (m) {
    let n = parseFloat(m[1]);
    const s = (m[2] || '').toLowerCase();
    n *= s === 'k' ? 1e3 : s === 'm' ? 1e6 : (s === 'b' || s === 'g') ? 1e9 : s === 't' ? 1e12 : 1;
    return { num: true, v: n };
  }
  if (/\d/.test(txt) && /[\/\-]/.test(txt)) {        // date-like (12/31/2026, 2026-01-02)
    const d = Date.parse(txt);
    if (!isNaN(d)) return { num: true, v: d };
  }
  return { num: false, v: txt.toLowerCase() };
}
function sortTableByColumn(table, idx, dir) {
  const tbody = table.tBodies[0];
  if (!tbody) return;
  const rows = Array.from(tbody.rows);
  // Rows marked data-nosort (e.g. the plan table's total row) are pinned to
  // the bottom instead of being sorted in with the data rows.
  const pinned = rows.filter(r => r.hasAttribute('data-nosort'));
  const keyed = rows.filter(r => !r.hasAttribute('data-nosort')).map(r => ({ r, k: cellSortKey(r.cells[idx]) }));
  keyed.sort((a, b) => {
    const cmp = (a.k.num && b.k.num)
      ? a.k.v - b.k.v
      : String(a.k.v).localeCompare(String(b.k.v), undefined, { numeric: true });
    return dir === 'asc' ? cmp : -cmp;
  });
  keyed.forEach(x => tbody.appendChild(x.r));
  pinned.forEach(r => tbody.appendChild(r));
}
function attachTableSorting(table) {
  if (!table.tHead || table._sortWired) return;
  table._sortWired = true;
  const ths = Array.from(table.tHead.rows[0].cells);
  ths.forEach((th, idx) => {
    th.addEventListener('click', (e) => {
      if (e.target.closest('.col-resizer')) return;   // resize grip, not a sort
      const cur = th.classList.contains('sort-asc') ? 'asc' : th.classList.contains('sort-desc') ? 'desc' : null;
      const dir = cur === 'desc' ? 'asc' : 'desc';    // first click = desc (largest first)
      ths.forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
      th.classList.add('sort-' + dir);
      sortTableByColumn(table, idx, dir);
    });
  });
}
document.querySelectorAll('table.data-table').forEach(attachTableSorting);

// ── Resizable / auto-fit columns ──────────────────────────────────────
// Columns carry explicit widths (fixed layout) so a long value (e.g. a
// project name or plan title) clips with an ellipsis instead of blowing out
// the page; the wrapper scrolls horizontally when the columns are wider than
// it. Drag a column's right edge to resize; double-click that edge to
// auto-fit to content. Header clicks still sort — the grip stops propagation.
function enhanceResizableTable(table, defaults) {
  if (!table || !table.tHead || table.classList.contains('vc-resizable')) return;
  table.classList.add('vc-resizable');
  const ths = Array.from(table.tHead.rows[0].cells);
  function syncTableWidth() {
    const sum = ths.reduce((s, th) => s + parseFloat(th.style.width || th.getBoundingClientRect().width || 0), 0);
    table.style.width = sum + 'px';
  }
  function autoFit(idx, th) {
    const sample = (table.tBodies[0] && table.tBodies[0].rows[0] && table.tBodies[0].rows[0].cells[idx]) || th;
    const cs = getComputedStyle(sample);
    const meas = document.createElement('span');
    meas.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;left:-9999px;top:0;';
    meas.style.font = cs.fontWeight + ' ' + cs.fontSize + '/' + cs.lineHeight + ' ' + cs.fontFamily;
    meas.style.letterSpacing = cs.letterSpacing;
    document.body.appendChild(meas);
    let max = 0;
    const thCs = getComputedStyle(th);
    meas.style.font = thCs.fontWeight + ' ' + thCs.fontSize + '/' + thCs.lineHeight + ' ' + thCs.fontFamily;
    meas.style.letterSpacing = thCs.letterSpacing;
    meas.textContent = th.textContent;
    max = meas.offsetWidth;
    meas.style.font = cs.fontWeight + ' ' + cs.fontSize + '/' + cs.lineHeight + ' ' + cs.fontFamily;
    meas.style.letterSpacing = cs.letterSpacing;
    if (table.tBodies[0]) Array.from(table.tBodies[0].rows).forEach(r => {
      const cell = r.cells[idx];
      if (cell) { meas.textContent = cell.textContent; if (meas.offsetWidth > max) max = meas.offsetWidth; }
    });
    meas.remove();
    th.style.width = Math.ceil(max + 30) + 'px'; // + cell padding allowance
    syncTableWidth();
  }
  ths.forEach((th, idx) => {
    if (!th.style.width) th.style.width = (defaults[idx] || 120) + 'px';
    const grip = document.createElement('span');
    grip.className = 'col-resizer';
    grip.title = 'Drag to resize · double-click to auto-fit';
    let startX = 0, startW = 0;
    grip.addEventListener('mousedown', (e) => {
      e.preventDefault(); e.stopPropagation();
      startX = e.clientX; startW = th.getBoundingClientRect().width;
      const onMove = (ev) => { th.style.width = Math.max(48, startW + (ev.clientX - startX)) + 'px'; syncTableWidth(); };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.body.style.cursor = '';
      };
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
      document.body.style.cursor = 'col-resize';
    });
    grip.addEventListener('click', (e) => e.stopPropagation());      // never trigger sort
    grip.addEventListener('dblclick', (e) => { e.preventDefault(); e.stopPropagation(); autoFit(idx, th); });
    th.appendChild(grip);
  });
  syncTableWidth();
}
enhanceResizableTable(document.getElementById('projectTable'), [460, 150, 100, 120, 120, 130, 120]); // name, source, sessions, messages, api, output, file size
enhanceResizableTable(document.getElementById('plansTable'), [300, 130, 90, 90]);                   // title, created, lines, kb

// ── Filter events ──────────────────────────────────────────────────────
function _applySessionFilter() {
  const filtered = getFilteredSessions();
  if (sessionTable) sessionTable.update(filtered);
  updateBulkBtnLabel();
}
document.getElementById('filterProject').addEventListener('change', _applySessionFilter);
document.getElementById('filterSource').addEventListener('change', _applySessionFilter);
document.getElementById('filterSearch').addEventListener('input', _applySessionFilter);
document.getElementById('hideEmptySessions').addEventListener('change', () => { applyFilter(currentDays); });

// ── Masonry layout (round-robin distribution into N independent flex columns) ──
// Adapted from collector/client/src/components/MasonryColumns.tsx pattern.
// Items are split round-robin so reading order stays row-major: items[0] →
// col[0], items[1] → col[1], items[2] → col[0], ... Both columns flow
// independently as flex columns, no inter-row alignment, so a short card
// next to a tall card doesn't leave forced empty space.
function _applyMasonry() {
  const sections = document.querySelectorAll('.masonry-section');
  const cols = window.innerWidth >= 960 ? 2 : 1;
  sections.forEach(function(section) {
    if (!section.__originalCards) {
      section.__originalCards = Array.from(section.children).filter(function(el) {
        return el.nodeType === 1 && el.classList.contains('chart-box');
      });
    }
    const cards = section.__originalCards;
    while (section.firstChild) section.removeChild(section.firstChild);
    const colEls = [];
    for (let i = 0; i < cols; i++) {
      const c = document.createElement('div');
      c.className = 'masonry-col';
      colEls.push(c);
    }
    cards.forEach(function(card, i) { colEls[i % cols].appendChild(card); });
    colEls.forEach(function(c) { section.appendChild(c); });
  });
}
_applyMasonry();
let _masonryResizeTimer;
window.addEventListener('resize', function() {
  clearTimeout(_masonryResizeTimer);
  _masonryResizeTimer = setTimeout(_applyMasonry, 150);
});

// ── Init ───────────────────────────────────────────────────────────────
// Apply the persisted/system theme class to <html> BEFORE any chart is built.
// custom.css (linked just above this script) scopes its --vc-* overrides to
// html.theme-light/.theme-dark .vc, so the class must be present at chart-build
// time for an accent override to be readable via getComputedStyle. The full
// theme wiring (toggle + re-sync) is set up later in the top-bar IIFE.
try {
  const _saved = localStorage.getItem('vc-theme');
  const _prefersDark = (typeof window !== 'undefined' && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches);
  const _initTheme = (_saved === 'light' || _saved === 'dark') ? _saved : (_prefersDark ? 'dark' : 'light');
  document.documentElement.classList.remove('theme-light', 'theme-dark');
  document.documentElement.classList.add('theme-' + _initTheme);
  if (typeof setupVcChartDefaults === 'function') setupVcChartDefaults();
} catch (e) {}

filterData(0, '');
initTimeFilter();
let pfTimer;
document.getElementById('projectFilter').addEventListener('input', function() {
  clearTimeout(pfTimer);
  pfTimer = setTimeout(() => applyFilter(undefined, this.value), 300);
});
initTabs();
renderKPI();
renderCosts();
renderActivity();
renderProjects();
renderSessions();
document.getElementById('bulkDownloadBtn').addEventListener('click', bulkDownloadSessions);
renderPlan();
renderLimits();
renderInsights();
renderAgentsTab();

function initInsightsSubnav() {
  const nav = document.getElementById('insightsSubnav');
  if (!nav) return;
  const sections = Array.from(document.querySelectorAll('#tab-insights .vc-subsection'));
  nav.addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-sub]');
    if (!btn) return;
    const key = btn.dataset.sub;
    nav.querySelectorAll('button').forEach(b => b.classList.toggle('on', b === btn));
    sections.forEach(s => { s.hidden = s.dataset.sub !== key; });
    if (window.Chart) Object.values(Chart.instances || {}).forEach(c => { try { c.resize(); } catch (_) {} });
  });
}

// F2 Anonymization mode
const anonMap = {};
let anonCounter = 0;
function anonName(name) {
  if (!anonMap[name]) { anonCounter++; anonMap[name] = 'Project ' + anonCounter; }
  return anonMap[name];
}
const anonSourceMap = {};
let anonSourceCounter = 0;
function anonSource(name) {
  if (!anonSourceMap[name]) { anonSourceCounter++; anonSourceMap[name] = 'Source ' + anonSourceCounter; }
  return anonSourceMap[name];
}
document.addEventListener('keydown', function(e) {
  if (e.key === 'F2') {
    e.preventDefault();
    anonMode = !anonMode;
    document.body.classList.toggle('anon-mode', anonMode);
    // Re-render everything via applyFilter (handles cleanup)
    applyFilter(currentDays);
    // Top bar USER is set once at load and not covered by applyFilter
    const topUser = document.getElementById('vcTopUser');
    if (topUser) topUser.textContent = anonMode ? 'Anonymous' : ((D.account && D.account.name) || '-');
    // Show/hide notification
    let note = document.getElementById('anonNote');
    if (!note) {
      note = document.createElement('div');
      note.id = 'anonNote';
      note.className = 'vc';
      note.style.cssText = 'position:fixed;top:14px;right:14px;padding:8px 14px;border:1px solid var(--vc-accent,#b04a2f);background:var(--vc-panel,#fbfaf6);font-family:\'Geist Mono\',\'JetBrains Mono\',ui-monospace,monospace;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;z-index:9999;transition:opacity 0.3s;color:var(--vc-accent,#b04a2f);';
      document.body.appendChild(note);
    }
    note.textContent = anonMode ? '> ANONYMIZATION ON' : '> ANONYMIZATION OFF';
    note.style.opacity = '1';
    setTimeout(() => { note.style.opacity = '0'; }, 2000);
  }
});


// ── Variant-C top bar wiring ──────────────────────────────────────
(function() {
  // Theme handling — two-state toggle (light/dark). System pref only used
  // for the very first render when no saved preference exists; once the
  // user clicks the toggle, their choice is locked.
  function vcSystemPrefersDark() {
    try { return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches; }
    catch (e) { return false; }
  }
  function applyVcTheme(theme) {
    document.documentElement.classList.remove('theme-light', 'theme-dark');
    document.documentElement.classList.add('theme-' + theme);
    const btn = document.getElementById('vcThemeToggle');
    if (btn) btn.innerHTML = theme === 'dark' ? '&#9790;' : '&#9737;';
    if (typeof setupVcChartDefaults === 'function') setupVcChartDefaults();
    // Existing Chart.js instances cache resolved arc borderColor at creation
    // time. After theme switch, refresh doughnut/pie datasets so segment
    // separators pick up the new panel colour.
    try {
      const arcCol = (Chart.defaults.elements.arc && Chart.defaults.elements.arc.borderColor) || '#fff';
      const instances = (Chart && Chart.instances) ? Object.values(Chart.instances) : [];
      instances.forEach(function(c) {
        const t = c && c.config && c.config.type;
        if (t !== 'doughnut' && t !== 'pie') return;
        (c.data && c.data.datasets || []).forEach(function(ds) { ds.borderColor = arcCol; });
        c.update('none');
      });
    } catch (e) {}
  }
  const saved = localStorage.getItem('vc-theme');
  const initialTheme = (saved === 'light' || saved === 'dark')
    ? saved
    : (vcSystemPrefersDark() ? 'dark' : 'light');
  applyVcTheme(initialTheme);
  document.getElementById('vcThemeToggle')?.addEventListener('click', () => {
    const cur = document.documentElement.classList.contains('theme-dark') ? 'dark' : 'light';
    const next = cur === 'dark' ? 'light' : 'dark';
    localStorage.setItem('vc-theme', next);
    applyVcTheme(next);
  });

  // Generated-at timestamp (replaces the old live UTC clock)
  (function fillGenerated() {
    const el = document.getElementById('vcGenerated');
    if (!el) return;
    const d = (typeof D !== 'undefined') ? D : null;
    if (!d || !d.generated_at) { el.textContent = ''; return; }
    const lbl = (d.locale && d.locale.header && d.locale.header.generated) || 'Generated';
    const locCode = (d.locale && d.locale.locale_code) || undefined;
    try {
      el.textContent = lbl + ': ' + new Date(d.generated_at).toLocaleString(locCode);
    } catch (e) {
      el.textContent = lbl + ': ' + d.generated_at;
    }
  })();

  // Populate USER / PLAN from DASHBOARD_DATA
  const d = (typeof D !== 'undefined') ? D : null;
  if (d) {
    const userEl = document.getElementById('vcTopUser');
    const planEl = document.getElementById('vcTopPlan');
    if (userEl) userEl.textContent = (d.account && d.account.name) || '-';
    if (planEl) {
      const plan = (d.plan && d.plan.current_billing && d.plan.current_billing.plan)
        || (d.account && d.account.plan)
        || '-';
      planEl.textContent = plan;
    }
  }
})();


// ── Variant-C primary nav wiring ──────────────────────────────────
(function() {
  const tabsEl = document.getElementById('vcTabs');
  if (!tabsEl) return;
  // Tabs: clone TAB_NAMES into vcTabs
  TAB_NAMES.forEach((t, i) => {
    const btn = document.createElement('button');
    btn.className = 'vc-tab' + (i === 0 ? ' active' : '');
    btn.textContent = (t.label || '').toUpperCase();
    btn.dataset.tab = t.id;
    btn.addEventListener('click', () => activateTabByName(t.id, true));
    tabsEl.appendChild(btn);
  });

  // Hash router: on page load, switch to the tab from #limits / #plan etc.
  // F5 preserves the visible tab because the URL still carries the hash.
  // hashchange handles back/forward and external hash edits.
  const initial = tabFromHash();
  if (initial) activateTabByName(initial, false);
  window.addEventListener('hashchange', () => {
    const t = tabFromHash();
    if (t) activateTabByName(t, false);
  });

  // Range buttons
  const rangeEl = document.getElementById('vcRange');
  rangeEl?.querySelectorAll('.vc-range-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      rangeEl.querySelectorAll('.vc-range-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const days = parseInt(btn.dataset.days, 10) || 0;
      // Update top-bar RANGE display
      const rEl = document.getElementById('vcTopRange');
      if (rEl) rEl.textContent = days === 0 ? 'all' : days + 'd';
      applyFilter(days);
    });
  });

  // Quick filter — drives the same handler as #projectFilter (debounced)
  let pfTimer;
  const qf = document.getElementById('vcQuickFilter');
  qf?.addEventListener('input', function() {
    clearTimeout(pfTimer);
    pfTimer = setTimeout(() => {
      const legacy = document.getElementById('projectFilter');
      if (legacy) legacy.value = qf.value;
      applyFilter(undefined, qf.value);
    }, 300);
  });

  // Insights sub-nav (one section visible at a time)
  initInsightsSubnav();
})();

// ── Variant-C KPI strip rendering ─────────────────────────────────
function fmtVcUsd(n) {
  return '$' + (n || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}
function fmtVcTok(n) {
  if (!n) return '0';
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return String(Math.round(n));
}

function renderVcKpis() {
  const k = (typeof F !== 'undefined' && F.kpi) ? F.kpi : (D && D.kpi) || {};
  if (!k) return;

  // Both currency modes share the day-slice basis (F.kpi.total_cost is the sum
  // of F.daily_costs): local mode converts per-day at each day's FX rate, USD
  // mode shows the same sum unconverted. Tokens mode keeps the USD display.
  const localMode = costMetricMode === 'local' && typeof F !== 'undefined' && !!currentFx();
  const fmtMoney = localMode ? costModeFmt : fmtVcUsd;
  const apiEq = localMode
    ? (F.daily_costs || []).reduce((a, r) => a + (r.total || 0) * (fxForDate(r.date) || 0), 0)
    : (k.total_cost || 0);
  const paid = localMode
    ? calcFilteredPlanCost((F.daily_costs || []).map(r => r.date), true)
    : (k.actual_plan_cost || 0);
  const savePct = apiEq > 0 ? ((apiEq - paid) / apiEq * 100) : 0;
  const apiEqEl = document.getElementById('vcKpiApiEq');
  if (apiEqEl) apiEqEl.textContent = fmtMoney(apiEq);
  const apiSubEl = document.getElementById('vcKpiApiEqSub');
  if (apiSubEl) apiSubEl.innerHTML = 'paid <b>' + fmtMoney(paid) + '</b> &middot; save <b>' + savePct.toFixed(1) + '%</b>';
  const deltaEl = document.getElementById('vcKpiSavePct');
  if (deltaEl) {
    if (savePct >= 0) {
      deltaEl.innerHTML = '&#9650; ' + savePct.toFixed(1) + '%';
    } else {
      deltaEl.innerHTML = '&#9660; ' + (-savePct).toFixed(1) + '%';
    }
  }

  const sessions = k.total_sessions || 0;
  // Sessions per day over the active span (first→last session date) of the
  // filtered range. Wall-clock session "duration" was dropped here: with ~41%
  // of sessions under a minute and ~13% spanning over a day (resumed/idle), its
  // median swung wildly between range filters and conveyed little.
  let perDay = 0;
  if (typeof F !== 'undefined' && F.sessions && F.sessions.length > 0) {
    const dates = F.sessions.map(s => s.date).filter(Boolean).sort();
    if (dates.length) {
      const spanDays = Math.max(1, Math.round((new Date(dates[dates.length - 1]) - new Date(dates[0])) / 86400000) + 1);
      perDay = F.sessions.length / spanDays;
    }
  }
  const sessEl = document.getElementById('vcKpiSessions');
  if (sessEl) sessEl.textContent = sessions.toLocaleString('en-US');
  const sessSub = document.getElementById('vcKpiSessionsSub');
  if (sessSub) {
    sessSub.innerHTML = '<b>' + perDay.toFixed(1) + '</b>/day';
    sessSub.title = D.locale.locale_code === 'de'
      ? 'Sitzungen pro Tag über die aktive Spanne (erste bis letzte Sitzung) des gewählten Zeitraums.'
      : 'Sessions per day across the active span (first to last session) of the selected range.';
  }

  const msgs = k.total_messages || 0;
  const perSession = sessions > 0 ? Math.round(msgs / sessions) : 0;
  const msgEl = document.getElementById('vcKpiMessages');
  if (msgEl) msgEl.textContent = msgs.toLocaleString('en-US');
  const msgSub = document.getElementById('vcKpiMessagesSub');
  if (msgSub) msgSub.innerHTML = '<b>' + perSession + '</b>/session';

  const output = k.total_output_tokens || 0;
  const input = k.total_input_tokens || 0;
  const cacheRead = k.total_cache_read_tokens || 0;
  const cacheWrite = k.total_cache_write_tokens || 0;
  const outEl = document.getElementById('vcKpiOutput');
  if (outEl) outEl.textContent = fmtVcTok(output);
  const inEl = document.getElementById('vcKpiInput');
  if (inEl) inEl.textContent = fmtVcTok(input);

  const totalIn = input + cacheRead + cacheWrite;
  const cacheHit = totalIn > 0 ? (cacheRead / totalIn * 100) : 0;
  const chEl = document.getElementById('vcKpiCacheHit');
  if (chEl) chEl.innerHTML = cacheHit.toFixed(1) + '<span class="vc-kpi-pct">%</span>';
  const chSub = document.getElementById('vcKpiCacheHitSub');
  if (chSub) chSub.innerHTML = 'read <b>' + fmtVcTok(cacheRead) + '</b>';
}
// Initial render
if (typeof F !== 'undefined') renderVcKpis();
// Re-render on filter change: hook into applyFilter via wrapper
if (typeof applyFilter === 'function') {
  const _origApplyFilter = applyFilter;
  applyFilter = function(...args) {
    const r = _origApplyFilter.apply(this, args);
    try { renderVcKpis(); } catch (e) { console.warn('renderVcKpis failed', e); }
    return r;
  };
}

// ── Variant-C shared render helpers ───────────────────────────────
function vcSection(title, meta) {
  const h = document.createElement('div');
  h.className = 'vc-tab-h';
  const t = document.createElement('div'); t.className = 'vc-tab-h-title';
  t.textContent = title;
  const r = document.createElement('div'); r.className = 'vc-tab-h-rule';
  const m = document.createElement('div'); m.className = 'vc-tab-h-meta'; m.textContent = meta || '';
  h.appendChild(t); h.appendChild(r); h.appendChild(m);
  return h;
}

function vcDistbar(rows, opts) {
  opts = opts || {};
  const max = opts.max || Math.max.apply(null, rows.map(function(r){return r.value||0}).concat([1]));
  const series = opts.series || 1;
  const seriesClass = series === 2 ? 's2' : (series === 3 ? 's3' : '');
  const c = document.createElement('div'); c.className = 'vc-distbar';
  rows.forEach(function(r){
    const row = document.createElement('div'); row.className = 'vc-distbar-row';
    const n = document.createElement('div'); n.className = 'vc-distbar-name'; n.textContent = r.name;
    if (opts.anonName) n.classList.add('anon-blur');
    const t = document.createElement('div'); t.className = 'vc-distbar-track';
    const f = document.createElement('div'); f.className = 'vc-distbar-fill ' + seriesClass;
    const v = (r.value || 0);
    f.style.width = (max > 0 ? (v / max * 100) : 0).toFixed(1) + '%';
    t.appendChild(f);
    const val = document.createElement('div'); val.className = 'vc-distbar-val';
    val.textContent = r.label != null ? r.label : v.toLocaleString('en-US');
    row.appendChild(n); row.appendChild(t); row.appendChild(val);
    c.appendChild(row);
  });
  return c;
}

function vcStatRows(rows) {
  const c = document.createDocumentFragment();
  rows.forEach(function(r){
    const row = document.createElement('div'); row.className = 'vc-stat-row';
    const k = document.createElement('div'); k.className = 'k'; k.textContent = r.k;
    const v = document.createElement('div'); v.className = 'v' + (r.acc ? ' acc' : '');
    if (r.html) { v.innerHTML = r.html; } else { v.textContent = r.v; }
    if (r.title) row.title = r.title;
    row.appendChild(k); row.appendChild(v);
    c.appendChild(row);
  });
  return c;
}

function vcMiscGrid(items) {
  const c = document.createElement('div'); c.className = 'vc-misc-grid';
  items.forEach(function(it){
    const m = document.createElement('div'); m.className = 'vc-misc';
    const v = document.createElement('div'); v.className = 'v' + (it.acc ? ' acc' : '');
    v.textContent = it.v;
    const l = document.createElement('div'); l.className = 'l'; l.textContent = it.l;
    m.appendChild(v); m.appendChild(l);
    c.appendChild(m);
  });
  return c;
}

// Wrap unpredictable text content (for anon-mode CSS blur)
function vcAnonWrap(text) {
  const s = document.createElement('span');
  s.className = 'anon-blur';
  s.textContent = text;
  return s;
}

// ── Variant-C tab section meta wiring ─────────────────────────────
function _vcMeta(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}
function updateVcTabMetas() {
  const k = (typeof F !== 'undefined' && F.kpi) ? F.kpi : (D && D.kpi) || {};
  const range = (function() {
    const active = document.querySelector('.vc-range-btn.active');
    return active ? (active.dataset.days === '0' ? 'all' : active.dataset.days + 'd') : 'all';
  })();
  // vcCostMeta is owned by renderCostMetricToggle (metric toggle)
  _vcMeta('vcProjectsMeta', (F && F.projects ? F.projects.length : 0) + ' projects · ' + range);
  _vcMeta('vcSessionsMeta', (F && F.sessions ? F.sessions.length : 0) + ' sessions · ' + range);
  // vcPlanMeta is owned by renderPlan (currency toggle)
}
updateVcTabMetas();
// Re-run on filter change via wrapping
if (typeof applyFilter === 'function') {
  const _origAF2 = applyFilter;
  applyFilter = function(...args) {
    const r = _origAF2.apply(this, args);
    try { updateVcTabMetas(); } catch (e) {}
    return r;
  };
}
