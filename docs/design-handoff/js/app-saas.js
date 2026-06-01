/* ============================================================
   app-saas.js — single-direction SaaS controller.
   Tabs, theme, Insights sub-nav, table/heatmap rendering,
   theme-aware charts, hooks for the Tweaks panel.
   ============================================================ */

const SCREEN_CHARTS = {
  hero: ['c-apiByDay', 'c-cumulative', 'c-tokenType'],
  plan: ['c-savingsByPeriod', 'c-avgPerDay'],
  activity: ['c-dailyActivity', 'c-hourly', 'c-weekday'],
  sessions: [],
};
const INS_SUB_CHARTS = {
  cache: ['c-outputByTool', 'c-outputByActivity', 'c-cacheEff'],
  tools: ['c-toolUsage'],
  workflows: [], storage: ['c-storage'], environment: [],
  agents: ['c-subagentTypes', 'c-agentDescriptions'],
  errors: ['c-errorRate', 'c-errorsByCategory', 'c-errorsByTool'],
};

const SAAS_DEFAULT = { screen: 'hero', theme: 'light', sub: 'cache' };
let S = loadSaasState();
let SESSION_SORT = { key: null, dir: 1 };

function loadSaasState() {
  try { return Object.assign({}, SAAS_DEFAULT, JSON.parse(localStorage.getItem('claudestats-saas') || '{}')); }
  catch (e) { return Object.assign({}, SAAS_DEFAULT); }
}
function saveSaasState() { localStorage.setItem('claudestats-saas', JSON.stringify(S)); }

/* ---------- helpers ---------- */
function el(tag, cls, html) { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
function td(label, html, cls) {
  const t = el('td', cls, html); t.setAttribute('data-label', label); return t;
}
function parseNum(s) {
  if (s == null) return -Infinity;
  let str = String(s).replace(/[$€,\s]/g, '');
  if (str === '–' || str === '-' || str === '') return -1;
  const m = str.match(/^([\d.]+)([KMB]?)/i);
  if (!m) return parseFloat(str) || 0;
  const mult = { '': 1, K: 1e3, M: 1e6, B: 1e9 }[m[2].toUpperCase()] || 1;
  return parseFloat(m[1]) * mult;
}

/* ---------- table / widget rendering ---------- */
function renderModelDetail() {
  const tb = document.getElementById('tb-model'); if (!tb) return; tb.innerHTML = '';
  MODEL_DETAIL.forEach(r => {
    const tr = el('tr');
    const sw = `<span class="swatch" style="background:${MODEL_COLORS[r[0]]}"></span>`;
    const est = r[6] ? '<span class="est">est.</span>' : '';
    tr.appendChild(td('Model', `${sw}${r[0]}${est}`, 'primary'));
    tr.appendChild(td('API Value', r[1]));
    tr.appendChild(td('Output', r[2]));
    tr.appendChild(td('Input', r[3]));
    tr.appendChild(td('Cache Read', r[4]));
    tr.appendChild(td('API Calls', r[5]));
    tb.appendChild(tr);
  });
}
function renderPeriod() {
  const tb = document.getElementById('tb-period'); if (!tb) return; tb.innerHTML = '';
  const cols = ['Period', 'Plan', 'Days', 'API Equiv.', 'Plan Cost', 'Savings', 'ROI', 'Sessions', 'Msgs.'];
  PERIOD_DETAIL.forEach(r => {
    const tr = el('tr');
    r.forEach((c, i) => {
      const cls = i === 5 && !c.startsWith('-') ? 'pos-cell' : (i === 0 ? 'primary' : '');
      tr.appendChild(td(cols[i], c, cls));
    });
    tb.appendChild(tr);
  });
  const tr = el('tr'); tr.style.fontWeight = '700';
  PERIOD_TOTAL.forEach((c, i) => tr.appendChild(td(cols[i], c, i === 0 ? 'primary' : '')));
  tb.appendChild(tr);
}
function renderRecTable(id, rows, total) {
  const tb = document.getElementById(id); if (!tb) return; tb.innerHTML = '';
  const cols = ['Cycle', 'Pro', 'Max 5x', 'Max 20x'];
  rows.forEach(r => {
    const tr = el('tr');
    r.forEach((c, i) => {
      const hit = i > 0 && c !== '0';
      tr.appendChild(td(cols[i], c, hit ? 'cell-err' : (i === 0 ? '' : 'muted-cell')));
    });
    tb.appendChild(tr);
  });
  const tr = el('tr'); tr.style.fontWeight = '700';
  total.forEach((c, i) => tr.appendChild(td(cols[i], c)));
  tb.appendChild(tr);
}
function renderProjects() {
  const tb = document.getElementById('tb-projects'); if (!tb) return; tb.innerHTML = '';
  const cols = ['Project', 'Source', 'Sessions', 'Messages', 'API Value', 'Output', 'File Size'];
  PROJECTS.forEach(r => {
    const tr = el('tr');
    tr.appendChild(td(cols[0], `<span class="cell-link">${r[0]}</span>`, 'primary'));
    tr.appendChild(td(cols[1], `<span class="tag-source">${r[1]}</span>`));
    tr.appendChild(td(cols[2], r[2]));
    tr.appendChild(td(cols[3], r[3]));
    tr.appendChild(td(cols[4], r[4], 'cell-cost'));
    tr.appendChild(td(cols[5], r[5]));
    tr.appendChild(td(cols[6], r[6] + ' MB'));
    tb.appendChild(tr);
  });
}
function renderSessions() {
  const tb = document.getElementById('tb-sessions'); if (!tb) return; tb.innerHTML = '';
  let rows = SESSIONS.slice();
  if (SESSION_SORT.key != null) {
    const k = SESSION_SORT.key;
    rows.sort((a, b) => (parseNum(a[k]) - parseNum(b[k])) * SESSION_SORT.dir);
  }
  const cols = ['Date', 'Project', 'Chat', 'Model', 'Duration', 'Messages', 'User', 'API Calls', 'Tokens', 'Cost', 'Agents', 'Errors'];
  rows.forEach(r => {
    const tr = el('tr');
    tr.appendChild(td('Date', r[0], 'primary'));
    tr.appendChild(td('Project', `<span class="cell-link">${r[1]}</span>`));
    tr.appendChild(td('Chat', '<span class="chat-btn">›</span>'));
    const ctx = r[3] ? '<span class="badge-ctx">1M</span>' : '';
    tr.appendChild(td('Model', `<span class="badge-model">${r[2]}</span>${ctx}`));
    tr.appendChild(td('Duration', r[4] + ' min'));
    tr.appendChild(td('Messages', r[5]));
    tr.appendChild(td('User', r[6]));
    tr.appendChild(td('API Calls', r[7]));
    tr.appendChild(td('Tokens', r[8]));
    tr.appendChild(td('Cost', r[9], 'cell-cost'));
    tr.appendChild(td('Agents', r[10]));
    tr.appendChild(td('Errors', r[11], r[11] !== '–' ? 'cell-err' : 'muted-cell'));
    tb.appendChild(tr);
  });
}
function renderPlugins() {
  const tb = document.getElementById('tb-plugins'); if (!tb) return; tb.innerHTML = '';
  const cols = ['Plugin', 'Status', 'Version', 'Tokens', 'Installed'];
  PLUGINS.forEach(r => {
    const tr = el('tr');
    tr.appendChild(td(cols[0], r[0], 'primary'));
    tr.appendChild(td(cols[1], `<span class="tag-status ${r[1]}">${r[1]}</span>`));
    tr.appendChild(td(cols[2], r[2]));
    tr.appendChild(td(cols[3], r[3]));
    tr.appendChild(td(cols[4], r[4]));
    tb.appendChild(tr);
  });
}
function renderPlans() {
  const tb = document.getElementById('tb-plans'); if (!tb) return; tb.innerHTML = '';
  const cols = ['Title', 'Created', 'Count'];
  PLANS.forEach(r => {
    const tr = el('tr');
    tr.appendChild(td(cols[0], r[0], 'primary'));
    tr.appendChild(td(cols[1], r[1]));
    tr.appendChild(td(cols[2], r[2]));
    tb.appendChild(tr);
  });
}
function renderWorkflowsAside() {
  const chips = document.getElementById('skills-chips');
  if (chips) { chips.innerHTML = ''; SKILLS.forEach(s => chips.appendChild(el('span', 'chip', `${s[0]} <span class="n">${s[1]}</span>`))); }
  const git = document.getElementById('gitops');
  if (git) { git.innerHTML = ''; GIT_OPS.forEach(g => git.appendChild(el('div', 'row', `<span class="k">${g[0]}</span><span class="v">${g[1]}</span>`))); }
}
function renderHeatmap() {
  const root = document.getElementById('heatmap'); if (!root) return; root.innerHTML = '';
  const months = el('div', 'heatmap-months');
  months.style.gridTemplateColumns = `repeat(${HEATMAP.length}, 14px)`;
  HEATMAP_MONTHS.forEach((m, i) => { const s = el('span', '', m); s.style.gridColumn = `${i * 4 + 1}`; months.appendChild(s); });
  const body = el('div', 'heatmap-body');
  const days = el('div', 'heatmap-days');
  ['', 'Mon', '', 'Wed', '', 'Fri', ''].forEach(d => days.appendChild(el('span', '', d)));
  const grid = el('div', 'heatmap-grid');
  HEATMAP.forEach(col => col.forEach(lvl => grid.appendChild(el('div', `hm-cell l${lvl}`))));
  body.appendChild(days); body.appendChild(grid);
  root.appendChild(months); root.appendChild(body);
}
function renderLimitEvents() {
  const root = document.getElementById('limit-events'); if (!root) return; root.innerHTML = '';
  LIMIT_EVENTS.forEach(row => {
    const r = el('div', 'le-row');
    r.appendChild(el('div', 'le-label', row.label));
    const track = el('div', 'le-track');
    row.events.forEach(ev => { const e = el('div', `le-ev ${ev.t === 'explicit' ? 'explicit' : 'fp'}`); e.style.left = ev.p + '%'; track.appendChild(e); });
    r.appendChild(track);
    r.appendChild(el('div', 'le-count' + (row.count ? ' has' : ''), row.count + ' events'));
    root.appendChild(r);
  });
}
function renderAll() {
  renderModelDetail(); renderPeriod();
  renderRecTable('tb-rec5h', REC_5H, REC_5H_TOTAL);
  renderRecTable('tb-recweek', REC_WEEK, REC_WEEK_TOTAL);
  renderProjects(); renderSessions(); renderPlugins(); renderPlans();
  renderWorkflowsAside(); renderHeatmap(); renderLimitEvents();
}

/* ---------- charts ---------- */
function currentChartIds() {
  if (S.screen === 'insights') return INS_SUB_CHARTS[S.sub] || [];
  return SCREEN_CHARTS[S.screen] || [];
}
function rebuildVisibleCharts() {
  destroyAllCharts();
  setTimeout(() => buildCharts(currentChartIds()), 40);
}
window.csRebuildCharts = rebuildVisibleCharts;

/* ---------- apply state ---------- */
function applySaas() {
  const wrap = document.querySelector('.appwrap');
  wrap.setAttribute('data-theme', S.theme);
  document.getElementById('themeLabel').textContent = S.theme === 'light' ? 'Light' : 'Dark';
  document.getElementById('themeIcon').textContent = S.theme === 'light' ? '◐' : '◑';

  document.querySelectorAll('.screen').forEach(s => { s.hidden = s.getAttribute('data-screen') !== S.screen; });
  document.querySelectorAll('.mainnav .tab').forEach(t => t.classList.toggle('active', t.getAttribute('data-screen') === S.screen));

  if (S.screen === 'insights') {
    document.querySelectorAll('.subsection').forEach(sec => { sec.hidden = sec.getAttribute('data-sub') !== S.sub; });
    document.querySelectorAll('.subnav button').forEach(b => b.classList.toggle('on', b.getAttribute('data-sub') === S.sub));
  }
  rebuildVisibleCharts();
  saveSaasState();
  window.scrollTo({ top: 0 });
}
function setS(patch) { Object.assign(S, patch); applySaas(); }

/* ---------- wire up ---------- */
document.addEventListener('DOMContentLoaded', () => {
  renderAll();

  document.querySelectorAll('.mainnav .tab').forEach(t =>
    t.addEventListener('click', () => setS({ screen: t.getAttribute('data-screen') })));

  document.querySelectorAll('.subnav button').forEach(b =>
    b.addEventListener('click', () => setS({ sub: b.getAttribute('data-sub') })));

  document.getElementById('themeToggle').addEventListener('click', () =>
    setS({ theme: S.theme === 'light' ? 'dark' : 'light' }));

  // session column sorting
  document.querySelectorAll('#tb-sessions');
  const sortMap = { Date: 0, Duration: 4, Messages: 5, Tokens: 8, Cost: 9 };
  document.querySelectorAll('.screen[data-screen="sessions"] th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const key = sortMap[th.textContent.trim().split(' ')[0]];
      if (key == null) return;
      SESSION_SORT.dir = (SESSION_SORT.key === key) ? -SESSION_SORT.dir : -1;
      SESSION_SORT.key = key;
      renderSessions();
    });
  });

  applySaas();

  let rt;
  window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(rebuildVisibleCharts, 200); });
});
