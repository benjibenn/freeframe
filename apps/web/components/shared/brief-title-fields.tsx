'use client'

/**
 * The six slots of a brief title as separate boxes, plus the angle.
 *
 * The playbook reads a brief's persona, lens, hook and format out of its title by
 * position (`parseTitle`, lib/playbook.ts). Typed as one free-text box, a title
 * that misses a slot makes all four read as null and the brief sits in the
 * coverage matrix with no persona and no lens — so the convention is the default
 * here and the preview shows exactly what will be written.
 *
 * Angle is asked for alongside but is NOT part of the title: it is a label on the
 * brief, and it is what the matrix's columns count.
 *
 * The toggle stays because this form also creates requests that are not ad briefs
 * ("Video Editor Interview — June 2026"); forcing a persona on one of those would
 * put a fiction in the matrix.
 */

import { Input } from '@/components/ui/input'
import { buildTitle, titleProblem, type TitleParts } from '@/lib/playbook'

export type BriefTitleValue = TitleParts & {
  useConvention: boolean
  /** Used only when useConvention is false. */
  title: string
  angle: string
}

export const EMPTY_BRIEF_TITLE: BriefTitleValue = {
  useConvention: true,
  title: '',
  date: '',
  sku: '',
  persona: '',
  lens: '',
  hook: '',
  format: '',
  angle: '',
}

/** The title to post, or null when the value is not yet writable. */
export function briefTitleOf(v: BriefTitleValue): string | null {
  if (!v.useConvention) return v.title.trim() || null
  return titleProblem(v) ? null : buildTitle(v)
}

/** Why it is not writable, for the form to show. */
export function briefTitleProblem(v: BriefTitleValue): string | null {
  if (!v.useConvention) return v.title.trim() ? null : 'Title is required'
  return titleProblem(v)
}

const SLOTS: { key: keyof TitleParts; label: string; placeholder: string }[] = [
  { key: 'sku', label: 'SKU', placeholder: 'iPhone 17 Pro Max' },
  { key: 'persona', label: 'Persona', placeholder: 'Frugal Phone Buyer' },
  { key: 'lens', label: 'Lens', placeholder: 'Fear' },
  { key: 'hook', label: 'Hook', placeholder: 'Battery dies by 3pm' },
  { key: 'format', label: 'Format', placeholder: 'Static' },
]

export function BriefTitleFields({
  value,
  onChange,
}: {
  value: BriefTitleValue
  onChange: (next: BriefTitleValue) => void
}) {
  const set = (patch: Partial<BriefTitleValue>) => onChange({ ...value, ...patch })
  const problem = value.useConvention ? titleProblem(value) : null

  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-center gap-2 text-sm text-text-secondary">
        <input
          type="checkbox"
          checked={value.useConvention}
          onChange={(e) => set({ useConvention: e.target.checked })}
        />
        Name it by the brief convention
      </label>

      {value.useConvention ? (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {SLOTS.map((s) => (
              <Input
                key={s.key}
                label={s.label}
                placeholder={s.placeholder}
                value={value[s.key]}
                onChange={(e) => set({ [s.key]: e.target.value } as Partial<BriefTitleValue>)}
              />
            ))}
            <Input
              label="Date"
              placeholder="today"
              value={value.date}
              onChange={(e) => set({ date: e.target.value })}
            />
          </div>
          <p
            data-testid="title-preview"
            className={`rounded-md border px-3 py-2 text-xs ${
              problem
                ? 'border-status-error/30 bg-status-error/10 text-status-error'
                : 'border-border bg-bg-primary text-text-secondary'
            }`}
          >
            {problem ?? buildTitle(value)}
          </p>
        </>
      ) : (
        <Input
          label="Title"
          placeholder="e.g. Video Editor Interview — June 2026"
          value={value.title}
          onChange={(e) => set({ title: e.target.value })}
        />
      )}

      <Input
        label="Angle (optional)"
        placeholder="A28 Battery anxiety"
        value={value.angle}
        onChange={(e) => set({ angle: e.target.value })}
      />
      <p className="text-xs text-text-tertiary">
        The angle is not part of the title — it is the playbook&apos;s other coverage axis, so a
        brief without one is uncounted.
      </p>
    </div>
  )
}
