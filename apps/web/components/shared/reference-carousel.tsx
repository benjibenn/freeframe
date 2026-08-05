'use client'

import * as React from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * Reference images as a carousel: one image at a time with prev/next arrows and
 * dots. A single image renders plain — no chrome for nothing to navigate.
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

  if (urls.length === 1) return <div className={className}>{img(urls[0])}</div>

  return (
    <div className={cn('relative', className)}>
      {img(urls[safeIndex])}
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
 *  glance-compare videos, and a hidden playing video is a bug factory). */
export function ReferenceVideoList({ urls, className }: { urls: string[]; className?: string }) {
  if (urls.length === 0) return null
  return (
    <div className={cn('flex flex-col gap-3', className)}>
      {urls.map((src) => (
        <video
          key={src}
          controls
          playsInline
          preload="metadata"
          src={src}
          className="w-full rounded-lg border border-border bg-black"
          controlsList="nodownload noremoteplayback"
          disablePictureInPicture
          onContextMenu={(e) => e.preventDefault()}
        />
      ))}
    </div>
  )
}
