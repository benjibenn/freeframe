/**
 * Narrowing the brief rows in a folder.
 *
 * Briefs are the folder view's other half: a folder can hold a hundred of them,
 * and "which ones still have nothing", "which ones are mine to place" and
 * "which ones are at this stage" are the questions that otherwise mean opening
 * them one at a time.
 *
 * All of it runs in the browser, against the brief list the page already holds —
 * no new endpoint, and no new request per filter.
 */

/** Whether an editor has submitted anything against the brief yet. */
export type BriefFileFilter = "all" | "with" | "without";

export interface BriefFilterState {
  files: BriefFileFilter;
  /** Only briefs with nobody's name on them. */
  unassignedOnly: boolean;
  /** Pipeline stages of the brief itself; empty means any. */
  stageIds: string[];
}

export const NO_BRIEF_FILTERS: BriefFilterState = {
  files: "all",
  unassignedOnly: false,
  stageIds: [],
};

/** True when nothing is being narrowed, so the page can skip the work. */
export function briefFiltersAreOff(state: BriefFilterState): boolean {
  return (
    state.files === "all" &&
    !state.unassignedOnly &&
    state.stageIds.length === 0
  );
}

interface FilterableBrief {
  id: string;
  assignee_id?: string | null;
  task_stage_id?: string | null;
}

/**
 * The briefs that pass every active filter (they AND together).
 *
 * `fileCounts` is the map from GET /brief-file-counts, which leaves out briefs
 * with no submissions — so a missing id means zero, not unknown. The stage set
 * ORs within itself, like the file status chips, since a brief sits at one
 * stage; "none" is a member of that set so untriaged briefs stay reachable.
 */
export function filterBriefs<T extends FilterableBrief>(
  briefs: T[],
  fileCounts: Record<string, number>,
  state: BriefFilterState,
): T[] {
  if (briefFiltersAreOff(state)) return briefs;
  return briefs.filter((brief) => {
    const files = fileCounts[brief.id] ?? 0;
    if (state.files === "with" && files === 0) return false;
    if (state.files === "without" && files > 0) return false;
    if (state.unassignedOnly && brief.assignee_id) return false;
    if (state.stageIds.length > 0) {
      const stage = brief.task_stage_id ?? "none";
      if (!state.stageIds.includes(stage)) return false;
    }
    return true;
  });
}
