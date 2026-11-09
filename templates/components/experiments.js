// ── Insights: Experiments (VCExperiments) ───────────────────────
// Renders D.experiments (claudestats_core/experiments.py
// build_experiment_summary) into the Insights "Experiments" section:
// intro, current assignment chips, a per-day timeline per ID, one
// comparison card per ID x model (grouped rows with change, 95% CI and
// p), a thinking table and the method and caveats. Full-range data, so it
// ignores the date/project filter. html() is pure (testable in Node); render()
// reads the locale and writes into the root element.
(function() {
  'use strict';

  const MIN_CARD_REPLIES = 20;   // display cutoff, not the verdict threshold
  const HIDE_KEY = 'vc-exp-hide-insufficient';
  const DAY_MS = 86400000;
  const DASH = '-';

  // Every UI string with its English fallback. Keep all locale reads as
  // literal property reads on L so the locale-key test can find them.
  function texts(L) {
    L = L || {};
    return {
      intro: L.intro || 'Anthropic sometimes tests changed behaviour on part of its users, and Claude Code records the ID of such an experiment in the session logs. This section compares replies made under an ID with replies of the same model without a recorded experiment ID. Keep in mind: the work itself differed between the periods, and this measures how the model worked, not whether the results were better.',
      empty: L.empty || 'No experiment IDs found in your session logs. Claude Code records them since late summer 2026; older logs and API-key setups may not have them.',
      current_title: L.current_title || 'Current assignment',
      current_none: L.current_none || 'none',
      current_hint: L.current_hint || 'Newest entry per model in ~/.claude.json',
      timeline_title: L.timeline_title || 'Timeline',
      timeline_hint: L.timeline_hint || 'One row per experiment ID, one cell per day. The darker the cell, the more replies that day.',
      legend_less: L.legend_less || 'fewer',
      legend_more: L.legend_more || 'more replies',
      replies: L.replies || 'replies',
      sessions: L.sessions || 'sessions',
      cards_title: L.cards_title || 'Comparison per ID and model',
      hide_insufficient: L.hide_insufficient || 'Hide cards with too little data ({n})',
      no_cards: L.no_cards || 'No model has enough replies under an ID yet for a comparison.',
      verdict_changed: L.verdict_changed || 'Behaviour changed',
      verdict_no_effect: L.verdict_no_effect || 'No clear effect',
      verdict_insufficient: L.verdict_insufficient || 'Too little data',
      col_metric: L.col_metric || 'Metric',
      col_baseline: L.col_baseline || 'Without ID',
      col_experiment: L.col_experiment || 'With ID',
      col_change: L.col_change || 'Change',
      col_ci: L.col_ci || '95% CI',
      col_p: L.col_p || 'p',
      change_na: L.change_na || 'too few events',
      group_behaviour: L.group_behaviour || 'Behaviour (decides the verdict)',
      group_session: L.group_session || 'Per session',
      group_quality: L.group_quality || 'Quality proxies (hints, not a quality verdict)',
      session_starts: L.session_starts || 'Sessions started {from} - {to}',
      rule: L.rule || '"Behaviour changed" = at least {n} of the 4 behaviour metrics move by {pct}% or more with p < {alpha}, given at least {min} replies and {sessions} sessions on each side.',
      reason_few_replies: L.reason_few_replies || 'Too little data: fewer than {min} replies on one side.',
      reason_few_sessions: L.reason_few_sessions || 'Too little data: fewer than {sessions} sessions on one side.',
      reason_few_metrics: L.reason_few_metrics || 'Too little data: fewer than {n} behaviour metrics have enough events to compare.',
      m_multi_tool_share: L.m_multi_tool_share || 'Replies with 2+ tool calls',
      m_text_before_share: L.m_text_before_share || 'Tool replies with text first',
      m_median_bash_chars: L.m_median_bash_chars || 'Median Bash command length',
      m_median_output_tokens: L.m_median_output_tokens || 'Median output tokens per reply',
      m_cost_per_reply: L.m_cost_per_reply || 'Cost per reply (list price incl. cache reads)',
      m_session_cost: L.m_session_cost || 'Median cost per session',
      m_session_replies: L.m_session_replies || 'Median replies per session',
      m_session_prompts: L.m_session_prompts || 'Median prompts per session',
      m_session_tool_calls: L.m_session_tool_calls || 'Median tool calls per session',
      m_session_active_min: L.m_session_active_min || 'Median active minutes per session',
      m_cost_per_prompt: L.m_cost_per_prompt || 'Cost per prompt',
      m_tool_error_rate: L.m_tool_error_rate || 'Tool calls ending in an error',
      m_repeat_call_rate: L.m_repeat_call_rate || 'Repeated identical tool calls',
      m_rejected_rate: L.m_rejected_rate || 'Tool calls rejected by the user',
      m_interrupt_rate: L.m_interrupt_rate || 'Prompts that interrupted a reply',
      m_correction_rate: L.m_correction_rate || 'Prompts that look like corrections',
      m_re_edit_rate: L.m_re_edit_rate || 'Edits of a file already edited',
      card_foot: L.card_foot || 'Without ID: same model without a recorded experiment ID, {from} to {to} ({base} replies in {sessions} sessions). With ID: {n} replies.',
      entrypoints_line: L.entrypoints_line || 'Entrypoints (replies) - with ID: {id}. Without ID: {base}.',
      sdk_excluded: L.sdk_excluded || '{n} SDK replies excluded',
      effort_line: L.effort_line || 'Effort mix with ID: {mix}. Each row reweights the baseline to the ID side\'s mix of that row\'s own base (for example tool replies or Bash commands), over the effort levels both sides have. Per-session rows are not reweighted.',
      unmatched: L.unmatched || '{n} replies at effort levels the baseline lacks are not compared.',
      late_line: L.late_line || 'Replies more than {days} days after session start are dropped: {n} with ID, {base} without.',
      thinking_title: L.thinking_title || 'Thinking tokens per effort level',
      thinking_hint: L.thinking_hint || 'Mean thinking tokens per reply (n = replies counted), by effort level, among replies that report thinking tokens. Hover a cell for the median and the share of replies with any thinking. Cells with fewer than {min} such replies are left out.',
      thinking_cell: L.thinking_cell || 'Median {median}, {share}% of replies with thinking',
      thinking_no_id: L.thinking_no_id || 'No ID',
      method: L.method || 'How the comparison works: replies made under an ID are compared with replies of the same model without a recorded experiment ID, up to {pad} days before and after the days of the ID, as far as the logs reach. Only interactive use counts (a person working in a terminal, an app or an editor); SDK-driven runs are left out. Behaviour rows, cost per reply and the quality proxies are reweighted by effort level: each row uses its own base (for example tool replies, Bash commands, tool calls, prompts or edits) and only the effort levels both sides have. The per-session rows, including cost per prompt, are not reweighted. The verdict rule is printed on every card. A behaviour metric only counts with at least {support} events behind it, otherwise its change reads "too few events". Intervals and p-values treat the session as the unit. Medians of single replies are histogram-based and within about 2%; per-session medians are exact. Cost per reply, the per-session rows and the quality proxies are context and do not enter the verdict.',
      caveats_title: L.caveats_title || 'Caveats',
      caveats: L.caveats || [
        'Latch records in the logs have no timestamp of their own, so the date comes from neighbouring lines.',
        'The latch is the value at session start. Experiments can change mid-session on the server side, so all replies of a session carry one ID, and replies more than {late} days after session start are dropped.',
        'Only the exact record type atis-latch is read.',
        'IDs are shown shortened, the full ID is used internally.',
        'Cost is list price including cache reads.',
        'Subagent transcripts are not counted.',
        'Significance is per session (replies of one session are not independent), and the medians use Woodruff intervals.',
        'None of the metrics measures the quality of the results.',
      ],
    };
  }

  // Table groups in display order. cost_per_reply (group "context") is
  // rendered inside the behaviour group as a context row.
  const GROUPS = ['behaviour', 'session', 'quality'];
  const EFFORT_ORDER = ['low', 'medium', 'high', 'xhigh', 'max', 'unknown'];

  function S() { return window.VCShared; }
  function esc(s) { return S().escHtml(s); }
  function loc() { return S().localeCode(); }

  function fill(tpl, vals) {
    return String(tpl).replace(/\{([a-z]+)\}/g, function(m, k) {
      return Object.prototype.hasOwnProperty.call(vals, k) ? vals[k] : m;
    });
  }

  function num(v, digits) {
    return Number(v).toLocaleString(loc(), {
      minimumFractionDigits: digits, maximumFractionDigits: digits,
    });
  }

  function fmtValue(v, kind) {
    if (v == null || !isFinite(v)) return DASH;
    if (kind === 'share') return num(v * 100, 1) + '%';
    if (kind === 'rate') return num(v * 100, 2) + '%';
    if (kind === 'usd') return S().fmtUSD(v, 4);
    // Small medians keep one decimal (a median of 3.5 prompts is not 4).
    const small = Math.abs(v) < 100 && v !== Math.round(v);
    return num(small ? v : Math.round(v), small ? 1 : 0);
  }

  function fmtChange(c) {
    if (c == null || !isFinite(c)) return DASH;
    const p = Math.round(c * 100);
    return (p > 0 ? '+' : '') + p + '%';
  }

  function fmtCI(lo, hi) {
    if (lo == null || hi == null || !isFinite(lo) || !isFinite(hi)) return DASH;
    return fmtChange(lo) + ' .. ' + fmtChange(hi);
  }

  function fmtP(p) {
    if (p == null || !isFinite(p)) return DASH;
    return p < 0.001 ? '<0.001' : num(p, 3);
  }

  function parseDay(s) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(s || ''));
    return m ? Date.UTC(+m[1], +m[2] - 1, +m[3]) : null;
  }

  function isoDay(ms) { return new Date(ms).toISOString().slice(0, 10); }

  function fmtDay(s, withYear) {
    const ms = parseDay(s);
    if (ms == null) return String(s || '');
    const o = { day: 'numeric', month: 'short', timeZone: 'UTC' };
    if (withYear) o.year = 'numeric';
    try { return new Date(ms).toLocaleDateString(loc(), o); }
    catch (e) { return String(s); }
  }

  function dayRange(a, b) {
    return a === b ? fmtDay(a, true) : fmtDay(a, true) + ' - ' + fmtDay(b, true);
  }

  // ── Pieces ──────────────────────────────────────────────────────

  // anon (F2): chips carry model and short ID only, no tooltip, so no
  // full ID, entrypoint or date can leak into a screenshot.
  function currentRow(current, T, shorts, anon) {
    if (!Array.isArray(current) || !current.length) return '';
    const chips = current.map(function(c) {
      const id = c.id || '';
      const short = id ? (shorts[id] || id.slice(0, 3)) : T.current_none;
      const tip = anon ? '' : ' title="' + esc([id || T.current_none, c.entrypoint,
        c.at ? String(c.at).slice(0, 10) : ''].filter(Boolean).join(' · ')) + '"';
      return '<span class="exp-chip ' + (id ? 'on' : 'off') + '"' + tip + '>'
        + '<span class="exp-chip-m">' + esc(c.model) + '</span>'
        + '<span class="exp-chip-v">' + esc(short) + '</span>'
        + '</span>';
    }).join('');
    return '<div class="exp-current"' + (anon ? '' : ' title="' + esc(T.current_hint) + '"') + '>'
      + '<span class="exp-current-l">' + esc(T.current_title) + '</span>'
      + '<div class="exp-chips">' + chips + '</div></div>';
  }

  function timeline(ids, T, src, anon) {
    let lo = null, hi = null, max = 0;
    ids.forEach(function(e) {
      const a = parseDay(e.first_day), b = parseDay(e.last_day);
      if (a != null && (lo == null || a < lo)) lo = a;
      if (b != null && (hi == null || b > hi)) hi = b;
      Object.keys(e.days || {}).forEach(function(d) {
        const n = dayTotal(e.days[d]);
        if (n > max) max = n;
      });
    });
    if (lo == null || hi == null || hi < lo) return '';
    const days = [];
    for (let t = lo; t <= hi; t += DAY_MS) days.push(isoDay(t));
    const short = days.length <= 90;

    let rows = '';
    ids.forEach(function(e) {
      rows += '<div class="exp-tl-label"' + (anon ? '' : ' title="' + esc(e.id) + '"') + '>'
        + esc(e.short) + '</div>';
      days.forEach(function(d) {
        const cell = (e.days || {})[d];
        const n = dayTotal(cell);
        if (!n) { rows += '<div class="exp-tl-cell empty"></div>'; return; }
        const alpha = (0.18 + 0.82 * (max ? n / max : 0)).toFixed(2);
        const srcText = Object.keys(cell).map(function(s) {
          return src(s) + ' ' + num(cell[s], 0);
        }).join(', ');
        const tip = d + ' · ' + num(n, 0) + ' ' + T.replies + ' · ' + srcText;
        rows += '<div class="exp-tl-cell" style="background:rgba(var(--vc-accent-rgb),' + alpha + ')"'
          + ' title="' + esc(tip) + '"></div>';
      });
    });
    // Axis: first day, then month starts (and mid-month on short ranges),
    // never crowding the first label.
    let axis = '<div class="exp-tl-axis-pad"></div>';
    days.forEach(function(d, i) {
      const dom = +d.slice(8, 10);
      const tick = i === 0 || (i >= 5 && (dom === 1 || (short && dom === 15)));
      axis += '<div class="exp-tl-tick">' + (tick ? '<span>' + esc(fmtDay(d, false)) + '</span>' : '') + '</div>';
    });
    const legend = [0.18, 0.39, 0.59, 0.8, 1].map(function(a) {
      return '<i style="background:rgba(var(--vc-accent-rgb),' + a + ')"></i>';
    }).join('');
    return '<div class="chart-box exp-tl-box">'
      + '<h3>' + esc(T.timeline_title) + '</h3>'
      + '<p class="vc-card-note">' + esc(T.timeline_hint) + '</p>'
      + '<div class="exp-timeline"><div class="exp-tl-grid" style="--exp-days:' + days.length + '">'
      + rows + axis + '</div></div>'
      + '<div class="exp-legend"><span>' + esc(T.legend_less) + '</span>' + legend
      + '<span>' + esc(T.legend_more) + '</span></div>'
      + '</div>';
  }

  function dayTotal(cell) {
    if (!cell || typeof cell !== 'object') return 0;
    return Object.keys(cell).reduce(function(s, k) { return s + (Number(cell[k]) || 0); }, 0);
  }

  function verdictBadge(v, T, tip) {
    const label = v === 'changed' ? T.verdict_changed
      : v === 'no_effect' ? T.verdict_no_effect : T.verdict_insufficient;
    const cls = v === 'changed' ? 'changed' : 'muted';
    return '<span class="exp-badge ' + cls + '" title="' + esc(tip) + '">' + esc(label) + '</span>';
  }

  // Effort levels with their share of the replies, in a fixed order.
  function mixText(mix) {
    const keys = Object.keys(mix || {}).filter(function(k) { return mix[k] > 0; });
    const total = keys.reduce(function(s, k) { return s + mix[k]; }, 0);
    if (!total) return DASH;
    keys.sort(function(a, b) {
      const ia = EFFORT_ORDER.indexOf(a), ib = EFFORT_ORDER.indexOf(b);
      return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
    });
    return keys.map(function(k) {
      const pct = Math.round(100 * mix[k] / total);
      return k + ' ' + (pct < 1 ? '<1' : pct) + '%';
    }).join(', ');
  }

  function epText(eps) {
    const keys = Object.keys(eps || {}).filter(function(k) { return eps[k] > 0; });
    keys.sort(function(a, b) { return eps[b] - eps[a] || (a < b ? -1 : 1); });
    return keys.length ? keys.map(function(k) { return k + ' ' + num(eps[k], 0); }).join(', ') : DASH;
  }

  function tableRow(r, T, cx, cls) {
    const label = T['m_' + r.key] || r.key;
    const behaviour = r.group === 'behaviour';
    // A behaviour row that cannot be judged (too few events, zero
    // baseline) keeps its values but withholds change, CI and p.
    const na = behaviour && !r.comparable;
    const hasChg = r.change != null && isFinite(r.change);
    const sig = behaviour && !na && cx.judged && hasChg
      && Math.abs(r.change) >= cx.rel && r.p != null && r.p < cx.alpha;
    let chg;
    if (na) chg = '<span class="exp-chg na">' + esc(T.change_na) + '</span>';
    else chg = '<span class="exp-chg' + (sig ? ' sig' : '') + '">' + esc(fmtChange(r.change)) + '</span>';
    return '<tr' + (cls ? ' class="' + cls + '"' : '') + '><td>' + esc(label) + '</td>'
      + '<td class="num">' + esc(fmtValue(r.base, r.kind)) + '</td>'
      + '<td class="num">' + esc(fmtValue(r.value, r.kind)) + '</td>'
      + '<td class="num">' + chg + '</td>'
      + '<td class="num exp-ci">' + esc(na ? DASH : fmtCI(r.lo, r.hi)) + '</td>'
      + '<td class="num exp-p">' + esc(na ? DASH : fmtP(r.p)) + '</td></tr>';
  }

  function groupBody(group, rows, T, cx) {
    const own = rows.filter(function(r) { return r.group === group; });
    if (group === 'behaviour') {
      // The cost context row closes the behaviour group, styled as context.
      rows.filter(function(r) { return r.key === 'cost_per_reply'; }).forEach(function(r) {
        own.push(r);
      });
    }
    if (!own.length) return '';
    const head = '<tr class="exp-group-h"><th colspan="6">' + esc(T['group_' + group]) + '</th></tr>';
    return '<tbody>' + head + own.map(function(r) {
      return tableRow(r, T, cx, r.group === 'context' ? 'exp-cost' : '');
    }).join('') + '</tbody>';
  }

  function card(e, m, T, cx, src, anon) {
    const th = cx.th;
    const base = m.baseline || {};
    const rows = Array.isArray(m.rows) ? m.rows : [];
    // Highlight only moves that can count: with too little data nothing
    // is significant, so the loud color would overstate it.
    cx = Object.assign({}, cx, { judged: m.verdict === 'changed' || m.verdict === 'no_effect' });

    const tables = GROUPS.map(function(g) { return groupBody(g, rows, T, cx); }).join('');

    const ruleText = fill(T.rule, cx.vals);
    let tip = ruleText;
    if (m.verdict === 'insufficient' && m.reason && T['reason_' + m.reason]) {
      tip += ' ' + fill(T['reason_' + m.reason], cx.vals);
    }

    // Days this ID ran on this model, not the ID-wide range.
    const meta = [dayRange(m.first_day || e.first_day, m.last_day || e.last_day)];
    if (m.session_start_from && m.session_start_to) {
      meta.push(fill(T.session_starts, {
        from: fmtDay(m.session_start_from, true), to: fmtDay(m.session_start_to, true) }));
    }
    meta.push((e.sources || []).map(src).join(', '));
    meta.push(num(m.sessions != null ? m.sessions : (e.sessions || 0), 0) + ' ' + T.sessions);

    let foot = '<p>' + esc(fill(T.card_foot, {
      from: fmtDay(base.from, true), to: fmtDay(base.to, true),
      base: num(base.replies || 0, 0), sessions: num(base.sessions || 0, 0),
      n: num(m.replies || 0, 0),
    })) + '</p>';
    let eps = fill(T.entrypoints_line, { id: epText(m.entrypoints), base: epText(m.base_entrypoints) });
    if (m.base_sdk_replies > 0) eps += ' ' + fill(T.sdk_excluded, { n: num(m.base_sdk_replies, 0) }) + '.';
    foot += '<p class="exp-eps">' + esc(eps) + '</p>';
    let eff = fill(T.effort_line, { mix: mixText(m.effort_mix) });
    foot += '<p class="exp-effort">' + esc(eff);
    if (m.unmatched_replies > 0) {
      foot += ' <span class="exp-unmatched">' + esc(fill(T.unmatched, { n: num(m.unmatched_replies, 0) })) + '</span>';
    }
    foot += '</p>';
    if ((m.late_replies || 0) + (m.base_late_replies || 0) > 0) {
      foot += '<p class="exp-late">' + esc(fill(T.late_line, {
        days: cx.vals.days, n: num(m.late_replies || 0, 0), base: num(m.base_late_replies || 0, 0),
      })) + '</p>';
    }
    foot += '<p class="exp-rule">' + esc(ruleText) + '</p>';

    const cls = m.verdict === 'insufficient' ? ' exp-card--insufficient' : '';
    return '<article class="chart-box exp-card' + cls + '">'
      + '<header class="exp-card-h">'
      + '<span class="exp-id"' + (anon ? '' : ' title="' + esc(e.id) + '"') + '>' + esc(e.short) + '</span>'
      + '<span class="exp-model">' + esc(m.model) + '</span>'
      + verdictBadge(m.verdict, T, tip)
      + '</header>'
      + '<div class="exp-card-meta">' + meta.filter(Boolean).map(esc).join(' · ') + '</div>'
      + '<div class="exp-table-wrap"><table class="exp-table"><thead><tr>'
      + '<th>' + esc(T.col_metric) + '</th><th class="num">' + esc(T.col_baseline) + '</th>'
      + '<th class="num">' + esc(T.col_experiment) + '</th><th class="num">' + esc(T.col_change) + '</th>'
      + '<th class="num">' + esc(T.col_ci) + '</th><th class="num exp-p">' + esc(T.col_p) + '</th>'
      + '</tr></thead>' + tables + '</table></div>'
      + '<div class="exp-card-foot">' + foot + '</div>'
      + '</article>';
  }

  // One table per model: rows "No ID" + IDs, one column per effort level
  // that has a cell, "median (n)" in each.
  function thinkingBox(thinking, T, th) {
    if (!Array.isArray(thinking) || !thinking.length) return '';
    const tables = thinking.map(function(t) {
      const rows = t.rows || [];
      const levels = EFFORT_ORDER.filter(function(l) {
        return rows.some(function(r) { return r.cells && r.cells[l]; });
      });
      if (!levels.length) return '';
      const head = '<tr><th>' + esc(t.model) + '</th>' + levels.map(function(l) {
        return '<th class="num">' + esc(l) + '</th>';
      }).join('') + '</tr>';
      const body = rows.map(function(r) {
        return '<tr><td>' + esc(r.id ? r.short : T.thinking_no_id) + '</td>' + levels.map(function(l) {
          const c = r.cells && r.cells[l];
          if (!c) return '<td class="num">' + DASH + '</td>';
          // Mean is the headline (most replies report 0 thinking tokens, so
          // the median is mostly 0); median and share go into the tooltip.
          const tip = c.nonzero_share == null ? '' : ' title="' + esc(fill(T.thinking_cell, {
            median: num(c.median, 0), share: String(Math.round(c.nonzero_share * 100)) })) + '"';
          return '<td class="num"' + tip + '>' + esc(num(c.mean, 0) + ' (n=' + num(c.replies, 0) + ')') + '</td>';
        }).join('') + '</tr>';
      }).join('');
      return '<div class="exp-table-wrap"><table class="exp-table exp-think-table"><thead>' + head
        + '</thead><tbody>' + body + '</tbody></table></div>';
    }).join('');
    if (!tables) return '';
    return '<div class="chart-box exp-think">'
      + '<h3>' + esc(T.thinking_title) + '</h3>'
      + '<p class="vc-card-note">' + esc(fill(T.thinking_hint, {
        min: num(th.think_min_replies != null ? th.think_min_replies : 20, 0) })) + '</p>'
      + tables + '</div>';
  }

  // ── Public ──────────────────────────────────────────────────────

  // opts = {anon: bool, anonSource: fn} masks source labels and drops
  // full IDs from tooltips (F2 mode).
  function html(exp, L, opts) {
    const T = texts(L);
    const anon = !!(opts && opts.anon && typeof opts.anonSource === 'function');
    const src = function(name) { return anon ? opts.anonSource(name) : name; };
    const current = (exp && exp.current) || [];
    const ids = (exp && Array.isArray(exp.ids)) ? exp.ids : [];
    const shorts = {};
    ids.forEach(function(e) { shorts[e.id] = e.short; });

    if (!exp || !exp.has_data) {
      return '<div class="exp">'
        + '<div class="chart-box exp-intro-box">'
        + '<p class="exp-empty">' + esc(T.empty) + '</p>'
        + '<p class="exp-intro muted">' + esc(T.intro) + '</p>'
        + currentRow(current, T, shorts, anon)
        + '</div></div>';
    }

    const th = exp.thresholds || {};
    const rel = th.rel_change != null ? Number(th.rel_change) : 0.4;
    const alpha = th.alpha != null ? Number(th.alpha) : 0.05;
    const vals = {
      n: String(th.min_changed_metrics != null ? th.min_changed_metrics : 2),
      pct: String(Math.round(rel * 100)),
      alpha: String(alpha),
      min: num(th.min_replies != null ? th.min_replies : 200, 0),
      sessions: num(th.min_sessions != null ? th.min_sessions : 5, 0),
      days: String(th.late_cutoff_days != null ? th.late_cutoff_days : 7),
      late: String(th.late_cutoff_days != null ? th.late_cutoff_days : 7),
      pad: String(th.baseline_pad_days != null ? th.baseline_pad_days : 14),
      support: num(th.min_support != null ? th.min_support : 30, 0),
    };
    const cx = { rel: rel, alpha: alpha, vals: vals, th: th };

    let cards = '', nInsufficient = 0, nJudged = 0;
    ids.forEach(function(e) {
      (e.models || []).forEach(function(m) {
        if ((m.replies || 0) < MIN_CARD_REPLIES) return;
        cards += card(e, m, T, cx, src, anon);
        if (m.verdict === 'insufficient') nInsufficient++; else nJudged++;
      });
    });
    // Only offer the switch when it leaves something to show.
    const hideSwitch = (nInsufficient && nJudged)
      ? '<label class="vc-checkbox exp-hide-switch"><input type="checkbox" data-exp-hide-insufficient />'
        + '<span>' + esc(fill(T.hide_insufficient, { n: String(nInsufficient) })) + '</span></label>'
      : '';

    const method = fill(T.method, vals);
    const caveats = (Array.isArray(T.caveats) ? T.caveats : []).map(function(c) {
      return '<li>' + esc(fill(c, vals)) + '</li>';
    }).join('');

    return '<div class="exp">'
      + '<div class="chart-box exp-intro-box">'
      + '<p class="exp-intro">' + esc(T.intro) + '</p>'
      + currentRow(current, T, shorts, anon)
      + '</div>'
      + timeline(ids, T, src, anon)
      + '<div class="exp-cards-bar"><h3 class="exp-cards-h">' + esc(T.cards_title) + '</h3>' + hideSwitch + '</div>'
      + (cards ? '<div class="exp-cards">' + cards + '</div>'
               : '<p class="exp-none">' + esc(T.no_cards) + '</p>')
      + thinkingBox(exp.thinking, T, th)
      + '<p class="exp-method">' + esc(method) + '</p>'
      + '<div class="exp-caveats-box"><h4 class="exp-caveats-h">' + esc(T.caveats_title) + '</h4>'
      + '<ul class="exp-caveats">' + caveats + '</ul></div>'
      + '</div>';
  }

  function render(exp, rootEl, opts) {
    if (!rootEl) return;
    const L = (window.__LOCALE__ && window.__LOCALE__.experiments) || {};
    rootEl.innerHTML = html(exp, L, opts);
    // "Hide cards with too little data": remembered per browser, re-applied
    // on every render (the section re-renders on filter changes).
    const box = rootEl.querySelector('[data-exp-hide-insufficient]');
    const wrap = rootEl.querySelector('.exp');
    if (!box || !wrap) return;
    let on = false;
    try { on = localStorage.getItem(HIDE_KEY) === '1'; } catch (err) {}
    const apply = function() { wrap.classList.toggle('exp--hide-insufficient', box.checked); };
    box.checked = on;
    apply();
    box.addEventListener('change', function() {
      apply();
      try { localStorage.setItem(HIDE_KEY, box.checked ? '1' : '0'); } catch (err) {}
    });
  }

  window.VCExperiments = { html: html, render: render };
})();
