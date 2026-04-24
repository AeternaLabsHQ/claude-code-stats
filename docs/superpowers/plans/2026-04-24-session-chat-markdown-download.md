# Session Chat Markdown Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Markdown download of session chats — single-session (next to Copy) and bulk (all currently filtered sessions as a ZIP).

**Architecture:** All changes land in `extract_stats.py`, which generates static HTML. Two template functions are modified: `_get_session_html_template()` (session detail page, ~L3930) and `_get_html_template()` (dashboard, ~L1941). A shared set of JS helpers (`buildMarkdown`, `mdFilename`, `sanitizeProjectSlug`, `yamlEscape`, `triggerDownload`) is duplicated into both templates — the project has no JS module system and no build pipeline, so sharing via copy is the path of least resistance. Bulk download lazy-loads JSZip from a CDN, sequentially fetches each `sessions/<id>.html`, extracts the embedded `const S = {...};` JSON via regex, and packages the resulting Markdown files into a ZIP.

**Tech Stack:** Python 3 (string-template HTML generation), vanilla JS in the browser, JSZip 3.10.1 (CDN, lazy-loaded). No tests — verification is manual via `python extract_stats.py` + browser.

**Design doc:** `docs/superpowers/specs/2026-04-24-session-chat-markdown-download-design.md`

**Gotcha (Python string escaping):** All JS lives inside Python `'''...'''` strings (not f-strings). JS backslash escapes must be doubled in the Python source: `\n` → `\\n`, `\d` → `\\d`, `\s` → `\\s`, `\w` → `\\w`, `\{` → `\\{`. JS template literals (backticks) are fine. Curly braces are fine (no f-string). Dollar signs are fine.

---

## File Structure

**Modified files:**
- `extract_stats.py`
  - `_get_session_html_template()` (~L3930–L5543): add Download button, CSS if needed, JS helpers, single-session click handler.
  - `_get_html_template()` (~L1941–L3739): add bulk Download button to sessions filter bar, CSS if needed, JS helpers (duplicated), JSZip loader, bulk click handler, integration with `renderSessionList`.

**No new files.** No tests (project has none).

**Not touched:** `update_dashboard.sh`, deploy infrastructure (local-only per project convention), generated HTML in `public/`.

---

## Task 1: Single-session Markdown download

**Files:**
- Modify: `extract_stats.py` — `_get_session_html_template()` (~L3930–L5543)

This task adds a `Download` button next to `Copy` on the session detail page (`sessions/<id>.html`), building a Markdown file from messages visible under the current role filter.

- [ ] **Step 1: Add the Download button to the chat toolbar**

Find the existing `copyBtn` line (~L4063) inside `_get_session_html_template()`:

```html
        <button class="copy-btn" id="copyBtn">&#128203; Copy</button>
```

Replace it with:

```html
        <button class="copy-btn" id="copyBtn">&#128203; Copy</button>
        <button class="copy-btn" id="downloadBtn" style="margin-left:6px" title="Download filtered messages as Markdown">&#11015; Download</button>
```

Reusing `.copy-btn` class means no new CSS. `margin-left:6px` inlines the small gap between the two buttons (the existing `margin-left:auto` on `.copy-btn` pushes the first button right; the second needs its own small left margin).

- [ ] **Step 2: Add JS helpers just before the Copy-to-clipboard handler**

Find the existing comment (~L4186):

```js
// Copy to clipboard
document.getElementById('copyBtn').addEventListener('click', function() {
```

Insert this block **immediately before** that comment line (in the Python source, mind the doubled backslashes):

```js
// ─── Markdown export helpers ───────────────────────────────────────────
function sanitizeProjectSlug(p) {
  const s = (p || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
  return s || 'unknown';
}
function mdFilename(session) {
  const date = session.date || (session.start ? String(session.start).slice(0,10) : '0000-00-00');
  const slug = sanitizeProjectSlug(session.project);
  const id8 = (session.session_id || '').slice(0, 8);
  return date + '-' + slug + '-' + id8 + '.md';
}
function yamlEscape(v) {
  if (v == null) return '';
  const str = String(v);
  if (/[:#"\\n]/.test(str)) return '"' + str.replace(/"/g, '\\\\"') + '"';
  return str;
}
function buildMarkdown(session, messages) {
  const lines = [];
  lines.push('---');
  lines.push('session_id: ' + yamlEscape(session.session_id));
  lines.push('project: ' + yamlEscape(session.project));
  lines.push('date: ' + yamlEscape(session.date));
  let startIso = '';
  if (session.start) {
    try { startIso = new Date(session.start).toISOString().replace(/\\.\\d{3}Z$/, 'Z'); } catch(e) { startIso = String(session.start); }
  }
  lines.push('start: ' + yamlEscape(startIso));
  lines.push('duration_min: ' + (session.duration_min != null ? session.duration_min : 0));
  lines.push('model: ' + yamlEscape(session.primary_model));
  lines.push('messages: ' + (session.messages != null ? session.messages : 0));
  lines.push('cost_usd: ' + (typeof session.cost === 'number' ? session.cost.toFixed(4) : '0.0000'));
  if (session.source) lines.push('source: ' + yamlEscape(session.source));
  lines.push('---');
  lines.push('');

  let title = ((session.first_prompt || '').split('\\n')[0] || '').trim();
  if (title.length > 80) title = title.slice(0, 80) + '\\u2026';
  if (!title) title = 'Session ' + ((session.session_id || '').slice(0, 8));
  lines.push('# ' + title);
  lines.push('');

  messages.forEach(m => {
    if (m.role !== 'user' && m.role !== 'assistant') return;
    let ts = '';
    if (m.timestamp) {
      try { ts = new Date(m.timestamp).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'}); } catch(e) {}
    }
    if (m.role === 'user') {
      lines.push('## User' + (ts ? ' \\u2014 ' + ts : ''));
    } else {
      const model = m.model ? ' (' + m.model + ')' : '';
      lines.push('## Assistant' + model + (ts ? ' \\u2014 ' + ts : ''));
    }
    lines.push('');
    lines.push(m.content || '');
    lines.push('');
  });
  return lines.join('\\n');
}
function triggerDownload(filename, content, mimeType) {
  const blob = content instanceof Blob ? content : new Blob([content], {type: mimeType || 'text/markdown;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
}
```

- [ ] **Step 3: Add the download click handler just after the Copy handler**

Find the closing `});` of the Copy handler (~L4207) — the block that ends with `}, 2000); });`:

```js
  navigator.clipboard.writeText(lines.join('\\n')).then(() => {
    btn.innerHTML = '&#10003; Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.innerHTML = '&#128203; Copy'; btn.classList.remove('copied'); }, 2000);
  });
});
```

Insert **immediately after** that `});`:

```js
// Download filtered chat as Markdown
document.getElementById('downloadBtn').addEventListener('click', function() {
  const btn = this;
  const visible = [];
  document.querySelectorAll('#chatPanel > .msg').forEach(el => {
    if (el.style.display === 'none') return;
    const m = el.id.match(/^msg-(\\d+)$/);
    if (m) visible.push(parseInt(m[1], 10));
  });
  const filtered = visible.map(i => msgs[i]).filter(m => m && (m.role === 'user' || m.role === 'assistant'));
  const md = buildMarkdown(sess, filtered);
  triggerDownload(mdFilename(sess), md);
  btn.innerHTML = '&#10003; Downloaded!';
  btn.classList.add('copied');
  setTimeout(() => { btn.innerHTML = '&#11015; Download'; btn.classList.remove('copied'); }, 2000);
});
```

- [ ] **Step 4: Regenerate session pages and spot-check one in a browser**

Run:

```bash
cd /home/andie/projects/claude-stats
python extract_stats.py
```

Expected: script completes without Python errors. Look for a line like `Generated N session pages in public/sessions`.

Then open one generated session page in a browser:

```bash
xdg-open public/sessions/0093ac4b-9efb-45fd-a346-9b5731293f6d.html
```

(Any `.html` file in `public/sessions/` will do; pick one that exists — `ls public/sessions/ | head -1`.)

Verify:
- Two buttons visible in the toolbar: `📋 Copy` and `⬇ Download`.
- Click Download — a `.md` file downloads with filename pattern `YYYY-MM-DD-<slug>-<id8>.md` (dashes only, no underscores).
- Open the `.md` file. Verify:
  - YAML frontmatter present with `session_id`, `project`, `date`, `start`, `duration_min`, `model`, `messages`, `cost_usd`, and (if applicable) `source`.
  - A `# Title` heading after the frontmatter (first line of first prompt, or `Session <id8>` fallback).
  - Messages alternate under `## User — HH:MM:SS` / `## Assistant (<model>) — HH:MM:SS` headings, content verbatim below.
  - No tool calls, hook markers, compaction markers in the output.
- Switch role filter to `User` on the page, click Download, open the `.md`. Verify only user messages appear.
- Switch to `Assistant`, download, verify only assistant messages appear.

If any check fails, go back to Step 1–3 and fix before committing.

- [ ] **Step 5: Commit**

```bash
cd /home/andie/projects/claude-stats
git add extract_stats.py
git commit -m "$(cat <<'EOF'
feat: add per-session Markdown download button

Adds a Download button next to Copy on the session detail page.
Respects the active role filter (All / User / Agent / Subagents).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Do **not** `git add public/sessions/` — generated artifacts are not checked in on feature branches (only deploy infra handles those, and is local-only per project convention).

---

## Task 2: Bulk Markdown download (filtered sessions → ZIP)

**Files:**
- Modify: `extract_stats.py` — `_get_html_template()` (~L1941–L3739)

This task adds a `⬇ Download all (N)` button to the sessions-tab filter bar in the dashboard, lazy-loads JSZip, sequentially fetches each filtered session's HTML, extracts the embedded session JSON, and builds a ZIP of Markdown files.

- [ ] **Step 1: Add the bulk Download button to the session filter bar**

Find the existing filter bar inside the sessions tab (~L2236–L2248 in `_get_html_template()`):

```html
    <div class="session-filters">
      <select id="filterProject"><option value="">__L_sessions_tab_all_projects__</option></select>
      <select id="filterSource"><option value="">All Sources</option></select>
      <select id="filterSort">
        <option value="date-desc">__L_sessions_tab_sort_date_desc__</option>
        <option value="date-asc">__L_sessions_tab_sort_date_asc__</option>
        <option value="cost-desc">__L_sessions_tab_sort_cost_desc__</option>
        <option value="cost-asc">__L_sessions_tab_sort_cost_asc__</option>
        <option value="messages-desc">__L_sessions_tab_sort_messages_desc__</option>
      </select>
      <input type="text" id="filterSearch" placeholder="__L_sessions_tab_search_placeholder__">
      <span class="meta" id="sessionCount"></span>
    </div>
```

Replace with (adds one new `<button>` after `sessionCount`):

```html
    <div class="session-filters">
      <select id="filterProject"><option value="">__L_sessions_tab_all_projects__</option></select>
      <select id="filterSource"><option value="">All Sources</option></select>
      <select id="filterSort">
        <option value="date-desc">__L_sessions_tab_sort_date_desc__</option>
        <option value="date-asc">__L_sessions_tab_sort_date_asc__</option>
        <option value="cost-desc">__L_sessions_tab_sort_cost_desc__</option>
        <option value="cost-asc">__L_sessions_tab_sort_cost_asc__</option>
        <option value="messages-desc">__L_sessions_tab_sort_messages_desc__</option>
      </select>
      <input type="text" id="filterSearch" placeholder="__L_sessions_tab_search_placeholder__">
      <span class="meta" id="sessionCount"></span>
      <button id="bulkDownloadBtn" class="bulk-download-btn" style="margin-left:auto" title="Download all currently filtered sessions as a ZIP of Markdown files">&#11015; Download all (0)</button>
    </div>
```

- [ ] **Step 2: Add CSS for the bulk download button**

Find the `.session-filters` CSS block in `_get_html_template()`. Search for the string `.session-filters` — there will be a CSS rule somewhere between L1960 and L2200. Append this rule immediately after it (keep existing styles untouched):

```css
.bulk-download-btn { padding: 6px 14px; font-size: 12px; font-weight: 600; border: 1px solid var(--border); background: var(--bg2); color: var(--text2); cursor: pointer; border-radius: 6px; transition: all 0.15s; display: inline-flex; align-items: center; gap: 4px; }
.bulk-download-btn:hover:not(:disabled) { background: var(--bg3); color: var(--text); }
.bulk-download-btn:disabled { opacity: 0.5; cursor: not-allowed; }
```

If the exact `.session-filters` selector is hard to locate by eye, just append this CSS block at the end of the `<style>` block (find `</style>` and insert above it) — CSS specificity is fine either way.

- [ ] **Step 3: Add the shared JS helpers to the dashboard template**

These are the **same helpers** as in Task 1 Step 2 (`sanitizeProjectSlug`, `mdFilename`, `yamlEscape`, `buildMarkdown`, `triggerDownload`), plus a `loadJSZip` function. Duplication is intentional — see plan header.

Find the `getFilteredSessions` function (~L2997):

```js
function getFilteredSessions() {
  let list = [...F.sessions];
```

Insert this block **immediately before** `function getFilteredSessions()` (mind the doubled backslashes — this is inside a Python `'''...'''` string):

```js
// ─── Markdown export helpers ───────────────────────────────────────────
function sanitizeProjectSlug(p) {
  const s = (p || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
  return s || 'unknown';
}
function mdFilename(session) {
  const date = session.date || (session.start ? String(session.start).slice(0,10) : '0000-00-00');
  const slug = sanitizeProjectSlug(session.project);
  const id8 = (session.session_id || '').slice(0, 8);
  return date + '-' + slug + '-' + id8 + '.md';
}
function yamlEscape(v) {
  if (v == null) return '';
  const str = String(v);
  if (/[:#"\\n]/.test(str)) return '"' + str.replace(/"/g, '\\\\"') + '"';
  return str;
}
function buildMarkdown(session, messages) {
  const lines = [];
  lines.push('---');
  lines.push('session_id: ' + yamlEscape(session.session_id));
  lines.push('project: ' + yamlEscape(session.project));
  lines.push('date: ' + yamlEscape(session.date));
  let startIso = '';
  if (session.start) {
    try { startIso = new Date(session.start).toISOString().replace(/\\.\\d{3}Z$/, 'Z'); } catch(e) { startIso = String(session.start); }
  }
  lines.push('start: ' + yamlEscape(startIso));
  lines.push('duration_min: ' + (session.duration_min != null ? session.duration_min : 0));
  lines.push('model: ' + yamlEscape(session.primary_model));
  lines.push('messages: ' + (session.messages != null ? session.messages : 0));
  lines.push('cost_usd: ' + (typeof session.cost === 'number' ? session.cost.toFixed(4) : '0.0000'));
  if (session.source) lines.push('source: ' + yamlEscape(session.source));
  lines.push('---');
  lines.push('');

  let title = ((session.first_prompt || '').split('\\n')[0] || '').trim();
  if (title.length > 80) title = title.slice(0, 80) + '\\u2026';
  if (!title) title = 'Session ' + ((session.session_id || '').slice(0, 8));
  lines.push('# ' + title);
  lines.push('');

  messages.forEach(m => {
    if (m.role !== 'user' && m.role !== 'assistant') return;
    let ts = '';
    if (m.timestamp) {
      try { ts = new Date(m.timestamp).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'}); } catch(e) {}
    }
    if (m.role === 'user') {
      lines.push('## User' + (ts ? ' \\u2014 ' + ts : ''));
    } else {
      const model = m.model ? ' (' + m.model + ')' : '';
      lines.push('## Assistant' + model + (ts ? ' \\u2014 ' + ts : ''));
    }
    lines.push('');
    lines.push(m.content || '');
    lines.push('');
  });
  return lines.join('\\n');
}
function triggerDownload(filename, content, mimeType) {
  const blob = content instanceof Blob ? content : new Blob([content], {type: mimeType || 'text/markdown;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 100);
}
function loadJSZip() {
  if (window.JSZip) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';
    s.onload = resolve;
    s.onerror = () => reject(new Error('Failed to load JSZip'));
    document.head.appendChild(s);
  });
}
```

- [ ] **Step 4: Add the bulk download handler and button-label updater**

Find `function renderSessionList()` (~L3137):

```js
function renderSessionList() {
  const filtered = getFilteredSessions();
  const total = filtered.length;
```

Insert this block **immediately before** `function renderSessionList()`:

```js
function updateBulkBtnLabel() {
  const btn = document.getElementById('bulkDownloadBtn');
  if (!btn) return;
  const n = getFilteredSessions().length;
  if (!btn.dataset.busy) {
    btn.textContent = '\\u2B07 Download all (' + n + ')';
    btn.disabled = (n === 0);
  }
}
async function bulkDownloadSessions() {
  const btn = document.getElementById('bulkDownloadBtn');
  const sessions = getFilteredSessions();
  if (sessions.length === 0) return;
  if (sessions.length > 100 && !confirm(sessions.length + ' Sessions als ZIP herunterladen? Das kann einen Moment dauern.')) return;

  btn.dataset.busy = '1';
  btn.disabled = true;

  try { await loadJSZip(); }
  catch (e) {
    alert('ZIP-Bibliothek konnte nicht geladen werden (offline?).');
    delete btn.dataset.busy;
    updateBulkBtnLabel();
    return;
  }

  const zip = new JSZip();
  const usedNames = new Set();
  let errors = 0;

  for (let i = 0; i < sessions.length; i++) {
    btn.textContent = 'Loading ' + (i + 1) + '/' + sessions.length + '\\u2026';
    try {
      const resp = await fetch('sessions/' + sessions[i].session_id + '.html');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      const text = await resp.text();
      const m = text.match(/const S = (\\{[\\s\\S]*?\\});\\s*\\nconst FLOW/);
      if (!m) throw new Error('Session JSON not found in HTML');
      const data = JSON.parse(m[1]);
      const md = buildMarkdown(data.session, data.messages);
      let name = mdFilename(data.session);
      if (usedNames.has(name)) {
        let n = 2;
        let candidate;
        do { candidate = name.replace(/\\.md$/, '-' + n + '.md'); n++; } while (usedNames.has(candidate));
        name = candidate;
      }
      usedNames.add(name);
      zip.file(name, md);
    } catch (e) {
      errors++;
      console.warn('Session ' + sessions[i].session_id + ' failed:', e);
    }
  }

  btn.textContent = 'Zipping\\u2026';
  const blob = await zip.generateAsync({type: 'blob'});
  const today = new Date().toISOString().slice(0, 10);
  triggerDownload('claude-sessions-' + today + '.zip', blob, 'application/zip');

  delete btn.dataset.busy;
  updateBulkBtnLabel();

  if (errors > 0) {
    alert(errors + ' sessions konnten nicht geladen werden \\u2014 siehe Konsole.');
  }
}
```

- [ ] **Step 5: Wire the handler and the label updater**

Find the end of `renderSessionList()` — the function ends with a closing `}` around L3174. The function currently ends with a pagination block followed by `}`:

```js
    if (sessionPage < pages - 1) {
      const next = document.createElement('button'); next.textContent = '›';
      next.addEventListener('click', () => { sessionPage++; renderSessionList(); });
      const last = document.createElement('button'); last.textContent = '»';
      last.addEventListener('click', () => { sessionPage = pages - 1; renderSessionList(); });
      pagDiv.appendChild(next); pagDiv.appendChild(last);
    }
  }
}
```

Change the final `}` section to:

```js
    if (sessionPage < pages - 1) {
      const next = document.createElement('button'); next.textContent = '›';
      next.addEventListener('click', () => { sessionPage++; renderSessionList(); });
      const last = document.createElement('button'); last.textContent = '»';
      last.addEventListener('click', () => { sessionPage = pages - 1; renderSessionList(); });
      pagDiv.appendChild(next); pagDiv.appendChild(last);
    }
  }
  updateBulkBtnLabel();
}
```

(One new line: `updateBulkBtnLabel();` just before the function's closing `}`.)

Then find where `renderSessions();` is first called at module load (~L3701 — the very last line of the sessions-tab JS, at the end of the sessions rendering block). Right after that, add a one-liner to wire the click:

```js
renderSessions();
document.getElementById('bulkDownloadBtn').addEventListener('click', bulkDownloadSessions);
```

(If `renderSessions();` at L3701 appears inside a larger init block, place the `addEventListener` immediately after it either way.)

- [ ] **Step 6: Regenerate the dashboard and verify the bulk download end-to-end**

Run:

```bash
cd /home/andie/projects/claude-stats
python extract_stats.py
```

Expected: completes without errors. Dashboard written to `public/index.html`.

Open the dashboard:

```bash
xdg-open public/index.html
```

Switch to the `Sessions` tab. Verify:

**Button render & label:**
- A `⬇ Download all (N)` button is visible at the right end of the filter row.
- `N` matches the `sessionCount` text next to it.
- When filters change (e.g. pick a project), `N` updates to match.

**Small bulk download (≤ 100):**
- Filter to a project with a handful of sessions (say 3–10).
- Click `Download all`. Button text changes to `Loading 1/N…`, then `Loading 2/N…`, then `Zipping…`, then downloads `claude-sessions-<today>.zip`.
- Open the ZIP. Verify file count matches N. Filenames follow `YYYY-MM-DD-<slug>-<id8>.md`. Open two files — verify frontmatter + chat content, same format as single-session download.

**Large bulk download:**
- Remove all filters so N > 100.
- Click `Download all`. Confirm dialog appears (`N Sessions als ZIP herunterladen? Das kann einen Moment dauern.`).
- Cancel → nothing happens.
- Accept → download completes (may take 30 s–2 min depending on N). Verify ZIP opens.

**Role filter does NOT apply to bulk:**
- (The sessions-tab filter bar has no role filter; this is only on the session detail page. Bulk downloads always contain full chats per spec. Nothing to test on the dashboard side beyond confirming no hidden role filter got wired in.)

**Failure path:**
- With the dashboard open, rename one session file temporarily:
  ```bash
  FILE=$(ls public/sessions/ | head -1)
  mv "public/sessions/$FILE" "public/sessions/${FILE}.hidden"
  ```
- Reload the dashboard, filter to include that session (or use a wide filter that includes it), click `Download all`.
- Verify: download completes with N-1 files, and an alert appears: `1 sessions konnten nicht geladen werden — siehe Konsole.`
- Open devtools → Console — verify the warning naming the failed session id.
- Restore:
  ```bash
  mv "public/sessions/${FILE}.hidden" "public/sessions/$FILE"
  ```

**Empty state:**
- Apply a filter that produces 0 sessions (e.g. search for `zzzzzzzzz`).
- Verify the button shows `Download all (0)` and is disabled (greyed out).

**Offline path:**
- In devtools → Network, enable "Offline".
- Click `Download all` (on a small filter). Since JSZip loads from CDN, this should produce the alert `ZIP-Bibliothek konnte nicht geladen werden (offline?).` (Note: if JSZip was already loaded in a prior successful click, this path won't fire — test in a fresh tab.)
- Re-enable network.

If any check fails, return to Steps 1–5 and fix.

- [ ] **Step 7: Commit**

```bash
cd /home/andie/projects/claude-stats
git add extract_stats.py
git commit -m "$(cat <<'EOF'
feat: add bulk session Markdown download (ZIP)

Adds a Download all (N) button to the sessions-tab filter bar.
Lazy-loads JSZip from CDN, sequentially fetches each filtered
session's HTML, extracts the embedded session JSON, and packages
Markdown files into claude-sessions-<date>.zip.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Final end-to-end verification

**Files:** none modified — verification only.

- [ ] **Step 1: Regenerate everything from scratch**

```bash
cd /home/andie/projects/claude-stats
python extract_stats.py
```

Expected: finishes without errors, prints generation summary.

- [ ] **Step 2: Cross-template consistency check**

Open a session page directly (e.g. `public/sessions/<id>.html`), download via the single-session button. Note the filename.

Then open the dashboard, filter so that same session is in the result set, run Download all, extract ZIP. Find the same session's `.md` in the ZIP.

**Diff the two files:**

```bash
diff /path/to/single-download.md /path/to/zip-extracted.md
```

Expected: identical content when the session page had no role filter applied. (If files differ, check that the session detail page's role filter was `All` during the single download.)

- [ ] **Step 3: Spot-check one downloaded Markdown file in an actual Markdown viewer**

Open one `.md` in a Markdown viewer (VS Code preview, Obsidian, `pandoc`, or similar). Verify:
- Frontmatter renders as frontmatter (not as body text).
- Headings render as headings.
- Code fences inside the assistant's content render correctly (not broken by our emission).
- Non-ASCII characters (umlauts, em dashes in source content) display correctly.

- [ ] **Step 4: Final commit is clean**

```bash
git status
```

Expected: nothing staged or modified. All changes were committed in Tasks 1 and 2. `public/` is dirty (regenerated artifacts) but not tracked on this branch.

- [ ] **Step 5: Summary to user**

State what shipped, which files changed, and any manual steps required to deploy (the user runs `update_dashboard.sh` locally on their own cadence — do not run it from the plan).

---

## Rollback

If anything regresses, revert both commits:

```bash
git log --oneline -5
git revert <task2-sha> <task1-sha>
```

Both commits are scoped to `extract_stats.py` and touch only additive changes (new buttons, new helpers, one new line inside `renderSessionList`). A revert cleanly restores the pre-feature state.
