# Session Flow Visualization — Design Spec

**Date:** 2026-03-24
**Status:** Approved
**Inspired by:** [agent-flow](https://github.com/patoles/agent-flow) (VS Code extension for Claude Code agent visualization)

## Overview

Add an interactive, animated Canvas 2D flow visualization to the session replay pages. The visualization shows the agent orchestration hierarchy, tool usage, and message flow as a force-directed graph with holographic/sci-fi aesthetics.

## Goals

- Provide a bird's-eye view of how Claude Code structured its work in a session
- Show agent hierarchy (main agent + sub-agents) and tool usage at a glance
- Look impressive and cool — holographic glow, animated particles, force-directed layout
- Integrate seamlessly with the existing chat replay below it
- No additional external dependencies (Vanilla JS, inline in generated HTML — existing highlight.js CDN usage unchanged)

## Layout Integration

### Split View

```
┌──────────────────────────────────────────────────┬──────────────┐
│                                                  │              │
│           Canvas Flow Visualization              │              │
│                (40% height)                      │   Sidebar    │
│                                                  │   (33%)      │
├──────────────────────────────────────────────────┤              │
│                                                  │   Token      │
│             Chat Message List                    │   Breakdown  │
│                (60% height)                      │              │
│                                                  │   Tools      │
│                                                  │   Models     │
│                                                  │   etc.       │
└──────────────────────────────────────────────────┴──────────────┘
```

- Flow canvas sits above the existing chat list (left column)
- Fixed 40/60 split (no resizable divider in v1 — keeps implementation simple)
- Sidebar remains unchanged on the right
- Bidirectional linking: click node → chat scrolls; click chat message → node pulses

### DOM Structure Change

The existing `.chat-panel` div (which contains toolbar + messages) gets wrapped in a new parent:

```html
<div class="left-column">
  <div class="flow-container" style="height: 40%">
    <canvas id="flow-canvas"></canvas>
    <!-- toolbar overlay is positioned absolute inside -->
  </div>
  <div class="chat-panel" style="height: 60%">
    <!-- existing toolbar + messages, unchanged -->
  </div>
</div>
```

The existing `grid-template-columns: 2fr 1fr` on `.main-layout` stays the same. The left cell just changes from `.chat-panel` to `.left-column` which uses `display: flex; flex-direction: column`.

### Responsive Behavior

- **< 1000px (mobile):** Flow canvas is hidden by default. A "Show Flow" toggle button appears above the chat panel. When toggled, canvas shows at 50% height, chat at 50%.
- **1000-1400px:** Canvas at 35% height, chat at 65% (more room for chat on smaller desktops).
- **> 1400px:** Canvas at 40%, chat at 60% (default).

### Chat Anchor IDs

Each `.msg` div in the chat list gets an `id="msg-{i}"` attribute (where `i` is the message index). Each `.marker` div gets `id="marker-{i}"`. This enables `scrollIntoView()` from canvas click handlers.

## Visual Style: Holographic / Sci-Fi

### Background
- Dark base (#0a0a0f or similar), darker than dashboard background
- Subtle animated hex-grid overlay (thin lines, low opacity)
- Depth particles (small, slow-moving dots for ambient motion)

### Color Palette
- **Cyan (#00d4ff)** — Main agent, primary glow
- **Magenta (#ff00aa)** — Sub-agents
- **Orange/Amber (#ff8800)** — Tool calls
- **Green (#00ff88)** — User message pulses
- **Red (#ff3344)** — Compaction markers
- **Yellow (#ffcc00)** — Hook markers
- **White (#ffffff)** — Text labels, highlights

### Effects
- **Glow:** Multiple `shadowBlur` passes with additive compositing (`globalCompositeOperation = 'lighter'`)
- **Scanlines:** Animated gradient overlay on hexagon nodes (moving top to bottom)
- **Particles:** Small glowing dots flowing along Bezier curves on edges
- **Spawn FX:** Expanding ring + flash when nodes appear during auto-play
- **Pulse:** Gentle scale/opacity oscillation on idle nodes

## Node Types

### Structural Nodes (persistent in graph)

| Type | Shape | Color | Size | Content |
|------|-------|-------|------|---------|
| Main Agent | Hexagon | Cyan | Large (r=50) | Claude icon or spark symbol, name label |
| Sub-Agent | Hexagon | Magenta | Medium (r=35) | Agent type badge, name label |
| Tool Call | Diamond/Rhombus | Orange | Small (r=20) | Tool icon, name. Grouped: "Read x5" |

- **Tool grouping:** Multiple calls to the same tool from one agent collapse into a single node with a count badge. Hover shows a tooltip listing individual calls (file paths, commands). No expand/collapse of nodes in v1 — keeps the force layout stable.

### Ephemeral Elements (animated, not graph nodes)

| Type | Visual | Trigger |
|------|--------|---------|
| User Message | Green glowing pulse flowing into agent node from left | Each user message in timeline |
| Compaction | Red lightning bolt marker at agent node | Context compaction event |
| Hook | Yellow gear marker at agent node | Hook fire event |

## Edges

### Types
- **Agent → Sub-Agent:** Tapered Bezier curve (thick at source, thin at target). Cyan-tinted particles flow along it.
- **Agent → Tool Cluster:** Shorter, thinner Bezier. Orange particles.

### Bezier Rendering
- Cubic Bezier with control points offset perpendicular to the straight line
- Tapered: draw two parallel curves with varying offset, fill between them
- Base layer (dim) + glow layer (bright, thinner, additive blend)

### Particle System
- N particles per edge (3-8 depending on edge importance)
- Each particle follows the cubic Bezier path with parametric t ∈ [0,1]
- Small random wobble perpendicular to path
- Comet trail: 3-5 trailing dots with decreasing opacity
- Glow: radial gradient sprite (pre-rendered to off-screen canvas for performance)

## Force-Directed Layout

### Forces
```
Charge (repulsion):  strength = -800,  all nodes push each other away
Link (attraction):   distance = 250,   connected nodes pull toward target distance
Center (gravity):    strength = 0.03,  weak pull toward canvas center
Collision:           radius = node_radius + 20,  prevent overlap
```

### Simulation
- Velocity-based with decay factor (0.4) for damping
- Runs on each frame during settling, then stops when velocity < threshold
- Re-activates when new nodes are added (during auto-play)
- Nodes can be dragged — dragged node becomes fixed, released node rejoins simulation

## Interaction

### Click
- **Agent node** → Chat scrolls to first message of this agent, node emits pulse, sidebar highlights agent stats
- **Tool node** → Chat scrolls to tool call, tooltip shows command/path detail
- **Background** → Deselect all, reset highlights
- **Chat message** → Corresponding node pulses in canvas (bidirectional)

### Hover
- **Node:** Glow intensity increases, connected edges highlight (brighter + faster particles), tooltip appears with:
  - Agent: name, type, token count, cost
  - Tool: name, detail (command/path), call count
- **Edge:** Particle speed increases briefly

### Canvas Navigation
- **Zoom:** Mouse wheel, exponential steps (0.92x / 1.08x per tick), range [0.3, 3.0]
- **Pan:** Click-drag on background, velocity-based inertia with smooth deceleration
- **Auto-fit button:** Top-right corner of canvas. Computes bounding box of all nodes + padding, LERP-animates camera to fit all nodes in view.
- **During auto-play:** Camera smoothly follows the active node (LERP toward it)
- **User override:** Once user pans/zooms manually, auto-follow disables until reset

## Auto-Play Timeline

### Sequence
1. Canvas starts empty with hex-grid background + depth particles
2. Main agent hexagon fades in with spawn effect (expanding ring + flash)
3. Events replay chronologically:
   - User messages: green pulse flows into agent
   - Tool calls: orange diamond spawns near agent with spawn FX
   - Sub-agent dispatches: new hexagon spawns, edge draws with particle animation
   - Compactions: red flash at agent
   - Hooks: yellow flash at agent
4. After last event: graph settles into static state with ambient animations (gentle particle flow, subtle glow pulse)

### Timing
- Events are spaced based on their relative timestamps
- Long pauses between events compressed to max 2 seconds (at 1x speed)
- Minimum gap between events: 0.3 seconds (at 1x speed)

### Controls (toolbar top-left of canvas)
- **Play / Pause** button
- **Speed:** 1x / 2x / 5x / Skip (skip jumps to completed static graph)
- **Progress bar:** Thin line below toolbar showing timeline position, clickable to seek

## Data Model

### Graph Construction (Python side — extract_stats.py)

Add a new function `build_session_flow(messages)` that takes the flat message list from `extract_session_messages()` and constructs a graph:

```python
session_flow = {
    "agents": [
        {
            "id": "main",
            "name": "Claude",
            "type": "main",
            "parent_id": None,
            "tokens": {"input": N, "output": N, "cache_read": N},
            "cost": 0.123,
            "tools_summary": {"Read": 5, "Edit": 3, "Bash": 2}
        },
        {
            "id": "subagent-0",
            "name": "Explore codebase",
            "type": "Explore",
            "parent_id": "main",
            "tokens": {...},
            "cost": 0.045,
            "tools_summary": {"Read": 8, "Grep": 3}
        }
    ],
    "events": [
        {"type": "message", "agent_id": "main", "role": "user", "t": 0, "msg_index": 0},
        {"type": "message", "agent_id": "main", "role": "assistant", "t": 1200, "msg_index": 1},
        {"type": "tool_call", "agent_id": "main", "tool": "Read", "detail": "src/main.py", "t": 1500, "msg_index": 1},
        {"type": "agent_spawn", "agent_id": "subagent-0", "parent_id": "main", "t": 2000, "msg_index": 2},
        {"type": "compaction", "agent_id": "main", "t": 5000, "msg_index": 10},
        {"type": "hook", "agent_id": "main", "hook_name": "pre-commit", "t": 6000, "msg_index": 12}
    ],
    "edges": [
        {"from": "main", "to": "subagent-0", "type": "dispatch"}
    ]
}
```

- `t` values are milliseconds relative to session start (for timeline positioning)
- `msg_index` links to the chat message list for bidirectional navigation
- Events are sorted chronologically

### Graph Construction Algorithm

**Agent ID generation:** Sub-agent IDs are synthetic: `subagent-{N}` where N is the zero-based index of the Agent tool_use in the message list. The JSONL data does not provide stable unique IDs for sub-agents.

**Agent attribution logic:**

1. Start with a single "main" agent.
2. Walk the message list sequentially. All messages and tool calls belong to "main" by default.
3. When an assistant message contains an `Agent` tool_use:
   - Create a new agent entry with `id = f"subagent-{counter}"`, `name` = agent description, `type` = agent_type, `parent_id` = current agent.
   - Emit an `agent_spawn` event.
   - Add an edge `{from: parent_id, to: new_agent_id, type: "dispatch"}`.
   - The sub-agent's tokens and cost are NOT attributable from the parent session's message list (sub-agents run in separate processes with their own JSONL). Set tokens/cost to `null` unless sub-agent session data is available.
4. For each assistant message: sum its tokens into the "main" agent's totals. Emit tool_call events for each tool in the message's `tools` array.
5. For compaction/hook markers: emit the corresponding event type with `agent_id = "main"`.

**Tool-to-agent edges:** The `edges` array only contains agent-to-agent dispatch links. Tool node positions and tool-to-agent edges are derived client-side from each agent's `tools_summary` dictionary.

### Embedding in HTML

The flow data is embedded as a JSON object alongside the existing session message data. Use the same placeholder replacement pattern as the existing session data:

```javascript
const FLOW = "__FLOW_DATA__";  // replaced by Python: html.replace('"__FLOW_DATA__"', flow_json)
```

## JavaScript Architecture

Single self-contained class `SessionFlow` (~2000-2500 lines), structured as:

```
SessionFlow
├── constructor(canvas, flowData, chatContainer)
├── // --- Layout ---
├── initNodes()              // create node objects from flowData.agents
├── initEdges()              // create edge objects from flowData.edges
├── stepSimulation()         // one tick of force-directed layout
├── // --- Rendering ---
├── draw()                   // main requestAnimationFrame loop
├── drawBackground()         // hex grid + depth particles
├── drawEdges()              // tapered beziers + particles
├── drawNodes()              // hexagons + diamonds + glow + scanlines
├── drawEffects()            // spawn rings, pulses, flashes
├── drawUI()                 // toolbar, progress bar, fit-all button
├── // --- Interaction ---
├── handleClick(e)           // hit detection, node selection, chat scroll
├── handleHover(e)           // tooltip, highlight
├── handleWheel(e)           // zoom
├── handleDrag(e)            // pan + node drag
├── hitTest(x, y)            // point-in-hexagon / point-in-diamond
├── // --- Camera ---
├── updateCamera()           // LERP toward target, apply inertia
├── fitAll()                 // compute bounding box, set target
├── // --- Auto-Play ---
├── startPlayback()          // begin timeline
├── stepPlayback(dt)         // advance timeline, spawn nodes/effects
├── seekTo(t)                // jump to timeline position
├── // --- Helpers ---
├── worldToScreen(x, y)      // apply camera transform
├── screenToWorld(x, y)      // inverse camera transform
├── drawHexagon(cx, cy, r)   // hexagon path helper
├── drawDiamond(cx, cy, r)   // diamond path helper
├── cubicBezier(t, p0..p3)   // bezier interpolation
└── preRenderSprites()       // cache glow sprites to off-screen canvas
```

## Performance Considerations

- **Sprite caching:** Pre-render glow gradients and particle sprites to off-screen canvases at init time
- **Text measurement cache:** Cache `measureText()` results for label rendering
- **Opacity culling:** Skip drawing elements with opacity < 0.05
- **Simulation stop:** Force simulation stops when total velocity drops below threshold (no wasted CPU on settled graphs)
- **Typical session size:** 1-5 agents, 5-30 tool nodes — performance is not a concern at this scale

## Files Modified

1. **extract_stats.py** — Add `build_session_flow()` function to construct graph data from parsed messages. Embed flow JSON in session HTML template. Add canvas container + CSS to template.
2. **No new files** — everything is inline in the generated session HTML, consistent with the existing approach.

## Out of Scope

- Real-time / live session visualization (this is post-hoc replay only)
- 3D rendering or WebGL
- Separate JS bundle or build step
- External libraries (D3, Three.js, etc.)
