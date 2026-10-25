"""Static checks on a candidate before it runs, and tamper detection after it runs.

The agent edits code that is then executed, so the evaluator's integrity cannot rest on trust.
Two layers: (1) reject candidates that look like they are trying to touch the measurement,
(2) hash the protected files around every run and undo any change.

These are guardrails, not a sandbox: a determined program could still evade a static check.
Run on a machine where a misbehaving experiment can do no damage.
"""
import ast
import hashlib
from pathlib import Path

from .task import Guard


def dotted(node: ast.AST) -> str | None:
    """'a.b.c' for a chain of attribute/name nodes, else None."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def check_candidate(source: str, guard: Guard) -> list[str]:
    """Return a list of problems; empty means the candidate may run."""
    if len(source.encode("utf-8")) > guard.max_bytes:
        return [f"file is larger than {guard.max_bytes} bytes"]
    problems = [f"contains forbidden text {t!r}" for t in guard.forbidden_text if t in source]
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return problems + [f"syntax error: {e.msg} (line {e.lineno})"]

    called = set()
    allow = guard.module_allowlist
    for node in ast.walk(tree):
        # Allow-listed modules (e.g. the fixed evaluator): no aliasing, no assignment to their
        # attributes, no `from m import x` of anything off the list, and no off-list attribute.
        if isinstance(node, ast.Import):
            problems += [f"must not alias module {a.name!r}" for a in node.names
                         if a.name in allow and a.asname]
        if isinstance(node, ast.ImportFrom) and node.module in allow:
            problems += [f"may not import {a.name!r} from {node.module!r}"
                         for a in node.names if a.name not in allow[node.module]]
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in allow):
            if not isinstance(node.ctx, ast.Load):
                problems.append(f"must not assign to {node.value.id}.{node.attr}")
            elif node.attr not in allow[node.value.id]:
                problems.append(f"may not use {node.value.id}.{node.attr}")

        if isinstance(node, ast.Import):
            roots = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            roots = [(node.module or "").split(".")[0]]
        else:
            roots = []
        problems += [f"imports forbidden module {r!r}" for r in roots if r in guard.forbidden_imports]

        if isinstance(node, ast.Name) and node.id in guard.forbidden_names:
            problems.append(f"uses forbidden name {node.id!r}")
        if isinstance(node, ast.Attribute) and node.attr in guard.forbidden_attrs:
            problems.append(f"uses forbidden attribute {node.attr!r}")
        if isinstance(node, ast.Call) and (name := dotted(node.func)):
            called.add(name)

    problems += [f"must still call {c}()" for c in guard.required_calls if c not in called]
    return sorted(set(problems))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Protected:
    """Snapshot protected files; detect and undo modifications."""

    def __init__(self, paths: tuple[Path, ...]):
        self._bytes = {p: p.read_bytes() for p in paths}

    def restore_tampered(self) -> list[Path]:
        tampered = []
        for path, original in self._bytes.items():
            if not path.exists() or path.read_bytes() != original:
                path.write_bytes(original)
                tampered.append(path)
        return tampered
