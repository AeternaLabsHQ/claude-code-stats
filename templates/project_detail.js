
const P = "__PROJECT_DATA__";
const PD_L = (window.__LOCALE__ && window.__LOCALE__.project_detail) || {};
const pdl = (key, fallback) => PD_L[key] != null ? PD_L[key] : fallback;
const fmt = n => (Number(n) || 0).toLocaleString(VCShared.localeCode());
const fmtUSD = n => VCShared.fmtUSD(n);
const fmtTokens = VCShared.fmtTokens;
const escHtml = VCShared.escHtml;

document.getElementById('projectTitle').textContent = P.name;
document.getElementById('kpiGrid').innerHTML =
  '<div class="kpi-card"><div class="label">'+pdl('kpi_sessions','Sessions')+'</div><div class="value" style="color:var(--blue)">'+P.stats.total_sessions+'</div></div>' +
  '<div class="kpi-card"><div class="label">'+pdl('kpi_messages','Messages')+'</div><div class="value" style="color:var(--green)">'+fmt(P.stats.total_messages)+'</div></div>' +
  '<div class="kpi-card"><div class="label">'+pdl('kpi_tokens','Tokens')+'</div><div class="value" style="color:var(--purple)">'+fmtTokens(P.stats.total_tokens)+'</div></div>' +
  '<div class="kpi-card"><div class="label">'+pdl('kpi_est_cost','Est. Cost')+'</div><div class="value" style="color:var(--orange)">'+fmtUSD(P.stats.total_cost)+'</div></div>';

// The name span is ellipsis-truncated in CSS (.vc .tool-pill span:first-child)
// on narrow chips - a title attribute is the only way to still read the
// full name (there is no scrollbar and no wrap on that span).
document.getElementById('toolPills').innerHTML = Object.entries(P.tools).slice(0,20).map(([n,c]) =>
  '<div class="tool-pill"><span title="'+escHtml(n)+'">'+escHtml(n)+'</span><span class="count">'+c+'x</span></div>'
).join('');

if (Object.keys(P.skills).length>0) {
  document.getElementById('skillsSection').innerHTML =
    '<div class="tools-section"><h3>'+pdl('skills','Skills')+'</h3><div class="tool-pills">' +
    Object.entries(P.skills).map(([n,c]) =>
      '<div class="tool-pill"><span title="'+escHtml(n)+'">'+escHtml(n)+'</span><span class="count">'+c+'x</span></div>'
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
    '<div class="memory-card" id="memCard"><h3 onclick="document.getElementById(\'memCard\').classList.toggle(\'expanded\')">'+pdl('memory','Project Memory')+'</h3><div class="memory-content anon-blur">'+escHtml(P.memory)+'</div></div>';
}

// Info grid (subagents, git ops, errors)
let infoHtml = '';
const agentTypes = Object.entries(P.agent_types || {});
if (agentTypes.length > 0) {
  infoHtml += '<div class="info-card"><h4>'+pdl('subagents','Subagents')+'</h4>' +
    agentTypes.map(([t,c]) => '<span class="tag" style="background:var(--vc-accent-soft);color:var(--vc-accent)">'+escHtml(t)+' '+c+'x</span>').join('') +
    '</div>';
}
const go = P.git_ops || {};
if ((go.commits||0) + (go.pushes||0) + (go.prs||0) > 0) {
  infoHtml += '<div class="info-card"><h4>'+pdl('git_operations','Git Operations')+'</h4>' +
    '<div class="info-row"><span class="lbl">'+pdl('commits','Commits')+'</span><span class="val" style="color:var(--green)">'+(go.commits||0)+'</span></div>' +
    '<div class="info-row"><span class="lbl">'+pdl('pushes','Pushes')+'</span><span class="val" style="color:var(--blue)">'+(go.pushes||0)+'</span></div>' +
    '<div class="info-row"><span class="lbl">'+pdl('prs','PRs')+'</span><span class="val" style="color:var(--purple)">'+(go.prs||0)+'</span></div>' +
    '</div>';
}
if (P.error_count > 0) {
  infoHtml += '<div class="info-card"><h4>'+pdl('errors_label','Errors')+'</h4>' +
    '<div style="font-size:24px;font-weight:700;color:var(--red)">'+P.error_count+'</div>' +
    '<div style="color:var(--text2);font-size:12px">'+pdl('tool_errors_note','tool errors in this project')+'</div></div>';
}
document.getElementById('infoGrid').innerHTML = infoHtml;

// Top files table
const tf = P.top_files || [];
if (tf.length > 0) {
  document.getElementById('topFilesSection').innerHTML =
    '<div class="tools-section"><h3>'+pdl('top_files','Top Files')+'</h3>' +
    '<div class="file-table-scroll">' +
    '<table class="file-table"><thead><tr><th>'+pdl('th_file','File')+'</th><th>'+pdl('th_reads','Reads')+'</th><th>'+pdl('th_edits','Edits')+'</th><th>'+pdl('th_writes','Writes')+'</th></tr></thead><tbody>' +
    tf.map(f => {
      const short = f.path.split('/').slice(-2).join('/');
      return '<tr><td title="'+escHtml(f.path)+'"><code style="font-size:11px">'+escHtml(short)+'</code></td>' +
        '<td style="color:var(--blue)">'+(f.ops.read||0)+'</td>' +
        '<td style="color:var(--cyan)">'+(f.ops.edit||0)+'</td>' +
        '<td style="color:var(--green)">'+(f.ops.write||0)+'</td></tr>';
    }).join('') +
    '</tbody></table>' +
    '</div></div>';
}

let pdSessionTable = null;
let pdSessionFilters = null;
const pdAllSessions = Array.isArray(P.sessions) ? P.sessions.slice() : [];

function pdApplyFilters() {
  let list = pdAllSessions.slice();
  if (pdSessionFilters) {
    const active = pdSessionFilters.getActiveFiltersList();
    for (const f of active) list = list.filter(f.predicate);
  }
  return list;
}

// Anon-source helper for the source column (project_detail has no global
// anonName plumbing; this gives it a per-page Source-N substitution that
// matches what dashboard.js uses).
const _pdAnonSrcMap = {};
let _pdAnonSrcN = 0;
function pdAnonSource(name) {
  if (!_pdAnonSrcMap[name]) { _pdAnonSrcN++; _pdAnonSrcMap[name] = 'Source ' + _pdAnonSrcN; }
  return _pdAnonSrcMap[name];
}

function pdRender() {
  const next = pdApplyFilters();
  if (!pdSessionTable) {
    pdSessionTable = mountSessionTable(
      document.getElementById('sessionList'),
      next,
      { context: 'projectDetail', hideChatInAnon: false, anonSource: pdAnonSource }
    );
  } else {
    pdSessionTable.update(next);
  }
}

pdSessionFilters = mountSessionFilters(
  document.getElementById('sessionFiltersMount'),
  {
    context: 'projectDetail',
    getPool: () => pdAllSessions,
    onChange: pdRender,
  }
);

pdRender();

// Workflow timeline
const wf = P.workflow || [];
const wfTypes = ['read','edit','write','git_commit','git_push','git_pr','agent'];
const wfLabels = {
  read: pdl('wf_read','Read'), edit: pdl('wf_edit','Edit'), write: pdl('wf_write','Write'),
  git_commit: pdl('wf_commit','Commit'), git_push: pdl('wf_push','Push'),
  git_pr: pdl('wf_pr','PR'), agent: pdl('wf_agent','Agent'),
};
let activeWfFilters = new Set(wfTypes);

function renderWorkflow() {
  const filtered = wf.filter(e => activeWfFilters.has(e.type));
  const el = document.getElementById('workflowTimeline');
  if (filtered.length === 0) { el.innerHTML = '<div style="color:var(--text2);padding:20px">'+pdl('no_workflow','No workflow events')+'</div>'; return; }
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
  }).join('') + (filtered.length > 200 ? '<div style="color:var(--text2);padding:8px;font-size:12px">'+pdl('more_suffix','...and {n} more').replace('{n}', filtered.length-200)+'</div>' : '');
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

// ── Page wiring (theme + utc + meta + anon F2) ───────────────────
document.addEventListener('keydown', function(e) {
  if (e.key === 'F2') {
    e.preventDefault();
    document.body.classList.toggle('anon-mode');
    // F19: re-render immediately so the table picks up anon-mode
    // (renderTable reads body class + applies anonSource substitution).
    pdRender();
    VCShared.vcAnonNote(document.body.classList.contains('anon-mode'));
  }
});


(function() {
  VCShared.vcInitThemePage();

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
