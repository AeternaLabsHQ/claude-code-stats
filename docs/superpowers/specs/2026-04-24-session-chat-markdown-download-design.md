# Session Chat Markdown Download

Date: 2026-04-24
Status: Approved for planning

## Summary

Add the ability to download session chats as Markdown:

1. **Single-session download** — a new `Download` button next to the existing `Copy` button on the session detail page (`sessions/<id>.html`). Produces one `.md` file, respecting the active role filter.
2. **Bulk download** — a new `Download all (N)` button in the sessions overview filter bar (`index.html` sessions tab). Produces a ZIP containing one `.md` per currently filtered session.

## Motivation

Users want to export chat transcripts for archiving, search in external tools (e.g. Obsidian), or for sharing. Copy-to-clipboard exists but is (a) plaintext only, (b) single-session only, and (c) requires manual paste into a file.

## Scope

### In scope
- Markdown export for a single session (filter-aware).
- Bulk export of the currently filtered session set as a ZIP of `.md` files.
- Client-side only. No server endpoint, no new Python emission beyond button markup.

### Out of scope
- Including tool calls, hook markers, compaction markers, agent-dispatch markers in the Markdown (chat content only — format "B").
- Other export formats (JSON, PDF, HTML).
- Selecting a subset of filtered sessions (no per-card checkboxes). The filter *is* the selection.

## UX

### Single session (`sessions/<id>.html`)

- New button `⬇ Download` in `.chat-toolbar`, immediately to the right of the `Copy` button.
- Uses the same CSS hover/active treatment as `.copy-btn` (reuse the class or add a sibling `.download-btn` with identical styling).
- Respects the active role filter (`All` / `User` / `Agent` / `Subagents`) exactly like `Copy` does — it iterates `#chatPanel > .msg, #chatPanel > .marker` and skips elements with `display: none`. For the Markdown export, only `.msg` elements are included (markers are excluded even when visible — chat content only, per format B).
- On click: builds the Markdown string, triggers a `Blob` + temporary `<a download>` click, then revokes the object URL.
- No loading state needed — building one session's Markdown is synchronous and instant.

### Bulk (`index.html` sessions tab)

- New button `⬇ Download all (N)` placed at the right end of the `.session-filters` bar, after `#sessionCount`. `N` updates whenever `renderSessionList` runs (same count as `sessionCount`).
- Disabled state (greyed out, `pointer-events: none`) when `N === 0`.
- Disabled during an in-flight bulk download (prevents re-entry).
- On click:
  1. If `N > 100`, show `confirm("N Sessions als ZIP herunterladen? Das kann einen Moment dauern.")`. Cancel aborts.
  2. Lazy-load JSZip from CDN if not already loaded (`<script>` tag appended to `<head>`, awaited via a Promise on `load`).
  3. For each filtered session, sequentially `fetch('sessions/<id>.html')`, extract the embedded session JSON, build Markdown, add to ZIP.
  4. Button text updates to `Loading 12/50…` during the run.
  5. On completion, trigger download of `claude-sessions-<YYYY-MM-DD>.zip` and reset the button text.
  6. If any sessions failed, show `alert("X sessions konnten nicht geladen werden — siehe Konsole.")` after the ZIP download, with details logged via `console.warn`.

## Markdown format

Both single and bulk downloads produce the same per-session format.

### Filename

`<YYYY-MM-DD>-<project-slug>-<session-id-8>.md`

- `YYYY-MM-DD` — session start date (local timezone of the browser, matching how dates are shown in the UI).
- `project-slug` — the session's project name, lowercased, non-alphanumerics collapsed to `-`, trimmed of leading/trailing `-`, capped at 40 chars. If empty after sanitization, use `unknown`.
- `session-id-8` — first 8 chars of the session UUID.

Example: `2026-04-17-music-0093ac4b.md`

Separator is **always `-`**. No underscores anywhere in the filename.

If the sanitized filename collides with an earlier one in the ZIP (same date + slug + id-8), append `-2`, `-3`, … before `.md`. Collisions are astronomically unlikely but cheap to guard against.

### Content structure

```markdown
---
session_id: 0093ac4b-9efb-45fd-a346-9b5731293f6d
project: Users/andie
date: 2026-04-17
start: 2026-04-17T07:16:51Z
duration_min: 0.4
model: Opus 4.7
messages: 3
cost_usd: 0.1738
source: galatea:andie
---

# <Title>

## User — 07:16:51
<content verbatim>

## Assistant (Opus 4.7) — 07:17:17
<content verbatim>
```

**Frontmatter fields** (YAML, pulled from `S.session`):
- `session_id` — full UUID
- `project` — `project` field verbatim
- `date` — `date` field (already `YYYY-MM-DD`)
- `start` — `start` field, ISO 8601 trimmed to seconds
- `duration_min` — numeric
- `model` — `primary_model`
- `messages` — numeric
- `cost_usd` — numeric, 4 decimal places
- `source` — only emitted if truthy

String values that contain YAML-significant characters (`:`, `#`, `"`, newline) are emitted as double-quoted strings with `"` escaped as `\"`.

**Title (`# <Title>`):** first line of `first_prompt`, trimmed, capped at 80 chars with `…` appended if truncated. If `first_prompt` is empty, use `Session <session-id-8>`.

**Per-message heading:**
- User: `## User — HH:MM:SS`
- Assistant: `## Assistant (<model>) — HH:MM:SS` — model omitted from heading if missing.
- Time format matches the UI: `HH:MM:SS` in the browser's locale timezone, same `fmtTime` helper logic.

**Message content:** written verbatim (the Markdown the assistant produced is already Markdown; user content is treated as Markdown too). No escaping of fences — if the content contains ` ``` `, it stays as-is. We don't wrap content in a code fence; we emit it as body text under the heading.

**Excluded from the Markdown:** tool calls, hook markers, compaction markers, agent-dispatch markers, subagent prompts. Chat content only.

## Data source

- **Single session:** read directly from `S.messages` / `S.session` already in the page.
- **Bulk:** fetch each `sessions/<id>.html`, extract the session JSON.

### Parsing the session HTML

Each session page contains exactly one line of the form:

```js
const S = {"session": {...}, "messages": [...]};
```

Extraction approach: `fetch(url).then(r => r.text())`, then a non-greedy regex `/const S = (\{.*?\});\s*\n/` with the `s` flag, then `JSON.parse` on the captured group. A single failure (fetch error, regex miss, JSON parse error) logs to console and increments the failure counter; the ZIP continues with the remaining sessions.

## Implementation notes

All code lives in `extract_stats.py` since the HTML/JS is emitted from Python string templates.

### Files touched
- `extract_stats.py` — the only file.

### Where changes land in `extract_stats.py`

1. **Session detail template** (around the `.chat-toolbar` / `copyBtn` block near line 4063, and the copy-to-clipboard handler near line 4187):
   - Add a `downloadBtn` next to `copyBtn`.
   - Add a shared helper `buildMarkdown(session, messages)` — pure function, no DOM access, so the same helper is reused by the bulk downloader via copy-paste into the dashboard template.
   - Add a click handler that filters messages by active role, calls `buildMarkdown`, triggers the download.

2. **Dashboard sessions tab template** (around lines 2236–2250 in the filter bar, and the `renderSessionList` function near line 3137, plus a new handler somewhere near `getFilteredSessions`):
   - Add the `Download all` button to the filter bar.
   - Update `renderSessionList` to refresh the button label with the current `N` and toggle disabled state.
   - Add a bulk handler that: lazy-loads JSZip, iterates filtered sessions, fetches + parses each, builds Markdown via the same `buildMarkdown` helper, assembles ZIP, triggers download.

### JSZip loading

```js
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

Integrity hash is skipped for now (adds complexity, the CDN is cloudflare's, and offline use was never a requirement for a static dashboard).

If JSZip fails to load (e.g. offline), the bulk handler shows `alert("ZIP-Bibliothek konnte nicht geladen werden (offline?).")` and aborts.

### Filename sanitization

```js
function slugifyProject(p) {
  const s = (p || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 40);
  return s || 'unknown';
}
```

### Fetch strategy

Sequential via `for…of` with `await`. Not parallel. Reasons:
- Browsers cap parallel fetches per origin at ~6 — parallelism provides no real speedup for 50+ files.
- Sequential gives an honest progress indicator.
- Simpler error accounting.

### Memory

For N = 500 sessions at ~500 KB each, peak memory inside the ZIP builder is ~250 MB before download. That's survivable on desktop browsers but worth noting. No optimization until it actually hurts someone; if it does, a future follow-up could stream via `JSZip.generateInternalStream`. Out of scope for this change.

## Testing

Manual testing steps:

1. **Single download, no filter** — open a session page, click Download, open the resulting `.md`. Verify frontmatter, title, headings, all messages present in order, no tool/marker artifacts.
2. **Single download with role filter** — switch to `User` filter, click Download, verify only user messages are in the `.md`.
3. **Bulk download, small set** — filter to a single project with ~5 sessions, click Download all. Verify ZIP contains 5 `.md` files with correct names and content.
4. **Bulk download, large set** — no filter (all sessions). Verify confirm dialog appears if `N > 100`. Verify progress counter updates. Verify resulting ZIP opens and contains all sessions.
5. **Bulk download with one bad session** — temporarily rename one `sessions/<id>.html` file to simulate 404. Verify the bulk download completes, the ZIP contains the rest, and the post-run alert mentions the failure.
6. **Filename edge cases** — session with no project, session with punctuation in project name, two sessions with identical date + project + id8 prefix (collision path).
7. **Offline** — disconnect network, click Download all. Verify graceful failure alert.

There are no automated tests in this project, so testing is manual.

## Open questions

None — all design choices confirmed during brainstorming.
