import { api } from '@/lib/api'
import type { TourContext } from '@/components/tour/tour-steps'
import type { Asset, Project } from '@/types'

/**
 * The project the tour walks through, or null when the user is an editor
 * nowhere — which is also the "editors only" gate.
 *
 * Projects with assets win over newer empty ones: the two asset steps only
 * exist when an asset does, so this maximises how much of the tour is
 * reachable. `Project` has no `updated_at`, so recency means `created_at`.
 */
export function resolveTargetProject(projects: Project[]): Project | null {
  const editable = projects.filter((p) => p.role === 'editor')
  if (editable.length === 0) return null

  const withAssets = editable.filter((p) => (p.asset_count ?? 0) > 0)
  const pool = withAssets.length > 0 ? withAssets : editable

  return pool.reduce((newest, p) =>
    Date.parse(p.created_at) > Date.parse(newest.created_at) ? p : newest,
  )
}

/** Resolves the context once, at tour start. Null means the tour must not run. */
export async function loadTourContext(): Promise<TourContext | null> {
  const projects = await api.get<Project[]>('/projects')
  const target = resolveTargetProject(projects)
  if (!target) return null

  // asset_count is already in the list payload, so an empty project costs no
  // second request.
  if ((target.asset_count ?? 0) === 0) return { projectId: target.id, assetId: null }

  const assets = await api.get<Asset[]>(`/projects/${target.id}/assets?skip=0&limit=1`)
  return { projectId: target.id, assetId: assets[0]?.id ?? null }
}
