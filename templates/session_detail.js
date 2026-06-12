
const S = "__SESSION_DATA__";
const FLOW = "__FLOW_DATA__";
const sess = S.session;
const msgs = S.messages;
const fmt = n => n.toLocaleString();
const fmtUSD = n => '$' + n.toFixed(4);
const fmtTokens = n => { if(n>=1e6) return (n/1e6).toFixed(1)+'M'; if(n>=1e3) return (n/1e3).toFixed(1)+'K'; return n.toString(); };
// Standard context window caps the prompt near 200k; a turn over this ran with
// the 1M-context window enabled. Keep in sync with CONTEXT_1M_THRESHOLD (extract_stats.py).
const CONTEXT_1M_THRESHOLD = 200000;
const turnContext = t => (t ? (t.input||0) + (t.cache_read||0) + (t.cache_write||0) : 0);
const ctx1mBadge = title => '<span class="ctx-1m-badge" title="'+escHtml(title)+'">1M</span>';
function escHtml(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
function fmtTime(ts) { if(!ts) return ''; const d=new Date(typeof ts==='number'?ts:ts); return d.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit',second:'2-digit'}); }
function fmtDate(ts) {
  if (!ts) return '';
  try { return new Date(ts).toLocaleDateString(); } catch (e) { return ''; }
}
function fmtDateTime(ts) {
  if (!ts) return '';
  const d = fmtDate(ts), t = fmtTime(ts);
  return d ? (t ? d + ' ' + t : d) : t;
}
function modelClass(m) { const l=(m||'').toLowerCase(); if(l.includes('opus')) return 'opus'; if(l.includes('sonnet')) return 'sonnet'; if(l.includes('haiku')) return 'haiku'; return ''; }
function cacheEff(s) {
  const inputSum = (s.input_tokens||0) + (s.cache_read_tokens||0) + (s.cache_write_tokens||0);
  if (inputSum === 0) return null;
  return (s.cache_read_tokens||0) / inputSum * 100;
}
function effStyle(pct) {
  if (pct == null) return {color:'var(--text2)', emoji:'—', label:'—'};
  if (pct >= 80) return {color:'var(--green)', emoji:'✅', label:pct.toFixed(1)+'%'};
  if (pct >= 50) return {color:'var(--amber)', emoji:'⚠️', label:pct.toFixed(1)+'%'};
  return {color:'var(--red)', emoji:'❌', label:pct.toFixed(1)+'%'};
}

function renderIdleGapPanel(sess) {
  const igs = sess.idle_gap_summary;
  if (!igs) return '';
  if (((igs.mid && igs.mid.count) || 0) === 0 && ((igs.long && igs.long.count) || 0) === 0) return '';

  // session_detail has no locale injection (matches existing convention:
  // 'Duration', 'Messages', 'Tool Calls' etc. are hardcoded English).
  const T = {
    title:     'Idle Gaps',
    short:     '<5 min',
    mid:       '5–60 min',
    long:      '>1 h',
    turns:     'turns',
    overspend: 'extra tokens spent on cache rebuild after pauses',
    pctOf:     'of this session',
    tip:       "Don't leave sessions open during longer breaks.",
  };

  const fmtNum = (n) => (n >= 1000 ? (n / 1000).toFixed(1) + 'k' : String(n));

  const maxCount = Math.max(igs.short.count, igs.mid.count, igs.long.count, 1);
  const bar = (count) => {
    const w = Math.round((count / maxCount) * 24);
    return '█'.repeat(w) + '░'.repeat(24 - w);
  };

  const rows = [
    {label: T.short, b: igs.short},
    {label: T.mid,   b: igs.mid},
    {label: T.long,  b: igs.long},
  ].map(r =>
    '<div class="igp-row">' +
      '<span class="igp-lbl">' + r.label + '</span>' +
      '<span class="igp-bar">' + bar(r.b.count) + '</span>' +
      '<span class="igp-num">' + r.b.count + ' ' + T.turns + ' · ' + fmtNum(r.b.cache_creation_tokens) + ' tok</span>' +
    '</div>'
  ).join('');

  const oversp = igs.estimated_overspend_tokens || 0;
  const overspPct = igs.estimated_overspend_pct_of_session || 0;

  return (
    '<div class="card idle-gap-panel">' +
      '<h3>' + T.title + '</h3>' +
      '<div class="igp-rows">' + rows + '</div>' +
      (oversp > 0 ?
        '<div class="igp-summary">≈ ' + fmtNum(oversp) + ' tok ' + T.overspend +
        ' (≈ ' + overspPct + '% ' + T.pctOf + ')</div>' : '') +
      '<div class="igp-tip">ⓘ ' + T.tip + '</div>' +
    '</div>'
  );
}

document.getElementById('sessionTitle').textContent = sess.project;
document.getElementById('sessionMeta').innerHTML =
  '<span>Session: <code>'+sess.session_id.slice(0,8)+'</code></span>' +
  '<span>'+new Date(sess.start).toLocaleDateString()+' '+new Date(sess.start).toLocaleTimeString()+'</span>' +
  '<span class="model-badge '+modelClass(sess.primary_model)+'">'+escHtml(sess.primary_model)+'</span>' +
  (sess.used_1m_context ? ctx1mBadge('1M context window used — peak '+fmtTokens(sess.peak_context_tokens||0)+(sess.first_1m_at?', since '+fmtTime(sess.first_1m_at):'')) : '');

const toolCount = Object.values(sess.tools||{}).reduce((s,v)=>s+v,0);
const sessEff = cacheEff(sess);
const sessEffSt = effStyle(sessEff);
document.getElementById('statsBar').innerHTML =
  '<div class="stat-card"><div class="label">Duration</div><div class="value">'+sess.duration_min+'m</div></div>' +
  '<div class="stat-card"><div class="label">Messages</div><div class="value" style="color:var(--green)">'+sess.messages+'</div></div>' +
  '<div class="stat-card"><div class="label">Tool Calls</div><div class="value" style="color:var(--cyan)">'+toolCount+'</div></div>' +
  '<div class="stat-card"><div class="label">Tokens</div><div class="value" style="color:var(--purple)">'+fmtTokens(sess.input_tokens+sess.output_tokens)+'</div></div>' +
  '<div class="stat-card"><div class="label">Cache Eff.</div><div class="value" style="color:'+sessEffSt.color+'">'+sessEffSt.emoji+' '+sessEffSt.label+'</div></div>' +
  '<div class="stat-card"><div class="label">Cache Flushes</div><div class="value" title="Turns where cache likely went cold (post-buildup + gap > TTL + creation > 2× session median)" style="color:'+((sess.cache_flush_count||0)>0?'var(--red)':'var(--text2)')+'">'+((sess.cache_flush_count||0))+'</div></div>' +
  '<div class="stat-card"><div class="label">Est. Cost</div><div class="value" style="color:var(--orange)">'+fmtUSD(sess.cost)+'</div></div>' +
  '<div class="stat-card"><div class="label">Compactions</div><div class="value" style="color:'+((sess.compactions||0)>0?'var(--amber)':'var(--text2)')+'">'+((sess.compactions||0))+'</div></div>' +
  '<div class="stat-card"><div class="label">Peak Context</div><div class="value" title="'+(sess.used_1m_context?('1M context window used'+(sess.first_1m_at?' since '+fmtTime(sess.first_1m_at):'')):'Highest prompt context reached (standard 200k window)')+'" style="color:'+(sess.used_1m_context?'var(--accent2, #a855f7)':'var(--text2)')+'">'+fmtTokens(sess.peak_context_tokens||0)+(sess.used_1m_context?' <span class="ctx-1m-badge">1M</span>':'')+'</div></div>';

// Idle-gap panel (Task 2): only renders if session has mid or long gaps
const idleGapEl = document.getElementById('idleGapPanel');
if (idleGapEl) idleGapEl.innerHTML = renderIdleGapPanel(sess);

// Simple markdown rendering
function renderMd(text) {
  if (!text) return '';
  let h = escHtml(text);
  h = h.replace(/```(\w*)\n([\s\S]*?)```/g, function(m,lang,code) { return '<pre><code class="language-'+lang+'">'+code+'</code></pre>'; });
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
  h = h.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  return h;
}

// Chat panel
const chatEl = document.getElementById('chatPanel');
// Slug helper: timestamp -> URL-fragment-safe id, must match the form used
// by the Limits-tab event-link in dashboard.js.
function evtId(ts) { return 'evt-' + String(ts || '').replace(/[^a-zA-Z0-9]/g, '-'); }
// A slash command (e.g. /close) carries no usage of its own; the tokens it
// "used" are the output of the assistant turn(s) it triggered, up to the next
// user/command boundary. Sum those so the command marker can show the cost.
function commandOutputTokens(idx) {
  let out = 0;
  for (let j = idx + 1; j < msgs.length; j++) {
    const r = msgs[j].role;
    if (r === 'user' || r === 'command') break;
    if (r === 'assistant' && msgs[j].tokens) out += msgs[j].tokens.output || 0;
  }
  return out;
}
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
  if (m.role==='hook') {
    chatHtml += '<div class="marker hook event-group" data-ts="'+(m.timestamp||'')+'" id="marker-'+i+'"><span>&#9881;</span> Hook: '+escHtml(m.hook_name)+' <span style="margin-left:auto">'+fmtTime(m.timestamp)+'</span></div>';
  } else if (m.role==='compaction') {
    chatHtml += '<div class="marker compaction event-group" data-ts="'+(m.timestamp||'')+'" id="marker-'+i+'"><span>&#9889;</span> Context Compaction <span style="margin-left:auto">'+fmtTime(m.timestamp)+'</span></div>';
  } else if (m.role==='rate_limit') {
    chatHtml += '<div class="marker rate-limit error-group" data-ts="'+(m.timestamp||'')+'" id="'+evtId(m.timestamp)+'">' +
      '<span>&#9888;</span> Rate-Limit-Event: <strong>'+escHtml(m.content)+'</strong>' +
      '<span style="margin-left:auto">'+fmtTime(m.timestamp)+'</span></div>';
  } else if (m.role==='error') {
    const elabel = (m.source==='backend'?'Backend':(m.tool||'Tool')) + ' &middot; ' + escHtml(m.category||'error');
    chatHtml += '<div class="marker error error-group" data-ts="'+(m.timestamp||'')+'" id="marker-'+i+'"><span>&#9888;</span> Error: <strong>'+elabel+'</strong>'+
      '<span style="margin-left:auto">'+fmtTime(m.timestamp)+'</span>'+
      (m.content?'<div class="marker-detail">'+escHtml(m.content)+'</div>':'')+
      '</div>';
  } else if (m.role==='rejected') {
    chatHtml += '<div class="marker rejected event-group" data-ts="'+(m.timestamp||'')+'" id="marker-'+i+'"><span>&#9995;</span> Rejected: <strong>'+escHtml(m.tool||'tool')+'</strong> <span style="opacity:.7">(you declined)</span><span style="margin-left:auto">'+fmtTime(m.timestamp)+'</span></div>';
  } else if (m.role==='command') {
    const cmdOut = commandOutputTokens(i);
    chatHtml += '<div class="marker command event-group" data-ts="'+(m.timestamp||'')+'" id="marker-'+i+'"><span>&#8984;</span> Command: <strong>'+escHtml(m.content)+'</strong>'+
      (cmdOut > 0 ? '<span class="msg-tokens" style="margin-left:12px">'+fmtTokens(cmdOut)+' out</span>' : '')+
      '<span style="margin-left:auto">'+fmtTime(m.timestamp)+'</span></div>';
  } else if (m.role==='interrupt') {
    chatHtml += '<div class="marker interrupt event-group" data-ts="'+(m.timestamp||'')+'" id="marker-'+i+'"><span>&#9099;</span> Interrupted by user<span style="margin-left:auto">'+fmtTime(m.timestamp)+'</span></div>';
  } else if (m.role==='attachment') {
    chatHtml += '<div class="marker attachment event-group" data-ts="'+(m.timestamp||'')+'" id="marker-'+i+'"><span>&#128206;</span> '+escHtml(m.content)+'<span style="margin-left:auto">'+fmtTime(m.timestamp)+'</span></div>';
  } else if (m.role==='mode') {
    chatHtml += '<div class="marker mode event-group" data-ts="'+(m.timestamp||'')+'" id="marker-'+i+'"><span>&#9881;</span> '+escHtml(m.content)+'<span style="margin-left:auto">'+fmtTime(m.timestamp)+'</span></div>';
  } else if (m.role==='queue') {
    chatHtml += '<div class="marker queue event-group" data-ts="'+(m.timestamp||'')+'" id="marker-'+i+'"><span>&#9203;</span> Queued: '+escHtml(m.content)+'<span style="margin-left:auto">'+fmtTime(m.timestamp)+'</span></div>';
  } else if (m.role==='effort') {
    chatHtml += '<div class="marker effort event-group" data-ts="'+(m.timestamp||'')+'" id="marker-'+i+'"><span>&#129504;</span> Effort: <strong>'+escHtml(m.content)+'</strong><span style="margin-left:auto">'+fmtTime(m.timestamp)+'</span></div>';
  } else {
    // Check for Agent dispatches in tools
    const agentTools = (m.tools || []).filter(t => t.name === 'Agent');
    agentTools.forEach(at => {
      chatHtml += '<div class="marker agent-dispatch agent-toggle" data-ts="'+(m.timestamp||'')+'" id="marker-'+i+'-a">' +
        '<span>&#129302;</span> Agent: <strong>'+escHtml(at.detail || 'unnamed')+'</strong>' +
        '<span class="agent-type-badge">'+escHtml(at.agent_type || 'general-purpose')+'</span>' +
        '<span style="margin-left:auto;font-size:11px;opacity:0.7">'+fmtTime(m.timestamp)+' &#9660; click to expand</span>' +
        (at.agent_prompt ? '<div class="agent-prompt">'+escHtml(at.agent_prompt)+'</div>' : '') +
      '</div>';
    });

    const isLong = (m.content||'').length > 2000;
    const display = isLong ? m.content.slice(0,2000) : m.content;
    const hasAgentDispatch = agentTools.length > 0;
    // Extended thinking. Text only exists for older models (Opus 4.6);
    // 4.7/4.8 return encrypted thinking, so we just flag that the turn
    // reasoned. Text present -> collapsible block; signature-only -> a small
    // indicator badge in the header.
    const thinkingHtml = m.thinking ?
      '<div class="msg-thinking">' +
        '<div class="thinking-toggle" data-idx="'+i+'"><span>&#128173;</span> Thinking ('+(m.thinking.length/1000).toFixed(1)+'K) <span class="thinking-caret">&#9656;</span></div>' +
        '<div class="thinking-body" id="think'+i+'" style="display:none">'+renderMd(m.thinking)+'</div>' +
      '</div>' : '';
    const thoughtBadge = (m.thought && !m.thinking) ?
      '<span class="thought-badge" title="Extended thinking was used on this turn. Claude Code does not store the reasoning text for this model, only an encrypted signature.">&#128173;</span>' : '';
    chatHtml += '<div class="msg '+m.role+(hasAgentDispatch?' has-agent-dispatch':'')+'" data-ts="'+(m.timestamp||'')+'" id="msg-'+i+'">' +
      '<div class="msg-header">' +
        '<div class="msg-role '+m.role+'">'+(m.role==='user'?'U':'A')+'</div>' +
        '<span class="msg-time">'+fmtTime(m.timestamp)+'</span>' +
        (m.model ? '<span class="msg-model"><span class="model-badge '+modelClass(m.model)+'">'+escHtml(m.model)+'</span></span>' : '') +
        thoughtBadge +
        (m.tokens ? '<span class="msg-tokens">'+fmtTokens(m.tokens.input)+'in / '+fmtTokens(m.tokens.output)+'out</span>' : '') +
        (m.tokens && turnContext(m.tokens) > CONTEXT_1M_THRESHOLD ? ctx1mBadge('Prompt context '+fmtTokens(turnContext(m.tokens))+' — exceeds the 200k standard window (1M enabled)') : '') +
      '</div>' +
      thinkingHtml +
      '<div class="msg-content" id="mc'+i+'">'+renderMd(display)+'</div>' +
      (isLong ? '<div class="msg-expand" data-idx="'+i+'">Show full message ('+(m.content.length/1000).toFixed(1)+'K chars)</div>' : '') +
      (m.tools && m.tools.length>0 ? '<div class="msg-tools">'+m.tools.map(t =>
        '<span class="tool-badge"'+(t.name==='Agent'?' style="background:rgba(99,102,241,0.15);color:var(--accent2);border-color:var(--accent)"':'')+'>'
        +escHtml(t.name)+(t.detail ? ' '+escHtml(t.detail) : '')+'</span>'
      ).join('')+'</div>' : '') +
    '</div>';
  }
});
chatEl.innerHTML = chatHtml;

// Expand handlers
document.querySelectorAll('.msg-expand').forEach(el => {
  el.addEventListener('click', function() {
    const idx = parseInt(this.getAttribute('data-idx'));
    document.getElementById('mc'+idx).innerHTML = renderMd(msgs[idx].content);
    this.remove();
  });
});

// Agent dispatch toggle
document.querySelectorAll('.agent-toggle').forEach(el => {
  el.addEventListener('click', function() { this.classList.toggle('expanded'); });
});

// Thinking block toggle
document.querySelectorAll('.thinking-toggle').forEach(el => {
  el.addEventListener('click', function() {
    const body = document.getElementById('think'+this.getAttribute('data-idx'));
    if (!body) return;
    const open = body.style.display === 'none';
    body.style.display = open ? '' : 'none';
    this.classList.toggle('expanded', open);
  });
});

// Syntax highlighting
document.querySelectorAll('pre code').forEach(el => hljs.highlightElement(el));

// If the URL points at a specific event marker (#evt-<slug>), scroll it
// into view and briefly flash it. The chat-panel is its own scroll
// container (overflow-y: auto), so we need to wait for hljs syntax
// highlighting and chart canvases to settle — otherwise the target's
// offsetTop is stale by the time scrollIntoView fires and the panel
// ends up scrolled past the marker. Smooth-scroll amplifies the drift,
// so use instant. Re-scroll once more 250ms after load to absorb late
// reflows from canvas/font/chart initialization.
if (location.hash && location.hash.startsWith('#evt-')) {
  const scrollToMarker = () => {
    const target = document.getElementById(location.hash.slice(1));
    if (target) target.scrollIntoView({ behavior: 'instant', block: 'center' });
    return target;
  };
  const flash = (el) => {
    if (!el) return;
    el.classList.add('marker-flash');
    setTimeout(() => el.classList.remove('marker-flash'), 1800);
  };
  window.addEventListener('load', () => {
    const t = scrollToMarker();
    setTimeout(() => { scrollToMarker(); flash(t); }, 250);
  });
}

// Role filter
// Chat filters are multi-select: each category button toggles on/off
// independently and the active categories combine as a union (an element
// shows if it matches ANY active category). "All" is the reset state —
// clicking it clears the categories; deselecting the last active category
// falls back to "All".
const FILTER_MATCHERS = {
  user: el => el.classList.contains('user'),
  assistant: el => el.classList.contains('assistant'),
  // agent-dispatch markers + messages that dispatched a subagent
  'agent-dispatch': el => el.classList.contains('agent-dispatch') || el.classList.contains('has-agent-dispatch'),
  // tool/backend errors + rate-limit markers
  error: el => el.classList.contains('error-group'),
  // compaction, command, interrupt, rejected, attachment, mode, queue, hook, effort
  event: el => el.classList.contains('event-group'),
};
const activeFilters = new Set(['all']);
function applyChatFilters() {
  const showAll = activeFilters.has('all');
  const keys = [...activeFilters].filter(k => k !== 'all');
  document.querySelectorAll('.filter-btn').forEach(b => {
    b.classList.toggle('active', activeFilters.has(b.getAttribute('data-filter')));
  });
  document.querySelectorAll('#chatPanel > .msg, #chatPanel > .marker').forEach(el => {
    const show = showAll || keys.some(k => FILTER_MATCHERS[k] && FILTER_MATCHERS[k](el));
    el.style.display = show ? '' : 'none';
  });
}
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', function() {
    const key = this.getAttribute('data-filter');
    if (key === 'all') {
      activeFilters.clear();
      activeFilters.add('all');
    } else {
      activeFilters.delete('all');           // leaving the "all" reset state
      if (activeFilters.has(key)) activeFilters.delete(key);
      else activeFilters.add(key);
      if (activeFilters.size === 0) activeFilters.add('all'); // last one off → reset
    }
    applyChatFilters();
  });
});

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
  if (/[:#"\n]/.test(str)) return '"' + str.replace(/"/g, '\\"') + '"';
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
    try { startIso = new Date(session.start).toISOString().replace(/\.\d{3}Z$/, 'Z'); } catch(e) { startIso = String(session.start); }
  }
  lines.push('start: ' + yamlEscape(startIso));
  lines.push('duration_min: ' + (session.duration_min != null ? session.duration_min : 0));
  lines.push('model: ' + yamlEscape(session.primary_model));
  lines.push('messages: ' + (session.messages != null ? session.messages : 0));
  lines.push('cost_usd: ' + (typeof session.cost === 'number' ? session.cost.toFixed(4) : '0.0000'));
  if (session.source) lines.push('source: ' + yamlEscape(session.source));
  lines.push('---');
  lines.push('');

  let title = ((session.first_prompt || '').split('\n')[0] || '').trim();
  if (title.length > 80) title = title.slice(0, 80) + '\u2026';
  if (!title) title = 'Session ' + ((session.session_id || '').slice(0, 8));
  lines.push('# ' + title);
  lines.push('');

  messages.forEach(m => {
    if (m.role !== 'user' && m.role !== 'assistant') return;
    if (!(m.content || '').trim()) return;
    let ts = '';
    if (m.timestamp) {
      try { ts = fmtDateTime(m.timestamp); } catch(e) {}
    }
    if (m.role === 'user') {
      lines.push('## User' + (ts ? ' \u2014 ' + ts : ''));
    } else {
      const model = m.model ? ' (' + m.model + ')' : '';
      lines.push('## Assistant' + model + (ts ? ' \u2014 ' + ts : ''));
    }
    lines.push('');
    lines.push(m.content || '');
    lines.push('');
  });
  return lines.join('\n');
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

// Copy to clipboard
document.getElementById('copyBtn').addEventListener('click', function() {
  const btn = this;
  const lines = [];
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
  navigator.clipboard.writeText(lines.join('\n')).then(() => {
    btn.innerHTML = '&#10003; Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.innerHTML = '&#128203; Copy'; btn.classList.remove('copied'); }, 2000);
  });
});

// Download filtered chat as Markdown
document.getElementById('downloadBtn').addEventListener('click', function() {
  const btn = this;
  const visible = [];
  document.querySelectorAll('#chatPanel > .msg').forEach(el => {
    if (el.style.display === 'none') return;
    const m = el.id.match(/^msg-(\d+)$/);
    if (m) visible.push(parseInt(m[1], 10));
  });
  const filtered = visible.map(i => msgs[i]).filter(m => m && (m.role === 'user' || m.role === 'assistant'));
  const md = buildMarkdown(sess, filtered);
  triggerDownload(mdFilename(sess), md);
  btn.innerHTML = '&#10003; Downloaded!';
  btn.classList.add('copied');
  setTimeout(() => { btn.innerHTML = '&#11015; Download'; btn.classList.remove('copied'); }, 2000);
});

// Sidebar
const sideEl = document.getElementById('sidebar');
let sideHtml = '';
sideHtml += '<div class="sidebar-card"><h4>Token Breakdown</h4>' +
  '<div class="sidebar-row"><span class="label">Input Tokens</span><span class="val">'+fmtTokens(sess.input_tokens)+'</span></div>' +
  '<div class="sidebar-row"><span class="label">Output Tokens</span><span class="val">'+fmtTokens(sess.output_tokens)+'</span></div>' +
  '<div class="sidebar-row"><span class="label">Cache Read</span><span class="val">'+fmtTokens(sess.cache_read_tokens)+'</span></div>' +
  '<div class="sidebar-row"><span class="label">Cache Write</span><span class="val">'+fmtTokens(sess.cache_write_tokens)+'</span></div>' +
  '</div>';
const toolTokens = sess.tool_tokens || {};
const tools = Object.entries(sess.tools||{}).sort((a,b)=>b[1]-a[1]);
const hasTokenAttribution = Object.keys(toolTokens).length > 0 || (sess.reasoning_output_tokens||0) > 0;
if (hasTokenAttribution) {
  sideHtml += '<div class="sidebar-card"><h4>Output-Token Share by Tool</h4>' +
    '<p style="font-size:11px;opacity:0.6;margin:0 0 8px 0">"Reasoning" = Turns ohne Tool-Call.</p>' +
    '<canvas id="chartSessionTokens" style="max-height:220px"></canvas>' +
    '</div>';
}

// Output by activity (stacked bar) — char-heuristic attribution of output_tokens
// across visible text / narration / thinking / file writes / bash / other tools.
const wc = sess.write_categories || {};
const WC_DEF = [
  ['screen_text',           'Final Answers',     '#10b981'],
  ['screen_text_narration', 'Pre-Tool Narration','#06b6d4'],
  ['thinking',              'Thinking',          '#94a3b8'],
  ['file_writes',           'File Writes',       '#6366f1'],
  ['bash_commands',         'Bash Commands',     '#f59e0b'],
  ['tool_inputs',           'Other Tool Inputs', '#a855f7'],
];
const wcTotal = WC_DEF.reduce((s, [k]) => s + (wc[k] || 0), 0);
if (wcTotal > 0) {
  const segs = WC_DEF
    .filter(([k]) => (wc[k] || 0) > 0)
    .map(([k, label, color]) => {
      const v = wc[k];
      const pct = (v / wcTotal) * 100;
      return {k, label, color, v, pct};
    });
  sideHtml += '<div class="sidebar-card"><h4>Output by Activity</h4>' +
    '<p style="font-size:11px;opacity:0.6;margin:0 0 8px 0">Heuristic split of output tokens by what the model emitted (text vs tool inputs vs commands).</p>' +
    '<div style="display:flex;height:14px;border-radius:4px;overflow:hidden;background:var(--bg-subtle, rgba(255,255,255,0.04));margin-bottom:8px">' +
      segs.map(s => '<div title="'+escHtml(s.label)+': '+fmtTokens(s.v)+' ('+s.pct.toFixed(1)+'%)" style="width:'+s.pct.toFixed(3)+'%;background:'+s.color+'"></div>').join('') +
    '</div>' +
    segs.map(s =>
      '<div class="sidebar-row">' +
        '<span class="label"><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:'+s.color+';margin-right:6px;vertical-align:middle"></span>'+escHtml(s.label)+'</span>' +
        '<span class="val">'+fmtTokens(s.v)+' <span style="opacity:0.55;font-size:11px">('+s.pct.toFixed(1)+'%)</span></span>' +
      '</div>'
    ).join('') +
  '</div>';
}
if (tools.length>0 || (sess.reasoning_output_tokens||0) > 0) {
  const totalOut = Object.values(toolTokens).reduce((s,v)=>s+(v.output_tokens||0),0)
                    + (sess.reasoning_output_tokens||0);
  sideHtml += '<div class="sidebar-card"><h4>Tools Used</h4>' +
    tools.slice(0,15).map(([n,c]) => {
      const tk = toolTokens[n] || {output_tokens: 0};
      const pct = totalOut > 0 ? ((tk.output_tokens / totalOut) * 100).toFixed(0) : '0';
      return '<div class="sidebar-row"><span class="label">'+escHtml(n)+'</span>' +
             '<span class="val">'+c+'x <span style="opacity:0.55;font-size:11px">('+fmtTokens(tk.output_tokens||0)+' &middot; '+pct+'%)</span></span></div>';
    }).join('') +
    (sess.reasoning_output_tokens > 0
      ? '<div class="sidebar-row" style="border-top:1px solid var(--border);margin-top:4px;padding-top:4px"><span class="label" style="opacity:0.7">Reasoning (no tools)</span><span class="val">' +
        fmtTokens(sess.reasoning_output_tokens) + ' &middot; ' +
        (totalOut > 0 ? ((sess.reasoning_output_tokens / totalOut) * 100).toFixed(0) : '0') + '%</span></div>'
      : '') +
    '</div>';
}
const skills = Object.entries(sess.skills||{}).sort((a,b)=>b[1]-a[1]);
if (skills.length>0) {
  sideHtml += '<div class="sidebar-card"><h4>Skills Used</h4>' +
    skills.map(([n,c]) => '<span class="sidebar-tag" style="color:var(--purple)">'+escHtml(n)+' '+c+'x</span>').join('') +
    '</div>';
}
const hooks = Object.entries(sess.hooks||{}).sort((a,b)=>b[1]-a[1]);
if (hooks.length>0) {
  sideHtml += '<div class="sidebar-card"><h4>Hooks Fired</h4>' +
    hooks.map(([n,c]) => '<div class="sidebar-row"><span class="label" style="color:var(--amber)">'+escHtml(n)+'</span><span class="val">'+c+'x</span></div>').join('') +
    '</div>';
}
if (sess.compaction_events && sess.compaction_events.length>0) {
  sideHtml += '<div class="sidebar-card" style="border-color:rgba(245,158,11,0.3)"><h4 style="color:var(--amber)">Compaction Timeline</h4>' +
    '<div class="compaction-timeline">' +
    sess.compaction_events.map(e => '<div class="compaction-event">'+fmtTime(e.timestamp)+'</div>').join('') +
    '</div></div>';
}
const models = Object.entries(sess.model_breakdown||{});
if (models.length>0) {
  sideHtml += '<div class="sidebar-card"><h4>Model Breakdown</h4>' +
    models.map(([m,d]) => '<div class="sidebar-row"><span class="label"><span class="model-badge '+modelClass(m)+'">'+escHtml(m)+'</span></span><span class="val">'+fmtUSD(d.cost)+' ('+d.calls+' calls)</span></div>').join('') +
    '</div>';
}
sideHtml += '<div class="sidebar-card"><h4>Metadata</h4>' +
  '<div class="sidebar-row"><span class="label">Session ID</span><span class="val" style="font-size:11px;font-family:var(--vc-font-mono);word-break:break-all;text-align:right">'+sess.session_id+'</span></div>' +
  '<div class="sidebar-row"><span class="label">File Size</span><span class="val">'+sess.file_size_mb+' MB</span></div>' +
  '</div>';
sideEl.innerHTML = sideHtml;

// Output-Token Share doughnut (per-session)
if (hasTokenAttribution && typeof Chart !== 'undefined') {
  const sortedTools = Object.entries(toolTokens)
    .map(([name, v]) => ({name, output_tokens: v.output_tokens||0}))
    .filter(t => t.output_tokens > 0)
    .sort((a,b) => b.output_tokens - a.output_tokens)
    .slice(0, 12);
  const labels = sortedTools.map(t => t.name);
  const values = sortedTools.map(t => t.output_tokens);
  const reasoningOut = sess.reasoning_output_tokens || 0;
  if (reasoningOut > 0) { labels.push('Reasoning'); values.push(reasoningOut); }
  const palette = ['#10b981','#06b6d4','#6366f1','#f59e0b','#ef4444','#a855f7','#ec4899','#84cc16','#14b8a6','#f97316','#3b82f6','#eab308','#94a3b8'];
  const canvas = document.getElementById('chartSessionTokens');
  if (canvas && values.length > 0) {
    new Chart(canvas, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: labels.map((_, i) => palette[i % palette.length]),
          borderWidth: 0,
        }],
      },
      options: {
        animation: false,
        plugins: {
          legend: {position: 'right', labels: {font: {size: 11}, boxWidth: 10}},
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const total = ctx.dataset.data.reduce((s,v)=>s+v,0);
                const pct = total > 0 ? ((ctx.raw / total) * 100).toFixed(1) : '0';
                return ctx.label + ': ' + fmtTokens(ctx.raw) + ' (' + pct + '%)';
              },
            },
          },
        },
      },
    });
  }
}

class SessionFlow {
  constructor(canvas, flowData, chatContainer) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.flow = flowData;
    this.chat = chatContainer;
    this.dpr = window.devicePixelRatio || 1;
    this.W = 0; this.H = 0;
    // Camera
    this.cam = {x:0, y:0, scale:1, tx:0, ty:0, ts:1, vx:0, vy:0};
    // Nodes and edges (populated later)
    this.nodes = []; this.edges = []; this.toolNodes = [];
    // Particles
    this.bgParticles = [];
    this.edgeParticles = [];
    // Effects queue
    this.effects = [];
    this.reverseBursts = [];
    // Interaction state
    this.hovered = null; this.selected = null;
    this.dragging = null; this.panning = false;
    this.panStart = {x:0,y:0}; this.panCamStart = {x:0,y:0};
    this.userOverride = false;
    // Auto-play state
    this.playing = false; this.playSpeed = 1;
    this.playTime = 0; this.playIndex = 0;
    this.playDone = false;
    this.showAll = false;
    this.convEdgeOpacity = 0;
    this.responseEdgeOpacity = 0;
    this._userMsgCount = 0;
    this._assistantMsgCount = 0;
    // Sprite cache
    this.sprites = {};
    // Hex grid params
    this.hexSize = 30;
    // Init
    this._resize();
    this._initBgParticles(60);
    this._preRenderSprites();
    this._initGraph();
    if (!this.flow.events || this.flow.events.length === 0) {
      this.allNodes.forEach(n => { n.opacity = 1; n.targetOpacity = 1; });
      this.playDone = true;
    }
    if (this.nodes.length > 0) {
      this.nodes[0].targetOpacity = 1;
      this._lastActiveNode = this.nodes[0];
      this.effects.push({type:"spawn", node:this.nodes[0], t:0, dur:1.0});
    }
    // Show user node immediately alongside main agent
    var userNode = this.allNodes.find(function(n) { return n.id === 'user'; });
    if (userNode) {
      userNode.targetOpacity = 1;
      this.effects.push({type:'spawn', node:userNode, t:0, dur:1.0});
    }
    this._fitAll();
    this._bindEvents();
    this._raf();
  }

  _resize() {
    var r = this.canvas.parentElement.getBoundingClientRect();
    if (Math.abs(r.width - this.W) < 1 && Math.abs(r.height - this.H) < 1) return;
    this.W = r.width; this.H = r.height;
    this.canvas.width = this.W * this.dpr;
    this.canvas.height = this.H * this.dpr;
    this.ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
  }

  _initBgParticles(n) {
    this.bgParticles = [];
    for (let i = 0; i < n; i++) {
      this.bgParticles.push({
        x: Math.random() * 2000 - 1000,
        y: Math.random() * 2000 - 1000,
        r: Math.random() * 1.5 + 0.3,
        a: Math.random() * 0.3 + 0.05,
        vx: (Math.random() - 0.5) * 0.15,
        vy: (Math.random() - 0.5) * 0.15
      });
    }
  }

  _preRenderSprites() {
    const sz = 32;
    const colors = [
      ["glow", "0,212,255"],
      ["glowOrange", "255,136,0"],
      ["glowMagenta", "255,0,170"],
      ["glowGreen", "0,255,136"]
    ];
    for (const [name, rgb] of colors) {
      const c = document.createElement("canvas");
      c.width = sz; c.height = sz;
      const g = c.getContext("2d");
      const gr = g.createRadialGradient(sz/2,sz/2,0,sz/2,sz/2,sz/2);
      gr.addColorStop(0, "rgba(255,255,255,0.9)");
      gr.addColorStop(0.3, "rgba(" + rgb + ",0.4)");
      gr.addColorStop(1, "rgba(" + rgb + ",0)");
      g.fillStyle = gr; g.fillRect(0,0,sz,sz);
      this.sprites[name] = c;
    }
  }

  worldToScreen(wx, wy) {
    return {
      x: (wx - this.cam.x) * this.cam.scale + this.W / 2,
      y: (wy - this.cam.y) * this.cam.scale + this.H / 2
    };
  }
  screenToWorld(sx, sy) {
    return {
      x: (sx - this.W / 2) / this.cam.scale + this.cam.x,
      y: (sy - this.H / 2) / this.cam.scale + this.cam.y
    };
  }

  _hexPath(ctx, cx, cy, r) {
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 3 * i - Math.PI / 6;
      const px = cx + r * Math.cos(a), py = cy + r * Math.sin(a);
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    }
    ctx.closePath();
  }

  _diamondPath(ctx, cx, cy, r) {
    ctx.beginPath();
    ctx.moveTo(cx, cy - r);
    ctx.lineTo(cx + r * 0.7, cy);
    ctx.lineTo(cx, cy + r);
    ctx.lineTo(cx - r * 0.7, cy);
    ctx.closePath();
  }

  _drawHexGrid(ctx) {
    const s = this.hexSize;
    const w = s * Math.sqrt(3), h = s * 1.5;
    const tl = this.screenToWorld(0, 0);
    const br = this.screenToWorld(this.W, this.H);
    const startCol = Math.floor(tl.x / w) - 1;
    const endCol = Math.ceil(br.x / w) + 1;
    const startRow = Math.floor(tl.y / h) - 1;
    const endRow = Math.ceil(br.y / h) + 1;

    ctx.strokeStyle = (this._themeColors && this._themeColors.gridLine) || "rgba(30,30,60,0.3)";
    ctx.lineWidth = 0.5;
    for (let row = startRow; row <= endRow; row++) {
      for (let col = startCol; col <= endCol; col++) {
        const ox = row % 2 === 0 ? 0 : w / 2;
        const cx = col * w + ox;
        const cy = row * h;
        const sc = this.worldToScreen(cx, cy);
        const sr = s * this.cam.scale;
        if (sr < 3) continue;
        this._hexPath(ctx, sc.x, sc.y, sr);
        ctx.stroke();
      }
    }
  }

  _drawBgParticles(ctx) {
    for (const p of this.bgParticles) {
      if (this.playing && !this.playDone) {
        p.x += p.vx; p.y += p.vy;
      }
      const sc = this.worldToScreen(p.x, p.y);
      ctx.globalAlpha = p.a;
      ctx.fillStyle = "#4444aa";
      ctx.beginPath();
      ctx.arc(sc.x, sc.y, p.r * this.cam.scale, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  _drawBackground(ctx) {
    const styles = getComputedStyle(this.canvas);
    const cssBg = styles.getPropertyValue('--vc-flow-bg').trim();
    this._themeColors = {
      nodeIcon: styles.getPropertyValue('--vc-node-icon').trim() || '#ffffff',
      gridLine: styles.getPropertyValue('--vc-grid-line').trim() || 'rgba(30,30,60,0.3)',
    };
    ctx.fillStyle = cssBg || "#0a0a0f";
    ctx.fillRect(0, 0, this.W, this.H);
    this._drawHexGrid(ctx);
    this._drawBgParticles(ctx);
  }

  _initGraph() {
    const agents = this.flow.agents || [];
    const flowEdges = this.flow.edges || [];
    this.nodes = [];
    this.edges = [];
    this.toolNodes = [];
    const nodeMap = {};

    agents.forEach((a, i) => {
      var isMain = a.type === 'main';
      var isUser = a.type === 'user';
      const node = {
        id: a.id, name: a.name, type: isUser ? 'user' : (isMain ? 'main' : 'subagent'),
        parentId: a.parent_id, data: a,
        x: isUser ? -250 : (isMain ? 0 : 150 + (Math.random() - 0.5) * 100),
        y: isUser ? 0 : (isMain ? 0 : (Math.random() - 0.5) * 200),
        vx: 0, vy: 0,
        fx: isUser ? -250 : null,
        fy: isUser ? 0 : null,
        r: isUser ? 40 : (isMain ? 50 : 35),
        color: isUser ? '#00ff88' : (isMain ? '#00d4ff' : '#ff00aa'),
        opacity: 0, targetOpacity: 0,
        lastActiveTime: 0,
        scanPhase: Math.random() * Math.PI * 2,
        glowPulse: Math.random() * Math.PI * 2
      };
      this.nodes.push(node);
      nodeMap[a.id] = node;
    });

    agents.forEach(a => {
      const parent = nodeMap[a.id];
      if (!parent) return;
      const tools = a.tools_summary || {};
      Object.entries(tools).forEach(([name, count]) => {
        if (name === "Agent") return;
        const tn = {
          id: a.id + "-tool-" + name, name: name, type: "tool",
          parentId: a.id, count: count, displayCount: 0,
          x: parent.x + 80 + Math.random() * 80,
          y: parent.y + (Math.random() - 0.5) * 100,
          vx: 0, vy: 0, fx: null, fy: null,
          r: 20, color: "#ff8800",
          opacity: 0, targetOpacity: 0,
          lastActiveTime: 0,
          glowPulse: Math.random() * Math.PI * 2
        };
        this.toolNodes.push(tn);
        nodeMap[tn.id] = tn;
        this.edges.push({from: parent, to: tn, type: "tool", particles: []});
      });
    });

    flowEdges.forEach(e => {
      const from = nodeMap[e.from], to = nodeMap[e.to];
      if (from && to) {
        this.edges.push({from, to, type: e.type || "dispatch", particles: []});
      }
    });

    this.allNodes = [...this.nodes, ...this.toolNodes];
    var self = this;
    this.nodeMap = {};
    this.allNodes.forEach(function(n) { self.nodeMap[n.id] = n; });
  }

  _stepSimulation() {
    const nodes = this.allNodes.filter(n => n.opacity > 0.01);
    if (nodes.length === 0) return;
    const CHARGE = -800, LINK_DIST = 250, TOOL_DIST = 120;
    const CENTER = 0.03, DECAY = 0.4, COLLISION = 20;

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        let dx = b.x - a.x, dy = b.y - a.y;
        let d2 = dx * dx + dy * dy;
        if (d2 < 1) d2 = 1;
        const f = CHARGE / d2;
        const fx = dx / Math.sqrt(d2) * f, fy = dy / Math.sqrt(d2) * f;
        a.vx -= fx; a.vy -= fy;
        b.vx += fx; b.vy += fy;
      }
    }

    for (const e of this.edges) {
      if (e.from.opacity < 0.01 || e.to.opacity < 0.01) continue;
      const dx = e.to.x - e.from.x, dy = e.to.y - e.from.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const target = e.type === "tool" ? TOOL_DIST : LINK_DIST;
      const f = (d - target) * 0.05;
      const fx = dx / d * f, fy = dy / d * f;
      e.from.vx += fx; e.from.vy += fy;
      e.to.vx -= fx; e.to.vy -= fy;
    }

    for (const n of nodes) {
      n.vx -= n.x * CENTER;
      n.vy -= n.y * CENTER;
    }

    // Push tools and sub-agents to the right of main agent
    for (var ni = 0; ni < nodes.length; ni++) {
      var node = nodes[ni];
      if (node.type === 'user' || node.type === 'main') continue;
      // Gentle rightward force
      node.vx += 0.3;
      // Also push away from user node (left side)
      var userNode = this.nodeMap ? this.nodeMap['user'] : null;
      if (userNode) {
        var udx = node.x - userNode.x;
        if (udx < 150) {
          node.vx += (150 - udx) * 0.01;
        }
      }
    }

    let totalV = 0;
    for (const n of nodes) {
      if (n.fx !== null) { n.x = n.fx; n.y = n.fy; n.vx = 0; n.vy = 0; continue; }
      n.vx *= DECAY; n.vy *= DECAY;
      n.x += n.vx; n.y += n.vy;
      totalV += Math.abs(n.vx) + Math.abs(n.vy);
    }

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 1;
        const minD = a.r + b.r + COLLISION;
        if (d < minD) {
          const push = (minD - d) / 2;
          const px = dx / d * push, py = dy / d * push;
          a.x -= px; a.y -= py;
          b.x += px; b.y += py;
        }
      }
    }

    this._simSettled = totalV < 0.5;
  }

  _drawNodes(ctx) {
    const t = performance.now() / 1000;

    for (const n of this.toolNodes) {
      if (n.opacity < 0.05) continue;
      const s = this.worldToScreen(n.x, n.y);
      const r = n.r * this.cam.scale;
      ctx.globalAlpha = n.opacity;

      ctx.save();
      ctx.shadowColor = n.color;
      ctx.shadowBlur = 15 * this.cam.scale;
      this._diamondPath(ctx, s.x, s.y, r);
      ctx.fillStyle = "rgba(255,136,0,0.15)";
      ctx.fill();
      ctx.restore();

      this._diamondPath(ctx, s.x, s.y, r);
      ctx.strokeStyle = n.color;
      ctx.lineWidth = 1.5;
      ctx.stroke();

      if (r > 8) {
        ctx.fillStyle = "#fff";
        ctx.font = Math.max(9, r * 0.5) + "px monospace";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        var showCount = this.playDone || this.showAll ? n.count : (n.displayCount || 0);
        const label = showCount > 1 ? n.name + " x" + showCount : n.name;
        ctx.fillText(label, s.x, s.y + r + 12);
      }
    }

    for (const n of this.nodes) {
      if (n.opacity < 0.05) continue;
      const s = this.worldToScreen(n.x, n.y);
      const r = n.r * this.cam.scale;
      ctx.globalAlpha = n.opacity;

      // Draw shape based on type
      if (n.type === 'user') {
        // Outer glow
        ctx.save();
        ctx.shadowColor = n.color;
        ctx.shadowBlur = 25 * this.cam.scale;
        ctx.beginPath();
        ctx.arc(s.x, s.y, r * 1.05, 0, Math.PI * 2);
        ctx.fillStyle = n.color + '10';
        ctx.fill(); ctx.fill();
        ctx.restore();
        // Circle fill (low-alpha node-color tint, like tool calls)
        ctx.beginPath();
        ctx.arc(s.x, s.y, r, 0, Math.PI * 2);
        ctx.fillStyle = n.color + '26';
        ctx.fill();
        // Circle border (full saturation = darker line)
        ctx.beginPath();
        ctx.arc(s.x, s.y, r, 0, Math.PI * 2);
        ctx.strokeStyle = n.color;
        ctx.lineWidth = 1.5;
        ctx.stroke();
        // Pulsing ring
        var pulse = 0.6 + Math.sin(t * 1.5 + n.glowPulse) * 0.4;
        ctx.beginPath();
        ctx.arc(s.x, s.y, r * 0.85, 0, Math.PI * 2);
        var pulseHex = Math.round(pulse * 40).toString(16).padStart(2,'0');
        ctx.strokeStyle = n.color + pulseHex;
        ctx.lineWidth = 1;
        ctx.stroke();
        // User icon
        ctx.fillStyle = (this._themeColors && this._themeColors.nodeIcon) || '#fff';
        ctx.font = 'bold ' + Math.max(16, r * 0.5) + 'px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('☺', s.x, s.y);
        // Label
        ctx.font = Math.max(9, r * 0.25) + 'px monospace';
        ctx.fillStyle = n.color;
        ctx.fillText('User', s.x, s.y + r + 14);
        // Selection highlight
        if (this.selected === n || this.hovered === n) {
          ctx.beginPath();
          ctx.arc(s.x, s.y, r + 4, 0, Math.PI * 2);
          ctx.strokeStyle = '#ffffff60';
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      } else {
        ctx.save();
        ctx.shadowColor = n.color;
        ctx.shadowBlur = 25 * this.cam.scale;
        this._hexPath(ctx, s.x, s.y, r * 1.05);
        ctx.fillStyle = n.color + "10";
        ctx.fill(); ctx.fill();
        ctx.restore();

        this._hexPath(ctx, s.x, s.y, r);
        ctx.fillStyle = n.color + '26';
        ctx.fill();

        ctx.save();
        this._hexPath(ctx, s.x, s.y, r);
        ctx.clip();
        const scanY = s.y - r + ((t * 40 + n.scanPhase * 50) % (r * 2));
        const scanGrad = ctx.createLinearGradient(s.x, scanY - 20, s.x, scanY + 20);
        scanGrad.addColorStop(0, "transparent");
        scanGrad.addColorStop(0.5, n.color + "15");
        scanGrad.addColorStop(1, "transparent");
        ctx.fillStyle = scanGrad;
        ctx.fillRect(s.x - r, s.y - r, r * 2, r * 2);
        ctx.restore();

        this._hexPath(ctx, s.x, s.y, r);
        ctx.strokeStyle = n.color;
        ctx.lineWidth = 1.5;
        ctx.stroke();

        const pulse = 0.6 + Math.sin(t * 1.5 + n.glowPulse) * 0.4;
        this._hexPath(ctx, s.x, s.y, r * 0.85);
        const pulseHex = Math.round(pulse * 40).toString(16).padStart(2,"0");
        ctx.strokeStyle = n.color + pulseHex;
        ctx.lineWidth = 1;
        ctx.stroke();

        if (r > 15) {
          ctx.fillStyle = (this._themeColors && this._themeColors.nodeIcon) || "#fff";
          ctx.font = "bold " + Math.max(10, r * 0.28) + "px monospace";
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          const icon = n.type === "main" ? "✦" : n.data.type.charAt(0).toUpperCase();
          ctx.fillText(icon, s.x, s.y - 2);
          ctx.font = Math.max(9, r * 0.22) + "px monospace";
          ctx.fillStyle = n.color;
          // Two-line name label
          var fullName = n.name || '';
          if (fullName.length <= 20) {
            ctx.fillText(fullName, s.x, s.y + r + 14);
          } else {
            // Split into two lines at a word boundary near the middle
            var mid = Math.floor(fullName.length / 2);
            var spaceAfter = fullName.indexOf(' ', mid);
            var spaceBefore = fullName.lastIndexOf(' ', mid);
            var splitAt;
            if (spaceAfter !== -1 && spaceAfter < mid + 10) {
              splitAt = spaceAfter;
            } else if (spaceBefore > 0) {
              splitAt = spaceBefore;
            } else {
              splitAt = 20; // No good space found, just cut
            }
            var line1 = fullName.slice(0, splitAt);
            var line2 = fullName.slice(splitAt).trim();
            if (line2.length > 22) line2 = line2.slice(0, 20) + '..';
            ctx.fillText(line1, s.x, s.y + r + 12);
            ctx.fillText(line2, s.x, s.y + r + 24);
          }
        }

        if (this.selected === n || this.hovered === n) {
          this._hexPath(ctx, s.x, s.y, r + 4);
          ctx.strokeStyle = "#ffffff60";
          ctx.lineWidth = 2;
          ctx.stroke();
        }
      }
    }
    ctx.globalAlpha = 1;
  }

  _cubicBezier(t, p0, p1, p2, p3) {
    const mt = 1 - t;
    return {
      x: mt*mt*mt*p0.x + 3*mt*mt*t*p1.x + 3*mt*t*t*p2.x + t*t*t*p3.x,
      y: mt*mt*mt*p0.y + 3*mt*mt*t*p1.y + 3*mt*t*t*p2.y + t*t*t*p3.y
    };
  }

  _initEdgeParticles(edge) {
    const n = edge.type === "dispatch" ? 6 : 3;
    edge.particles = [];
    for (let i = 0; i < n; i++) {
      edge.particles.push({
        t: i / n,
        speed: 0.003 + Math.random() * 0.002,
        wobble: Math.random() * Math.PI * 2,
        wobbleAmp: 2 + Math.random() * 3
      });
    }
  }

  _drawEdges(ctx) {
    for (const e of this.edges) {
      const fa = e.from, ta = e.to;
      if (fa.opacity < 0.05 || ta.opacity < 0.05) continue;

      const sf = this.worldToScreen(fa.x, fa.y);
      const st = this.worldToScreen(ta.x, ta.y);
      const alpha = Math.min(fa.opacity, ta.opacity);

      const dx = st.x - sf.x, dy = st.y - sf.y;
      const d = Math.sqrt(dx*dx + dy*dy) || 1;
      const nx = -dy/d, ny = dx/d;
      const off = d * 0.15;
      const cp1 = {x: sf.x + dx*0.3 + nx*off, y: sf.y + dy*0.3 + ny*off};
      const cp2 = {x: sf.x + dx*0.7 + nx*off, y: sf.y + dy*0.7 + ny*off};

      var edgeColor = e.type === "dispatch" ? "#00d4ff" : (e.type === "conversation" ? "#00ff88" : "#ff8800");
      var edgeAlpha = e.type === 'conversation' ? alpha * this.convEdgeOpacity : alpha;
      ctx.globalAlpha = edgeAlpha * 0.3;
      ctx.beginPath();
      ctx.moveTo(sf.x, sf.y);
      ctx.bezierCurveTo(cp1.x, cp1.y, cp2.x, cp2.y, st.x, st.y);
      ctx.strokeStyle = edgeColor;
      ctx.lineWidth = e.type === "dispatch" ? 2 : 1.5;
      ctx.stroke();

      ctx.save();
      ctx.globalCompositeOperation = "lighter";
      ctx.globalAlpha = edgeAlpha * 0.15;
      ctx.beginPath();
      ctx.moveTo(sf.x, sf.y);
      ctx.bezierCurveTo(cp1.x, cp1.y, cp2.x, cp2.y, st.x, st.y);
      ctx.strokeStyle = edgeColor;
      ctx.lineWidth = 4;
      ctx.stroke();
      ctx.restore();

      // Draw response edge (Claude → User) if active
      if (e.type === 'conversation' && this.responseEdgeOpacity > 0.01) {
        // Reverse direction: from target (main agent) to source (user), curving the opposite way
        var rcp1 = {x: sf.x + dx*0.3 - nx*off, y: sf.y + dy*0.3 - ny*off};
        var rcp2 = {x: sf.x + dx*0.7 - nx*off, y: sf.y + dy*0.7 - ny*off};
        ctx.globalAlpha = alpha * this.responseEdgeOpacity * 0.3;
        ctx.beginPath();
        ctx.moveTo(st.x, st.y);
        ctx.bezierCurveTo(rcp2.x, rcp2.y, rcp1.x, rcp1.y, sf.x, sf.y);
        ctx.strokeStyle = '#00d4ff';
        ctx.lineWidth = 2;
        ctx.stroke();
        // Glow
        ctx.save();
        ctx.globalCompositeOperation = 'lighter';
        ctx.globalAlpha = alpha * this.responseEdgeOpacity * 0.15;
        ctx.beginPath();
        ctx.moveTo(st.x, st.y);
        ctx.bezierCurveTo(rcp2.x, rcp2.y, rcp1.x, rcp1.y, sf.x, sf.y);
        ctx.strokeStyle = '#00d4ff';
        ctx.lineWidth = 4;
        ctx.stroke();
        ctx.restore();
      }

      // Message counters drawn in _drawMessageCounters() after nodes

      // Only draw permanent particles for dispatch/tool edges, not conversation
      if (e.type !== 'conversation') {
        if (e.particles.length === 0) this._initEdgeParticles(e);
        const sprite = e.type === "dispatch" ? this.sprites.glow : this.sprites.glowOrange;
        ctx.globalAlpha = alpha;
        for (const p of e.particles) {
          var isHovered = this.hovered === fa || this.hovered === ta;
          var isFaded = fa.opacity < 0.5 || ta.opacity < 0.5;
          var particleSpeed = this.playing && !this.playDone && !isFaded ? p.speed : (isHovered ? p.speed * 1.5 : 0);
          p.t += particleSpeed;
          if (p.t > 1) p.t -= 1;
          p.wobble += 0.03;

          const pos = this._cubicBezier(p.t, sf, cp1, cp2, st);
          const tan = this._cubicBezier(Math.min(1, p.t + 0.01), sf, cp1, cp2, st);
          const tdx = tan.x - pos.x, tdy = tan.y - pos.y;
          const tl = Math.sqrt(tdx*tdx + tdy*tdy) || 1;
          const wobX = -tdy/tl * Math.sin(p.wobble) * p.wobbleAmp;
          const wobY = tdx/tl * Math.sin(p.wobble) * p.wobbleAmp;

          const sz = 10 * this.cam.scale;
          ctx.drawImage(sprite, pos.x + wobX - sz/2, pos.y + wobY - sz/2, sz, sz);

          for (let ti = 1; ti <= 3; ti++) {
            const tt = p.t - ti * 0.015;
            if (tt < 0) continue;
            const tp = this._cubicBezier(tt, sf, cp1, cp2, st);
            ctx.globalAlpha = alpha * (1 - ti * 0.3);
            ctx.drawImage(sprite, tp.x - sz*0.3, tp.y - sz*0.3, sz*0.6, sz*0.6);
          }
          ctx.globalAlpha = alpha;
        }
      }
    }
    ctx.globalAlpha = 1;

    // Draw particle bursts (user→agent and agent→user)
    var burstsToRemove = [];
    for (var bi = 0; bi < this.reverseBursts.length; bi++) {
      var burst = this.reverseBursts[bi];
      var bFrom = burst.from, bTo = burst.to;
      if (!bFrom || !bTo || bFrom.opacity < 0.05) { burstsToRemove.push(bi); continue; }

      if (this.playing && !this.playDone) {
        burst.t += burst.speed;
      }

      if (burst.t >= 1) {
        this.effects.push({type:'pulse', node:bTo, t:0, dur:0.8, color:burst.color});
        burstsToRemove.push(bi);
        continue;
      }

      // Draw particles traveling from burst.from to burst.to
      var sf = this.worldToScreen(bFrom.x, bFrom.y);
      var st = this.worldToScreen(bTo.x, bTo.y);
      var dx = st.x - sf.x, dy = st.y - sf.y;
      var d = Math.sqrt(dx*dx + dy*dy) || 1;
      var nx = -dy/d, ny = dx/d;
      var off = d * 0.15;
      var cp1 = {x: sf.x + dx*0.3 + nx*off, y: sf.y + dy*0.3 + ny*off};
      var cp2 = {x: sf.x + dx*0.7 + nx*off, y: sf.y + dy*0.7 + ny*off};

      var sprite = burst.color === '#00ff88' ? this.sprites.glowGreen : this.sprites.glow;
      ctx.globalAlpha = 0.9;
      for (var pi = 0; pi < burst.particles; pi++) {
        var pt = burst.t - pi * 0.04;
        if (pt < 0 || pt > 1) continue;
        var pos = this._cubicBezier(pt, sf, cp1, cp2, st);
        var sz = 12 * this.cam.scale;
        ctx.drawImage(sprite, pos.x - sz/2, pos.y - sz/2, sz, sz);
        for (var ti = 1; ti <= 3; ti++) {
          var tt = pt - ti * 0.02;
          if (tt < 0) continue;
          var tp = this._cubicBezier(tt, sf, cp1, cp2, st);
          ctx.globalAlpha = 0.9 * (1 - ti * 0.3);
          ctx.drawImage(sprite, tp.x - sz*0.3, tp.y - sz*0.3, sz*0.6, sz*0.6);
        }
        ctx.globalAlpha = 0.9;
      }
    }
    ctx.globalAlpha = 1;
    for (var ri = burstsToRemove.length - 1; ri >= 0; ri--) {
      this.reverseBursts.splice(burstsToRemove[ri], 1);
    }
  }

  _fitAll() {
    const visible = this.allNodes.filter(n => n.opacity > 0.1);
    if (visible.length === 0) return;
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const n of visible) {
      minX = Math.min(minX, n.x - n.r);
      maxX = Math.max(maxX, n.x + n.r);
      minY = Math.min(minY, n.y - n.r);
      maxY = Math.max(maxY, n.y + n.r);
    }
    const pad = 80;
    const cw = maxX - minX + pad * 2, ch = maxY - minY + pad * 2;
    this.cam.tx = (minX + maxX) / 2;
    this.cam.ty = (minY + maxY) / 2;
    this.cam.ts = Math.min(this.W / cw, this.H / ch, 2.0);
    this.userOverride = false;
  }

  _raf() {
    const now = performance.now();
    const dt = this._lastFrame ? (now - this._lastFrame) / 1000 : 0.016;
    this._lastFrame = now;
    this._resize();
    this.cam.x += (this.cam.tx - this.cam.x) * 0.08;
    this.cam.y += (this.cam.ty - this.cam.y) * 0.08;
    this.cam.scale += (this.cam.ts - this.cam.scale) * 0.08;
    this.ctx.clearRect(0, 0, this.W, this.H);
    this._drawBackground(this.ctx);
    if (!this._simSettled) this._stepSimulation();
    for (const n of this.allNodes) {
      n.opacity += (n.targetOpacity - n.opacity) * 0.08;
    }
    if (!this.showAll && this.convEdgeOpacity > 0.01) {
      this.convEdgeOpacity *= 0.97; // slow fade
    } else if (!this.showAll) {
      this.convEdgeOpacity = 0;
    }
    if (!this.showAll && this.responseEdgeOpacity > 0.01) {
      this.responseEdgeOpacity *= 0.97;
    } else if (!this.showAll) {
      this.responseEdgeOpacity = 0;
    }
    this._stepPlayback(dt);
    this._drawEdges(this.ctx);
    this._drawNodes(this.ctx);
    this._drawMessageCounters(this.ctx);
    this._drawEffects(this.ctx, dt);
    requestAnimationFrame(() => this._raf());
  }

  _hitTest(sx, sy) {
    const w = this.screenToWorld(sx, sy);
    for (let i = this.nodes.length - 1; i >= 0; i--) {
      const n = this.nodes[i];
      if (n.opacity < 0.1) continue;
      const dx = w.x - n.x, dy = w.y - n.y;
      if (dx*dx + dy*dy < n.r*n.r) return n;
    }
    for (let i = this.toolNodes.length - 1; i >= 0; i--) {
      const n = this.toolNodes[i];
      if (n.opacity < 0.1) continue;
      const dx = w.x - n.x, dy = w.y - n.y;
      if (dx*dx + dy*dy < n.r*n.r) return n;
    }
    return null;
  }

  _updateTooltip(mx, my, node) {
    const el = document.getElementById("flow-tooltip");
    if (!el) return;
    if (!node) { el.style.display = "none"; return; }
    el.textContent = "";
    const h = document.createElement("h4");
    h.style.cssText = "color:#00d4ff;margin:0 0 4px;font-size:12px";
    h.textContent = node.name;
    el.appendChild(h);
    const addRow = (label, val) => {
      const row = document.createElement("div");
      row.style.cssText = "display:flex;justify-content:space-between;gap:12px";
      const lbl = document.createElement("span");
      lbl.style.color = "#666"; lbl.textContent = label;
      const v = document.createElement("span");
      v.style.color = "#fff"; v.textContent = val;
      row.appendChild(lbl); row.appendChild(v);
      el.appendChild(row);
    };
    if (node.type === "tool") {
      addRow("Calls", String(node.count));
    } else {
      const d = node.data || {};
      addRow("Type", d.type || "main");
      if (d.tokens) addRow("Tokens", ((d.tokens.input+d.tokens.output)/1000).toFixed(1) + "K");
      if (d.cost != null) addRow("Cost", "$" + d.cost.toFixed(4));
    }
    el.style.display = "block";
    el.style.left = (mx + 15) + "px";
    el.style.top = (my + 15) + "px";
  }

  _hideTooltip() {
    const el = document.getElementById("flow-tooltip");
    if (el) el.style.display = "none";
  }

  _scrollToMessage(node) {
    var evt;
    if (node.type === "tool") {
      evt = this.flow.events.find(e => e.type === "tool_call" && e.tool === node.name && e.agent_id === node.parentId);
    }
    if (!evt) {
      evt = this.flow.events.find(e => e.agent_id === node.id);
    }
    if (!evt) return;
    const msgEl = document.getElementById("msg-" + evt.msg_index) || document.getElementById("marker-" + evt.msg_index);
    if (msgEl) {
      msgEl.scrollIntoView({behavior: "smooth", block: "center"});
      msgEl.style.outline = "2px solid #00d4ff";
      setTimeout(() => { msgEl.style.outline = ""; }, 2000);
    }
  }

  _compressTime(t, events) {
    if (!events || events.length === 0) return 0;
    var compressed = 0, prevT = 0;
    for (var i = 0; i < events.length; i++) {
      if (events[i].t > t) break;
      compressed += Math.max(300, Math.min(2000, events[i].t - prevT));
      prevT = events[i].t;
    }
    compressed += Math.max(0, Math.min(2000, t - prevT));
    return compressed;
  }

  _processEvent(evt) {
    var nodeMap = this.nodeMap;
    var agent, toolNode, toolId;
    switch (evt.type) {
      case "message":
        agent = nodeMap[evt.agent_id];
        var userNode = nodeMap['user'];
        if (agent) {
          agent.targetOpacity = 1;
          agent.lastActiveTime = this.playTime;
          this._lastActiveNode = agent;
          if (evt.role === "user") {
            this._userMsgCount++;
            // Burst from user to main agent
            if (userNode && agent) {
              userNode.lastActiveTime = this.playTime;
              userNode.targetOpacity = 1;
              this.reverseBursts.push({
                from: userNode,
                to: agent,
                t: 0,
                speed: 0.03,
                color: '#00ff88',
                particles: 3
              });
              this.convEdgeOpacity = 1;
              agent.glowPulse = 0;
            }
          } else if (evt.role === "assistant") {
            this._assistantMsgCount++;
            // Reverse burst from main agent back to user (response)
            if (userNode) {
              userNode.targetOpacity = 1;
              this.reverseBursts.push({
                from: agent,
                to: userNode,
                t: 0,
                speed: 0.02,
                color: '#00d4ff',
                particles: 3
              });
              this.responseEdgeOpacity = 1;
              userNode.glowPulse = 0;
            }
          }
        }
        break;
      case "tool_call":
        toolId = evt.agent_id + "-tool-" + evt.tool;
        toolNode = nodeMap[toolId];
        if (toolNode) {
          toolNode.targetOpacity = 1;
          toolNode.displayCount = (toolNode.displayCount || 0) + 1;
          toolNode.lastActiveTime = this.playTime;
          this.effects.push({type:"spawn", node:toolNode, t:0, dur:0.6});
        }
        agent = nodeMap[evt.agent_id];
        if (agent) { agent.targetOpacity = 1; agent.lastActiveTime = this.playTime; this._lastActiveNode = agent; }
        break;
      case "agent_spawn":
        var newAgent = nodeMap[evt.agent_id];
        if (newAgent) {
          newAgent.targetOpacity = 1;
          newAgent.lastActiveTime = this.playTime;
          this.effects.push({type:"spawn", node:newAgent, t:0, dur:1.0});
          this._lastActiveNode = newAgent;
          this._simSettled = false;
        }
        break;
      case "compaction":
        agent = nodeMap[evt.agent_id];
        if (agent) this.effects.push({type:"flash", node:agent, t:0, dur:0.5, color:"#ff3344"});
        break;
      case "hook":
        agent = nodeMap[evt.agent_id];
        if (agent) this.effects.push({type:"flash", node:agent, t:0, dur:0.4, color:"#ffcc00"});
        break;
    }
    // Auto-scroll chat during playback
    if (evt.msg_index != null && this.playing) {
      var msgEl = document.getElementById('msg-' + evt.msg_index) || document.getElementById('marker-' + evt.msg_index);
      if (msgEl) {
        msgEl.scrollIntoView({behavior: 'smooth', block: 'nearest'});
      }
    }
  }

  _stepPlayback(dt) {
    if (!this.playing || this.playDone) return;
    var events = this.flow.events || [];
    if (events.length === 0) { this.playDone = true; return; }
    var maxT = events[events.length - 1].t;
    this.playTime += dt * 1000 * this.playSpeed;
    while (this.playIndex < events.length) {
      var playT = this._compressTime(events[this.playIndex].t, events);
      if (playT > this.playTime) break;
      this._processEvent(events[this.playIndex]);
      this.playIndex++;
    }
    // Fade out nodes unused for more than 8 seconds (compressed time)
    if (!this.showAll) {
      var fadeThreshold = 8000;
      for (var ni = 0; ni < this.allNodes.length; ni++) {
        var node = this.allNodes[ni];
        if (node.type === 'main' || node.type === 'user') continue; // Never fade main/user
        if (node.targetOpacity > 0 && this.playTime - node.lastActiveTime > fadeThreshold) {
          node.targetOpacity = 0.15; // Dim but not invisible
        }
      }
    }
    var prog = document.getElementById("flow-progress");
    if (prog) {
      var maxCompressed = this._compressTime(maxT, events);
      prog.style.width = Math.min(100, (this.playTime / maxCompressed) * 100) + "%";
    }
    if (this.playIndex >= events.length) {
      this.playDone = true;
      this.allNodes.forEach(function(n) { n.targetOpacity = 1; });
    }
    if (!this.userOverride && this._lastActiveNode) {
      this.cam.tx = this._lastActiveNode.x;
      this.cam.ty = this._lastActiveNode.y;
    }
  }

  _skipToEnd() {
    this.showAll = true;
    this.allNodes.forEach(function(n) { n.opacity = 1; n.targetOpacity = 1; });
    this.toolNodes.forEach(function(n) { n.displayCount = n.count; });
    this.playDone = true;
    this.playIndex = (this.flow.events || []).length;
    this.convEdgeOpacity = 0.3;
    this.responseEdgeOpacity = 0.3;
    this._userMsgCount = 0;
    this._assistantMsgCount = 0;
    var evts = this.flow.events || [];
    for (var ei = 0; ei < evts.length; ei++) {
      if (evts[ei].type === 'message' && evts[ei].role === 'user') this._userMsgCount++;
      if (evts[ei].type === 'message' && evts[ei].role === 'assistant') this._assistantMsgCount++;
    }
    var prog = document.getElementById("flow-progress");
    if (prog) prog.style.width = "100%";
    this._fitAll();
  }

  _drawMessageCounters(ctx) {
    // Draw message counters anchored to node edges, rendered above nodes
    var userNode = this.nodeMap ? this.nodeMap['user'] : null;
    var mainNode = this.nodeMap ? this.nodeMap['main'] : null;
    if (!userNode || !mainNode || userNode.opacity < 0.05 || mainNode.opacity < 0.05) return;

    ctx.font = '10px monospace';
    ctx.textBaseline = 'middle';

    // User message count - anchored to right edge of User node
    if (this._userMsgCount > 0) {
      var us = this.worldToScreen(userNode.x, userNode.y);
      var ur = userNode.r * this.cam.scale;
      var umAlpha = this.convEdgeOpacity > 0.1 ? 0.8 : 0.35;
      ctx.globalAlpha = userNode.opacity * umAlpha;
      ctx.fillStyle = '#00ff88';
      ctx.textAlign = 'left';
      ctx.fillText(this._userMsgCount + '', us.x + ur + 8, us.y - ur * 0.5);
    }

    // Assistant message count - anchored to left edge of Claude node
    if (this._assistantMsgCount > 0) {
      var ms = this.worldToScreen(mainNode.x, mainNode.y);
      var mr = mainNode.r * this.cam.scale;
      var amAlpha = this.responseEdgeOpacity > 0.1 ? 0.8 : 0.35;
      ctx.globalAlpha = mainNode.opacity * amAlpha;
      ctx.fillStyle = '#00d4ff';
      ctx.textAlign = 'right';
      ctx.fillText(this._assistantMsgCount + '', ms.x - mr - 6, ms.y + mr * 0.5);
    }

    ctx.globalAlpha = 1;
  }

  _drawEffects(ctx, dt) {
    var toRemove = [];
    for (var i = 0; i < this.effects.length; i++) {
      var fx = this.effects[i];
      if (this.playing || this.playDone) fx.t += dt;
      var progress = fx.t / fx.dur;
      if (progress > 1) { toRemove.push(i); continue; }
      var n = fx.node;
      if (!n || n.opacity < 0.01) continue;
      var s = this.worldToScreen(n.x, n.y);
      var r = n.r * this.cam.scale;
      var color = fx.color || n.color;
      if (fx.type === "spawn") {
        var ringR = r * (1 + progress * 1.5);
        ctx.globalAlpha = (1 - progress) * 0.6;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(s.x, s.y, ringR, 0, Math.PI * 2);
        ctx.stroke();
        if (progress < 0.3) {
          ctx.globalAlpha = (1 - progress / 0.3) * 0.4;
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(s.x, s.y, r * 1.2, 0, Math.PI * 2);
          ctx.fill();
        }
      } else if (fx.type === "pulse") {
        var pulseR = r + Math.sin(progress * Math.PI) * 15;
        ctx.globalAlpha = (1 - progress) * 0.5;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        this._hexPath(ctx, s.x, s.y, pulseR);
        ctx.stroke();
      } else if (fx.type === "flash") {
        ctx.globalAlpha = (1 - progress) * 0.7;
        ctx.save();
        ctx.shadowColor = color;
        ctx.shadowBlur = 20;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(s.x, s.y, r * 0.4, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
      }
    }
    ctx.globalAlpha = 1;
    for (var j = toRemove.length - 1; j >= 0; j--) {
      this.effects.splice(toRemove[j], 1);
    }
  }

  _bindEvents() {
    const c = this.canvas;
    window.addEventListener("resize", () => this._resize());

    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      const factor = e.deltaY > 0 ? 0.92 : 1.08;
      const newScale = Math.max(0.3, Math.min(3.0, this.cam.scale * factor));
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const before = this.screenToWorld(mx, my);
      this.cam.scale = newScale;
      const after = this.screenToWorld(mx, my);
      this.cam.x -= (after.x - before.x);
      this.cam.y -= (after.y - before.y);
      this.cam.tx = this.cam.x; this.cam.ty = this.cam.y;
      this.cam.ts = this.cam.scale;
      this.userOverride = true;
    }, {passive: false});

    this._dragDist = 0;
    this._mouseDownPos = {x:0, y:0};

    c.addEventListener("mousedown", (e) => {
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      this._mouseDownPos = {x: mx, y: my};
      this._dragDist = 0;
      const hit = this._hitTest(mx, my);
      if (hit) {
        this.dragging = hit;
        hit.fx = hit.x; hit.fy = hit.y;
        this._simSettled = false;
      } else {
        this.panning = true;
        this.panStart = {x: mx, y: my};
        this.panCamStart = {x: this.cam.x, y: this.cam.y};
      }
    });

    c.addEventListener("mousemove", (e) => {
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const ddx = mx - this._mouseDownPos.x, ddy = my - this._mouseDownPos.y;
      this._dragDist = Math.sqrt(ddx*ddx + ddy*ddy);
      if (this.dragging) {
        const w = this.screenToWorld(mx, my);
        this.dragging.fx = w.x; this.dragging.fy = w.y;
        this.dragging.x = w.x; this.dragging.y = w.y;
        this._simSettled = false;
      } else if (this.panning) {
        const dx = (mx - this.panStart.x) / this.cam.scale;
        const dy = (my - this.panStart.y) / this.cam.scale;
        this.cam.x = this.panCamStart.x - dx;
        this.cam.y = this.panCamStart.y - dy;
        this.cam.tx = this.cam.x; this.cam.ty = this.cam.y;
        this.cam.vx = -dx * 0.1; this.cam.vy = -dy * 0.1;
        this.userOverride = true;
      } else {
        const hit = this._hitTest(mx, my);
        this.hovered = hit;
        c.style.cursor = hit ? "pointer" : "grab";
        this._updateTooltip(mx, my, hit);
      }
    });

    c.addEventListener("mouseup", () => {
      if (this.dragging) {
        this.dragging.fx = null; this.dragging.fy = null;
        this._simSettled = false;
        this.dragging = null;
      }
      if (this.panning) {
        this.cam.tx = this.cam.x + this.cam.vx * 5;
        this.cam.ty = this.cam.y + this.cam.vy * 5;
      }
      this.panning = false;
    });

    c.addEventListener("mouseleave", () => {
      this.hovered = null;
      this._hideTooltip();
    });

    c.addEventListener("click", (e) => {
      if (this._dragDist > 5) return;
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const hit = this._hitTest(mx, my);
      this.selected = hit;
      if (hit) this._scrollToMessage(hit);
    });

    const fitBtn = document.getElementById("flow-fit");
    if (fitBtn) fitBtn.addEventListener("click", () => this._fitAll());

    var self = this;
    var fsBtn = document.getElementById('flow-fullscreen');
    if (fsBtn) fsBtn.addEventListener('click', function() {
      var fc = document.querySelector('.flow-container');
      if (!fc) return;
      var isFs = fc.classList.toggle('fullscreen');
      fsBtn.textContent = isFs ? '✖' : '⛶';
      fsBtn.title = isFs ? 'Exit fullscreen' : 'Fullscreen';
      self._resize();
      self._fitAll();
    });

    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        var fc = document.querySelector('.flow-container');
        if (fc && fc.classList.contains('fullscreen')) {
          fc.classList.remove('fullscreen');
          if (fsBtn) { fsBtn.textContent = '⛶'; fsBtn.title = 'Fullscreen'; }
          self._resize();
          self._fitAll();
        }
      }
    });
    var playBtn = document.getElementById("flow-play");
    if (playBtn) playBtn.addEventListener("click", function() {
      self.playing = !self.playing;
      playBtn.textContent = self.playing ? "⏸" : "▶";
    });

    var showAllBtn = document.getElementById("flow-showall");
    if (showAllBtn) showAllBtn.addEventListener("click", function() {
      self.showAll = !self.showAll;
      showAllBtn.classList.toggle("active", self.showAll);
      if (self.showAll) {
        self.allNodes.forEach(function(n) { n.targetOpacity = 1; });
      }
    });

    var rewindBtn = document.getElementById("flow-rewind");
    if (rewindBtn) rewindBtn.addEventListener("click", function() {
      self.playTime = 0;
      self.playIndex = 0;
      self.playDone = false;
      self.showAll = false;
      self.effects = [];
      self.reverseBursts = [];
      self._userMsgCount = 0;
      self._assistantMsgCount = 0;
      self.allNodes.forEach(function(n) { n.opacity = 0; n.targetOpacity = 0; });
      self.toolNodes.forEach(function(n) { n.displayCount = 0; });
      // Show user and main agent immediately
      if (self.nodes.length > 0) {
        self.nodes[0].targetOpacity = 1;
        self.effects.push({type:"spawn", node:self.nodes[0], t:0, dur:1.0});
      }
      var userNode = self.allNodes.find(function(n) { return n.id === "user"; });
      if (userNode) {
        userNode.targetOpacity = 1;
        self.effects.push({type:"spawn", node:userNode, t:0, dur:1.0});
      }
      self.playing = true;
      if (playBtn) playBtn.textContent = "▶";
      var prog = document.getElementById("flow-progress");
      if (prog) prog.style.width = "0%";
      self.userOverride = false;
      self._fitAll();
      if (showAllBtn) showAllBtn.classList.remove("active");
    });

    document.querySelectorAll(".speed-btn").forEach(function(btn) {
      btn.addEventListener("click", function() {
        var speed = parseInt(btn.dataset.speed);
        if (isNaN(speed)) return; // skip non-speed buttons like showall
        if (speed === 0) { self._skipToEnd(); return; }
        self.playSpeed = speed;
        document.querySelectorAll(".speed-btn").forEach(function(b) { b.classList.remove("active"); });
        btn.classList.add("active");
      });
    });

    var progBar = document.querySelector(".flow-progress");
    if (progBar) progBar.addEventListener("click", function(e) {
      var rect = progBar.getBoundingClientRect();
      var pct = (e.clientX - rect.left) / rect.width;
      var events = self.flow.events || [];
      if (events.length === 0) return;
      var maxT = self._compressTime(events[events.length - 1].t, events);
      self.playTime = pct * maxT;
      self.playIndex = 0;
      self._userMsgCount = 0;
      self._assistantMsgCount = 0;
      self.allNodes.forEach(function(n) { n.opacity = 0; n.targetOpacity = 0; });
      self.toolNodes.forEach(function(n) { n.displayCount = 0; });
      self.effects = [];
      self.reverseBursts = [];
      self.playDone = false;
      var wasPlaying = self.playing;
      self.playing = true;
      self._stepPlayback(0);
      self.playing = wasPlaying;
    });
  }
}

if (document.body.classList.contains('flow-hidden')) {
  // Visualization globally hidden via config — skip canvas init entirely.
} else if (FLOW && FLOW.agents && FLOW.agents.length > 0 && FLOW.events && FLOW.events.length > 0) {
  const fc = document.getElementById("flow-canvas");
  const cp = document.querySelector(".chat-panel");
  if (fc && cp) {
    window._sessionFlow = new SessionFlow(fc, FLOW, cp);
  }
} else {
  var fc = document.querySelector('.flow-container');
  if (fc) fc.style.display = 'none';
}

document.querySelectorAll(".msg,.marker").forEach(function(el) {
  el.addEventListener("click", function() {
    if (!window._sessionFlow) return;
    var match = (el.id || "").match(/(?:msg|marker)-(\d+)/);
    var idx = match ? parseInt(match[1]) : NaN;
    if (isNaN(idx)) return;
    var sf = window._sessionFlow;
    var evt = sf.flow.events.find(function(e) { return e.msg_index === idx; });
    if (!evt) return;
    var node = sf.allNodes.find(function(n) { return n.id === evt.agent_id; });
    if (node) {
      sf.selected = node;
      sf.effects.push({type:"pulse", node:node, t:0, dur:1.0});
    }
  });
});

var flowToggle = document.getElementById('flow-toggle');
var flowContainer = document.querySelector('.flow-container');
if (flowToggle && flowContainer) {
  var FLOW_COLLAPSE_KEY = 'claude-stats:flow-collapsed';
  var iconEl = flowToggle.querySelector('.flow-toggle-icon');
  var labelEl = flowToggle.querySelector('.flow-toggle-label');

  function applyCollapsed(collapsed) {
    document.body.classList.toggle('flow-collapsed', collapsed);
    flowToggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    if (iconEl) iconEl.innerHTML = collapsed ? '&#9660;' : '&#9650;';
    if (labelEl) labelEl.textContent = collapsed ? 'Show Flow' : 'Hide Flow';
  }

  var stored = null;
  try { stored = localStorage.getItem(FLOW_COLLAPSE_KEY); } catch (e) {}
  applyCollapsed(stored === '1');

  flowToggle.addEventListener('click', function() {
    var next = !document.body.classList.contains('flow-collapsed');
    applyCollapsed(next);
    try { localStorage.setItem(FLOW_COLLAPSE_KEY, next ? '1' : '0'); } catch (e) {}
    if (!next && window._sessionFlow) {
      window._sessionFlow._resize();
      window._sessionFlow._fitAll();
    }
  });
}

// ── Variant-C wiring (theme + utc + anon F2) ─────────────────────
document.addEventListener('keydown', function(e) {
  if (e.key === 'F2') {
    e.preventDefault();
    document.body.classList.toggle('anon-mode');
    let note = document.getElementById('anonNote');
    if (!note) {
      note = document.createElement('div');
      note.id = 'anonNote';
      note.className = 'vc';
      note.style.cssText = 'position:fixed;top:14px;right:14px;padding:8px 14px;border-radius:var(--vc-radius-sm,10px);border:1px solid var(--vc-accent,#c2562f);background:var(--vc-panel,#ffffff);box-shadow:var(--vc-shadow);font-family:var(--vc-font-mono,JetBrains Mono,ui-monospace,monospace);font-size:11px;letter-spacing:0.14em;text-transform:uppercase;z-index:9999;transition:opacity 0.3s;color:var(--vc-accent,#c2562f);';
      document.body.appendChild(note);
    }
    note.textContent = document.body.classList.contains('anon-mode') ? '> ANONYMIZATION ON' : '> ANONYMIZATION OFF';
    note.style.opacity = '1';
    setTimeout(() => { note.style.opacity = '0'; }, 2000);
  }
});

(function() {
  function vcSystemPrefersDark() {
    try { return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches; }
    catch (e) { return false; }
  }
  function applyTheme(t) {
    document.documentElement.classList.remove('theme-light','theme-dark');
    document.documentElement.classList.add('theme-' + t);
    const btn = document.getElementById('vcThemeToggle');
    if (btn) btn.innerHTML = t === 'dark' ? '&#9790;' : '&#9737;';
  }
  const saved = localStorage.getItem('vc-theme');
  const initial = (saved === 'light' || saved === 'dark') ? saved : (vcSystemPrefersDark() ? 'dark' : 'light');
  applyTheme(initial);
  document.getElementById('vcThemeToggle')?.addEventListener('click', () => {
    const cur = document.documentElement.classList.contains('theme-dark') ? 'dark' : 'light';
    const n = cur === 'dark' ? 'light' : 'dark';
    localStorage.setItem('vc-theme', n);
    applyTheme(n);
  });
  function utc() {
    const el = document.getElementById('vcUtcTime');
    if (!el) return;
    el.textContent = new Date().toISOString().slice(11,19) + ' UTC';
  }
  utc();
  setInterval(utc, 1000);

  // Anon-blur the session title (it's typically a project-derived title with potentially unpredictable text)
  const titleEl = document.getElementById('sessionTitle');
  if (titleEl) titleEl.classList.add('anon-blur');

  // Anon-blur message content (user prompts and assistant outputs are unpredictable)
  function blurMessages() {
    document.querySelectorAll('.message-content, .message-text, .chat-messages .message').forEach(el => {
      if (!el.classList.contains('anon-blur') && !el.querySelector('.anon-blur')) {
        // Only wrap text-containing nodes, not whole message wrappers
        if (el.classList.contains('message')) {
          el.querySelectorAll('p, pre, code, span, div').forEach(child => {
            if (child.children.length === 0 && child.textContent.trim() && !child.classList.contains('anon-blur')) {
              child.classList.add('anon-blur');
            }
          });
        } else {
          el.classList.add('anon-blur');
        }
      }
    });
  }
  // Run after chat panel initializes (give it a moment)
  setTimeout(blurMessages, 500);
  // Re-run when chat content changes (filter switch)
  const chat = document.getElementById('chatPanel');
  if (chat) {
    new MutationObserver(() => setTimeout(blurMessages, 100)).observe(chat, {childList: true, subtree: true});
  }
})();
