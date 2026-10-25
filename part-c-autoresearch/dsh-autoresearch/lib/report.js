// Pure reporting logic over the autoresearch journal: no harness imports, so it is unit-tested alone.
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'

export async function readJournal(projectDir) {
  let text
  try {
    text = await readFile(join(projectDir, 'runs', 'journal.jsonl'), 'utf8')
  } catch {
    return []
  }
  return text.split('\n').filter(Boolean).flatMap(line => {
    try { return [JSON.parse(line)] } catch { return [] } // skip a torn last line
  })
}

const fmt = x => (x == null ? 'n/a' : Number(x).toFixed(6))

// The metric name and which direction is good live in task.toml. A bare "3.28 -> 2.14" is
// ambiguous (a model once read it as a decline), so the report states the direction and verdict.
export async function readTaskInfo(projectDir) {
  let text = ''
  try { text = await readFile(join(projectDir, 'task.toml'), 'utf8') } catch { /* use defaults */ }
  const pick = key => new RegExp(`^${key}\\s*=\\s*"([^"]+)"`, 'm').exec(text)?.[1]
  return { metric: pick('metric') ?? 'score', direction: pick('direction') === 'max' ? 'max' : 'min' }
}

function verdict(before, after, direction) {
  if (before == null || after == null) return ''
  const change = (after - before) / Math.abs(before) * 100
  const better = direction === 'min' ? after < before : after > before
  if (Math.abs(change) < 0.05) return '  (unchanged)'
  return `  (${better ? 'IMPROVED' : 'WORSENED'} by ${Math.abs(change).toFixed(1)}%)`
}

export function summarize(records, info = { metric: 'score', direction: 'min' }) {
  if (records.length === 0) return 'no experiments recorded yet (run `autoresearch run` first)'
  const base = records[0]
  const kept = records.filter(r => r.decision === 'kept')
  const best = kept.length ? kept[kept.length - 1] : base
  const counts = {}
  for (const r of records.slice(1)) counts[r.decision] = (counts[r.decision] ?? 0) + 1
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  const breakdown = Object.entries(counts).sort().map(([k, v]) => `${k}=${v}`).join('  ')
  const goal = info.direction === 'min' ? 'LOWER is better' : 'HIGHER is better'
  return [
    `experiments: ${total}  ${breakdown}`,
    `metric: ${info.metric} (${goal})`,
    `validation: ${fmt(base.score)} -> ${fmt(best.score)}${verdict(base.score, best.score, info.direction)}`,
    `held-out test: ${fmt(base.test_score)} -> ${fmt(best.test_score)}${verdict(base.test_score, best.test_score, info.direction)}`,
    `best change: ${best === base ? '(none kept)' : `#${best.iteration} ${best.idea}`}`,
  ].join('\n')
}

export function historyText(records, limit = 10) {
  const rows = records.filter(r => r.decision !== 'baseline').slice(-limit)
  if (rows.length === 0) return 'no experiments recorded yet'
  return rows.map(r => {
    const runs = r.repeats?.length > 1 ? ` runs=[${r.repeats.map(x => x.toFixed(3)).join(', ')}]` : ''
    const why = r.error ? ` (${r.error.slice(0, 100)})` : ''
    return `#${r.iteration} [${r.decision}] score=${fmt(r.score)}${runs} ${r.idea}${why}`
  }).join('\n')
}

// Minimal line diff (longest common subsequence). The files are small, so O(n*m) is fine.
export function lineDiff(before, after) {
  const a = before.split(/\r?\n/)
  const b = after.split(/\r?\n/)
  const dp = Array.from({ length: a.length + 1 }, () => new Uint16Array(b.length + 1))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  const out = []
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++ }
    else if (dp[i + 1][j] >= dp[i][j + 1]) out.push(`- ${a[i++]}`)
    else out.push(`+ ${b[j++]}`)
  }
  while (i < a.length) out.push(`- ${a[i++]}`)
  while (j < b.length) out.push(`+ ${b[j++]}`)
  return out
}

export async function bestDiff(projectDir) {
  const read = name => readFile(join(projectDir, 'runs', name), 'utf8').catch(() => null)
  const [base, best] = [await read('baseline-train.py'), await read('best-train.py')]
  if (base == null) return 'no baseline saved yet'
  if (best == null) return 'no improvement has been kept yet, so there is no diff'
  const lines = lineDiff(base, best)
  return lines.length ? lines.join('\n') : 'best file is identical to the baseline'
}
