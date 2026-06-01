/* ============================================================
   claude.stats redesign — shared data layer
   Real headline figures pulled from the current-state screenshots;
   daily series are synthesized deterministically to match shape.
   ============================================================ */

// ---- Model color families (earth-tone triad, version-stepped) ----
// Opus = terracotta, Sonnet = sage, Haiku = ochre.
// Lighter step = newer version within the family.
const MODEL_COLORS = {
  'Opus 4.8':   '#e0926f',
  'Opus 4.7':   '#c4623f',
  'Opus 4.6':   '#a8442a',
  'Opus 4.5':   '#7d2f1d',
  'Sonnet 4.6': '#7aa589',
  'Sonnet 4.5': '#4f7a5f',
  'Haiku 4.5':  '#cda43f',
};
const MODEL_ORDER = ['Haiku 4.5','Opus 4.5','Opus 4.6','Opus 4.7','Opus 4.8','Sonnet 4.5','Sonnet 4.6'];

// ---- Headline KPIs (Token & API Value) ----
const KPI = {
  apiEquivalent: '$8,725.39',
  savingsPct: '90.4%',
  paid: '$839.33',
  sessions: '840',
  avgDuration: '837m',
  messages: '62,708',
  perSession: '75',
  outputTokens: '35.74M',
  inputTokens: '1.87M',
  cacheHit: '96.6%',
  cacheRead: '11.59B',
  idleTokens: '123.9M',
  idleCost: '$464.72',
  idleSessions: '336',
};

// ---- Model detail table ----
const MODEL_DETAIL = [
  ['Opus 4.7',   '$4,319.54', '23.7M',  '160.4K', '5.6B',   '27,710'],
  ['Opus 4.6',   '$3,235.87', '6.3M',   '468.2K', '4.3B',   '32,891'],
  ['Opus 4.8',   '$447.54',   '2.8M',   '425.6K', '395.9M', '1,859', true],
  ['Opus 4.5',   '$337.05',   '52.7K',  '229.3K', '391.3M', '4,728'],
  ['Sonnet 4.6', '$292.27',   '2.2M',   '138.0K', '518.9M', '12,765'],
  ['Haiku 4.5',  '$75.37',    '547.9K', '416.4K', '338.4M', '6,368'],
  ['Sonnet 4.5', '$17.74',    '4.5K',   '33.4K',  '28.9M',  '559'],
];

// ---- Token-type value (USD) ----
const TOKEN_TYPE = {
  labels: ['Input', 'Output', 'Cache Read', 'Cache Write'],
  values: [124, 902, 5498, 2201],
};

// ---- Deterministic RNG so charts are stable across reloads ----
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---- Daily series (every ~2 days from 2026-01-22 → 2026-06-01) ----
function buildDaily() {
  const rnd = mulberry32(42);
  const labels = [];
  const start = new Date(2026, 0, 22);
  const N = 64;
  // Per-model daily arrays
  const series = {};
  MODEL_ORDER.forEach(m => series[m] = []);
  let cum = 0;
  const cumArr = [];
  for (let i = 0; i < N; i++) {
    const d = new Date(start.getTime());
    d.setDate(start.getDate() + i * 2);
    labels.push(`${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`);

    const phase = i / N; // 0..1 over the range
    // spikiness
    const spike = rnd() < 0.22 ? (1.6 + rnd() * 1.6) : (rnd() < 0.5 ? 0.15 : 0.6);
    let dayTotal = spike * (40 + phase * 120) * (0.4 + rnd());

    // model mix shifts over time: early Opus4.6/4.7, late Opus4.8 + Sonnet4.6
    const mix = {
      'Opus 4.6':   Math.max(0, 0.55 - phase * 0.5),
      'Opus 4.7':   Math.max(0, 0.25 + phase * 0.25 - Math.max(0, phase - 0.85) * 1.5),
      'Opus 4.8':   Math.max(0, (phase - 0.78) * 3.2),
      'Opus 4.5':   Math.max(0, 0.12 - phase * 0.12) + (rnd() < 0.1 ? 0.05 : 0),
      'Sonnet 4.6': Math.max(0, (phase - 0.55) * 0.5) * (rnd() < 0.6 ? 1 : 0),
      'Sonnet 4.5': rnd() < 0.08 ? 0.06 : 0,
      'Haiku 4.5':  rnd() < 0.5 ? 0.02 : 0,
    };
    const mixSum = Object.values(mix).reduce((a, b) => a + b, 0) || 1;
    MODEL_ORDER.forEach(m => {
      const v = dayTotal * (mix[m] / mixSum);
      const val = Math.round(v * 10) / 10;
      series[m].push(val);
    });
    const realDayTotal = MODEL_ORDER.reduce((a, m) => a + series[m][i], 0);
    cum += realDayTotal;
    cumArr.push(Math.round(cum));
  }
  // scale cumulative to land near 8725
  const scale = 8725 / (cumArr[cumArr.length - 1] || 1);
  const cumScaled = cumArr.map(v => Math.round(v * scale));
  return { labels, series, cumulative: cumScaled };
}
const DAILY = buildDaily();

// ---- Cache efficiency daily (%) ----
function buildCacheEff() {
  const rnd = mulberry32(7);
  return DAILY.labels.map(() => Math.round((78 + rnd() * 20) * 10) / 10);
}
const CACHE_EFF = buildCacheEff();

// ---- Insights: doughnuts & bars ----
const OUTPUT_BY_TOOL = {
  labels: ['Edit', 'Write', 'Bash', 'Read', 'MultiEdit', 'Task', 'Grep', 'NotebookEdit', 'WebFetch', 'Other'],
  values: [28, 19, 14, 11, 8, 7, 5, 3, 2, 3],
};
const OUTPUT_BY_ACTIVITY = {
  labels: ['Coding', 'Debugging', 'Refactor', 'Planning', 'Research', 'Writing', 'Review', 'Other'],
  values: [34, 18, 12, 11, 9, 7, 6, 3],
};
const TOOL_USAGE = {
  labels: ['Read', 'Edit', 'Bash', 'Write', 'Grep', 'Glob', 'TodoWrite', 'Task', 'MultiEdit',
           'mcp__memory', 'WebFetch', 'mcp__search', 'NotebookEdit', 'mcp__fetch', 'WebSearch'],
  values: [40212, 31946, 19736, 11494, 10377, 6920, 5426, 4761, 4110, 3402, 2980, 2114, 1880, 1530, 980],
};
const STORAGE = {
  labels: ['claude-stats', 'aeterna-labs', 'OBSIDIAN', 'beautyland', 'scripta', 'collector', 'open-brain', 'Other'],
  values: [34.17, 16.19, 12.09, 10.37, 8.89, 7.39, 5.14, 22.6],
};
const SUBAGENT_TYPES = {
  labels: ['general-purpose', 'explore', 'code-reviewer', 'frontend-design', 'researcher', 'debugger', 'Other'],
  values: [712, 486, 318, 244, 180, 132, 97],
};
const AGENT_DESCRIPTIONS = {
  labels: ['Implement feature in module', 'Investigate failing test', 'Review diff for correctness',
           'Research approach + tradeoffs', 'Refactor component', 'Write migration', 'Audit dependencies'],
  values: [241, 198, 167, 142, 118, 96, 74],
};
const ERROR_RATE = (() => {
  const rnd = mulberry32(99);
  return DAILY.labels.map((_, i) => {
    const base = 1.5 + Math.sin(i / 4) * 0.8;
    const spike = rnd() < 0.15 ? rnd() * 5 : 0;
    return Math.round((Math.max(0.2, base + spike)) * 10) / 10;
  });
})();
const ERRORS_BY_CATEGORY = {
  labels: ['File not found', 'Type error', 'Rate limit', 'Timeout', 'Permission', 'Syntax', 'Network', 'Other'],
  values: [624, 487, 342, 286, 201, 178, 134, 90],
};
const ERRORS_BY_TOOL = {
  labels: ['Bash', 'Edit', 'Read', 'mcp__fetch', 'Write', 'Task', 'Grep'],
  values: [812, 540, 388, 246, 201, 96, 59],
};

// ---- Plan & billing-ish KPI (used lightly) ----
const INSIGHT_KPI = {
  cacheRatio: '11.68',
  cacheWrite: '406.0M',
  cacheSavings: '$49,932.41',
  agentInvocations: '2,169',
  agentTasks: '86',
  agentErrorRate: '2.7%',
  taskCompletion: '64%',
  totalErrors: '2,342',
  fileSnapshots: '9,382',
  storageTotal: '218.8 MB',
  snapshotSessions: '573',
  completionRate: '79%',
};

// ---- Tools & Plugins table ----
const PLUGINS = [
  ['fj-mcp', 'active', '2.0.8', '20,381', '12/24/2025'],
  ['commit-craft', 'active', '1.4.2', '194,113', '12/24/2025'],
  ['frontend-design', 'active', '0.9.1', '735,990', '12/24/2025'],
  ['github', 'active', '2.6.0', '290,557', '12/24/2025'],
  ['superpowers', 'active', '3.1.7', '447,140', '12/24/2025'],
  ['memory-mcp', 'active', '0.4.0', '210,113', '12/24/2025'],
  ['claude-simplifier', 'active', '1.0.0', '256,407', '12/24/2025'],
  ['security-guidance', 'beta', '0.0.4', '132,079', '01/12/2026'],
  ['context-mgmt', 'active', '1.0.0', '200,000', '01/12/2026'],
  ['research-kit', 'active', '1.8.1', '25,511', '01/12/2026'],
];

// ---- Workflows ----
const PLANS = [
  ['Prompt-consulting in admin dashboard', '04/14/2026', '353'],
  ['Briefing-document for content output', '04/14/2026', '119'],
  ['Permissions overview structure', '04/14/2026', '17'],
  ['Beautyland portal — UI/X passes', '04/14/2026', '111'],
  ['Persona-builder generator integration', '04/14/2026', '101'],
  ['URL routing experiment — phase 2', '04/14/2026', '60'],
];
const SKILLS = [
  ['superpowers:brainstorming', '1453'], ['superpowers:writing-slides', '986'],
  ['frontend-design', '742'], ['superpowers:systematic-debugging', '655'],
  ['superpowers:visual-design', '498'], ['code-review:commit', '441'],
  ['arcade', '372'], ['superpowers:research', '318'], ['git-ops', '244'],
  ['wireframe', '180'], ['xlsx', '132'], ['pdf', '96'],
];
const GIT_OPS = [['Commits', '480'], ['Pushes', '162'], ['Pull requests', '34']];
