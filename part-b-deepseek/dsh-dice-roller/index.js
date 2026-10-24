// Corrected version of the plugin the free model first generated in Creator mode.
// The original failed because it used @cordisjs/core, CommonJS, ctx.provide and a
// non-array patch file. DSH wants an ES module that registers a tool through
// ctx.tools.register(defineTool(...)).
import { defineTool } from '@deepseek-ai/dsh-tools'
import { rollDie } from './roll.js'

export const name = 'dice-roller'
export const inject = ['tools']

export function apply(ctx) {
  ctx.tools.register(defineTool({
    name: 'dice',
    description: 'Roll a die and return the number. Defaults to a six-sided die.',
    parameters: {
      sides: { type: 'number', description: 'Number of sides, 2 to 1000 (default 6)' },
    },
    output: {
      schema: { type: 'string' },
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute(args) {
      const sides = args.sides ?? 6
      return `You rolled a ${rollDie(sides)} on a d${sides}.`
    },
  }))
}
