
const D = "__DATA_PLACEHOLDER__";

// ── Helpers ────────────────────────────────────────────────────────────
const fmt = n => n.toLocaleString(D.locale.locale_code);
const fmtUSD = n => '$' + n.toLocaleString(D.locale.locale_code, {minimumFractionDigits:2, maximumFractionDigits:2});
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

const MODEL_COLORS = {
  'Opus 4.7': '#c084fc', 'Opus 4.6': '#a855f7', 'Opus 4.5': '#7c3aed',
  'Sonnet 4.5': '#3b82f6', 'Haiku 4.5': '#22c55e',
  'Unknown': '#6b7280'
};

const SOURCE_COLORS = [
  {bg:'rgba(245,158,11,0.15)', fg:'#f59e0b'},
  {bg:'rgba(6,182,212,0.15)', fg:'#06b6d4'},
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

Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#1e293b';

const scaleDefaults = {
  x: { ticks: { color: '#64748b' }, grid: { color: '#1e293b' } },
  y: { ticks: { color: '#64748b' }, grid: { color: '#1e293b' } },
};

// ── Filtered Data & Time Filter ────────────────────────────────────────
let F = {};
const charts = {};
let currentDays = 0;
let anonMode = false;
let agentTypesChartInstance, agentDescsChartInstance, errorByCatChartInstance, errorByToolChartInstance;
const chartColors = ['#6366f1','#22c55e','#f59e0b','#ef4444','#a855f7','#06b6d4','#ec4899','#3b82f6','#f97316','#14b8a6'];
let currentProjectFilter = '';

function calcFilteredPlanCost(filteredDates) {
  if (!filteredDates.length || !D.plan) return D.kpi.actual_plan_cost;
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
    cost += (p.plan_cost_usd || 0) * fraction;
  });
  return Math.round(cost * 100) / 100;
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
  if (cutoff) filteredSessions = filteredSessions.filter(s => s.date >= cutoff);
  if (pf) filteredSessions = filteredSessions.filter(s => (s.project || '').toLowerCase().includes(pf));
  F.sessions = filteredSessions;

  // Rebuild daily aggregates from filtered sessions
  const dailyCostMap = {};
  const dailyMsgMap = {};
  F.sessions.forEach(s => {
    if (!s.date) return;
    if (!dailyMsgMap[s.date]) dailyMsgMap[s.date] = {date: s.date, messages: 0, sessions: 0};
    dailyMsgMap[s.date].messages += s.messages || 0;
    dailyMsgMap[s.date].sessions += 1;
    if (!dailyCostMap[s.date]) dailyCostMap[s.date] = {date: s.date, total: 0};
    dailyCostMap[s.date].total += s.cost || 0;
    Object.entries(s.model_breakdown || {}).forEach(([model, d]) => {
      dailyCostMap[s.date][model] = (dailyCostMap[s.date][model] || 0) + (d.cost || 0);
    });
  });
  const allDates = [...new Set([...Object.keys(dailyCostMap), ...Object.keys(dailyMsgMap)])].sort();
  F.daily_costs = allDates.map(d => dailyCostMap[d] || {date: d, total: 0});
  F.daily_messages = allDates.map(d => dailyMsgMap[d] || {date: d, messages: 0, sessions: 0});

  // Recalculate cumulative costs from filtered daily costs
  let cum = 0;
  F.cumulative_costs = F.daily_costs.map(r => { cum += r.total; return {date: r.date, cost: cum}; });

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

  // Recalculate hourly_distribution
  const hourly = Array.from({length:24}, (_, i) => ({hour: i, messages: 0}));
  F.sessions.forEach(s => {
    if (s.start) {
      const h = new Date(s.start).getHours();
      hourly[h].messages += s.messages || 0;
    }
  });
  F.hourly_distribution = hourly;

  // Recalculate weekday_distribution
  const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const weekday = [0,0,0,0,0,0,0];
  F.sessions.forEach(s => {
    if (s.start) {
      const d = new Date(s.start).getDay();
      weekday[d] += s.messages || 0;
    }
  });
  // Reorder to Mon-Sun
  F.weekday_distribution = [1,2,3,4,5,6,0].map(i => ({day: dayNames[i], messages: weekday[i]}));

  // Recalculate tool_summary
  const toolMap = {};
  F.sessions.forEach(s => {
    Object.entries(s.tools || {}).forEach(([name, count]) => {
      toolMap[name] = (toolMap[name] || 0) + count;
    });
  });
  F.tool_summary = Object.entries(toolMap).map(([name, count]) => ({name, count})).sort((a, b) => b.count - a.count);

  // Recalculate KPI
  const totalCost = filteredTotalCost;
  const totalSessions = F.sessions.length;
  const totalMessages = F.sessions.reduce((s, x) => s + (x.messages || 0), 0);
  const totalOutputTokens = F.sessions.reduce((s, x) => s + (x.output_tokens || 0), 0);
  const totalInputTokens = F.sessions.reduce((s, x) => s + (x.input_tokens || 0), 0);
  const totalCacheReadTokens = F.sessions.reduce((s, x) => s + (x.cache_read_tokens || 0), 0);
  const totalCacheWriteTokens = F.sessions.reduce((s, x) => s + (x.cache_write_tokens || 0), 0);
  const dates = F.sessions.map(s => s.date).filter(Boolean).sort();
  F.kpi = {
    total_cost: totalCost,
    actual_plan_cost: calcFilteredPlanCost(dates),
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
      const t = ad.type || 'unknown';
      agentTypeMap[t] = (agentTypeMap[t] || 0) + 1;
      const d = ad.description || ad.desc || '';
      if (d) agentDescMap[d] = (agentDescMap[d] || 0) + 1;
    });
    (s.subagents || []).forEach(sa => {
      totalDispatches++;
      const t = sa.type || 'unknown';
      agentTypeMap[t] = (agentTypeMap[t] || 0) + 1;
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
  const fErrByTool = {}, fErrByCat = {};
  F.sessions.forEach(s => {
    (s.errors || []).forEach(e => {
      fErrByTool[e.tool || 'unknown'] = (fErrByTool[e.tool || 'unknown'] || 0) + 1;
      fErrByCat[e.category || 'other'] = (fErrByCat[e.category || 'other'] || 0) + 1;
    });
  });
  F.error_summary = {
    total_errors: fErrors,
    total_tool_calls: fToolCalls,
    error_rate: fToolCalls > 0 ? +(fErrors / fToolCalls * 100).toFixed(2) : 0,
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
  renderAgentsTab();
}

function renderToolUsageChart() {
  const tools = (F.tool_summary || []).slice(0, 20);
  if (tools.length > 0) {
    charts.toolUsage = new Chart(document.getElementById('chartToolUsage'), {
      type: 'bar',
      data: { labels: tools.map(t => t.name),
        datasets: [{ label: D.locale.insights.tool_calls, data: tools.map(t => t.count),
          backgroundColor: tools.map((_, i) => 'hsl(' + (i * 18) + ',60%,55%)'), borderRadius: 4 }] },
      options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: { x: { ...scaleDefaults.x, title: { display: true, text: D.locale.insights.tool_calls, color: '#64748b' } },
          y: { ...scaleDefaults.y, ticks: { font: { size: 11 } } } } }
    });
  }
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
  {id:'activity', label:D.locale.tabs.activity},
  {id:'projects', label:D.locale.tabs.projects},
  {id:'sessions', label:D.locale.tabs.sessions},
  {id:'plan', label:D.locale.tabs.plan},
  {id:'insights', label:D.locale.tabs.insights},
  {id:'agents', label:D.locale.tabs.agents},
];

function initTabs() {
  const bar = document.getElementById('tabBar');
  TAB_NAMES.forEach((t, i) => {
    const btn = document.createElement('button');
    btn.className = 'tab-btn' + (i === 0 ? ' active' : '');
    btn.textContent = t.label;
    btn.addEventListener('click', () => switchTab(t.id, btn));
    bar.appendChild(btn);
  });
}

function switchTab(name, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-' + name).classList.add('active');
}

// ── Tab 1: Costs ───────────────────────────────────────────────────────
function renderCosts() {
  const dates = F.daily_costs.map(d => d.date);
  const models = D.models;

  charts.dailyCost = new Chart(document.getElementById('chartDailyCost'), {
    type: 'bar',
    data: {
      labels: dates,
      datasets: models.map(m => ({
        label: m,
        data: F.daily_costs.map(d => d[m] || 0),
        backgroundColor: MODEL_COLORS[m] || '#6b7280',
        borderRadius: 2,
      }))
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8' } }, tooltip: { mode: 'index', intersect: false } },
      scales: { x: { ...scaleDefaults.x, stacked: true }, y: { ...scaleDefaults.y, stacked: true, title: { display: true, text: 'USD', color: '#64748b' } } }
    }
  });

  charts.cumCost = new Chart(document.getElementById('chartCumCost'), {
    type: 'line',
    data: {
      labels: F.cumulative_costs.map(d => d.date),
      datasets: [{ label: D.locale.costs.cumulative_label, data: F.cumulative_costs.map(d => d.cost),
        borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.1)', fill: true, tension: 0.3, pointRadius: 2 }]
    },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8' } } },
      scales: { x: scaleDefaults.x, y: { ...scaleDefaults.y, title: { display: true, text: 'USD', color: '#64748b' } } } }
  });

  charts.modelDist = new Chart(document.getElementById('chartModelDist'), {
    type: 'doughnut',
    data: {
      labels: F.model_summary.map(m => m.model),
      datasets: [{ data: F.model_summary.map(m => m.cost),
        backgroundColor: F.model_summary.map(m => MODEL_COLORS[m.model] || '#6b7280'), borderWidth: 0 }]
    },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom', labels: { color: '#94a3b8', padding: 16 } },
        tooltip: { callbacks: { label: ctx => ctx.label + ': ' + fmtUSD(ctx.raw) + ' (' + (F.kpi.total_cost > 0 ? (ctx.raw / F.kpi.total_cost * 100).toFixed(1) : '0.0') + '%)' } } } }
  });

  const cbt = F.cost_by_token_type;
  charts.tokenType = new Chart(document.getElementById('chartTokenType'), {
    type: 'bar',
    data: {
      labels: ['Input', 'Output', 'Cache Read', 'Cache Write'],
      datasets: [{ data: [cbt.input, cbt.output, cbt.cache_read, cbt.cache_write],
        backgroundColor: ['#3b82f6', '#a855f7', '#22c55e', '#f59e0b'], borderRadius: 6 }]
    },
    options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: { x: { ...scaleDefaults.x, title: { display: true, text: 'USD', color: '#64748b' } }, y: scaleDefaults.y } }
  });

  // Model table
  const tbody = document.getElementById('modelTableBody');
  F.model_summary.forEach(m => {
    const tr = document.createElement('tr');
    const cells = [m.model, fmtUSD(m.cost), fmtTokens(m.output_tokens), fmtTokens(m.input_tokens), fmtTokens(m.cache_read_tokens), fmt(m.calls)];
    cells.forEach((val, i) => {
      const td = document.createElement('td');
      if (i > 0) td.className = 'num';
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
}

function renderHeatmap() {
  const container = document.getElementById('activityHeatmap');
  const monthsEl = document.getElementById('heatmapMonths');
  if (!container) return;
  const msgMap = {};
  F.daily_messages.forEach(d => { msgMap[d.date] = d.messages; });
  const today = new Date();
  const startDate = new Date(today);
  startDate.setDate(startDate.getDate() - (24 * 7) + 1);
  while (startDate.getDay() !== 1) startDate.setDate(startDate.getDate() - 1);
  let maxMsg = 0;
  const td = new Date(startDate);
  while (td <= today) { const k = td.toISOString().slice(0,10); maxMsg = Math.max(maxMsg, msgMap[k]||0); td.setDate(td.getDate()+1); }
  let html = '';
  const weeks = [];
  const d = new Date(startDate);
  let cw = [];
  while (d <= today) {
    const k = d.toISOString().slice(0,10);
    const m = msgMap[k]||0;
    let bg = 'var(--bg3)';
    if (m > 0 && maxMsg > 0) {
      const r = m/maxMsg;
      if (r > 0.7) bg = 'var(--accent)';
      else if (r > 0.4) bg = 'rgba(99,102,241,0.7)';
      else if (r > 0.2) bg = 'rgba(99,102,241,0.4)';
      else bg = 'rgba(99,102,241,0.2)';
    }
    cw.push('<div class="heatmap-cell" style="background:'+bg+'" data-tip="'+k+': '+m+' messages"></div>');
    if (d.getDay()===0) { while(cw.length<7) cw.push('<div class="heatmap-cell" style="background:transparent"></div>'); weeks.push(cw); cw=[]; }
    d.setDate(d.getDate()+1);
  }
  if (cw.length>0) { while(cw.length<7) cw.push('<div class="heatmap-cell" style="background:transparent"></div>'); weeks.push(cw); }
  weeks.forEach(w => { html += '<div class="heatmap-col">'+w.join('')+'</div>'; });
  container.innerHTML = html;
  if (monthsEl) {
    const months = [];
    const md = new Date(startDate);
    let lastMonth = -1, weekIdx = 0;
    while (md <= today) {
      if (md.getDay()===1) { if(md.getMonth()!==lastMonth) { months.push({idx:weekIdx,label:md.toLocaleString('default',{month:'short'})}); lastMonth=md.getMonth(); } weekIdx++; }
      md.setDate(md.getDate()+1);
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
  charts.dailyMsgs = new Chart(document.getElementById('chartDailyMsgs'), {
    type: 'bar',
    data: { labels: F.daily_messages.map(d => d.date),
      datasets: [{ label: D.locale.activity.messages_label, data: F.daily_messages.map(d => d.messages), backgroundColor: '#6366f1', borderRadius: 3 }] },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8' } } }, scales: scaleDefaults }
  });

  const maxHourly = Math.max(...F.hourly_distribution.map(x => x.messages || 1));
  charts.hourly = new Chart(document.getElementById('chartHourly'), {
    type: 'polarArea',
    data: { labels: F.hourly_distribution.map(h => h.hour + ':00'),
      datasets: [{ data: F.hourly_distribution.map(h => h.messages),
        backgroundColor: F.hourly_distribution.map(h => 'rgba(99,102,241,' + (0.3 + 0.7 * (h.messages / maxHourly)) + ')'),
        borderWidth: 1, borderColor: '#2d3348' }] },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { r: { ticks: { color: '#64748b', backdropColor: 'transparent' }, grid: { color: '#1e293b' } } } }
  });

  charts.weekday = new Chart(document.getElementById('chartWeekday'), {
    type: 'bar',
    data: { labels: F.weekday_distribution.map(d => d.day),
      datasets: [{ label: D.locale.activity.messages_label, data: F.weekday_distribution.map(d => d.messages),
        backgroundColor: F.weekday_distribution.map((d, i) => i >= 5 ? '#f59e0b' : '#6366f1'), borderRadius: 4 }] },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } }, scales: scaleDefaults }
  });

  charts.dailySessions = new Chart(document.getElementById('chartDailySessions'), {
    type: 'bar',
    data: { labels: F.daily_messages.map(d => d.date),
      datasets: [{ label: D.locale.activity.sessions_label, data: F.daily_messages.map(d => d.sessions), backgroundColor: '#06b6d4', borderRadius: 3 }] },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8' } } }, scales: scaleDefaults }
  });
  renderHeatmap();
}

// ── Tab 3: Projects ────────────────────────────────────────────────────
function renderProjects() {
  const top = F.projects.slice(0, 15);
  charts.projectCost = new Chart(document.getElementById('chartProjectCost'), {
    type: 'bar',
    data: { labels: top.map(p => anonMode ? anonName(p.name) : p.name.split('/').pop()),
      datasets: [{ label: D.locale.projects.top15_label, data: top.map(p => p.cost), backgroundColor: '#6366f1', borderRadius: 4 }] },
    options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: { x: { ...scaleDefaults.x, title: { display: true, text: 'USD', color: '#64748b' } },
        y: { ...scaleDefaults.y, ticks: { font: { size: 11 } } } } }
  });
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
      return '<span class="source-badge" style="background:'+c.bg+';color:'+c.fg+'">'+escHtml(src)+'</span>';
    }).join(' ');
    const cells = [
      {html: nameCell, cls: ''},
      {html: sourceCell, cls: ''},
      {val: p.sessions, cls: 'num'},
      {val: fmt(p.messages), cls: 'num'},
      {val: fmtUSD(p.cost), cls: 'num'},
      {val: fmtTokens(p.output_tokens), cls: 'num'},
      {val: String(p.file_size_mb), cls: 'num'},
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      if (c.html) { td.innerHTML = c.html; } else { td.textContent = c.val; }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

// ── Tab 4: Sessions ────────────────────────────────────────────────────
let sessionPage = 0;
const SESSION_PER_PAGE = 20;

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
  const sort = document.getElementById('filterSort').value;

  if (proj) list = list.filter(s => s.project === proj);
  if (src) list = list.filter(s => s.source === src);
  if (search) list = list.filter(s =>
    (s.first_prompt || '').toLowerCase().includes(search) ||
    s.project.toLowerCase().includes(search));

  const [key, dir] = sort.split('-');
  list.sort((a, b) => {
    const va = key === 'date' ? a.start : a[key];
    const vb = key === 'date' ? b.start : b[key];
    if (typeof va === 'string') return dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
    return dir === 'asc' ? va - vb : vb - va;
  });
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
    o.value = src; o.textContent = src;
    srcSel.appendChild(o);
  });
  if (sources.includes(currentSrc)) srcSel.value = currentSrc;

  sessionPage = 0;
  renderSessionList();
}

function buildSessionCard(s) {
  const card = document.createElement('div');
  card.className = 'session-card';
  card.addEventListener('click', () => card.classList.toggle('expanded'));

  const modelClass = s.primary_model.toLowerCase().includes('opus') ? 'opus' :
                     s.primary_model.toLowerCase().includes('sonnet') ? 'sonnet' : 'haiku';

  // Top row
  const top = document.createElement('div'); top.className = 'top';
  const projSpan = document.createElement('span'); projSpan.className = 'project'; projSpan.textContent = anonMode ? anonName(s.project) : s.project;
  const costSpan = document.createElement('span'); costSpan.className = 'cost'; costSpan.textContent = fmtUSD(s.cost);
  const rightGroup = document.createElement('span'); rightGroup.style.display = 'flex'; rightGroup.style.alignItems = 'center';
  if (!anonMode && s.has_chat !== false) {
    const chatLink = document.createElement('a'); chatLink.href = 'sessions/' + s.session_id + '.html';
    chatLink.textContent = 'Chat'; chatLink.addEventListener('click', function(e) { e.stopPropagation(); });
    chatLink.style.cssText = 'color:var(--accent2);font-size:12px;padding:4px 10px;border:1px solid var(--accent);border-radius:6px;margin-right:8px;text-decoration:none';
    rightGroup.appendChild(chatLink);
  }
  rightGroup.appendChild(costSpan);
  top.appendChild(projSpan);
  top.appendChild(rightGroup);
  card.appendChild(top);

  // Info row
  const info = document.createElement('div'); info.className = 'info';
  const infoParts = [
    new Date(s.start).toLocaleString(D.locale.locale_code),
    s.duration_min + ' min',
    fmt(s.messages) + D.locale.sessions_tab.messages_suffix,
    fmt(s.api_calls) + D.locale.sessions_tab.api_calls_suffix,
  ];
  infoParts.forEach(t => { const sp = document.createElement('span'); sp.textContent = t; info.appendChild(sp); });
  const badge = document.createElement('span'); badge.className = 'model-badge ' + modelClass; badge.textContent = s.primary_model;
  info.appendChild(badge);
  if (s.source) info.appendChild(makeSourceBadge(s.source));
  if (s.compactions > 0) {
    const compSpan = document.createElement('span'); compSpan.style.color = 'var(--amber)';
    compSpan.innerHTML = '&#9889; ' + s.compactions;
    info.appendChild(compSpan);
  }
  card.appendChild(info);

  // Prompt
  if (s.first_prompt && !anonMode) {
    const prompt = document.createElement('div'); prompt.className = 'prompt';
    prompt.textContent = s.first_prompt;
    card.appendChild(prompt);
  }

  // Details (expandable)
  const details = document.createElement('div'); details.className = 'details';

  const modelDetail = Object.entries(s.model_breakdown || {})
    .map(([m, d]) => m + ': ' + fmtUSD(d.cost) + ' (' + fmtTokens(d.output_tokens) + ' out, ' + d.calls + ' calls)')
    .join(', ');
  const p1 = document.createElement('p'); p1.style.marginBottom = '8px';
  const b1 = document.createElement('strong'); b1.textContent = D.locale.sessions_tab.models_label;
  p1.appendChild(b1);
  p1.appendChild(document.createTextNode(modelDetail));
  details.appendChild(p1);

  const p2 = document.createElement('p');
  p2.textContent = 'Output: ' + fmtTokens(s.output_tokens) + ' | Input: ' + fmtTokens(s.input_tokens) + ' | Cache Read: ' + fmtTokens(s.cache_read_tokens);
  details.appendChild(p2);

  const toolEntries = Object.entries(s.tools || {}).sort((a,b) => b[1]-a[1]).slice(0, 10);
  if (toolEntries.length > 0) {
    const toolsDiv = document.createElement('div'); toolsDiv.className = 'tools'; toolsDiv.style.marginTop = '8px';
    const b2 = document.createElement('strong'); b2.textContent = 'Tools: '; toolsDiv.appendChild(b2);
    toolEntries.forEach(([name, count]) => {
      const tag = document.createElement('span'); tag.className = 'tool-tag';
      tag.textContent = name + ' (' + count + ')';
      toolsDiv.appendChild(tag);
    });
    details.appendChild(toolsDiv);
  }

  const p3 = document.createElement('p');
  p3.style.marginTop = '8px'; p3.style.color = 'var(--text2)'; p3.style.fontSize = '11px';
  p3.textContent = D.locale.sessions_tab.session_label + s.session_id + D.locale.sessions_tab.slug_label + (s.slug || '-');
  details.appendChild(p3);

  card.appendChild(details);
  return card;
}

function updateBulkBtnLabel() {
  const btn = document.getElementById('bulkDownloadBtn');
  if (!btn) return;
  const n = getFilteredSessions().length;
  if (!btn.dataset.busy) {
    btn.textContent = '\u2B07 Download all (' + n + ')';
    btn.disabled = (n === 0);
  }
}
async function bulkDownloadSessions() {
  const btn = document.getElementById('bulkDownloadBtn');
  const sessions = getFilteredSessions().filter(s => s.has_chat !== false);
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
      btn.textContent = 'Loading ' + (i + 1) + '/' + sessions.length + '\u2026';
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
      btn.textContent = 'Zipping\u2026';
      const blob = await zip.generateAsync({type: 'blob'});
      const today = new Date().toISOString().slice(0, 10);
      triggerDownload('claude-sessions-' + today + '.zip', blob, 'application/zip');
    }
  } finally {
    delete btn.dataset.busy;
    updateBulkBtnLabel();
  }

  if (errors > 0) {
    alert(errors + ' sessions konnten nicht geladen werden \u2014 siehe Konsole.');
  }
}

function renderSessionList() {
  const filtered = getFilteredSessions();
  const total = filtered.length;
  const pages = Math.ceil(total / SESSION_PER_PAGE);
  sessionPage = Math.min(sessionPage, Math.max(pages - 1, 0));

  const start = sessionPage * SESSION_PER_PAGE;
  const page = filtered.slice(start, start + SESSION_PER_PAGE);

  document.getElementById('sessionCount').textContent = total + D.locale.sessions_tab.sessions_count_suffix;

  const container = document.getElementById('sessionList');
  container.textContent = '';
  page.forEach(s => container.appendChild(buildSessionCard(s)));

  // Pagination
  const pagDiv = document.getElementById('sessionPagination');
  pagDiv.textContent = '';
  if (pages > 1) {
    if (sessionPage > 0) {
      const first = document.createElement('button'); first.textContent = '«';
      first.addEventListener('click', () => { sessionPage = 0; renderSessionList(); });
      const prev = document.createElement('button'); prev.textContent = '‹';
      prev.addEventListener('click', () => { sessionPage--; renderSessionList(); });
      pagDiv.appendChild(first); pagDiv.appendChild(prev);
    }
    const info = document.createElement('span'); info.className = 'info';
    info.textContent = D.locale.sessions_tab.page_prefix + (sessionPage + 1) + D.locale.sessions_tab.page_separator + pages;
    pagDiv.appendChild(info);
    if (sessionPage < pages - 1) {
      const next = document.createElement('button'); next.textContent = '›';
      next.addEventListener('click', () => { sessionPage++; renderSessionList(); });
      const last = document.createElement('button'); last.textContent = '»';
      last.addEventListener('click', () => { sessionPage = pages - 1; renderSessionList(); });
      pagDiv.appendChild(next); pagDiv.appendChild(last);
    }
  }
  updateBulkBtnLabel();
}

// ── Tab 5: Plan & Billing ──────────────────────────────────────────────
function renderPlan() {
  const plan = D.plan;
  if (!plan) return;
  const cb = plan.current_billing;

  // KPI cards
  const grid = document.getElementById('planKpi');
  const kpis = [
    {cls:'plan-type', label:D.locale.plan.current_plan, value:cb.plan, sub:fmtUSD(cb.plan_cost_usd) + D.locale.plan.monthly_suffix + (cb.plan_cost_eur != null ? ' (' + cb.plan_cost_eur.toFixed(2) + ' \u20ac)' : '')},
    {cls:'api-cost', label:D.locale.plan.total_api_cost, value:fmtUSD(plan.total_api_cost), sub:D.locale.plan.total_api_sub},
    {cls:'savings', label:D.locale.plan.total_savings, value:fmtUSD(plan.total_savings), sub:D.locale.plan.total_savings_sub},
    {cls:'roi', label:D.locale.plan.roi_factor, value:plan.overall_roi + 'x', sub:D.locale.plan.roi_sub},
  ];
  kpis.forEach(c => {
    const div = document.createElement('div');
    div.className = 'plan-card ' + c.cls;
    const lbl = document.createElement('div'); lbl.className = 'label'; lbl.textContent = c.label;
    const val = document.createElement('div'); val.className = 'value'; val.textContent = c.value;
    const sub = document.createElement('div'); sub.className = 'sub'; sub.textContent = c.sub;
    div.appendChild(lbl); div.appendChild(val); div.appendChild(sub);
    grid.appendChild(div);
  });

  // Billing progress
  const bp = document.getElementById('billingProgress');
  const pct = Math.min(100, Math.round(cb.days_elapsed / cb.days_total * 100));
  const barColor = cb.api_cost > cb.plan_cost_usd * 0.8 ? 'var(--green)' : 'var(--accent)';

  const h3 = document.createElement('h3');
  h3.textContent = D.locale.plan.billing_period + ' (' + cb.period_start + ' – ' + cb.period_end + ')';
  bp.appendChild(h3);

  const outer = document.createElement('div'); outer.className = 'progress-bar-outer';
  const inner = document.createElement('div'); inner.className = 'progress-bar-inner';
  inner.style.width = pct + '%';
  inner.style.background = 'linear-gradient(90deg, var(--accent), ' + barColor + ')';
  inner.textContent = pct + '%';
  outer.appendChild(inner);
  bp.appendChild(outer);

  const stats = document.createElement('div'); stats.className = 'progress-stats';
  const statItems = [
    {label:D.locale.plan.day, val:cb.days_elapsed + ' / ' + cb.days_total},
    {label:D.locale.plan.api_cost_so_far, val:fmtUSD(cb.api_cost)},
    {label:D.locale.plan.projected, val:fmtUSD(cb.projected_cost)},
    {label:D.locale.plan.savings_so_far, val:fmtUSD(cb.savings)},
    {label:D.locale.plan.roi, val:cb.roi_factor + 'x'},
    {label:D.locale.plan.sessions, val:String(cb.sessions)},
    {label:D.locale.plan.messages, val:fmt(cb.messages)},
    {label:D.locale.plan.avg_per_day, val:fmtUSD(cb.cost_per_day)},
  ];
  statItems.forEach(s => {
    const item = document.createElement('div'); item.className = 'stat-item';
    const lbl = document.createElement('span'); lbl.textContent = s.label;
    const val = document.createElement('span'); val.className = 'stat-val'; val.textContent = s.val;
    item.appendChild(lbl); item.appendChild(val);
    stats.appendChild(item);
  });
  bp.appendChild(stats);

  // Comparison bars
  const comp = document.getElementById('planComparison');
  const maxApi = Math.max(...plan.periods.map(p => p.api_cost), 1);

  plan.periods.forEach(p => {
    const row = document.createElement('div'); row.className = 'bar-row';
    const label = document.createElement('div'); label.className = 'bar-label';
    label.textContent = p.plan + ' (' + p.start.slice(5) + ' - ' + p.end.slice(5) + ')';

    const track = document.createElement('div'); track.className = 'bar-track';
    const apiBar = document.createElement('div'); apiBar.className = 'bar-fill';
    apiBar.style.width = (p.api_cost / maxApi * 100) + '%';
    apiBar.style.background = 'var(--orange)';
    apiBar.textContent = D.locale.plan.api_label;
    track.appendChild(apiBar);

    const val = document.createElement('div'); val.className = 'bar-val';
    val.textContent = fmtUSD(p.api_cost);
    val.style.color = 'var(--orange)';

    row.appendChild(label); row.appendChild(track); row.appendChild(val);
    comp.appendChild(row);

    const row2 = document.createElement('div'); row2.className = 'bar-row';
    const label2 = document.createElement('div'); label2.className = 'bar-label';
    label2.style.color = 'var(--text2)';
    label2.textContent = '';

    const track2 = document.createElement('div'); track2.className = 'bar-track';
    const planBar = document.createElement('div'); planBar.className = 'bar-fill';
    planBar.style.width = (p.plan_cost_usd / maxApi * 100) + '%';
    planBar.style.background = 'var(--accent)';
    planBar.textContent = D.locale.plan.plan_label;
    track2.appendChild(planBar);

    const val2 = document.createElement('div'); val2.className = 'bar-val';
    val2.textContent = fmtUSD(p.plan_cost_usd);
    val2.style.color = 'var(--accent2)';

    row2.appendChild(label2); row2.appendChild(track2); row2.appendChild(val2);
    comp.appendChild(row2);
  });

  // Charts
  const periodLabels = plan.periods.map(p => p.plan + ' (' + p.start.slice(5) + ')');

  new Chart(document.getElementById('chartPlanSavings'), {
    type: 'bar',
    data: {
      labels: periodLabels,
      datasets: [
        {label: D.locale.plan.api_cost_label, data: plan.periods.map(p => p.api_cost), backgroundColor: 'rgba(245,158,11,0.7)', borderRadius: 4},
        {label: D.locale.plan.plan_cost_label, data: plan.periods.map(p => p.plan_cost_usd), backgroundColor: 'rgba(99,102,241,0.7)', borderRadius: 4},
      ]
    },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8' } } },
      scales: { x: scaleDefaults.x, y: { ...scaleDefaults.y, title: { display: true, text: 'USD', color: '#64748b' } } } }
  });

  new Chart(document.getElementById('chartCostPerDay'), {
    type: 'bar',
    data: {
      labels: periodLabels,
      datasets: [{ label: D.locale.plan.api_cost_per_day_label, data: plan.periods.map(p => p.cost_per_day),
        backgroundColor: plan.periods.map(p => p.plan === 'Max' ? 'rgba(34,197,94,0.7)' : 'rgba(245,158,11,0.7)'),
        borderRadius: 4 }]
    },
    options: { responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: scaleDefaults.x, y: { ...scaleDefaults.y, title: { display: true, text: D.locale.plan.usd_per_day, color: '#64748b' } } } }
  });

  // Period table
  const tbody = document.getElementById('planTableBody');
  plan.periods.forEach(p => {
    const tr = document.createElement('tr');
    const cells = [
      {val: p.start + ' \u2013 ' + p.end, cls:''},
      {val: p.plan, cls:''},
      {val: p.total_days + ' (' + p.days_active + D.locale.plan.active_suffix + ')', cls:'num'},
      {val: fmtUSD(p.api_cost), cls:'num'},
      {val: fmtUSD(p.plan_cost_usd), cls:'num'},
      {val: fmtUSD(p.savings), cls:'num'},
      {val: p.roi_factor + 'x', cls:'num'},
      {val: String(p.sessions), cls:'num'},
      {val: fmt(p.messages), cls:'num'},
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      td.textContent = c.val;
      if (c.val.startsWith('$') && parseFloat(c.val.replace(/[^0-9.-]/g, '')) > 100) td.style.color = 'var(--green)';
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });

  // Total row
  const trTotal = document.createElement('tr');
  trTotal.style.fontWeight = '700';
  trTotal.style.borderTop = '2px solid var(--border)';
  const totalCells = [
    {val: D.locale.plan.total, cls:''},
    {val: '', cls:''},
    {val: '', cls:'num'},
    {val: fmtUSD(plan.total_api_cost), cls:'num'},
    {val: fmtUSD(plan.total_plan_cost), cls:'num'},
    {val: fmtUSD(plan.total_savings), cls:'num'},
    {val: plan.overall_roi + 'x', cls:'num'},
    {val: '', cls:'num'},
    {val: '', cls:'num'},
  ];
  totalCells.forEach(c => {
    const td = document.createElement('td');
    if (c.cls) td.className = c.cls;
    td.textContent = c.val;
    trTotal.appendChild(td);
  });
  tbody.appendChild(trTotal);
}

// ── Tab 6: Insights ───────────────────────────────────────────────────
function renderInsights() {
  const ins = D.insights;
  if (!ins) return;

  // Tool usage chart
  renderToolUsageChart();

  // Storage chart
  const storage = ins.storage || {};
  const storageItems = (storage.items || []).filter(s => s.size_mb >= 0.1);
  if (storageItems.length > 0) {
    new Chart(document.getElementById('chartStorage'), {
      type: 'doughnut',
      data: { labels: storageItems.map(s => s.name),
        datasets: [{ data: storageItems.map(s => s.size_mb),
          backgroundColor: storageItems.map((_, i) => 'hsl(' + (i * 40 + 200) + ',55%,50%)'), borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'right', labels: { color: '#94a3b8', padding: 8, font: { size: 11 } } },
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
      {val: p.short_name, cls: ''},
      {val: isEnabled ? D.locale.insights.active : D.locale.insights.inactive, cls: '', badge: isEnabled ? 'active' : 'inactive'},
      {val: p.version, cls: ''},
      {val: globalInstalls > 0 ? fmt(globalInstalls) : '-', cls: 'num'},
      {val: p.installed_at ? new Date(p.installed_at).toLocaleDateString(D.locale.locale_code) : '-', cls: ''},
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
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
  const configDiv = document.getElementById('configInfo');
  const settings = plugins.settings || {};
  const configItems = [
    {label: D.locale.insights.permission_mode, value: settings.permission_mode || '-'},
    {label: D.locale.insights.auto_updates, value: settings.auto_updates || '-'},
    {label: D.locale.insights.plugins_installed, value: String(installed.length)},
    {label: D.locale.insights.plugins_active, value: String(Object.values(enabled).filter(v => v).length)},
    {label: D.locale.insights.total_storage, value: (storage.total_mb || 0) + ' MB'},
    {label: D.locale.insights.transcripts, value: ((storage.items || []).find(s => s.name === 'projects/') || {}).size_mb + ' MB'},
    {label: D.locale.insights.debug_logs, value: ((storage.items || []).find(s => s.name === 'debug/') || {}).size_mb + ' MB'},
    {label: D.locale.insights.file_history_label, value: ((storage.items || []).find(s => s.name === 'file-history/') || {}).size_mb + ' MB'},
  ];
  const grid = document.createElement('div'); grid.className = 'config-grid';
  configItems.forEach(c => {
    const item = document.createElement('div'); item.className = 'config-item';
    const lbl = document.createElement('div'); lbl.className = 'ci-label'; lbl.textContent = c.label;
    const val = document.createElement('div'); val.className = 'ci-value'; val.textContent = c.value;
    item.appendChild(lbl); item.appendChild(val);
    grid.appendChild(item);
  });
  configDiv.appendChild(grid);

  // Plans table
  const plans = ins.plans || [];
  const plansTbody = document.getElementById('plansTableBody');
  plans.forEach(p => {
    const tr = document.createElement('tr');
    const cells = [
      {val: p.title, cls: ''},
      {val: new Date(p.created).toLocaleDateString(D.locale.locale_code), cls: ''},
      {val: String(p.lines), cls: 'num'},
      {val: String(p.size_kb), cls: 'num'},
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      td.textContent = c.val;
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
      '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--border)">' +
      '<span style="font-size:13px;color:var(--text)">' + escHtml(s.name) + '</span>' +
      '<span class="tool-tag" style="background:rgba(168,85,247,0.2);color:var(--purple)">' + s.count + 'x</span>' +
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
      return '<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;border-bottom:1px solid var(--border)">' +
        '<div><span class="model-badge" style="background:rgba(245,158,11,0.2);color:var(--orange);font-size:10px;margin-right:6px">' + escHtml(event) + '</span><span style="font-size:13px">' + escHtml(name) + '</span></div>' +
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

  // Error rate over time chart
  const dailyErrors = {};
  D.sessions.forEach(s => {
    if (!dailyErrors[s.date]) dailyErrors[s.date] = {errors:0, calls:0};
    dailyErrors[s.date].errors += s.error_count || 0;
    dailyErrors[s.date].calls += s.api_calls || 0;
  });
  const errDates = Object.keys(dailyErrors).sort();
  const errRates = errDates.map(d => dailyErrors[d].calls > 0 ? +(dailyErrors[d].errors / dailyErrors[d].calls * 100).toFixed(1) : 0);
  if (errDates.length > 0) {
    new Chart(document.getElementById('errorRateChart'), {
      type: 'line',
      data: {
        labels: errDates,
        datasets: [{ label: 'Error Rate (%)', data: errRates, borderColor: '#ef4444', backgroundColor: 'rgba(239,68,68,0.1)', fill:true, tension:0.3 }]
      },
      options: { responsive:true, plugins:{legend:{labels:{color:'#e2e8f0'}}}, scales:{ x:{ticks:{color:'#94a3b8',maxTicksLimit:15}}, y:{ticks:{color:'#94a3b8'}, beginAtZero:true} } }
    });
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
        datasets: [{ data: atd.map(d => d.count), backgroundColor: chartColors }]
      },
      options: { responsive:true, plugins:{ legend:{ position:'right', labels:{color:'#e2e8f0',font:{size:11}} } } }
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
        datasets: [{ data: tds.map(d => d.count), backgroundColor: 'rgba(99,102,241,0.7)', borderRadius:4 }]
      },
      options: { indexAxis:'y', responsive:true, plugins:{legend:{display:false}}, scales:{ x:{ticks:{color:'#94a3b8'}}, y:{ticks:{color:'#94a3b8',font:{size:10}}} } }
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

  // Task overview
  const taskEl = document.getElementById('taskOverview');
  const tasks = D.insights?.tasks || {};
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
    new Chart(document.getElementById('taskDonut'), {
      type: 'doughnut',
      data: { labels:['Completed','Pending','In Progress'], datasets:[{data:[tasks.completed,tasks.pending||0,tasks.in_progress||0], backgroundColor:['#22c55e','#94a3b8','#6366f1']}] },
      options: { cutout:'70%', responsive:true, plugins:{legend:{display:false}} }
    });
  } else {
    taskEl.innerHTML = '<div style="color:var(--text2)">No tasks found</div>';
  }

  // Error overview
  const errEl = document.getElementById('errorOverview');
  const catLabels = {'rejected':'Rejected','file_not_found':'File Not Found','edit_not_unique':'Edit Not Unique','edit_no_match':'Edit No Match','permission_denied':'Permission Denied','timeout':'Timeout','command_not_found':'Cmd Not Found','exit_code':'Exit Code Error','syntax_error':'Syntax Error','import_error':'Import Error','hook_error':'Hook Error','edit_failed':'Edit Failed','other':'Other'};
  const topCats = (es.by_category || []).slice(0, 5);
  errEl.innerHTML =
    '<div style="margin-bottom:12px"><span style="font-size:20px;font-weight:700;color:var(--red)">'+(es.total_errors||0)+'</span> errors / <span style="font-weight:600">'+(es.total_tool_calls||0)+'</span> tool calls</div>' +
    '<div style="font-size:12px;color:var(--text2);margin-bottom:8px">__L_agents_error_rate__: '+(es.error_rate||0)+'%</div>' +
    '<div style="margin-top:12px">' + topCats.map(c =>
      '<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border)">' +
        '<span style="font-size:12px">'+(catLabels[c.category]||c.category)+'</span>' +
        '<span style="font-size:12px;font-weight:600;color:var(--red)">'+c.count+'</span></div>'
    ).join('') + '</div>';

  // Error by category doughnut
  const ebc = es.by_category || [];
  if (errorByCatChartInstance) errorByCatChartInstance.destroy();
  if (ebc.length > 0) {
    const errColors = ['#ef4444','#f97316','#eab308','#22c55e','#06b6d4','#6366f1','#a855f7','#ec4899','#64748b','#78716c','#84cc16','#14b8a6','#f43f5e'];
    errorByCatChartInstance = new Chart(document.getElementById('errorByCategoryChart'), {
      type: 'doughnut',
      data: {
        labels: ebc.map(e => catLabels[e.category] || e.category),
        datasets: [{ data: ebc.map(e => e.count), backgroundColor: errColors }]
      },
      options: { responsive:true, plugins:{ legend:{ position:'right', labels:{color:'#e2e8f0',font:{size:11}} } } }
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
        datasets: [{ data: ebt.map(e => e.count), backgroundColor: 'rgba(239,68,68,0.7)', borderRadius:4 }]
      },
      options: { indexAxis:'y', responsive:true, plugins:{legend:{display:false}}, scales:{ x:{ticks:{color:'#94a3b8'}}, y:{ticks:{color:'#94a3b8',font:{size:11}}} } }
    });
  }
}

// ── Sortable Tables ────────────────────────────────────────────────────
document.querySelectorAll('.sortable th[data-sort]').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.dataset.sort;
    const table = th.closest('table');
    const current = th.classList.contains('sort-asc') ? 'asc' : th.classList.contains('sort-desc') ? 'desc' : null;
    table.querySelectorAll('th').forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
    const dir = current === 'desc' ? 'asc' : 'desc';
    th.classList.add('sort-' + dir);
    renderProjectTable(key, dir);
  });
});

// ── Filter events ──────────────────────────────────────────────────────
document.getElementById('filterProject').addEventListener('change', () => { sessionPage = 0; renderSessionList(); });
document.getElementById('filterSource').addEventListener('change', () => { sessionPage = 0; renderSessionList(); });
document.getElementById('filterSort').addEventListener('change', () => { sessionPage = 0; renderSessionList(); });
document.getElementById('filterSearch').addEventListener('input', () => { sessionPage = 0; renderSessionList(); });
document.getElementById('hideEmptySessions').addEventListener('change', () => { applyFilter(currentDays); });

// ── Init ───────────────────────────────────────────────────────────────
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
renderInsights();
renderAgentsTab();

// F2 Anonymization mode
const anonMap = {};
let anonCounter = 0;
function anonName(name) {
  if (!anonMap[name]) { anonCounter++; anonMap[name] = 'Project ' + anonCounter; }
  return anonMap[name];
}
document.addEventListener('keydown', function(e) {
  if (e.key === 'F2') {
    e.preventDefault();
    anonMode = !anonMode;
    document.body.classList.toggle('anon-mode', anonMode);
    // Re-render everything via applyFilter (handles cleanup)
    applyFilter(currentDays);
    // Show/hide notification
    let note = document.getElementById('anonNote');
    if (!note) {
      note = document.createElement('div');
      note.id = 'anonNote';
      note.style.cssText = 'position:fixed;top:12px;right:12px;padding:8px 16px;border-radius:8px;font-size:12px;font-weight:600;z-index:9999;transition:opacity 0.3s;';
      document.body.appendChild(note);
    }
    note.style.background = anonMode ? 'var(--green)' : 'var(--red)';
    note.style.color = 'white';
    note.textContent = anonMode ? 'Anonymization ON' : 'Anonymization OFF';
    note.style.opacity = '1';
    setTimeout(() => { note.style.opacity = '0'; }, 2000);
  }
});


// ── Variant-C top bar wiring ──────────────────────────────────────
(function() {
  // Theme handling
  function applyVcTheme(theme) {
    document.documentElement.classList.remove('theme-light', 'theme-dark');
    if (theme === 'light' || theme === 'dark') {
      document.documentElement.classList.add('theme-' + theme);
    }
    const btn = document.getElementById('vcThemeToggle');
    if (btn) {
      const isDark = theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches);
      btn.innerHTML = isDark ? '&#9790;' : '&#9737;';
    }
    if (typeof setupVcChartDefaults === 'function') setupVcChartDefaults();
  }
  const savedTheme = localStorage.getItem('vc-theme') || 'system';
  applyVcTheme(savedTheme);
  document.getElementById('vcThemeToggle')?.addEventListener('click', () => {
    const current = localStorage.getItem('vc-theme') || 'system';
    const next = current === 'system' ? 'light' : (current === 'light' ? 'dark' : 'system');
    localStorage.setItem('vc-theme', next);
    applyVcTheme(next);
  });
  // React to system pref change while in 'system' mode
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    const t = localStorage.getItem('vc-theme') || 'system';
    if (t === 'system') applyVcTheme(t);
  });

  // Language toggle (config-based, alert is honest)
  document.getElementById('vcLangToggle')?.addEventListener('click', () => {
    alert('Language is set in config.json — edit "language" and re-run extract_stats.py to switch.');
  });

  // UTC time
  function updateVcUtc() {
    const el = document.getElementById('vcUtcTime');
    if (!el) return;
    const now = new Date();
    el.textContent = now.toISOString().slice(11, 19) + ' UTC';
  }
  updateVcUtc();
  setInterval(updateVcUtc, 1000);

  // Populate USER / PLAN from DASHBOARD_DATA
  const d = (typeof D !== 'undefined') ? D : null;
  if (d) {
    const userEl = document.getElementById('vcTopUser');
    const planEl = document.getElementById('vcTopPlan');
    if (userEl) userEl.textContent = (d.config && (d.config.display_name || d.account?.name)) || (d.account && d.account.name) || '-';
    if (planEl) {
      const plan = d.account?.plan || (d.config && d.config.plan) || (d.plan_summary && d.plan_summary.current_plan) || '-';
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
    btn.addEventListener('click', () => {
      tabsEl.querySelectorAll('.vc-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      // Drive legacy switchTab via the corresponding hidden tab-btn (simpler than calling switchTab(id, btn) which expects the legacy btn)
      const legacy = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.textContent === t.label);
      if (legacy) {
        switchTab(t.id, legacy);
      } else {
        // Fallback: directly toggle tab-content
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        const target = document.getElementById('tab-' + t.id);
        if (target) target.classList.add('active');
      }
    });
    tabsEl.appendChild(btn);
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
})();
