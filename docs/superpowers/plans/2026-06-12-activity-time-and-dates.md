# Activity-Time Attribution + Date Display Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** (1) hourly/weekday charts attribute each message to its ACTUAL local hour/weekday (not the session start hour). (2) Sessions table marks multi-day sessions and its date-range filter becomes activity-based. (3) Session-detail chat shows the date (day dividers), and the copy + markdown exports include date (and time).

**Architecture:** Mirrors the per-day work already merged. Backend accumulates per-session `hour_hist`/`weekday_hist` (local-time message-count buckets) at the same two sites where `message_count` increments, sums them into the global `hourly_distribution`/`weekday_distribution`, and serializes the per-session histograms. The frontend `filterData` uses the server distributions directly when unfiltered and sums the per-session histograms when filtered. The session date filter switches from start-day to last-activity-day. Session-detail gets shared `fmtDate`/`fmtDateTime` helpers used by day dividers, the clipboard copy, and the markdown export.

**Tech Stack:** Python 3 stdlib; vanilla browser JS (no build step beyond `extract_stats.py` inlining templates into `public/index.html`). Verify JS with `node -c`.

**Metric note:** hourly/weekday already counts `message_count` (typed user prompts + assistant messages); the fix keeps that exact metric, only moving each count to its real hour. Sum per session stays `message_count` (messages lacking a parseable timestamp — virtually none — are simply not bucketed).

---

## Task A: Backend — per-message hour/weekday histograms

**Files:** Modify `extract_stats.py`.

- [ ] **Step 1: Add per-session histogram fields to session-init**

ANCHOR: the `sessions[session_id] = { ... }` literal, where `"daily_message_count": defaultdict(int),` already exists. Immediately after that line, add:
```python
                                    "hour_hist": defaultdict(int),
                                    "weekday_hist": defaultdict(int),
```

- [ ] **Step 2: Populate at the user-typed prompt site**

ANCHOR: in the user typed-prompt branch, the existing block (added in the per-day work):
```python
                                    if ts_ms_for_msg is not None:
                                        sess["daily_message_count"][_day_from_ms(ts_ms_for_msg)] += 1
```
Replace it with (same guard, add local hour/weekday buckets):
```python
                                    if ts_ms_for_msg is not None:
                                        sess["daily_message_count"][_day_from_ms(ts_ms_for_msg)] += 1
                                        _lt = datetime.fromtimestamp(ts_ms_for_msg / 1000)
                                        sess["hour_hist"][_lt.hour] += 1
                                        sess["weekday_hist"][_lt.weekday()] += 1
```
(`datetime.fromtimestamp` WITHOUT tz = local time, matching the timezone the frontend currently displays. Do NOT use `tz=timezone.utc` here.)

- [ ] **Step 3: Populate at the assistant site**

ANCHOR: in the assistant branch, the existing block:
```python
                                if ts_ms_for_msg is not None:
                                    sess["daily_message_count"][_day_from_ms(ts_ms_for_msg)] += 1
```
Replace with:
```python
                                if ts_ms_for_msg is not None:
                                    sess["daily_message_count"][_day_from_ms(ts_ms_for_msg)] += 1
                                    _lt = datetime.fromtimestamp(ts_ms_for_msg / 1000)
                                    sess["hour_hist"][_lt.hour] += 1
                                    sess["weekday_hist"][_lt.weekday()] += 1
```

- [ ] **Step 4: Sum into the global distributions; drop the old start-hour logic**

In `build_dashboard_data`'s session loop:
- ANCHOR the two lines:
```python
        hourly_messages[hour] += sess["user_message_count"]
        weekday_messages[weekday] += sess["user_message_count"]
```
Replace them with:
```python
        for _h, _c in sess["hour_hist"].items():
            hourly_messages[_h] += _c
        for _w, _c in sess["weekday_hist"].items():
            weekday_messages[_w] += _c
```
- The locals `hour = start_dt.hour` / `weekday = start_dt.weekday()` (defined earlier in the loop) are now unused by this block. Leave them ONLY if something else in the loop references them; otherwise remove the two assignments. Grep `\bhour\b` / `\bweekday\b` in the loop body first and report what you found.

- [ ] **Step 5: Serialize per-session histograms**

ANCHOR: in `session_list.append({ ... })`, the line `"per_day": session_per_day,` (added in the per-day work). After it, add:
```python
            "hour_hist": dict(sess["hour_hist"]),
            "weekday_hist": dict(sess["weekday_hist"]),
```
(JSON object keys become strings; the frontend reads them with `+key`.)

- [ ] **Step 6: Pop the temp defaultdicts before serialization (optional cleanliness)**

The per-session dicts are serialized via `dict(...)` copies, so the defaultdicts themselves stay on `sess` until the cleanup loop. They are not in `data`, so no action strictly required. Do NOT add them to the pop list (they are read in Step 5). Skip.

- [ ] **Step 7: Verify**

```bash
cd /home/andie/projects/claude-stats/.claude/worktrees/chart-session-dates
python3 -c "import extract_stats"
python3 -m pytest tests/ -q
python3 extract_stats.py
python3 -c "
import json; d=json.load(open('public/dashboard_data.json'))
print('hourly total:', sum(x['messages'] for x in d['hourly_distribution']))
print('weekday total:', sum(x['messages'] for x in d['weekday_distribution']))
s=[x for x in d['sessions'] if x.get('hour_hist')][0]
print('sample hour_hist:', s['hour_hist'], 'weekday_hist:', s['weekday_hist'])
# reconciliation: hourly total should equal sum of message_count over sessions that had a timestamp (≈ total messages)
print('sum message_count:', sum(x['messages'] for x in d['sessions']))
"
```
Expected: hourly total ≈ weekday total ≈ sum of session message counts (small shortfall only from messages without a timestamp). per-session `hour_hist`/`weekday_hist` present and integer-valued.

- [ ] **Step 8: Commit**
```bash
git add extract_stats.py
git commit -m "feat(activity): attribute hourly/weekday by actual message time + per-session histograms"
```

---

## Task B: Frontend — consume histograms + activity-based date filter

**Files:** Modify `templates/dashboard.js` (function `filterData`).

- [ ] **Step 1: Activity-based date filter**

ANCHOR:
```javascript
  if (cutoff) filteredSessions = filteredSessions.filter(s => s.date >= cutoff);
```
Replace with (a session is in range if its LAST activity is within the range, not just its start):
```javascript
  if (cutoff) filteredSessions = filteredSessions.filter(s => (s.end ? s.end.slice(0, 10) : s.date) >= cutoff);
```

- [ ] **Step 2: hourly/weekday from server (unfiltered) or per-session histograms (filtered)**

ANCHOR: the block
```javascript
  // Recalculate hourly_distribution
  const hourly = Array.from({length:24}, (_, i) => ({hour: i, messages: 0}));
  F.sessions.forEach(s => {
    if (s.start) {
      const h = new Date(s.start).getHours();
      hourly[h].messages += s.messages || 0;
    }
  });
  F.hourly_distribution = hourly;

  // Recalculate weekday_distribution
  const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const weekday = [0,0,0,0,0,0,0];
  F.sessions.forEach(s => {
    if (s.start) {
      const d = new Date(s.start).getDay();
      weekday[d] += s.messages || 0;
    }
  });
  // Reorder to Mon-Sun
  F.weekday_distribution = [1,2,3,4,5,6,0].map(i => ({day: dayNames[i], messages: weekday[i]}));
```
Replace the WHOLE block with:
```javascript
  // Hour/weekday distributions. Unfiltered: server distributions (per-message,
  // local-time) directly. Filtered: sum per-session hour_hist/weekday_hist
  // (same local-time buckets), reusing the server's labels/order for the
  // weekday axis so toggling a filter never changes labels.
  if (noFilter) {
    F.hourly_distribution = D.hourly_distribution;
    F.weekday_distribution = D.weekday_distribution;
  } else {
    const hourly = (D.hourly_distribution || []).map(r => ({hour: r.hour, messages: 0}));
    const wsum = [0, 0, 0, 0, 0, 0, 0];
    F.sessions.forEach(s => {
      const hh = s.hour_hist || {};
      for (const h in hh) { if (hourly[+h]) hourly[+h].messages += hh[h]; }
      const wh = s.weekday_hist || {};
      for (const w in wh) { wsum[+w] += wh[w]; }
    });
    F.hourly_distribution = hourly;
    F.weekday_distribution = (D.weekday_distribution || []).map((row, i) => ({day: row.day, messages: wsum[i]}));
  }
```
(`noFilter` is already declared earlier in `filterData` by the per-day work — `const noFilter = currentDays === 0 && !pf && !hideEmpty;`. Confirm it is in scope above this block; if not, STOP and report.)

- [ ] **Step 3: Verify**

`node -c templates/dashboard.js`. Confirm `noFilter` resolves (grep it appears once as `const noFilter`). Confirm the weekday index `i` aligns: `D.weekday_distribution[i]` is built backend-side as `weekday_names[i]` for Python weekday `i` (Mon=0..Sun=6), and `s.weekday_hist` is keyed by the same Python weekday — so `wsum[i]` matches `row` at index `i`.

- [ ] **Step 4: Commit**
```bash
git add templates/dashboard.js
git commit -m "feat(activity): consume hour/weekday histograms; activity-based session date filter"
```

---

## Task C: Sessions table — multi-day badge

**Files:** Modify `templates/components/session_table.js` + `templates/components/session_table.css`.

- [ ] **Step 1: Add a multi-day span badge to the date column**

ANCHOR in `session_table.js`, the `date` column render:
```javascript
    { id: 'date', label: 'Date', group: 'identity', align: 'left', sortable: true,
```
Find its `render` function:
```javascript
        if (!s.start) return '';
        try { return escHtml(new Date(s.start).toLocaleString(ctx.locale)); }
        catch (e) { return escHtml(s.start); }
```
Replace those three lines with (keeps the existing date+time, appends a badge for multi-day sessions whose `per_day` has >1 day):
```javascript
        if (!s.start) return '';
        let base;
        try { base = escHtml(new Date(s.start).toLocaleString(ctx.locale)); }
        catch (e) { base = escHtml(s.start); }
        if (s.per_day) {
          const nDays = Object.keys(s.per_day).length;
          if (nDays > 1) {
            let endDay = '';
            try { endDay = s.end ? new Date(s.end).toISOString().slice(0, 10) : ''; } catch (e) {}
            const tip = 'Multi-day session — active through ' + (endDay || '?') + ' (' + nDays + ' days)';
            base += ' <span class="st-multiday" title="' + escHtml(tip) + '">⇴ ' + nDays + 'd</span>';
          }
        }
        return base;
```
(`escHtml` is already used in this function/file. `⇴` is ⇴.)

- [ ] **Step 2: Style the badge**

In `session_table.css`, add:
```css
.st-multiday {
  display: inline-block;
  margin-left: 6px;
  padding: 0 6px;
  font-size: 11px;
  line-height: 16px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--vc-accent) 16%, transparent);
  color: var(--vc-accent);
  white-space: nowrap;
  vertical-align: baseline;
}
```
(If `--vc-accent` is not in scope for this component's CSS, mirror whatever accent token the rest of `session_table.css` uses — grep the file for `--vc-` to confirm the token name.)

- [ ] **Step 3: Verify**

`node -c templates/components/session_table.js`. Confirm the date column still renders date+time for single-day sessions (badge only added when `per_day` has >1 day).

- [ ] **Step 4: Commit**
```bash
git add templates/components/session_table.js templates/components/session_table.css
git commit -m "feat(sessions-table): badge multi-day sessions in the date column"
```

---

## Task D: Session detail — chat date dividers + export dates

**Files:** Modify `templates/session_detail.js` + `templates/session_detail.css`.

- [ ] **Step 1: Add shared date helpers**

ANCHOR the existing helper near the top:
```javascript
function fmtTime(ts) { 
  if(!ts) return ''; 
  const d=new Date(typeof ts==='number'?ts:ts); 
  return d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'}); 
}
```
Immediately after it, add:
```javascript
function fmtDate(ts) {
  if (!ts) return '';
  try { return new Date(ts).toLocaleDateString(); } catch (e) { return ''; }
}
function fmtDateTime(ts) {
  if (!ts) return '';
  const d = fmtDate(ts), t = fmtTime(ts);
  return d ? (t ? d + ' ' + t : d) : t;
}
```

- [ ] **Step 2: Insert day dividers into the chat stream**

ANCHOR:
```javascript
let chatHtml = '';
msgs.forEach((m,i) => {
```
Replace those two lines with (track the calendar day; emit a divider when it changes, including before the first dated message):
```javascript
let chatHtml = '';
let _lastChatDay = null;
msgs.forEach((m,i) => {
  if (m.timestamp) {
    const _d = fmtDate(m.timestamp);
    if (_d && _d !== _lastChatDay) {
      chatHtml += '<div class="day-divider"><span>' + escHtml(_d) + '</span></div>';
      _lastChatDay = _d;
    }
  }
```
(This adds the divider logic at the very start of the existing `forEach` body; the rest of the body is unchanged. Make sure the `forEach` still closes properly — you are only inserting lines after `msgs.forEach((m,i) => {`.)

- [ ] **Step 3: Add `data-ts` to every chat item so copy can include the timestamp**

Each top-level chat item is a `<div class="marker ...">` or `<div class="msg ...">`. Add a `data-ts="<timestamp>"` attribute to EACH of them so the copy handler can read the raw timestamp. Concretely, for every `chatHtml += '<div class="marker ...'` and the `chatHtml += '<div class="msg ...'` opening tag, insert ` data-ts="'+(m.timestamp||'')+'"'` right after the class attribute. The item divs to update (by their class):
- `marker hook`, `marker compaction`, `marker rate-limit`, `marker error`, `marker rejected`, `marker command`, `marker interrupt`, `marker attachment`, `marker mode`, `marker queue`, `marker effort`, `marker agent-dispatch`, and the `msg` div.

Example — change:
```javascript
    chatHtml += '<div class="marker hook event-group" id="marker-'+i+'"><span>&#9881;</span> Hook: '...
```
to:
```javascript
    chatHtml += '<div class="marker hook event-group" data-ts="'+(m.timestamp||'')+'" id="marker-'+i+'"><span>&#9881;</span> Hook: '...
```
and the message div:
```javascript
    chatHtml += '<div class="msg '+m.role+(hasAgentDispatch?' has-agent-dispatch':'')+'" data-ts="'+(m.timestamp||'')+'" id="msg-'+i+'">' +
```
Apply the same ` data-ts="'+(m.timestamp||'')+'"'` insertion to all 12 marker branches + the msg div. (The agent-dispatch marker uses `id="marker-'+i+'-a"`; add data-ts there too.)

- [ ] **Step 4: Day-divider CSS**

In `session_detail.css`, add:
```css
.day-divider {
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 14px 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--vc-fg-3, #6b7280);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.day-divider span {
  padding: 2px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, currentColor 12%, transparent);
}
```
(If `--vc-fg-3` is not defined in this file's scope, grep `session_detail.css` for the muted-foreground token and use it.)

- [ ] **Step 5: Copy export — prepend date+time per item**

ANCHOR the copy handler:
```javascript
document.querySelectorAll('#chatPanel > .msg, #chatPanel > .marker').forEach(el => {
    if (el.style.display === 'none') return;
    if (el.classList.contains('marker')) {
      lines.push('[' + el.textContent.trim() + ']');
    } else {
      const role = el.classList.contains('user') ? 'User' : 'Assistant';
      const content = el.querySelector('.msg-content');
      lines.push('--- ' + role + ' ---');
      lines.push(content ? content.textContent.trim() : '');
    }
    lines.push('');
  });
```
Replace with (read `data-ts`, prepend a `[date time]` stamp):
```javascript
document.querySelectorAll('#chatPanel > .msg, #chatPanel > .marker').forEach(el => {
    if (el.style.display === 'none') return;
    const stamp = fmtDateTime(el.getAttribute('data-ts'));
    if (el.classList.contains('marker')) {
      lines.push('[' + (stamp ? stamp + ' ' : '') + el.textContent.trim() + ']');
    } else {
      const role = el.classList.contains('user') ? 'User' : 'Assistant';
      const content = el.querySelector('.msg-content');
      lines.push('--- ' + role + (stamp ? ' (' + stamp + ')' : '') + ' ---');
      lines.push(content ? content.textContent.trim() : '');
    }
    lines.push('');
  });
```

- [ ] **Step 6: Markdown export — include date in per-message heading**

ANCHOR in `buildMarkdown`:
```javascript
    let ts = '';
    if (m.timestamp) {
      try { ts = new Date(m.timestamp).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'}); } catch(e) {}
    }
```
Replace with (date + time):
```javascript
    let ts = '';
    if (m.timestamp) {
      try { ts = fmtDateTime(m.timestamp); } catch(e) {}
    }
```
(The headings `'## User' + (ts ? ' — ' + ts : '')` now show date + time. The YAML frontmatter `date:`/`start:` stay as-is.)

- [ ] **Step 7: Verify**

`node -c templates/session_detail.js`. Then regenerate (`python3 extract_stats.py`) and render the session_detail of a known multi-day session headless (e.g. session `5bc2bc3b...`): confirm day dividers appear between 2026-06-10/06-11/06-12, the copy output (simulate by evaluating the copy handler logic over the DOM) includes `[date time ...]`, and `buildMarkdown` output contains `## User — <date> <time>`. Report what you ran.

- [ ] **Step 8: Commit**
```bash
git add templates/session_detail.js templates/session_detail.css
git commit -m "feat(session-detail): chat day dividers + dates in copy and markdown exports"
```

---

## Task E: End-to-end smoke + reconciliation

- [ ] **Step 1:** `python3 extract_stats.py` (rebuild). `python3 -m pytest tests/ -q` (still green).
- [ ] **Step 2:** Headless-load `public/index.html`: 0 console errors; the hourly chart and weekday chart render; toggle a date-range filter (e.g. 30 days) and confirm no error and that the hourly chart updates. Open a multi-day session detail and confirm day dividers.
- [ ] **Step 3:** Data assertions:
```bash
python3 -c "
import json; d=json.load(open('public/dashboard_data.json'))
print('hourly sum:', sum(x['messages'] for x in d['hourly_distribution']))
print('msg sum:', sum(x['messages'] for x in d['sessions']))
print('multi-day sessions (per_day):', sum(1 for s in d['sessions'] if s.get('per_day')))
"
```
Expected: hourly sum ≈ msg sum (per-message attribution preserves the total).
