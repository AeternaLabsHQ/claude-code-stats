# Design Handoff: claude.stats Dashboard Redesign (for Claude Design)

> **How to use this file.** This is a brief to paste into a new Claude Design
> project. Section 8 is the literal opening message. Sections 1-7 are the
> supporting context Claude Design needs. Attach the screenshots listed in
> Section 7. The goal is to get **2-3 distinct visual directions** for the
> dashboard - not a finished build.

---

## 1. What this product is

**claude.stats** is a self-hosted analytics dashboard for Claude Code usage. It
reads a user's local Claude Code session logs and renders a static HTML page
that breaks down cost, token consumption, activity patterns, plan value, and
deep per-session detail.

Two audiences, both real:

- **The power user (primary):** a technical person looking at their own usage.
  They *like* density - lots of numbers per screen is a feature, not a bug.
- **The self-hoster (secondary):** it ships as an open-source project on GitHub,
  so other people install and run it. First impression and legibility matter;
  the current look reads as "internal tool", and a redesign is a chance to make
  it feel like a polished product without dumbing down the data.

It is a **read-only dashboard**. No forms, no editing, no workflows - just
navigation, filtering, and reading. Privacy is a theme: the page literally warns
"contains private data, do not share publicly" and has a one-key anonymization
toggle (F2) that blanks names for screenshots.

## 2. The mandate

**Explore a fresh visual direction.** The current design (described in Section 4)
is a deliberate "terminal" aesthetic. It has served its purpose, but for this
exercise it is **fair game to challenge entirely**. Do not feel bound to it.

Please propose **2-3 distinct design languages** for the same content - for
example (illustrative, not prescriptive):

- a refined evolution of the current terminal/monospace look,
- a clean modern analytics look (think a well-made SaaS dashboard),
- something more editorial / typographic that treats the numbers as the story.

For each direction, show the **Token & API Value** tab as the hero screen
(it is the default landing tab and the densest "value" view), plus at least one
secondary screen so the system is legible across layouts.

Brand constraints are intentionally minimal - see Section 5 for the few things
that are fixed.

## 3. Hard constraints (do not optimize these away)

These are non-negotiable. The *visual language* is open; the *data scope and
capabilities* are not.

1. **Keep every chart, table, and metric.** If a panel is missing from a mockup,
   that reads as "we cut it" - we don't want anything cut. The full content
   inventory is in Section 4. You may **regroup, reprioritize, or restructure**
   how content is laid out, but the information must still have a home.
2. **Light and dark mode both required.** Show the hero screen in both. The
   current product defaults to light and switches to dark via a toggle and via
   `prefers-color-scheme`.
3. **Responsive.** Must work on desktop *and* mobile/tablet. No desktop-only
   mockups. Dense tables especially need a thought-through small-screen behavior.
4. **Models must stay visually distinguishable.** Charts color-code by model.
   There are model *families* (Opus, Sonnet, Haiku), each with multiple versions
   (e.g. Opus 4.8 / 4.7 / 4.6). Versions within a family should read as related
   but distinct. Today this is done with three color families; keep that idea
   (related-within-family, distinct-across-family) however you express it.
5. **Charts are Chart.js.** Implementation uses Chart.js, so chart *types* should
   stay within what a canvas charting lib does well (line, bar, stacked bar,
   doughnut, scatter/heatmap-as-grid). Lean into clean, standard chart forms
   rather than exotic bespoke visualizations.

## 4. Current content inventory (what must have a home)

Global chrome (persists across all tabs):

- **Top bar:** brand mark + name + version; key-value readouts USER / PLAN /
  RANGE; "hide empty sessions" checkbox; light/dark theme toggle; F2
  anonymization hint; "generated at" UTC timestamp.
- **Primary nav:** the 5 tab links; a quick-filter text input; a time-range
  selector (All / 7D / 30D / 90D / 1Y) that re-scopes the whole dashboard.
- **Footer:** version, "contains private data" warning, anonymization hint,
  GitHub link.

The 5 tabs:

**Tab 1 - Token & API Value** (default landing tab, the "what did I get" view)
- KPI strip: API EQUIVALENT (+ savings %), SESSIONS (+ avg duration), MESSAGES
  (+ per session), OUTPUT TOKENS (+ input count), CACHE HIT % (+ read count).
  This strip is the headline of the whole dashboard.
- Daily cost chart (full-width line/bar).
- Cumulative cost chart (full-width line).
- Token-type breakdown chart + a per-model detail table (model, API value,
  output, input, cache read, API calls) with an "estimated pricing" notice when
  a model's price is a guess.

**Tab 2 - Plan & Billing** (the "is my subscription worth it" view)
- Plan highlight KPI + a billing-period progress bar.
- Savings-by-period chart + average-cost-per-day chart.
- Period detail table (period, plan, days, API cost, plan cost, savings, ROI,
  sessions, messages).
- Sub-section "Limits & Recommendation": a usage-limit event timeline and a
  plan recommendation block.

**Tab 3 - Activity & Projects** (the "when and where do I work" view)
- GitHub-style contribution heatmap (calendar grid, month + weekday labels,
  less->more legend).
- Daily activity chart (dual-axis: messages + sessions).
- Hourly-distribution chart + weekday-distribution chart.
- Sub-section "Projects": a sortable table of all projects (project, source,
  sessions, messages, API value, output tokens, file size).

**Tab 4 - Sessions** (the drill-down list)
- Filter row: project dropdown, source dropdown, search box, and export buttons
  (XLSX, CSV, "download all as ZIP").
- A large, filterable/sortable session table. Each row links to a per-session
  **chat detail view** (a separate page - see note below).

**Tab 5 - Insights & System** (the dense "everything else" mega-tab)
Currently 7 stacked sub-sections, and it is the most overwhelming screen:
- *Cache & Tokens:* cache-efficiency KPIs, output-token share by tool
  (doughnut), output tokens by activity (doughnut), daily cache-efficiency chart.
- *Tools & Plugins:* tool-usage bar chart (top N), installed-plugins table.
- *Workflows:* plan-mode plans table, skills list, hooks list, git-ops summary.
- *Storage & Files:* storage doughnut, file-snapshot stats.
- *Environment:* configuration block, system-info block.
- *Agents:* subagent-types chart, top-descriptions chart, agent KPIs, task
  overview.
- *Errors & Reliability:* error-rate-over-time chart, error overview, errors by
  category, errors by tool.

> This mega-tab is the strongest candidate for restructuring (see Section 6).
> It is acceptable - encouraged, even - to propose splitting it or giving it a
> clearer internal navigation, as long as all the content survives.

**Secondary screens (out of scope for the first mockups, but design-consistent):**
There are two detail pages that share the dashboard's visual language: a
**session chat-detail view** (a full conversation transcript with markers and
filters) and a **project-detail page**. The redesign should be a system that
could extend to these later, but you don't need to mock them up first.

## 5. Current brand tokens (reference, NOT a constraint)

Provided so you can see where we're coming from, and so the "refined evolution"
direction has something to build on. The other directions are free to depart.

- **Palette (light):** background `#faf5ea` (warm cream), panels `#fbfaf6`,
  foreground `#1c1a17`, muted text `#4d4a42` / `#918a7a`, grid lines `#d8d2c4`,
  accent `#b04a2f` (terracotta).
- **Palette (dark):** background `#0e0d0b`, panels `#15140f`, foreground
  `#ece7da`, accent `#d97757`.
- **Model color families:** Opus = terracotta, Sonnet = sage, Haiku = ochre -
  an earth-tone triad, each with 2-3 lightness steps for versions.
- **Type:** monospace primary (Geist Mono / JetBrains Mono), Geist / Inter for
  sans where used. Tabular figures (`tnum`) are on - numbers align in columns.
- **Shape language:** zero border-radius everywhere (hard rectangles), thin
  hairline rules between sections, very tight density.

## 6. Known pain points (what isn't working today)

- **Density without hierarchy.** Everything is roughly the same visual weight, so
  the eye has no obvious entry point. The KPI headline numbers don't read as
  more important than a deep table.
- **The Insights mega-tab is overwhelming.** Seven sub-sections stacked
  vertically in one tab; users have to scroll a long way and lose orientation.
- **Awkward empty / unbalanced spaces.** Some panels leave large dead areas
  (especially where a chart sits next to a short list), making the grid feel
  broken rather than airy.
- **Tables dominate.** A lot of the page is raw tables. They're necessary, but
  they currently set the tone; the design could do more to make the *insights*
  pop and let tables be the detail layer.
- **"Internal tool" feel.** Monospace-everything + hard rectangles is
  distinctive but can read as unfinished to a newcomer evaluating the project.

## 7. Success criteria - what "good" looks like

A direction is succeeding if:

- A newcomer can land on the Token & API Value tab and **immediately** see the
  headline (what did this cost / what was it worth) before the detail.
- Density is preserved for power users but **organized** - clear levels of
  hierarchy (headline KPIs > primary charts > supporting tables).
- The Insights content feels navigable, not like one endless scroll.
- It looks equally intentional in light and dark, and doesn't fall apart on a
  phone.
- It feels like a **product someone chose to ship**, while still being
  unmistakably a dense, numbers-first analytics tool.

## 8. Screenshots to attach

Attach current-state screenshots so Claude Design sees the real starting point.
Capture at desktop width, then toggle and recapture:

- [ ] Tab 1 - Token & API Value (light) **and** (dark)
- [ ] Tab 2 - Plan & Billing
- [ ] Tab 3 - Activity & Projects (so the heatmap is visible)
- [ ] Tab 4 - Sessions (the filtered table)
- [ ] Tab 5 - Insights & System (full-length scroll capture - this shows the
      "overwhelming" problem better than a crop)
- [ ] One mobile-width capture of Tab 1 (to show the responsive starting point)

Tip: press **F2** first to anonymize names before screenshotting, since these go
into a third-party tool.

## 9. Suggested opening message for Claude Design

> I'm redesigning the dashboard for **claude.stats**, a self-hosted analytics
> tool for Claude Code usage. I've attached screenshots of the current design and
> a detailed brief below.
>
> I want you to **explore 2-3 distinct visual directions** for it - the current
> "terminal / monospace" look is fair game to completely rethink. For each
> direction, show me the main "Token & API Value" tab as the hero screen in both
> light and dark mode, plus one secondary screen.
>
> Hard rules: keep all the data and metrics (don't drop panels), it must work in
> light + dark mode and be responsive to mobile, and charts should stay within
> standard types (we render with Chart.js). It's a dense, read-only, numbers-first
> dashboard for technical users - organize the density into clear hierarchy
> rather than flattening it.
>
> [paste Sections 4, 5, 6, 7 of the brief here]
>
> Start by showing me thumbnail-level concepts of the 2-3 directions before
> going deep on any one.

---

## 10. After Claude Design - bringing it back to code (note for later)

Claude Design produces standalone HTML/CSS mockups, not a drop-in for this repo.
When a direction is chosen, the **implementation** handoff to Claude Code is a
separate, technical document. Key facts it will need (recorded here so they're
not lost):

- Source of truth is `templates/dashboard.{html,css,js}` + `locales/{en,de}.json`.
- `public/index.html` is **generated** by `extract_stats.py` - never hand-edited.
- The current design system is CSS custom properties (`--vc-*`) scoped to a
  `.vc` class, with a legacy-variable remap layer; a redesign will likely rework
  that token layer.
- UI is bilingual (en/de) via `__L_*__` placeholder keys - any new copy needs
  entries in both locale files.
- Charts are Chart.js 4.4.7 with shared defaults in `setupVcChartDefaults`.

Do not paste this section into Claude Design - it's only relevant to the
follow-up code implementation.
