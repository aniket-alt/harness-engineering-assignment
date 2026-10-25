import pytest

from autoresearch.runner import run_experiment

from conftest import make_task


def run_with(tmp_path, source, **kw):
    task = make_task(tmp_path, **kw)
    task.editable.write_text(source, encoding="utf-8")
    return run_experiment(task)


def test_reads_score_and_heldout_test(tmp_path):
    r = run_with(tmp_path, "print('step 1 loss 3.2')\nprint('SCORE: 1.5')\nprint('TEST: 1.7')\n")
    assert (r.ok, r.score, r.test_score) == (True, 1.5, 1.7)


@pytest.mark.parametrize("body, fragment", [
    ("print('hello')", "no SCORE line"),
    ("print('SCORE: 1')\nprint('SCORE: 0')", "2 SCORE lines"),
    ("print('SCORE: nan')", "not finite"),
    ("print('SCORE: inf')", "not finite"),
    ("raise RuntimeError('boom')", "exit code 1"),
    ("print('score is 3')", "no SCORE line"),
])
def test_bad_runs_are_failures_not_crashes(tmp_path, body, fragment):
    r = run_with(tmp_path, body + "\n")
    assert not r.ok and r.score is None and fragment in r.error


def test_timeout_is_a_failure(tmp_path):
    r = run_with(tmp_path, "import time\ntime.sleep(30)\n", timeout=1)
    assert not r.ok and "timed out" in r.error
