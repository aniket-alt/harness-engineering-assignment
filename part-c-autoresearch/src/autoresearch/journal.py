"""Append-only experiment journal (JSONL). Written as each run finishes, so an interrupted
session keeps its progress, and read back both for the report and for the proposer's prompt."""
import difflib
import json
import time
from pathlib import Path

MAX_DIFF_CHARS = 6000


def make_diff(before: str, after: str) -> str:
    diff = "".join(difflib.unified_diff(
        before.splitlines(keepends=True), after.splitlines(keepends=True),
        fromfile="before", tofile="after", n=2))
    return diff if len(diff) <= MAX_DIFF_CHARS else diff[:MAX_DIFF_CHARS] + "\n...[diff truncated]"


class Journal:
    def __init__(self, path: Path):
        self.path = Path(path)

    def append(self, **record) -> dict:
        record = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), **record}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return record

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        records = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a torn last line from an interrupted write
        return records

    def next_iteration(self) -> int:
        return max((r.get("iteration", 0) for r in self.read()), default=0) + 1

    def history_text(self, limit: int = 15) -> str:
        """Compact recent history for the proposer. Held-out TEST scores are never included."""
        rows = [r for r in self.read() if r.get("decision") != "baseline"][-limit:]
        if not rows:
            return "(no experiments yet)"
        lines = []
        for r in rows:
            score = "n/a" if r.get("score") is None else f"{r['score']:.6f}"
            note = f" -- {r['error'][:140]}" if r.get("error") else ""
            lines.append(f"#{r['iteration']} [{r['decision']}] score={score} idea: {r['idea']}{note}")
        return "\n".join(lines)
