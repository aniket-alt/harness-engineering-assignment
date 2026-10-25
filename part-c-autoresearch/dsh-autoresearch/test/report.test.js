import assert from 'node:assert/strict'
import { mkdtemp, mkdir, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { bestDiff, historyText, lineDiff, readJournal, summarize } from '../lib/report.js'

const REAL_PROJECT = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')

async function withProject(records, files, fn) {
  const dir = await mkdtemp(join(tmpdir(), 'research-'))
  try {
    await mkdir(join(dir, 'runs'))
    if (records) {
      await writeFile(join(dir, 'runs', 'journal.jsonl'), records.map(r => JSON.stringify(r)).join('\n') + '\n')
    }
    for (const [name, text] of Object.entries(files ?? {})) await writeFile(join(dir, 'runs', name), text)
    await fn(dir)
  } finally {
    await rm(dir, { recursive: true, force: true })
  }
}

const RECORDS = [
  { iteration: 0, decision: 'baseline', score: 3.0, test_score: 3.5, idea: 'starting point' },
  { iteration: 1, decision: 'reverted', score: 3.4, idea: 'try rope', repeats: [3.4] },
  { iteration: 2, decision: 'kept', score: 2.5, test_score: 2.9, idea: 'smaller batch', repeats: [2.4, 2.5] },
  { iteration: 3, decision: 'rejected', score: null, idea: 'sneaky', error: 'imports forbidden module os' },
]

test('summary reports counts and baseline-to-best for both splits', () => {
  const text = summarize(RECORDS)
  assert.match(text, /experiments: 3 {2}kept=1 {2}rejected=1 {2}reverted=1/)
  assert.match(text, /validation score: 3\.000000 -> 2\.500000/)
  assert.match(text, /held-out test score: 3\.500000 -> 2\.900000/)
  assert.match(text, /#2 smaller batch/)
})

test('summary with nothing kept says so; empty journal is a friendly message', () => {
  assert.match(summarize(RECORDS.slice(0, 2)), /\(none kept\)/)
  assert.match(summarize([]), /no experiments recorded/)
})

test('history shows decision, both confirmation runs and the guard reason', () => {
  const text = historyText(RECORDS)
  assert.match(text, /#2 \[kept\] score=2\.500000 runs=\[2\.400, 2\.500\] smaller batch/)
  assert.match(text, /#3 \[rejected\] score=n\/a sneaky \(imports forbidden module os\)/)
  assert.doesNotMatch(text, /baseline/)
  assert.equal(historyText(RECORDS, 1).split('\n').length, 1)
})

test('lineDiff marks only changed lines and ignores line-ending differences', () => {
  assert.deepEqual(lineDiff('a\nb\nc', 'a\nB\nc'), ['- b', '+ B'])
  assert.deepEqual(lineDiff('a\r\nb', 'a\nb'), [])
  assert.deepEqual(lineDiff('a', 'a\nb'), ['+ b'])
})

test('readJournal skips a torn last line and tolerates a missing file', async () => {
  await withProject(null, {}, async dir => {
    assert.deepEqual(await readJournal(dir), [])
    await writeFile(join(dir, 'runs', 'journal.jsonl'), '{"iteration":1}\n{"iteration":2')
    assert.deepEqual(await readJournal(dir), [{ iteration: 1 }])
  })
})

test('bestDiff handles missing baseline, missing best and a real change', async () => {
  await withProject(null, {}, async dir => assert.match(await bestDiff(dir), /no baseline/))
  await withProject(null, { 'baseline-train.py': 'x = 1\n' }, async dir =>
    assert.match(await bestDiff(dir), /no improvement/))
  await withProject(null, { 'baseline-train.py': 'BATCH = 64\n', 'best-train.py': 'BATCH = 8\n' }, async dir =>
    assert.match(await bestDiff(dir), /- BATCH = 64\n\+ BATCH = 8/))
})

test('against the REAL journal from the 8-iteration run', async () => {
  const records = await readJournal(REAL_PROJECT)
  assert.ok(records.length >= 9, `expected the real journal, found ${records.length} records`)
  const text = summarize(records)
  assert.match(text, /validation score: 3\.28\d+ -> 2\.13\d+/)
  assert.match(text, /held-out test score: 3\.79\d+ -> 2\.53\d+/)
  const diff = await bestDiff(REAL_PROJECT)
  assert.match(diff, /- BATCH_SIZE = 64/)
  assert.match(diff, /\+ BATCH_SIZE = 8/)
  assert.match(diff, /silu/)
})
