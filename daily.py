#!/usr/bin/env python3
"""Show daily Claude Code usage for the last 30 days."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
DAYS = 30

# Token costs per million (USD) — matched by substring
COSTS = {
    "opus":   {"input": 15.0,  "output": 75.0,  "cache_read": 1.5,  "cache_write": 18.75},
    "sonnet": {"input": 3.0,   "output": 15.0,  "cache_read": 0.3,  "cache_write": 3.75},
    "haiku":  {"input": 0.8,   "output": 4.0,   "cache_read": 0.08, "cache_write": 1.0},
}

def model_cost(model, usage):
    model = (model or "").lower()
    rates = next((r for key, r in COSTS.items() if key in model), None)
    if not rates:
        return 0.0
    m = 1_000_000
    return (
        usage.get("input_tokens", 0) * rates["input"] / m +
        usage.get("output_tokens", 0) * rates["output"] / m +
        usage.get("cache_read_input_tokens", 0) * rates["cache_read"] / m +
        usage.get("cache_creation_input_tokens", 0) * rates["cache_write"] / m
    )

def parse_ts(ts):
    if isinstance(ts, str):
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return datetime.fromtimestamp(ts / 1000 if ts > 1e10 else ts, tz=timezone.utc)

def main():
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS)
    daily = {}

    for jsonl in PROJECTS_DIR.rglob("*.jsonl"):
        try:
            with open(jsonl) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        ts = entry.get("timestamp")
                        if not ts:
                            continue
                        dt = parse_ts(ts)
                        if dt < cutoff:
                            continue
                        usage = entry.get("message", {}).get("usage") or entry.get("usage")
                        model = entry.get("message", {}).get("model") or entry.get("model")
                        if not usage or not model:
                            continue
                        day = dt.strftime("%Y-%m-%d")
                        daily[day] = daily.get(day, 0.0) + model_cost(model, usage)
                    except Exception:
                        pass
        except Exception:
            pass

    if not daily:
        print("No usage data found.")
        return

    max_cost = max(daily.values())
    total = sum(daily.values())
    print(f"Daily API-equivalent usage (last {DAYS} days)\n{'─' * 38}")
    for day in sorted(daily):
        bar = "█" * int(daily[day] / max_cost * 20)
        print(f"{day}  ${daily[day]:6.2f}  {bar}")
    print(f"{'─' * 38}\nTotal: ${total:.2f}")

if __name__ == "__main__":
    main()
