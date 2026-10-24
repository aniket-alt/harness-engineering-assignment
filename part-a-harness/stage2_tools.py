"""Stage 2: tools + the agent loop.

Stage 1 could only talk. Now the model can ask us to run tools. The harness:
  1. sends messages + tool schemas to the model
  2. if the reply contains tool_calls, runs them and appends the results
  3. calls the model again, and repeats until it answers without tool_calls
Also adds retry with backoff, since free models often return 429.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from openai import APIConnectionError, InternalServerError, OpenAI, RateLimitError

MODEL = os.environ.get("OPENROUTER_MODEL", "openrouter/free")
MAX_STEPS = 20
MAX_OUTPUT_CHARS = 10_000
WORKDIR = Path.cwd().resolve()

API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
if not API_KEY:
    sys.exit("OPENROUTER_API_KEY is missing or empty. Set it in this terminal first.")

client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=API_KEY)

SYSTEM_PROMPT = f"""You are a coding agent working in {WORKDIR}.
Use the tools to inspect and change files and to run commands. Prefer small,
verifiable steps. Read a file before editing it. When the task is done, reply
with a short summary and no tool call."""


# ---------- tools ----------

def _resolve(path: str) -> Path:
    return (WORKDIR / path).resolve()


def read_file(path: str) -> str:
    return _resolve(path).read_text(encoding="utf-8")


def write_file(path: str, content: str) -> str:
    p = _resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return f"wrote {len(content)} chars to {path}"


def edit_file(path: str, old: str, new: str) -> str:
    p = _resolve(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        return f"error: 'old' must match exactly once, found {count} matches"
    p.write_text(text.replace(old, new), encoding="utf-8")
    return f"edited {path}"


def list_dir(path: str = ".") -> str:
    entries = sorted(_resolve(path).iterdir())
    return "\n".join(e.name + ("/" if e.is_dir() else "") for e in entries) or "(empty)"


def bash(command: str) -> str:
    # On Windows this runs through cmd.exe, so the model should use cmd syntax.
    try:
        r = subprocess.run(
            command, shell=True, cwd=WORKDIR, capture_output=True, text=True, timeout=30
        )
    except subprocess.TimeoutExpired:
        return "error: command timed out after 30s"
    return f"exit code {r.returncode}\n{r.stdout}{r.stderr}"


TOOLS = {f.__name__: f for f in (read_file, write_file, edit_file, list_dir, bash)}


def _schema(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


S = {"type": "string"}
TOOL_SCHEMAS = [
    _schema("read_file", "Read a UTF-8 text file.", {"path": S}, ["path"]),
    _schema("write_file", "Create or overwrite a file.", {"path": S, "content": S}, ["path", "content"]),
    _schema(
        "edit_file",
        "Replace one exact occurrence of 'old' with 'new' in a file.",
        {"path": S, "old": S, "new": S},
        ["path", "old", "new"],
    ),
    _schema("list_dir", "List files in a directory.", {"path": S}, []),
    _schema("bash", "Run a shell command and return its output.", {"command": S}, ["command"]),
]


def run_tool(name: str, raw_args: str) -> str:
    """Never raise: errors go back to the model as text so it can recover."""
    if name not in TOOLS:
        return f"error: unknown tool '{name}'"
    try:
        result = TOOLS[name](**json.loads(raw_args or "{}"))
    except Exception as e:  # noqa: BLE001
        return f"error: {type(e).__name__}: {e}"
    if len(result) > MAX_OUTPUT_CHARS:
        result = result[:MAX_OUTPUT_CHARS] + f"\n...[truncated {len(result) - MAX_OUTPUT_CHARS} chars]"
    return result


# ---------- model call with retry ----------

def call_model(messages):
    for attempt in range(5):
        try:
            return client.chat.completions.create(
                model=MODEL, messages=messages, tools=TOOL_SCHEMAS
            ).choices[0].message
        except (RateLimitError, InternalServerError, APIConnectionError) as e:
            wait = 2 ** attempt * 2
            print(f"  [retry {attempt + 1}/5 in {wait}s: {type(e).__name__}]")
            time.sleep(wait)
    sys.exit("giving up after 5 retries")


# ---------- the agent loop ----------

def run_agent(messages):
    for step in range(MAX_STEPS):
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
            result = run_tool(tc.function.name, tc.function.arguments)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    return "stopped: reached MAX_STEPS"


def main():
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"Stage 2 harness | model={MODEL} | cwd={WORKDIR} | 'exit' to quit")
    while True:
        try:
            user_input = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if user_input in ("exit", "quit"):
            break
        if not user_input:
            continue
        messages.append({"role": "user", "content": user_input})
        print(f"\nagent> {run_agent(messages)}")


if __name__ == "__main__":
    main()
