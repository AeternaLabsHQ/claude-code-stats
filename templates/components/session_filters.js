// ── Session Filters Component ───────────────────────────────────
// Reusable filter module mounted above the session table. Owns its
// own UI, state and localStorage persistence. Consumers call
// getActiveFiltersList() and feed the predicates into their
// existing session-filtering pipeline.
(function() {
  'use strict';

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

  const GROUP_ORDER = ['volume','tokens','cost','cache','activity','errors'];
  const GROUP_LABELS = {
    volume: 'Volume', tokens: 'Tokens', cost: 'Cost',
    cache: 'Cache Health', activity: 'Activity', errors: 'Errors',
  };

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

    // Placeholder DOM so consumers see *something* and verify
    // the file is loaded. Subsequent tasks replace this.
    const wrapper = document.createElement('div');
    wrapper.className = 'sf-wrapper';
    wrapper.setAttribute('data-context', ctx.context);
    container.appendChild(wrapper);

    return {
      getActiveFiltersList: function() { return []; },
      onPoolChanged: function() {},
      destroy: function() { wrapper.remove(); },
    };
  }

  window.mountSessionFilters = mountSessionFilters;
})();
