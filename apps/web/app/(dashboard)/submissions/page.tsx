'use client'

import { useEffect, useRef, useState } from 'react'
import Link from 'next/link'
import { api, ApiError } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Copy, Check, Trash2, ChevronDown, ChevronRight, Plus, Pencil, X, Film, FolderOpen, FolderPlus, FileText } from 'lucide-react'
import { useAuthStore } from '@/stores/auth-store'
import { PreAssignFolderDialog } from '@/components/shared/pre-assign-folder-dialog'

interface SubmissionLink {
  id: string
  token: string
  title: string
  instructions: string | null
  is_enabled: boolean
  expires_at: string | null
  created_at: string
  submission_count: number
  has_brief?: boolean
  has_brief_json?: boolean
}

interface SubmissionItem {
  id: string
  user_id: string
  user_name: string
  user_email: string
  project_id: string
  asset_count: number
  created_at: string
}

interface MySubmissionItem {
  submission_id: string
  project_id: string
  project_name: string
  link_id: string
  link_title: string
  link_token: string
  asset_count: number
  created_at: string
}

function submitUrl(token: string): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return `${origin}/submit/${token}`
}

// ─── Editor view ──────────────────────────────────────────────────────────────

function MySubmissionsView() {
  const [items, setItems] = useState<MySubmissionItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get<MySubmissionItem[]>('/my-submissions')
      .then(setItems)
      .catch((err) => setError(err instanceof ApiError ? err.detail : 'Failed to load submissions.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="space-y-2">{Array.from({ length: 3 }).map((_, i) => <div key={i} className="h-16 animate-pulse rounded-lg bg-bg-secondary" />)}</div>
  if (error) return <div className="rounded-md border border-status-error/30 bg-status-error/10 px-3 py-2.5 text-sm text-status-error">{error}</div>
  if (items.length === 0) return <p className="text-sm text-text-tertiary">You haven&apos;t submitted anything yet.</p>

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.submission_id} className="flex items-center justify-between gap-4 rounded-lg border border-border bg-bg-secondary px-4 py-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-text-primary truncate">{item.link_title}</p>
            <p className="text-xs text-text-tertiary flex items-center gap-1 mt-0.5">
              <Film className="h-3 w-3 shrink-0" />
              {item.asset_count} {item.asset_count === 1 ? 'asset' : 'assets'}
              <span className="mx-1">·</span>
              <FolderOpen className="h-3 w-3 shrink-0" />
              {item.project_name}
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Link
              href={`/submit/${item.link_token}`}
              className="text-xs text-text-tertiary hover:text-text-primary underline"
            >
              Submit more
            </Link>
            <Link
              href={`/projects/${item.project_id}`}
              className="rounded-md border border-border bg-bg-secondary px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
            >
              View project
            </Link>
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function SubmissionsPage() {
  const { user } = useAuthStore()
  const isPlatformAdmin = Boolean(user?.is_superadmin || user?.is_subadmin)
  const [links, setLinks] = useState<SubmissionLink[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // create form
  const [title, setTitle] = useState('')
  const [instructions, setInstructions] = useState('')
  const [briefFile, setBriefFile] = useState<File | null>(null)
  const [briefJson, setBriefJson] = useState('')
  const [creating, setCreating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)

  async function load() {
    try {
      setLinks(await api.get<SubmissionLink[]>('/submission-links'))
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to load submission links.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (isPlatformAdmin) load()
    else setLoading(false)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlatformAdmin])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!title.trim()) return
    if (briefFile && briefFile.type !== 'application/pdf') {
      setError('Brief must be a PDF.')
      return
    }
    // Parse the optional structured brief up front so a syntax error blocks creation.
    let parsedBrief: Record<string, unknown> | null = null
    if (briefJson.trim()) {
      try {
        parsedBrief = JSON.parse(briefJson)
      } catch {
        setError('Structured brief is not valid JSON.')
        return
      }
      if (typeof parsedBrief !== 'object' || parsedBrief === null || Array.isArray(parsedBrief)) {
        setError('Structured brief must be a JSON object.')
        return
      }
    }
    setCreating(true)
    try {
      const link = await api.post<SubmissionLink>('/submission-links', {
        title: title.trim(),
        instructions: instructions.trim() || null,
      })
      // Attach the optional brief PDF as a second step (the create endpoint is JSON;
      // the brief endpoint is multipart).
      if (briefFile && link?.id) {
        const fd = new FormData()
        fd.append('file', briefFile)
        await api.upload(`/submission-links/${link.id}/brief`, fd)
      }
      if (parsedBrief && link?.id) {
        await api.put(`/submission-links/${link.id}/brief-json`, { brief: parsedBrief })
      }
      setTitle('')
      setInstructions('')
      setBriefFile(null)
      setBriefJson('')
      setShowCreate(false)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to create link.')
    } finally {
      setCreating(false)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Disable this link? Existing submissions are kept, but the link will stop accepting new ones.')) return
    try {
      await api.delete(`/submission-links/${id}`)
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to disable link.')
    }
  }

  if (!isPlatformAdmin) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
        <div className="mb-6">
          <h1 className="text-xl font-semibold text-text-primary">My Submissions</h1>
          <p className="text-sm text-text-secondary">
            Submission requests you&apos;ve participated in. Click &quot;View project&quot; to see your uploaded assets.
          </p>
        </div>
        <MySubmissionsView />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6 sm:py-8">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Submission links</h1>
          <p className="text-sm text-text-secondary">
            One link, many submitters. Each person who signs in gets their own private project to
            upload into — they can’t see each other’s work, and you review them all.
          </p>
        </div>
        <Button onClick={() => setShowCreate((v) => !v)} className="shrink-0">
          <Plus className="h-4 w-4" /> New link
        </Button>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-status-error/30 bg-status-error/10 px-3 py-2.5 text-sm text-status-error">
          {error}
        </div>
      )}

      {showCreate && (
        <form
          onSubmit={handleCreate}
          className="mb-6 flex flex-col gap-3 rounded-lg border border-border bg-bg-secondary p-4"
        >
          <Input
            label="Title"
            placeholder="e.g. Video Editor Interview — June 2026"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-text-secondary">Instructions (optional)</label>
            <textarea
              className="flex min-h-[80px] w-full rounded-md border border-border bg-bg-secondary px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
              placeholder="Shown to submitters before they sign in."
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-text-secondary">Brief PDF (optional)</label>
            <input
              type="file"
              accept="application/pdf"
              onChange={(e) => setBriefFile(e.target.files?.[0] ?? null)}
              className="text-sm text-text-secondary file:mr-3 file:rounded-md file:border file:border-border file:bg-bg-primary file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-text-secondary hover:file:bg-bg-hover"
            />
            <p className="text-xs text-text-tertiary">Submitters can view this from the submission page.</p>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-text-secondary">Structured brief (JSON, optional)</label>
            <textarea
              className="flex min-h-[120px] w-full rounded-md border border-border bg-bg-secondary px-3 py-2 font-mono text-xs text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
              placeholder='{ "title": "…", "overview": "…", "script_with_storyboard": [ … ] }'
              value={briefJson}
              onChange={(e) => setBriefJson(e.target.value)}
            />
            <p className="text-xs text-text-tertiary">Paste a brief object. It renders on the submission and project pages.</p>
          </div>
          <div className="flex gap-2">
            <Button type="submit" loading={creating}>Create link</Button>
            <Button type="button" variant="ghost" onClick={() => { setShowCreate(false); setBriefFile(null); setBriefJson('') }}>Cancel</Button>
          </div>
        </form>
      )}

      {loading ? (
        <p className="text-sm text-text-secondary">Loading…</p>
      ) : links.length === 0 ? (
        <p className="text-sm text-text-secondary">No submission links yet. Create one to get started.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {links.map((link) => (
            <LinkCard
              key={link.id}
              link={link}
              onDelete={() => handleDelete(link.id)}
              onUpdated={load}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function LinkCard({
  link,
  onDelete,
  onUpdated,
}: {
  link: SubmissionLink
  onDelete: () => void
  onUpdated: () => void | Promise<void>
}) {
  const [copied, setCopied] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [subs, setSubs] = useState<SubmissionItem[] | null>(null)
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState(link.title)
  const [editInstructions, setEditInstructions] = useState(link.instructions ?? '')
  const [editBriefJson, setEditBriefJson] = useState('')
  const [editBriefFile, setEditBriefFile] = useState<File | null>(null)
  const [hasBrief, setHasBrief] = useState(!!link.has_brief)
  const [briefError, setBriefError] = useState('')
  const [saving, setSaving] = useState(false)
  const [preAssignOpen, setPreAssignOpen] = useState(false)
  const editFileRef = useRef<HTMLInputElement>(null)

  const url = submitUrl(link.token)

  async function startEdit() {
    setEditTitle(link.title)
    setEditInstructions(link.instructions ?? '')
    setEditBriefFile(null)
    setBriefError('')
    setHasBrief(!!link.has_brief)
    setEditing(true)
    // The list payload omits brief_json to stay light; fetch the full link so the
    // textarea prefills with the current brief (else saving would wipe it).
    setEditBriefJson('')
    try {
      const full = await api.get<SubmissionLink & { brief_json?: Record<string, unknown> | null; has_brief?: boolean }>(
        `/submission-links/${link.id}`,
      )
      setEditBriefJson(full.brief_json ? JSON.stringify(full.brief_json, null, 2) : '')
      setHasBrief(!!full.has_brief)
    } catch {
      /* leave empty; user can still paste */
    }
  }

  async function saveEdit(e: React.FormEvent) {
    e.preventDefault()
    if (!editTitle.trim() || saving) return
    if (editBriefFile && editBriefFile.type !== 'application/pdf') {
      setBriefError('Brief file must be a PDF.')
      return
    }
    // Parse the structured brief up front so a syntax error blocks the save.
    let parsedBrief: Record<string, unknown> | null = null
    const briefText = editBriefJson.trim()
    if (briefText) {
      try {
        parsedBrief = JSON.parse(briefText)
      } catch {
        setBriefError('Structured brief is not valid JSON.')
        return
      }
      if (typeof parsedBrief !== 'object' || parsedBrief === null || Array.isArray(parsedBrief)) {
        setBriefError('Structured brief must be a JSON object.')
        return
      }
    }
    setBriefError('')
    setSaving(true)
    try {
      await api.patch(`/submission-links/${link.id}`, {
        title: editTitle.trim(),
        instructions: editInstructions.trim() || null,
      })
      if (editBriefFile) {
        const fd = new FormData()
        fd.append('file', editBriefFile)
        await api.upload(`/submission-links/${link.id}/brief`, fd)
      }
      // Sets or clears the structured brief (null clears).
      await api.put(`/submission-links/${link.id}/brief-json`, { brief: parsedBrief })
      setEditing(false)
      await onUpdated()
    } catch (err) {
      setBriefError(err instanceof ApiError ? err.detail : 'Could not save changes.')
    } finally {
      setSaving(false)
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      /* clipboard unavailable */
    }
  }

  async function toggle() {
    const next = !expanded
    setExpanded(next)
    if (next && subs === null) {
      try {
        setSubs(await api.get<SubmissionItem[]>(`/submission-links/${link.id}/submissions`))
      } catch {
        setSubs([])
      }
    }
  }

  return (
    <div className="rounded-lg border border-border bg-bg-secondary p-4">
      {editing ? (
        <form onSubmit={saveEdit} className="flex flex-col gap-3">
          <Input
            label="Name"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            autoFocus
          />
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-text-secondary">Instructions (optional)</label>
            <textarea
              className="flex min-h-[80px] w-full rounded-md border border-border bg-bg-secondary px-3 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
              value={editInstructions}
              onChange={(e) => setEditInstructions(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-text-secondary">Brief PDF (optional)</label>
            <div className="flex items-center gap-2">
              <input
                ref={editFileRef}
                type="file"
                accept="application/pdf"
                className="hidden"
                onChange={(e) => setEditBriefFile(e.target.files?.[0] ?? null)}
              />
              <Button type="button" variant="secondary" size="sm" onClick={() => editFileRef.current?.click()}>
                {hasBrief ? 'Replace PDF' : 'Upload PDF'}
              </Button>
              <span className="truncate text-xs text-text-tertiary">
                {editBriefFile ? editBriefFile.name : hasBrief ? 'A brief PDF is attached.' : 'No PDF attached.'}
              </span>
            </div>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium text-text-secondary">Structured brief (JSON, optional)</label>
            <textarea
              className="flex min-h-[120px] w-full rounded-md border border-border bg-bg-secondary px-3 py-2 font-mono text-xs text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
              placeholder='{ "title": "…", "overview": "…", "script_with_storyboard": [ … ] }'
              value={editBriefJson}
              onChange={(e) => setEditBriefJson(e.target.value)}
              spellCheck={false}
            />
            <p className="text-xs text-text-tertiary">Empty and save to clear the structured brief.</p>
          </div>
          {briefError && (
            <p className="rounded-md border border-status-error/30 bg-status-error/10 px-3 py-2 text-xs text-status-error">
              {briefError}
            </p>
          )}
          <div className="flex gap-2">
            <Button type="submit" size="sm" loading={saving}>Save</Button>
            <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(false)}>
              <X className="h-4 w-4" /> Cancel
            </Button>
          </div>
        </form>
      ) : (
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="truncate font-medium text-text-primary">{link.title}</h3>
            {link.instructions && (
              <p className="mt-0.5 line-clamp-2 text-sm text-text-secondary">{link.instructions}</p>
            )}
            {(link.has_brief || link.has_brief_json) && (
              <p className="mt-0.5 inline-flex items-center gap-1 text-xs text-text-tertiary">
                <FileText className="h-3 w-3" />
                {link.has_brief && link.has_brief_json
                  ? 'Brief PDF + structured brief attached'
                  : link.has_brief
                    ? 'Brief PDF attached'
                    : 'Structured brief attached'}
              </p>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Button variant="ghost" size="sm" onClick={startEdit} title="Edit name">
              <Pencil className="h-4 w-4" />
            </Button>
            <Button variant="ghost" size="sm" onClick={onDelete} title="Disable link">
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      <div className="mt-3 flex items-center gap-2">
        <input
          readOnly
          value={url}
          className="flex h-9 flex-1 rounded-md border border-border bg-bg-primary px-3 text-sm text-text-secondary"
          onFocus={(e) => e.currentTarget.select()}
        />
        <Button variant="secondary" size="sm" onClick={copy}>
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          {copied ? 'Copied' : 'Copy'}
        </Button>
      </div>

      <button
        onClick={toggle}
        className="mt-3 flex items-center gap-1 text-sm text-text-secondary hover:text-text-primary"
      >
        {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        {link.submission_count} submission{link.submission_count === 1 ? '' : 's'}
      </button>

      {expanded && (
        <div className="mt-2 border-t border-border pt-2">
          {subs === null ? (
            <p className="py-2 text-sm text-text-tertiary">Loading…</p>
          ) : subs.length === 0 ? (
            <p className="py-2 text-sm text-text-tertiary">No submissions yet.</p>
          ) : (
            <ul className="flex flex-col">
              {subs.map((s) => (
                <li key={s.id}>
                  <Link
                    href={`/projects/${s.project_id}`}
                    className="flex items-center justify-between rounded-md px-2 py-2 hover:bg-bg-hover"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm text-text-primary">
                        {s.user_name || s.user_email}
                      </span>
                      {s.user_name && (
                        <span className="block truncate text-xs text-text-tertiary">{s.user_email}</span>
                      )}
                    </span>
                    <span className="shrink-0 text-xs text-text-tertiary">
                      {s.asset_count} file{s.asset_count === 1 ? '' : 's'}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          <button
            onClick={() => setPreAssignOpen(true)}
            className="mt-1 flex items-center gap-1.5 rounded-md px-2 py-2 text-xs text-text-tertiary hover:text-text-primary hover:bg-bg-hover transition-colors w-full"
          >
            <FolderPlus className="h-3.5 w-3.5" />
            Pre-assign folder to email…
          </button>
        </div>
      )}

      <PreAssignFolderDialog
        open={preAssignOpen}
        onOpenChange={setPreAssignOpen}
        linkId={link.id}
        onCreated={async () => {
          if (expanded) {
            setSubs(await api.get<SubmissionItem[]>(`/submission-links/${link.id}/submissions`))
          }
        }}
      />
    </div>
  )
}
