import { api } from './api'

/**
 * Upload an owner reference video for a submission link: presign a direct-to-S3 PUT,
 * upload the file straight to S3 (bypasses the API so large clips work), then confirm
 * the key back so the server records it. onProgress reports 0–100 during the S3 PUT.
 */
export async function uploadReferenceVideo(
  linkId: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<void> {
  const contentType = file.type || 'video/mp4'
  const { url, s3_key } = await api.post<{ url: string; s3_key: string }>(
    `/submission-links/${linkId}/reference-video/presign`,
    { filename: file.name, content_type: contentType },
  )

  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('PUT', url)
    // Must match the Content-Type the URL was signed with, or S3 rejects the PUT.
    xhr.setRequestHeader('Content-Type', contentType)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300 ? resolve() : reject(new Error(`Upload failed (${xhr.status})`))
    xhr.onerror = () => reject(new Error('Upload failed'))
    xhr.send(file)
  })

  await api.put(`/submission-links/${linkId}/reference-video`, { s3_key })
}
