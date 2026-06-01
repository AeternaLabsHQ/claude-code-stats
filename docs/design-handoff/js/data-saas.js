/* ============================================================
   data-saas.js — additional datasets for the full SaaS build:
   Plan & Billing, Activity & Projects, Sessions.
   Figures taken from the current-state screenshots.
   ============================================================ */

// ---------- PLAN & BILLING ----------
const PLAN = {
  current: 'Max 20x', perMonthEur: '214.20 €', perMonthUsd: '$200.00',
  paidSoFar: '873.48 €', apiCostTotal: '9,344.14 €', totalSavings: '8,470.66 €', roi: '10.7x',
  period: '2026-05-27 – 2026-06-27', day: '6 / 31', pct: 19,
  apiCostSoFar: '543.74 €', projected: '2,809.32 €', savingsSoFar: '329.54 €',
  periodRoi: '2.5x', sessions: '21', messages: '2,234', avgDay: '90.62 €',
};
const SAVINGS_PERIODS = {
  labels: ['Pro (annual)', 'Max 5x · 01', 'Max 5x · 02', 'Max 5x · 03', 'Max 5x · 04', 'Max 20x · 04', 'Max 20x · 05'],
  apiEquivalent: [10.56, 743.36, 842.82, 2788.87, 891.69, 3523.10, 543.74],
  planCost: [16.68, 107.10, 107.10, 107.10, 107.10, 214.20, 214.20],
  avgPerDay: [5.3, 33.8, 64.8, 96.2, 222.9, 135.5, 90.6],
};
const PERIOD_DETAIL = [
  ['2025-12-27 – 2026-01-22', 'Pro (annual)', '27 (2 active)', '10.56 €', '16.68 €', '-6.12 €', '0.6x', '6', '192'],
  ['2026-01-23 – 2026-02-22', 'Max 5x', '31 (22 active)', '743.36 €', '107.10 €', '636.26 €', '6.9x', '63', '7,538'],
  ['2026-02-23 – 2026-03-22', 'Max 5x', '28 (13 active)', '842.82 €', '107.10 €', '735.72 €', '7.9x', '42', '5,706'],
  ['2026-03-23 – 2026-04-22', 'Max 5x', '31 (29 active)', '2,788.87 €', '107.10 €', '2,681.77 €', '26x', '382', '22,252'],
  ['2026-04-23 – 2026-04-26', 'Max 5x', '4 (4 active)', '891.69 €', '107.10 €', '784.59 €', '8.3x', '43', '5,693'],
  ['2026-04-27 – 2026-05-26', 'Max 20x', '30 (26 active)', '3,523.10 €', '214.20 €', '3,308.90 €', '16.4x', '301', '19,093'],
  ['2026-05-27 – 2026-06-01', 'Max 20x', '6 (6 active)', '543.74 €', '214.20 €', '329.54 €', '2.5x', '21', '2,234'],
];
const PERIOD_TOTAL = ['Total', '', '', '9,344.14 €', '873.48 €', '8,470.66 €', '10.7x', '', ''];
const LIMIT_EVENTS = [
  { label: 'Pro (annual) · 2025-12', events: [], count: 0 },
  { label: 'Max 5x · 2026-01', events: [{ p: 38, t: 'explicit' }, { p: 60, t: 'fp' }, { p: 72, t: 'fp' }], count: 3 },
  { label: 'Max 5x · 2026-02', events: [{ p: 88, t: 'explicit' }], count: 1 },
  { label: 'Max 5x · 2026-03', events: [{ p: 10, t: 'explicit' }, { p: 22, t: 'explicit' }, { p: 40, t: 'fp' }, { p: 70, t: 'fp' }, { p: 82, t: 'explicit' }], count: 12 },
  { label: 'Max 5x · 2026-04', events: [{ p: 30, t: 'explicit' }], count: 2 },
  { label: 'Max 20x · 2026-04', events: [], count: 0 },
  { label: 'Max 20x · 2026-05', events: [], count: 0 },
];
const REC_5H = [
  ['Pro (annual) · 2025-12', '1', '0', '0'],
  ['Max 5x · 2026-01', '31', '1', '0'],
  ['Max 5x · 2026-02', '23', '5', '0'],
  ['Max 5x · 2026-03', '67', '24', '2'],
  ['Max 5x · 2026-04', '13', '9', '0'],
  ['Max 20x · 2026-04', '67', '35', '4'],
  ['Max 20x · 2026-05', '11', '8', '0'],
];
const REC_5H_TOTAL = ['Total across all cycles', '213', '82', '6'];
const REC_WEEK = [
  ['Pro (annual) · 2025-12', '1', '0', '0'],
  ['Max 5x · 2026-01', '3', '0', '0'],
  ['Max 5x · 2026-02', '2', '1', '0'],
  ['Max 5x · 2026-03', '5', '5', '1'],
  ['Max 5x · 2026-04', '0', '0', '0'],
  ['Max 20x · 2026-04', '5', '5', '2'],
  ['Max 20x · 2026-05', '0', '0', '0'],
];
const REC_WEEK_TOTAL = ['Total across all cycles', '16', '11', '3'];

// ---------- ACTIVITY & PROJECTS ----------
// Contribution heatmap: 26 weeks × 7 days, intensity 0..4
const HEATMAP = (() => {
  const rnd = mulberry32(2026);
  const weeks = 26;
  const grid = [];
  for (let w = 0; w < weeks; w++) {
    const col = [];
    const wk = w / weeks;
    for (let d = 0; d < 7; d++) {
      const weekend = d >= 5;
      let lvl = 0;
      const r = rnd();
      const bias = 0.25 + wk * 0.5;
      if (r < (weekend ? 0.55 : 0.18)) lvl = 0;
      else if (r < 0.5) lvl = 1;
      else if (r < 0.72) lvl = 2;
      else if (r < 0.9) lvl = Math.min(4, 2 + Math.round(bias));
      else lvl = 4;
      col.push(lvl);
    }
    grid.push(col);
  }
  return grid;
})();
const HEATMAP_MONTHS = ['Dec', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'];

// Daily activity (reuse the date labels; messages bar + sessions line)
const DAILY_ACTIVITY = (() => {
  const rnd = mulberry32(11);
  const messages = [], sessions = [];
  DAILY.labels.forEach((_, i) => {
    const spike = rnd() < 0.2 ? 2.2 : 1;
    messages.push(Math.round((200 + rnd() * 900) * spike));
    sessions.push(Math.round(2 + rnd() * 16 * (rnd() < 0.1 ? 3 : 1)));
  });
  return { messages, sessions };
})();
// Hour-of-day distribution (0..23)
const HOURLY = (() => {
  const rnd = mulberry32(5);
  const base = [2, 1, 1, 0, 0, 1, 2, 4, 7, 9, 11, 10, 9, 11, 13, 12, 10, 9, 8, 9, 11, 10, 7, 4];
  return base.map(v => Math.round(v * 1000 * (0.8 + rnd() * 0.4)));
})();
const WEEKDAY = {
  labels: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
  values: [6100, 11200, 13400, 10700, 10800, 5400, 6200],
};
const PROJECTS = [
  ['projects/research', 'cortex·andie', '39', '4,728', '$998.21', '1.6M', '11.63'],
  ['Projects/aeterna-labs', 'galates·andie', '28', '3,987', '$908.79', '4.0M', '8.89'],
  ['projects/zrue', 'galates·dori', '41', '4,675', '$750.11', '2.8M', '47.7'],
  ['projects/claude-stats', 'cortex·andie', '42', '5,293', '$631.71', '3.8M', '7.39'],
  ['_OBSIDIAN/AeternaLabs', 'galates·andie', '18', '5,382', '$571.45', '1.8M', '16.19'],
  ['D:/Home', 'galates·andie', '36', '2,680', '$405.32', '2.8M', '8.01'],
  ['projects/open-brain', 'cortex·andie', '27', '3,227', '$395.44', '2.1M', '5.14'],
  ['_Claude/ICQLogParser', 'archiv·galates', '26', '3,775', '$377.18', '183.7K', '34.17'],
  ['andie/collector', 'cortex·andie', '20', '2,840', '$365.41', '1.9M', '3.74'],
  ['projects/pulled', 'cortex·andie', '20', '2,433', '$335.12', '2.2M', '3.77'],
  ['d:/vscode', 'laptop·dori', '33', '2,144', '$269.74', '1.9M', '8.84'],
  ['Projects/beautyland', 'galates·andie', '16', '1,324', '$251.38', '1.3M', '10.37'],
  ['projects/scripta', 'cortex·andie', '7', '785', '$147.99', '1.0M', '4.05'],
  ['Projects/youtube', 'galates·andie', '15', '1,484', '$136.53', '674.1K', '21.68'],
  ['aeterna-labs/website', 'galates·andie', '4', '602', '$114.22', '569.7K', '3.96'],
  ['projects/redpull', 'cortex·andie', '9', '1,115', '$100.84', '529.3K', '2.46'],
  ['projects/ki-navigator', 'galates·andie', '3', '320', '$71.80', '471.5K', '2.17'],
  ['projects/aeterna-photo', 'cortex·andie', '3', '517', '$64.98', '145.4K', '5.11'],
  ['Home/AeternaLabs', 'galates·andie', '9', '391', '$50.90', '357.0K', '0.68'],
  ['projects/1912', 'cortex·andie', '2', '632', '$58.25', '161.8K', '11.18'],
];
const ACTIVITY_KPI = { totalProjects: '89', activeDays: '121', busiestDay: 'Wed', peakHour: '14:00' };

// ---------- SESSIONS ----------
// [date, project, model, ctx1M, durationMin, messages, userMsgs, apiCalls, tokens, cost, agents, errors]
const SESSIONS = [
  ['6/1, 10:26 AM', 'projects/scripta', 'Opus 4.8', false, '73', '18', '2', '36', '2.6M', '$2.00', '2', '3'],
  ['6/1, 10:22 AM', 'projects/claude-stats', 'Opus 4.8', false, '12', '16', '2', '14', '926.5K', '$1.33', '–', '–'],
  ['6/1, 9:02 AM', 'andie/collector', 'Opus 4.8', false, '147', '79', '5', '74', '7.1M', '$8.46', '–', '–'],
  ['5/31, 10:16 PM', 'Projects/higgsfield-v', 'Opus 4.8', false, '4', '19', '2', '17', '1.2M', '$1.82', '–', '1'],
  ['5/31, 9:46 PM', 'projects/scripta', 'Opus 4.8', true, '1478', '55', '8', '497', '33.9M', '$44.29', '15', '4'],
  ['5/30, 9:02 PM', 'projects/scripta', 'Opus 4.8', false, '23', '48', '8', '40', '2.4M', '$2.61', '–', '2'],
  ['5/30, 8:50 PM', 'projects/claude-stats', 'Opus 4.8', true, '2265', '312', '13', '374', '74.2M', '$64.01', '4', '5'],
  ['5/30, 8:07 PM', 'home/andie', 'Opus 4.8', false, '3', '6', '3', '3', '101.1K', '$0.26', '–', '–'],
  ['5/30, 8:05 PM', 'projects/claude-stats', 'Opus 4.8', false, '46', '91', '3', '88', '9.5M', '$8.49', '–', '3'],
  ['5/30, 9:58 AM', 'projects/claude-stats', 'Opus 4.8', true, '682', '72', '8', '64', '28.3M', '$44.44', '–', '23'],
  ['5/29, 5:24 PM', 'Projects/beautyland', 'Opus 4.8', true, '1596', '172', '4', '168', '33.4M', '$26.18', '–', '10'],
  ['5/29, 2:07 PM', 'projects/claude-stats', 'Opus 4.8', true, '453', '167', '11', '156', '29.3M', '$24.92', '–', '4'],
  ['5/29, 11:04 AM', 'Projects/beautyland', 'Opus 4.8', true, '1623', '433', '38', '395', '153.5M', '$133.16', '–', '9'],
  ['5/29, 10:40 AM', 'Projects/beautyland', 'Opus 4.8', true, '1577', '67', '17', '64', '17.0M', '$40.82', '2', '54'],
  ['5/28, 11:08 AM', 'projects/scripta', 'Opus 4.8', false, '75', '84', '7', '77', '9.6M', '$9.29', '–', '3'],
  ['5/27, 9:21 PM', 'Projects/beautyland', 'Opus 4.8', false, '2248', '47', '3', '44', '5.3M', '$5.62', '–', '3'],
  ['5/27, 2:32 PM', 'projects/scripta', 'Opus 4.7', true, '421', '292', '30', '412', '66.8M', '$42.68', '17', '4'],
  ['5/26, 7:03 PM', 'projects/scripta', 'Opus 4.7', false, '211', '139', '6', '271', '19.1M', '$13.29', '6', '7'],
  ['5/26, 6:58 PM', 'andie/collector', 'Opus 4.7', false, '1135', '140', '9', '214', '23.5M', '$13.13', '4', '4'],
  ['5/24, 10:18 AM', 'projects/kdbx-audit', 'Opus 4.7', true, '667', '109', '20', '88', '13.8M', '$15.29', '–', '2'],
];
const SESSIONS_META = { total: '840', filtered: '439', downloadable: '439' };
