"""Command line: autoresearch {eval,run,report,restore,models}."""
import argparse
import shutil
import sys
from pathlib import Path

from .journal import Journal
from .llm import from_env
from .loop import run_loop, summarize
from .runner import run_experiment
from .task import Task


def _task(args) -> Task:
    path = Path(args.task)
    if not path.exists():
        raise SystemExit(f"task file not found: {path} (run from the project folder or pass --task)")
    return Task.from_toml(path)


def cmd_eval(args):
    task = _task(args)
    result = run_experiment(task)
    if not result.ok:
        raise SystemExit(f"run failed: {result.error}")
    print(f"{task.metric}: {result.score:.6f}   held-out: {result.test_score}   ({result.seconds:.0f}s)")


def cmd_run(args):
    task = _task(args)
    run_loop(task, from_env(args.model), Journal(task.runs_dir / "journal.jsonl"), args.iterations)
    print("\n" + summarize(Journal(task.runs_dir / "journal.jsonl").read(), task))


def cmd_report(args):
    task = _task(args)
    print(summarize(Journal(task.runs_dir / "journal.jsonl").read(), task))


def cmd_restore(args):
    task = _task(args)
    baseline = task.runs_dir / f"baseline-{task.editable.name}"
    if not baseline.exists():
        raise SystemExit("no baseline copy found; nothing to restore")
    shutil.copyfile(baseline, task.editable)
    print(f"restored {task.editable.name} to the original baseline")


def cmd_models(args):
    for model in from_env(args.model).list_models():
        print(model)


def cmd_ping(args):
    llm = from_env(args.model)
    print(f"model: {llm.model}")
    print("reply:", llm.complete("You are a test endpoint.", "Reply with exactly the word: OK").strip())


def main(argv=None):
    parser = argparse.ArgumentParser(prog="autoresearch", description=__doc__)
    parser.add_argument("--task", default="task.toml", help="path to task.toml (default: ./task.toml)")
    parser.add_argument("--model", default=None, help="model id (default: $AUTORESEARCH_MODEL or provider default)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("eval", help="run the current file once and print its score").set_defaults(fn=cmd_eval)
    p = sub.add_parser("run", help="run the autonomous loop")
    p.add_argument("-n", "--iterations", type=int, default=8)
    p.set_defaults(fn=cmd_run)
    sub.add_parser("report", help="print the journal as a table").set_defaults(fn=cmd_report)
    sub.add_parser("restore", help="put the original baseline file back").set_defaults(fn=cmd_restore)
    sub.add_parser("models", help="list model ids the provider offers").set_defaults(fn=cmd_models)
    sub.add_parser("ping", help="send one tiny request to check the model answers").set_defaults(fn=cmd_ping)
    args = parser.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
