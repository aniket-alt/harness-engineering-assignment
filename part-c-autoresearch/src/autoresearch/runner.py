"""Run one experiment as a subprocess and read one number back.

The harness never imports the experiment. The only contract is on stdout:
exactly one line `SCORE: <float>` (and optionally one `TEST: <float>`, a held-out score the
proposer never sees). A crash, a timeout, a missing score or a duplicated score all count as a
failed run, so a bad candidate cannot stop the loop.
"""
import math
import re
import subprocess
import sys
import time
from dataclasses import dataclass

from .task import Task

_NUMBER = r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|nan|inf|-inf)"
SCORE_RE = re.compile(rf"^SCORE:\s*{_NUMBER}\s*$", re.MULTILINE | re.IGNORECASE)
TEST_RE = re.compile(rf"^TEST:\s*{_NUMBER}\s*$", re.MULTILINE | re.IGNORECASE)
TAIL_CHARS = 1500


@dataclass(frozen=True)
class RunResult:
    ok: bool
    score: float | None
    test_score: float | None
    seconds: float
    error: str = ""
    log: str = ""  # short stdout tail, e.g. the step count


def _one_float(regex: re.Pattern, text: str, label: str) -> tuple[float | None, str]:
    matches = regex.findall(text)
    if not matches:
        return None, f"no {label} line in output"
    if len(matches) > 1:
        return None, f"{len(matches)} {label} lines in output, expected exactly one"
    value = float(matches[0])
    if not math.isfinite(value):
        return None, f"{label} is not finite: {value}"
    return value, ""


def tail(text: str) -> str:
    text = text.strip()
    return text if len(text) <= TAIL_CHARS else "..." + text[-TAIL_CHARS:]


def run_experiment(task: Task) -> RunResult:
    command = [sys.executable if c == "python" else c for c in task.command]
    start = time.monotonic()
    try:
        proc = subprocess.run(
            command, cwd=task.root, capture_output=True, text=True,
            timeout=task.timeout_seconds, env=None,
        )
    except subprocess.TimeoutExpired:
        return RunResult(False, None, None, time.monotonic() - start,
                         f"timed out after {task.timeout_seconds:.0f}s")
    seconds = time.monotonic() - start

    if proc.returncode != 0:
        return RunResult(False, None, None, seconds,
                         f"exit code {proc.returncode}: {tail(proc.stderr or proc.stdout)}")
    score, problem = _one_float(SCORE_RE, proc.stdout, "SCORE")
    if score is None:
        return RunResult(False, None, None, seconds, f"{problem}: {tail(proc.stdout)}")
    test_score, _ = _one_float(TEST_RE, proc.stdout, "TEST")
    return RunResult(True, score, test_score, seconds, log=tail(proc.stdout)[-300:])
