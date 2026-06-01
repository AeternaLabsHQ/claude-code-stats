/* ============================================================
   app.js — controller: direction / theme / screen / sub-nav,
   chart (re)building, persistence.
   ============================================================ */

const HERO_CHARTS = ['c-apiByDay', 'c-cumulative', 'c-tokenType'];
const SUB_CHARTS = {
  cache: ['c-outputByTool', 'c-outputByActivity', 'c-cacheEff'],
  tools: ['c-toolUsage'],
  workflows: [],
  storage: ['c-storage'],
  environment: [],
  agents: ['c-subagentTypes', 'c-agentDescriptions'],
  errors: ['c-errorRate', 'c-errorsByCategory', 'c-errorsByTool'],
};
const SUB_ORDER = ['cache', 'tools', 'workflows', 'storage', 'environment', 'agents', 'errors'];

const DEFAULT_STATE = { direction: 'terminal', theme: 'light', screen: 'hero', sub: 'cache' };
let STATE = loadState();

function loadState() {
  try {
    const s = JSON.parse(localStorage.getItem('claudestats-redesign') || '{}');
    return Object.assign({}, DEFAULT_STATE, s);
  } catch (e) { return Object.assign({}, DEFAULT_STATE); }
}
function saveState() {
  localStorage.setItem('claudestats-redesign', JSON.stringify(STATE));
}

function rebuildVisibleCharts() {
  destroyAllCharts();
  // setTimeout (not rAF) so charts still build when the iframe is backgrounded.
  setTimeout(() => {
    if (STATE.screen === 'hero') buildCharts(HERO_CHARTS);
    else if (STATE.screen === 'insights') buildCharts(SUB_CHARTS[STATE.sub] || []);
  }, 40);
}

function applyState() {
  const wrap = document.querySelector('.appwrap');
  wrap.setAttribute('data-direction', STATE.direction);
  wrap.setAttribute('data-theme', STATE.theme);

  // chrome buttons
  document.querySelectorAll('[data-set]').forEach(btn => {
    const [k, v] = btn.getAttribute('data-set').split(':');
    btn.setAttribute('aria-pressed', String(STATE[k] === v));
  });

  // screens
  document.querySelectorAll('.screen').forEach(s => {
    s.hidden = s.getAttribute('data-screen') !== STATE.screen;
  });

  // product nav active state
  document.querySelectorAll('.mainnav .tab').forEach(t => {
    t.classList.toggle('active', t.getAttribute('data-screen') === STATE.screen);
  });

  // subsections
  if (STATE.screen === 'insights') {
    document.querySelectorAll('.subsection').forEach(sec => {
      sec.hidden = sec.getAttribute('data-sub') !== STATE.sub;
    });
    document.querySelectorAll('.subnav button').forEach(b => {
      b.classList.toggle('on', b.getAttribute('data-sub') === STATE.sub);
    });
  }

  rebuildVisibleCharts();
  saveState();
}

function setState(patch) { Object.assign(STATE, patch); applyState(); }

document.addEventListener('DOMContentLoaded', () => {
  // chrome segmented controls
  document.querySelectorAll('[data-set]').forEach(btn => {
    btn.addEventListener('click', () => {
      const [k, v] = btn.getAttribute('data-set').split(':');
      setState({ [k]: v });
    });
  });

  // product nav tabs (Token & API Value / Insights & System switch; others stub)
  document.querySelectorAll('.mainnav .tab').forEach(t => {
    t.addEventListener('click', () => {
      const scr = t.getAttribute('data-screen');
      if (scr === 'hero' || scr === 'insights') setState({ screen: scr });
      else flashStub();
    });
  });

  // insights sub-nav
  document.querySelectorAll('.subnav button').forEach(b => {
    b.addEventListener('click', () => setState({ sub: b.getAttribute('data-sub') }));
  });

  // theme toggle inside product topbar
  const tt = document.getElementById('themeToggleProduct');
  if (tt) tt.addEventListener('click', () => setState({ theme: STATE.theme === 'light' ? 'dark' : 'light' }));

  applyState();

  // rebuild charts on resize (debounced)
  let rt;
  window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(rebuildVisibleCharts, 200); });
});

function flashStub() {
  let el = document.getElementById('stub-toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'stub-toast';
    el.style.cssText = 'position:fixed;left:50%;bottom:28px;transform:translateX(-50%);z-index:200;' +
      'background:var(--fg);color:var(--bg);font-family:var(--font-label);font-size:12px;letter-spacing:.04em;' +
      'padding:11px 18px;border-radius:var(--radius-sm);box-shadow:0 8px 24px rgba(0,0,0,.25);max-width:80vw;text-align:center;';
    document.body.appendChild(el);
  }
  el.textContent = 'This exploration mocks the two hero screens — Token & API Value and Insights & System.';
  el.style.opacity = '1';
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.transition = 'opacity .4s'; el.style.opacity = '0'; }, 2600);
}
