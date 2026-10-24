"""Stage 3: context management.

Every model call resends the whole message list, so long sessions get slow, costly
and eventually overflow the context window. This stage adds:
  - an OS-aware system prompt plus optional project memory (AGENTS.md)
  - a token estimate and a budget
  - two-tier compaction when over budget:
      tier 1: elide old, bulky tool outputs (cheap, no model call)
      tier 2: summarize older turns with the model, keep recent turns verbatim
  - /clear, /compact and /tokens commands
"""
import json
import os
import platform
import sys

from stage2_tools import MAX_STEPS, MODEL, WORKDIR, call_model, client, run_tool

BUDGET_TOKENS = int(os.environ.get("CONTEXT_BUDGET_TOKENS", "12000"))
KEEP_RECENT_TURNS = 2  # user turns kept verbatim during tier-2 compaction
ELIDE_OVER_CHARS = 500


def build_base_prompt() -> str:
    prompt = (
        f"You are a coding agent working in {WORKDIR}.\n"
        f"Platform: {platform.system()} (shell commands run via the system shell, "
        f"so use syntax valid for it).\n"
        "Use the tools to inspect and change files and to run commands. Prefer small, "
        "verifiable steps. Read a file before editing it. When the task is done, "
        "reply with a short summary and no tool call."
    )
    memory = WORKDIR / "AGENTS.md"
    if memory.exists():
        prompt += "\n\nProject notes (AGENTS.md):\n" + memory.read_text(encoding="utf-8")
    return prompt


BASE_PROMPT = build_base_prompt()


def estimate_tokens(messages) -> int:
    return len(json.dumps(messages)) // 4  # rough: ~4 chars per token


def _last_user_indexes(messages):
    return [i for i, m in enumerate(messages) if m["role"] == "user"]


def elide_old_tool_output(messages) -> int:
    """Tier 1: shrink bulky tool results from before the latest user turn."""
    users = _last_user_indexes(messages)
    if not users:
        return 0
    freed = 0
    for m in messages[: users[-1]]:
        if m["role"] == "tool" and len(m["content"]) > ELIDE_OVER_CHARS:
            freed += len(m["content"])
            m["content"] = "[old tool output elided to save context]"
    return freed


def summarize(old_messages) -> str:
    lines = []
    for m in old_messages:
        text = m.get("content") or ""
        if m.get("tool_calls"):
            text += " " + json.dumps([t["function"] for t in m["tool_calls"]])
        lines.append(f"{m['role']}: {text[:1500]}")
    prompt = (
        "Summarize this agent session so work can continue. Keep: the user's goal, "
        "files created/changed, decisions made, errors hit, and what remains.\n\n"
        + "\n".join(lines)
    )
    resp = client.chat.completions.create(
        model=MODEL, messages=[{"role": "user", "content": prompt}]
    )
    return resp.choices[0].message.content or "(empty summary)"


def compact(messages, force=False) -> bool:
    """Shrink `messages` in place if over budget (or forced). Returns True if changed."""
    if not force and estimate_tokens(messages) <= BUDGET_TOKENS:
        return False
    elide_old_tool_output(messages)
    if not force and estimate_tokens(messages) <= BUDGET_TOKENS:
        print("  [context] elided old tool output")
        return True

    users = _last_user_indexes(messages)
    if len(users) <= KEEP_RECENT_TURNS:
        return True  # nothing old enough to summarize
    cut = users[-KEEP_RECENT_TURNS]  # cut on a user boundary: tool_call/result pairs stay intact
    old, recent = messages[1:cut], messages[cut:]
    summary = summarize(old)
    messages[:] = (
        [{"role": "system", "content": BASE_PROMPT + "\n\nSummary of earlier work:\n" + summary}]
        + recent
    )
    print(f"  [context] summarized {len(old)} messages -> ~{estimate_tokens(messages)} tokens")
    return True


def run_agent(messages, tool_runner=run_tool):
    for _ in range(MAX_STEPS):
        compact(messages)
        reply = call_model(messages)
        entry = {"role": "assistant", "content": reply.content or ""}
        if reply.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in reply.tool_calls
            ]
        messages.append(entry)
        if not reply.tool_calls:
            return reply.content
        for tc in reply.tool_calls:
            print(f"  [tool] {tc.function.name}({tc.function.arguments})")
            result = tool_runner(tc.function.name, tc.function.arguments)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    return "stopped: reached MAX_STEPS"


def repl(title, tool_runner=run_tool):
    messages = [{"role": "system", "content": BASE_PROMPT}]
    print(f"{title} | model={MODEL} | budget={BUDGET_TOKENS} tokens | /clear /compact /tokens /exit")
    while True:
        try:
            user_input = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if user_input in ("exit", "quit", "/exit"):
            break
        if user_input == "/clear":
            messages[:] = [{"role": "system", "content": BASE_PROMPT}]
            print("cleared.")
            continue
        if user_input == "/tokens":
            print(f"~{estimate_tokens(messages)} tokens in context (budget {BUDGET_TOKENS})")
            continue
        if user_input == "/compact":
            compact(messages, force=True)
            continue
        if not user_input:
            continue
        messages.append({"role": "user", "content": user_input})
        print(f"\nagent> {run_agent(messages, tool_runner)}")


if __name__ == "__main__":
    repl("Stage 3 harness")
