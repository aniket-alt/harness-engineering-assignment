// Plugin 1: "brain-notes" -- a second brain as model-callable tools (the TOOL seam).
// The model can save, search, read and list markdown notes stored in a local vault.
import Schema from '@deepseek-ai/schemastery'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { snippet, Vault } from './lib/vault.js'

export const name = 'brain-notes'
export const inject = ['tools']

export const Config = Schema.object({
  vaultDir: Schema.string().default(join(homedir(), '.dsh', 'brain')),
  maxResults: Schema.number().default(5),
})

const text = (_args, value) => [{ type: 'text', text: value }]
const asText = { schema: { type: 'string' }, render: text }

export function apply(ctx, config) {
  const vault = new Vault(config.vaultDir)

  ctx.tools.register(defineTool({
    name: 'brain_save',
    description:
      'Save a note to the second brain (a local markdown vault). Use it for facts, decisions and ' +
      'lessons worth remembering across sessions. Saving with an existing title updates that note.',
    parameters: {
      title: { type: 'string', required: true, description: 'Short unique title' },
      content: { type: 'string', required: true, description: 'Note body in markdown' },
      tags: { type: 'string', description: 'Comma-separated tags, e.g. "python,testing"' },
    },
    output: asText,
    async execute(args) {
      const { id, existed } = await vault.save(args)
      return `${existed ? 'updated' : 'saved'} note "${id}"`
    },
  }))

  ctx.tools.register(defineTool({
    name: 'brain_search',
    description:
      'Search the second brain by keywords (title and tag matches rank higher than body matches). ' +
      'Check this BEFORE answering questions about the user\'s past work, preferences or decisions.',
    parameters: {
      query: { type: 'string', required: true, description: 'Space-separated keywords' },
      limit: { type: 'number', description: `Max results (default ${config.maxResults})` },
    },
    output: asText,
    async execute(args) {
      const limit = Math.min(Math.max(Math.trunc(args.limit ?? config.maxResults), 1), 20)
      const hits = await vault.search(args.query, limit)
      if (hits.length === 0) return 'no matching notes'
      return hits
        .map(n => `- ${n.id} [${n.tags.join(', ')}]: ${snippet(n.content, args.query)}`)
        .join('\n')
    },
  }))

  ctx.tools.register(defineTool({
    name: 'brain_read',
    description: 'Read one full note from the second brain by its id (as shown by brain_search or brain_list).',
    parameters: {
      id: { type: 'string', required: true, description: 'Note id, e.g. "pytest-fixtures"' },
    },
    output: asText,
    async execute(args) {
      const note = await vault.read(args.id)
      return `# ${note.title}\ntags: ${note.tags.join(', ')}\nupdated: ${note.updated}\n\n${note.content}`
    },
  }))

  ctx.tools.register(defineTool({
    name: 'brain_list',
    description: 'List all notes in the second brain, newest first.',
    parameters: {},
    output: asText,
    async execute() {
      const notes = await vault.all()
      if (notes.length === 0) return 'the second brain is empty'
      return notes.map(n => `- ${n.id} [${n.tags.join(', ')}] ${n.title}`).join('\n')
    },
  }))
}
