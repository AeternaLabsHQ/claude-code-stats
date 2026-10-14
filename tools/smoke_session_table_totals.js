// Behaviour smoke for the session table totals row, run in plain Node:
//   node tools/smoke_session_table_totals.js
// Loads shared_helpers.js + session_table.js with stubbed DOM globals and
// checks what each column puts into the totals row.
'use strict';
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const ROOT = path.resolve(__dirname, '..');
global.window = {};
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

const T = window.SESSION_TABLE_TOTALS;
assert.ok(T, 'SESSION_TABLE_TOTALS exported');

const sessions = [
  { project: 'a', duration_min: 30, messages: 10, input_tokens: 100, output_tokens: 50,
    cache_read_tokens: 800, cache_write_tokens: 100, cost: 1.25, error_count: 1,
    tools: { Read: 2, Bash: 1 }, agent_dispatches: [{}, {}], file_size_mb: 0.5,
    primary_model: 'claude-opus-5', first_prompt: 'hi' },
  { project: 'b', duration_min: 60, messages: 5, input_tokens: 0, output_tokens: 10,
    cache_read_tokens: 0, cache_write_tokens: 0, cost: 0.75,
    tools: { Read: 1 }, file_size_mb: 0.25 },
  { project: 'a', duration_min: 0, messages: 0, cost: 0 },
];

const agg = T.aggregate(sessions);
assert.strictEqual(agg.count, 3);
assert.strictEqual(agg.duration_min, 90);
assert.strictEqual(agg.messages, 15);
assert.strictEqual(agg.input_tokens, 100);
assert.strictEqual(agg.output_tokens, 60);
assert.strictEqual(agg.cost, 2);
assert.strictEqual(agg.error_count, 1);
assert.deepStrictEqual(agg.tools, { Read: 3, Bash: 1 });
assert.strictEqual(agg.agent_count, 2);
assert.strictEqual(agg.project_count, 2);

const ctx = { context: 'dashboard', locale: 'en-US', anonMode: false };
const cols = Object.fromEntries(window.SESSION_TABLE_COLUMNS.map(c => [c.id, c]));
const cell = (id) => T.totalCell(cols[id], agg, ctx);

// Summed columns
assert.strictEqual(cell('messages'), '15');
assert.strictEqual(cell('total_tokens'), '1.1K');       // 100+60+800+100
assert.strictEqual(cell('cost'), '$2.00');
assert.strictEqual(cell('duration'), '1.5 h');
assert.ok(cell('tool_calls').includes('4'));
assert.ok(cell('agent_dispatches').includes('2'));
assert.strictEqual(cell('file_size'), '0.75');
// Ratio, recomputed from summed tokens: 800 / (100+800+100) = 80%
assert.ok(cell('cache_eff').includes('80.0%'), cell('cache_eff'));
// Distinct count instead of a sum
assert.ok(cell('project').includes('2'), cell('project'));
// Text columns stay empty
['chat_link', 'first_prompt', 'model', 'source'].forEach(id => {
  assert.strictEqual(cell(id), '', id + ' should be empty');
});
// Short durations stay in minutes
assert.strictEqual(T.totalCell(cols.duration, T.aggregate([{ duration_min: 42 }]), ctx), '42 min');
// Empty set does not crash
assert.strictEqual(T.aggregate([]).count, 0);

console.log('smoke_session_table_totals: OK');
