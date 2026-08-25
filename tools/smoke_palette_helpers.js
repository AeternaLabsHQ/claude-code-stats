// Behaviour smoke for the VCShared palette layer, run in plain Node:
//   node tools/smoke_palette_helpers.js
// Loads templates/components/shared_helpers.js with stubbed DOM globals.
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const store = {
  '--vc-accent': '#c2562f', '--vc-panel': '#ffffff',
  '--vc-series-1': '#111111', '--vc-series-2': '#222222', '--vc-series-soft': '#333333',
  '--vc-cat-1': '#c10001', '--vc-cat-2': '#c10002', '--vc-cat-3': '#c10003', '--vc-cat-4': '#c10004',
  '--vc-cat-5': '#c10005', '--vc-cat-6': '#c10006', '--vc-cat-7': '#c10007', '--vc-cat-8': '#c10008',
  '--vc-cat-n1': '#aaaaa1', '--vc-cat-n2': '#aaaaa2',
  '--vc-model-opus-1': '#a00001', '--vc-model-opus-2': '#a00002', '--vc-model-opus-3': '#a00003', '--vc-model-opus-4': '#a00004',
  '--vc-model-sonnet-1': '#b00001', '--vc-model-sonnet-2': '#b00002',
  '--vc-model-haiku-1': '#c00001', '--vc-model-fable-1': '#d00001',
  '--vc-model-unknown': '#777777',
};
// <html> class list with real add/remove, so vcInitThemePage's applyTheme and
// the click handler's theme lookup see each other.
const htmlClasses = new Set();
// Theme toggle stub: captures the click handler so the test can fire it.
let clickHandler = null;
const themeToggle = {
  innerHTML: '',
  addEventListener: (type, fn) => { if (type === 'click') clickHandler = fn; },
};
global.window = {};
global.document = {
  documentElement: {
    classList: {
      contains: (c) => htmlClasses.has(c),
      add: (...cs) => cs.forEach((c) => htmlClasses.add(c)),
      remove: (...cs) => cs.forEach((c) => htmlClasses.delete(c)),
    },
  },
  body: {},
  querySelector: () => ({}),
  createElement: () => ({ getContext: () => null }),
  getElementById: (id) => (id === 'vcThemeToggle' ? themeToggle : null),
};
global.getComputedStyle = () => ({ getPropertyValue: (n) => store[n] || '' });
global.localStorage = { getItem: () => null, setItem() {} };
global.setInterval = () => 0;  // vcInitThemePage starts a UTC clock; don't hang the run

eval(fs.readFileSync(path.join(__dirname, '..', 'templates', 'components', 'shared_helpers.js'), 'utf8'));
const S = global.window.VCShared;
const MODELS = ['Fable 5', 'Haiku 4.5', 'Opus 4.5', 'Opus 4.6', 'Opus 4.7', 'Opus 4.8', 'Opus 5', 'Sonnet 4.5', 'Sonnet 4.6', 'Sonnet 5'];

assert.strictEqual(S.token('--vc-accent', '#000'), '#c2562f');
assert.strictEqual(S.token('--vc-nope', '#888888'), '#888888');

assert.strictEqual(S.catColor(0), '#c10001');
assert.strictEqual(S.catColor(7), '#c10008');
assert.strictEqual(S.catColor(8), '#aaaaa1');
assert.strictEqual(S.catColor(9), '#aaaaa2');
assert.strictEqual(S.catColor(42), '#aaaaa2', 'never cycles back to slot 1');

assert.deepStrictEqual(S.parseModel('Opus 4.8'), { family: 'opus', version: 4.8 });
assert.deepStrictEqual(S.parseModel('Sonnet 5'), { family: 'sonnet', version: 5 });
assert.deepStrictEqual(S.parseModel('Opus'), { family: 'opus', version: null });
assert.strictEqual(S.parseModel('Unknown'), null);
assert.strictEqual(S.parseModel(''), null);

assert.deepStrictEqual(S.modelStep('Opus 5', MODELS), { family: 'opus', step: 1 });
assert.deepStrictEqual(S.modelStep('Opus 4.8', MODELS), { family: 'opus', step: 2 });
assert.deepStrictEqual(S.modelStep('Opus 4.7', MODELS), { family: 'opus', step: 3 });
assert.deepStrictEqual(S.modelStep('Opus 4.6', MODELS), { family: 'opus', step: 4 });
assert.deepStrictEqual(S.modelStep('Opus 4.5', MODELS), { family: 'opus', step: 4 }, 'older than 4 versions share step 4');
assert.deepStrictEqual(S.modelStep('Sonnet 5', MODELS), { family: 'sonnet', step: 1 });
assert.deepStrictEqual(S.modelStep('Sonnet 4.5', MODELS), { family: 'sonnet', step: 3 });
assert.deepStrictEqual(S.modelStep('Fable 5', MODELS), { family: 'fable', step: 1 });
assert.deepStrictEqual(S.modelStep('Opus', MODELS), { family: 'opus', step: 1 }, 'unversioned alias = newest');
assert.deepStrictEqual(S.modelStep('Opus 9', MODELS), { family: 'opus', step: 1 }, 'model missing from the list still ranks');
assert.strictEqual(S.modelStep('Unknown', MODELS), null);

assert.strictEqual(S.modelColor('Opus 4.8', MODELS), '#a00002');
assert.strictEqual(S.modelColor('Sonnet 5', MODELS), '#b00001');
assert.strictEqual(S.modelColor('Unknown', MODELS), '#777777');
assert.strictEqual(S.modelColor('Synthetic', MODELS), '#777777');
assert.strictEqual(S.modelColor(null, MODELS), '#777777');

assert.strictEqual(S.seriesColor(0), '#c2562f');
assert.strictEqual(S.seriesColor(1), '#111111');
assert.strictEqual(S.seriesColor(2), '#222222');
assert.strictEqual(S.seriesColor(3), '#333333');
assert.strictEqual(S.seriesColor(5), '#111111');

assert.strictEqual(S.hexRgba('#ff0000', 0.5), 'rgba(255,0,0,0.5)');
assert.strictEqual(S.hexRgba('#f00', 1), 'rgba(255,0,0,1)');
assert.strictEqual(S.hexRgba('rgb(1,2,3)', 0.5), 'rgb(1,2,3)');

// vcInitThemePage: the optional callback fires on a click-applied change only.
// No stored vc-theme and no matchMedia in the stub, so the initial theme is
// light and the first click switches to dark.
let seenTheme = null;
S.vcInitThemePage((t) => { seenTheme = t; });
assert.strictEqual(seenTheme, null, 'the initial apply must not fire onChange');
assert.ok(typeof clickHandler === 'function', 'toggle click handler registered');
clickHandler();
assert.strictEqual(seenTheme, 'dark', 'onChange gets the new theme name');
clickHandler = null;
assert.doesNotThrow(() => S.vcInitThemePage(), 'callback is optional');
assert.doesNotThrow(() => clickHandler(), 'toggling without a callback is fine');

console.log('smoke_palette_helpers: OK');
