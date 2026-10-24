// Pure journal logic: formats and appends one line per tool call to a daily markdown file.
import { appendFile, mkdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'

export function dayStamp(date = new Date()) {
  const p = n => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}`
}

export function summarizeArgs(args, maxChars) {
  let text
  try { text = JSON.stringify(args) } catch { text = String(args) }
  if (text === undefined) return ''
  return text.length > maxChars ? text.slice(0, maxChars) + '...' : text
}

export function formatEntry({ time, tool, ok, args }) {
  const stamp = time.toTimeString().slice(0, 8)
  const status = ok ? 'ok' : 'FAILED'
  return `- ${stamp} \`${tool}\` ${status}${args ? ` ${args}` : ''}\n`
}

export class Journal {
  constructor(dir, { ignoreTools = [], includeArgs = false, maxArgChars = 80 } = {}) {
    this.dir = join(dir, 'journal')
    this.ignoreTools = new Set(ignoreTools)
    this.includeArgs = includeArgs
    this.maxArgChars = maxArgChars
  }

  fileFor(date = new Date()) {
    return join(this.dir, `${dayStamp(date)}.md`)
  }

  async record({ tool, ok, args }, date = new Date()) {
    if (this.ignoreTools.has(tool)) return false
    await mkdir(this.dir, { recursive: true })
    const file = this.fileFor(date)
    let header = ''
    try { await readFile(file, 'utf8') } catch { header = `# Journal ${dayStamp(date)}\n\n` }
    const line = formatEntry({
      time: date,
      tool,
      ok,
      args: this.includeArgs ? summarizeArgs(args, this.maxArgChars) : '',
    })
    await appendFile(file, header + line, 'utf8')
    return true
  }

  async today(date = new Date()) {
    try { return await readFile(this.fileFor(date), 'utf8') } catch { return '' }
  }
}
