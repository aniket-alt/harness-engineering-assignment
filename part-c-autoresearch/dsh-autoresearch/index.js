// "autoresearch-reader": read-only DSH tools over the Part C autoresearch journal, so a DSH agent
// can answer "how did the experiment go?" and "what changed?" from real data.
// It never starts a run and never edits anything.
import Schema from '@deepseek-ai/schemastery'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { bestDiff, historyText, readJournal, summarize } from './lib/report.js'

export const name = 'autoresearch-reader'
export const inject = ['tools']

const here = dirname(fileURLToPath(import.meta.url))

export const Config = Schema.object({
  // Default: the autoresearch project this bundle ships inside (its parent folder).
  projectDir: Schema.string().default(resolve(here, '..')),
})

const asText = { schema: { type: 'string' }, render: (_args, value) => [{ type: 'text', text: value }] }

export function apply(ctx, config) {
  ctx.tools.register(defineTool({
    name: 'research_status',
    description:
      'Summarize the autoresearch experiment: how many changes were tried, kept and reverted, ' +
      'and the validation and held-out test scores before and after. Read-only.',
    parameters: {},
    output: asText,
    async execute() {
      return summarize(await readJournal(config.projectDir))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'research_history',
    description:
      'List the most recent autoresearch experiments with their decision (kept, reverted, rejected, ' +
      'failed), score and the idea that was tried. Read-only.',
    parameters: {
      limit: { type: 'number', description: 'How many recent experiments to show (default 10, max 50)' },
    },
    output: asText,
    async execute(args) {
      const limit = Math.min(Math.max(Math.trunc(args.limit ?? 10), 1), 50)
      return historyText(await readJournal(config.projectDir), limit)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'research_best_diff',
    description:
      'Show the cumulative code change between the original baseline training script and the best ' +
      'version found (lines starting with - were removed, + were added). Read-only.',
    parameters: {},
    output: asText,
    async execute() {
      return bestDiff(config.projectDir)
    },
  }))
}
