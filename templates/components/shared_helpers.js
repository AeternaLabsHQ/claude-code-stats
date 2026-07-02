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

  // One F2 note style for all three pages (Modern SaaS variant).
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
  function vcInitThemePage() {
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
  };
})();
