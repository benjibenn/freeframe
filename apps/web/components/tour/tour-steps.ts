/**
 * The new-submitter tour.
 *
 * Written for creators who arrive through a request link: they upload hooks,
 * revise them, read reviewer feedback, and browse the footage library. It is
 * deliberately not an owner/reviewer tour — nothing here covers creating
 * requests or managing members, and it is shown only to users who hold `editor`
 * somewhere (see lib/tour-context.ts).
 *
 * `target` is a `data-tour` key on a real element; `page` is where that element
 * lives. The overlay navigates to a step's page rather than asking the user to
 * find it, so the steps are ordered to match the natural path through the app
 * (project → asset → library) instead of being grouped by feature.
 */
export type TourPage = 'project' | 'asset' | 'library'

/** The concrete project/asset the tour walks the user through, resolved once at start. */
export interface TourContext {
  projectId: string
  assetId: string | null
}

export interface TourStep {
  id: string
  /** `data-tour` value to spotlight. `null` renders a centered card. */
  target: string | null
  title: string
  body: string
  /** Shown when the target isn't on this page — tells the user how to get there. */
  waitingFor?: string
  /**
   * Page this step's target lives on. Absent means the step is valid wherever
   * the user already is: the library step points at the sidebar, which is
   * mounted everywhere, so navigating on it would contradict its own copy.
   */
  page?: TourPage
}

export function stepHref(page: TourPage, ctx: TourContext): string | null {
  switch (page) {
    case 'project':
      return `/projects/${ctx.projectId}`
    case 'asset':
      return ctx.assetId ? `/projects/${ctx.projectId}/assets/${ctx.assetId}` : null
    case 'library':
      return '/library'
  }
}

/** Steps this context can actually reach. Without an asset there is no asset page. */
export function visibleSteps(ctx: TourContext): TourStep[] {
  if (ctx.assetId) return TOUR_STEPS
  return TOUR_STEPS.filter((s) => s.page !== 'asset')
}

export const TOUR_STEPS: TourStep[] = [
  {
    id: 'upload',
    target: 'upload-button',
    page: 'project',
    title: 'Upload your hooks',
    body: 'Click Upload and pick one or more files at once. You don’t name them — each new file is numbered for you: Hook 1, Hook 2, Hook 3, and so on.',
    waitingFor: 'Open your project from the sidebar to start uploading.',
  },
  {
    id: 'grid',
    target: 'asset-grid',
    page: 'project',
    title: 'Your hooks live here',
    body: 'One tile per hook. A tile shows the newest version of that hook. Click a tile to open it.',
    waitingFor: 'Open your project to see your hooks.',
  },
  {
    id: 'new-version',
    target: 'new-version-button',
    page: 'asset',
    title: 'Revising? Upload a new version',
    body: 'Use New Version to replace the cut on this same hook. The hook keeps its number and every comment stays attached. Uploading from the project page instead would create a brand-new hook.',
    waitingFor: 'Click any hook to open it, and this step will continue.',
  },
  {
    id: 'comments',
    target: 'comments-tab',
    page: 'asset',
    title: 'Read the feedback',
    body: 'Comments from your reviewer land here. Each one is pinned to a moment in the video — click a comment to jump the player straight to that timecode.',
    waitingFor: 'Open a hook to see its comments.',
  },
  {
    id: 'library',
    target: 'sidebar-library',
    title: 'Open the footage library',
    body: 'The Library is every clip you have access to, across all projects, in one grid — useful for finding footage you or your team already shot.',
    waitingFor: 'Look for Library in the left sidebar.',
  },
  {
    id: 'keywords',
    target: 'library-keywords',
    page: 'library',
    title: 'Tags describe the whole clip',
    body: 'A tag (shown here as Keywords) applies to an entire clip — things like kitchen, unboxing, or testimonial. Pick one or more to narrow the grid. Picking several shows clips that match any of them.',
    waitingFor: 'Open the Library to try the filters.',
  },
  {
    id: 'video-labels',
    target: 'library-video-labels',
    page: 'library',
    title: 'Video tags mark a moment inside a clip',
    body: 'A video tag (shown as Video Labels) is pinned to a timecode, not the whole clip — hook, cta, product reveal. Filter by one to find every clip that contains that moment, then jump straight to it.',
    waitingFor: 'Open the Library to try the filters.',
  },
  {
    id: 'done',
    target: null,
    title: 'That’s the loop',
    body: 'Upload hooks → read comments → upload a new version of the hook you’re revising. Reach for the Library when you need footage that already exists. You can replay this tour any time from the ? button in the header.',
  },
]
