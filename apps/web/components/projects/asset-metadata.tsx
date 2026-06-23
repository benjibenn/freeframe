'use client'

import * as React from 'react'
import useSWR, { mutate as globalMutate } from 'swr'
import { Star, ChevronDown, Check, CalendarDays } from 'lucide-react'
import * as Select from '@radix-ui/react-select'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import type {
  Asset,
  MetadataField,
  AssetMetadata,
  User,
  MetadataFieldType,
  ProjectMember,
} from '@/types'

// ─── Star rating ──────────────────────────────────────────────────────────────

function StarRating({
  value,
  onChange,
}: {
  value: number | null
  onChange: (v: number | null) => void
}) {
  const [hover, setHover] = React.useState(0)
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => {
        const star = i + 1
        const filled = star <= (hover || value || 0)
        return (
          <button
            key={i}
            type="button"
            className="p-0.5 transition-transform hover:scale-110"
            onMouseEnter={() => setHover(star)}
            onMouseLeave={() => setHover(0)}
            onClick={() => onChange(value === star ? null : star)}
          >
            <Star
              className={cn(
                'h-4 w-4 transition-colors',
                filled ? 'fill-yellow-400 text-yellow-400' : 'text-text-tertiary',
              )}
            />
          </button>
        )
      })}
    </div>
  )
}

// ─── Custom field renderer ────────────────────────────────────────────────────

function CustomFieldInput({
  field,
  value,
  onChange,
}: {
  field: MetadataField
  value: unknown
  onChange: (v: unknown) => void
}) {
  const type = field.field_type as MetadataFieldType

  if (type === 'text') {
    return (
      <input
        type="text"
        value={(value as string) ?? ''}
        onChange={(e) => onChange(e.target.value)}
        className="flex h-8 w-full rounded-md border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus transition-colors"
        placeholder={`Enter ${field.name.toLowerCase()}`}
      />
    )
  }

  if (type === 'number') {
    return (
      <input
        type="number"
        value={(value as number) ?? ''}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        className="flex h-8 w-full rounded-md border border-border bg-bg-secondary px-3 text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus transition-colors"
        placeholder="0"
      />
    )
  }

  if (type === 'date') {
    return (
      <input
        type="date"
        value={(value as string) ?? ''}
        onChange={(e) => onChange(e.target.value || null)}
        className="flex h-8 w-full rounded-md border border-border bg-bg-secondary px-3 text-sm text-text-primary focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus transition-colors"
      />
    )
  }

  if (type === 'select') {
    const opts = (field.options as string[]) ?? []
    const current = (value as string) ?? ''
    return (
      <Select.Root value={current} onValueChange={onChange}>
        <Select.Trigger className="inline-flex items-center justify-between gap-2 rounded-md border border-border bg-bg-secondary px-3 h-8 text-sm text-text-primary hover:bg-bg-tertiary transition-colors focus:outline-none focus:ring-1 focus:ring-border-focus w-full">
          <Select.Value placeholder={`Select ${field.name}`} />
          <ChevronDown className="h-3.5 w-3.5 text-text-tertiary shrink-0" />
        </Select.Trigger>
        <Select.Portal>
          <Select.Content className="z-50 min-w-[160px] overflow-hidden rounded-md border border-border bg-bg-secondary shadow-xl">
            <Select.Viewport className="p-1">
              {opts.map((opt) => (
                <Select.Item
                  key={opt}
                  value={opt}
                  className="relative flex items-center gap-2 rounded-sm px-7 py-1.5 text-sm text-text-primary outline-none data-[highlighted]:bg-bg-hover cursor-pointer"
                >
                  <Select.ItemIndicator className="absolute left-2">
                    <Check className="h-3.5 w-3.5 text-accent" />
                  </Select.ItemIndicator>
                  <Select.ItemText>{opt}</Select.ItemText>
                </Select.Item>
              ))}
            </Select.Viewport>
          </Select.Content>
        </Select.Portal>
      </Select.Root>
    )
  }

  if (type === 'multi_select') {
    const opts = (field.options as string[]) ?? []
    const selected = (value as string[]) ?? []
    const toggle = (opt: string) => {
      if (selected.includes(opt)) {
        onChange(selected.filter((s) => s !== opt))
      } else {
        onChange([...selected, opt])
      }
    }
    return (
      <div className="flex flex-wrap gap-1.5">
        {opts.map((opt) => (
          <button
            key={opt}
            type="button"
            onClick={() => toggle(opt)}
            className={cn(
              'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium border transition-colors',
              selected.includes(opt)
                ? 'bg-accent-muted border-accent text-accent'
                : 'border-border text-text-secondary hover:border-text-secondary',
            )}
          >
            {opt}
          </button>
        ))}
      </div>
    )
  }

  return null
}

// ─── Main component ───────────────────────────────────────────────────────────

interface AssetMetadataEditorProps {
  asset: Asset
  projectId: string
  /** Project members — used to populate the assignee dropdown. */
  members?: ProjectMember[]
  /** When false the editor renders nothing (editing is editor+ / admin only). */
  canEdit: boolean
  onUpdated?: () => void
}

/**
 * Editor for an asset's built-in fields (rating, assignee, due date) and any
 * project custom fields. Tags live in their own editor (AssetTagsEditor); status
 * lives in AssetStatusSelect. Built-ins save via PATCH /assets/{id}; custom fields
 * via PUT /assets/{id}/metadata.
 */
export function AssetMetadataEditor({
  asset,
  projectId,
  members,
  canEdit,
  onUpdated,
}: AssetMetadataEditorProps) {
  const assetKey = `/assets/${asset.id}`

  const [rating, setRating] = React.useState<number | null>(asset.rating)
  const [dueDate, setDueDate] = React.useState<string>(
    asset.due_date ? asset.due_date.slice(0, 10) : '',
  )
  const [assigneeId, setAssigneeId] = React.useState<string>(asset.assignee_id ?? '')
  const [saving, setSaving] = React.useState(false)
  const [msg, setMsg] = React.useState('')

  // Reset when navigating to a different asset.
  React.useEffect(() => {
    setRating(asset.rating)
    setDueDate(asset.due_date ? asset.due_date.slice(0, 10) : '')
    setAssigneeId(asset.assignee_id ?? '')
    setMsg('')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asset.id])

  // Custom fields defined on the project + this asset's current values.
  const { data: metadataFields } = useSWR<MetadataField[]>(
    canEdit ? `/projects/${projectId}/metadata-fields` : null,
    (k: string) => api.get<MetadataField[]>(k),
  )
  const { data: assetMetadata } = useSWR<AssetMetadata[]>(
    canEdit ? `/assets/${asset.id}/metadata` : null,
    (k: string) => api.get<AssetMetadata[]>(k),
  )

  const [customValues, setCustomValues] = React.useState<Record<string, unknown>>({})
  React.useEffect(() => {
    if (assetMetadata && metadataFields) {
      const map: Record<string, unknown> = {}
      for (const m of assetMetadata) map[m.field_id] = m.value
      setCustomValues(map)
    }
  }, [assetMetadata, metadataFields])

  // Member display names for the assignee dropdown.
  const memberIds = React.useMemo(
    () => Array.from(new Set((members ?? []).map((m) => m.user_id))),
    [members],
  )
  const { data: memberUsers } = useSWR<User[]>(
    canEdit && memberIds.length > 0 ? `/users?ids=${memberIds.join(',')}` : null,
    (k: string) => api.get<User[]>(k),
  )
  const userName = (id: string) => {
    const u = memberUsers?.find((x) => x.id === id)
    return u?.name || u?.email || id.slice(0, 8)
  }

  const handleSave = async () => {
    setSaving(true)
    setMsg('')
    try {
      await api.patch(`/assets/${asset.id}`, {
        rating,
        due_date: dueDate || null,
        assignee_id: assigneeId || null,
      })
      if (metadataFields && metadataFields.length > 0) {
        const fieldIds = new Set(metadataFields.map((f) => f.id))
        const payload = Object.entries(customValues)
          .filter(([fid]) => fieldIds.has(fid))
          .map(([field_id, value]) => ({ field_id, value }))
        if (payload.length > 0) {
          await api.put(`/assets/${asset.id}/metadata`, payload)
        }
      }
      setMsg('Saved.')
      globalMutate(assetKey)
      onUpdated?.()
    } catch (err: unknown) {
      setMsg(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  if (!canEdit) return null

  return (
    <div className="space-y-4">
      {/* Rating */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-text-tertiary uppercase tracking-wide">Rating</label>
        <StarRating value={rating} onChange={setRating} />
      </div>

      {/* Assignee */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-text-tertiary uppercase tracking-wide">Assignee</label>
        <select
          data-field-shortcut="assignee"
          value={assigneeId}
          onChange={(e) => setAssigneeId(e.target.value)}
          className="flex h-8 w-full rounded-md border border-border bg-bg-secondary px-3 text-sm text-text-primary focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus transition-colors"
        >
          <option value="">Unassigned</option>
          {(members ?? []).map((m) => (
            <option key={m.user_id} value={m.user_id}>
              {userName(m.user_id)}
            </option>
          ))}
        </select>
      </div>

      {/* Due date */}
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-text-tertiary uppercase tracking-wide flex items-center gap-1">
          <CalendarDays className="h-3 w-3" />
          Due Date
        </label>
        <input
          type="date"
          data-field-shortcut="duedate"
          value={dueDate}
          onChange={(e) => setDueDate(e.target.value)}
          className="flex h-8 w-full rounded-md border border-border bg-bg-secondary px-3 text-sm text-text-primary focus:outline-none focus:border-border-focus focus:ring-1 focus:ring-border-focus transition-colors"
        />
      </div>

      {/* Custom fields */}
      {metadataFields && metadataFields.length > 0 && (
        <div className="space-y-3 border-t border-border pt-4">
          <p className="text-xs font-medium text-text-tertiary uppercase tracking-wide">Custom Fields</p>
          {metadataFields.map((field) => (
            <div key={field.id} className="flex flex-col gap-1.5">
              <label className="text-sm text-text-secondary flex items-center gap-1">
                {field.name}
                {field.required && <span className="text-status-error">*</span>}
              </label>
              <CustomFieldInput
                field={field}
                value={customValues[field.id]}
                onChange={(v) => setCustomValues((prev) => ({ ...prev, [field.id]: v }))}
              />
            </div>
          ))}
        </div>
      )}

      {/* Save */}
      <div className="flex items-center justify-between pt-2 border-t border-border">
        {msg && <p className="text-xs text-text-secondary">{msg}</p>}
        <div className="ml-auto">
          <Button size="sm" loading={saving} onClick={handleSave}>
            Save
          </Button>
        </div>
      </div>
    </div>
  )
}
