# Claude Code Usage Statistics

A comprehensive analytics dashboard for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) usage data. Parses your local Claude Code session transcripts, calculates hypothetical API costs, and generates an interactive HTML dashboard.

***Disclaimer:*** *This is an unofficial, community-built tool. Not affiliated with or endorsed by Anthropic.*

> **PRIVACY WARNING**
>
> This dashboard may contain **sensitive data**: source code snippets, file paths, API keys, project memories, conversation history, and internal notes. **Do NOT publish the generated output to the public internet or any unsecured location.** Use authentication or keep it local. Use `--no-memories` to exclude project memory content. Press `F2` in the dashboard to toggle anonymization mode for screenshots.

## Features

- **Time Range Filter** -- Global pill buttons (All / 7D / 30D / 90D / 1Y) to filter the entire dashboard by time period
- **KPI Dashboard** -- Total API-equivalent cost, messages, sessions, output tokens
- **Token & API Value** -- Daily costs, cumulative costs, model distribution
- **Activity** -- Message patterns, hourly distribution, weekday distribution
- **Projects** -- Top projects by cost, detailed project metrics
- **Sessions** -- Filterable/searchable session details with expandable metadata
- **Plan & Billing** -- Cost savings analysis vs. your subscription plan
- **Insights** -- Tool usage, storage breakdown, plugins, todos, file snapshots

![Dashboard Screenshot](docs/images/claude-code-stats-01.png)

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/AeternaLabsHQ/claude-code-stats.git
   cd claude-code-stats
   ```

2. **Create your configuration**
   ```bash
   cp config.example.json config.json
   ```
   Edit `config.json` to match your subscription plan and preferences.

3. **Run the extractor**
   ```bash
   python3 extract_stats.py
   ```

4. **Open the dashboard**
   ```bash
   open public/index.html      # macOS
   xdg-open public/index.html  # Linux
   start public/index.html     # Windows
   ```

## Configuration

See [`config.example.json`](config.example.json) for all options:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `language` | `string` | `"en"` | UI language (`"en"` or `"de"`) |
| `plan_history` | `array` | `[]` | Your subscription plan history |
| `migration.enabled` | `bool` | `false` | Enable data from a migration backup |
| `migration.dir` | `string` | `null` | Path to migration backup directory |

### Plan History

Each entry in `plan_history` represents a subscription period:

```json
{
  "plan": "Max",
  "start": "2026-01-23",
  "end": null,
  "cost_eur": 87.61,
  "cost_usd": 93.00,
  "billing_day": 23
}
```

- `end: null` means the plan is currently active
- `billing_day` determines billing cycle boundaries for cost analysis

### Migration Support

If you migrated Claude Code data from another machine, you can include that historical data:

```json
{
  "migration": {
    "enabled": true,
    "dir": "~/backups/old-machine",
    "claude_dir_name": ".claude-windows",
    "dot_claude_json_name": ".claude-windows.json"
  }
}
```

The script deduplicates sessions across both sources automatically.

## Output

The script generates files in the `public/` directory:

- `index.html` -- Self-contained interactive dashboard (open in any browser)
- `dashboard_data.json` -- Raw aggregated data (for custom analysis)

## Automation

To auto-refresh the dashboard periodically:

```bash
*/10 * * * * cd /path/to/claude-stats && python3 extract_stats.py 2>&1 >> update.log
```

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)
- Claude Code installed with session data in `~/.claude/`

## Localization

The dashboard supports English and German. Set `"language": "en"` or `"language": "de"` in your `config.json`.

To add a new language, create a file in `locales/` following the structure of [`locales/en.json`](locales/en.json).

## License

MIT
