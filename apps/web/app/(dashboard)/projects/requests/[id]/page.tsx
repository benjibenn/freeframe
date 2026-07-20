'use client'

import * as React from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import useSWR, { mutate as globalMutate } from 'swr'
import * as Dialog from '@radix-ui/react-dialog'
import {
  ArrowLeft,
  Copy,
  Check,
  Users,
  FolderOpen,
  Eye,
  Loader2,
  Pencil,
  X,
  Trash2,
  Undo2,
  UserPlus,
  FileText,
  Film,
  Upload,
} from 'lucide-react'
import { api, ApiError } from '@/lib/api'
import { uploadReferenceVideo } from '@/lib/reference-video'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/shared/empty-state'
import { useToast } from '@/components/shared/toast'
import { usePageTitle } from '@/hooks/use-page-title'
import { PreAssignFolderDialog } from '@/components/shared/pre-assign-folder-dialog'
import { BriefView } from '@/components/projects/brief-view'
import type { VideoRequest } from '@/components/projects/request-card'

interface SubmissionItem {
  id: string
  user_id: string
  user_name: string
  user_email: string
  display_name: string | null
  project_id: string
  asset_count: number
  created_at: string
}

interface ChildProjectItem {
  project_id: string
  name: string
  asset_count: number
  is_reference: boolean
}

// A unified submission card: either a per-editor submission (editable handle) or a
// manually-attached project (editable project name, removable).
type Card = {
  key: string
  kind: 'submission' | 'attached'
  projectId: string
  label: string
  secondary: string | null
  assetCount: number
  editDefault: string
  submissionId?: string
}

function submitUrl(token: string): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return `${origin}/submit/${token}`
}

export default function RequestDetailPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const toast = useToast()
  const id = params.id

  const { data: request, mutate: mutateRequest } = useSWR<VideoRequest>(
    id ? `/submission-links/${id}` : null,
    (key: string) => api.get<VideoRequest>(key),
  )
  const { data: subs, isLoading, mutate: mutateSubs } = useSWR<SubmissionItem[]>(
    id ? `/submission-links/${id}/submissions` : null,
    (key: string) => api.get<SubmissionItem[]>(key),
  )
  const { data: childProjects, mutate: mutateChildren } = useSWR<ChildProjectItem[]>(
    id ? `/submission-links/${id}/projects` : null,
    (key: string) => api.get<ChildProjectItem[]>(key),
  )

  // Manually-attached child folders (the shared reference is shown separately above).
  const attached = React.useMemo(
    () => (childProjects ?? []).filter((p) => !p.is_reference),
    [childProjects],
  )

  // Per-editor submissions and attached projects render together as one grid.
  const cards = React.useMemo<Card[]>(() => {
    const submissionCards: Card[] = (subs ?? []).map((s) => ({
      key: `sub-${s.id}`,
      kind: 'submission',
      projectId: s.project_id,
      label: s.display_name || s.user_name || s.user_email,
      secondary:
        s.display_name && s.display_name !== s.user_name
          ? s.user_name || s.user_email
          : null,
      assetCount: s.asset_count,
      editDefault: s.display_name ?? s.user_name ?? '',
      submissionId: s.id,
    }))
    const attachedCards: Card[] = attached.map((p) => ({
      key: `att-${p.project_id}`,
      kind: 'attached',
      projectId: p.project_id,
      label: p.name,
      secondary: null,
      assetCount: p.asset_count,
      editDefault: p.name,
    }))
    return [...submissionCards, ...attachedCards]
  }, [subs, attached])

  const detach = async (projectId: string) => {
    if (!confirm('Remove this project from the request? The project itself is kept.')) return
    try {
      await api.post(`/submission-links/${id}/detach-project/${projectId}`, {})
      await Promise.all([mutateChildren(), globalMutate('/projects')])
      toast.success('Removed from request')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Could not remove')
    }
  }

  usePageTitle(request?.title ?? 'Request')

  const [copied, setCopied] = React.useState(false)
  const [preAssignOpen, setPreAssignOpen] = React.useState(false)
  const [togglingRef, setTogglingRef] = React.useState(false)
  const [editingId, setEditingId] = React.useState<string | null>(null)
  const [editValue, setEditValue] = React.useState('')
  const [savingHandle, setSavingHandle] = React.useState(false)

  const startEditCard = (card: Card) => {
    setEditingId(card.key)
    setEditValue(card.editDefault)
  }

  const saveCard = async (card: Card) => {
    if (savingHandle) return
    const value = editValue.trim()
    if (card.kind === 'attached' && !value) return
    setSavingHandle(true)
    try {
      if (card.kind === 'submission') {
        // Per-editor submission: edit the handle override.
        await api.patch(`/submission-links/${id}/submissions/${card.submissionId}`, {
          display_name: value || null,
        })
        await mutateSubs()
      } else {
        // Attached project: rename the project itself.
        await api.patch(`/projects/${card.projectId}`, { name: value })
        await mutateChildren()
      }
      setEditingId(null)
      toast.success('Name updated')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Could not update name')
    } finally {
      setSavingHandle(false)
    }
  }

  const copy = async () => {
    if (!request) return
    try {
      await navigator.clipboard.writeText(submitUrl(request.token))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
      toast.success('Submission link copied')
    } catch {
      toast.error('Could not copy link')
    }
  }

  const [dissolving, setDissolving] = React.useState(false)

  const dissolve = async () => {
    if (!request) return
    if (
      !confirm(
        `Undo this request? "${request.title}" will be removed and every project under it — including this one's files — goes back to your Projects unchanged.`,
      )
    )
      return
    setDissolving(true)
    try {
      await api.post(`/submission-links/${request.id}/dissolve`, {})
      await globalMutate('/projects')
      await globalMutate('/submission-links')
      toast.success('Request undone — projects moved back to Projects')
      router.push('/projects')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Could not undo the request')
      setDissolving(false)
    }
  }

  const briefInputRef = React.useRef<HTMLInputElement>(null)
  const [uploadingBrief, setUploadingBrief] = React.useState(false)

  const uploadBrief = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = '' // let the same file be re-selected after an error
    if (!file || !request) return
    if (file.type !== 'application/pdf') {
      toast.error('Brief must be a PDF')
      return
    }
    setUploadingBrief(true)
    try {
      const fd = new FormData()
      fd.append('file', file)
      await api.upload(`/submission-links/${request.id}/brief`, fd)
      await mutateRequest()
      toast.success(request.has_brief ? 'Brief replaced' : 'Brief uploaded')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Could not upload the brief')
    } finally {
      setUploadingBrief(false)
    }
  }

  const briefHref = request
    ? `${process.env.NEXT_PUBLIC_API_URL || ''}/submit/${request.token}/brief.pdf`
    : '#'

  const videoInputRef = React.useRef<HTMLInputElement>(null)
  const [uploadingVideo, setUploadingVideo] = React.useState(false)
  const [videoPct, setVideoPct] = React.useState<number | null>(null)

  const uploadVideo = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file || !request) return
    if (!file.type.startsWith('video/')) {
      toast.error('Reference must be a video file')
      return
    }
    setUploadingVideo(true)
    setVideoPct(0)
    try {
      await uploadReferenceVideo(request.id, file, setVideoPct)
      await mutateRequest()
      toast.success(request.has_reference_video ? 'Reference video replaced' : 'Reference video uploaded')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Could not upload the video')
    } finally {
      setUploadingVideo(false)
      setVideoPct(null)
    }
  }

  const removeVideo = async () => {
    if (!request) return
    try {
      await api.delete(`/submission-links/${request.id}/reference-video`)
      await mutateRequest()
      toast.success('Reference video removed')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Could not remove the video')
    }
  }

  // Structured JSON brief editor. Sync the textarea from the loaded request once.
  const [briefText, setBriefText] = React.useState('')
  const [briefLoaded, setBriefLoaded] = React.useState(false)
  const [savingBriefJson, setSavingBriefJson] = React.useState(false)
  const [briefPreviewOpen, setBriefPreviewOpen] = React.useState(false)
  React.useEffect(() => {
    if (request && !briefLoaded) {
      setBriefText(request.brief_json ? JSON.stringify(request.brief_json, null, 2) : '')
      setBriefLoaded(true)
    }
  }, [request, briefLoaded])

  const saveBriefJson = async () => {
    if (!request || savingBriefJson) return
    const text = briefText.trim()
    let brief: Record<string, unknown> | null = null
    if (text) {
      try {
        brief = JSON.parse(text)
      } catch {
        toast.error('Brief is not valid JSON')
        return
      }
      if (typeof brief !== 'object' || brief === null || Array.isArray(brief)) {
        toast.error('Brief must be a JSON object')
        return
      }
    }
    setSavingBriefJson(true)
    try {
      await api.put(`/submission-links/${request.id}/brief-json`, { brief })
      await mutateRequest()
      toast.success(brief ? 'Structured brief saved' : 'Structured brief cleared')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Could not save the brief')
    } finally {
      setSavingBriefJson(false)
    }
  }

  let briefPreview: Record<string, unknown> | null = null
  try {
    briefPreview = briefText.trim() ? JSON.parse(briefText) : null
  } catch {
    briefPreview = null
  }

  const referenceEnabled = !!request?.reference_project_id

  const toggleReference = async () => {
    if (!request) return
    setTogglingRef(true)
    try {
      if (referenceEnabled) {
        await api.delete(`/submission-links/${request.id}/reference`)
        toast.success('Shared reference folder disabled')
      } else {
        await api.post(`/submission-links/${request.id}/reference`, {})
        toast.success('Shared reference folder enabled — visible to all submitters')
      }
      await mutateRequest()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : 'Could not update shared reference')
    } finally {
      setTogglingRef(false)
    }
  }

  return (
    <div className="p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div>
        <Link
          href="/projects"
          className="inline-flex items-center gap-1.5 text-sm text-text-tertiary hover:text-text-primary transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Projects
        </Link>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-lg font-semibold text-text-primary truncate">
              {request?.title ?? 'Request'}
            </h1>
            {request?.instructions && (
              <p className="mt-1 text-sm text-text-secondary max-w-2xl">{request.instructions}</p>
            )}
            {(request?.persona_label || request?.angle_label || request?.problem) && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {[
                  request?.persona_label,
                  request?.angle_label,
                  request?.problem ? `Problem: ${request.problem}` : null,
                ]
                  .filter(Boolean)
                  .map((label) => (
                    <span
                      key={label as string}
                      className="rounded-full border border-border bg-bg-secondary px-2 py-0.5 text-2xs text-text-tertiary"
                    >
                      {label}
                    </span>
                  ))}
              </div>
            )}
            <p className="mt-1 flex items-center gap-1.5 text-xs text-text-tertiary">
              <Users className="h-3 w-3" />
              {request?.submission_count ?? subs?.length ?? 0} submission
              {(request?.submission_count ?? 0) !== 1 ? 's' : ''}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button variant="secondary" size="sm" onClick={copy} disabled={!request}>
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              {copied ? 'Copied' : 'Copy submission link'}
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setPreAssignOpen(true)}>
              <UserPlus className="h-4 w-4" />
              Pre-assign slot
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={dissolve}
              disabled={dissolving || !request}
              title="Undo this request and move its projects back to Projects"
            >
              {dissolving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Undo2 className="h-4 w-4" />}
              Undo request
            </Button>
          </div>
        </div>
      </div>

      {/* Shared reference toggle */}
      <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-bg-secondary px-4 py-3">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-bg-tertiary text-text-secondary">
            <Eye className="h-4 w-4" />
          </div>
          <div>
            <p className="text-sm font-medium text-text-primary">Shared reference folder</p>
            <p className="text-xs text-text-tertiary">
              A common folder every submitter can view (brief, examples). Their own submissions
              stay private to them.
            </p>
            {referenceEnabled && request?.reference_project_id && (
              <Link
                href={`/projects/${request.reference_project_id}`}
                className="mt-1 inline-flex items-center gap-1 text-xs text-accent hover:underline"
              >
                <FolderOpen className="h-3 w-3" />
                Open shared folder
              </Link>
            )}
          </div>
        </div>
        <Button
          variant={referenceEnabled ? 'secondary' : 'primary'}
          size="sm"
          onClick={toggleReference}
          disabled={togglingRef || !request}
        >
          {togglingRef && <Loader2 className="h-4 w-4 animate-spin" />}
          {referenceEnabled ? 'Disable' : 'Enable'}
        </Button>
      </div>

      {/* Brief PDF (non-flywheel: hand-uploaded by the owner) */}
      <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-bg-secondary px-4 py-3">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-bg-tertiary text-text-secondary">
            <FileText className="h-4 w-4" />
          </div>
          <div>
            <p className="text-sm font-medium text-text-primary">Brief (PDF)</p>
            <p className="text-xs text-text-tertiary">
              Upload a PDF brief. Submitters can view it from the submission page before
              they upload.
            </p>
            {request?.has_brief && (
              <a
                href={briefHref}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-1 inline-flex items-center gap-1 text-xs text-accent hover:underline"
              >
                <FileText className="h-3 w-3" />
                View brief (PDF)
              </a>
            )}
          </div>
        </div>
        <input
          ref={briefInputRef}
          type="file"
          accept="application/pdf"
          className="hidden"
          onChange={uploadBrief}
        />
        <Button
          variant={request?.has_brief ? 'secondary' : 'primary'}
          size="sm"
          onClick={() => briefInputRef.current?.click()}
          disabled={uploadingBrief || !request}
        >
          {uploadingBrief ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {request?.has_brief ? 'Replace' : 'Upload PDF'}
        </Button>
      </div>

      {/* Reference video (owner-uploaded, streamed inline in the View-brief dialog) */}
      <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-bg-secondary px-4 py-3">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-bg-tertiary text-text-secondary">
            <Film className="h-4 w-4" />
          </div>
          <div>
            <p className="text-sm font-medium text-text-primary">Reference video</p>
            <p className="text-xs text-text-tertiary">
              {videoPct !== null
                ? `Uploading… ${videoPct}%`
                : 'Upload a reference clip. Submitters watch it inline before they upload.'}
            </p>
            {request?.has_reference_video && videoPct === null && (
              <button onClick={removeVideo} className="mt-1 text-xs text-status-error hover:underline">
                Remove video
              </button>
            )}
          </div>
        </div>
        <input
          ref={videoInputRef}
          type="file"
          accept="video/*"
          className="hidden"
          onChange={uploadVideo}
        />
        <Button
          variant={request?.has_reference_video ? 'secondary' : 'primary'}
          size="sm"
          onClick={() => videoInputRef.current?.click()}
          disabled={uploadingVideo || !request}
        >
          {uploadingVideo ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {request?.has_reference_video ? 'Replace' : 'Upload video'}
        </Button>
      </div>

      {/* Structured brief (JSON) — renders inline on the submit + project pages */}
      <div className="rounded-xl border border-border bg-bg-secondary px-4 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-bg-tertiary text-text-secondary">
              <FileText className="h-4 w-4" />
            </div>
            <div>
              <p className="text-sm font-medium text-text-primary">Structured brief (JSON)</p>
              <p className="text-xs text-text-tertiary">
                Paste a brief object. It renders as a formatted brief on the submission and
                project pages. Leave empty and save to clear.
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {briefPreview && (
              <Button variant="secondary" size="sm" onClick={() => setBriefPreviewOpen(true)}>
                Preview
              </Button>
            )}
            <Button size="sm" onClick={saveBriefJson} disabled={savingBriefJson || !request}>
              {savingBriefJson && <Loader2 className="h-4 w-4 animate-spin" />}
              Save
            </Button>
          </div>
        </div>
        <textarea
          className="mt-3 flex min-h-[140px] w-full rounded-md border border-border bg-bg-primary px-3 py-2 font-mono text-xs text-text-primary placeholder:text-text-tertiary focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20"
          placeholder='{ "title": "…", "overview": "…", "script_with_storyboard": [ … ] }'
          value={briefText}
          onChange={(e) => setBriefText(e.target.value)}
          spellCheck={false}
        />
      </div>

      {/* Structured brief preview */}
      <Dialog.Root open={briefPreviewOpen} onOpenChange={setBriefPreviewOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-border bg-bg-secondary shadow-xl">
            <div className="flex items-center justify-between gap-3 border-b border-border px-5 py-3">
              <Dialog.Title className="text-sm font-semibold text-text-primary">Brief preview</Dialog.Title>
              <Dialog.Close asChild>
                <button className="flex h-6 w-6 items-center justify-center rounded text-text-tertiary hover:bg-bg-hover hover:text-text-primary">
                  <X className="h-4 w-4" />
                </button>
              </Dialog.Close>
            </div>
            <div className="overflow-y-auto px-5 py-4">
              {briefPreview && <BriefView data={briefPreview} />}
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Submissions (per-editor submissions + attached projects, unified) */}
      <h2 className="text-sm font-medium text-text-secondary">Submissions</h2>
      {isLoading ? (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="flex flex-col rounded-xl overflow-hidden border border-border">
              <div className="aspect-square animate-pulse bg-bg-tertiary" />
              <div className="px-3 py-2.5">
                <div className="h-3 w-2/3 animate-pulse rounded bg-bg-tertiary" />
              </div>
            </div>
          ))}
        </div>
      ) : cards.length === 0 ? (
        <div className="rounded-xl border border-border bg-bg-secondary">
          <EmptyState
            icon={FolderOpen}
            title="No submissions yet"
            description="Share the submission link above, or add an existing project. Each editor who signs in gets their own private folder here."
          />
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {cards.map((card) => {
            const isEditing = editingId === card.key
            return (
              <div key={card.key} className="group relative">
                <Link
                  href={`/projects/${card.projectId}`}
                  className="block rounded-xl overflow-hidden bg-bg-secondary border border-border hover:border-accent/40 transition-all duration-200 hover:shadow-lg hover:shadow-black/10"
                >
                  <div className="relative aspect-square w-full overflow-hidden bg-gradient-to-br from-violet-600 to-fuchsia-500">
                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_40%,rgba(255,255,255,0.1),transparent_60%)]" />
                    <div className="absolute inset-0 flex items-center justify-center">
                      <FolderOpen className="h-12 w-12 text-white/85 drop-shadow" />
                    </div>
                    <div className="absolute inset-x-0 bottom-0 h-20 bg-gradient-to-t from-black/70 via-black/30 to-transparent" />
                    <div className="absolute inset-x-0 bottom-0 p-3">
                      <p className="text-sm font-semibold text-white line-clamp-2 drop-shadow-sm">
                        {card.label}
                      </p>
                      {card.secondary && (
                        <p className="text-[11px] text-white/70 line-clamp-1">{card.secondary}</p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center justify-between px-3 py-2.5">
                    <span className="text-2xs text-text-tertiary">
                      {card.assetCount} file{card.assetCount !== 1 ? 's' : ''}
                    </span>
                  </div>
                </Link>

                {/* Rename */}
                <button
                  type="button"
                  onClick={() => startEditCard(card)}
                  title={card.kind === 'submission' ? 'Rename editor' : 'Rename project'}
                  aria-label="Rename"
                  className="absolute bottom-2 right-2.5 flex h-7 w-7 items-center justify-center rounded-md text-text-tertiary hover:bg-bg-hover hover:text-text-primary transition-all opacity-0 group-hover:opacity-100"
                >
                  <Pencil className="h-3.5 w-3.5" />
                </button>

                {/* Remove (attached projects only) */}
                {card.kind === 'attached' && (
                  <button
                    type="button"
                    onClick={() => detach(card.projectId)}
                    title="Remove from request"
                    aria-label="Remove from request"
                    className="absolute bottom-2 right-10 flex h-7 w-7 items-center justify-center rounded-md text-text-tertiary hover:bg-status-error/10 hover:text-status-error transition-all opacity-0 group-hover:opacity-100"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}

                {isEditing && (
                  <div className="absolute inset-x-0 top-0 z-10 flex items-center gap-1 rounded-t-xl border border-accent/40 bg-bg-secondary p-2 shadow-lg">
                    <input
                      autoFocus
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveCard(card)
                        if (e.key === 'Escape') setEditingId(null)
                      }}
                      placeholder={card.kind === 'submission' ? 'Editor name' : 'Project name'}
                      className="h-7 min-w-0 flex-1 rounded border border-border bg-bg-primary px-2 text-xs text-text-primary focus:outline-none focus:border-accent"
                    />
                    <button
                      type="button"
                      onClick={() => saveCard(card)}
                      disabled={savingHandle}
                      title="Save"
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded text-status-success hover:bg-bg-hover"
                    >
                      {savingHandle ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingId(null)}
                      title="Cancel"
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded text-text-tertiary hover:bg-bg-hover"
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      <PreAssignFolderDialog
        open={preAssignOpen}
        onOpenChange={setPreAssignOpen}
        linkId={id}
        onCreated={mutateSubs}
      />
    </div>
  )
}
