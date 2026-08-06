"""Transcript entry / tool-error / API-error classification and stream merge."""
import re

# Empirically derived from real Claude Code JSONLs: only these phrases
# uniquely indicate a USER-plan rate-limit hit (vs auth, server overload,
# network, invalid request). Used by the isApiErrorMessage-driven
# limit-event detection: see _is_user_plan_limit_text().
_USER_PLAN_LIMIT_SIGNALS = (
    "you've hit your limit",         # Claude Code 5h-session cap banner
    "hit your org's monthly usage",  # Weekly/monthly org cap
    "usage limit reached",
    "plan limit reached",
    "rate limit reached",            # "API Error: Rate limit reached"
)


def _is_user_plan_limit_text(text: str) -> bool:
    """True iff an API-error message clearly indicates a user / plan
    rate-limit. Distinguishes from auth / server-overload / network errors
    that Claude Code also reports via isApiErrorMessage."""
    t = (text or "").lower()
    return any(needle in t for needle in _USER_PLAN_LIMIT_SIGNALS)


# Categories a type:"user" transcript entry can fall into. Only "prompt"
# is a message the person actually typed; the rest are synthetic entries
# Claude Code emits on the "user" channel. Tracked as separate metrics.
USER_ENTRY_CATEGORIES = ("prompt", "tool_result", "command", "interrupt", "meta")


def _classify_user_entry(obj: dict) -> str:
    """Classify a type:"user" transcript entry into one of
    USER_ENTRY_CATEGORIES. Precedence: tool_result > command > interrupt >
    meta > prompt. Claude Code records tool_result blocks on the "user"
    channel, and emits slash-command / interrupt / meta wrappers as user
    entries too; none of those are messages the person actually typed.
    Mirrors the per-session chat transcript filter (which is why the
    session detail page already shows only real prompts)."""
    # Compaction summaries arrive as type:"user" with a plain-string body;
    # they are a synthetic continuation note, counted via `compactions`.
    if obj.get("isCompactSummary"):
        return "meta"
    content = obj.get("message", {}).get("content", "")
    if isinstance(content, list):
        # tool_result blocks are delivered on the user channel
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return "tool_result"
        text = next((b.get("text", "") for b in content
                     if isinstance(b, dict) and b.get("type") == "text"), "")
    elif isinstance(content, str):
        text = content
    else:
        text = ""
    text = text.strip()
    if text.startswith("<command") or text.startswith("<local-command"):
        return "command"
    if text.startswith("[Request interrupted"):
        return "interrupt"
    if obj.get("isMeta"):
        return "meta"
    if not text:
        # empty, non-tool-result user entry (e.g. attachment-only), not a
        # typed prompt; bucket with meta rather than inflating the count
        return "meta"
    return "prompt"


def _merge_streamed_assistant_entries(entries: list) -> list:
    """Collapse stream-split assistant rows back into one entry per API
    response.

    Claude Code writes ONE JSONL line per assistant content block
    (thinking / text / each tool_use). Every line of a single response
    shares the same message.id and carries a `usage` object, but the
    usages are NOT identical: output_tokens grows across the lines and
    only the LAST line holds the response's final total (input/cache
    fields are near-constant). Counting per line therefore multiplies
    tokens / cost / calls / message counts by the number of content
    blocks, while keeping only the first line's usage undercounts output
    tokens 1.5-4x. We merge assistant lines with the same message.id into
    a single entry (content blocks concatenated, timestamp/uuid kept from
    the first line, usage overwritten by each later line that has one) so
    downstream accounting sees one response = one entry with its final
    usage, exactly once.

    message.id is globally unique per API response, so all rows of one
    response are merged into the single entry at its first occurrence, even
    when they are NOT consecutive. Agentic turns interleave one response's
    tool_use rows with the tool_result (type:"user") rows that come back, so
    the same message.id can recur dozens of times spread across the
    transcript; consecutive-only merging would miss those. Assistant entries
    without a message.id (rare) and the older one-line-per-response format
    both pass through unchanged. The input list is not mutated; interleaved
    non-assistant entries keep their position."""
    merged = []
    targets = {}        # message.id -> the merge-target entry in `merged`
    for e in entries:
        if not isinstance(e, dict) or e.get("type") != "assistant":
            merged.append(e)
            continue
        mid = (e.get("message") or {}).get("id")
        if mid and mid in targets:
            later_msg = e.get("message") or {}
            targets[mid]["message"]["content"].extend(
                later_msg.get("content", []) or []
            )
            later_usage = later_msg.get("usage")
            if isinstance(later_usage, dict):
                targets[mid]["message"]["usage"] = later_usage
            continue
        # first sighting of this response: shallow-copy so input stays intact
        copy = dict(e)
        msg = dict(e.get("message") or {})
        msg["content"] = list(msg.get("content", []) or [])
        copy["message"] = msg
        merged.append(copy)
        if mid:
            targets[mid] = copy
    return merged


def _classify_tool_error(msg: str, tool_name: str) -> tuple:
    """Classify a tool_result `is_error` payload into (source, category).

    source is one of: "user" (the person declined / a parallel sibling was
    cancelled, NOT a failure), "hook" (a PreToolUse/PostToolUse hook
    failed), or "tool" (the tool call genuinely failed).

    Deliberately does NOT recognise backend categories (rate_limit /
    server_overload): those keywords routinely appear *inside* a tool's own
    stdout/stderr (test output, code being edited, tracebacks) and matching
    them here miscategorises ordinary tool failures as API rate-limits.
    Genuine backend errors arrive on the isApiErrorMessage channel and are
    classified by _classify_api_error()."""
    m = msg.lower()
    # user-driven, not failures
    if "cancelled:" in m or "canceled:" in m or "parallel tool call" in m:
        return ("user", "cancelled")
    if ("doesn't want to proceed" in m or "does not want to proceed" in m
            or "tool use was rejected" in m or "user rejected" in m):
        return ("user", "rejected")
    # hook failures
    if "hook error" in m or "hook_error" in m:
        return ("hook", "hook_error")
    # genuine tool failures
    if "no replacement was performed" in m or "old_string not found" in m \
            or "string to replace not found" in m:
        cat = "edit_no_match"
    elif "not unique" in m or "multiple occurrences" in m or "matches of the string" in m:
        cat = "edit_not_unique"
    elif ("has not been read yet" in m or "has been modified since read" in m):
        cat = "stale_read"
    elif "does not exist" in m or "no such file" in m or ("not found" in m and "command not found" not in m):
        cat = "file_not_found"
    elif "command not found" in m:
        cat = "command_not_found"
    elif "permission" in m or "denied" in m:
        cat = "permission_denied"
    elif "timeout" in m or "timed out" in m:
        cat = "timeout"
    elif "syntaxerror" in m or "syntax error" in m:
        cat = "syntax_error"
    elif "importerror" in m or "modulenotfounderror" in m:
        cat = "import_error"
    elif "exit code" in m or "returned non-zero" in m:
        cat = "exit_code"
    elif tool_name == "Edit":
        cat = "edit_failed"
    else:
        cat = "other"
    return ("tool", cat)


_ANSI_CSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _clean_error_text(s) -> str:
    """Make a raw tool-error payload readable: strip ANSI escape sequences
    (color/cursor codes that Bash output carries) and carriage returns, and
    trim trailing whitespace. Newlines are preserved."""
    if not s:
        return ""
    s = _ANSI_CSI_RE.sub("", str(s))
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    return s.rstrip()


def _route_tool_error(source: str, category: str):
    """Decide how a classified tool error is accounted. Returns the source
    label to count it under, or None if it is NOT a real error.

    A cancelled parallel-call sibling is not a failure (-> None, tracked as
    cancelled_count). A user rejection DOES count as an error under its own
    "rejected" source. Genuine tool / hook / backend failures keep their
    source."""
    if source == "user":
        if category == "cancelled":
            return None
        return "rejected"
    return source


def _extract_command_label(text: str) -> str:
    """Pull a readable slash-command label out of a `<command-name>` wrapper.
    Returns "" for command *output* (`<local-command-stdout>`) or plain text,
    so only genuine invocations become chat markers."""
    if "<command-name>" not in text:
        return ""
    name = text.split("<command-name>", 1)[1].split("</command-name>", 1)[0].strip()
    if not name:
        return ""
    if not name.startswith("/"):
        name = "/" + name
    args = ""
    if "<command-args>" in text:
        args = text.split("<command-args>", 1)[1].split("</command-args>", 1)[0].strip()
    return (name + " " + args).strip()


def _classify_api_error(text: str) -> str:
    """Categorise an isApiErrorMessage payload (always source "backend")."""
    t = (text or "").lower()
    if ("hit your limit" in t or "usage limit" in t or "rate limit" in t
            or "rate_limit_error" in t or re.search(r"\b429\b", t)):
        return "rate_limit"
    if "overloaded" in t or re.search(r"\b529\b", t):
        return "server_overload"
    if ("authentication" in t or "run /login" in t or re.search(r"\b401\b", t)
            or "invalid authentication" in t):
        return "auth"
    if (re.search(r"\b5\d\d\b", t) or "internal server error" in t
            or "bad gateway" in t or "server-side issue" in t):
        return "server_error"
    if ("idle timeout" in t or "socket" in t or "connection was closed" in t
            or "timed out" in t or "timeout" in t):
        return "connection"
    if "content filtering" in t or "content filter" in t:
        return "content_filter"
    if ("prompt is too long" in t or "too long" in t or "invalid_request" in t
            or re.search(r"\b400\b", t) or "could not process" in t):
        return "invalid_request"
    return "other"
