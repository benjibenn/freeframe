import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import {
  ReferenceImageCarousel,
  ReferenceVideoList,
  DownloadAllButton,
} from '../shared/reference-carousel'

/**
 * The `?download=1` suffix is the whole feature. These URLs 302 to S3, and an
 * anchor's `download` attribute is ignored cross-origin — so if the suffix is
 * missing or malformed the button silently opens the file instead of saving it,
 * AND the server-side brief_reference_downloaded audit row never gets written.
 * That is a failure you would not notice by looking at the page.
 */
const IMAGES = ['https://api.test/submit/tok/reference-image/0', 'https://api.test/submit/tok/reference-image/1']
const VIDEOS = ['https://api.test/submit/tok/reference-video/0']

describe('reference download links', () => {
  it('points the image download at ?download=1, not the inline URL', () => {
    render(<ReferenceImageCarousel urls={IMAGES} />)
    expect(screen.getByLabelText('Download image 1')).toHaveAttribute(
      'href',
      'https://api.test/submit/tok/reference-image/0?download=1',
    )
  })

  it('still offers a download when there is only one image', () => {
    // The single-image branch skips all the carousel chrome; the download button
    // is the one control that has to survive that shortcut.
    render(<ReferenceImageCarousel urls={[IMAGES[0]]} />)
    expect(screen.getByLabelText('Download image')).toHaveAttribute(
      'href',
      `${IMAGES[0]}?download=1`,
    )
  })

  it('follows the carousel, so the button saves the image on screen', () => {
    render(<ReferenceImageCarousel urls={IMAGES} />)
    fireEvent.click(screen.getByLabelText('Next image'))
    expect(screen.getByLabelText('Download image 2')).toHaveAttribute(
      'href',
      'https://api.test/submit/tok/reference-image/1?download=1',
    )
  })

  it('appends with & when the URL already carries a query string', () => {
    render(<ReferenceImageCarousel urls={['https://api.test/x?v=2']} />)
    expect(screen.getByLabelText('Download image')).toHaveAttribute(
      'href',
      'https://api.test/x?v=2&download=1',
    )
  })

  it('gives each video its own download link', () => {
    render(<ReferenceVideoList urls={VIDEOS} />)
    expect(screen.getByLabelText('Download video 1')).toHaveAttribute(
      'href',
      `${VIDEOS[0]}?download=1`,
    )
  })

  it('keeps controlsList=nodownload so the browser menu offers no unlogged second route', () => {
    const { container } = render(<ReferenceVideoList urls={VIDEOS} />)
    expect(container.querySelector('video')).toHaveAttribute('controlsList', 'nodownload noremoteplayback')
  })
})

describe('DownloadAllButton', () => {
  it('renders nothing for a single file — the per-item button already covers it', () => {
    const { container } = render(<DownloadAllButton urls={[IMAGES[0]]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the count so you know how many files are about to land', () => {
    render(<DownloadAllButton urls={IMAGES} />)
    expect(screen.getByRole('button', { name: /Download all \(2\)/ })).toBeInTheDocument()
  })
})
