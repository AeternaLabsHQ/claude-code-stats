/* global React */

const fmtUSD_C = (n) => '$' + n.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
const fmtNum_C = (n) => n.toLocaleString('en-US');
const fmtTok_C = (n) => {
  if (n >= 1e9) return (n/1e9).toFixed(2) + 'B';
  if (n >= 1e6) return (n/1e6).toFixed(2) + 'M';
  if (n >= 1e3) return (n/1e3).toFixed(1) + 'K';
  return String(n);
};

// ═══════════════════════════════════════════════════════════
//  VARIANT C — TERMINAL · proper tab nav
// ═══════════════════════════════════════════════════════════
const terminalCSS = `
.vc {
  --bg: #f4f1ec;
  --panel: #fbfaf6;
  --grid: #d8d2c4;
  --grid-2: #e8e3d6;
  --fg: #1c1a17;
  --fg-2: #4d4a42;
  --fg-3: #918a7a;
  --accent: #b04a2f;
  --accent-soft: #f1d9cd;
  font-family: 'Geist', 'Inter', system-ui, sans-serif;
  background: var(--bg); color: var(--fg); letter-spacing: -0.005em;
}
.vc.dark {
  --bg: #0e0d0b; --panel: #15140f; --grid: #2a2620; --grid-2: #1f1d18;
  --fg: #ece7da; --fg-2: #b3ad9b; --fg-3: #76705f;
  --accent: #d97757; --accent-soft: #2c1c14;
}
.vc * { box-sizing: border-box; }
.vc .mono { font-family: 'Geist Mono', 'JetBrains Mono', ui-monospace, monospace; font-feature-settings: 'tnum' 1, 'zero' 1; }

.vc-shell { padding: 0; }

.vc-top { display: grid; grid-template-columns: auto 1fr auto; gap: 16px; align-items: center; padding: 10px 20px; border-bottom: 1px solid var(--grid); background: var(--panel); font-family: 'Geist Mono', monospace; font-size: 11px; }
.vc-top .id { display: flex; align-items: center; gap: 10px; }
.vc-top .id .dot { width: 8px; height: 8px; background: var(--accent); border-radius: 1px; }
.vc-top .id .name { font-weight: 600; letter-spacing: 0.02em; }
.vc-top .id .v { color: var(--fg-3); }
.vc-top .center { display: flex; gap: 20px; justify-content: center; color: var(--fg-3); }
.vc-top .center b { color: var(--fg); font-weight: 500; }
.vc-top .right { display: flex; gap: 8px; align-items: center; color: var(--fg-3); }
.vc-top .right .live { color: var(--accent); }

/* MAIN TAB NAV — full-width, primary navigation */
.vc-nav { display: flex; background: var(--bg); border-bottom: 1px solid var(--grid); padding: 0 20px; font-family: 'Geist Mono', monospace; }
.vc-nav button { background: transparent; border: 0; padding: 14px 18px; font-family: inherit; font-size: 11px; color: var(--fg-3); cursor: pointer; letter-spacing: 0.14em; text-transform: uppercase; position: relative; font-weight: 500; }
.vc-nav button:hover { color: var(--fg-2); }
.vc-nav button.on { color: var(--fg); }
.vc-nav button.on::after { content: ''; position: absolute; left: 12px; right: 12px; bottom: -1px; height: 2px; background: var(--accent); }
.vc-nav .spacer { flex: 1; }
.vc-nav .range { display: flex; align-items: center; gap: 0; padding: 8px 0; }
.vc-nav .range .lbl { font-size: 10px; letter-spacing: 0.16em; color: var(--fg-3); margin-right: 12px; text-transform: uppercase; }
.vc-nav .range button { padding: 6px 12px; font-size: 11px; border-left: 1px solid var(--grid); }
.vc-nav .range button:first-of-type { border-left: 0; }
.vc-nav .range button.on { color: var(--accent); }
.vc-nav .range button.on::after { display: none; }

.vc-main { padding: 20px 20px 40px; max-width: 1400px; margin: 0 auto; font-family: 'Geist Mono', monospace; }

/* KPI strip - persistent across tabs */
.vc-kpis { display: grid; grid-template-columns: 1.4fr 1fr 1fr 1fr 1fr; border: 1px solid var(--grid); background: var(--panel); margin-bottom: 24px; }
.vc-kpi { padding: 14px 18px; border-right: 1px solid var(--grid); }
.vc-kpi:last-child { border-right: 0; }
.vc-kpi .lab { font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--fg-3); margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; }
.vc-kpi .lab .delta { color: var(--fg); font-weight: 500; letter-spacing: 0; text-transform: none; font-size: 11px; }
.vc-kpi .lab .delta.up { color: var(--accent); }
.vc-kpi .val { font-size: 26px; font-weight: 500; line-height: 1; letter-spacing: -0.02em; font-feature-settings: 'tnum' 1; margin-bottom: 6px; }
.vc-kpi.primary .val { color: var(--accent); }
.vc-kpi .sub { font-size: 11px; color: var(--fg-3); line-height: 1.5; }
.vc-kpi .sub b { color: var(--fg-2); font-weight: 500; }

/* Tab indicator — shows which tab content is below */
.vc-tab-h { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 12px; margin-bottom: 14px; padding-top: 4px; }
.vc-tab-h .lbl { font-size: 11px; letter-spacing: 0.16em; text-transform: uppercase; color: var(--fg-3); }
.vc-tab-h .lbl b { color: var(--fg); font-weight: 500; margin-right: 8px; }
.vc-tab-h .rule { height: 1px; background: var(--grid); }
.vc-tab-h .meta { font-size: 11px; color: var(--fg-3); }

/* Pane grids */
.vc-pane-grid { display: grid; gap: 0; border: 1px solid var(--grid); background: var(--panel); margin-bottom: 16px; }
.vc-pane-grid.cols-2 { grid-template-columns: 1.6fr 1fr; }
.vc-pane-grid.cols-2-eq { grid-template-columns: 1fr 1fr; }
.vc-pane-grid.cols-3 { grid-template-columns: 1fr 1fr 1fr; }
.vc-pane { padding: 16px 18px; border-right: 1px solid var(--grid); }
.vc-pane:last-child { border-right: 0; }
.vc-pane h3 { font-size: 11px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--fg); margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; }
.vc-pane h3 .meta { color: var(--fg-3); font-weight: 400; letter-spacing: 0.04em; text-transform: none; font-size: 10px; }

/* Big chart */
.vc-bigchart { height: 280px; width: 100%; }
.vc-bigchart .grid { stroke: var(--grid-2); stroke-width: 1; stroke-dasharray: 1 3; }
.vc-bigchart .axis { stroke: var(--grid); stroke-width: 1; }
.vc-bigchart .tx { font-family: 'Geist Mono', monospace; font-size: 10px; fill: var(--fg-3); font-feature-settings: 'tnum' 1; }
.vc-bigchart .area { fill: var(--accent); fill-opacity: 0.1; }
.vc-bigchart .line { stroke: var(--accent); stroke-width: 1.5; fill: none; }
.vc-bigchart .gh { stroke: var(--fg-2); stroke-width: 0.75; stroke-dasharray: 4 2; fill: none; opacity: 0.6; }

.vc-stat-row { display: grid; grid-template-columns: 1fr auto; padding: 8px 0; border-bottom: 1px dashed var(--grid); font-size: 12px; }
.vc-stat-row:last-child { border-bottom: 0; }
.vc-stat-row .k { color: var(--fg-3); }
.vc-stat-row .v { color: var(--fg); font-feature-settings: 'tnum' 1; }
.vc-stat-row .v.acc { color: var(--accent); }

.vc-distbar { display: flex; flex-direction: column; gap: 10px; margin-top: 8px; }
.vc-distbar-row { display: grid; grid-template-columns: 90px 1fr 90px; gap: 10px; align-items: center; font-size: 11px; }
.vc-distbar-row .nm { color: var(--fg); }
.vc-distbar-row .bar { height: 12px; background: var(--bg); border: 1px solid var(--grid); position: relative; overflow: hidden; }
.vc-distbar-row .bar i { display: block; height: 100%; background: var(--accent); }
.vc-distbar-row.s2 .bar i { background: var(--fg-2); }
.vc-distbar-row.s3 .bar i { background: var(--fg-3); }
.vc-distbar-row .vl { color: var(--fg-2); text-align: right; font-feature-settings: 'tnum' 1; }

.vc-heatmap { display: grid; gap: 2px; }
.vc-heatmap-row { display: grid; grid-template-columns: 28px repeat(18, 1fr); gap: 2px; align-items: center; }
.vc-heatmap-row .day { font-size: 10px; color: var(--fg-3); }
.vc-heatmap-cell { aspect-ratio: 1; background: var(--accent); border-radius: 1px; }

.vc-hourly { display: grid; grid-template-columns: repeat(24, 1fr); gap: 2px; align-items: end; height: 80px; padding-bottom: 4px; border-bottom: 1px solid var(--grid); }
.vc-hourly .b { background: var(--accent); min-height: 1px; opacity: var(--o, 0.7); }
.vc-hourly-x { display: grid; grid-template-columns: repeat(24, 1fr); font-size: 10px; color: var(--fg-3); padding-top: 4px; }
.vc-hourly-x span { text-align: center; }

.vc-table-pane { padding: 0; }
.vc-table-pane .pane-h { padding: 12px 16px; border-bottom: 1px solid var(--grid); display: flex; justify-content: space-between; align-items: center; }
.vc-table-pane .pane-h h3 { font-size: 11px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; margin: 0; }
.vc-table-pane .pane-h .meta { font-size: 11px; color: var(--fg-3); }
.vc-table { width: 100%; border-collapse: collapse; font-size: 11px; font-family: 'Geist Mono', monospace; }
.vc-table th { text-align: left; padding: 8px 14px; font-size: 10px; font-weight: 500; color: var(--fg-3); text-transform: uppercase; letter-spacing: 0.1em; border-bottom: 1px solid var(--grid); background: var(--bg); }
.vc-table th.num { text-align: right; }
.vc-table td { padding: 8px 14px; border-bottom: 1px solid var(--grid-2); }
.vc-table td.idx { color: var(--fg-3); width: 32px; }
.vc-table td.proj { color: var(--fg); }
.vc-table td.num { text-align: right; font-feature-settings: 'tnum' 1; color: var(--fg); }
.vc-table td.num.acc { color: var(--accent); }
.vc-table tr:last-child td { border-bottom: 0; }
.vc-table tr:hover td { background: var(--accent-soft); }
.vc-table .bar-cell { display: flex; align-items: center; justify-content: flex-end; gap: 8px; }
.vc-table .bar-cell .b { width: 80px; height: 6px; background: var(--bg); border: 1px solid var(--grid); }
.vc-table .bar-cell .b i { display: block; height: 100%; background: var(--accent); }

.vc-tag { display: inline-block; padding: 1px 6px; border: 1px solid var(--grid); font-size: 10px; color: var(--fg-2); letter-spacing: 0.04em; }
.vc-tag.acc { color: var(--accent); border-color: var(--accent); }
.vc-tag.model { font-family: 'Geist Mono', monospace; }

/* Plan tab specifics */
.vc-progress-row { display: grid; grid-template-columns: 1fr auto; gap: 16px; margin-bottom: 12px; }
.vc-progress-track { height: 28px; background: var(--bg); border: 1px solid var(--grid); position: relative; }
.vc-progress-fill { height: 100%; background: var(--accent); position: relative; }
.vc-progress-fill::after { content: attr(data-label); position: absolute; right: 8px; top: 50%; transform: translateY(-50%); font-size: 10px; color: var(--bg); font-weight: 500; }
.vc-plan-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 0; border: 1px solid var(--grid); background: var(--panel); margin-bottom: 16px; }
.vc-plan-cell { padding: 14px 18px; border-right: 1px solid var(--grid); }
.vc-plan-cell:last-child { border-right: 0; }

/* Sessions list */
.vc-session { display: grid; grid-template-columns: 90px 1fr auto auto; gap: 16px; padding: 11px 16px; border-bottom: 1px solid var(--grid-2); align-items: center; font-size: 11px; }
.vc-session:last-child { border-bottom: 0; }
.vc-session:hover { background: var(--accent-soft); }
.vc-session .when { color: var(--fg-3); }
.vc-session .body { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.vc-session .body .l1 { display: flex; align-items: center; gap: 8px; }
.vc-session .body .proj { color: var(--fg); font-weight: 500; }
.vc-session .body .prompt { color: var(--fg-3); font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 600px; font-family: 'Geist', sans-serif; }
.vc-session .stats { display: flex; gap: 12px; color: var(--fg-2); font-feature-settings: 'tnum' 1; }
.vc-session .stats span { color: var(--fg-3); }
.vc-session .stats span b { color: var(--fg); font-weight: 500; }
.vc-session .cost { color: var(--accent); font-weight: 500; font-feature-settings: 'tnum' 1; min-width: 60px; text-align: right; }

/* Insights blocks */
.vc-misc-grid { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 0; }
.vc-misc { padding: 16px 18px; border-right: 1px solid var(--grid); border-bottom: 1px solid var(--grid); }
.vc-misc:last-child { border-right: 0; }
.vc-misc .v { font-size: 22px; font-weight: 500; color: var(--fg); font-feature-settings: 'tnum' 1; line-height: 1; }
.vc-misc .v.acc { color: var(--accent); }
.vc-misc .l { font-size: 10px; color: var(--fg-3); text-transform: uppercase; letter-spacing: 0.12em; margin-top: 8px; }

/* Empty placeholder for not-yet-mocked tabs */
.vc-stub { padding: 80px 40px; text-align: center; border: 1px dashed var(--grid); background: var(--panel); }
.vc-stub .h { font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase; color: var(--fg-3); margin-bottom: 12px; }
.vc-stub .t { font-size: 14px; color: var(--fg-2); }
`;

// ── Sub-component: cost chart (reused) ────────────────────
function CostChart({ data }) {
  const W = 800, H = 280, P = { l: 44, r: 16, t: 20, b: 28 };
  const innerW = W - P.l - P.r, innerH = H - P.t - P.b;
  const maxC = Math.max(...data.daily_cost) * 1.1;
  const pts = data.daily_cost.map((v, i) => ({
    x: P.l + (i / (data.daily_cost.length - 1)) * innerW,
    y: P.t + innerH - (v / maxC) * innerH,
  }));
  const linePath = pts.map((p, i) => (i === 0 ? 'M' : 'L') + p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' ');
  const areaPath = linePath + ` L${pts[pts.length-1].x.toFixed(1)},${P.t + innerH} L${pts[0].x.toFixed(1)},${P.t + innerH} Z`;
  const ma = data.daily_cost.map((_, i) => {
    const s = Math.max(0, i - 6);
    const slice = data.daily_cost.slice(s, i + 1);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  });
  const maPts = ma.map((v, i) => ({ x: P.l + (i / (ma.length - 1)) * innerW, y: P.t + innerH - (v / maxC) * innerH }));
  const maPath = maPts.map((p, i) => (i === 0 ? 'M' : 'L') + p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' ');
  const today = new Date('2026-04-30');
  const xTicks = [];
  for (let i = data.daily_cost.length - 1; i >= 0; i -= 12) {
    const d = new Date(today); d.setDate(d.getDate() - (data.daily_cost.length - 1 - i));
    xTicks.push({i, lbl: d.toLocaleDateString('en-US', {month: 'short', day: 'numeric'})});
  }
  return (
    <svg className="vc-bigchart" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
      {[0, 0.25, 0.5, 0.75, 1].map((f, i) => (
        <g key={i}>
          <line className="grid" x1={P.l} x2={W - P.r} y1={P.t + innerH * (1 - f)} y2={P.t + innerH * (1 - f)} />
          <text className="tx" x={P.l - 6} y={P.t + innerH * (1 - f) + 4} textAnchor="end">{(maxC * f).toFixed(0)}</text>
        </g>
      ))}
      <line className="axis" x1={P.l} x2={P.l} y1={P.t} y2={P.t + innerH} />
      <line className="axis" x1={P.l} x2={W - P.r} y1={P.t + innerH} y2={P.t + innerH} />
      {xTicks.map(t => (
        <text key={t.i} className="tx" x={P.l + (t.i / (data.daily_cost.length - 1)) * innerW} y={H - 8} textAnchor="middle">{t.lbl}</text>
      ))}
      <path className="area" d={areaPath} />
      <path className="line" d={linePath} />
      <path className="gh" d={maPath} />
    </svg>
  );
}

// ── Tab content ────────────────────────────────────────────
function CostTab({ data }) {
  return (
    <>
      <div className="vc-tab-h">
        <span className="lbl"><b>↳</b> Token & API Value</span>
        <span className="rule"></span>
        <span className="meta">90d · daily · USD</span>
      </div>
      <div className="vc-pane-grid cols-2">
        <div className="vc-pane">
          <h3>cost.daily <span className="meta">── value · - - 7d ma</span></h3>
          <CostChart data={data} />
        </div>
        <div className="vc-pane">
          <h3>by_model <span className="meta">share</span></h3>
          <div className="vc-distbar">
            {data.models.map((m, i) => (
              <div key={m.name} className={'vc-distbar-row' + (i === 1 ? ' s2' : i === 2 ? ' s3' : '')}>
                <span className="nm">{m.name}</span>
                <span className="bar"><i style={{width: m.share + '%'}} /></span>
                <span className="vl">{fmtUSD_C(m.cost)}</span>
              </div>
            ))}
          </div>
          <h3 style={{marginTop: 22}}>token_breakdown</h3>
          <div className="vc-stat-row"><span className="k">output</span><span className="v">{fmtTok_C(data.kpi.output_tokens)}</span></div>
          <div className="vc-stat-row"><span className="k">input (new)</span><span className="v">{fmtTok_C(data.kpi.input_tokens)}</span></div>
          <div className="vc-stat-row"><span className="k">cache.read</span><span className="v">{fmtTok_C(data.kpi.cache_read)}</span></div>
          <div className="vc-stat-row"><span className="k">cache.write</span><span className="v">{fmtTok_C(data.kpi.cache_write)}</span></div>
          <div className="vc-stat-row"><span className="k">cache.efficiency</span><span className="v acc">97.7%</span></div>
        </div>
      </div>

      <div className="vc-pane-grid">
        <div className="vc-pane vc-table-pane">
          <div className="pane-h">
            <h3>model_detail</h3>
            <span className="meta">{data.models.length} models · 90d</span>
          </div>
          <table className="vc-table">
            <thead>
              <tr>
                <th>MODEL</th>
                <th className="num">API VALUE</th>
                <th className="num">CALLS</th>
                <th className="num">OUTPUT TOKENS</th>
                <th className="num">$/CALL</th>
                <th className="num" style={{width: 140}}>SHARE</th>
              </tr>
            </thead>
            <tbody>
              {data.models.map(m => (
                <tr key={m.name}>
                  <td className="proj"><span className="vc-tag model">{m.name}</span></td>
                  <td className="num acc">{fmtUSD_C(m.cost)}</td>
                  <td className="num">{fmtNum_C(m.calls)}</td>
                  <td className="num">{fmtTok_C(m.output)}</td>
                  <td className="num">{fmtUSD_C(m.cost / m.calls)}</td>
                  <td className="num">
                    <div className="bar-cell">
                      <span style={{color: 'var(--fg-3)'}}>{m.share.toFixed(1)}%</span>
                      <span className="b"><i style={{width: m.share + '%'}} /></span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function ActivityTab({ data }) {
  const heatmapMax = Math.max(...data.heatmap.flat());
  return (
    <>
      <div className="vc-tab-h">
        <span className="lbl"><b>↳</b> Activity</span>
        <span className="rule"></span>
        <span className="meta">all-time · UTC+1</span>
      </div>
      <div className="vc-pane-grid cols-2">
        <div className="vc-pane">
          <h3>activity.heatmap <span className="meta">last 18 weeks · darker = more</span></h3>
          <div className="vc-heatmap">
            {['M','T','W','T','F','S','S'].map((d, di) => (
              <div key={di} className="vc-heatmap-row">
                <span className="day">{d}</span>
                {data.heatmap[di].map((v, wi) => {
                  const intensity = Math.max(0, Math.min(1, v / heatmapMax));
                  return <span key={wi} className="vc-heatmap-cell" style={{opacity: 0.08 + intensity * 0.92}} />;
                })}
              </div>
            ))}
          </div>
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 12, fontSize: 10, color: 'var(--fg-3)'}}>
            <span>18 weeks ago</span>
            <span style={{display: 'flex', gap: 4, alignItems: 'center'}}>
              less
              {[0.1, 0.3, 0.5, 0.7, 0.95].map(o => (<span key={o} style={{width: 10, height: 10, background: 'var(--accent)', opacity: o}} />))}
              more
            </span>
            <span>this week</span>
          </div>
          <h3 style={{marginTop: 22}}>weekday <span className="meta">total messages</span></h3>
          <div className="vc-distbar">
            {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((d, i) => {
              const v = data.weekday[i], max = Math.max(...data.weekday);
              return (
                <div key={d} className="vc-distbar-row">
                  <span className="nm">{d}</span>
                  <span className="bar"><i style={{width: (v / max * 100) + '%'}} /></span>
                  <span className="vl">{fmtNum_C(v)}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div className="vc-pane">
          <h3>hour_of_day <span className="meta">msgs</span></h3>
          <div className="vc-hourly">
            {data.hourly.map((v, i) => (
              <div key={i} className="b" style={{height: (v / Math.max(...data.hourly) * 100) + '%', '--o': 0.4 + (v / Math.max(...data.hourly)) * 0.6}} />
            ))}
          </div>
          <div className="vc-hourly-x">
            {Array.from({length: 24}, (_, i) => <span key={i}>{i % 4 === 0 ? String(i).padStart(2,'0') : ''}</span>)}
          </div>

          <h3 style={{marginTop: 22}}>summary <span className="meta">90d</span></h3>
          <div className="vc-stat-row"><span className="k">peak hour</span><span className="v">15:00 — 16:00</span></div>
          <div className="vc-stat-row"><span className="k">peak day</span><span className="v">Tuesday</span></div>
          <div className="vc-stat-row"><span className="k">active days</span><span className="v">82 / 90</span></div>
          <div className="vc-stat-row"><span className="k">avg session/day</span><span className="v">2.7</span></div>
          <div className="vc-stat-row"><span className="k">longest streak</span><span className="v acc">14 days</span></div>
          <div className="vc-stat-row"><span className="k">current streak</span><span className="v acc">6 days</span></div>
        </div>
      </div>
    </>
  );
}

function ProjectsTab({ data }) {
  const totalProj = data.projects.reduce((s, p) => s + p.cost, 0);
  return (
    <>
      <div className="vc-tab-h">
        <span className="lbl"><b>↳</b> Projects</span>
        <span className="rule"></span>
        <span className="meta">{data.projects.length} total · sorted by api value desc</span>
      </div>
      <div className="vc-pane-grid">
        <div className="vc-pane vc-table-pane">
          <div className="pane-h">
            <h3>projects.all</h3>
            <span className="meta">click row to drill into project</span>
          </div>
          <table className="vc-table">
            <thead>
              <tr>
                <th>#</th>
                <th>PROJECT</th>
                <th className="num">SESSIONS</th>
                <th className="num">MSGS</th>
                <th className="num">OUT.TOKENS</th>
                <th className="num">SIZE</th>
                <th className="num">API VALUE</th>
                <th className="num" style={{width: 180}}>SHARE</th>
              </tr>
            </thead>
            <tbody>
              {data.projects.map((p, i) => (
                <tr key={p.name}>
                  <td className="idx">{String(i + 1).padStart(2, '0')}</td>
                  <td className="proj">{p.name}</td>
                  <td className="num">{p.sessions}</td>
                  <td className="num">{fmtNum_C(p.messages)}</td>
                  <td className="num">{fmtTok_C(p.output)}</td>
                  <td className="num">{p.sizeMb.toFixed(1)} MB</td>
                  <td className="num acc">{fmtUSD_C(p.cost)}</td>
                  <td className="num">
                    <div className="bar-cell">
                      <span style={{color: 'var(--fg-3)'}}>{(p.cost / totalProj * 100).toFixed(1)}%</span>
                      <span className="b"><i style={{width: (p.cost / totalProj * 100 * 3) + '%'}} /></span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

function SessionsTab({ data }) {
  const modelClass = (m) => m.toLowerCase().includes('opus') ? 'acc' : '';
  return (
    <>
      <div className="vc-tab-h">
        <span className="lbl"><b>↳</b> Sessions</span>
        <span className="rule"></span>
        <span className="meta">{data.kpi.sessions} total · most recent first</span>
      </div>
      <div className="vc-pane-grid">
        <div className="vc-pane vc-table-pane">
          <div className="pane-h">
            <h3>sessions.recent</h3>
            <span className="meta">showing 7 of {data.kpi.sessions} · filter: all projects</span>
          </div>
          {data.recent_sessions.map((s, i) => (
            <div key={i} className="vc-session">
              <span className="when">{s.date}</span>
              <span className="body">
                <span className="l1">
                  <span className="proj">{s.project}</span>
                  <span className={'vc-tag model ' + modelClass(s.model)}>{s.model}</span>
                </span>
                <span className="prompt">{s.prompt}</span>
              </span>
              <span className="stats">
                <span>{s.duration}<b>m</b></span>
                <span>{s.messages}<b> msg</b></span>
              </span>
              <span className="cost">{fmtUSD_C(s.cost)}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}

function PlanTab({ data }) {
  const subscriptionPaid = data.kpi.actual_paid;
  const apiValue = data.kpi.api_equivalent;
  const savings = apiValue - subscriptionPaid;
  const roi = (apiValue / subscriptionPaid).toFixed(1);
  return (
    <>
      <div className="vc-tab-h">
        <span className="lbl"><b>↳</b> Plan & Billing</span>
        <span className="rule"></span>
        <span className="meta">Max 20× · cycle 14 Apr → 14 May</span>
      </div>
      <div className="vc-plan-grid">
        <div className="vc-plan-cell">
          <div style={{fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 8}}>PLAN</div>
          <div style={{fontSize: 20, color: 'var(--accent)', fontWeight: 500}}>Max 20×</div>
          <div style={{fontSize: 11, color: 'var(--fg-3)', marginTop: 4}}>$200/mo</div>
        </div>
        <div className="vc-plan-cell">
          <div style={{fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 8}}>PAID THIS PERIOD</div>
          <div style={{fontSize: 20, fontWeight: 500}}>{fmtUSD_C(subscriptionPaid)}</div>
          <div style={{fontSize: 11, color: 'var(--fg-3)', marginTop: 4}}>fixed subscription</div>
        </div>
        <div className="vc-plan-cell">
          <div style={{fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 8}}>API EQUIVALENT</div>
          <div style={{fontSize: 20, fontWeight: 500}}>{fmtUSD_C(apiValue)}</div>
          <div style={{fontSize: 11, color: 'var(--fg-3)', marginTop: 4}}>at pay-as-you-go rates</div>
        </div>
        <div className="vc-plan-cell">
          <div style={{fontSize: 10, color: 'var(--fg-3)', letterSpacing: '0.14em', textTransform: 'uppercase', marginBottom: 8}}>EFFECTIVE ROI</div>
          <div style={{fontSize: 20, color: 'var(--accent)', fontWeight: 500}}>{roi}×</div>
          <div style={{fontSize: 11, color: 'var(--fg-3)', marginTop: 4}}>save {fmtUSD_C(savings)}</div>
        </div>
      </div>

      <div className="vc-pane-grid cols-2">
        <div className="vc-pane">
          <h3>billing.cycle <span className="meta">16 of 30 days</span></h3>
          <div className="vc-progress-row">
            <div className="vc-progress-track">
              <div className="vc-progress-fill" data-label="53% used · 14 days left" style={{width: '53%'}} />
            </div>
          </div>
          <div className="vc-stat-row" style={{marginTop: 14}}><span className="k">cycle start</span><span className="v">14 Apr 2026</span></div>
          <div className="vc-stat-row"><span className="k">cycle end</span><span className="v">14 May 2026</span></div>
          <div className="vc-stat-row"><span className="k">api value so far</span><span className="v acc">{fmtUSD_C(apiValue * 0.53)}</span></div>
          <div className="vc-stat-row"><span className="k">projected end</span><span className="v">{fmtUSD_C(apiValue)}</span></div>
        </div>
        <div className="vc-pane">
          <h3>plan_comparison <span className="meta">your usage vs plan limits</span></h3>
          <div className="vc-distbar">
            {[
              {n: 'Free', max: 12, color: 'fg-3'},
              {n: 'Pro $20', max: 320, color: 'fg-2'},
              {n: 'Max 5×', max: 1200, color: 'fg-2'},
              {n: 'Max 20×', max: 4800, color: 'accent'},
              {n: 'Team', max: 10000, color: 'fg-2'},
            ].map(p => {
              const pct = Math.min(100, (apiValue / p.max) * 100);
              return (
                <div key={p.n} className={'vc-distbar-row' + (p.color === 'fg-2' ? ' s2' : p.color === 'fg-3' ? ' s3' : '')}>
                  <span className="nm">{p.n}</span>
                  <span className="bar"><i style={{width: pct + '%'}} /></span>
                  <span className="vl">{fmtUSD_C(p.max)}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </>
  );
}

function InsightsTab({ data }) {
  return (
    <>
      <div className="vc-tab-h">
        <span className="lbl"><b>↳</b> Insights</span>
        <span className="rule"></span>
        <span className="meta">configuration · file ops · todos</span>
      </div>

      <div className="vc-pane-grid" style={{padding: 0, gridTemplateColumns: '1fr'}}>
        <div className="vc-misc-grid">
          <div className="vc-misc"><div className="v acc">1,842</div><div className="l">file edits</div></div>
          <div className="vc-misc"><div className="v">312</div><div className="l">file writes</div></div>
          <div className="vc-misc"><div className="v">1,428</div><div className="l">file reads</div></div>
          <div className="vc-misc"><div className="v">912</div><div className="l">bash runs</div></div>
          <div className="vc-misc"><div className="v acc">42</div><div className="l">git commits</div></div>
          <div className="vc-misc"><div className="v">18</div><div className="l">git pushes</div></div>
          <div className="vc-misc"><div className="v">7</div><div className="l">prs opened</div></div>
          <div className="vc-misc"><div className="v">128</div><div className="l">subagent calls</div></div>
        </div>
      </div>

      <div className="vc-pane-grid cols-2">
        <div className="vc-pane">
          <h3>top_tools <span className="meta">by call count</span></h3>
          <div className="vc-distbar">
            {data.top_tools.map(t => {
              const max = data.top_tools[0].count;
              return (
                <div key={t.name} className="vc-distbar-row">
                  <span className="nm">{t.name}</span>
                  <span className="bar"><i style={{width: (t.count / max * 100) + '%'}} /></span>
                  <span className="vl">{fmtNum_C(t.count)}</span>
                </div>
              );
            })}
          </div>
        </div>
        <div className="vc-pane">
          <h3>config <span className="meta">claude code installation</span></h3>
          <div className="vc-stat-row"><span className="k">version</span><span className="v">1.4.2</span></div>
          <div className="vc-stat-row"><span className="k">user</span><span className="v">{data.account.name}</span></div>
          <div className="vc-stat-row"><span className="k">plan</span><span className="v acc">{data.account.plan}</span></div>
          <div className="vc-stat-row"><span className="k">mcp servers</span><span className="v">3 active</span></div>
          <div className="vc-stat-row"><span className="k">hooks</span><span className="v">2 active</span></div>
          <div className="vc-stat-row"><span className="k">custom skills</span><span className="v">8</span></div>
          <div className="vc-stat-row"><span className="k">file snapshots</span><span className="v">412 · 84.2 MB</span></div>
          <div className="vc-stat-row"><span className="k">todos completed</span><span className="v">218 / 264</span></div>
        </div>
      </div>
    </>
  );
}

function AgentsTab({ data }) {
  return (
    <>
      <div className="vc-tab-h">
        <span className="lbl"><b>↳</b> Agents</span>
        <span className="rule"></span>
        <span className="meta">subagent dispatches · errors</span>
      </div>
      <div className="vc-pane-grid cols-2">
        <div className="vc-pane">
          <h3>by_type <span className="meta">128 dispatches · 90d</span></h3>
          <div className="vc-distbar">
            {[
              {n: 'verifier', c: 48},
              {n: 'general-purpose', c: 32},
              {n: 'output-style-setup', c: 22},
              {n: 'repo-explorer', c: 16},
              {n: 'design-reviewer', c: 10},
            ].map(a => {
              const max = 48;
              return (
                <div key={a.n} className="vc-distbar-row">
                  <span className="nm">{a.n}</span>
                  <span className="bar"><i style={{width: (a.c / max * 100) + '%'}} /></span>
                  <span className="vl">{a.c}</span>
                </div>
              );
            })}
          </div>
        </div>
        <div className="vc-pane">
          <h3>errors <span className="meta">by category</span></h3>
          <div className="vc-distbar">
            {[
              {n: 'tool_timeout', c: 8},
              {n: 'parse_error', c: 4},
              {n: 'rate_limit', c: 2},
              {n: 'network', c: 1},
            ].map(a => {
              const max = 8;
              return (
                <div key={a.n} className={'vc-distbar-row s2'}>
                  <span className="nm">{a.n}</span>
                  <span className="bar"><i style={{width: (a.c / max * 100) + '%'}} /></span>
                  <span className="vl">{a.c}</span>
                </div>
              );
            })}
          </div>
          <h3 style={{marginTop: 22}}>summary</h3>
          <div className="vc-stat-row"><span className="k">total dispatches</span><span className="v">128</span></div>
          <div className="vc-stat-row"><span className="k">avg duration</span><span className="v">42s</span></div>
          <div className="vc-stat-row"><span className="k">success rate</span><span className="v acc">88.3%</span></div>
          <div className="vc-stat-row"><span className="k">error count</span><span className="v">15</span></div>
        </div>
      </div>
    </>
  );
}

const TABS = [
  { id: 'cost', label: 'Cost', component: CostTab },
  { id: 'activity', label: 'Activity', component: ActivityTab },
  { id: 'projects', label: 'Projects', component: ProjectsTab },
  { id: 'sessions', label: 'Sessions', component: SessionsTab },
  { id: 'plan', label: 'Plan', component: PlanTab },
  { id: 'insights', label: 'Insights', component: InsightsTab },
  { id: 'agents', label: 'Agents', component: AgentsTab },
];

function VariantC({ data, dark, activeTab: extActive }) {
  const [tab, setTab] = React.useState(extActive || 'cost');
  React.useEffect(() => { if (extActive) setTab(extActive); }, [extActive]);
  const TabComp = (TABS.find(t => t.id === tab) || TABS[0]).component;

  return (
    <div className={'vc' + (dark ? ' dark' : '')}>
      <style>{terminalCSS}</style>
      <div className="vc-shell">

        <header className="vc-top">
          <div className="id">
            <div className="dot"></div>
            <span className="name">CLAUDE.STATS</span>
            <span className="v">v2.4.0</span>
          </div>
          <div className="center">
            <span><b>USER</b> {data.account.name}</span>
            <span><b>PLAN</b> {data.account.plan}</span>
            <span><b>RANGE</b> {data.account.first_session} → {data.account.last_session}</span>
          </div>
          <div className="right">
            <span className="live">● LIVE</span>
            <span>16:30 UTC</span>
          </div>
        </header>

        {/* PRIMARY NAV — switches the content below */}
        <nav className="vc-nav">
          {TABS.map(t => (
            <button key={t.id} className={tab === t.id ? 'on' : ''} onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
          <span className="spacer"></span>
          <div className="range">
            <span className="lbl">range</span>
            {['7d','30d','90d','YTD','ALL'].map((t, i) => (
              <button key={t} className={i === 2 ? 'on' : ''}>{t}</button>
            ))}
          </div>
        </nav>

        <div className="vc-main">
          {/* Persistent KPI strip */}
          <div className="vc-kpis">
            <div className="vc-kpi primary">
              <div className="lab">API EQUIVALENT <span className="delta up">▲ 12.4%</span></div>
              <div className="val">{fmtUSD_C(data.kpi.api_equivalent)}</div>
              <div className="sub">paid <b>{fmtUSD_C(data.kpi.actual_paid)}</b> · save <b>95.3%</b></div>
            </div>
            <div className="vc-kpi">
              <div className="lab">SESSIONS <span className="delta">{data.projects.length} prj</span></div>
              <div className="val">{fmtNum_C(data.kpi.sessions)}</div>
              <div className="sub">avg <b>38m</b></div>
            </div>
            <div className="vc-kpi">
              <div className="lab">MESSAGES</div>
              <div className="val">{fmtNum_C(data.kpi.messages)}</div>
              <div className="sub">{Math.round(data.kpi.messages / data.kpi.sessions)}/session</div>
            </div>
            <div className="vc-kpi">
              <div className="lab">OUTPUT TOKENS</div>
              <div className="val">{fmtTok_C(data.kpi.output_tokens)}</div>
              <div className="sub">in <b>{fmtTok_C(data.kpi.input_tokens)}</b></div>
            </div>
            <div className="vc-kpi">
              <div className="lab">CACHE HIT</div>
              <div className="val">97.7<span style={{fontSize: 16, color: 'var(--fg-3)'}}>%</span></div>
              <div className="sub">read <b>{fmtTok_C(data.kpi.cache_read)}</b></div>
            </div>
          </div>

          {/* Active tab content */}
          <TabComp data={data} />
        </div>
      </div>
    </div>
  );
}

window.VariantC = VariantC;
window.VC_TABS = TABS;
