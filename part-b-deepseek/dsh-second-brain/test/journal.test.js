import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { Journal, dayStamp, formatEntry, summarizeArgs } from '../lib/journal.js'

async function withDir(fn) {
  const dir = await mkdtemp(join(tmpdir(), 'journal-'))
  try { await fn(dir) } finally { await rm(dir, { recursive: true, force: true }) }
}

const noon = new Date(2026, 9, 24, 12, 30, 5)

test('dayStamp is zero padded local date', () => {
  assert.equal(dayStamp(new Date(2026, 0, 5)), '2026-01-05')
})

test('formatEntry marks failures', () => {
  assert.equal(formatEntry({ time: noon, tool: 'bash', ok: true, args: '' }), '- 12:30:05 `bash` ok\n')
  assert.match(formatEntry({ time: noon, tool: 'bash', ok: false, args: '' }), /FAILED/)
})

test('summarizeArgs truncates and survives circular input', () => {
  assert.equal(summarizeArgs({ a: 'x'.repeat(200) }, 20).length, 23)
  const circular = {}
  circular.self = circular
  assert.equal(typeof summarizeArgs(circular, 20), 'string')
})

test('record writes a header once, then appends', () => withDir(async dir => {
  const journal = new Journal(dir)
  await journal.record({ tool: 'read_file', ok: true }, noon)
  await journal.record({ tool: 'bash', ok: false }, noon)
  const text = await readFile(journal.fileFor(noon), 'utf8')
  assert.equal(text.match(/# Journal/g).length, 1)
  assert.match(text, /`read_file` ok/)
  assert.match(text, /`bash` FAILED/)
}))

test('arguments are omitted unless includeArgs is on', () => withDir(async dir => {
  await new Journal(dir).record({ tool: 'bash', ok: true, args: { command: 'secret' } }, noon)
  assert.doesNotMatch(await new Journal(dir).today(noon), /secret/)
  await new Journal(dir, { includeArgs: true }).record({ tool: 'bash', ok: true, args: { command: 'visible' } }, noon)
  assert.match(await new Journal(dir).today(noon), /visible/)
}))

test('ignored tools are skipped; missing day reads as empty', () => withDir(async dir => {
  const journal = new Journal(dir, { ignoreTools: ['journal_today'] })
  assert.equal(await journal.record({ tool: 'journal_today', ok: true }, noon), false)
  assert.equal(await journal.today(noon), '')
}))
