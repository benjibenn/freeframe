/**
 * The new-submitter tour.
 *
 * Written for creators who arrive through a request link: they upload hooks,
 * revise them, read reviewer feedback, and browse the footage library. It is
 * deliberately not an owner/reviewer tour — nothing here covers creating
 * requests or managing members.
 *
 * `target` is a `data-tour` key on a real element. The overlay follows the user
 * rather than driving them: if the current step's element isn't on screen it
 * shows `waitingFor` and jumps ahead as soon as a later step's element appears.
 * That is why the steps are ordered to match the natural path through the app
 * (project → asset → library) instead of being grouped by feature.
 */
export interface TourStep {
  id: string
  /** `data-tour` value to spotlight. `null` renders a centered card. */
  target: string | null
  title: string
  body: string
  /** Shown when the target isn't on this page — tells the user how to get there. */
  waitingFor?: string
  /**
   * True when the target lives in persistent layout chrome rather than page
   * content. The dashboard layout renders the sidebar outside `{children}`, so
   * such a target is in the DOM on every page and its presence says nothing
   * about where the user is. Look-ahead must skip these or the tour lands on
   * them immediately and can never be rewound.
   */
  alwaysMounted?: boolean
}

/**
 * The step to skip forward to, or -1 to stay put.
 *
 * Only ever looks forward, and only at page-scoped targets: a step is evidence
 * the user navigated somewhere only if its target appears and disappears with
 * the page. `isPresent` is injected so this stays pure and testable.
 */
export function lookAheadIndex(
  currentIndex: number,
  isPresent: (target: string) => boolean,
): number {
  return TOUR_STEPS.findIndex(
    (s, i) => i > currentIndex && s.target && !s.alwaysMounted && isPresent(s.target),
  )
}

export const TOUR_STEPS: TourStep[] = [
  {
    id: 'upload',
    target: 'upload-button',
    title: 'Upload your hooks',
    body: 'Click Upload and pick one or more files at once. You don’t name them — each new file is numbered for you: Hook 1, Hook 2, Hook 3, and so on.',
    waitingFor: 'Open your project from the sidebar to start uploading.',
  },
  {
    id: 'grid',
    target: 'asset-grid',
    title: 'Your hooks live here',
    body: 'One tile per hook. A tile shows the newest version of that hook. Click a tile to open it.',
    waitingFor: 'Open your project to see your hooks.',
  },
  {
    id: 'new-version',
    target: 'new-version-button',
    title: 'Revising? Upload a new version',
    body: 'Use New Version to replace the cut on this same hook. The hook keeps its number and every comment stays attached. Uploading from the project page instead would create a brand-new hook.',
    waitingFor: 'Click any hook to open it, and this step will continue.',
  },
  {
    id: 'comments',
    target: 'comments-tab',
    title: 'Read the feedback',
    body: 'Comments from your reviewer land here. Each one is pinned to a moment in the video — click a comment to jump the player straight to that timecode.',
    waitingFor: 'Open a hook to see its comments.',
  },
  {
    id: 'library',
    target: 'sidebar-library',
    alwaysMounted: true,
    title: 'Open the footage library',
    body: 'The Library is every clip you have access to, across all projects, in one grid — useful for finding footage you or your team already shot.',
    waitingFor: 'Look for Library in the left sidebar.',
  },
  {
    id: 'keywords',
    target: 'library-keywords',
    title: 'Tags describe the whole clip',
    body: 'A tag (shown here as Keywords) applies to an entire clip — things like kitchen, unboxing, or testimonial. Pick one or more to narrow the grid. Picking several shows clips that match any of them.',
    waitingFor: 'Open the Library to try the filters.',
  },
  {
    id: 'video-labels',
    target: 'library-video-labels',
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
