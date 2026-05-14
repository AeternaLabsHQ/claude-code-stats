// ── Session Filters Component ───────────────────────────────────
// Reusable filter module mounted above the session table. Owns its
// own UI, state and localStorage persistence. Consumers call
// getActiveFiltersList() and feed the predicates into their
// existing session-filtering pipeline.
(function() {
  'use strict';

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
