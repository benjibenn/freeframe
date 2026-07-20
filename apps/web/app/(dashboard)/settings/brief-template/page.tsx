'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import { ArrowUp, ArrowDown, Trash2, Plus, GripVertical } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { api } from '@/lib/api'
import { useToast } from '@/components/shared/toast'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { BriefView, type BriefSection } from '@/components/projects/brief-view'

const RENDER_TYPES: BriefSection['as'][] = ['text', 'bullets', 'table']

// A representative brief so the live preview shows something before the admin pastes
// their own. Matches the default template's paths.
const SAMPLE_BRIEF = JSON.stringify(
  {
    title: 'Sample brief',
    overview: 'A 30s UGC ad for the new product. Hook hard in the first 2 seconds.',
    final_deliverable: {
      label: 'Final deliverable: 1× 9:16 video, 30s',
      hook_variations: [
        { variation: 'Hook 1: Problem-first', script: 'Tired of X?', shot: 'Close-up, frustrated', on_screen_text: 'Ugh.' },
        { variation: 'Hook 2: Result-first', script: 'This changed everything', shot: 'Product reveal', on_screen_text: 'Wait for it…' },
      ],
    },
    script_with_storyboard: [
      { script: 'Intro line', shot: 'Wide shot', on_screen_text: 'NEW' },
      { script: 'Demo the product', shot: 'Hands on product', on_screen_text: '' },
    ],
    guidelines: ['Keep it under 30s', 'No competitor mentions', 'Subtitles required'],
  },
  null,
  2,
)

function newId() {
  return `sec_${Math.random().toString(36).slice(2, 9)}`
}

export default function BriefTemplatePage() {
  const { user, isSuperAdmin, isSubAdmin } = useAuthStore()
  const router = useRouter()
  const toast = useToast()
  const canAccess = isSuperAdmin || isSubAdmin

  const [sections, setSections] = React.useState<BriefSection[]>([])
  const [sampleText, setSampleText] = React.useState(SAMPLE_BRIEF)
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)

  React.useEffect(() => {
    if (user && !canAccess) router.replace('/')
  }, [user, canAccess, router])

  React.useEffect(() => {
    if (!canAccess) return
    api
      .get<{ sections: BriefSection[] }>('/brief-template')
      .then((r) => setSections(r.sections ?? []))
      .catch(() => toast.error('Failed to load template'))
      .finally(() => setLoading(false))
  }, [canAccess, toast])

  // Preview parses the sample JSON; invalid JSON just yields no preview.
  const parsedSample = React.useMemo<Record<string, unknown> | null>(() => {
    try {
      const v = JSON.parse(sampleText)
      return v && typeof v === 'object' ? v : null
    } catch {
      return null
    }
  }, [sampleText])

  function patch(id: string, next: Partial<BriefSection>) {
    setSections((prev) => prev.map((s) => (s.id === id ? { ...s, ...next } : s)))
  }
  function move(idx: number, dir: -1 | 1) {
    setSections((prev) => {
      const next = [...prev]
      const j = idx + dir
      if (j < 0 || j >= next.length) return prev
      ;[next[idx], next[j]] = [next[j], next[idx]]
      return next
    })
  }
  function remove(id: string) {
    setSections((prev) => prev.filter((s) => s.id !== id))
  }
  function add() {
    setSections((prev) => [...prev, { id: newId(), title: '', path: '', as: 'text' }])
  }

  async function save() {
    setSaving(true)
    try {
      const r = await api.put<{ sections: BriefSection[] }>('/brief-template', { sections })
      setSections(r.sections ?? [])
      toast.success('Brief template saved')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  if (!canAccess) return null

  return (
    <div className="p-4 sm:p-6">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Brief template</h1>
          <p className="mt-1 max-w-2xl text-sm text-text-tertiary">
            Controls how structured JSON briefs render on submission pages. Each section maps a
            path in the brief JSON (e.g. <code className="text-text-secondary">final_deliverable.label</code>)
            to a display type. Reorder, remap, or add sections so new JSON shapes render without a code change.
          </p>
        </div>
        <Button onClick={save} disabled={saving || loading}>
          {saving ? 'Saving…' : 'Save template'}
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Builder */}
        <div className="flex flex-col gap-3">
          {loading ? (
            <p className="text-sm text-text-tertiary">Loading…</p>
          ) : (
            sections.map((s, idx) => (
              <div key={s.id} className="rounded-lg border border-border bg-bg-secondary p-3">
                <div className="mb-2 flex items-center gap-2">
                  <GripVertical className="h-4 w-4 text-text-tertiary" />
                  <span className="text-xs font-medium text-text-tertiary">Section {idx + 1}</span>
                  <div className="ml-auto flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => move(idx, -1)}
                      disabled={idx === 0}
                      className="rounded p-1 text-text-tertiary hover:bg-bg-hover disabled:opacity-30"
                      aria-label="Move up"
                    >
                      <ArrowUp className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => move(idx, 1)}
                      disabled={idx === sections.length - 1}
                      className="rounded p-1 text-text-tertiary hover:bg-bg-hover disabled:opacity-30"
                      aria-label="Move down"
                    >
                      <ArrowDown className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => remove(s.id)}
                      className="rounded p-1 text-status-error hover:bg-bg-hover"
                      aria-label="Remove section"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                <div className="grid gap-2 sm:grid-cols-2">
                  <label className="flex flex-col gap-1 text-xs text-text-tertiary">
                    Heading <span className="text-text-tertiary/60">(blank = no heading)</span>
                    <Input value={s.title} onChange={(e) => patch(s.id, { title: e.target.value })} placeholder="Overview" />
                  </label>
                  <label className="flex flex-col gap-1 text-xs text-text-tertiary">
                    JSON path
                    <Input value={s.path} onChange={(e) => patch(s.id, { path: e.target.value })} placeholder="final_deliverable.label" />
                  </label>
                </div>

                <div className="mt-2 flex items-center gap-2">
                  <label className="flex items-center gap-2 text-xs text-text-tertiary">
                    Render as
                    <select
                      value={s.as}
                      onChange={(e) => patch(s.id, { as: e.target.value as BriefSection['as'] })}
                      className="rounded-md border border-border bg-bg-primary px-2 py-1.5 text-sm text-text-primary"
                    >
                      {RENDER_TYPES.map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </label>
                </div>

                {s.as === 'table' && (
                  <ColumnsEditor
                    columns={s.columns ?? []}
                    onChange={(columns) => patch(s.id, { columns })}
                  />
                )}
              </div>
            ))
          )}

          <Button variant="secondary" onClick={add} className="self-start">
            <Plus className="mr-1.5 h-4 w-4" /> Add section
          </Button>
        </div>

        {/* Live preview */}
        <div className="flex flex-col gap-3">
          <div>
            <h2 className="text-sm font-semibold text-text-primary">Preview</h2>
            <p className="text-xs text-text-tertiary">Paste a sample brief JSON to see it render with the config on the left.</p>
          </div>
          <textarea
            value={sampleText}
            onChange={(e) => setSampleText(e.target.value)}
            spellCheck={false}
            className="h-40 w-full rounded-lg border border-border bg-bg-primary p-3 font-mono text-xs text-text-primary"
          />
          <div className="rounded-lg border border-border bg-bg-secondary p-4">
            {parsedSample ? (
              <BriefView data={parsedSample} sectionsOverride={sections} />
            ) : (
              <p className="text-sm text-status-error">Sample JSON is not valid.</p>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

function ColumnsEditor({
  columns,
  onChange,
}: {
  columns: { key: string; header: string }[]
  onChange: (cols: { key: string; header: string }[]) => void
}) {
  function set(i: number, next: Partial<{ key: string; header: string }>) {
    onChange(columns.map((c, j) => (j === i ? { ...c, ...next } : c)))
  }
  return (
    <div className="mt-3 rounded-md border border-border/60 bg-bg-primary/40 p-2">
      <p className="mb-1.5 text-xs font-medium text-text-tertiary">Table columns (key → header)</p>
      <div className="flex flex-col gap-1.5">
        {columns.map((c, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <Input value={c.key} onChange={(e) => set(i, { key: e.target.value })} placeholder="key (e.g. script)" className="text-xs" />
            <Input value={c.header} onChange={(e) => set(i, { header: e.target.value })} placeholder="Header" className="text-xs" />
            <button
              type="button"
              onClick={() => onChange(columns.filter((_, j) => j !== i))}
              className="rounded p-1 text-status-error hover:bg-bg-hover"
              aria-label="Remove column"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() => onChange([...columns, { key: '', header: '' }])}
        className="mt-1.5 text-xs text-accent hover:underline"
      >
        + Add column
      </button>
    </div>
  )
}
