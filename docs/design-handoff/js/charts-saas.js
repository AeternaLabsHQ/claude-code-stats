/* ============================================================
   charts-saas.js — chart builders for Plan & Billing,
   Activity & Projects. Reuses helpers/globals from charts.js.
   ============================================================ */

function buildSavingsByPeriod(ctx) {
  const accent = cvar('--accent', '#c2562f');
  const muted = cvar('--muted', '#888');
  const font = fam();
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels: SAVINGS_PERIODS.labels,
      datasets: [
        { label: 'API Equivalent', data: SAVINGS_PERIODS.apiEquivalent,
          backgroundColor: withAlpha2(muted, 0.5), borderRadius: 4, barPercentage: 0.9, categoryPercentage: 0.7 },
        { label: 'Plan Cost', data: SAVINGS_PERIODS.planCost,
          backgroundColor: accent, borderRadius: 4, barPercentage: 0.9, categoryPercentage: 0.7 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: legendCfg(true, font), tooltip: { mode: 'index', intersect: false } },
      scales: baseScales({ rotate: true, xTicks: 8, yFmt: v => '€' + v }),
    },
  });
}

function buildAvgPerDay(ctx) {
  const accent = cvar('--accent', '#c2562f');
  return new Chart(ctx, {
    type: 'bar',
    data: { labels: SAVINGS_PERIODS.labels, datasets: [{
      data: SAVINGS_PERIODS.avgPerDay, backgroundColor: withAlpha2(accent, 0.85),
      borderRadius: 4, barPercentage: 0.7,
    }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: baseScales({ rotate: true, xTicks: 8, yFmt: v => '€' + v }),
    },
  });
}

function buildDailyActivity(ctx) {
  const accent = cvar('--accent', '#c2562f');
  const muted = cvar('--muted', '#888');
  const grid = cvar('--line', '#ddd');
  const tick = cvar('--muted', '#666');
  const font = fam();
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels: DAILY.labels,
      datasets: [
        { type: 'bar', label: 'Messages', data: DAILY_ACTIVITY.messages, yAxisID: 'y',
          backgroundColor: withAlpha2(accent, 0.65), borderRadius: 2, barPercentage: 0.95, categoryPercentage: 0.95, order: 2 },
        { type: 'line', label: 'Sessions', data: DAILY_ACTIVITY.sessions, yAxisID: 'y1',
          borderColor: muted, backgroundColor: muted, borderWidth: 1.5, pointRadius: 0, tension: 0.3, order: 1 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: legendCfg(true, font) },
      scales: {
        x: { grid: { display: false }, border: { color: grid },
          ticks: { color: tick, font: { family: font, size: 9 }, maxRotation: 60, autoSkip: true, maxTicksLimit: 16 } },
        y: { position: 'left', grid: { color: withAlpha2(grid, 0.6), drawTicks: false }, border: { display: false },
          ticks: { color: tick, font: { family: font, size: 9 } }, beginAtZero: true, title: { display: true, text: 'Messages', color: tick, font: { family: font, size: 9 } } },
        y1: { position: 'right', grid: { drawOnChartArea: false }, border: { display: false },
          ticks: { color: tick, font: { family: font, size: 9 } }, beginAtZero: true, title: { display: true, text: 'Sessions', color: tick, font: { family: font, size: 9 } } },
      },
    },
  });
}

function buildHourly(ctx) {
  const accent = cvar('--accent', '#c2562f');
  const font = fam();
  const labels = Array.from({ length: 24 }, (_, h) => (h % 3 === 0 ? `${h}:00` : ''));
  const max = Math.max(...HOURLY);
  const colors = HOURLY.map(v => withAlpha2(accent, 0.25 + 0.6 * (v / max)));
  return new Chart(ctx, {
    type: 'polarArea',
    data: { labels, datasets: [{ data: HOURLY, backgroundColor: colors, borderColor: cvar('--panel', '#fff'), borderWidth: 1 }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: { r: { grid: { color: withAlpha2(cvar('--line', '#ddd'), 0.7) },
        ticks: { display: false, backdropColor: 'transparent' },
        pointLabels: { display: false },
        angleLines: { color: withAlpha2(cvar('--line', '#ddd'), 0.7) } } },
    },
  });
}

function buildWeekday(ctx) {
  const accent = cvar('--accent', '#c2562f');
  const muted = cvar('--muted', '#888');
  const colors = WEEKDAY.values.map((_, i) => (i >= 5 ? withAlpha2(muted, 0.4) : accent));
  return new Chart(ctx, {
    type: 'bar',
    data: { labels: WEEKDAY.labels, datasets: [{ data: WEEKDAY.values, backgroundColor: colors, borderRadius: 4, barPercentage: 0.7 }] },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { display: false } },
      scales: baseScales({ yFmt: v => (v / 1000) + 'k' }),
    },
  });
}

Object.assign(CHART_BUILDERS, {
  'c-savingsByPeriod': buildSavingsByPeriod,
  'c-avgPerDay': buildAvgPerDay,
  'c-dailyActivity': buildDailyActivity,
  'c-hourly': buildHourly,
  'c-weekday': buildWeekday,
});
