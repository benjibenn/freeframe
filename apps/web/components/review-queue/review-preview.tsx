'use client'

import * as React from 'react'
import type { ReviewQueueItem } from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

/** The HLS proxy hands back paths relative to the API, like /stream/hls/... */
function absolute(url: string): string {
  return url.startsWith('/') ? `${API_URL}${url}` : url
}

function HlsVideo({ src, poster }: { src: string; poster: string | null }) {
  const ref = React.useRef<HTMLVideoElement>(null)
  React.useEffect(() => {
    const video = ref.current
    if (!video) return
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = src
      return
    }
    let cancelled = false
    let hls: { destroy(): void } | null = null
    import('hls.js').then(({ default: Hls }) => {
      if (cancelled || !Hls.isSupported()) return
      const instance = new Hls()
      instance.loadSource(src)
      instance.attachMedia(video)
      hls = instance
    })
    return () => {
      cancelled = true
      hls?.destroy()
    }
  }, [src])
  return <video ref={ref} controls poster={poster ?? undefined} className="max-h-full max-w-full" />
}

/** The big pane: image, video or audio, or the thumbnail while it processes. */
export function ReviewPreview({ item }: { item: ReviewQueueItem }) {
  if (!item.preview_url) {
    return (
      <div className="flex flex-col items-center gap-3 text-sm text-text-tertiary">
        {item.thumbnail_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={item.thumbnail_url} alt={item.file_name} className="max-h-[60vh] max-w-full object-contain opacity-60" />
        )}
        <p>Still processing — no preview yet.</p>
      </div>
    )
  }
  if (item.asset_type === 'video') {
    return <HlsVideo key={item.asset_id} src={absolute(item.preview_url)} poster={item.thumbnail_url} />
  }
  if (item.asset_type === 'audio') {
    return <audio key={item.asset_id} controls src={item.preview_url} className="w-full max-w-xl" />
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={item.preview_url} alt={item.file_name} className="max-h-full max-w-full object-contain" />
  )
}
