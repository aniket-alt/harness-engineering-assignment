import textwrap

import pytest

from autoresearch.journal import Journal
from autoresearch.task import Guard, Task


def make_task(tmp_path, guard=None, direction="min", timeout=20):
    """A fake experiment: the score is the constant X in train.py."""
    (tmp_path / "experiment").mkdir()
    (tmp_path / "experiment" / "prepare.py").write_text("# the fixed evaluator\n", encoding="utf-8")
    (tmp_path / "experiment" / "train.py").write_text("X = 5\nprint(f'SCORE: {X}')\n", encoding="utf-8")
    (tmp_path / "program.md").write_text("You are a researcher.\n", encoding="utf-8")
    return Task(
        root=tmp_path, name="fake", editable=tmp_path / "experiment" / "train.py",
        protected=(tmp_path / "experiment" / "prepare.py", tmp_path / "program.md"),
        command=("python", "experiment/train.py"), budget_seconds=1, timeout_seconds=timeout,
        metric="loss", direction=direction, guard=guard or Guard(),
    )


FENCE = "`" * 3


def reply(idea, source):
    return f"IDEA: {idea}\n{FENCE}python\n{textwrap.dedent(source)}\n{FENCE}"


@pytest.fixture
def task(tmp_path):
    return make_task(tmp_path)


@pytest.fixture
def journal(tmp_path):
    return Journal(tmp_path / "runs" / "journal.jsonl")
