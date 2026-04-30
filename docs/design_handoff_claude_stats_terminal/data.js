// Shared mock data for Claude Stats dashboard variants
window.STATS_DATA = {
  account: { name: "andie", plan: "Max 20×", first_session: "2025-12-14", last_session: "2026-04-30" },
  generated_at: "2026-04-30T16:30:23Z",

  kpi: {
    api_equivalent: 4287.42,
    actual_paid: 200.00,
    messages: 18432,
    sessions: 247,
    output_tokens: 8_420_000,
    input_tokens: 412_000,
    cache_read: 184_200_000,
    cache_write: 9_120_000,
  },

  // 60 days of daily cost data
  daily_cost: Array.from({length: 60}, (_, i) => {
    const base = 12 + Math.sin(i / 4) * 6 + Math.cos(i / 9) * 8;
    const weekend = (i % 7 === 5 || i % 7 === 6) ? 0.4 : 1;
    const spike = (i === 42 || i === 31 || i === 18) ? 2.4 : 1;
    return Math.max(0, base * weekend * spike + (Math.random() - 0.5) * 4);
  }),

  models: [
    { name: "Opus 4.7",   cost: 2890.30, calls: 4210, share: 67.4, output: 5_820_000 },
    { name: "Sonnet 4.5", cost: 1184.20, calls: 8932, share: 27.6, output: 2_180_000 },
    { name: "Haiku 4.5", cost:  212.92, calls: 5102, share:  5.0, output:   420_000 },
  ],

  projects: [
    { name: "claude-stats",          sessions: 42, messages: 3120, cost: 824.50, output: 1_420_000, sizeMb: 18.2 },
    { name: "open-brain",            sessions: 38, messages: 2890, cost: 712.10, output: 1_280_000, sizeMb: 24.1 },
    { name: "cortex-web",            sessions: 31, messages: 2412, cost: 612.40, output: 1_120_000, sizeMb: 12.8 },
    { name: "mealcal-ios",           sessions: 24, messages: 1820, cost: 482.30, output:   820_000, sizeMb:  8.9 },
    { name: "andie.dev",             sessions: 19, messages: 1240, cost: 318.90, output:   612_000, sizeMb:  4.2 },
    { name: "claude-bridge",         sessions: 17, messages: 1110, cost: 282.40, output:   540_000, sizeMb:  6.1 },
    { name: "synthesizer",           sessions: 14, messages:  892, cost: 218.10, output:   412_000, sizeMb:  3.8 },
    { name: "internal-tools",        sessions: 12, messages:  724, cost: 198.40, output:   380_000, sizeMb:  9.2 },
    { name: "scratch",               sessions: 28, messages:  512, cost: 142.30, output:   220_000, sizeMb:  1.4 },
    { name: "writing-archive",       sessions:  9, messages:  402, cost: 112.80, output:   190_000, sizeMb:  2.1 },
    { name: "obsidian-utils",        sessions:  7, messages:  312, cost:  84.20, output:   142_000, sizeMb:  1.2 },
    { name: "homelab",               sessions:  6, messages:  248, cost:  76.40, output:   118_000, sizeMb:  3.1 },
  ],

  // 24-hour activity (messages by hour, Mon=0..Sun=6)
  hourly: Array.from({length: 24}, (_, h) => {
    if (h < 6) return Math.floor(Math.random() * 12);
    if (h < 9) return Math.floor(40 + Math.random() * 60);
    if (h < 13) return Math.floor(180 + Math.random() * 80);
    if (h < 18) return Math.floor(220 + Math.random() * 100);
    if (h < 22) return Math.floor(120 + Math.random() * 80);
    return Math.floor(20 + Math.random() * 30);
  }),

  weekday: [342, 412, 398, 384, 320, 142, 98], // Mon..Sun

  // 14-week activity heatmap (rows = weekday, cols = week)
  heatmap: Array.from({length: 7}, (_, d) =>
    Array.from({length: 18}, (_, w) => {
      if (d >= 5) return Math.floor(Math.random() * 3);
      return Math.floor(Math.random() * 12) + (Math.sin((w + d) / 3) * 4);
    })
  ),

  recent_sessions: [
    { date: "2026-04-30 14:08", project: "claude-stats", model: "Opus 4.7",   duration: 52,  messages: 198, cost: 10.23, prompt: "Cache-Effizienz-Metriken in Session-Übersicht ergänzen…" },
    { date: "2026-04-30 09:11", project: "claude-stats", model: "Opus 4.7",   duration: 55,  messages: 144, cost:  3.44, prompt: "Workflow-Timeline für Project Detail bauen…" },
    { date: "2026-04-29 19:42", project: "open-brain",   model: "Sonnet 4.5", duration: 38,  messages:  92, cost:  1.82, prompt: "Refactor capture_thought to support batch operations…" },
    { date: "2026-04-29 14:20", project: "cortex-web",   model: "Opus 4.7",   duration: 41,  messages: 112, cost:  4.18, prompt: "Tighten the chat panel layout on mobile, avoid horizontal overflow…" },
    { date: "2026-04-29 10:08", project: "mealcal-ios",  model: "Sonnet 4.5", duration: 28,  messages:  76, cost:  1.12, prompt: "Add weekly meal grouping with collapsed state…" },
    { date: "2026-04-28 16:50", project: "claude-stats", model: "Opus 4.7",   duration: 62,  messages: 184, cost:  8.92, prompt: "Build the new dashboard tweaks panel…" },
    { date: "2026-04-28 11:24", project: "andie.dev",    model: "Haiku 4.5",  duration: 18,  messages:  42, cost:  0.34, prompt: "Quick copy edit on the about page…" },
  ],

  top_tools: [
    { name: "Edit", count: 1842 },
    { name: "Read", count: 1428 },
    { name: "Bash", count:  912 },
    { name: "TaskUpdate", count: 482 },
    { name: "Write", count: 312 },
    { name: "Grep", count: 248 },
    { name: "TaskCreate", count: 198 },
    { name: "Glob", count: 142 },
  ],
};
