// Behaviour smoke for the session table "Experiment" column, run in plain Node:
//   node tools/smoke_session_table_experiment.js
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..');
global.window = { __LOCALE__: { sessions_tab: { experiment_tip: 'Tip text <b>' } } };
global.document = {
  documentElement: { classList: { contains: () => false, add() {}, remove() {} } },
  body: {},
  querySelector: () => null,
  createElement: () => ({ getContext: () => null }),
};
global.getComputedStyle = () => ({ getPropertyValue: () => '' });
eval(fs.readFileSync(path.join(ROOT, 'templates/components/shared_helpers.js'), 'utf8'));
global.VCShared = window.VCShared;
eval(fs.readFileSync(path.join(ROOT, 'templates/components/session_table.js'), 'utf8'));

const cols = window.SESSION_TABLE_COLUMNS;
const ids = cols.map(c => c.id);
const col = cols.find(c => c.id === 'experiment');
assert.ok(col, 'experiment column exists');
assert.strictEqual(ids.indexOf('experiment'), ids.indexOf('model') + 1, 'placed right after model');
assert.strictEqual(col.group, 'identity');
assert.strictEqual(col.align, 'left');
assert.strictEqual(col.sortable, true);
assert.deepStrictEqual(Array.from(col.defaultIn), ['dashboard', 'projectDetail']);
assert.strictEqual(col.total, undefined, 'no totals cell');

const ctx = { context: 'dashboard', locale: 'en-US', anonMode: false };

// One badge per ID, short text, full ID in title
const one = col.render({ experiment_ids: ['21e0afd842ce5836'] }, ctx);
assert.ok(one.includes('st-exp-badge'), one);
assert.ok(one.includes('>21e<'), one);
assert.ok(one.includes('title="21e0afd842ce5836"'), one);

const two = col.render({ experiment_ids: ['21e0afd842ce5836', '5ddd0466fd524dad'] }, ctx);
assert.strictEqual((two.match(/st-exp-badge/g) || []).length, 2, two);
assert.ok(two.includes('>5dd<'), two);

// Empty / missing -> muted dash, no badge
for (const s of [{}, { experiment_ids: [] }]) {
  const out = col.render(s, ctx);
  assert.ok(out.includes('st-muted'), out);
  assert.ok(!out.includes('st-exp-badge'), out);
}

// Hostile data is escaped
const evil = col.render({ experiment_ids: ['"><img src=x>'] }, ctx);
assert.ok(!evil.includes('<img'), evil);

// get(): full IDs joined by comma, '' for none (used by sort and export)
assert.strictEqual(col.get({}), '');
assert.strictEqual(col.get({ experiment_ids: [] }), '');
assert.strictEqual(col.get({ experiment_ids: ['a1', 'b2'] }), 'a1,b2');

// Header tooltip comes from the locale
assert.strictEqual(col.tipKey, 'experiment_tip');

console.log('smoke_session_table_experiment: OK');
