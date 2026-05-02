
const P = "__PROJECT_DATA__";
const fmt = n => n.toLocaleString();
const fmtUSD = n => '$'+n.toFixed(2);
const fmtTokens = n => { if(n>=1e6) return (n/1e6).toFixed(1)+'M'; if(n>=1e3) return (n/1e3).toFixed(1)+'K'; return n.toString(); };
function escHtml(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
function modelClass(m) { const l=(m||'').toLowerCase(); if(l.includes('opus')) return 'opus'; if(l.includes('sonnet')) return 'sonnet'; if(l.includes('haiku')) return 'haiku'; return ''; }

document.getElementById('projectTitle').textContent = P.name;
document.getElementById('kpiGrid').innerHTML =
  '<div class="kpi-card"><div class="label">Sessions</div><div class="value" style="color:var(--blue)">'+P.stats.total_sessions+'</div></div>' +
  '<div class="kpi-card"><div class="label">Messages</div><div class="value" style="color:var(--green)">'+fmt(P.stats.total_messages)+'</div></div>' +
  '<div class="kpi-card"><div class="label">Tokens</div><div class="value" style="color:var(--purple)">'+fmtTokens(P.stats.total_tokens)+'</div></div>' +
  '<div class="kpi-card"><div class="label">Est. Cost</div><div class="value" style="color:var(--orange)">'+fmtUSD(P.stats.total_cost)+'</div></div>';

document.getElementById('toolPills').innerHTML = Object.entries(P.tools).slice(0,20).map(([n,c]) =>
  '<div class="tool-pill"><span>'+escHtml(n)+'</span><span class="count">'+c+'x</span></div>'
).join('');

if (Object.keys(P.skills).length>0) {
  document.getElementById('skillsSection').innerHTML =
    '<div class="tools-section"><h3>Skills</h3><div class="tool-pills">' +
    Object.entries(P.skills).map(([n,c]) =>
      '<div class="tool-pill" style="border:1px solid rgba(168,85,247,0.3)"><span style="color:var(--purple)">'+escHtml(n)+'</span><span class="count" style="color:var(--purple)">'+c+'x</span></div>'
    ).join('') + '</div></div>';
}

// Tab switching
document.querySelectorAll('.proj-tab').forEach(tab => {
  tab.addEventListener('click', function() {
    document.querySelectorAll('.proj-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.proj-tab-content').forEach(c => c.classList.remove('active'));
    this.classList.add('active');
    document.getElementById('ptab-'+this.dataset.tab).classList.add('active');
  });
});

// Memory
if (P.memory) {
  document.getElementById('memorySection').innerHTML =
    '<div class="memory-card" id="memCard"><h3 onclick="document.getElementById(\'memCard\').classList.toggle(\'expanded\')">Project Memory</h3><div class="memory-content anon-blur">'+escHtml(P.memory)+'</div></div>';
}

// Info grid (subagents, git ops, errors)
let infoHtml = '';
const agentTypes = Object.entries(P.agent_types || {});
if (agentTypes.length > 0) {
  infoHtml += '<div class="info-card"><h4>Subagents</h4>' +
    agentTypes.map(([t,c]) => '<span class="tag" style="background:rgba(99,102,241,0.15);color:var(--accent2)">'+escHtml(t)+' '+c+'x</span>').join('') +
    '</div>';
}
const go = P.git_ops || {};
if ((go.commits||0) + (go.pushes||0) + (go.prs||0) > 0) {
  infoHtml += '<div class="info-card"><h4>Git Operations</h4>' +
    '<div class="info-row"><span class="lbl">Commits</span><span class="val" style="color:var(--green)">'+(go.commits||0)+'</span></div>' +
    '<div class="info-row"><span class="lbl">Pushes</span><span class="val" style="color:var(--blue)">'+(go.pushes||0)+'</span></div>' +
    '<div class="info-row"><span class="lbl">PRs</span><span class="val" style="color:var(--purple)">'+(go.prs||0)+'</span></div>' +
    '</div>';
}
if (P.error_count > 0) {
  infoHtml += '<div class="info-card"><h4>Errors</h4>' +
    '<div style="font-size:24px;font-weight:700;color:var(--red)">'+P.error_count+'</div>' +
    '<div style="color:var(--text2);font-size:12px">tool errors in this project</div></div>';
}
document.getElementById('infoGrid').innerHTML = infoHtml;

// Top files table
const tf = P.top_files || [];
if (tf.length > 0) {
  document.getElementById('topFilesSection').innerHTML =
    '<div class="tools-section"><h3>Top Files</h3>' +
    '<table class="file-table"><thead><tr><th>File</th><th>Reads</th><th>Edits</th><th>Writes</th></tr></thead><tbody>' +
    tf.map(f => {
      const short = f.path.split('/').slice(-2).join('/');
      return '<tr><td title="'+escHtml(f.path)+'"><code style="font-size:11px">'+escHtml(short)+'</code></td>' +
        '<td style="color:var(--blue)">'+(f.ops.read||0)+'</td>' +
        '<td style="color:var(--cyan)">'+(f.ops.edit||0)+'</td>' +
        '<td style="color:var(--green)">'+(f.ops.write||0)+'</td></tr>';
    }).join('') +
    '</tbody></table></div>';
}

document.getElementById('sessionList').innerHTML = P.sessions.map(s =>
  '<div class="session-card">' +
    '<div class="top">' +
      '<div>' +
        '<span style="color:var(--text2);font-size:12px">'+new Date(s.start).toLocaleDateString()+' '+new Date(s.start).toLocaleTimeString()+'</span>' +
        '<span class="model-badge '+modelClass(s.primary_model)+'" style="margin-left:8px">'+escHtml(s.primary_model)+'</span>' +
        ((s.compactions||0)>0 ? '<span style="color:var(--amber);font-size:12px;margin-left:8px">&#9889; '+s.compactions+'</span>' : '') +
      '</div>' +
      '<div style="display:flex;gap:12px;align-items:center">' +
        '<a href="../sessions/'+s.session_id+'.html" style="font-size:12px;padding:4px 10px;border:1px solid var(--accent);border-radius:6px">Chat</a>' +
        '<span class="cost">'+fmtUSD(s.cost)+'</span>' +
      '</div>' +
    '</div>' +
    '<div class="info">' +
      '<span>'+s.duration_min+'m</span>' +
      '<span>'+s.messages+' msgs</span>' +
      '<span>'+fmtTokens(s.input_tokens+s.output_tokens)+' tokens</span>' +
      '<span>'+s.api_calls+' API calls</span>' +
    '</div>' +
  '</div>'
).join('');

// Workflow timeline
const wf = P.workflow || [];
const wfTypes = ['read','edit','write','git_commit','git_push','git_pr','agent'];
const wfLabels = {read:'Read',edit:'Edit',write:'Write',git_commit:'Commit',git_push:'Push',git_pr:'PR',agent:'Agent'};
let activeWfFilters = new Set(wfTypes);

function renderWorkflow() {
  const filtered = wf.filter(e => activeWfFilters.has(e.type));
  const el = document.getElementById('workflowTimeline');
  if (filtered.length === 0) { el.innerHTML = '<div style="color:var(--text2);padding:20px">No workflow events</div>'; return; }
  const shown = filtered.slice(0, 200);
  el.innerHTML = shown.map(e => {
    let label = '';
    if (e.path) {
      const short = e.path.split('/').slice(-2).join('/');
      label = '<span class="path">'+escHtml(short)+'</span>';
    } else if (e.message) {
      label = '<span class="msg">'+escHtml(e.message.slice(0,80))+'</span>';
    } else if (e.description) {
      label = '<span class="msg">'+escHtml(e.description)+'</span>';
    }
    const ts = e.timestamp ? '<span class="ts">'+new Date(e.timestamp).toLocaleTimeString()+'</span>' : '';
    return '<div class="wf-entry '+e.type+'">'+label+ts+'</div>';
  }).join('') + (filtered.length > 200 ? '<div style="color:var(--text2);padding:8px;font-size:12px">...and '+(filtered.length-200)+' more</div>' : '');
}

document.getElementById('wfFilters').innerHTML = wfTypes.map(t =>
  '<button class="wf-filter active" data-type="'+t+'">'+wfLabels[t]+'</button>'
).join('');

document.querySelectorAll('.wf-filter').forEach(btn => {
  btn.addEventListener('click', function() {
    const type = this.dataset.type;
    if (activeWfFilters.has(type)) { activeWfFilters.delete(type); this.classList.remove('active'); }
    else { activeWfFilters.add(type); this.classList.add('active'); }
    renderWorkflow();
  });
});

renderWorkflow();

// ── Variant-C wiring (theme + utc + meta + anon F2) ──────────────
document.addEventListener('keydown', function(e) {
  if (e.key === 'F2') {
    e.preventDefault();
    document.body.classList.toggle('anon-mode');
    let note = document.getElementById('anonNote');
    if (!note) {
      note = document.createElement('div');
      note.id = 'anonNote';
      note.className = 'vc';
      note.style.cssText = 'position:fixed;top:14px;right:14px;padding:8px 14px;border:1px solid var(--vc-accent,#b04a2f);background:var(--vc-panel,#fbfaf6);font-family:Geist Mono,JetBrains Mono,ui-monospace,monospace;font-size:11px;letter-spacing:0.14em;text-transform:uppercase;z-index:9999;transition:opacity 0.3s;color:var(--vc-accent,#b04a2f);';
      document.body.appendChild(note);
    }
    note.textContent = document.body.classList.contains('anon-mode') ? '> ANONYMIZATION ON' : '> ANONYMIZATION OFF';
    note.style.opacity = '1';
    setTimeout(() => { note.style.opacity = '0'; }, 2000);
  }
});


(function() {
  function v(name, fb) { return getComputedStyle(document.querySelector('.vc') || document.documentElement).getPropertyValue(name).trim() || fb; }
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

  // Project name + meta
  const nameEl = document.getElementById('vcProjectName');
  if (nameEl && typeof P !== 'undefined' && P.name) {
    nameEl.textContent = P.name;
    nameEl.classList.add('anon-blur'); // Project names get blurred in anon-mode
  }
  const metaEl = document.getElementById('vcProjectMeta');
  if (metaEl && typeof P !== 'undefined') {
    const stats = P.stats || {};
    metaEl.textContent = (stats.total_sessions || 0) + ' sessions · ' + (stats.total_messages || 0) + ' msgs · $' + (stats.total_cost || 0).toFixed(2);
  }
})();
