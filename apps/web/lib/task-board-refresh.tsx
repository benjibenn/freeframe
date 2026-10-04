'use client'

import * as React from 'react'

/**
 * How a row, the pipeline or the stages dialog asks the tasks page to reload
 * its board after a change. The board is a paged useSWRInfinite list, which a
 * global mutate('/task-board') does not reach (SWR's key filter skips infinite
 * keys), so the page hands its own bound mutate down instead.
 *
 * Outside the tasks page (component tests) there is nothing to reload, so the
 * default does nothing.
 */
const TaskBoardRefreshContext = React.createContext<() => void>(() => {})

export const TaskBoardRefreshProvider = TaskBoardRefreshContext.Provider

export function useTaskBoardRefresh(): () => void {
  return React.useContext(TaskBoardRefreshContext)
}
