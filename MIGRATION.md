# Migrating from 0.8.x to 1.0.0

Nothing is required of you. `python3 extract_stats.py` runs against your existing `config.json` and produces the new dashboard. This document explains what changed, and how to get pieces of the old behavior back if you want them.

## For users

### The seven tabs are now five

Two of the seven tabs were folded into others: Projects merged into Activity, and Agents became a section under Insights & System. The remaining five kept their content and gained clearer names. Nothing was dropped, only regrouped.

| Old tab | Where it is now |
|---|---|
| Costs | Token & API Value |
| Activity | Activity & Projects |
| Projects | Activity & Projects |
| Sessions | Sessions |
| Plan | Plan & Billing |
| Insights | Insights & System |
| Agents | Insights & System |

Deep links keep working. `index.html#projects` and `index.html#agents` open the tab their content moved to, so existing bookmarks land on the content rather than on the default tab.

### New color scheme

The dashboard now ships a light and a dark theme, and the accent moved from indigo to terracotta.

**Keep the old behavior:** copy the example file and uncomment the `Classic Indigo` block.

```bash
cp public/custom.css.example public/custom.css
# then uncomment the "=== Classic Indigo ===" block near the bottom
```

The generated pages load `public/custom.css` after the inlined stylesheet, so it wins the cascade. Charts and the activity heatmap read the accent live, so the change applies without a rebuild. The builder never overwrites an existing `custom.css`.

### Your config keeps working

No configuration changes are required. The older `cost_eur` key is still read, and every key added since has a default.

One thing is worth adding if you track a non-USD plan price. `cost_eur` was assumed to be euro; if you use a different currency, name it explicitly so the dashboard labels it correctly:

```json
{
  "plan_history": [
    {
      "plan": "Max 5x",
      "cost_usd": 100.00,
      "cost_local": 92.00,
      "currency_symbol": "CHF"
    }
  ]
}
```

### If you deploy the output yourself

The dashboard was never a single file: 0.8.x already wrote the `projects/` and `sessions/` directories alongside `index.html`, and a deploy script that copied only `index.html` already produced a dashboard with broken detail-page links. What's new in 1.0.0 is `custom.css` and `custom.css.example`; their absence doesn't break anything since the styling is inlined into `index.html` and `custom.css` is purely an override, but you won't get your theming. Copy the whole `public/` directory either way.

## For fork maintainers

### The license stays MIT

No new obligations. The repository now carries a real `LICENSE` file, where before MIT was only stated in the README.

### The file layout changed substantially

This is the part that affects you. `extract_stats.py` went from 6283 to 1790 lines. It is now the CLI and the HTML renderer, nothing else.

The HTML, CSS and JavaScript are no longer Python strings. They live in `templates/` as real files. The computation logic moved into a `claudestats_core` package:

| Module | Responsibility |
|---|---|
| `claudestats_core/pricing.py` | Price tables, model display names, cost calculation |
| `claudestats_core/sessions.py` | Session merging, subagent linking, day splitting |
| `claudestats_core/aggregate.py` | `build_dashboard_data` |
| `claudestats_core/plan_analysis.py` | Plan and billing analysis |
| `claudestats_core/limits.py` | Five-hour windows, weekly buckets, limit events |
| `claudestats_core/classify.py` | Entry and error classification, stream merging |
| `claudestats_core/attribution.py` | Token and write-category attribution |
| `claudestats_core/anomalies.py` | Cache flush, idle gap, context window detection |
| `claudestats_core/settings.py` | Configuration seam |

**Re-apply your patch rather than merge it.** A merge across this move produces conflicts that are harder to read than the original change. Find the module owning your area in the table above, and apply your change there.

If your fork added models to the price table, that is now `claudestats_core/pricing.py`, and it is a much shorter file to work in than the old monolith.

## Rolling back to 0.8.x

Straightforward, because there is no migrated state to undo. The dashboard is rebuilt from your JSONL transcripts on every run.

```bash
git checkout v0.8.1
python3 extract_stats.py
```

A `public/custom.css` you created stays on disk and is simply inert on 0.8.x, which does not load it.
