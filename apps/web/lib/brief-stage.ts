import type { BriefEditor, BriefTaskItem } from '@/types'

/**
 * Whose status a brief is read by, for the reader looking at it.
 *
 * A brief carries two kinds of status: its own, and one per editor on it. Which
 * one answers "where is this" depends on who is asking, and the tasks page shows
 * the same briefs three ways — stage chips, pipeline columns, rows. Answering it
 * differently in each place is what this module exists to stop: an editor filtered
 * by the brief's status while grouped by their own reads as two contradictory
 * screens, and neither tells them what they can actually move.
 */

/** The reader's own editor row on a brief, if they have one.
 *
 *  Nothing for an admin: their board is the roll-up over every editor, so the
 *  brief's own status is the one they work. Nothing either for a non-admin who
 *  owns the brief without making it — they own it, so it is theirs to move.
 *
 *  `asEditorId` is an admin looking at one editor's desk: the brief is then read
 *  as that editor reads it, so the admin sees where they actually are. */
export function ownEditorRow(
  brief: BriefTaskItem,
  viewerId: string | undefined,
  isAdmin: boolean,
  asEditorId?: string | null,
): BriefEditor | undefined {
  if (asEditorId) return brief.editors.find((e) => e.id === asEditorId)
  if (isAdmin) return undefined
  return brief.editors.find((e) => e.id === viewerId)
}

/** The stage this brief sits in from the reader's point of view: their own if
 *  they are an editor on it, otherwise the brief's. */
export function stageOf(
  brief: BriefTaskItem,
  viewerId: string | undefined,
  isAdmin: boolean,
  asEditorId?: string | null,
): string | null {
  const own = ownEditorRow(brief, viewerId, isAdmin, asEditorId)
  return (own ? own.task_stage_id : brief.task_stage_id) ?? null
}
