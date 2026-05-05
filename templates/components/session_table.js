// ── Session Table Component ─────────────────────────────────────
// Reusable dense data table for session lists. Used by both the
// dashboard Sessions tab and the project detail page bottom section.
// State (visible columns, sort, page size) persists per context in
// localStorage. Self-contained: defines its own helpers so it works
// inside both dashboard.js and project_detail.js without conflicts.
(function() {
  'use strict';

  // ── Helpers ───────────────────────────────────────────────────
  function escHtml(s) {
    if (s == null) return '';
    const d = document.createElement('div');
    d.textContent = String(s);
    return d.innerHTML;
  }
  function fmtUSD(n) {
    n = Number(n) || 0;
    return '$' + n.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
  }
  function fmtNum(n, locale) {
    n = Number(n) || 0;
    return n.toLocaleString(locale);
  }
  function fmtTokens(n) {
    n = Number(n) || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return String(n);
  }
  function modelClass(m) {
    const l = String(m || '').toLowerCase();
    if (l.includes('opus')) return 'opus';
    if (l.includes('sonnet')) return 'sonnet';
    if (l.includes('haiku')) return 'haiku';
    return '';
  }
  function calcCacheEff(s) {
    const inputSum = (s.input_tokens||0) + (s.cache_read_tokens||0) + (s.cache_write_tokens||0);
    if (inputSum === 0) return null;
    return (s.cache_read_tokens||0) / inputSum * 100;
  }
  function effStyle(pct) {
    if (pct == null) return {color:'var(--text2)', emoji:'—', label:'—'};
    if (pct >= 80) return {color:'var(--green)', emoji:'✅', label:pct.toFixed(1)+'%'};
    if (pct >= 50) return {color:'var(--amber)', emoji:'⚠️', label:pct.toFixed(1)+'%'};
    return {color:'var(--red)', emoji:'❌', label:pct.toFixed(1)+'%'};
  }
  // Mirrors Python: re.sub(r'[^a-zA-Z0-9_-]', '_', proj_name.replace('/', '_'))
  function projectSlug(name) {
    if (!name) return '';
    return String(name).replace(/\//g, '_').replace(/[^a-zA-Z0-9_-]/g, '_');
  }
  function sumTools(s) {
    if (!s.tools) return 0;
    let sum = 0;
    for (const k in s.tools) sum += s.tools[k] || 0;
    return sum;
  }
  function totalTokens(s) {
    return (s.input_tokens||0) + (s.output_tokens||0) + (s.cache_read_tokens||0) + (s.cache_write_tokens||0);
  }
  function truncate(s, n) {
    s = String(s || '');
    if (s.length <= n) return s;
    return s.slice(0, n - 1) + '…';
  }

  // ── Column definitions ────────────────────────────────────────
  // group: identity | volume | tokens | cost | cache | activity | errors | action
  const GROUP_LABELS = {
    identity: 'Identity',
    volume: 'Volume',
    tokens: 'Tokens',
    cost: 'Cost',
    cache: 'Cache Health',
    activity: 'Activity',
    errors: 'Errors',
    action: 'Action',
  };
  const GROUP_ORDER = ['identity','volume','tokens','cost','cache','activity','errors','action'];

  const COLUMNS = [
    // Identity
    { id: 'date', label: 'Date', group: 'identity', align: 'left', sortable: true,
      defaultIn: ['dashboard','projectDetail'],
      get: (s) => s.start || '',
      render: (s, ctx) => {
        if (!s.start) return '';
        try { return escHtml(new Date(s.start).toLocaleString(ctx.locale)); }
        catch (e) { return escHtml(s.start); }
      }
    },
    { id: 'project', label: 'Project', group: 'identity', align: 'left', sortable: true,
      defaultIn: ['dashboard'],
      hideWhen: (ctx) => ctx.context === 'projectDetail',
      get: (s) => s.project || '',
      render: (s, ctx) => {
        const raw = s.project || '';
        const name = ctx.anonMode ? ctx.anonName(raw) : raw;
        if (ctx.anonMode) {
          return '<span class="anon-blur">' + escHtml(name) + '</span>';
        }
        const slug = projectSlug(raw);
        if (!slug) return escHtml(name);
        const href = (ctx.context === 'projectDetail' ? '../' : '') + 'projects/' + slug + '.html';
        return '<a href="' + href + '" class="st-link-soft">' + escHtml(name) + '</a>';
      }
    },
    { id: 'first_prompt', label: 'First Prompt', group: 'identity', align: 'left', sortable: false,
      defaultIn: ['dashboard','projectDetail'],
      get: (s) => s.first_prompt || '',
      render: (s, ctx) => {
        const raw = s.first_prompt || '';
        if (!raw) return '<span class="st-muted">—</span>';
        const short = truncate(raw, 80);
        const cls = ctx.anonMode ? 'anon-blur st-prompt' : 'st-prompt';
        return '<span class="' + cls + '" title="' + escHtml(raw) + '">' + escHtml(short) + '</span>';
      }
    },
    { id: 'source', label: 'Source', group: 'identity', align: 'left', sortable: true,
      defaultIn: [],
      get: (s) => s.source || '',
      render: (s) => s.source ? '<span class="st-source">' + escHtml(s.source) + '</span>' : ''
    },
    { id: 'model', label: 'Model', group: 'identity', align: 'left', sortable: true,
      defaultIn: ['dashboard','projectDetail'],
      get: (s) => s.primary_model || '',
      render: (s) => {
        const m = s.primary_model || '—';
        const cls = modelClass(m);
        return '<span class="model-badge ' + cls + '">' + escHtml(m) + '</span>';
      }
    },

    // Volume
    { id: 'duration', label: 'Duration', group: 'volume', align: 'right', sortable: true,
      defaultIn: ['dashboard','projectDetail'],
      get: (s) => s.duration_min || 0,
      render: (s) => {
        const d = s.duration_min || 0;
        return d.toFixed(d < 10 ? 1 : 0) + ' min';
      }
    },
    { id: 'messages', label: 'Messages', group: 'volume', align: 'right', sortable: true,
      defaultIn: ['dashboard','projectDetail'],
      get: (s) => s.messages || 0,
      render: (s, ctx) => fmtNum(s.messages || 0, ctx.locale)
    },
    { id: 'user_messages', label: 'User Msgs', group: 'volume', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.user_messages || 0,
      render: (s, ctx) => fmtNum(s.user_messages || 0, ctx.locale)
    },
    { id: 'assistant_messages', label: 'Assistant Msgs', group: 'volume', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.assistant_messages || 0,
      render: (s, ctx) => fmtNum(s.assistant_messages || 0, ctx.locale)
    },
    { id: 'api_calls', label: 'API Calls', group: 'volume', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.api_calls || 0,
      render: (s, ctx) => fmtNum(s.api_calls || 0, ctx.locale)
    },

    // Tokens
    { id: 'input_tokens', label: 'Input', group: 'tokens', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.input_tokens || 0,
      render: (s) => fmtTokens(s.input_tokens || 0)
    },
    { id: 'output_tokens', label: 'Output', group: 'tokens', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.output_tokens || 0,
      render: (s) => fmtTokens(s.output_tokens || 0)
    },
    { id: 'cache_read_tokens', label: 'Cache Read', group: 'tokens', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.cache_read_tokens || 0,
      render: (s) => fmtTokens(s.cache_read_tokens || 0)
    },
    { id: 'cache_write_tokens', label: 'Cache Write', group: 'tokens', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.cache_write_tokens || 0,
      render: (s) => fmtTokens(s.cache_write_tokens || 0)
    },
    { id: 'reasoning_tokens', label: 'Reasoning', group: 'tokens', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.reasoning_output_tokens || 0,
      render: (s) => fmtTokens(s.reasoning_output_tokens || 0)
    },
    { id: 'total_tokens', label: 'Total Tokens', group: 'tokens', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => totalTokens(s),
      render: (s) => fmtTokens(totalTokens(s))
    },

    // Cost
    { id: 'cost', label: 'Cost', group: 'cost', align: 'right', sortable: true,
      defaultIn: ['dashboard','projectDetail'],
      get: (s) => s.cost || 0,
      render: (s) => fmtUSD(s.cost || 0)
    },
    { id: 'reasoning_cost', label: 'Reasoning Cost', group: 'cost', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.reasoning_cost || 0,
      render: (s) => fmtUSD(s.reasoning_cost || 0)
    },

    // Cache Health
    { id: 'cache_eff', label: 'Cache Eff.', group: 'cache', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => calcCacheEff(s) ?? -1,
      render: (s) => {
        const pct = calcCacheEff(s);
        const st = effStyle(pct);
        return '<span style="color:' + st.color + ';font-weight:600">' + st.emoji + ' ' + escHtml(st.label) + '</span>';
      }
    },
    { id: 'compactions', label: '⚡ Comp.', group: 'cache', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.compactions || 0,
      render: (s) => {
        const v = s.compactions || 0;
        if (v === 0) return '<span class="st-muted">—</span>';
        return '<span style="color:var(--amber)">' + v + '</span>';
      }
    },
    { id: 'flushes', label: '↻ Flushes', group: 'cache', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.cache_flush_count || 0,
      render: (s) => {
        const v = s.cache_flush_count || 0;
        if (v === 0) return '<span class="st-muted">—</span>';
        return '<span style="color:var(--red)">' + v + '</span>';
      }
    },

    // Activity
    { id: 'tool_calls', label: 'Tool Calls', group: 'activity', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => sumTools(s),
      render: (s, ctx) => {
        const v = sumTools(s);
        return v === 0 ? '<span class="st-muted">—</span>' : fmtNum(v, ctx.locale);
      }
    },
    { id: 'file_ops', label: 'File Ops', group: 'activity', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.file_ops_count || 0,
      render: (s, ctx) => {
        const v = s.file_ops_count || 0;
        return v === 0 ? '<span class="st-muted">—</span>' : fmtNum(v, ctx.locale);
      }
    },
    { id: 'agent_dispatches', label: 'Agents', group: 'activity', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => Array.isArray(s.agent_dispatches) ? s.agent_dispatches.length : 0,
      render: (s, ctx) => {
        const v = Array.isArray(s.agent_dispatches) ? s.agent_dispatches.length : 0;
        return v === 0 ? '<span class="st-muted">—</span>' : fmtNum(v, ctx.locale);
      }
    },
    { id: 'file_size', label: 'Size MB', group: 'activity', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.file_size_mb || 0,
      render: (s) => {
        const v = s.file_size_mb || 0;
        return v === 0 ? '<span class="st-muted">—</span>' : v.toFixed(2);
      }
    },

    // Errors
    { id: 'errors', label: 'Errors', group: 'errors', align: 'right', sortable: true,
      defaultIn: [],
      get: (s) => s.error_count || 0,
      render: (s) => {
        const v = s.error_count || 0;
        if (v === 0) return '<span class="st-muted">—</span>';
        return '<span style="color:var(--red);font-weight:600">' + v + '</span>';
      }
    },

    // Action
    { id: 'chat_link', label: 'Chat', group: 'action', align: 'center', sortable: false,
      defaultIn: ['dashboard','projectDetail'],
      get: () => 0,
      render: (s, ctx) => {
        if (s.has_chat === false) return '<span class="st-muted">—</span>';
        if (ctx.anonMode && ctx.hideChatInAnon) return '<span class="st-muted">—</span>';
        const href = (ctx.context === 'projectDetail' ? '../' : '') + 'sessions/' + s.session_id + '.html';
        return '<a href="' + href + '" class="st-chat-btn" title="Open chat">›</a>';
      }
    },
  ];

  const COLUMNS_BY_ID = Object.fromEntries(COLUMNS.map(c => [c.id, c]));

  // ── Settings persistence ──────────────────────────────────────
  function storageKey(context, suffix) {
    return 'sessionTable.' + context + '.' + suffix;
  }
  function loadSetting(context, suffix, fallback) {
    try {
      const raw = localStorage.getItem(storageKey(context, suffix));
      if (raw == null) return fallback;
      return JSON.parse(raw);
    } catch (e) { return fallback; }
  }
  function saveSetting(context, suffix, value) {
    try { localStorage.setItem(storageKey(context, suffix), JSON.stringify(value)); }
    catch (e) {}
  }

  function defaultColumnsFor(context) {
    return COLUMNS.filter(c => c.defaultIn.includes(context)).map(c => c.id);
  }

  // ── Mount ─────────────────────────────────────────────────────
  function mountSessionTable(container, sessions, options) {
    options = options || {};
    const ctx = {
      context: options.context || 'dashboard',
      locale: options.locale,
      anonMode: false,
      anonName: options.anonName || ((x) => x),
      hideChatInAnon: !!options.hideChatInAnon,
    };
    const onChange = options.onChange || function() {};

    // ── State ────────────────────────────────────────────────────
    let visibleColumnIds = loadSetting(ctx.context, 'columns', null);
    if (!Array.isArray(visibleColumnIds) || visibleColumnIds.length === 0) {
      visibleColumnIds = options.defaultColumns || defaultColumnsFor(ctx.context);
    }
    // Filter out any unknown column ids (could happen after a release that removed columns)
    visibleColumnIds = visibleColumnIds.filter(id => COLUMNS_BY_ID[id]);

    let sort = loadSetting(ctx.context, 'sort', null);
    if (!sort || !COLUMNS_BY_ID[sort.col] || !COLUMNS_BY_ID[sort.col].sortable) {
      sort = { col: 'date', dir: 'desc' };
    }
    let pageSize = Number(loadSetting(ctx.context, 'pageSize', null)) || options.defaultPageSize || 50;
    if (![25, 50, 100].includes(pageSize)) pageSize = 50;

    let page = 0;
    let currentSessions = Array.isArray(sessions) ? sessions.slice() : [];
    let sortedCache = null;

    // ── DOM scaffold ─────────────────────────────────────────────
    const wrapper = document.createElement('div');
    wrapper.className = 'st-wrapper';
    container.appendChild(wrapper);

    const toolbar = document.createElement('div');
    toolbar.className = 'st-toolbar';
    const meta = document.createElement('span');
    meta.className = 'st-meta';
    const gear = document.createElement('button');
    gear.type = 'button';
    gear.className = 'st-gear';
    gear.title = 'Choose columns';
    gear.innerHTML = '&#9881;';
    toolbar.appendChild(meta);
    toolbar.appendChild(gear);
    wrapper.appendChild(toolbar);

    const pickerHost = document.createElement('div');
    pickerHost.className = 'st-picker-host';
    wrapper.appendChild(pickerHost);

    const scroll = document.createElement('div');
    scroll.className = 'st-scroll';
    wrapper.appendChild(scroll);

    const table = document.createElement('table');
    table.className = 'st-table';
    const thead = document.createElement('thead');
    const tbody = document.createElement('tbody');
    table.appendChild(thead);
    table.appendChild(tbody);
    scroll.appendChild(table);

    const footer = document.createElement('div');
    footer.className = 'st-footer';
    wrapper.appendChild(footer);

    // ── Picker dropdown ──────────────────────────────────────────
    let pickerOpen = false;
    let pickerEl = null;

    function buildPicker() {
      const el = document.createElement('div');
      el.className = 'st-picker';
      const visibleSet = new Set(visibleColumnIds);

      GROUP_ORDER.forEach(g => {
        const cols = COLUMNS.filter(c => c.group === g && !(c.hideWhen && c.hideWhen(ctx)));
        if (cols.length === 0) return;
        const groupDiv = document.createElement('div');
        groupDiv.className = 'st-picker-group';
        const h = document.createElement('div');
        h.className = 'st-picker-group-h';
        h.textContent = GROUP_LABELS[g];
        groupDiv.appendChild(h);
        cols.forEach(c => {
          const lbl = document.createElement('label');
          lbl.className = 'st-picker-row';
          const cb = document.createElement('input');
          cb.type = 'checkbox';
          cb.checked = visibleSet.has(c.id);
          cb.addEventListener('change', () => {
            if (cb.checked) {
              if (!visibleSet.has(c.id)) {
                visibleSet.add(c.id);
                visibleColumnIds = COLUMNS.filter(x => visibleSet.has(x.id)).map(x => x.id);
              }
            } else {
              visibleSet.delete(c.id);
              visibleColumnIds = visibleColumnIds.filter(x => x !== c.id);
            }
            saveSetting(ctx.context, 'columns', visibleColumnIds);
            renderTable();
            onChange();
          });
          const txt = document.createElement('span');
          txt.textContent = c.label;
          lbl.appendChild(cb);
          lbl.appendChild(txt);
          groupDiv.appendChild(lbl);
        });
        el.appendChild(groupDiv);
      });

      const actions = document.createElement('div');
      actions.className = 'st-picker-actions';
      const reset = document.createElement('button');
      reset.type = 'button';
      reset.className = 'st-picker-btn';
      reset.textContent = 'Reset to default';
      reset.addEventListener('click', () => {
        visibleColumnIds = options.defaultColumns || defaultColumnsFor(ctx.context);
        saveSetting(ctx.context, 'columns', visibleColumnIds);
        closePicker();
        renderTable();
        onChange();
      });
      const minimal = document.createElement('button');
      minimal.type = 'button';
      minimal.className = 'st-picker-btn';
      minimal.textContent = 'Hide all optional';
      minimal.addEventListener('click', () => {
        visibleColumnIds = defaultColumnsFor(ctx.context);
        saveSetting(ctx.context, 'columns', visibleColumnIds);
        closePicker();
        renderTable();
        onChange();
      });
      actions.appendChild(reset);
      actions.appendChild(minimal);
      el.appendChild(actions);
      return el;
    }

    function openPicker() {
      if (pickerOpen) return;
      pickerEl = buildPicker();
      pickerHost.appendChild(pickerEl);
      pickerOpen = true;
      setTimeout(() => {
        document.addEventListener('click', onDocClick, true);
        document.addEventListener('keydown', onEsc, true);
      }, 0);
    }
    function closePicker() {
      if (!pickerOpen) return;
      pickerOpen = false;
      if (pickerEl) { pickerEl.remove(); pickerEl = null; }
      document.removeEventListener('click', onDocClick, true);
      document.removeEventListener('keydown', onEsc, true);
    }
    function onDocClick(e) {
      if (!pickerEl) return;
      if (pickerEl.contains(e.target) || gear.contains(e.target)) return;
      closePicker();
    }
    function onEsc(e) {
      if (e.key === 'Escape') closePicker();
    }
    gear.addEventListener('click', (e) => {
      e.stopPropagation();
      pickerOpen ? closePicker() : openPicker();
    });

    // ── Sort ─────────────────────────────────────────────────────
    function getSortedSessions() {
      if (sortedCache) return sortedCache;
      const col = COLUMNS_BY_ID[sort.col];
      const arr = currentSessions.slice();
      if (col && col.sortable) {
        const dir = sort.dir === 'asc' ? 1 : -1;
        arr.sort((a, b) => {
          const va = col.get(a);
          const vb = col.get(b);
          let cmp;
          if (va == null && vb == null) cmp = 0;
          else if (va == null) cmp = -1;
          else if (vb == null) cmp = 1;
          else if (typeof va === 'number' && typeof vb === 'number') cmp = va - vb;
          else cmp = String(va).localeCompare(String(vb));
          if (cmp !== 0) return cmp * dir;
          // Tie-breaker: start desc
          const ta = a.start || '';
          const tb = b.start || '';
          if (ta < tb) return 1;
          if (ta > tb) return -1;
          return 0;
        });
      }
      sortedCache = arr;
      return arr;
    }

    // ── Rendering ────────────────────────────────────────────────
    function renderTable() {
      ctx.anonMode = document.body.classList.contains('anon-mode');

      // Filter columns: visible + not hidden by context
      const cols = visibleColumnIds
        .map(id => COLUMNS_BY_ID[id])
        .filter(c => c && !(c.hideWhen && c.hideWhen(ctx)));

      // Header
      thead.innerHTML = '';
      const tr = document.createElement('tr');
      cols.forEach(c => {
        const th = document.createElement('th');
        th.className = 'st-th-' + (c.align || 'left');
        if (c.sortable) {
          th.classList.add('st-sortable');
          if (sort.col === c.id) th.classList.add(sort.dir === 'asc' ? 'sort-asc' : 'sort-desc');
          th.addEventListener('click', () => {
            if (sort.col === c.id) {
              sort = { col: c.id, dir: sort.dir === 'asc' ? 'desc' : 'asc' };
            } else {
              // Numeric columns default to desc, text columns to asc
              const defaultDir = (c.align === 'right' ? 'desc' : 'asc');
              sort = { col: c.id, dir: defaultDir };
            }
            saveSetting(ctx.context, 'sort', sort);
            sortedCache = null;
            page = 0;
            renderTable();
            renderFooter();
            onChange();
          });
        }
        th.textContent = c.label;
        tr.appendChild(th);
      });
      thead.appendChild(tr);

      // Body
      const sorted = getSortedSessions();
      const total = sorted.length;
      const pages = Math.max(1, Math.ceil(total / pageSize));
      page = Math.min(page, pages - 1);
      const start = page * pageSize;
      const slice = sorted.slice(start, start + pageSize);

      tbody.innerHTML = '';
      if (slice.length === 0) {
        const trEmpty = document.createElement('tr');
        const td = document.createElement('td');
        td.colSpan = cols.length || 1;
        td.className = 'st-empty';
        td.textContent = 'No sessions match the current filter.';
        trEmpty.appendChild(td);
        tbody.appendChild(trEmpty);
      } else {
        slice.forEach(s => {
          const trow = document.createElement('tr');
          cols.forEach(c => {
            const td = document.createElement('td');
            td.className = 'st-td-' + (c.align || 'left');
            try { td.innerHTML = c.render(s, ctx); }
            catch (e) { td.textContent = ''; }
            trow.appendChild(td);
          });
          tbody.appendChild(trow);
        });
      }

      meta.textContent = total + ' session' + (total === 1 ? '' : 's');
    }

    function renderFooter() {
      const sorted = getSortedSessions();
      const total = sorted.length;
      const pages = Math.max(1, Math.ceil(total / pageSize));
      page = Math.min(page, pages - 1);

      footer.innerHTML = '';

      // Page size picker
      const sizeWrap = document.createElement('span');
      sizeWrap.className = 'st-page-size';
      const sizeLbl = document.createElement('span');
      sizeLbl.textContent = 'Rows: ';
      sizeLbl.className = 'st-muted';
      sizeWrap.appendChild(sizeLbl);
      [25, 50, 100].forEach(n => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'st-size-btn' + (n === pageSize ? ' active' : '');
        b.textContent = String(n);
        b.addEventListener('click', () => {
          if (n === pageSize) return;
          pageSize = n;
          saveSetting(ctx.context, 'pageSize', pageSize);
          page = 0;
          renderTable();
          renderFooter();
          onChange();
        });
        sizeWrap.appendChild(b);
      });
      footer.appendChild(sizeWrap);

      // Pagination
      const pagWrap = document.createElement('span');
      pagWrap.className = 'st-pagination';
      function pBtn(label, disabled, onClick, extraCls) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'st-pag-btn' + (extraCls ? ' ' + extraCls : '');
        b.textContent = label;
        b.disabled = !!disabled;
        if (!disabled) b.addEventListener('click', onClick);
        return b;
      }
      pagWrap.appendChild(pBtn('«', page === 0, () => { page = 0; renderTable(); renderFooter(); }));
      pagWrap.appendChild(pBtn('‹', page === 0, () => { page--; renderTable(); renderFooter(); }));
      const info = document.createElement('span');
      info.className = 'st-pag-info';
      info.textContent = (page + 1) + ' / ' + pages;
      pagWrap.appendChild(info);
      pagWrap.appendChild(pBtn('›', page >= pages - 1, () => { page++; renderTable(); renderFooter(); }));
      pagWrap.appendChild(pBtn('»', page >= pages - 1, () => { page = pages - 1; renderTable(); renderFooter(); }));
      footer.appendChild(pagWrap);
    }

    // ── Initial render ───────────────────────────────────────────
    renderTable();
    renderFooter();

    // ── Public handle ────────────────────────────────────────────
    return {
      update(newSessions) {
        currentSessions = Array.isArray(newSessions) ? newSessions.slice() : [];
        sortedCache = null;
        renderTable();
        renderFooter();
        onChange();
      },
      getFiltered() {
        return getSortedSessions();
      },
      destroy() {
        closePicker();
        wrapper.remove();
      }
    };
  }

  // ── Public export ─────────────────────────────────────────────
  window.mountSessionTable = mountSessionTable;
  window.SESSION_TABLE_COLUMNS = COLUMNS;
})();
