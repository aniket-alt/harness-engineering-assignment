# Part C: A guarded autoresearch harness for ML experiments

An LLM (Gemini) proposes one change at a time to a small GPT training script. The harness runs
it on the local GPU under a fixed time budget, reads one number back, and keeps the change only
if it genuinely beats the best so far. Otherwise it restores the previous file byte for byte.

The pattern follows Karpathy's `autoresearch` (one editable file, one fixed evaluator, a fixed
wall-clock budget, keep or revert). The engineering effort goes into making the result
trustworthy when the thing being edited is also the thing being executed.

## Result (one real run, RTX 5070 Laptop GPU, `gemini-3.8-flash`, 8 iterations)

| | Baseline | After 8 iterations | Change |
|---|---|---|---|
| Validation bits/char (drives keep/revert) | 3.282 | **2.136** | -35% |
| Held-out test bits/char (never shown to the model) | 3.798 | **2.533** | -33% |

| # | Decision | Score | Change proposed |
|---|---|---|---|
| 0 | baseline | 3.282 | starting point |
| 1 | reverted | 4.285 | learned positions -> rotary embeddings |
| 2 | **kept** | 3.061 | batch size 64 -> 32 |
| 3 | reverted | 3.070 | exempt LayerNorm/bias parameters from weight decay |
| 4 | **kept** | 2.981 | GELU MLP -> SwiGLU MLP |
| 5 | reverted | 3.128 | depth 4 -> 6 layers |
| 6 | **kept** | 2.331 | batch size 32 -> 16 |
| 7 | **kept** | 2.136 | batch size 16 -> 8 |
| 8 | reverted | 2.213 | batch size 8 -> 4 |

The full journal, with every diff, is in `runs/journal.jsonl`. The final file is
`runs/best-train.py`; the starting file is `runs/baseline-train.py`.

### What the agent found, and what it means

The net change is two edits: **batch size 64 -> 8** and a **SwiGLU MLP**. Batch size did most of
the work, and it is worth understanding why. The baseline is deliberately naive and **over-fits**:
its training loss falls to about 0.7 nats while the validation score stays near 3 bits per
character, because 90 seconds of training makes well over 100 passes over a 1 MB text. A smaller
batch means each step sees less data, so the model makes fewer passes over the training set in
the same time. The agent found a real regularization effect, not a modelling breakthrough.

Evidence that the gain is real and not tuning to the validation set: the held-out test score
improved by almost the same amount (3.80 -> 2.53), and the agent never saw it.

## How it works

```
task.toml          what is editable, what is protected, the metric, the guard rules
program.md         the researcher's instructions (the human's main lever)
experiment/
  prepare.py       FIXED: data, 90 s budget, evaluator (validation score + held-out test score)
  train.py         EDITABLE: a small character-level GPT
src/autoresearch/
  loop.py          propose -> check -> run -> keep or revert -> journal
  guard.py         static checks before a run; tamper detection after it
  runner.py        runs the experiment as a subprocess and reads one number back
  journal.py       append-only JSONL history
  llm.py           model boundary (Gemini or OpenRouter, plus a scripted model for tests)
  cli.py           autoresearch {eval, run, report, restore, models, ping}
tests/             31 tests, no GPU, network or API key needed
dsh-autoresearch/  a DeepSeek Harness plugin that reads the journal (see below)
```

### Protecting the measurement

The agent edits code that is then executed, so the evaluator cannot be taken on trust:

- **Static guard before a run.** A candidate must still call `prepare.evaluate`. It may not
  import `os`, `subprocess` or similar, use `open`/`exec`/`eval`, print the scoring words, alias
  or rebind the `prepare` module, or touch anything on it except an allow-list of names (so it
  cannot reach the validation or test data).
- **Tamper detection after a run.** The protected files are snapshotted and compared after every
  run. Any change is undone and the run is logged as `tampered`, never kept.
- **Held-out test score.** Logged for every run, never included in the model's prompt.
- **Exactly one `SCORE` line.** A duplicated, missing, non-finite or crashing result is a failed
  run. The loop continues.

### Handling noisy scores

Scores under a fixed wall-clock budget are noisy, and the run showed how much:

- **Baseline measured twice;** the better run is the bar to beat. A single bad outlier cannot
  lower the bar. (A first trial run had scored 3.24 for the same file that usually scored 2.74.)
- **Confirmation run.** A candidate that looks better is run again and judged on its **worse**
  run. Iteration 2 shows why: its two runs scored 3.061 and 2.761.
- **Minimum margin.** An improvement must exceed `min_delta` (0.02), not merely be lower.
- **Exact revert.** Every non-improvement restores the previous file's exact bytes.

## DeepSeek Harness plugin

`dsh-autoresearch/` is a bundle for the DeepSeek Harness from Part B. It gives a DSH agent three
**read-only** tools over `runs/`, so it can answer questions about an experiment from real data:

| Tool | Returns |
|---|---|
| `research_status` | counts of kept/reverted/rejected, validation and held-out test score before and after, the best change |
| `research_history` | the most recent experiments with decision, score, both confirmation runs and the idea tried |
| `research_best_diff` | the cumulative code change from the baseline to the best file |

It never starts a run and never edits a file. The logic is in `lib/report.js` with no harness
imports; `index.js` is a thin wrapper, the same pattern as the Part B plugins. Its 7 unit tests
include one that reads this project's real journal.

```powershell
cd dsh-autoresearch; npm test                                          # 7 tests
cd ..; npx @deepseek-ai/dsh plugin --profile web add ./dsh-autoresearch
npx @deepseek-ai/dsh web
```

Then ask a DSH agent, for example: `Use research_status and tell me how the experiment went.`
The plugin reads the project folder it ships inside by default; set `projectDir` in
`dsh-autoresearch/cordis.patch.yml` to point it elsewhere.

## Limitations

- **Noise.** The two baseline runs differed by 0.078, and the two runs of one early candidate by
  0.30, both well above `min_delta`. Early keep/revert decisions are therefore noise-limited
  (the harness prints a warning). Iteration 4's two runs differed by 0.15. Iterations 6 and 7,
  at smaller batch sizes where over-fitting is milder, were stable (differences of 0.015 and
  0.002). The overall gain of 1.15 bits is much larger than the early noise.
- **Throughput matters.** The score depends on how many steps fit in 90 seconds, which depends on
  GPU speed and temperature. The baseline trained 8,036 steps in the logged run and about 5,500
  in another where the laptop GPU was throttled, scoring 3.28 and 2.74. Because this baseline
  over-fits, more steps score worse. Scores are comparable within one run of the harness on one
  machine, not across machines.
- **One run, one seed.** This is a demonstration of the harness on one task, not a benchmark. The
  model's proposals vary between runs.
- **Greedy hill climbing** can get stuck in a local optimum.
- **The guard is not a sandbox.** A determined program could evade a static check. Run it on a
  machine where a misbehaving experiment can do no harm.

## Run it

Python 3.11+ and an NVIDIA GPU. Use a virtual environment.

```powershell
# CUDA build of PyTorch. Do NOT add PyPI as an extra index: pip then prefers a newer CPU-only build.
python -m venv .venv
.venv\Scripts\python -m pip install torch --index-url https://download.pytorch.org/whl/cu128
.venv\Scripts\python -m pip install -e ".[dev]"

$env:GEMINI_API_KEY = "..."                    # or AUTORESEARCH_PROVIDER=openrouter + OPENROUTER_API_KEY
.venv\Scripts\autoresearch ping                # check the model answers
.venv\Scripts\autoresearch eval                # one 90 s run of the current file
.venv\Scripts\autoresearch run -n 8            # the loop (about 30 minutes)
.venv\Scripts\autoresearch report              # print the journal as a table
.venv\Scripts\autoresearch restore             # put the original baseline back
.venv\Scripts\python -m pytest                 # 31 tests, no GPU or key needed
```

Set `AUTORESEARCH_BUDGET=10` for a quick smoke test of `experiment/train.py`.
