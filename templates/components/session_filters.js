// ── Session Filters Component ───────────────────────────────────
// Reusable filter module mounted above the session table. Owns its
// own UI, state and localStorage persistence. Consumers call
// getActiveFiltersList() and feed the predicates into their
// existing session-filtering pipeline.
(function() {
  'use strict';

  function sfL(key, fallback) {
    const sec = (typeof window !== 'undefined' && window.__LOCALE__ && window.__LOCALE__.sessions_tab) || {};
    return sec[key] != null ? sec[key] : fallback;
  }

  // ── Attribute spec ─────────────────────────────────────────
  // scale: 'linear' | 'log'
  // get(s): returns a finite number, never null
  const ATTRIBUTES = [
    { id: 'user_messages',  group: 'volume',   label: 'User Msgs',
      get: (s) => s.user_messages || 0,
      scale: 'linear', step: 1, unit: '' },
    { id: 'messages',       group: 'volume',   label: 'Messages',
      get: (s) => s.messages || 0,
      scale: 'linear', step: 1, unit: '' },
    { id: 'duration_min',   group: 'volume',   label: 'Duration',
      get: (s) => s.duration_min || 0,
      scale: 'linear', step: 1, unit: 'min' },
    { id: 'total_tokens',   group: 'tokens',   label: 'Total Tokens',
      get: (s) => (s.input_tokens||0) + (s.output_tokens||0)
                  + (s.cache_read_tokens||0) + (s.cache_write_tokens||0),
      scale: 'log', step: 1, unit: '' },
    { id: 'cost',           group: 'cost',     label: 'Cost',
      get: (s) => Number(s.cost) || 0,
      scale: 'log', step: 0.01, unit: 'USD' },
    { id: 'cache_eff',      group: 'cache',    label: 'Cache Eff.',
      get: (s) => {
        const sum = (s.input_tokens||0) + (s.cache_read_tokens||0) + (s.cache_write_tokens||0);
        if (sum === 0) return 0;
        return Math.round((s.cache_read_tokens||0) / sum * 100);
      },
      scale: 'linear', step: 1, unit: '%' },
    { id: 'tool_calls',     group: 'activity', label: 'Tool Calls',
      get: (s) => {
        if (!s.tools) return 0;
        let n = 0;
        for (const k in s.tools) n += s.tools[k] || 0;
        return n;
      },
      scale: 'log', step: 1, unit: '' },
    { id: 'agent_dispatches', group: 'activity', label: 'Agent Dispatches',
      get: (s) => Array.isArray(s.agent_dispatches) ? s.agent_dispatches.length : 0,
      scale: 'log', step: 1, unit: '' },
    { id: 'errors',         group: 'errors',   label: 'Error Count',
      get: (s) => s.error_count || 0,
      scale: 'linear', step: 1, unit: '' },
  ];
  const ATTRIBUTES_BY_ID = {};
  ATTRIBUTES.forEach(a => { ATTRIBUTES_BY_ID[a.id] = a; });
  ATTRIBUTES.forEach(a => { a.label = sfL('f_' + a.id, a.label); });

  const GROUP_ORDER = ['volume','tokens','cost','cache','activity','errors'];
  const GROUP_LABELS = {
    volume: sfL('group_volume', 'Volume'),
    tokens: sfL('group_tokens', 'Tokens'),
    cost: sfL('group_cost', 'Cost'),
    cache: sfL('group_cache', 'Cache Health'),
    activity: sfL('group_activity', 'Activity'),
    errors: sfL('group_errors', 'Errors'),
  };

  // ── Range computation ──────────────────────────────────────
  const NICE_STEPS = [1, 2, 5, 10, 20, 50, 100, 200, 500,
                      1000, 2000, 5000, 10000, 20000, 50000,
                      100000, 200000, 500000, 1000000, 2000000,
                      5000000, 10000000];

  function niceCeil(value) {
    if (!isFinite(value) || value <= 0) return 1;
    for (const s of NICE_STEPS) {
      if (s >= value) return s;
    }
    // Beyond the predefined table: snap up to the next power of 10
    // so very heavy sessions still get a sensible slider max.
    return Math.pow(10, Math.ceil(Math.log10(value)));
  }

  function percentile(sorted, p) {
    if (sorted.length === 0) return 0;
    if (sorted.length === 1) return sorted[0];
    const idx = (sorted.length - 1) * p;
    const lo = Math.floor(idx), hi = Math.ceil(idx);
    if (lo === hi) return sorted[lo];
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
  }

  function computeRanges(sessions) {
    const out = {};
    ATTRIBUTES.forEach(a => {
      const vals = sessions.map(a.get).filter(v => Number.isFinite(v));
      if (vals.length === 0) { out[a.id] = { min: 0, max: 0 }; return; }
      vals.sort((x, y) => x - y);
      const p99 = percentile(vals, 0.99);
      let hi;
      if (a.unit === 'USD') {
        // Cents-precise nice ceil so cost sliders don't snap to $1.
        hi = Math.max(1, Math.ceil(p99 * 100) / 100);
        if (hi > 1) hi = niceCeil(hi);
      } else if (a.unit === '%') {
        hi = 100;
      } else {
        hi = niceCeil(p99 || 1);
      }
      out[a.id] = { min: 0, max: hi };
    });
    return out;
  }

  // Slider position is always integer 0-1000. We convert to/from the
  // attribute's domain using either linear or log10(value + 1).
  const SLIDER_RES = 1000;

  function valueToPos(attr, range, value) {
    if (range.max <= range.min) return 0;
    let v = Math.max(range.min, Math.min(range.max, value));
    if (attr.scale === 'log') {
      const a = Math.log10(range.min + 1);
      const b = Math.log10(range.max + 1);
      if (b <= a) return 0;
      return Math.round((Math.log10(v + 1) - a) / (b - a) * SLIDER_RES);
    }
    return Math.round((v - range.min) / (range.max - range.min) * SLIDER_RES);
  }

  function posToValue(attr, range, pos) {
    if (range.max <= range.min) return range.min;
    const t = Math.max(0, Math.min(SLIDER_RES, pos)) / SLIDER_RES;
    if (attr.scale === 'log') {
      const a = Math.log10(range.min + 1);
      const b = Math.log10(range.max + 1);
      const raw = Math.pow(10, a + (b - a) * t) - 1;
      return snap(attr, raw);
    }
    return snap(attr, range.min + (range.max - range.min) * t);
  }

  function snap(attr, v) {
    if (attr.step >= 1) return Math.round(v / attr.step) * attr.step;
    const inv = 1 / attr.step;
    return Math.round(v * inv) / inv;
  }

  // ── Storage helpers ─────────────────────────────────────────
  function storageKey(context) {
    return 'sessionFilters.' + context;
  }
  function loadState(context) {
    try {
      const raw = localStorage.getItem(storageKey(context));
      if (raw == null) return null;
      return JSON.parse(raw);
    } catch (e) { return null; }
  }
  function saveState(context, value) {
    try { localStorage.setItem(storageKey(context), JSON.stringify(value)); }
    catch (e) {}
  }

  // ── Mount ──────────────────────────────────────────────────
  function mountSessionFilters(container, options) {
    options = options || {};
    const ctx = { context: options.context || 'dashboard' };
    const getPool = options.getPool || function() { return []; };
    const onChange = options.onChange || function() {};

    // ── State ────────────────────────────────────────────────
    // Shape: { user_messages: {min, max}, ..., panelOpen: bool }
    // null on min/max means "unbounded on that side"
    let state = loadState(ctx.context) || {};
    state.panelOpen = !!state.panelOpen;
    ATTRIBUTES.forEach(a => {
      if (!state[a.id] || typeof state[a.id] !== 'object') {
        state[a.id] = { min: null, max: null };
      } else {
        if (typeof state[a.id].min !== 'number') state[a.id].min = null;
        if (typeof state[a.id].max !== 'number') state[a.id].max = null;
      }
    });
    // Drop unknown attribute keys from older releases
    Object.keys(state).forEach(k => {
      if (k === 'panelOpen') return;
      if (!ATTRIBUTES_BY_ID[k]) delete state[k];
    });

    let notifyTimer = null;
    function scheduleNotify() {
      if (notifyTimer) clearTimeout(notifyTimer);
      notifyTimer = setTimeout(() => { notifyTimer = null; notifyChange(); }, 200);
    }

    function persist() { saveState(ctx.context, state); }

    function setBound(attrId, side, value) {
      const cur = state[attrId];
      if (!cur) return;
      cur[side] = (value == null || isNaN(value)) ? null : Number(value);
      persist();
    }

    function clearAttr(attrId) {
      if (!state[attrId]) return;
      state[attrId].min = null;
      state[attrId].max = null;
      persist();
    }

    function clearAll() {
      ATTRIBUTES.forEach(a => { state[a.id].min = null; state[a.id].max = null; });
      persist();
    }

    function activeCount() {
      let n = 0;
      ATTRIBUTES.forEach(a => {
        const v = state[a.id];
        if (v && (v.min != null || v.max != null)) n++;
      });
      return n;
    }

    let ranges = computeRanges(getPool());

    function refreshRanges() {
      ranges = computeRanges(getPool());
      // Stored bounds stay exactly as the user set them. Sliders clamp
      // visually via valueToPos and predicates use the raw values, so a
      // pool change (range switch, empty pool) must never rewrite or
      // persist user filters.
    }

    // ── DOM scaffold ────────────────────────────────────────
    const wrapper = document.createElement('div');
    wrapper.className = 'sf-wrapper';
    wrapper.setAttribute('data-context', ctx.context);
    container.appendChild(wrapper);

    const toolbar = document.createElement('div');
    toolbar.className = 'sf-toolbar';
    wrapper.appendChild(toolbar);

    const chipsRow = document.createElement('div');
    chipsRow.className = 'sf-chips';
    wrapper.appendChild(chipsRow);

    const panelHost = document.createElement('div');
    panelHost.className = 'sf-panel-host';
    wrapper.appendChild(panelHost);

    // Preset configs.
    const PRESETS = [
      { id: 'real',     label: sfL('preset_real', 'Real sessions only'),
        apply:  () => { state.user_messages.min = 2; persist(); },
        clear:  () => { state.user_messages.min = null; persist(); },
        isOn:   () => state.user_messages.min === 2 },
      { id: 'expensive', label: sfL('preset_costly', 'Costly sessions only'),
        apply:  () => { state.cost.min = 1.00; persist(); },
        clear:  () => { state.cost.min = null; persist(); },
        isOn:   () => state.cost.min === 1.00 },
    ];

    function renderToolbar() {
      toolbar.innerHTML = '';
      PRESETS.forEach(p => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'sf-preset' + (p.isOn() ? ' is-on' : '');
        b.textContent = p.label;
        b.addEventListener('click', () => {
          if (p.isOn()) p.clear(); else p.apply();
          renderAll();
          notifyChange();
        });
        toolbar.appendChild(b);
      });

      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'sf-toggle' + (state.panelOpen ? ' is-open' : '');
      const n = activeCount();
      toggle.innerHTML = '&#9881; ' + sfL('more_filters', 'More filters')
        + (n > 0 ? ' (' + n + ')' : '')
        + ' <span class="sf-caret">' + (state.panelOpen ? '▴' : '▾') + '</span>';
      toggle.addEventListener('click', () => {
        state.panelOpen = !state.panelOpen;
        persist();
        renderAll();
      });
      toolbar.appendChild(toggle);
    }

    function chipText(attr, v) {
      const fmt = (n) => attr.unit === 'USD' ? n.toFixed(2) : String(n);
      if (v.min != null && v.max != null) return attr.label + ' ' + fmt(v.min) + '–' + fmt(v.max);
      if (v.min != null) return attr.label + ' ≥' + fmt(v.min);
      if (v.max != null) return attr.label + ' ≤' + fmt(v.max);
      return attr.label;
    }

    function renderChips() {
      chipsRow.innerHTML = '';
      const active = ATTRIBUTES.filter(a => {
        const v = state[a.id];
        return v && (v.min != null || v.max != null);
      });
      if (active.length === 0) return;
      active.forEach(a => {
        const c = document.createElement('span');
        c.className = 'sf-chip';
        const txt = document.createElement('span');
        txt.textContent = chipText(a, state[a.id]);
        c.appendChild(txt);
        const x = document.createElement('button');
        x.type = 'button';
        x.className = 'sf-chip-x';
        x.innerHTML = '&times;';
        x.setAttribute('aria-label', sfL('clear_aria_prefix', 'Clear ') + a.label);
        x.addEventListener('click', () => {
          clearAttr(a.id);
          renderAll();
          notifyChange();
        });
        c.appendChild(x);
        chipsRow.appendChild(c);
      });
      const ca = document.createElement('button');
      ca.type = 'button';
      ca.className = 'sf-clear-all';
      ca.textContent = sfL('clear_all', 'Clear all');
      ca.addEventListener('click', () => {
        clearAll();
        renderAll();
        notifyChange();
      });
      chipsRow.appendChild(ca);
    }

    function renderPanel() {
      panelHost.innerHTML = '';
      if (!state.panelOpen) return;

      const panel = document.createElement('div');
      panel.className = 'sf-panel';

      GROUP_ORDER.forEach(g => {
        const attrs = ATTRIBUTES.filter(a => a.group === g);
        if (attrs.length === 0) return;
        const grp = document.createElement('div');
        grp.className = 'sf-group';
        const h = document.createElement('div');
        h.className = 'sf-group-h';
        h.textContent = GROUP_LABELS[g];
        grp.appendChild(h);
        attrs.forEach(a => grp.appendChild(buildRow(a)));
        panel.appendChild(grp);
      });

      const actions = document.createElement('div');
      actions.className = 'sf-panel-actions';
      const reset = document.createElement('button');
      reset.type = 'button';
      reset.className = 'sf-action';
      reset.textContent = sfL('reset', 'Reset');
      reset.addEventListener('click', () => {
        clearAll();
        renderAll();
        notifyChange();
      });
      const closeBtn = document.createElement('button');
      closeBtn.type = 'button';
      closeBtn.className = 'sf-action';
      closeBtn.textContent = sfL('close', 'Close');
      closeBtn.addEventListener('click', () => {
        state.panelOpen = false;
        persist();
        renderAll();
      });
      actions.appendChild(reset);
      actions.appendChild(closeBtn);
      panel.appendChild(actions);

      panelHost.appendChild(panel);
    }

    function buildRow(attr) {
      const r = ranges[attr.id];
      const v = state[attr.id];
      const row = document.createElement('div');
      row.className = 'sf-row';

      const lbl = document.createElement('label');
      lbl.className = 'sf-row-label';
      lbl.textContent = attr.label + (attr.unit ? ' (' + attr.unit + ')' : '');
      row.appendChild(lbl);

      // Two-handle slider as two <input type=range> stacked.
      const track = document.createElement('div');
      track.className = 'sf-track';
      const sMin = document.createElement('input');
      sMin.type = 'range';
      sMin.min = 0; sMin.max = SLIDER_RES; sMin.step = 1;
      sMin.className = 'sf-slider sf-slider-min';
      sMin.value = valueToPos(attr, r, v.min != null ? v.min : r.min);
      sMin.setAttribute('aria-label', attr.label + sfL('min_aria_suffix', ' minimum'));
      const sMax = document.createElement('input');
      sMax.type = 'range';
      sMax.min = 0; sMax.max = SLIDER_RES; sMax.step = 1;
      sMax.className = 'sf-slider sf-slider-max';
      sMax.value = valueToPos(attr, r, v.max != null ? v.max : r.max);
      sMax.setAttribute('aria-label', attr.label + sfL('max_aria_suffix', ' maximum'));
      track.appendChild(sMin);
      track.appendChild(sMax);
      row.appendChild(track);

      const iMin = document.createElement('input');
      iMin.type = 'number';
      iMin.className = 'sf-num sf-num-min';
      iMin.placeholder = sfL('min_placeholder', 'min');
      iMin.step = attr.step;
      if (v.min != null) iMin.value = v.min;
      const iMax = document.createElement('input');
      iMax.type = 'number';
      iMax.className = 'sf-num sf-num-max';
      iMax.placeholder = sfL('max_placeholder', 'max');
      iMax.step = attr.step;
      if (v.max != null) iMax.value = v.max;
      row.appendChild(iMin);
      row.appendChild(iMax);

      function commit(side, raw) {
        const num = (raw === '' || raw == null) ? null : Number(raw);
        if (num == null || isNaN(num)) { setBound(attr.id, side, null); }
        else { setBound(attr.id, side, num); }
        // Keep slider thumbs in sync with input values
        sMin.value = valueToPos(attr, r, state[attr.id].min != null ? state[attr.id].min : r.min);
        sMax.value = valueToPos(attr, r, state[attr.id].max != null ? state[attr.id].max : r.max);
        scheduleNotify();
        renderToolbar();
        renderChips();
      }

      sMin.addEventListener('input', () => {
        const val = posToValue(attr, r, Number(sMin.value));
        let other = state[attr.id].max != null ? state[attr.id].max : r.max;
        const minVal = Math.min(val, other);
        setBound(attr.id, 'min', minVal);
        iMin.value = minVal;
        sMin.value = valueToPos(attr, r, minVal);
        scheduleNotify();
        renderToolbar();
        renderChips();
      });
      sMax.addEventListener('input', () => {
        const val = posToValue(attr, r, Number(sMax.value));
        let other = state[attr.id].min != null ? state[attr.id].min : r.min;
        const maxVal = Math.max(val, other);
        setBound(attr.id, 'max', maxVal);
        iMax.value = maxVal;
        sMax.value = valueToPos(attr, r, maxVal);
        scheduleNotify();
        renderToolbar();
        renderChips();
      });
      iMin.addEventListener('change', () => commit('min', iMin.value));
      iMax.addEventListener('change', () => commit('max', iMax.value));

      return row;
    }

    function renderAll() {
      renderToolbar();
      renderChips();
      renderPanel();
    }

    function notifyChange() { onChange(); }

    renderAll();

    function onDocKey(e) {
      if (e.key === 'Escape' && state.panelOpen) {
        state.panelOpen = false;
        persist();
        renderAll();
      }
    }
    document.addEventListener('keydown', onDocKey);

    return {
      getActiveFiltersList: function() {
        const list = [];
        ATTRIBUTES.forEach(a => {
          const v = state[a.id];
          if (!v) return;
          if (v.min == null && v.max == null) return;
          list.push({
            id: a.id,
            label: a.label,
            min: v.min,
            max: v.max,
            predicate: (s) => {
              const n = a.get(s);
              if (v.min != null && n < v.min) return false;
              if (v.max != null && n > v.max) return false;
              return true;
            },
          });
        });
        return list;
      },
      onPoolChanged: function() { refreshRanges(); renderAll(); },
      destroy: function() {
        document.removeEventListener('keydown', onDocKey);
        wrapper.remove();
      },
      _state: state,           // for test/debug only
      _activeCount: activeCount,
      _clearAll: clearAll,
      _setBound: setBound,
    };
  }

  window.mountSessionFilters = mountSessionFilters;
})();
