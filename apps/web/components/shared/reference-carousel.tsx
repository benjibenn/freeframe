'use client'

import * as React from 'react'
import { ChevronLeft, ChevronRight, Download } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Reference URLs point at an API route that 302s to a presigned S3 URL. An anchor's
 * `download` attribute is ignored cross-origin, so forcing a save has to happen
 * server-side: `?download=1` makes the presign carry Content-Disposition: attachment.
 * That same flag is what the API records as brief_reference_downloaded.
 */
function withDownload(url: string): string {
  return `${url}${url.includes('?') ? '&' : '?'}download=1`
}

/** Click a throwaway anchor per file, spaced out — browsers drop bursts of
 *  simultaneous navigations, and each one still has its own redirect to survive. */
async function triggerDownloads(urls: string[]): Promise<void> {
  for (const url of urls) {
    const a = document.createElement('a')
    a.href = withDownload(url)
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    a.remove()
    await new Promise((resolve) => setTimeout(resolve, 400))
  }
}

/** Single-file download control, styled as a dark chip for overlaying on media. */
function DownloadOverlay({ url, label, className }: { url: string; label: string; className?: string }) {
  return (
    <a
      href={withDownload(url)}
      aria-label={label}
      title={label}
      className={cn(
        'absolute z-10 rounded-full bg-black/50 p-1.5 text-white transition-colors hover:bg-black/70',
        className,
      )}
    >
      <Download className="h-4 w-4" />
    </a>
  )
}

/**
 * "Download all" for a set of references, rendered beside a section heading on both
 * the dashboard brief popup and the public submit page. Renders nothing for a single
 * file — the per-item button already covers that case.
 */
export function DownloadAllButton({ urls, className }: { urls: string[]; className?: string }) {
  const [busy, setBusy] = React.useState(false)
  if (urls.length < 2) return null
  return (
    <button
      type="button"
      disabled={busy}
      onClick={async () => {
        setBusy(true)
        try {
          await triggerDownloads(urls)
        } finally {
          setBusy(false)
        }
      }}
      className={cn(
        'inline-flex items-center gap-1.5 text-xs font-medium text-text-tertiary transition-colors hover:text-text-primary disabled:opacity-50',
        className,
      )}
    >
      <Download className="h-3.5 w-3.5" />
      {busy ? 'Downloading…' : `Download all (${urls.length})`}
    </button>
  )
}

/**
 * Reference images as a carousel: one image at a time with prev/next arrows and
 * dots. A single image renders without navigation chrome — but still gets its
 * download button, which is the one control that applies to every case.
 *
 * Deliberately dependency-free: the brief page is also shown to signed-out
 * guests, so it stays light. Images are served via API redirects to short-lived
 * presigned URLs, which next/image can't optimize — hence the raw <img>.
 */
export function ReferenceImageCarousel({ urls, className }: { urls: string[]; className?: string }) {
  const [index, setIndex] = React.useState(0)
  // If an image is removed while open (admin pages mutate the list), stay in range.
  const safeIndex = Math.min(index, urls.length - 1)

  if (urls.length === 0) return null

  const img = (src: string) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt="Reference ad to adapt"
      className="w-full rounded-lg border border-border bg-bg-primary"
      onContextMenu={(e) => e.preventDefault()}
    />
  )

  if (urls.length === 1)
    return (
      <div className={cn('relative', className)}>
        {img(urls[0])}
        <DownloadOverlay url={urls[0]} label="Download image" className="right-2 top-2" />
      </div>
    )

  return (
    <div className={cn('relative', className)}>
      {img(urls[safeIndex])}
      {/* Left of the "n / total" counter, which owns the top-right corner. */}
      <DownloadOverlay
        url={urls[safeIndex]}
        label={`Download image ${safeIndex + 1}`}
        className="right-12 top-2"
      />
      <button
        type="button"
        aria-label="Previous image"
        onClick={() => setIndex((safeIndex - 1 + urls.length) % urls.length)}
        className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-black/50 p-1.5 text-white hover:bg-black/70"
      >
        <ChevronLeft className="h-4 w-4" />
      </button>
      <button
        type="button"
        aria-label="Next image"
        onClick={() => setIndex((safeIndex + 1) % urls.length)}
        className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-black/50 p-1.5 text-white hover:bg-black/70"
      >
        <ChevronRight className="h-4 w-4" />
      </button>
      <div className="absolute inset-x-0 bottom-2 flex items-center justify-center gap-1.5">
        {urls.map((u, i) => (
          <button
            key={u}
            type="button"
            aria-label={`Image ${i + 1} of ${urls.length}`}
            onClick={() => setIndex(i)}
            className={cn(
              'h-1.5 w-1.5 rounded-full transition-colors',
              i === safeIndex ? 'bg-white' : 'bg-white/40 hover:bg-white/70',
            )}
          />
        ))}
      </div>
      <span className="absolute right-2 top-2 rounded bg-black/50 px-1.5 py-0.5 text-[10px] text-white">
        {safeIndex + 1} / {urls.length}
      </span>
    </div>
  )
}

/** Reference videos stacked — players don't belong in a carousel (you can't
 *  glance-compare videos, and a hidden playing video is a bug factory).
 *
 *  The download button sits above each player rather than overlaid on it: an
 *  overlay would land on the native controls, and `controlsList="nodownload"`
 *  stays so the browser's own menu doesn't offer a second, unlogged route out. */
export function ReferenceVideoList({ urls, className }: { urls: string[]; className?: string }) {
  if (urls.length === 0) return null
  return (
    <div className={cn('flex flex-col gap-3', className)}>
      {urls.map((src, i) => (
        <div key={src} className="flex flex-col gap-1">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-text-tertiary">
              {urls.length > 1 ? `Video ${i + 1}` : ''}
            </span>
            <a
              href={withDownload(src)}
              aria-label={`Download video ${i + 1}`}
              title="Download video"
              className="inline-flex items-center gap-1.5 text-xs font-medium text-text-tertiary transition-colors hover:text-text-primary"
            >
              <Download className="h-3.5 w-3.5" />
              Download
            </a>
          </div>
          <video
            controls
            playsInline
            preload="metadata"
            src={src}
            className="w-full rounded-lg border border-border bg-black"
            controlsList="nodownload noremoteplayback"
            disablePictureInPicture
            onContextMenu={(e) => e.preventDefault()}
          />
        </div>
      ))}
    </div>
  )
}
