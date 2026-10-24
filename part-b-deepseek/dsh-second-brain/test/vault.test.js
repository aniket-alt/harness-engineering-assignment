import assert from 'node:assert/strict'
import { mkdtemp, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import { Vault, parseTags, slugify, snippet } from '../lib/vault.js'

async function withVault(fn) {
  const dir = await mkdtemp(join(tmpdir(), 'brain-'))
  try { await fn(new Vault(dir)) } finally { await rm(dir, { recursive: true, force: true }) }
}

test('slugify makes safe ids', () => {
  assert.equal(slugify('Pytest Fixtures: A Guide!'), 'pytest-fixtures-a-guide')
  assert.equal(slugify('../../etc/passwd'), 'etc-passwd')
  assert.equal(slugify('!!!'), 'untitled')
})

test('parseTags dedupes and normalizes', () => {
  assert.deepEqual(parseTags(' Python, testing ,python,'), ['python', 'testing'])
  assert.deepEqual(parseTags(undefined), [])
})

test('save then read round-trips; saving again updates', () => withVault(async vault => {
  const first = await vault.save({ title: 'Deploy checklist', content: 'run tests first', tags: 'ops' })
  assert.deepEqual(first, { id: 'deploy-checklist', existed: false })
  const second = await vault.save({ title: 'Deploy checklist', content: 'run tests, then migrate', tags: 'ops,db' })
  assert.equal(second.existed, true)
  const note = await vault.read('deploy-checklist')
  assert.equal(note.content.trim(), 'run tests, then migrate')
  assert.deepEqual(note.tags, ['ops', 'db'])
}))

test('read rejects path traversal ids', () => withVault(async vault => {
  await assert.rejects(vault.read('../secret'), /invalid note id/)
  await assert.rejects(vault.read('a/b'), /invalid note id/)
}))

test('search ranks title above body and ignores non-matches', () => withVault(async vault => {
  await vault.save({ title: 'Docker tips', content: 'use multi-stage builds', tags: 'ops' })
  await vault.save({ title: 'Misc', content: 'docker docker', tags: '' })
  await vault.save({ title: 'Unrelated', content: 'nothing here', tags: '' })
  const hits = await vault.search('docker')
  assert.deepEqual(hits.map(n => n.id), ['docker-tips', 'misc'])
  assert.deepEqual(await vault.search('zzz'), [])
  assert.deepEqual(await vault.search('   '), [])
}))

test('empty vault lists nothing; empty fields are rejected', () => withVault(async vault => {
  assert.deepEqual(await vault.all(), [])
  await assert.rejects(vault.save({ title: '  ', content: 'x' }), /title/)
  await assert.rejects(vault.save({ title: 'x', content: '' }), /content/)
}))

test('snippet centers on the match', () => {
  const text = 'a '.repeat(100) + 'NEEDLE ' + 'b '.repeat(100)
  assert.match(snippet(text, 'needle'), /NEEDLE/)
})
