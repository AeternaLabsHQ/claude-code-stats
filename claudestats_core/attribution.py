"""Per-turn token/cost attribution across tools and write categories."""
import json


def attribute_turn_tokens(output_tokens, cost, tool_names):
    """Split a turn's output_tokens and cost across its tool_use blocks.

    Repeated tool names in the same turn collapse into a single entry whose
    share equals (count_of_that_tool / total_tools) of the turn.
    Turns with no tools attribute fully to the reasoning bucket.
    """
    if not tool_names:
        return {
            "per_tool": [],
            "reasoning_output_tokens": output_tokens,
            "reasoning_cost": cost,
        }

    n = len(tool_names)
    per_tool_counts = {}
    for name in tool_names:
        per_tool_counts[name] = per_tool_counts.get(name, 0) + 1

    per_tool = []
    items = list(per_tool_counts.items())
    allocated_tokens = 0
    allocated_cost = 0.0
    for i, (name, c) in enumerate(items):
        share = c / n
        if i < len(items) - 1:
            tokens = int(round(output_tokens * share))
            tcost = cost * share
        else:
            # Last entry absorbs rounding remainder so totals reconcile exactly.
            tokens = output_tokens - allocated_tokens
            tcost = cost - allocated_cost
        allocated_tokens += tokens
        allocated_cost += tcost
        per_tool.append({
            "tool": name,
            "output_tokens": tokens,
            "cost": tcost,
        })

    return {
        "per_tool": per_tool,
        "reasoning_output_tokens": 0,
        "reasoning_cost": 0.0,
    }


WRITE_CATEGORIES = (
    "screen_text",            # text in turns with NO tool_use — final answers / pure explanations
    "screen_text_narration",  # text in turns WITH tool_use — "let me check…" inter-tool narration
    "thinking",
    "file_writes",
    "bash_commands",
    "tool_inputs",
)
_FILE_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def _block_weight(block):
    """Approximate char-count of model-generated payload for one content block.

    Used as a proportional weight to split a message's output_tokens across blocks.
    Tool-use blocks include the tool name + compact JSON of input parameters,
    since both are emitted by the model.
    """
    if not isinstance(block, dict):
        return 0
    btype = block.get("type")
    if btype == "text":
        return len(block.get("text") or "")
    if btype == "thinking":
        return len(block.get("thinking") or "")
    if btype == "tool_use":
        name = block.get("name") or ""
        inp = block.get("input")
        try:
            payload = json.dumps(inp, ensure_ascii=False, separators=(",", ":")) if inp is not None else ""
        except (TypeError, ValueError):
            payload = str(inp) if inp is not None else ""
        return len(name) + len(payload)
    return 0


def _block_category(block, turn_has_tools):
    """Map a content block to one of WRITE_CATEGORIES, or None if it doesn't generate tokens.

    `turn_has_tools` distinguishes a text block in a tool-using turn (narration
    between tool calls, visible to user) from a text block in a pure-text turn
    (final answer / explanation).
    """
    if not isinstance(block, dict):
        return None
    btype = block.get("type")
    if btype == "text":
        return "screen_text_narration" if turn_has_tools else "screen_text"
    if btype == "thinking":
        return "thinking"
    if btype == "tool_use":
        name = block.get("name") or ""
        if name in _FILE_WRITE_TOOLS:
            return "file_writes"
        if name == "Bash":
            return "bash_commands"
        return "tool_inputs"
    return None


def attribute_write_categories(content_blocks, output_tokens):
    """Split a turn's output_tokens across write categories by char-weight heuristic.

    Heuristic: each content block contributes a weight equal to the char-count
    of the payload the model had to generate (text body, thinking body, or
    tool name + JSON of input). The message's output_tokens are distributed
    proportionally; rounding remainder goes to the last non-zero bucket so
    totals reconcile exactly.
    """
    result = {cat: 0 for cat in WRITE_CATEGORIES}
    if not output_tokens or not content_blocks:
        return result

    turn_has_tools = any(
        isinstance(b, dict) and b.get("type") == "tool_use"
        for b in content_blocks
    )

    per_block = []
    total_weight = 0
    for block in content_blocks:
        cat = _block_category(block, turn_has_tools)
        if cat is None:
            continue
        w = _block_weight(block)
        if w <= 0:
            continue
        per_block.append((cat, w))
        total_weight += w

    if total_weight <= 0:
        # No measurable payload — dump everything into screen_text as a safe fallback.
        result["screen_text"] = output_tokens
        return result

    allocated = 0
    last_idx = len(per_block) - 1
    for i, (cat, w) in enumerate(per_block):
        if i < last_idx:
            tokens = int(round(output_tokens * w / total_weight))
        else:
            tokens = output_tokens - allocated
        result[cat] += tokens
        allocated += tokens
    return result
