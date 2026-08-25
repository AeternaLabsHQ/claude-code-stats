// tools/palette_sheet.mjs - render a README comparison sheet of the two chart
// palettes (default, colorblind) straight from templates/dashboard.css, in
// light and dark, plus a deuteranopia simulation of both. Never hardcodes hex
// values: the PALETTE:<palette>:<variant> blocks are parsed the same way
// tools/palette_check.py parses them, and the parsed colors flow into the
// generated HTML sheet that Playwright then screenshots.
//
// Usage: node tools/palette_sheet.mjs   (run from the repo root)
import { chromium } from 'playwright';
import { readFileSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const CSS_PATH = resolve(ROOT, 'templates', 'dashboard.css');
const OUT_PATH = resolve(ROOT, 'docs', 'images', 'palettes.png');

// -- CSS parsing (JS port of tools/palette_check.py load_blocks/load_palettes) ----
const MARK_RE = /\/\* PALETTE:([a-z]+):([a-z-]+) \*\//g;
const DECL_RE = /(--vc-[a-z0-9-]+)\s*:\s*([^;]+);/g;

function loadBlocks(cssText) {
  const blocks = {};
  MARK_RE.lastIndex = 0;
  let m;
  while ((m = MARK_RE.exec(cssText))) {
    const start = cssText.indexOf('{', MARK_RE.lastIndex);
    let depth = 0;
    let i = start;
    while (i < cssText.length) {
      if (cssText[i] === '{') depth += 1;
      else if (cssText[i] === '}') {
        depth -= 1;
        if (depth === 0) break;
      }
      i += 1;
    }
    const body = cssText.slice(start, i);
    const decls = {};
    let d;
    DECL_RE.lastIndex = 0;
    while ((d = DECL_RE.exec(body))) decls[d[1]] = d[2].trim();
    blocks[`${m[1]}:${m[2]}`] = decls;
  }
  return blocks;
}

function loadPalettes(cssText) {
  const blocks = loadBlocks(cssText);
  const out = {};
  for (const mode of ['light', 'dark']) {
    const base = { ...blocks[`base:${mode}`] };
    const def = { ...base, ...blocks[`default:${mode}`] };
    const cvd = { ...def, ...blocks[`cvd:${mode}`] };
    out[`default:${mode}`] = def;
    out[`cvd:${mode}`] = cvd;
  }
  return out;
}

const cssText = readFileSync(CSS_PATH, 'utf8');
const palettes = loadPalettes(cssText);

// -- color helpers -----------------------------------------------------------
function hexToRgba(hex, alpha) {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// -- chip / row builders ------------------------------------------------------
function chip(hex, borderRgba) {
  return `<div class="chip" style="background:${hex};border-color:${borderRgba}"></div>`;
}

function chipStack(hex, label, borderRgba) {
  const labelHtml = label ? `<div class="chip-label">${label}</div>` : '';
  return `<div class="chip-stack">${chip(hex, borderRgba)}${labelHtml}</div>`;
}

function catRow(t) {
  const borderRgba = hexToRgba(t['--vc-fg-2'], 0.12);
  const cats = [1, 2, 3, 4, 5, 6, 7, 8].map((i) => chip(t[`--vc-cat-${i}`], borderRgba)).join('');
  const neutrals = ['n1', 'n2'].map((n) => chip(t[`--vc-cat-${n}`], borderRgba)).join('');
  return `
    <div class="row cat-row">
      <div class="row-label">Category</div>
      <div class="chip-group">${cats}</div>
      <div class="chip-group neutral-group">${neutrals}<div class="group-label">neutral</div></div>
    </div>`;
}

function famRow(label, key, t) {
  const borderRgba = hexToRgba(t['--vc-fg-2'], 0.12);
  const stepLabels = ['newest', '2', '3', 'older'];
  const stacks = [1, 2, 3, 4]
    .map((s, idx) => chipStack(t[`--vc-model-${key}-${s}`], stepLabels[idx], borderRgba))
    .join('');
  return `
    <div class="row fam-row">
      <div class="row-label">${label}</div>
      <div class="chip-group">${stacks}</div>
    </div>`;
}

function unknownRow(t) {
  const borderRgba = hexToRgba(t['--vc-fg-2'], 0.12);
  return `
    <div class="row fam-row">
      <div class="row-label">Unknown</div>
      <div class="chip-group">${chipStack(t['--vc-model-unknown'], null, borderRgba)}</div>
    </div>`;
}

function statusRow(t) {
  const borderRgba = hexToRgba(t['--vc-fg-2'], 0.12);
  const items = [
    ['positive', t['--vc-pos']],
    ['negative', t['--vc-neg']],
    ['accent', t['--vc-accent']],
  ];
  const stacks = items.map(([label, hex]) => chipStack(hex, label, borderRgba)).join('');
  return `
    <div class="row status-row">
      <div class="row-label"></div>
      <div class="chip-group">${stacks}</div>
    </div>`;
}

function panelStyle(t) {
  return `background:${t['--vc-panel']};border:1px solid ${t['--vc-grid']};color:${t['--vc-fg-2']}`;
}

function buildFullPanel(t) {
  return `
    <div class="panel" style="${panelStyle(t)}">
      ${catRow(t)}
      ${famRow('Opus', 'opus', t)}
      ${famRow('Sonnet', 'sonnet', t)}
      ${famRow('Haiku', 'haiku', t)}
      ${famRow('Fable', 'fable', t)}
      ${unknownRow(t)}
      ${statusRow(t)}
    </div>`;
}

function buildSimPanel(t) {
  return `
    <div class="panel" style="${panelStyle(t)}">
      ${catRow(t)}
      ${famRow('Opus', 'opus', t)}
      ${famRow('Sonnet', 'sonnet', t)}
      ${famRow('Haiku', 'haiku', t)}
      ${famRow('Fable', 'fable', t)}
    </div>`;
}

function sectionTwoColumn(title, tLight, tDark) {
  return `
    <div class="section">
      <div class="section-title">${title}</div>
      <div class="columns">
        <div class="column" style="background:${tLight['--vc-bg']}">
          <div class="column-caption" style="color:${tLight['--vc-fg-2']}">Light</div>
          ${buildFullPanel(tLight)}
        </div>
        <div class="column" style="background:${tDark['--vc-bg']}">
          <div class="column-caption" style="color:${tDark['--vc-fg-2']}">Dark</div>
          ${buildFullPanel(tDark)}
        </div>
      </div>
    </div>`;
}

function sectionSimulation(title, defaultTokens, cvdTokens) {
  return `
    <div class="section">
      <div class="section-title">${title}</div>
      <div class="columns" style="filter:url(#deutan)">
        <div class="column" style="background:${defaultTokens['--vc-bg']}">
          <div class="column-caption" style="color:${defaultTokens['--vc-fg-2']}">Default</div>
          ${buildSimPanel(defaultTokens)}
        </div>
        <div class="column" style="background:${cvdTokens['--vc-bg']}">
          <div class="column-caption" style="color:${cvdTokens['--vc-fg-2']}">Colorblind</div>
          ${buildSimPanel(cvdTokens)}
        </div>
      </div>
    </div>`;
}

const style = `
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    background: #eef0f3;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  .sheet { width: 1400px; padding: 22px 28px 24px; color: #20242c; }
  .header-row { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 14px; }
  .header-row h1 { font-size: 20px; font-weight: 700; margin: 0; }
  .legend { font-size: 13px; color: #5b6473; }
  .section { margin-bottom: 14px; }
  .section-title { font-size: 13px; font-weight: 600; margin: 0 0 7px 0; }
  .columns { display: flex; gap: 16px; }
  .column { flex: 1; min-width: 0; padding: 11px; border-radius: 12px; }
  .column-caption { font-size: 11px; font-weight: 500; margin-bottom: 6px; }
  .panel { border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .row { display: flex; align-items: center; gap: 6px; min-height: 28px; }
  .row-label { width: 56px; flex: 0 0 56px; font-size: 11px; font-weight: 600; white-space: nowrap; }
  .chip-group { display: flex; gap: 4px; align-items: center; }
  .neutral-group { margin-left: 8px; }
  .group-label { font-size: 11px; margin-left: 4px; white-space: nowrap; }
  .chip-stack { display: flex; flex-direction: column; align-items: center; gap: 2px; }
  .chip { width: 44px; height: 28px; border-radius: 4px; border-width: 1px; border-style: solid; }
  .chip-label { font-size: 11px; line-height: 1.1; }
`;

const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>${style}</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute">
  <filter id="deutan" color-interpolation-filters="linearRGB">
    <feColorMatrix type="matrix" values="0.367322 0.860646 -0.227968 0 0  0.280085 0.672501 0.047413 0 0  -0.011820 0.042940 0.968881 0 0  0 0 0 1 0" />
  </filter>
</svg>
<div class="sheet">
  <div class="header-row">
    <h1>Chart palettes</h1>
    <div class="legend">Left: light theme, right: dark theme</div>
  </div>
  ${sectionTwoColumn('Default palette', palettes['default:light'], palettes['default:dark'])}
  ${sectionTwoColumn('Colorblind palette (config.json: "palette": "colorblind")', palettes['cvd:light'], palettes['cvd:dark'])}
  ${sectionSimulation('Seen with red-green color vision deficiency (deuteranopia simulation)', palettes['default:light'], palettes['cvd:light'])}
</div>
</body>
</html>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, deviceScaleFactor: 2 });
await page.setContent(html, { waitUntil: 'load' });
mkdirSync(dirname(OUT_PATH), { recursive: true });
await page.screenshot({ path: OUT_PATH, fullPage: true });
const box = await page.evaluate(() => ({
  w: document.documentElement.scrollWidth,
  h: document.documentElement.scrollHeight,
}));
await browser.close();

console.log(OUT_PATH);
console.log(`${box.w * 2}x${box.h * 2}px (css ${box.w}x${box.h} @ scale 2)`);
