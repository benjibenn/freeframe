'use client'

import * as React from 'react'
import * as Popover from '@radix-ui/react-popover'
import { Keyboard } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface ShortcutItem {
  keys: string[]
  label: string
}

export interface ShortcutGroup {
  title: string
  items: ShortcutItem[]
}

function KeyBadge({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex min-w-[1.5rem] items-center justify-center rounded border border-border bg-bg-hover px-1.5 py-0.5 font-mono text-xs text-text-secondary">
      {children}
    </kbd>
  )
}

interface ShortcutsHintProps {
  groups: ShortcutGroup[]
  className?: string
}

export function ShortcutsHint({ groups, className }: ShortcutsHintProps) {
  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          className={cn(
            'flex items-center justify-center h-7 w-7 rounded-md text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-colors',
            className,
          )}
          title="Keyboard shortcuts"
        >
          <Keyboard className="h-4 w-4" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="end"
          sideOffset={6}
          className={cn(
            'z-50 w-72 rounded-xl border border-border bg-bg-elevated shadow-2xl',
            'data-[state=open]:animate-fade-in',
          )}
        >
          <div className="px-4 py-3 border-b border-border">
            <p className="text-xs font-semibold text-text-primary">Keyboard shortcuts</p>
          </div>
          <div className="px-4 py-3 space-y-4 max-h-[60vh] overflow-y-auto">
            {groups.map((group) => (
              <div key={group.title} className="space-y-2">
                <p className="text-[10px] font-medium uppercase tracking-wider text-text-tertiary">
                  {group.title}
                </p>
                <div className="space-y-1.5">
                  {group.items.map((item, i) => (
                    <div key={i} className="flex items-center justify-between gap-3">
                      <span className="text-xs text-text-secondary">{item.label}</span>
                      <div className="flex shrink-0 items-center gap-1">
                        {item.keys.map((k, ki) => (
                          <KeyBadge key={ki}>{k}</KeyBadge>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
