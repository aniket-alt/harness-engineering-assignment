import json

from autoresearch.llm import ScriptedLLM
from autoresearch.loop import parse_proposal, run_loop, summarize
from autoresearch.task import Guard

from conftest import FENCE, make_task, reply

SRC = "X = {x}\nprint(f'SCORE: {{X}}')\n"
QUIET = dict(log=lambda *_: None)


def decisions(journal):
    return [r["decision"] for r in journal.read()]


def test_parse_proposal_takes_longest_block_and_idea():
    text = f"IDEA: bigger lr\nsome words {FENCE}x{FENCE} more\n{FENCE}python\nline1\nline2\n{FENCE}"
    assert parse_proposal(text) == ("bigger lr", "line1\nline2\n")
    assert parse_proposal("no code here") is None


def test_keeps_improvements_and_reverts_the_rest(task, journal):
    original = task.editable.read_bytes()
    llm = ScriptedLLM([reply("lower x", SRC.format(x=3)), reply("worse", SRC.format(x=9)),
                       reply("tie", SRC.format(x=3))])
    run_loop(task, llm, journal, 3, **QUIET)
    assert decisions(journal) == ["baseline", "kept", "reverted", "reverted"]  # a tie is not progress
    assert task.editable.read_text() == SRC.format(x=3)
    assert (task.runs_dir / "baseline-train.py").read_bytes() == original
    assert (task.runs_dir / "best-train.py").read_text() == SRC.format(x=3)


def test_candidates_are_saved_with_lf_line_endings_so_diffs_stay_small(task, journal):
    run_loop(task, ScriptedLLM([reply("lower", SRC.format(x=3))]), journal, 1, **QUIET)
    assert b"\r\n" not in task.editable.read_bytes()
    assert b"\r\n" not in (task.runs_dir / "best-train.py").read_bytes()


def test_every_non_improvement_restores_exact_previous_bytes(task, journal):
    before = task.editable.read_bytes()
    run_loop(task, ScriptedLLM([reply("worse", SRC.format(x=9))]), journal, 1, **QUIET)
    assert task.editable.read_bytes() == before


def test_crashing_candidate_is_failed_and_loop_continues(task, journal):
    llm = ScriptedLLM([reply("crash", "raise SystemExit(3)\n"), reply("good", SRC.format(x=2))])
    run_loop(task, llm, journal, 2, **QUIET)
    assert decisions(journal) == ["baseline", "failed", "kept"]


def test_unparseable_reply_and_guard_rejection_never_run(tmp_path, journal):
    task = make_task(tmp_path, guard=Guard(forbidden_imports=("os",)))
    llm = ScriptedLLM(["I refuse to use the format", reply("sneaky", "import os\nprint('SCORE: 0')\n")])
    run_loop(task, llm, journal, 2, **QUIET)
    assert decisions(journal) == ["baseline", "no-proposal", "rejected"]
    assert task.editable.read_text() == SRC.format(x=5)


def test_tampering_with_the_evaluator_is_detected_undone_and_not_kept(task, journal):
    evaluator = task.root / "experiment" / "prepare.py"
    cheat = ("p = r'" + str(evaluator) + "'\n"
             "f = open(p, 'w'); f.write('hacked'); f.close()\nprint('SCORE: -999')\n")
    run_loop(task, ScriptedLLM([reply("cheat", cheat)]), journal, 1, **QUIET)
    assert decisions(journal) == ["baseline", "tampered"]
    assert evaluator.read_text() == "# the fixed evaluator\n"
    assert task.editable.read_text() == SRC.format(x=5)


def test_maximize_direction(tmp_path, journal):
    task = make_task(tmp_path, direction="max")
    llm = ScriptedLLM([reply("up", SRC.format(x=8)), reply("down", SRC.format(x=2))])
    run_loop(task, llm, journal, 2, **QUIET)
    assert decisions(journal) == ["baseline", "kept", "reverted"]


def test_gains_within_the_noise_margin_are_not_kept(tmp_path, journal):
    from dataclasses import replace
    task = replace(make_task(tmp_path), min_delta=0.5)
    llm = ScriptedLLM([reply("tiny gain", SRC.format(x=4.8)), reply("real gain", SRC.format(x=4)),
                       reply("another tiny", SRC.format(x=3.7))])
    run_loop(task, llm, journal, 3, **QUIET)
    assert decisions(journal) == ["baseline", "reverted", "kept", "reverted"]
    assert task.editable.read_text() == SRC.format(x=4)


# A run whose score depends on how many times it has been run (state lives in count.txt).
def sequence(*scores):
    return (
        "import os\n"
        "n = int(open('count.txt').read()) if os.path.exists('count.txt') else 0\n"
        "open('count.txt', 'w').write(str(n + 1))\n"
        f"scores = {list(scores)}\n"
        "print(f'SCORE: {scores[min(n, len(scores) - 1)]}')\n"
    )


def test_a_lucky_first_run_is_not_kept_when_the_confirmation_run_disagrees(tmp_path, journal):
    from dataclasses import replace
    task = replace(make_task(tmp_path), confirm=True)
    # candidate: run 1 scores 1 (looks great), confirmation run scores 9 (the truth)
    run_loop(task, ScriptedLLM([reply("lucky", sequence(1, 9))]), journal, 1, **QUIET)
    rec = journal.read()[-1]
    assert rec["decision"] == "reverted" and rec["repeats"] == [1.0, 9.0]
    assert task.editable.read_text() == SRC.format(x=5)


def test_a_consistent_improvement_survives_confirmation(tmp_path, journal):
    from dataclasses import replace
    task = replace(make_task(tmp_path), confirm=True)
    run_loop(task, ScriptedLLM([reply("real", SRC.format(x=3))]), journal, 1, **QUIET)
    rec = journal.read()[-1]
    assert rec["decision"] == "kept" and rec["repeats"] == [3.0, 3.0]


def test_baseline_is_measured_repeatedly_and_the_best_run_is_the_bar(tmp_path, journal):
    from dataclasses import replace
    task = replace(make_task(tmp_path), baseline_runs=2)
    task.editable.write_text(sequence(8, 4), encoding="utf-8")  # a bad outlier, then a normal run
    run_loop(task, ScriptedLLM([reply("meh", SRC.format(x=4.5))]), journal, 1, **QUIET)
    base = journal.read()[0]
    assert base["score"] == 4.0 and base["repeats"] == [8.0, 4.0]
    assert journal.read()[-1]["decision"] == "reverted"  # 4.5 does not beat the bar of 4


def test_prompt_shows_history_but_never_the_heldout_score(task, journal):
    task.editable.write_text("print('SCORE: 5')\nprint('TEST: 123.456')\n", encoding="utf-8")
    llm = ScriptedLLM([reply("a", SRC.format(x=4)), reply("b", SRC.format(x=3))])
    run_loop(task, llm, journal, 2, **QUIET)
    second_prompt = llm.prompts[1][1]
    assert "#1 [kept]" in second_prompt and "idea: a" in second_prompt
    assert "123.456" not in second_prompt


def test_journal_persists_and_a_second_session_continues_numbering(task, journal):
    run_loop(task, ScriptedLLM([reply("a", SRC.format(x=4))]), journal, 1, **QUIET)
    run_loop(task, ScriptedLLM([reply("b", SRC.format(x=1))]), journal, 1, **QUIET)
    its = [r["iteration"] for r in journal.read() if r["decision"] in ("kept", "reverted")]
    assert its == [1, 2]
    json.loads(journal.path.read_text().splitlines()[-1])  # every line is valid JSON


def test_summary_reports_baseline_to_best(task, journal):
    llm = ScriptedLLM([reply("a", SRC.format(x=4)), reply("b", SRC.format(x=7))])
    run_loop(task, llm, journal, 2, **QUIET)
    text = summarize(journal.read(), task)
    assert "5.000000 -> 4.000000" in text and "kept=1" in text and "reverted=1" in text
