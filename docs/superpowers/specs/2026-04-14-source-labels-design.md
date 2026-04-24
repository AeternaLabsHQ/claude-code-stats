# Source Labels

Display the origin of each session and project in the dashboard via configurable labels.

## Config Changes

### New fields

- **Top-level `source_label`**: label for the local/primary source (replaces hardcoded `"current"`)
- **`migration.label`**: label for the migration source (replaces hardcoded `"migration"`)
- `additional_sources[].label` already exists, just update values

### Target config.json

```json
{
  "source_label": "cortex:andie",
  "migration": {
    "enabled": true,
    "label": "archiv:galatea",
    "dir": "~/projects/_migration-backup",
    "claude_dir_name": ".claude-windows",
    "dot_claude_json_name": ".claude-windows.json"
  },
  "additional_sources": [
    { "label": "cortex:dori", "claude_dir": "/home/dori/.claude", "dot_claude_json": "/home/dori/.claude.json" },
    { "label": "galatea:andie", "claude_dir": "/home/andie/galatea-claude/.claude", "dot_claude_json": "/home/andie/galatea-claude/.claude.json" }
  ]
}
```

### config.example.json

Add `source_label` field and `migration.label` field.

## Data Pipeline

### parse_session_transcripts()

- Read `source_label` from config for local source (fallback: `"current"`)
- Read `migration.label` from config for migration source (fallback: `"migration"`)
- `additional_sources[].label` already used as-is

### build_dashboard_data()

- Add `"source": sess["source"]` to session_list items (line ~1478-1511)
- Aggregate `sources` per project: collect the set of distinct source labels across all sessions for each project
- Add `"sources": [...]` to project_list items (line ~1551-1563)

## UI Changes

### Session Cards (buildSessionCard)

- Show a source badge on every session card, next to the project name
- Style: small pill/tag, muted color, similar to model-badge but distinct
- Color coding: use a hash-based color from a palette so each source gets a consistent color

### Project Table (renderProjectTable)

- After the project name, render source tags inline
- Same styling as session source badges

### Session Filter

- Add a source dropdown filter next to the existing project filter
- Options: "All Sources" + distinct source labels from the data

## What does NOT change

- Session detail pages (sessions/*.html)
- Project detail pages (projects/*.html)
- Plan analysis
- KPI calculations
