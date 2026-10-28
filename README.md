# Harness Engineering

Three parts, each a different way of looking at the same idea: a language model on its own only
produces text, and the **harness** around it (the loop, the tools, the permissions, the memory,
the checks) is what turns it into something that acts.

| Part | What it is | Code | Video |
|---|---|---|---|
| **A** | A coding agent built from scratch in four stages | [`part-a-harness/`](part-a-harness) | [VIDEO]([https://drive.google.com/file/d/1HNDsydR9sekH8N2RY65rPTQvaoaELUEZ/view?usp=sharing]) |
| **B** | The DeepSeek Harness, customized: a new mode and plugins written from scratch | [`part-b-deepseek/`](part-b-deepseek) | [Video](https://drive.google.com/file/d/1aNafVavO-ePK_3PJIrI9X-YhBdEQW24f/view?usp=sharing) |
| **C** | A guarded autoresearch harness that improves an ML model on its own | [`part-c-autoresearch/`](part-c-autoresearch) | [Video](https://drive.google.com/file/d/1mhXpbmHte2uF03c8WZcfljxqNV6xROqX/view?usp=sharing) |

Each folder has its own README with setup and run instructions. API keys are read from
environment variables and are never stored in the repo.

---

## Part A: a coding agent from scratch

Python, using the OpenRouter API (so the model behind it can be swapped freely). Built
progressively, one file per stage, each importing the one before:

| Stage | File | Adds |
|---|---|---|
| 1 | `stage1_loop.py` | the chat loop: a message list resent every turn |
| 2 | `stage2_tools.py` | tools (read, write, edit, list, bash), the agent loop, step limit, retry with backoff |
| 3 | `stage3_context.py` | token budget and two-tier context compaction, project memory, `/compact` `/tokens` `/clear` |
| 4 | `stage4_safety.py` | path sandbox, destructive-command denylist, human approval before writes and commands |

## Part B: customizing the DeepSeek Harness

The DeepSeek Harness (DSH) treats everything as a plugin, and a *mode* is just a list of plugins
in YAML. This part builds a custom **Second Brain** mode: seven built-in plugins plus two written
from scratch, using two different extension points.

- **`brain-notes`** (tool seam): `brain_save`, `brain_search`, `brain_read`, `brain_list` over a
  local markdown vault.
- **`brain-journal`** (event seam): listens to every tool result and keeps a daily journal.
- **`dsh-dice-roller`**: a Creator Mode demo. The model's first attempt failed to load; the
  README documents why, and the corrected plugin was verified in a live session log.
- Logic lives in modules with no harness imports, so it is unit-tested (16 tests).

## Part C: a guarded autoresearch harness

A Gemini model proposes one change at a time to a small GPT training script. The harness trains
it on the local GPU for a fixed 90 seconds, reads one score back, and keeps the change only if it
clearly beats the best so far. Otherwise it restores the previous file byte for byte.

Because the agent edits code that is then executed, the measurement is protected: a static guard
before each run, tamper detection after it, a held-out test score the model never sees, a
baseline measured twice, and a confirmation run for anything that looks like an improvement.

**One real run, RTX 5070 laptop GPU, 8 iterations:**

| | Baseline | After | Change |
|---|---|---|---|
| Validation bits per character | 3.28 | 2.14 | -35% |
| Held-out test | 3.80 | 2.53 | -33% |

The README in that folder explains what the agent actually found (mostly a regularization
effect, since the baseline over-fits) and the limitations, including run-to-run noise. A small
DSH plugin lets a DeepSeek Harness agent read the experiment's results (31 Python and 11
JavaScript tests).

---

## Repository layout

```
part-a-harness/        stage1_loop.py ... stage4_safety.py
part-b-deepseek/       dsh-second-brain/  dsh-dice-roller/  CREATOR_DEMO.md  read-session.mjs
part-c-autoresearch/   experiment/  src/autoresearch/  tests/  dsh-autoresearch/  runs/
```

## Notes

- The tools in this repo run model-generated code and commands. The guards and prompts reduce the
  risk but are **not** a sandbox. Run them on a machine where a mistake can do no harm.
- The DeepSeek Harness is a developer preview and its own docs say it has not been security audited.
