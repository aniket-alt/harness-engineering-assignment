"""Stage 4: safety and permissions.

The model can now write files and run shell commands, so the harness must be the
safety layer. This stage wraps tool execution with:
  - a path sandbox: file tools may not touch anything outside the working folder
  - a hard denylist for obviously destructive shell commands
  - human approval for every side-effecting tool (y = once, a = always, n = deny)
A denial is returned to the model as an ordinary tool result so it can adapt.
"""
import json
import re

from stage2_tools import WORKDIR, run_tool
from stage3_context import repl

READ_ONLY = {"read_file", "list_dir"}
PATH_TOOLS = {"read_file", "write_file", "edit_file", "list_dir"}
DENY_PATTERNS = [
    r"\brm\s+-[a-z]*r[a-z]*f?\b",
    r"\brmdir\s+/s\b",
    r"\bdel\s+/[sfq]\b",
    r"\bformat\s+[a-z]:",
    r"\bshutdown\b",
    r"\bmkfs\b",
    r"curl[^|]*\|\s*(sh|bash)",
    r"Remove-Item[^\n]*-Recurse",
]
always_allowed: set[str] = set()


def inside_workdir(path: str) -> bool:
    return (WORKDIR / path).resolve().is_relative_to(WORKDIR)


def describe(name: str, args: dict) -> str:
    if name == "bash":
        return f"run command: {args.get('command')}"
    if name == "write_file":
        return f"write {len(args.get('content', ''))} chars to {args.get('path')}"
    if name == "edit_file":
        return f"edit {args.get('path')}: {args.get('old')!r} -> {args.get('new')!r}"
    return f"{name} {args}"


def guarded_run_tool(name: str, raw_args: str) -> str:
    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError:
        return "error: arguments were not valid JSON"

    if name in PATH_TOOLS and not inside_workdir(args.get("path", ".")):
        return f"error: blocked, path escapes the working folder ({WORKDIR})"

    if name == "bash":
        for pattern in DENY_PATTERNS:
            if re.search(pattern, args.get("command", ""), re.IGNORECASE):
                return "error: blocked, command matches the destructive-command denylist"

    if name not in READ_ONLY and name not in always_allowed:
        answer = input(f"  [approve?] {describe(name, args)}  [y/n/a] ").strip().lower()
        if answer == "a":
            always_allowed.add(name)
        elif answer != "y":
            return "error: the user denied this action"

    return run_tool(name, raw_args)


if __name__ == "__main__":
    repl("Stage 4 harness (guarded)", tool_runner=guarded_run_tool)
