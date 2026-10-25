"""The research loop: propose, check, run, keep or revert, journal. Repeat.

Greedy hill climbing against the best score so far (not the previous candidate), strict
improvement only. Every non-improvement restores the exact previous bytes of the editable file.
"""
import re
import shutil
from pathlib import Path
from typing import Callable

from .guard import Protected, check_candidate
from .journal import Journal, make_diff
from .llm import LLM
from .runner import RunResult, run_experiment
from .task import Task

FENCE_RE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.DOTALL)
IDEA_RE = re.compile(r"^\s*IDEA:\s*(.+)$", re.MULTILINE)

REPLY_FORMAT = """Reply in exactly this format and nothing else:
IDEA: <one sentence describing the single change you are making>
```python
<the COMPLETE new contents of the editable file>
```"""


def parse_proposal(reply: str) -> tuple[str, str] | None:
    """Return (idea, full_source), taking the longest fenced block as the file."""
    blocks = FENCE_RE.findall(reply)
    if not blocks:
        return None
    idea = IDEA_RE.search(reply)
    source = max(blocks, key=len).rstrip() + "\n"  # exactly one trailing newline, however the model fenced it
    return (idea.group(1).strip() if idea else "(no idea stated)"), source


def build_prompt(task: Task, source: str, best: float, baseline: float, history: str) -> str:
    return (
        f"Metric: {task.metric} ({'lower' if task.direction == 'min' else 'higher'} is better).\n"
        f"Baseline: {baseline:.6f}. Current best: {best:.6f}.\n"
        f"Each run trains for {task.budget_seconds:.0f}s of wall-clock time.\n\n"
        f"Recent experiments (oldest first):\n{history}\n\n"
        f"Current contents of {task.editable.name}:\n```python\n{source}\n```\n\n"
        f"Make ONE focused change likely to improve the metric and not already tried above.\n"
        f"{REPLY_FORMAT}"
    )


def _pick(task: Task, runs: list[RunResult], better: bool) -> RunResult:
    """The best (or worst) successful run by the task's direction."""
    lower_is_better = task.direction == "min"
    return (min if lower_is_better == better else max)(runs, key=lambda r: r.score)


def _attempt(task: Task, candidate: str, protected: Protected) -> tuple[RunResult, list[Path]]:
    # newline="\n": on Windows write_text would otherwise save CRLF and every line would show as changed
    task.editable.write_text(candidate, encoding="utf-8", newline="\n")
    try:
        result = run_experiment(task)
    finally:
        tampered = protected.restore_tampered()
    return result, tampered


def run_loop(task: Task, llm: LLM, journal: Journal, iterations: int,
             log: Callable[[str], None] = print) -> list[dict]:
    program = (task.root / "program.md").read_text(encoding="utf-8")
    protected = Protected(task.protected)
    task.runs_dir.mkdir(exist_ok=True)

    baseline_copy = task.runs_dir / f"baseline-{task.editable.name}"
    if not baseline_copy.exists():
        shutil.copyfile(task.editable, baseline_copy)

    log(f"measuring current {task.editable.name} {task.baseline_runs}x to establish the score to beat ...")
    runs = []
    for _ in range(task.baseline_runs):
        run = run_experiment(task)
        if not run.ok:
            raise SystemExit(f"the starting file does not run: {run.error}")
        runs.append(run)
    first = _pick(task, runs, better=True)  # the best run is the bar: a bad outlier must not lower it
    best = first.score
    spread = max(r.score for r in runs) - min(r.score for r in runs)
    history = journal.read()
    is_first_session = not history
    baseline = history[0]["score"] if history else best
    journal.append(
        iteration=journal.next_iteration() - 1 if history else 0,
        idea="starting point" if is_first_session else "resumed from current file",
        decision="baseline" if is_first_session else "resume",
        score=first.score, test_score=first.test_score, best_before=None,
        repeats=[r.score for r in runs], log=first.log,
        seconds=round(first.seconds, 1), error="", diff="")
    log(f"starting {task.metric}: {best:.6f}  ({first.seconds:.0f}s per run; "
        f"{len(runs)} run(s), spread {spread:.4f}, min_delta {task.min_delta})")
    if spread > task.min_delta:
        log(f"  warning: the baseline runs differ by more than min_delta ({spread:.4f} > {task.min_delta})."
            " Results may be noise-limited.")

    records = []
    for _ in range(iterations):
        n = journal.next_iteration()
        backup = task.editable.read_bytes()
        current = backup.decode("utf-8")

        reply = llm.complete(program, build_prompt(task, current, best, baseline, journal.history_text()))
        proposal = parse_proposal(reply)
        if proposal is None:
            rec = journal.append(iteration=n, idea="(unparseable reply)", decision="no-proposal",
                                 score=None, test_score=None, best_before=best, seconds=0,
                                 error="reply had no code block", diff="")
            log(f"#{n} no usable proposal"); records.append(rec); continue

        idea, candidate = proposal
        problems = check_candidate(candidate, task.guard)
        if problems:
            rec = journal.append(iteration=n, idea=idea, decision="rejected", score=None,
                                 test_score=None, best_before=best, seconds=0,
                                 error="; ".join(problems), diff="")
            log(f"#{n} rejected by guard: {'; '.join(problems)}"); records.append(rec); continue

        result, tampered = _attempt(task, candidate, protected)
        repeats = [result.score]
        confirm_error = ""
        if not tampered and result.ok and task.confirm and task.improves(result.score, best):
            log(f"#{n} looks better ({result.score:.6f}); confirming with a second run ...")
            second, tampered = _attempt(task, candidate, protected)
            if second.ok:
                repeats.append(second.score)
                result = _pick(task, [result, second], better=False)  # judged on its WORSE run
            else:
                confirm_error = f"confirmation run failed: {second.error}"
        diff = make_diff(current, candidate)
        if tampered:
            decision, error = "tampered", f"modified protected file(s): {', '.join(p.name for p in tampered)}"
        elif confirm_error:
            decision, error = "failed", confirm_error
        elif not result.ok:
            decision, error = "failed", result.error
        elif task.improves(result.score, best):
            decision, error = "kept", ""
        else:
            decision, error = "reverted", ""

        best_before = best
        if decision == "kept":
            best = result.score
            shutil.copyfile(task.editable, task.runs_dir / f"best-{task.editable.name}")
        else:
            task.editable.write_bytes(backup)  # exact previous bytes

        rec = journal.append(iteration=n, idea=idea, decision=decision, score=result.score,
                             test_score=result.test_score, best_before=best_before,
                             repeats=repeats, log=result.log,
                             seconds=round(result.seconds, 1), error=error, diff=diff)
        shown = "n/a" if result.score is None else f"{result.score:.6f}"
        log(f"#{n} {decision.upper():9} score={shown} best={best:.6f}  {idea}")
        records.append(rec)
    return records


def summarize(records: list[dict], task: Task) -> str:
    """Table of every journal entry plus baseline vs best, on validation and held-out test."""
    if not records:
        return "journal is empty"
    base = records[0]
    kept = [r for r in records if r["decision"] == "kept"]
    best = kept[-1] if kept else base
    counts: dict[str, int] = {}
    for r in records[1:]:
        counts[r["decision"]] = counts.get(r["decision"], 0) + 1

    def fmt(x):
        return "n/a" if x is None else f"{x:.6f}"

    lines = [f"{'#':>3}  {'decision':9}  {'score':>10}  idea"]
    for r in records:
        lines.append(f"{r['iteration']:>3}  {r['decision']:9}  {fmt(r.get('score')):>10}  {r['idea'][:90]}")
    lines += ["",
              f"experiments: {sum(counts.values())}  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())),
              f"{task.metric} (validation): {fmt(base['score'])} -> {fmt(best['score'])}",
              f"held-out test score:        {fmt(base.get('test_score'))} -> {fmt(best.get('test_score'))}"]
    return "\n".join(lines)
