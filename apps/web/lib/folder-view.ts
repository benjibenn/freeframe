/**
 * File view: the project page's folder listing, flattened.
 *
 * The folder view shows three kinds of row — subfolders, briefs and files. File
 * view drops the containers and lists every file beneath the folder instead, so
 * a store folder can be read without opening each model and each brief.
 *
 * The three decisions below live here rather than inline in the page because
 * each has a way of going quietly wrong: a folder click that loses the view, a
 * tag filter that leaves a stale flat grid on screen, or a key that keeps
 * pointing at the folder-scoped endpoint.
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
 * Whether file view is actually in effect.
 *
 * A tag or moment filter turns the grid into a project-wide search, and an open
 * brief replaces it with that brief's submissions. Both already drop the folder
 * listing, so file view yields to them instead of fighting over the same grid.
 */
export function isFileViewActive(
  fileView: boolean,
  opts: { filteringByTagOrLabel: boolean; openBriefId: string | null },
): boolean {
  return fileView && !opts.filteringByTagOrLabel && !opts.openBriefId;
}

/**
 * The endpoint the grid pages through, without its skip/limit.
 *
 * Flattening needs the server: a brief's files live in each submitter's own
 * project, so the browser cannot name them, and the two sources have to be
 * unioned before LIMIT or the pages drift.
 */
export function assetsBasePath(
  projectId: string,
  opts: {
    fileViewActive: boolean;
    currentFolderId: string | null;
    assetsQuery: string;
  },
): string {
  return opts.fileViewActive
    ? `/projects/${projectId}/folder-files?folder_id=${opts.currentFolderId ?? "root"}`
    : `/projects/${projectId}/assets?${opts.assetsQuery}`;
}
