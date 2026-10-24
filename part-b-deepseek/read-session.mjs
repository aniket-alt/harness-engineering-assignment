// Print the tool calls and results of a DSH session log (the "trajectory").
// Session logs are append-only JSONL written as many concatenated zstd frames, so we
// split on the zstd magic number and decode each frame.
//
// usage: node read-session.mjs                   (latest session)
//        node read-session.mjs <session-dir>
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { zstdDecompressSync } from 'node:zlib'

const MAGIC = [0x28, 0xb5, 0x2f, 0xfd]

function newestSession() {
  const root = join(homedir(), '.dsh', 'sessions')
  const dirs = readdirSync(root).flatMap(w =>
    readdirSync(join(root, w)).map(s => join(root, w, s)))
  const withLog = dirs.filter(d => {
    try { return statSync(join(d, 'session.v4.jsonl.zstd')).isFile() } catch { return false }
  })
  return withLog.sort((a, b) => statSync(b).mtimeMs - statSync(a).mtimeMs)[0]
}

function readEvents(sessionDir) {
  const buf = readFileSync(join(sessionDir, 'session.v4.jsonl.zstd'))
  const starts = []
  for (let i = 0; i <= buf.length - 4; i++) {
    if (MAGIC.every((b, k) => buf[i + k] === b)) starts.push(i)
  }
  const events = []
  starts.forEach((start, k) => {
    const text = zstdDecompressSync(buf.subarray(start, starts[k + 1] ?? buf.length)).toString('utf8')
    for (const line of text.split('\n').filter(Boolean)) {
      try { events.push(JSON.parse(line)) } catch { /* skip a torn line */ }
    }
  })
  return events
}

const dir = process.argv[2] ?? newestSession()
if (!dir) { console.error('no session logs found under ~/.dsh/sessions'); process.exit(1) }
const events = readEvents(dir)
console.log(`session: ${dir}\n${events.length} events\n`)

for (const e of events) {
  const d = e.data ?? {}
  if (e.type === 'user/message' && d.source?.kind === 'user') {
    console.log(`USER      turn ${d.turn ?? '?'}: ${d.content?.map(c => c.text).join('')}`)
  } else if (e.type === 'tool/call') {
    console.log(`TOOL CALL turn ${d.turn}: ${d.name}(${d.arguments})`)
  } else if (e.type === 'tool/result') {
    const text = d.message?.content?.map(c => c.text).join('') ?? ''
    console.log(`RESULT    ${d.message?.isError ? 'ERROR ' : ''}${text.slice(0, 200)}`)
  } else if (e.type === 'llm/retry') {
    console.log(`RETRY     ${JSON.stringify(d).slice(0, 160)}`)
  }
}
