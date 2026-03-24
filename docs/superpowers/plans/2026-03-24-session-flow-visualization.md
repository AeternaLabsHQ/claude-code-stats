# Session Flow Visualization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an interactive Canvas 2D flow visualization with holographic/sci-fi aesthetics to session replay pages, showing agent hierarchy, tool usage, and message flow.

**Architecture:** Python builds a flow graph from the existing flat message list, embeds it as JSON in session HTML. A self-contained `SessionFlow` JS class renders the graph on a Canvas 2D element with force-directed layout, animated particles, and auto-play timeline. The canvas sits above the existing chat panel in a 40/60 split.

**Tech Stack:** Python 3.8+ (graph construction), Vanilla JS (Canvas 2D rendering), inline CSS (layout/responsive)

**Spec:** `docs/superpowers/specs/2026-03-24-session-flow-visualization-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `extract_stats.py` | Modify | Add `build_session_flow()`, modify `generate_session_pages()` and `_get_session_html_template()` |

All changes are in the single file `extract_stats.py` — consistent with the existing monolith approach. The session HTML template, CSS, and JS are all inline strings within this file.

**JS class method insertion:** Tasks 4-8 add methods to the `SessionFlow` class created in Task 3. Insert each new method immediately before the closing `}` of the class (before the `// Initialize if flow data` comment). Methods within the class are unordered so position doesn't matter — just keep them inside the class body.

---

### Task 1: Python — `build_session_flow()` function

**Files:**
- Modify: `extract_stats.py` (insert new function before `generate_session_pages()` at ~line 3480)

This function takes the flat message list from `extract_session_messages()` and produces the flow graph data structure.

- [ ] **Step 1: Write `build_session_flow()` function**

Insert before `generate_session_pages()` (~line 3480):

```python
def build_session_flow(messages):
    """Build a flow graph from the flat message list for Canvas visualization."""
    if not messages:
        return {"agents": [], "events": [], "edges": []}

    # Main agent is always present
    agents = [{
        "id": "main",
        "name": "Claude",
        "type": "main",
        "parent_id": None,
        "tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        "cost": 0.0,
        "tools_summary": {}
    }]
    events = []
    edges = []
    subagent_counter = 0

    # Determine session start time for relative timestamps
    first_ts = None
    for m in messages:
        ts = m.get("timestamp")
        if ts:
            if isinstance(ts, str):
                try:
                    from datetime import datetime
                    first_ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() * 1000
                except Exception:
                    first_ts = 0
            elif isinstance(ts, (int, float)):
                first_ts = float(ts)
            break
    if first_ts is None:
        first_ts = 0

    def relative_t(timestamp):
        """Convert a timestamp to milliseconds relative to session start."""
        if not timestamp:
            return 0
        if isinstance(timestamp, str):
            try:
                from datetime import datetime
                ts_ms = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp() * 1000
                return max(0, ts_ms - first_ts)
            except Exception:
                return 0
        elif isinstance(timestamp, (int, float)):
            return max(0, float(timestamp) - first_ts)
        return 0

    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        t = relative_t(msg.get("timestamp"))

        if role == "user":
            events.append({
                "type": "message",
                "agent_id": "main",
                "role": "user",
                "t": t,
                "msg_index": i
            })

        elif role == "assistant":
            # Accumulate tokens/cost to main agent
            tokens = msg.get("tokens", {})
            agents[0]["tokens"]["input"] += tokens.get("input", 0)
            agents[0]["tokens"]["output"] += tokens.get("output", 0)
            agents[0]["tokens"]["cache_read"] += tokens.get("cache_read", 0)
            agents[0]["tokens"]["cache_write"] += tokens.get("cache_write", 0)
            agents[0]["cost"] += msg.get("cost", 0.0)

            events.append({
                "type": "message",
                "agent_id": "main",
                "role": "assistant",
                "t": t,
                "msg_index": i
            })

            # Process tools
            for tool in msg.get("tools", []):
                tool_name = tool.get("name", "")
                # Track in tools_summary
                agents[0]["tools_summary"][tool_name] = agents[0]["tools_summary"].get(tool_name, 0) + 1

                if tool_name == "Agent":
                    # Create sub-agent node
                    agent_id = f"subagent-{subagent_counter}"
                    subagent_counter += 1
                    agents.append({
                        "id": agent_id,
                        "name": tool.get("detail", "Sub-agent")[:80],
                        "type": tool.get("agent_type", "general-purpose"),
                        "parent_id": "main",
                        "tokens": None,
                        "cost": None,
                        "tools_summary": {}
                    })
                    edges.append({
                        "from": "main",
                        "to": agent_id,
                        "type": "dispatch"
                    })
                    events.append({
                        "type": "agent_spawn",
                        "agent_id": agent_id,
                        "parent_id": "main",
                        "t": t,
                        "msg_index": i
                    })
                else:
                    events.append({
                        "type": "tool_call",
                        "agent_id": "main",
                        "tool": tool_name,
                        "detail": tool.get("detail", "")[:120],
                        "t": t,
                        "msg_index": i
                    })

        elif role == "compaction":
            events.append({
                "type": "compaction",
                "agent_id": "main",
                "t": t,
                "msg_index": i
            })

        elif role == "hook":
            events.append({
                "type": "hook",
                "agent_id": "main",
                "hook_name": msg.get("hook_name", ""),
                "t": t,
                "msg_index": i
            })

    # Sort events by time
    events.sort(key=lambda e: e["t"])

    return {"agents": agents, "events": events, "edges": edges}
```

- [ ] **Step 2: Integrate into `generate_session_pages()`**

In `generate_session_pages()` (~line 3490), after `messages = extract_session_messages(sid, project_dir)`, add:

```python
        flow_data = build_session_flow(messages)
```

Then in the template replacement section (~line 3500-3502), add:

```python
        flow_json = json.dumps(flow_data, ensure_ascii=False, separators=(',', ':'))
        html = html.replace('"__FLOW_DATA__"', flow_json)
```

- [ ] **Step 3: Add `__FLOW_DATA__` placeholder to template**

In `_get_session_html_template()`, in the JavaScript section (after the existing `const S = "__SESSION_DATA__";` at ~line 3616), add:

```javascript
const FLOW = "__FLOW_DATA__";
```

- [ ] **Step 4: Verify data generation**

Run the script and check that a generated session HTML contains valid FLOW data:

```bash
cd /home/andie/projects/claude-stats && python3 extract_stats.py
grep -o 'const FLOW = {[^}]*' public/sessions/*.html | head -5
```

Expected: JSON objects with `agents`, `events`, `edges` keys.

- [ ] **Step 5: Commit**

```bash
git add extract_stats.py
git commit -m "feat(flow): add build_session_flow() graph construction"
```

---

### Task 2: HTML/CSS — Layout restructure and canvas container

**Files:**
- Modify: `extract_stats.py` — `_get_session_html_template()` CSS and HTML sections

Restructure the left column from a single `.chat-panel` to a `.left-column` with flow canvas above and chat below.

- [ ] **Step 1: Add CSS for flow container and left-column layout**

In the CSS section, first modify `.chat-panel` at line 3542 — remove `max-height` (the parent `.left-column` now controls height):

Change:
```css
.chat-panel { padding:0 0 20px 0; max-height:calc(100vh - 180px); overflow-y:auto; border-right:1px solid var(--border); }
```
To:
```css
.chat-panel { padding:0 0 20px 0; flex:1; overflow-y:auto; border-right:1px solid var(--border); }
```

Then after the `.chat-panel` styles, add:

```css
.left-column{display:flex;flex-direction:column;max-height:calc(100vh - 180px);overflow:hidden}
.flow-container{position:relative;height:40%;min-height:200px;background:#0a0a0f;border-bottom:1px solid #1a1a2e}
.flow-container canvas{width:100%;height:100%;display:block}
.flow-toolbar{position:absolute;top:8px;left:8px;display:flex;gap:6px;z-index:10}
.flow-toolbar button{background:rgba(10,10,15,0.8);color:#8888aa;border:1px solid #1a1a2e;border-radius:4px;padding:4px 10px;cursor:pointer;font-size:11px;backdrop-filter:blur(4px)}
.flow-toolbar button:hover{color:#00d4ff;border-color:#00d4ff40}
.flow-toolbar button.active{color:#00d4ff;border-color:#00d4ff60}
.flow-toolbar .speed-btn{min-width:32px;text-align:center}
.flow-fitall{position:absolute;top:8px;right:8px;z-index:10}
.flow-fitall button{background:rgba(10,10,15,0.8);color:#8888aa;border:1px solid #1a1a2e;border-radius:4px;padding:4px 10px;cursor:pointer;font-size:11px}
.flow-fitall button:hover{color:#00d4ff;border-color:#00d4ff40}
.flow-progress{position:absolute;bottom:0;left:0;right:0;height:3px;background:#0a0a0f;z-index:10;cursor:pointer}
.flow-progress-bar{height:100%;background:linear-gradient(90deg,#00d4ff,#ff00aa);width:0%;transition:width 0.1s}
.flow-tooltip{position:absolute;display:none;background:rgba(10,10,15,0.95);border:1px solid #00d4ff40;border-radius:6px;padding:8px 12px;color:#ccc;font-size:11px;pointer-events:none;z-index:20;max-width:280px;backdrop-filter:blur(8px)}
.flow-toggle{display:none;width:100%;padding:8px;background:#12121f;color:#8888aa;border:none;border-bottom:1px solid #1a1a2e;cursor:pointer;font-size:12px}
.flow-toggle:hover{color:#00d4ff;background:#15152a}
```

- [ ] **Step 2: Update responsive CSS**

In the media query for <1000px (~line 3588), add:

```css
.flow-container{display:none}
.flow-container.visible{display:block;height:50%}
.flow-toggle{display:block}
```

Add a new breakpoint:

```css
@media(min-width:1000px) and (max-width:1400px){.flow-container{height:35%}}
```

- [ ] **Step 3: Restructure HTML — wrap chat in left-column**

At line 3600-3614, replace the exact block:

```
<div class="main-layout">
  <div class="chat-panel">
    <div class="chat-toolbar">
      <div class="filter-group">
        <button class="filter-btn active" data-filter="all">All</button>
        <button class="filter-btn" data-filter="user">User</button>
        <button class="filter-btn" data-filter="assistant">Agent</button>
        <button class="filter-btn" data-filter="agent-dispatch">Subagents</button>
      </div>
      <button class="copy-btn" id="copyBtn">&#128203; Copy</button>
    </div>
    <div class="chat-messages" id="chatPanel"></div>
  </div>
  <div class="sidebar" id="sidebar"></div>
</div>
```

with:

```
<div class="main-layout">
  <div class="left-column">
    <div class="flow-container">
      <canvas id="flow-canvas"></canvas>
      <div class="flow-toolbar">
        <button id="flow-play" class="active" title="Play/Pause">&#9654;</button>
        <button class="speed-btn active" data-speed="1">1x</button>
        <button class="speed-btn" data-speed="2">2x</button>
        <button class="speed-btn" data-speed="5">5x</button>
        <button class="speed-btn" data-speed="0" title="Skip to end">&#9199;</button>
      </div>
      <div class="flow-fitall"><button id="flow-fit" title="Fit all nodes">&#8982;</button></div>
      <div class="flow-progress"><div class="flow-progress-bar" id="flow-progress"></div></div>
      <div class="flow-tooltip" id="flow-tooltip"></div>
    </div>
    <button class="flow-toggle" id="flow-toggle">Show Flow</button>
    <div class="chat-panel">
      <div class="chat-toolbar">
        <div class="filter-group">
          <button class="filter-btn active" data-filter="all">All</button>
          <button class="filter-btn" data-filter="user">User</button>
          <button class="filter-btn" data-filter="assistant">Agent</button>
          <button class="filter-btn" data-filter="agent-dispatch">Subagents</button>
        </div>
        <button class="copy-btn" id="copyBtn">&#128203; Copy</button>
      </div>
      <div class="chat-messages" id="chatPanel"></div>
    </div>
  </div>
  <div class="sidebar" id="sidebar"></div>
</div>
```

- [ ] **Step 4: Add `id="msg-{i}"` and `id="marker-{i}"` to chat message rendering**

In the JavaScript chat rendering loop at line 3654-3689, make these exact changes:

**Line 3656** — hook marker, change:
```javascript
    chatHtml += '<div class="marker hook"><span>&#9881;</span>
```
to:
```javascript
    chatHtml += '<div class="marker hook" id="marker-'+i+'"><span>&#9881;</span>
```

**Line 3658** — compaction marker, change:
```javascript
    chatHtml += '<div class="marker compaction"><span>&#9889;</span>
```
to:
```javascript
    chatHtml += '<div class="marker compaction" id="marker-'+i+'"><span>&#9889;</span>
```

**Line 3663** — agent-dispatch marker, change:
```javascript
      chatHtml += '<div class="marker agent-dispatch agent-toggle">' +
```
to:
```javascript
      chatHtml += '<div class="marker agent-dispatch agent-toggle" id="marker-'+i+'-a">' +
```

**Line 3674** — message div, change:
```javascript
    chatHtml += '<div class="msg '+m.role+(hasAgentDispatch?' has-agent-dispatch':'')+'">' +
```
to:
```javascript
    chatHtml += '<div class="msg '+m.role+(hasAgentDispatch?' has-agent-dispatch':'')+'" id="msg-'+i+'">' +
```

- [ ] **Step 5: Verify layout**

```bash
python3 extract_stats.py
```

Open a session HTML page and verify:
- Canvas container appears above chat panel
- Chat panel still scrolls correctly
- Sidebar is unchanged
- Canvas shows black background (no JS yet)

- [ ] **Step 6: Commit**

```bash
git add extract_stats.py
git commit -m "feat(flow): add canvas container and split layout"
```

---

### Task 3: JS — Canvas setup, hex-grid background, depth particles

**Files:**
- Modify: `extract_stats.py` — JavaScript section of `_get_session_html_template()`

Build the `SessionFlow` class shell with background rendering.

- [ ] **Step 1: Write SessionFlow class — constructor, canvas setup, background**

Add after the existing JavaScript in the template (before `</script>`). This is the foundation class with hex-grid and depth particles:

```javascript
class SessionFlow {
  constructor(canvas, flowData, chatContainer) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.flow = flowData;
    this.chat = chatContainer;
    this.dpr = window.devicePixelRatio || 1;
    this.W = 0; this.H = 0;
    // Camera
    this.cam = {x:0, y:0, scale:1, tx:0, ty:0, ts:1, vx:0, vy:0};
    // Nodes & edges (populated later)
    this.nodes = []; this.edges = []; this.toolNodes = [];
    // Particles
    this.bgParticles = [];
    this.edgeParticles = [];
    // Effects queue
    this.effects = [];
    // Interaction state
    this.hovered = null; this.selected = null;
    this.dragging = null; this.panning = false;
    this.panStart = {x:0,y:0}; this.panCamStart = {x:0,y:0};
    this.userOverride = false;
    // Auto-play state
    this.playing = true; this.playSpeed = 1;
    this.playTime = 0; this.playIndex = 0;
    this.playDone = false;
    // Sprite cache
    this.sprites = {};
    // Hex grid params
    this.hexSize = 30;
    // Init
    this._resize();
    this._initBgParticles(60);
    this._preRenderSprites();
    this._bindEvents();
    this._raf();
  }

  _resize() {
    const r = this.canvas.parentElement.getBoundingClientRect();
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
      ['glow', '0,212,255'],
      ['glowOrange', '255,136,0'],
      ['glowMagenta', '255,0,170'],
      ['glowGreen', '0,255,136']
    ];
    for (const [name, rgb] of colors) {
      const c = document.createElement('canvas');
      c.width = sz; c.height = sz;
      const g = c.getContext('2d');
      const gr = g.createRadialGradient(sz/2,sz/2,0,sz/2,sz/2,sz/2);
      gr.addColorStop(0, 'rgba(255,255,255,0.9)');
      gr.addColorStop(0.3, `rgba(${rgb},0.4)`);
      gr.addColorStop(1, `rgba(${rgb},0)`);
      g.fillStyle = gr; g.fillRect(0,0,sz,sz);
      this.sprites[name] = c;
    }
  }

  // --- Coordinate transforms ---
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

  // --- Drawing helpers ---
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

  // --- Background ---
  _drawHexGrid(ctx) {
    const s = this.hexSize;
    const w = s * Math.sqrt(3), h = s * 1.5;
    const tl = this.screenToWorld(0, 0);
    const br = this.screenToWorld(this.W, this.H);
    const startCol = Math.floor(tl.x / w) - 1;
    const endCol = Math.ceil(br.x / w) + 1;
    const startRow = Math.floor(tl.y / h) - 1;
    const endRow = Math.ceil(br.y / h) + 1;

    ctx.strokeStyle = 'rgba(30,30,60,0.3)';
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
      p.x += p.vx; p.y += p.vy;
      const sc = this.worldToScreen(p.x, p.y);
      ctx.globalAlpha = p.a;
      ctx.fillStyle = '#4444aa';
      ctx.beginPath();
      ctx.arc(sc.x, sc.y, p.r * this.cam.scale, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  _drawBackground(ctx) {
    ctx.fillStyle = '#0a0a0f';
    ctx.fillRect(0, 0, this.W, this.H);
    this._drawHexGrid(ctx);
    this._drawBgParticles(ctx);
  }

  // --- Main loop ---
  _raf() {
    const now = performance.now();
    const dt = this._lastFrame ? (now - this._lastFrame) / 1000 : 0.016;
    this._lastFrame = now;
    this._resize();
    this.ctx.clearRect(0, 0, this.W, this.H);
    this._drawBackground(this.ctx);
    // (Later: camera lerp, simulation, edges, nodes, effects, playback)
    requestAnimationFrame(() => this._raf());
  }

  _bindEvents() {
    window.addEventListener('resize', () => this._resize());
    // (Later: mouse/wheel events)
  }
}

// Initialize if flow data is present
if (FLOW && FLOW.agents && FLOW.agents.length > 0) {
  const fc = document.getElementById('flow-canvas');
  const cp = document.querySelector('.chat-panel');
  if (fc && cp) {
    window._sessionFlow = new SessionFlow(fc, FLOW, cp);
  }
}
```

- [ ] **Step 2: Verify background renders**

```bash
python3 extract_stats.py
```

Open a session page. The canvas should show:
- Dark background (#0a0a0f)
- Subtle hex-grid lines
- Slowly drifting background particles

- [ ] **Step 3: Commit**

```bash
git add extract_stats.py
git commit -m "feat(flow): canvas setup with hex-grid background and depth particles"
```

---

### Task 4: JS — Force-directed layout engine and node initialization

**Files:**
- Modify: `extract_stats.py` — SessionFlow class

Add force simulation and node/edge initialization from flow data.

- [ ] **Step 1: Add node and edge initialization methods**

Add to SessionFlow class:

```javascript
  _initGraph() {
    const agents = this.flow.agents || [];
    const flowEdges = this.flow.edges || [];
    this.nodes = [];
    this.edges = [];
    this.toolNodes = [];
    const nodeMap = {};

    // Create agent nodes
    agents.forEach((a, i) => {
      const node = {
        id: a.id, name: a.name, type: a.type === 'main' ? 'main' : 'subagent',
        parentId: a.parent_id, data: a,
        x: (Math.random() - 0.5) * 200, y: (Math.random() - 0.5) * 200,
        vx: 0, vy: 0, fx: null, fy: null,
        r: a.type === 'main' ? 50 : 35,
        color: a.type === 'main' ? '#00d4ff' : '#ff00aa',
        opacity: 0, targetOpacity: 0,
        scanPhase: Math.random() * Math.PI * 2,
        glowPulse: Math.random() * Math.PI * 2
      };
      this.nodes.push(node);
      nodeMap[a.id] = node;
    });

    // Create tool nodes from each agent's tools_summary
    agents.forEach(a => {
      const parent = nodeMap[a.id];
      if (!parent) return;
      const tools = a.tools_summary || {};
      Object.entries(tools).forEach(([name, count]) => {
        if (name === 'Agent') return;
        const tn = {
          id: `${a.id}-tool-${name}`, name: name, type: 'tool',
          parentId: a.id, count: count,
          x: parent.x + (Math.random() - 0.5) * 100,
          y: parent.y + (Math.random() - 0.5) * 100,
          vx: 0, vy: 0, fx: null, fy: null,
          r: 20, color: '#ff8800',
          opacity: 0, targetOpacity: 0,
          glowPulse: Math.random() * Math.PI * 2
        };
        this.toolNodes.push(tn);
        nodeMap[tn.id] = tn;
        this.edges.push({from: parent, to: tn, type: 'tool', particles: []});
      });
    });

    // Create dispatch edges
    flowEdges.forEach(e => {
      const from = nodeMap[e.from], to = nodeMap[e.to];
      if (from && to) {
        this.edges.push({from, to, type: 'dispatch', particles: []});
      }
    });

    this.allNodes = [...this.nodes, ...this.toolNodes];
  }
```

- [ ] **Step 2: Add force simulation**

Add to SessionFlow class:

```javascript
  _stepSimulation() {
    const nodes = this.allNodes.filter(n => n.opacity > 0.01);
    if (nodes.length === 0) return;
    const CHARGE = -800, LINK_DIST = 250, TOOL_DIST = 120;
    const CENTER = 0.03, DECAY = 0.4, COLLISION = 20;

    // Charge repulsion (all pairs)
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

    // Link attraction
    for (const e of this.edges) {
      if (e.from.opacity < 0.01 || e.to.opacity < 0.01) continue;
      const dx = e.to.x - e.from.x, dy = e.to.y - e.from.y;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const target = e.type === 'tool' ? TOOL_DIST : LINK_DIST;
      const f = (d - target) * 0.05;
      const fx = dx / d * f, fy = dy / d * f;
      e.from.vx += fx; e.from.vy += fy;
      e.to.vx -= fx; e.to.vy -= fy;
    }

    // Center gravity
    for (const n of nodes) {
      n.vx -= n.x * CENTER;
      n.vy -= n.y * CENTER;
    }

    // Apply velocity + decay
    let totalV = 0;
    for (const n of nodes) {
      if (n.fx !== null) { n.x = n.fx; n.y = n.fy; n.vx = 0; n.vy = 0; continue; }
      n.vx *= DECAY; n.vy *= DECAY;
      n.x += n.vx; n.y += n.vy;
      totalV += Math.abs(n.vx) + Math.abs(n.vy);
    }

    // Collision
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
```

- [ ] **Step 3: Wire into constructor and render loop**

In constructor, after `this._initBgParticles(60)`:
```javascript
    this._initGraph();
    if (!this.flow.events || this.flow.events.length === 0) {
      this.allNodes.forEach(n => { n.opacity = 1; n.targetOpacity = 1; });
      this.playDone = true;
    }
```

In `_raf()`, after `this._drawBackground(this.ctx)`:
```javascript
    if (!this._simSettled) this._stepSimulation();
    for (const n of this.allNodes) {
      n.opacity += (n.targetOpacity - n.opacity) * 0.08;
    }
```

- [ ] **Step 4: Add temporary debug dots and verify simulation**

Add to `_raf()` temporarily to verify:

```javascript
    for (const n of this.allNodes) {
      if (n.opacity < 0.01) continue;
      const s = this.worldToScreen(n.x, n.y);
      this.ctx.fillStyle = n.color;
      this.ctx.globalAlpha = n.opacity;
      this.ctx.beginPath();
      this.ctx.arc(s.x, s.y, n.r * this.cam.scale * 0.3, 0, Math.PI*2);
      this.ctx.fill();
    }
    this.ctx.globalAlpha = 1;
```

```bash
python3 extract_stats.py
```

Open a session with sub-agents. Dots should appear and settle. Remove debug code after verifying.

- [ ] **Step 5: Commit**

```bash
git add extract_stats.py
git commit -m "feat(flow): force-directed layout engine with node/edge init"
```

---

### Task 5: JS — Node rendering (hexagons, diamonds, glow, scanlines)

**Files:**
- Modify: `extract_stats.py` — SessionFlow class

Replace the debug dots with proper holographic node rendering.

- [ ] **Step 1: Write `_drawNodes()` method**

```javascript
  _drawNodes(ctx) {
    const t = performance.now() / 1000;

    // Draw tool nodes first (behind agents)
    for (const n of this.toolNodes) {
      if (n.opacity < 0.05) continue;
      const s = this.worldToScreen(n.x, n.y);
      const r = n.r * this.cam.scale;
      ctx.globalAlpha = n.opacity;

      // Glow
      ctx.save();
      ctx.shadowColor = n.color;
      ctx.shadowBlur = 15 * this.cam.scale;
      this._diamondPath(ctx, s.x, s.y, r);
      ctx.fillStyle = 'rgba(255,136,0,0.15)';
      ctx.fill();
      ctx.restore();

      // Diamond outline
      this._diamondPath(ctx, s.x, s.y, r);
      ctx.strokeStyle = n.color;
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Label
      if (r > 8) {
        ctx.fillStyle = '#fff';
        ctx.font = Math.max(9, r * 0.5) + 'px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const label = n.count > 1 ? n.name + ' x' + n.count : n.name;
        ctx.fillText(label, s.x, s.y + r + 12);
      }
    }

    // Draw agent nodes
    for (const n of this.nodes) {
      if (n.opacity < 0.05) continue;
      const s = this.worldToScreen(n.x, n.y);
      const r = n.r * this.cam.scale;
      ctx.globalAlpha = n.opacity;

      // Outer glow (multiple passes for bloom effect)
      ctx.save();
      ctx.shadowColor = n.color;
      ctx.shadowBlur = 25 * this.cam.scale;
      this._hexPath(ctx, s.x, s.y, r * 1.05);
      ctx.fillStyle = n.color + '10';
      ctx.fill(); ctx.fill();
      ctx.restore();

      // Hexagon fill
      this._hexPath(ctx, s.x, s.y, r);
      ctx.fillStyle = '#0d0d1a';
      ctx.fill();

      // Scanline effect
      ctx.save();
      this._hexPath(ctx, s.x, s.y, r);
      ctx.clip();
      const scanY = s.y - r + ((t * 40 + n.scanPhase * 50) % (r * 2));
      const scanGrad = ctx.createLinearGradient(s.x, scanY - 20, s.x, scanY + 20);
      scanGrad.addColorStop(0, 'transparent');
      scanGrad.addColorStop(0.5, n.color + '15');
      scanGrad.addColorStop(1, 'transparent');
      ctx.fillStyle = scanGrad;
      ctx.fillRect(s.x - r, s.y - r, r * 2, r * 2);
      ctx.restore();

      // Hexagon border
      this._hexPath(ctx, s.x, s.y, r);
      ctx.strokeStyle = n.color + '80';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Inner glow ring (pulsing)
      const pulse = 0.6 + Math.sin(t * 1.5 + n.glowPulse) * 0.4;
      this._hexPath(ctx, s.x, s.y, r * 0.85);
      const pulseHex = Math.round(pulse * 40).toString(16).padStart(2,'0');
      ctx.strokeStyle = n.color + pulseHex;
      ctx.lineWidth = 1;
      ctx.stroke();

      // Center label
      if (r > 15) {
        ctx.fillStyle = '#fff';
        ctx.font = 'bold ' + Math.max(10, r * 0.28) + 'px monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const icon = n.type === 'main' ? '\u2726' : n.data.type.charAt(0).toUpperCase();
        ctx.fillText(icon, s.x, s.y - 2);
        ctx.font = Math.max(9, r * 0.22) + 'px monospace';
        ctx.fillStyle = n.color;
        const name = n.name.length > 18 ? n.name.slice(0,16) + '..' : n.name;
        ctx.fillText(name, s.x, s.y + r + 14);
      }

      // Highlight ring if selected/hovered
      if (this.selected === n || this.hovered === n) {
        this._hexPath(ctx, s.x, s.y, r + 4);
        ctx.strokeStyle = '#ffffff60';
        ctx.lineWidth = 2;
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;
  }
```

- [ ] **Step 2: Wire into render loop**

In `_raf()`, replace the debug dot drawing with:

```javascript
    this._drawNodes(this.ctx);
```

- [ ] **Step 3: Verify hexagons render**

```bash
python3 extract_stats.py
```

Open a session page. Should see:
- Large cyan hexagon for main agent with scanline animation and glow
- Magenta hexagons for sub-agents (if any)
- Orange diamonds for tool clusters
- Labels below each node
- Pulsing inner glow ring

- [ ] **Step 4: Commit**

```bash
git add extract_stats.py
git commit -m "feat(flow): holographic hexagon and diamond node rendering"
```

---

### Task 6: JS — Edge rendering (tapered Beziers, particles)

**Files:**
- Modify: `extract_stats.py` — SessionFlow class

- [ ] **Step 1: Write edge and particle methods**

```javascript
  _cubicBezier(t, p0, p1, p2, p3) {
    const mt = 1 - t;
    return {
      x: mt*mt*mt*p0.x + 3*mt*mt*t*p1.x + 3*mt*t*t*p2.x + t*t*t*p3.x,
      y: mt*mt*mt*p0.y + 3*mt*mt*t*p1.y + 3*mt*t*t*p2.y + t*t*t*p3.y
    };
  }

  _initEdgeParticles(edge) {
    const n = edge.type === 'dispatch' ? 6 : 3;
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

      // Control points (perpendicular offset)
      const dx = st.x - sf.x, dy = st.y - sf.y;
      const d = Math.sqrt(dx*dx + dy*dy) || 1;
      const nx = -dy/d, ny = dx/d;
      const off = d * 0.15;
      const cp1 = {x: sf.x + dx*0.3 + nx*off, y: sf.y + dy*0.3 + ny*off};
      const cp2 = {x: sf.x + dx*0.7 + nx*off, y: sf.y + dy*0.7 + ny*off};

      // Base edge (dim)
      ctx.globalAlpha = alpha * 0.3;
      ctx.beginPath();
      ctx.moveTo(sf.x, sf.y);
      ctx.bezierCurveTo(cp1.x, cp1.y, cp2.x, cp2.y, st.x, st.y);
      ctx.strokeStyle = e.type === 'dispatch' ? '#00d4ff' : '#ff8800';
      ctx.lineWidth = e.type === 'dispatch' ? 2 : 1.5;
      ctx.stroke();

      // Glow edge (additive)
      ctx.save();
      ctx.globalCompositeOperation = 'lighter';
      ctx.globalAlpha = alpha * 0.15;
      ctx.beginPath();
      ctx.moveTo(sf.x, sf.y);
      ctx.bezierCurveTo(cp1.x, cp1.y, cp2.x, cp2.y, st.x, st.y);
      ctx.strokeStyle = e.type === 'dispatch' ? '#00d4ff' : '#ff8800';
      ctx.lineWidth = 4;
      ctx.stroke();
      ctx.restore();

      // Particles
      if (e.particles.length === 0) this._initEdgeParticles(e);
      const sprite = e.type === 'dispatch' ? this.sprites.glow : this.sprites.glowOrange;
      ctx.globalAlpha = alpha;
      for (const p of e.particles) {
        p.t += p.speed * (this.hovered === fa || this.hovered === ta ? 2.5 : 1);
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

        // Comet trail
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
    ctx.globalAlpha = 1;
  }
```

- [ ] **Step 2: Wire into render loop**

In `_raf()`, add before `_drawNodes()`:

```javascript
    this._drawEdges(this.ctx);
```

- [ ] **Step 3: Verify edges render**

```bash
python3 extract_stats.py
```

Open a session with sub-agents or multiple tools. Should see:
- Curved glowing lines connecting agents to sub-agents and tools
- Small bright particles flowing along the curves with comet trails

- [ ] **Step 4: Commit**

```bash
git add extract_stats.py
git commit -m "feat(flow): tapered Bezier edges with particle system"
```

---

### Task 7: JS — Interaction (click, hover, pan, zoom, auto-fit)

**Files:**
- Modify: `extract_stats.py` — SessionFlow class

- [ ] **Step 1: Write hit testing**

```javascript
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
```

- [ ] **Step 2: Replace `_bindEvents()` with full interaction handling**

```javascript
  _bindEvents() {
    const c = this.canvas;
    window.addEventListener('resize', () => this._resize());

    c.addEventListener('wheel', (e) => {
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

    // Track drag distance to distinguish click from drag
    this._dragDist = 0;
    this._mouseDownPos = {x:0, y:0};

    c.addEventListener('mousedown', (e) => {
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

    c.addEventListener('mousemove', (e) => {
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      // Accumulate drag distance
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
        // Pan inertia: track velocity
        this.cam.vx = -dx * 0.1; this.cam.vy = -dy * 0.1;
        this.userOverride = true;
      } else {
        const hit = this._hitTest(mx, my);
        this.hovered = hit;
        c.style.cursor = hit ? 'pointer' : 'grab';
        this._updateTooltip(mx, my, hit);
      }
    });

    c.addEventListener('mouseup', () => {
      if (this.dragging) {
        this.dragging.fx = null; this.dragging.fy = null;
        this._simSettled = false;
        this.dragging = null;
      }
      if (this.panning) {
        // Apply pan inertia
        this.cam.tx = this.cam.x + this.cam.vx * 5;
        this.cam.ty = this.cam.y + this.cam.vy * 5;
      }
      this.panning = false;
    });

    c.addEventListener('mouseleave', () => {
      this.hovered = null;
      this._hideTooltip();
    });

    c.addEventListener('click', (e) => {
      // Skip click if user was dragging/panning (moved > 5px)
      if (this._dragDist > 5) return;
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const hit = this._hitTest(mx, my);
      this.selected = hit;
      if (hit) this._scrollToMessage(hit);
    });

    const fitBtn = document.getElementById('flow-fit');
    if (fitBtn) fitBtn.addEventListener('click', () => this._fitAll());
  }
```

- [ ] **Step 3: Write tooltip, scroll, and camera methods**

```javascript
  _updateTooltip(mx, my, node) {
    const el = document.getElementById('flow-tooltip');
    if (!el) return;
    if (!node) { el.style.display = 'none'; return; }
    // Build tooltip using safe DOM methods
    el.textContent = '';
    const h = document.createElement('h4');
    h.style.cssText = 'color:#00d4ff;margin:0 0 4px;font-size:12px';
    h.textContent = node.name;
    el.appendChild(h);
    const addRow = (label, val) => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;justify-content:space-between;gap:12px';
      const lbl = document.createElement('span');
      lbl.style.color = '#666'; lbl.textContent = label;
      const v = document.createElement('span');
      v.style.color = '#fff'; v.textContent = val;
      row.appendChild(lbl); row.appendChild(v);
      el.appendChild(row);
    };
    if (node.type === 'tool') {
      addRow('Calls', String(node.count));
    } else {
      const d = node.data || {};
      addRow('Type', d.type || 'main');
      if (d.tokens) addRow('Tokens', ((d.tokens.input+d.tokens.output)/1000).toFixed(1) + 'K');
      if (d.cost != null) addRow('Cost', '$' + d.cost.toFixed(4));
    }
    el.style.display = 'block';
    el.style.left = (mx + 15) + 'px';
    el.style.top = (my + 15) + 'px';
  }

  _hideTooltip() {
    const el = document.getElementById('flow-tooltip');
    if (el) el.style.display = 'none';
  }

  _scrollToMessage(node) {
    // For tool nodes, find the specific tool_call event matching this tool name
    var evt;
    if (node.type === 'tool') {
      evt = this.flow.events.find(e => e.type === 'tool_call' && e.tool === node.name && e.agent_id === node.parentId);
    }
    // For agent nodes, find first event for this agent
    if (!evt) {
      evt = this.flow.events.find(e => e.agent_id === node.id);
    }
    if (!evt) return;
    const msgEl = document.getElementById('msg-' + evt.msg_index) || document.getElementById('marker-' + evt.msg_index);
    if (msgEl) {
      msgEl.scrollIntoView({behavior: 'smooth', block: 'center'});
      msgEl.style.outline = '2px solid #00d4ff';
      setTimeout(() => { msgEl.style.outline = ''; }, 2000);
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
```

- [ ] **Step 4: Add camera LERP to render loop**

In `_raf()`, add before drawing:

```javascript
    // Camera LERP
    this.cam.x += (this.cam.tx - this.cam.x) * 0.08;
    this.cam.y += (this.cam.ty - this.cam.y) * 0.08;
    this.cam.scale += (this.cam.ts - this.cam.scale) * 0.08;
```

- [ ] **Step 5: Add bidirectional chat-to-canvas linking**

After the existing chat rendering loop, add:

```javascript
document.querySelectorAll('.msg,.marker').forEach(function(el) {
  el.addEventListener('click', function() {
    if (!window._sessionFlow) return;
    var idx = parseInt((el.id || '').replace(/\D/g, ''));
    if (isNaN(idx)) return;
    var sf = window._sessionFlow;
    var evt = sf.flow.events.find(function(e) { return e.msg_index === idx; });
    if (!evt) return;
    var node = sf.allNodes.find(function(n) { return n.id === evt.agent_id; });
    if (node) {
      sf.selected = node;
      sf.effects.push({type:'pulse', node:node, t:0, dur:1.0});
    }
  });
});
```

- [ ] **Step 6: Verify interactions**

```bash
python3 extract_stats.py
```

Test: hover (tooltip), click (chat scroll), wheel (zoom), drag (pan), fit-all button, chat click (node pulse).

- [ ] **Step 7: Commit**

```bash
git add extract_stats.py
git commit -m "feat(flow): interaction system - click, hover, pan, zoom, fit-all"
```

---

### Task 8: JS — Auto-play timeline with effects

**Files:**
- Modify: `extract_stats.py` — SessionFlow class

- [ ] **Step 1: Write auto-play and effects methods**

```javascript
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
    var nodeMap = {};
    this.allNodes.forEach(function(n) { nodeMap[n.id] = n; });
    var agent, toolNode, toolId;
    switch (evt.type) {
      case 'message':
        agent = nodeMap[evt.agent_id];
        if (agent) {
          agent.targetOpacity = 1;
          this._lastActiveNode = agent;
          if (evt.role === 'user')
            this.effects.push({type:'pulse', node:agent, t:0, dur:0.8, color:'#00ff88'});
        }
        break;
      case 'tool_call':
        toolId = evt.agent_id + '-tool-' + evt.tool;
        toolNode = nodeMap[toolId];
        if (toolNode) {
          toolNode.targetOpacity = 1;
          this.effects.push({type:'spawn', node:toolNode, t:0, dur:0.6});
        }
        agent = nodeMap[evt.agent_id];
        if (agent) { agent.targetOpacity = 1; this._lastActiveNode = agent; }
        break;
      case 'agent_spawn':
        var newAgent = nodeMap[evt.agent_id];
        if (newAgent) {
          newAgent.targetOpacity = 1;
          this.effects.push({type:'spawn', node:newAgent, t:0, dur:1.0});
          this._lastActiveNode = newAgent;
          this._simSettled = false;
        }
        break;
      case 'compaction':
        agent = nodeMap[evt.agent_id];
        if (agent) this.effects.push({type:'flash', node:agent, t:0, dur:0.5, color:'#ff3344'});
        break;
      case 'hook':
        agent = nodeMap[evt.agent_id];
        if (agent) this.effects.push({type:'flash', node:agent, t:0, dur:0.4, color:'#ffcc00'});
        break;
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
    var prog = document.getElementById('flow-progress');
    if (prog) {
      var maxCompressed = this._compressTime(maxT, events);
      prog.style.width = Math.min(100, (this.playTime / maxCompressed) * 100) + '%';
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
    this.allNodes.forEach(function(n) { n.opacity = 1; n.targetOpacity = 1; });
    this.playDone = true;
    this.playIndex = (this.flow.events || []).length;
    var prog = document.getElementById('flow-progress');
    if (prog) prog.style.width = '100%';
    this._fitAll();
  }

  _drawEffects(ctx) {
    var toRemove = [];
    for (var i = 0; i < this.effects.length; i++) {
      var fx = this.effects[i];
      fx.t += 0.016;
      var progress = fx.t / fx.dur;
      if (progress > 1) { toRemove.push(i); continue; }
      var n = fx.node;
      if (!n || n.opacity < 0.01) continue;
      var s = this.worldToScreen(n.x, n.y);
      var r = n.r * this.cam.scale;
      var color = fx.color || n.color;
      if (fx.type === 'spawn') {
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
      } else if (fx.type === 'pulse') {
        var pulseR = r + Math.sin(progress * Math.PI) * 15;
        ctx.globalAlpha = (1 - progress) * 0.5;
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        this._hexPath(ctx, s.x, s.y, pulseR);
        ctx.stroke();
      } else if (fx.type === 'flash') {
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
```

- [ ] **Step 2: Wire playback and effects into render loop**

In `_raf()`:
```javascript
    this._stepPlayback(dt);
    // After drawNodes:
    this._drawEffects(this.ctx);
```

- [ ] **Step 3: Bind toolbar buttons**

Add to `_bindEvents()`:

```javascript
    // Play/Pause
    var self = this;
    var playBtn = document.getElementById('flow-play');
    if (playBtn) playBtn.addEventListener('click', function() {
      self.playing = !self.playing;
      playBtn.textContent = self.playing ? '\u25B6' : '\u23F8';
    });

    // Speed buttons
    document.querySelectorAll('.speed-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var speed = parseInt(btn.dataset.speed);
        if (speed === 0) { self._skipToEnd(); return; }
        self.playSpeed = speed;
        document.querySelectorAll('.speed-btn').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
      });
    });

    // Progress bar seek
    var progBar = document.querySelector('.flow-progress');
    if (progBar) progBar.addEventListener('click', function(e) {
      var rect = progBar.getBoundingClientRect();
      var pct = (e.clientX - rect.left) / rect.width;
      var events = self.flow.events || [];
      if (events.length === 0) return;
      var maxT = self._compressTime(events[events.length - 1].t, events);
      self.playTime = pct * maxT;
      self.playIndex = 0;
      self.allNodes.forEach(function(n) { n.opacity = 0; n.targetOpacity = 0; });
      self.effects = [];
      self._stepPlayback(0);
    });
```

- [ ] **Step 4: Start auto-play in constructor**

After `_initGraph()`:

```javascript
    if (this.nodes.length > 0) {
      this.nodes[0].targetOpacity = 1;
      this._lastActiveNode = this.nodes[0];
      this.effects.push({type:'spawn', node:this.nodes[0], t:0, dur:1.0});
    }
    this._fitAll();
```

- [ ] **Step 5: Verify auto-play**

```bash
python3 extract_stats.py
```

Open a session page:
- Main agent fades in with spawn ring
- Events replay: tools appear, sub-agents spawn, green/red/yellow flashes
- Progress bar advances, speed buttons work, skip jumps to end

- [ ] **Step 6: Commit**

```bash
git add extract_stats.py
git commit -m "feat(flow): auto-play timeline with effects and toolbar controls"
```

---

### Task 9: JS — Responsive behavior and mobile toggle

**Files:**
- Modify: `extract_stats.py` — JS section

- [ ] **Step 1: Add mobile flow toggle logic**

Add after SessionFlow initialization:

```javascript
var flowToggle = document.getElementById('flow-toggle');
var flowContainer = document.querySelector('.flow-container');
if (flowToggle && flowContainer) {
  if (window.innerWidth < 1000) {
    flowContainer.style.display = 'none';
  }
  flowToggle.addEventListener('click', function() {
    var visible = flowContainer.classList.toggle('visible');
    flowContainer.style.display = visible ? 'block' : 'none';
    flowToggle.textContent = visible ? 'Hide Flow' : 'Show Flow';
    if (visible && window._sessionFlow) {
      window._sessionFlow._resize();
      window._sessionFlow._fitAll();
    }
  });
  window.addEventListener('resize', function() {
    if (window.innerWidth >= 1000) {
      flowToggle.style.display = 'none';
      flowContainer.style.display = '';
      flowContainer.classList.remove('visible');
    } else if (!flowContainer.classList.contains('visible')) {
      flowToggle.style.display = 'block';
      flowContainer.style.display = 'none';
    }
  });
}
```

- [ ] **Step 2: Verify responsive**

```bash
python3 extract_stats.py
```

Test with browser devtools responsive mode:
- < 1000px: canvas hidden, "Show Flow" button visible, toggle works
- > 1000px: canvas always visible, toggle hidden

- [ ] **Step 3: Commit**

```bash
git add extract_stats.py
git commit -m "feat(flow): responsive layout with mobile toggle"
```

---

### Task 10: Integration testing and polish

**Files:**
- Modify: `extract_stats.py` — final tweaks

- [ ] **Step 1: Test with various session types**

```bash
python3 extract_stats.py
```

Test by opening different session pages:
1. Simple session (no sub-agents, few tools) — clean main agent + tool diamonds
2. Complex session (multiple sub-agents) — hierarchy with dispatch edges
3. Session with compactions — red flashes during auto-play
4. Session with hooks — yellow flashes
5. Empty/minimal session — graceful handling

- [ ] **Step 2: Hide flow container when no meaningful flow data**

Update initialization guard:

```javascript
if (FLOW && FLOW.agents && FLOW.agents.length > 0 && FLOW.events && FLOW.events.length > 0) {
  // init SessionFlow
} else {
  var fc = document.querySelector('.flow-container');
  if (fc) fc.style.display = 'none';
}
```

- [ ] **Step 3: Performance check**

Open a large session (50+ messages). Verify:
- Canvas runs at 60fps (no visible jank)
- Force simulation settles within 2-3 seconds
- Auto-play completes without freezing

- [ ] **Step 4: Final commit**

```bash
git add extract_stats.py
git commit -m "feat(flow): integration polish and edge case handling"
```

---

## Summary

| Task | Description | Key Output |
|------|-------------|------------|
| 1 | Python graph construction | `build_session_flow()` function |
| 2 | HTML/CSS layout restructure | Split view with canvas container |
| 3 | Canvas background | Hex-grid + depth particles |
| 4 | Force-directed layout | Physics simulation + node init |
| 5 | Node rendering | Holographic hexagons + diamonds |
| 6 | Edge rendering | Tapered Beziers + particle system |
| 7 | Interaction | Click, hover, pan, zoom, fit-all, bidirectional linking |
| 8 | Auto-play | Timeline with effects + toolbar controls |
| 9 | Responsive | Mobile toggle, breakpoints |
| 10 | Polish | Edge cases, performance, final testing |
