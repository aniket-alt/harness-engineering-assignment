# Part B: Customizing the DeepSeek Harness (DSH)

DSH is DeepSeek's open-source agent harness. Everything in it is a Cordis plugin, and a
**mode** (Standard, Code, Minimal, Creator) is just a *preset*: a YAML list of plugins.
This part adds a custom **Second Brain** mode made of 7 built-in plugins plus 2 plugins
written from scratch, packaged as one installable bundle.

## What is in this folder

```
part-b-deepseek/
  dsh-second-brain/          <- the bundle (installed into the DSH "web" profile)
    package.json             declares dsh.bundle, exports the two plugins
    cordis.patch.yml         the "Second Brain" preset (mode) definition
    brain-notes.js           plugin 1: tools (TOOL seam)
    brain-journal.js         plugin 2: event listener + tool (EVENT seam)
    lib/vault.js             note storage and search (no harness imports)
    lib/journal.js           journal formatting and appending (no harness imports)
    test/                    13 unit tests (node:test)
```

## The Second Brain mode

| # | Plugin | Kind | Role in the mode |
|---|---|---|---|
| 1 | `dsh-tool-pwsh` / `dsh-tool-bash` | built-in | run shell commands (PowerShell on Windows) |
| 2 | `dsh-tool-fs` | built-in | read, write and edit files |
| 3 | `dsh-tool-fs-search` | built-in | grep and glob |
| 4 | `dsh-tool-todo` | built-in | task tracking |
| 5 | `dsh-tool-web` | built-in | web fetch and search |
| 6 | `dsh-plan-mode` | built-in | read-only planning phase, told to consult past notes |
| 7 | `dsh-compaction-basic` + `command-compact` + `tool-result-pruner` | built-in | context compaction |
| - | `dsh-tool-cordis`, plugin manager | built-in (Creator) | inspect the runtime and manage plugins |
| **A** | **`brain-notes`** | **written from scratch** | `brain_save`, `brain_search`, `brain_read`, `brain_list` |
| **B** | **`brain-journal`** | **written from scratch** | logs every tool call to a daily journal; `journal_today` |

The mode's persona tells the model to call `brain_search` before answering questions about
past work and to `brain_save` durable lessons.

### Why two different extension points

- **brain-notes** registers tools with the `tools` service (`ctx.tools.register(defineTool(...))`).
  The model decides when to call them.
- **brain-journal** listens to the harness's `tools/result` event (`ctx.on(...)`). It runs on
  every tool call whether or not the model asks, so the journal is complete by construction.
  Arguments are not logged unless `includeArgs: true`, because shell commands and URLs can
  contain secrets.

### Design choices worth knowing

- Notes are plain markdown files with frontmatter in `~/.dsh/brain/notes/`, so they open in
  any editor or in Obsidian. Search is keyword scoring (title 3x, tags 2x, body 1x), with no
  embeddings and no downloads.
- Note ids are slugs. `brain_read` rejects ids that do not match `[a-z0-9_-]`, so the model
  cannot read files outside the vault.
- Plugin logic lives in `lib/` with no harness imports, so it is unit-tested without booting DSH.
- Both plugins export a Schemastery `Config`, so `vaultDir` (and `includeArgs`, `ignoreTools`)
  can be changed in `cordis.patch.yml` without touching code.

## Install and run

Prerequisites: Node 24+, and pnpm (DSH's `dsh plugin` command shells out to it).

```powershell
npm install -g pnpm@11.28.5
cd part-b-deepseek
npx @deepseek-ai/dsh plugin --profile web add ./dsh-second-brain
npx @deepseek-ai/dsh web
```

In the browser, add the OpenRouter provider (Settings > Models > Third-party model provider >
`openrouter`), pick a model such as `openrouter/free`, open a new session and choose the
**Second Brain** mode.

Verify without the UI:

```powershell
npx @deepseek-ai/dsh web --dump-config      # shows a "# == dsh-second-brain" layer
cd dsh-second-brain; npm test               # 13 tests
npx @deepseek-ai/dsh plugin --profile web remove dsh-second-brain   # uninstall
```

## Demo prompts (Second Brain mode)

1. `What tools do you have? List their names.`
2. `Save a note titled "Pytest fixtures" with tags python,testing: fixtures share setup code, use scope="module" to reuse across tests.`
3. `Search my notes for fixtures.`
4. `What did you do today? Check the journal.`

Then inspect the results on disk:

```powershell
ls $HOME\.dsh\brain\notes
type $HOME\.dsh\brain\journal\*.md
```

Observed in testing: the note was written as `pytest-fixtures.md` with correct frontmatter,
and the journal recorded `brain_save` and `brain_search` automatically.

## Creator Mode demos

See [CREATOR_DEMO.md](CREATOR_DEMO.md): a plugin generated from one sentence, why it failed,
the corrected version (`dsh-dice-roller/`), and the verified trajectory. Run
`node read-session.mjs` to print the tool calls of the latest session.

## Known limitations

- The model must choose to call the brain tools. Free models sometimes skip tool calls.
- Search is keyword-based, so synonyms are not matched.
- DSH's own `SAFETY.md` warns that plugins run with your permissions, so only install plugins
  whose source you have read.
- DSH is a developer preview and the npm package version (0.2.1-rc.2) differs slightly from
  the source docs (0.2.1-rc.3) that were used as reference.
