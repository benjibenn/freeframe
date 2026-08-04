'use client'

import * as React from 'react'
import { mutate } from 'swr'
import * as Dialog from '@radix-ui/react-dialog'
import { Settings2, Plus, X, Trash2, ArrowUp, ArrowDown, Star } from 'lucide-react'
import { api } from '@/lib/api'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import type { TaskStage } from '@/types'

const STAGES_KEY = '/task-stages'
const TASKS_KEY = '/task-board'

function StageDot({ color }: { color: string | null }) {
  return (
    <span
      className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
      style={{ backgroundColor: color || 'var(--text-tertiary, #6b7280)' }}
    />
  )
}

export function ManageStagesDialog({ stages }: { stages: TaskStage[] }) {
  const [open, setOpen] = React.useState(false)
  const [newName, setNewName] = React.useState('')
  const [newColor, setNewColor] = React.useState('#3b82f6')
  const [busy, setBusy] = React.useState(false)

  const refresh = () => {
    mutate(STAGES_KEY)
    mutate(TASKS_KEY)
  }

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    const name = newName.trim()
    if (!name) return
    setBusy(true)
    try {
      await api.post('/task-stages', { name, color: newColor })
      setNewName('')
      refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to add stage')
    } finally {
      setBusy(false)
    }
  }

  const handleRename = async (stage: TaskStage, name: string) => {
    if (name.trim() === stage.name || !name.trim()) return
    try {
      await api.patch(`/task-stages/${stage.id}`, { name: name.trim() })
      refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to rename stage')
    }
  }

  const handleRecolor = async (stage: TaskStage, color: string) => {
    try {
      await api.patch(`/task-stages/${stage.id}`, { color })
      refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to update colour')
    }
  }

  const handleSetDefault = async (stage: TaskStage) => {
    if (stage.is_default) return
    try {
      await api.patch(`/task-stages/${stage.id}`, { is_default: true })
      refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to set default stage')
    }
  }

  const handleDelete = async (stage: TaskStage) => {
    if (
      !window.confirm(
        `Delete the "${stage.name}" stage? Videos in this stage become Unassigned.`,
      )
    )
      return
    try {
      await api.delete(`/task-stages/${stage.id}`)
      refresh()
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to delete stage')
    }
  }

  const handleMove = async (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= stages.length) return
    const reordered = [...stages]
    const [moved] = reordered.splice(index, 1)
    reordered.splice(target, 0, moved)
    const ordered_ids = reordered.map((s) => s.id)
    // Optimistic
    mutate(
      STAGES_KEY,
      reordered.map((s, i) => ({ ...s, position: i + 1 })),
      false,
    )
    try {
      await api.post('/task-stages/reorder', { ordered_ids })
      refresh()
    } catch (err) {
      mutate(STAGES_KEY)
      alert(err instanceof Error ? err.message : 'Failed to reorder stages')
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <Button variant="secondary" size="sm">
          <Settings2 className="h-4 w-4" />
          Manage stages
        </Button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in-0" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] max-w-lg max-h-[85vh] overflow-y-auto -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-bg-secondary p-6 shadow-xl data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95">
          <Dialog.Close className="absolute right-4 top-4 text-text-tertiary hover:text-text-primary transition-colors">
            <X className="h-4 w-4" />
          </Dialog.Close>

          <Dialog.Title className="text-base font-semibold text-text-primary">
            Pipeline stages
          </Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-text-secondary">
            Define the flow each video moves through. Reorder with the arrows. The
            starred stage is where newly uploaded videos start.
          </Dialog.Description>

          <div className="mt-4 space-y-2">
            {stages.map((stage, index) => (
              <div
                key={stage.id}
                className="flex items-center gap-2 rounded-md border border-border bg-bg-primary px-2.5 py-2"
              >
                <div className="flex flex-col">
                  <button
                    onClick={() => handleMove(index, -1)}
                    disabled={index === 0}
                    className="text-text-tertiary hover:text-text-primary disabled:opacity-30"
                    title="Move up"
                  >
                    <ArrowUp className="h-3.5 w-3.5" />
                  </button>
                  <button
                    onClick={() => handleMove(index, 1)}
                    disabled={index === stages.length - 1}
                    className="text-text-tertiary hover:text-text-primary disabled:opacity-30"
                    title="Move down"
                  >
                    <ArrowDown className="h-3.5 w-3.5" />
                  </button>
                </div>
                <input
                  type="color"
                  value={stage.color || '#6b7280'}
                  onChange={(e) => handleRecolor(stage, e.target.value)}
                  className="h-7 w-7 shrink-0 cursor-pointer rounded border border-border bg-transparent"
                  title="Stage colour"
                />
                <input
                  defaultValue={stage.name}
                  onBlur={(e) => handleRename(stage, e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') (e.target as HTMLInputElement).blur()
                  }}
                  className="flex-1 rounded-md border border-transparent bg-transparent px-2 py-1 text-sm text-text-primary hover:border-border focus:border-border-focus focus:outline-none"
                />
                <button
                  onClick={() => handleSetDefault(stage)}
                  className={cn(
                    'transition-colors',
                    stage.is_default
                      ? 'text-amber-400'
                      : 'text-text-tertiary hover:text-amber-400',
                  )}
                  title={stage.is_default ? 'Default stage for new uploads' : 'Make default for new uploads'}
                >
                  <Star className={cn('h-4 w-4', stage.is_default && 'fill-amber-400')} />
                </button>
                <button
                  onClick={() => handleDelete(stage)}
                  className="text-text-tertiary hover:text-status-error transition-colors"
                  title="Delete stage"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
            {stages.length === 0 && (
              <p className="text-sm text-text-tertiary py-2">
                No stages yet — add the first one below.
              </p>
            )}
          </div>

          <form onSubmit={handleAdd} className="mt-4 flex items-center gap-2 border-t border-border pt-4">
            <input
              type="color"
              value={newColor}
              onChange={(e) => setNewColor(e.target.value)}
              className="h-9 w-9 shrink-0 cursor-pointer rounded border border-border bg-transparent"
              title="New stage colour"
            />
            <div className="flex-1">
              <Input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="New stage name…"
              />
            </div>
            <Button type="submit" size="sm" loading={busy} disabled={!newName.trim()}>
              <Plus className="h-4 w-4" />
              Add
            </Button>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
