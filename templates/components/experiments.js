// ── Insights: Experiments (VCExperiments) ───────────────────────
// Renders D.experiments (claudestats_core/experiments.py
// build_experiment_summary) into the Insights "Experiments" section:
// intro, current assignment chips, a per-day timeline per ID and one
// comparison card per ID x model. Full-range data, so it ignores the
// date/project filter. html() is pure (testable in Node); render()
// reads the locale and writes into the root element.
(function() {
  'use strict';

  const MIN_CARD_REPLIES = 20;   // display cutoff, not the verdict threshold
  const DAY_MS = 86400000;
  const DASH = '-';

  // Every UI string with its English fallback. Keep all locale reads as
  // literal property reads on L so the locale-key test can find them.
  function texts(L) {
    L = L || {};
    return {
      intro: L.intro || 'Anthropic sometimes tests changed behaviour on part of its users, and Claude Code records the ID of such an experiment in the session logs. This section compares replies made under an ID with replies of the same model without a recorded experiment ID. Keep in mind: the work itself differed between the periods, this measures how the model worked, not whether the results were better, and thinking and effort are not in the logs.',
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
      no_cards: L.no_cards || 'No model has enough replies under an ID yet for a comparison.',
      verdict_changed: L.verdict_changed || 'Behaviour changed',
      verdict_no_effect: L.verdict_no_effect || 'No clear effect',
      verdict_insufficient: L.verdict_insufficient || 'Too little data',
      col_metric: L.col_metric || 'Metric',
      col_baseline: L.col_baseline || 'Without ID',
      col_experiment: L.col_experiment || 'With ID',
      col_change: L.col_change || 'Change',
      change_na: L.change_na || 'too few events',
      m_multi_tool_share: L.m_multi_tool_share || 'Replies with 2+ tool calls',
      m_text_before_share: L.m_text_before_share || 'Tool replies with text first',
      m_median_bash_chars: L.m_median_bash_chars || 'Median Bash command length',
      m_median_output_tokens: L.m_median_output_tokens || 'Median output tokens per reply',
      m_cost_per_reply: L.m_cost_per_reply || 'Cost per reply',
      card_foot: L.card_foot || 'Without ID: same model without a recorded experiment ID, {from} to {to} ({base} replies). With ID: {n} replies.',
      method: L.method || 'Verdict: "Behaviour changed" means at least {n} of the four behaviour metrics moved by {pct}% or more, with at least {min} replies on both sides. "Too little data" means fewer replies than that, or fewer than {n} metrics that could be compared. A metric only counts with at least {support} events behind it: replies with 2+ tool calls on one side or the other, tool replies on each side plus text-first replies on one side, Bash commands on each side. Otherwise its change reads "too few events". The comparison uses the same model without a recorded experiment ID, up to {pad} days before and after, as far as the logs reach. Medians are approximate (histogram-based, within about 10%). Cost per reply is context only and does not count.',
    };
  }

  const METRICS = [
    { key: 'multi_tool_share', kind: 'share' },
    { key: 'text_before_share', kind: 'share' },
    { key: 'median_bash_chars', kind: 'int' },
    { key: 'median_output_tokens', kind: 'int' },
  ];

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
    if (kind === 'usd') return S().fmtUSD(v, 4);
    return num(Math.round(v), 0);
  }

  function fmtChange(c) {
    if (c == null || !isFinite(c)) return DASH;
    const p = Math.round(c * 100);
    return (p > 0 ? '+' : '') + p + '%';
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

  function currentRow(current, T) {
    if (!Array.isArray(current) || !current.length) return '';
    const chips = current.map(function(c) {
      const id = c.id || '';
      const tip = [id || T.current_none, c.entrypoint, c.at ? String(c.at).slice(0, 10) : '']
        .filter(Boolean).join(' · ');
      return '<span class="exp-chip ' + (id ? 'on' : 'off') + '" title="' + esc(tip) + '">'
        + '<span class="exp-chip-m">' + esc(c.model) + '</span>'
        + '<span class="exp-chip-v">' + esc(id ? id.slice(0, 3) : T.current_none) + '</span>'
        + '</span>';
    }).join('');
    return '<div class="exp-current" title="' + esc(T.current_hint) + '">'
      + '<span class="exp-current-l">' + esc(T.current_title) + '</span>'
      + '<div class="exp-chips">' + chips + '</div></div>';
  }

  function timeline(ids, T, src) {
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
      rows += '<div class="exp-tl-label" title="' + esc(e.id) + '">' + esc(e.short) + '</div>';
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

  function verdictBadge(v, T) {
    const label = v === 'changed' ? T.verdict_changed
      : v === 'no_effect' ? T.verdict_no_effect : T.verdict_insufficient;
    const cls = v === 'changed' ? 'changed' : 'muted';
    return '<span class="exp-badge ' + cls + '">' + esc(label) + '</span>';
  }

  function card(e, m, T, rel, src) {
    const mx = m.metrics || {};
    const base = m.baseline || {};
    const bx = base.metrics || {};
    const changes = m.changes || {};
    // Highlight only moves that can count: with too little data nothing
    // is significant, so the loud color would overstate it.
    const judged = m.verdict === 'changed' || m.verdict === 'no_effect';
    let body = '';
    METRICS.forEach(function(spec) {
      const c = changes[spec.key];
      // null: too few events (or no baseline value) to compare, so the
      // values stay visible but the change is withheld.
      const na = c == null || !isFinite(c);
      const sig = judged && !na && Math.abs(c) >= rel;
      const chg = na ? '<span class="exp-chg na">' + esc(T.change_na) + '</span>'
        : '<span class="exp-chg' + (sig ? ' sig' : '') + '">' + esc(fmtChange(c)) + '</span>';
      body += '<tr><td>' + esc(T['m_' + spec.key]) + '</td>'
        + '<td class="num">' + esc(fmtValue(bx[spec.key], spec.kind)) + '</td>'
        + '<td class="num">' + esc(fmtValue(mx[spec.key], spec.kind)) + '</td>'
        + '<td class="num">' + chg + '</td></tr>';
    });
    const bc = bx.cost_per_reply, ec = mx.cost_per_reply;
    const costChg = (bc > 0 && ec != null) ? (ec - bc) / bc : null;
    body += '<tr class="exp-cost"><td>' + esc(T.m_cost_per_reply) + '</td>'
      + '<td class="num">' + esc(fmtValue(bc, 'usd')) + '</td>'
      + '<td class="num">' + esc(fmtValue(ec, 'usd')) + '</td>'
      + '<td class="num"><span class="exp-chg">' + esc(fmtChange(costChg)) + '</span></td></tr>';

    // Days this ID ran on this model, not the ID-wide range.
    const meta = [dayRange(m.first_day || e.first_day, m.last_day || e.last_day),
      (e.sources || []).map(src).join(', '),
      num(e.sessions || 0, 0) + ' ' + T.sessions].filter(Boolean);
    const foot = fill(T.card_foot, {
      from: fmtDay(base.from, true), to: fmtDay(base.to, true),
      base: num(base.replies || 0, 0), n: num(m.replies || 0, 0),
    });
    return '<article class="chart-box exp-card">'
      + '<header class="exp-card-h">'
      + '<span class="exp-id" title="' + esc(e.id) + '">' + esc(e.short) + '</span>'
      + '<span class="exp-model">' + esc(m.model) + '</span>'
      + verdictBadge(m.verdict, T)
      + '</header>'
      + '<div class="exp-card-meta">' + meta.map(esc).join(' · ') + '</div>'
      + '<table class="exp-table"><thead><tr>'
      + '<th>' + esc(T.col_metric) + '</th><th class="num">' + esc(T.col_baseline) + '</th>'
      + '<th class="num">' + esc(T.col_experiment) + '</th><th class="num">' + esc(T.col_change) + '</th>'
      + '</tr></thead><tbody>' + body + '</tbody></table>'
      + '<p class="exp-card-foot">' + esc(foot) + '</p>'
      + '</article>';
  }

  // ── Public ──────────────────────────────────────────────────────

  // opts = {anon: bool, anonSource: fn} masks source labels (F2 mode).
  function html(exp, L, opts) {
    const T = texts(L);
    const anon = !!(opts && opts.anon && typeof opts.anonSource === 'function');
    const src = function(name) { return anon ? opts.anonSource(name) : name; };
    const current = (exp && exp.current) || [];

    if (!exp || !exp.has_data) {
      return '<div class="exp">'
        + '<div class="chart-box exp-intro-box">'
        + '<p class="exp-empty">' + esc(T.empty) + '</p>'
        + '<p class="exp-intro muted">' + esc(T.intro) + '</p>'
        + currentRow(current, T)
        + '</div></div>';
    }

    const ids = Array.isArray(exp.ids) ? exp.ids : [];
    const th = exp.thresholds || {};
    const rel = th.rel_change != null ? Number(th.rel_change) : 0.4;

    let cards = '';
    ids.forEach(function(e) {
      (e.models || []).forEach(function(m) {
        if ((m.replies || 0) >= MIN_CARD_REPLIES) cards += card(e, m, T, rel, src);
      });
    });

    const method = fill(T.method, {
      min: num(th.min_replies != null ? th.min_replies : 200, 0),
      pct: String(Math.round(rel * 100)),
      n: String(th.min_changed_metrics != null ? th.min_changed_metrics : 2),
      pad: String(th.baseline_pad_days != null ? th.baseline_pad_days : 14),
      support: num(th.min_support != null ? th.min_support : 30, 0),
    });

    return '<div class="exp">'
      + '<div class="chart-box exp-intro-box">'
      + '<p class="exp-intro">' + esc(T.intro) + '</p>'
      + currentRow(current, T)
      + '</div>'
      + timeline(ids, T, src)
      + '<h3 class="exp-cards-h">' + esc(T.cards_title) + '</h3>'
      + (cards ? '<div class="exp-cards">' + cards + '</div>'
               : '<p class="exp-none">' + esc(T.no_cards) + '</p>')
      + '<p class="exp-method">' + esc(method) + '</p>'
      + '</div>';
  }

  function render(exp, rootEl, opts) {
    if (!rootEl) return;
    const L = (window.__LOCALE__ && window.__LOCALE__.experiments) || {};
    rootEl.innerHTML = html(exp, L, opts);
  }

  window.VCExperiments = { html: html, render: render };
})();
