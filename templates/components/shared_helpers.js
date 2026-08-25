// ── Shared page helpers (VCShared) ──────────────────────────────
// Single source of truth for escaping, number formatting, model
// badges, cache-efficiency styling, the F2 anon note and the
// detail-page theme/UTC wiring. Bundled as the FIRST script into
// dashboard, project-detail and session-detail pages by
// extract_stats.py, so every later script may assume window.VCShared.
(function() {
  'use strict';

  function localeCode() {
    return (typeof window !== 'undefined' && window.__LOCALE__ && window.__LOCALE__.locale_code) || 'en-US';
  }

  // Escapes text for BOTH element and attribute context (quotes included).
  // null/undefined become '' (the old div.textContent trick rendered
  // "undefined" for undefined input and left quotes unescaped).
  function escHtml(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function fmtTokens(n) {
    n = Number(n) || 0;
    if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
    if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return String(n);
  }

  function fmtUSD(n, decimals) {
    const d = decimals == null ? 2 : decimals;
    return '$' + (Number(n) || 0).toLocaleString(localeCode(), {
      minimumFractionDigits: d, maximumFractionDigits: d,
    });
  }

  function modelClass(m) {
    const l = String(m || '').toLowerCase();
    if (l.includes('opus')) return 'opus';
    if (l.includes('sonnet')) return 'sonnet';
    if (l.includes('haiku')) return 'haiku';
    return '';
  }

  function calcCacheEff(s) {
    const inputSum = (s.input_tokens || 0) + (s.cache_read_tokens || 0) + (s.cache_write_tokens || 0);
    if (inputSum === 0) return null;
    return (s.cache_read_tokens || 0) / inputSum * 100;
  }

  function effStyle(pct) {
    if (pct == null) return { color: 'var(--text2)', emoji: '—', label: '—' };
    if (pct >= 80) return { color: 'var(--green)', emoji: '✅', label: pct.toFixed(1) + '%' };
    if (pct >= 50) return { color: 'var(--amber)', emoji: '⚠️', label: pct.toFixed(1) + '%' };
    return { color: 'var(--red)', emoji: '❌', label: pct.toFixed(1) + '%' };
  }

  // One F2 note style for all three pages.
  function vcAnonNote(isOn) {
    let note = document.getElementById('anonNote');
    if (!note) {
      note = document.createElement('div');
      note.id = 'anonNote';
      note.className = 'vc';
      note.style.cssText = 'position:fixed;top:14px;right:14px;padding:8px 14px;border-radius:var(--vc-radius-sm,10px);border:1px solid var(--vc-accent,#c2562f);background:var(--vc-panel,#ffffff);box-shadow:var(--vc-shadow);font-family:var(--vc-font-mono,JetBrains Mono,ui-monospace,monospace);font-size:11px;letter-spacing:0.14em;text-transform:uppercase;z-index:9999;transition:opacity 0.3s;color:var(--vc-accent,#c2562f);';
      document.body.appendChild(note);
    }
    note.textContent = isOn ? '> ANONYMIZATION ON' : '> ANONYMIZATION OFF';
    note.style.opacity = '1';
    setTimeout(function() { note.style.opacity = '0'; }, 2000);
  }

  // Theme toggle + UTC clock for the two detail pages. The dashboard keeps
  // its own theme wiring (it additionally refreshes charts on toggle).
  // onChange (optional) fires after a click-applied theme change with the
  // new theme name. Charts that resolved palette tokens into fixed colors
  // at render time use it to re-tint; the initial apply does not fire it,
  // nothing has rendered yet at that point.
  function vcInitThemePage(onChange) {
    function prefersDark() {
      try { return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches; }
      catch (e) { return false; }
    }
    function applyTheme(t) {
      document.documentElement.classList.remove('theme-light', 'theme-dark');
      document.documentElement.classList.add('theme-' + t);
      const btn = document.getElementById('vcThemeToggle');
      if (btn) btn.innerHTML = t === 'dark' ? '&#9790;' : '&#9737;';
    }
    const saved = localStorage.getItem('vc-theme');
    const initial = (saved === 'light' || saved === 'dark') ? saved : (prefersDark() ? 'dark' : 'light');
    applyTheme(initial);
    const toggle = document.getElementById('vcThemeToggle');
    if (toggle) {
      toggle.addEventListener('click', function() {
        const cur = document.documentElement.classList.contains('theme-dark') ? 'dark' : 'light';
        const n = cur === 'dark' ? 'light' : 'dark';
        localStorage.setItem('vc-theme', n);
        applyTheme(n);
        if (typeof onChange === 'function') onChange(n);
      });
    }
    function utc() {
      const el = document.getElementById('vcUtcTime');
      if (!el) return;
      el.textContent = new Date().toISOString().slice(11, 19) + ' UTC';
    }
    utc();
    setInterval(utc, 1000);
  }

  // ── Chart palette layer ───────────────────────────────────────────
  // Every chart color is a CSS custom property on .vc / body.vc-page
  // (templates/*.css, VC-SHARED:tokens block). JS reads them live so the
  // light/dark theme, the colorblind palette (html.palette-cvd, set by the
  // build from config.json "palette") and custom.css overrides all apply
  // without duplicating hex values here. The only fallback is a neutral.
  const NEUTRAL = '#888888';

  function token(name, fallback) {
    if (typeof document === 'undefined' || typeof getComputedStyle === 'undefined') return fallback;
    try {
      const probe = document.querySelector('.vc') || document.body || document.documentElement;
      const val = getComputedStyle(probe).getPropertyValue(name).trim();
      return val || fallback;
    } catch (e) { return fallback; }
  }

  // Categorical slots in fixed order; ranks past 8 fall into the two
  // neutral tail slots and stay there (never cycle back to slot 1).
  function catColor(i) {
    i = Math.max(0, Number(i) || 0);
    if (i < 8) return token('--vc-cat-' + (i + 1), NEUTRAL);
    return token(i === 8 ? '--vc-cat-n1' : '--vc-cat-n2', NEUTRAL);
  }

  const FAMILY_RE = /\b(fable|opus|sonnet|haiku)\b\s*(\d+(?:\.\d+)?)?/i;
  function parseModel(name) {
    const m = FAMILY_RE.exec(String(name == null ? '' : name));
    if (!m) return null;
    return { family: m[1].toLowerCase(), version: m[2] != null ? parseFloat(m[2]) : null };
  }

  // Family = hue, version rank = lightness step: the newest version of a
  // family is step 1, older ones recede; everything older than the four
  // most recent shares step 4. Rank is computed over the full model list
  // (D.models), not the filtered subset, so colors do not shift with filters.
  function modelStep(name, allModels) {
    const p = parseModel(name);
    if (!p) return null;
    if (p.version == null) return { family: p.family, step: 1 };
    const versions = [];
    (allModels || []).forEach(function(n) {
      const q = parseModel(n);
      if (q && q.family === p.family && q.version != null && versions.indexOf(q.version) < 0) versions.push(q.version);
    });
    if (versions.indexOf(p.version) < 0) versions.push(p.version);
    versions.sort(function(a, b) { return b - a; });
    return { family: p.family, step: Math.min(versions.indexOf(p.version) + 1, 4) };
  }

  function modelColor(name, allModels) {
    const s = modelStep(name, allModels);
    if (!s) return token('--vc-model-unknown', NEUTRAL);
    return token('--vc-model-' + s.family + '-' + s.step, NEUTRAL);
  }

  // Neutral series palette: rank 0 is the accent, 1-2 neutrals, 3 a soft fill.
  const SERIES_TOKENS = ['--vc-accent', '--vc-series-1', '--vc-series-2', '--vc-series-soft'];
  function seriesColor(rank) {
    return token(SERIES_TOKENS[((Number(rank) || 0) % 4 + 4) % 4], NEUTRAL);
  }

  function hexRgba(color, alpha) {
    if (typeof color !== 'string' || color[0] !== '#') return color;
    let hex = color.slice(1);
    if (hex.length === 3) hex = hex.split('').map(function(c) { return c + c; }).join('');
    if (hex.length !== 6) return color;
    const r = parseInt(hex.substr(0, 2), 16), g = parseInt(hex.substr(2, 2), 16), b = parseInt(hex.substr(4, 2), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
  }

  function isCvdPalette() {
    try { return document.documentElement.classList.contains('palette-cvd'); }
    catch (e) { return false; }
  }

  // Hatched fill for the colorblind palette: panel-colored diagonal lines
  // over `color` so two lightness steps of one family differ in texture,
  // not only in tone. Returns the plain color where canvas is unavailable.
  function patternFill(color, angle) {
    try {
      const size = 8;
      const c = document.createElement('canvas');
      c.width = size; c.height = size;
      const x = c.getContext && c.getContext('2d');
      if (!x) return color;
      x.fillStyle = color; x.fillRect(0, 0, size, size);
      x.strokeStyle = token('--vc-panel', '#ffffff');
      x.lineWidth = 2; x.lineCap = 'square';
      x.beginPath();
      if (angle === 135) {
        x.moveTo(-2, size + 2); x.lineTo(size + 2, -2);
        x.moveTo(-2, 2); x.lineTo(2, -2);
        x.moveTo(size - 2, size + 2); x.lineTo(size + 2, size - 2);
      } else {
        x.moveTo(-2, -2); x.lineTo(size + 2, size + 2);
        x.moveTo(size - 2, -2); x.lineTo(size + 2, 2);
        x.moveTo(-2, size - 2); x.lineTo(2, size + 2);
      }
      x.stroke();
      return x.createPattern(c, 'repeat') || color;
    } catch (e) { return color; }
  }

  window.VCShared = {
    localeCode: localeCode,
    escHtml: escHtml,
    fmtTokens: fmtTokens,
    fmtUSD: fmtUSD,
    modelClass: modelClass,
    calcCacheEff: calcCacheEff,
    effStyle: effStyle,
    vcAnonNote: vcAnonNote,
    vcInitThemePage: vcInitThemePage,
    token: token,
    catColor: catColor,
    parseModel: parseModel,
    modelStep: modelStep,
    modelColor: modelColor,
    seriesColor: seriesColor,
    hexRgba: hexRgba,
    isCvdPalette: isCvdPalette,
    patternFill: patternFill,
  };
})();
