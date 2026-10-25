from autoresearch.guard import Protected, check_candidate
from autoresearch.task import Guard

GUARD = Guard(
    forbidden_imports=("os", "subprocess"), forbidden_names=("open", "exec"),
    forbidden_attrs=("save",), forbidden_text=("SCORE",), required_calls=("prepare.evaluate",),
)
GOOD = "import prepare\nimport torch\nx = torch.zeros(2)\nprepare.evaluate(x)\n"


def test_clean_candidate_passes():
    assert check_candidate(GOOD, GUARD) == []


def test_forbidden_import_name_attr_and_text_are_flagged():
    bad = GOOD + "import os\nopen('x')\nx.save('f')\nprint('SCORE: 0')\n"
    problems = " | ".join(check_candidate(bad, GUARD))
    for expected in ("'os'", "'open'", "'save'", "'SCORE'"):
        assert expected in problems


def test_from_import_is_checked():
    assert any("subprocess" in p for p in check_candidate(GOOD + "from subprocess import run\n", GUARD))


def test_evaluate_call_is_required():
    assert any("prepare.evaluate" in p for p in check_candidate("import prepare\nx = 1\n", GUARD))


ALLOW = Guard(module_allowlist={"prepare": ("evaluate", "get_batch")})


def test_module_allowlist_blocks_reaching_into_the_evaluator():
    attacks = {
        "reads validation tensor": "import prepare\nprepare._VAL.copy_(prepare._TRAIN[:5])\n",
        "rebinds the budget": "import prepare\nprepare.TIME_BUDGET_SECONDS = 1e9\n",
        "aliases the module": "import prepare as p\np.evaluate\n",
        "from-imports private name": "from prepare import _VAL\n",
        "augmented assignment": "import prepare\nprepare.EVAL_BLOCK += 1\n",
    }
    for label, source in attacks.items():
        assert check_candidate(source, ALLOW), f"{label} was not flagged"


def test_module_allowlist_permits_the_listed_names():
    ok = "import prepare\nfrom prepare import evaluate\nx = prepare.get_batch(1, 2, 'cpu')\nprepare.evaluate(x)\n"
    assert check_candidate(ok, ALLOW) == []


def test_syntax_error_and_size_limit():
    assert any("syntax error" in p for p in check_candidate("def broken(:\n", GUARD))
    assert any("larger" in p for p in check_candidate("x = 1\n" * 10, Guard(max_bytes=5)))


def test_protected_files_are_restored_when_modified_or_deleted(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("keep")
    b.write_text("keep")
    snap = Protected((a, b))
    assert snap.restore_tampered() == []
    a.write_text("changed")
    b.unlink()
    assert sorted(p.name for p in snap.restore_tampered()) == ["a.txt", "b.txt"]
    assert a.read_text() == "keep" and b.read_text() == "keep"
