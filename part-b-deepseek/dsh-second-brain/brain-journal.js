// Plugin 2: "brain-journal" -- an automatic daily journal (the EVENT seam).
// It listens to the harness's `tools/result` event and appends one line per tool call to
// <vault>/journal/YYYY-MM-DD.md. The model also gets a `journal_today` tool to read it back.
import Schema from '@deepseek-ai/schemastery'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { Journal } from './lib/journal.js'

export const name = 'brain-journal'
export const inject = ['tools']

export const Config = Schema.object({
  vaultDir: Schema.string().default(join(homedir(), '.dsh', 'brain')),
  // Arguments can contain secrets (shell commands, URLs), so they are off by default.
  includeArgs: Schema.boolean().default(false),
  ignoreTools: Schema.array(Schema.string()).default(['journal_today']),
})

export function apply(ctx, config) {
  const journal = new Journal(config.vaultDir, {
    ignoreTools: config.ignoreTools,
    includeArgs: config.includeArgs,
  })

  ctx.on('tools/result', (exec, result) => {
    // Observers must not throw or block the agent: record in the background and log failures.
    journal
      .record({ tool: exec.name, ok: !result.isError, args: exec.arguments })
      .catch(err => console.error('[brain-journal] could not write journal:', err.message))
  })

  ctx.tools.register(defineTool({
    name: 'journal_today',
    description: 'Show today\'s tool-call journal: a timestamped list of what was done in this and other sessions today.',
    parameters: {},
    output: { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] },
    async execute() {
      return (await journal.today()) || 'nothing journaled yet today'
    },
  }))
}
