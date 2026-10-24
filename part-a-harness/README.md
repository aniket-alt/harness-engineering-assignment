# Part A: A coding-agent harness, built from scratch

A small coding agent built in four progressive stages. It talks to any model
through the OpenRouter API (OpenAI-compatible), so the backend can be a free
model or your own Gemini key added under OpenRouter's integrations.

## Setup

```powershell
pip install -r requirements.txt
$env:OPENROUTER_API_KEY = "sk-or-v1-..."          # never commit this
$env:OPENROUTER_MODEL   = "openrouter/free"        # optional; any OpenRouter model id
```

## Stages

Each stage is one file. Stages 2-4 build on the previous one.

| Stage | File | What it adds |
|---|---|---|
| 1 | `stage1_loop.py` | Chat loop. Keeps a message list and resends it every turn. |
| 2 | `stage2_tools.py` | Tools (`read_file`, `write_file`, `edit_file`, `list_dir`, `bash`), the agent loop (call model, run tools, repeat), step limit, retry with backoff. |
| 3 | `stage3_context.py` | OS-aware prompt, `AGENTS.md` project memory, token budget, two-tier compaction (elide old tool output, then summarize), `/clear /compact /tokens`. |
| 4 | `stage4_safety.py` | Path sandbox, destructive-command denylist, human approval for side-effecting tools. |

Run any stage with `python stageN_*.py`. Stage 4 is the one to use day to day.

## Design notes

- The harness is the loop around the model: messages in, tool calls out, results back in.
- Tool errors are returned to the model as text, so it can recover instead of crashing the run.
- Compaction cuts only at user-message boundaries so a tool call is never separated from its result.
- The denylist is a speed bump, not a security boundary. Real isolation needs a container or VM.
- Token counts are estimated (about 4 characters per token).
