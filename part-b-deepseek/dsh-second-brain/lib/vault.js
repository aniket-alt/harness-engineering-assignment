// Pure note-vault logic: no harness imports, so it can be unit-tested with node:test.
import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

const ID_PATTERN = /^[a-z0-9][a-z0-9_-]{0,79}$/

export function slugify(title) {
  const slug = title
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80)
  return slug || 'untitled'
}

export function parseTags(raw) {
  if (!raw) return []
  return [...new Set(raw.split(',').map(t => t.trim().toLowerCase()).filter(Boolean))]
}

function frontmatter(note) {
  return `---\ntitle: ${JSON.stringify(note.title)}\ntags: ${JSON.stringify(note.tags)}\ncreated: ${note.created}\nupdated: ${note.updated}\n---\n\n`
}

function parseNote(id, text) {
  const match = /^---\n([\s\S]*?)\n---\n\n?([\s\S]*)$/.exec(text)
  const meta = {}
  if (match) {
    for (const line of match[1].split('\n')) {
      const i = line.indexOf(':')
      if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).trim()
    }
  }
  const safeJson = (value, fallback) => {
    try { return JSON.parse(value) } catch { return fallback }
  }
  return {
    id,
    title: safeJson(meta.title, id),
    tags: safeJson(meta.tags, []),
    created: meta.created ?? '',
    updated: meta.updated ?? '',
    content: match ? match[2] : text,
  }
}

export class Vault {
  constructor(dir) {
    this.notesDir = join(dir, 'notes')
  }

  assertId(id) {
    // The id becomes a filename, so reject anything that could escape the notes folder.
    if (!ID_PATTERN.test(id)) throw new Error(`invalid note id: ${JSON.stringify(id)}`)
  }

  async save({ title, content, tags }) {
    if (!title.trim()) throw new Error('title must not be empty')
    if (!content.trim()) throw new Error('content must not be empty')
    const id = slugify(title)
    await mkdir(this.notesDir, { recursive: true })
    const file = join(this.notesDir, `${id}.md`)
    const now = new Date().toISOString()
    let created = now
    let existed = false
    try {
      created = parseNote(id, await readFile(file, 'utf8')).created || now
      existed = true
    } catch { /* new note */ }
    const note = { title: title.trim(), tags: parseTags(tags), created, updated: now }
    await writeFile(file, frontmatter(note) + content.trim() + '\n', 'utf8')
    return { id, existed }
  }

  async read(id) {
    this.assertId(id)
    return parseNote(id, await readFile(join(this.notesDir, `${id}.md`), 'utf8'))
  }

  async all() {
    let files
    try { files = await readdir(this.notesDir) } catch { return [] }
    const notes = []
    for (const f of files.filter(f => f.endsWith('.md'))) {
      const id = f.slice(0, -3)
      if (ID_PATTERN.test(id)) notes.push(parseNote(id, await readFile(join(this.notesDir, f), 'utf8')))
    }
    return notes.sort((a, b) => b.updated.localeCompare(a.updated))
  }

  async search(query, limit = 5) {
    const terms = query.toLowerCase().split(/\s+/).filter(Boolean)
    if (terms.length === 0) return []
    const count = (haystack, term) => haystack.split(term).length - 1
    const scored = []
    for (const note of await this.all()) {
      const title = note.title.toLowerCase()
      const tags = note.tags.join(' ')
      const body = note.content.toLowerCase()
      let score = 0
      for (const term of terms) score += 3 * count(title, term) + 2 * count(tags, term) + count(body, term)
      if (score > 0) scored.push({ note, score })
    }
    return scored.sort((a, b) => b.score - a.score).slice(0, limit).map(s => s.note)
  }
}

export function snippet(text, query, width = 160) {
  const flat = text.replace(/\s+/g, ' ').trim()
  const first = query.toLowerCase().split(/\s+/).filter(Boolean)
    .map(t => flat.toLowerCase().indexOf(t)).filter(i => i >= 0).sort((a, b) => a - b)[0] ?? 0
  const start = Math.max(0, first - 40)
  return (start > 0 ? '...' : '') + flat.slice(start, start + width) + (start + width < flat.length ? '...' : '')
}
