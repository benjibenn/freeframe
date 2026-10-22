/**
 * File view: the project page's folder listing, flattened.
 *
 * The folder view shows three kinds of row — subfolders, briefs and files. A
 * flattened grid drops the containers and lists every file beneath the folder
 * instead, so a store folder can be read without opening each model and then
 * each brief.
 *
 * Three things flatten the grid: the File view toggle and — because one folder
 * level holds almost no files when the work sits in briefs — a name query or a
 * status chip.
 * The decisions live here rather than inline in the page because each has a way
 * of going quietly wrong: a folder click that loses the view, a stale flat grid
 * left on screen by a tag filter, or a key still pointing at the folder-scoped
 * endpoint.
 */

/** The project URL for a folder and view, so navigation and the toggle agree. */
export function projectUrl(
  projectId: string,
  folderId: string | null,
  fileView: boolean,
): string {
  const params = new URLSearchParams();
  if (folderId) params.set("folder", folderId);
  if (fileView) params.set("view", "files");
  const qs = params.toString();
  return `/projects/${projectId}${qs ? `?${qs}` : ""}`;
}

/**
 * Whether the grid is flattened right now.
 *
 * This is the page's single gate. Everything that must behave differently in a
 * flattened grid reads it: which endpoint the grid pages through, whether the
 * subfolder and brief tiles are drawn, and which writes are withheld. A flat
 * grid holds the submitters' files, which belong to other projects, so move,
 * delete, rename and the multi-select share must be off — keying any of those
 * off the toggle alone would re-open that hole as soon as a query flattens.
 *
 * A tag or moment filter turns the grid into a project-wide search, and an open
 * brief replaces it with that brief's submissions. Both already drop the folder
 * listing, so flattening yields to them rather than fighting over the grid.
 */
export function isFlattened(opts: {
  fileView: boolean;
  query: string;
  stageIds: string[];
  filteringByTagOrLabel: boolean;
  openBriefId: string | null;
}): boolean {
  if (opts.openBriefId) return false;
  if (opts.filteringByTagOrLabel) return false;
  return (
    opts.fileView || opts.query.trim() !== "" || opts.stageIds.length > 0
  );
}

/**
 * The endpoint the grid pages through, without its skip/limit.
 *
 * Flattening needs the server: a brief's files live in each submitter's own
 * project, so the browser cannot name them, and the two sources have to be
 * unioned before LIMIT or the pages drift. The query rides along either way, so
 * it narrows the folder listing and the tag search too.
 */
export function assetsBasePath(
  projectId: string,
  opts: {
    flattened: boolean;
    currentFolderId: string | null;
    assetsQuery: string;
    query: string;
    stageIds: string[];
  },
): string {
  const base = opts.flattened
    ? `/projects/${projectId}/folder-files?folder_id=${opts.currentFolderId ?? "root"}`
    : `/projects/${projectId}/assets?${opts.assetsQuery}`;
  const extra = new URLSearchParams();
  const q = opts.query.trim();
  if (q) extra.set("q", q);
  // Repeated, not comma-joined: the API reads stage_id as a list, and ORs it.
  for (const id of opts.stageIds) extra.append("stage_id", id);
  const tail = extra.toString();
  return tail ? `${base}&${tail}` : base;
}

/** What the grid is actually searching, for the hint under the search box. */
export function searchScopeHint(
  opts: { flattened: boolean; filteringByTagOrLabel: boolean },
  folderName: string,
): string {
  if (opts.filteringByTagOrLabel) return "Searching the tagged files";
  if (opts.flattened) return `Searching everything under ${folderName}`;
  return `Searching ${folderName}`;
}

// ── Remembering the view ─────────────────────────────────────────────────────
//
// Per project, not per folder: the shape of a project is what makes file view
// the right default ("this one is all briefs"), and a per-folder memory would
// make the grid change form as you walk the tree.

const REMEMBERED_VIEW_PREFIX = "ff:fileView:";

/**
 * Which view the page should open in.
 *
 * The URL wins, so a pasted or bookmarked link always lands where it says. Only
 * when it says nothing does the remembered default apply.
 */
export function initialFileView(
  urlView: string | null,
  remembered: boolean,
): boolean {
  if (urlView !== null) return urlView === "files";
  return remembered;
}

/** The remembered default, or false. Storage can throw, so this never does. */
export function readRememberedView(projectId: string): boolean {
  try {
    return localStorage.getItem(REMEMBERED_VIEW_PREFIX + projectId) === "files";
  } catch {
    return false;
  }
}

/** Remember the view just chosen. Silent when storage is unavailable. */
export function rememberView(projectId: string, fileView: boolean): void {
  try {
    localStorage.setItem(
      REMEMBERED_VIEW_PREFIX + projectId,
      fileView ? "files" : "folders",
    );
  } catch {
    // Private mode, blocked site data, quota — a forgotten preference is not
    // worth breaking the toggle over.
  }
}
