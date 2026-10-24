# Creator Mode demo: generate a plugin from one sentence

Creator mode lets the agent author, install and inspect plugins from chat. This documents a
real run, including the failure, because the failure is the instructive part.

## Prompt 1 (Creator mode, `google/gemini-3.1-flash-lite`)

```
Add a tool called dice that rolls a six-sided die and returns the number.
```

The agent read the `cordis-plugin-development` skill and the templates, wrote a plugin into the
workspace, installed it as a bundle, and replied that it was "successfully implemented and
installed."

## It was not working

`npx @deepseek-ai/dsh web --dump-config` printed:

```
dsh: [dice-roller] patch: entry "dice-roller" not found
```

Reading the generated files showed four mistakes against DSH's actual plugin contract:

| | Generated | DSH expects |
|---|---|---|
| Import | `@cordisjs/core` | `@deepseek-ai/cordis` |
| Module style | CommonJS `require` | ES module, `export function apply` |
| Tool registration | `ctx.provide('tool', {...})` | `ctx.tools.register(defineTool({...}))` |
| `cordis.patch.yml` | a map with `main:` | an array of `- insert:` rows |

Lesson: an agent's "it worked" is a claim, not evidence. `--dump-config` and the tool catalog
are the evidence.

## The corrected plugin (`dsh-dice-roller/`)

Written by hand using the same contract the docs describe, then installed with:

```powershell
npx @deepseek-ai/dsh plugin --profile web add ./dsh-dice-roller
```

- `roll.js` holds the pure dice logic; 3 unit tests (`npm test` in that folder).
- `index.js` registers the `dice` tool with an optional `sides` parameter.
- `cordis.patch.yml` inserts the plugin at host level.

`--dump-config` now shows a clean `# == dsh-dice-roller` layer with no "not found" error.

## Verified result

Prompts `Use the dice tool to roll a die.` and `roll a 20-sided die` (model
`cohere/north-mini-code:free`). The trajectory, read with `node read-session.mjs`:

```
TOOL CALL turn 2: dice({})
RESULT    You rolled a 1 on a d6.
TOOL CALL turn 3: dice({"sides":20})
RESULT    You rolled a 6 on a d20.
```

The tool results come from the plugin, not from the model. The model only rephrased them
("You rolled a 1 (on a standard 6-sided die)"). The first turn shows five `llm/retry` events
from rate limiting before it was resent.

## Inspecting a run

`read-session.mjs` decodes the append-only session log (many concatenated zstd frames) and
prints each user message, tool call, result and retry. This is the "inspect the trajectory"
step from the Creator-mode workflow.
