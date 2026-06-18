import { describe, it, expect } from 'vitest'
import { enqueueWrite } from '../write-queue'

describe('enqueueWrite', () => {
  it('runs tasks for the same key strictly in order', async () => {
    const order: number[] = []
    const defer = () => {
      let resolve!: () => void
      const p = new Promise<void>((r) => (resolve = r))
      return { p, resolve }
    }
    const a = defer()
    const b = defer()

    const t1 = enqueueWrite('asset-1', async () => { await a.p; order.push(1) })
    const t2 = enqueueWrite('asset-1', async () => { await b.p; order.push(2) })

    b.resolve() // resolve the SECOND task's work first…
    a.resolve() // …but order must still be [1, 2]
    await Promise.all([t1, t2])
    expect(order).toEqual([1, 2])
  })

  it('does not block across different keys', async () => {
    const order: string[] = []
    const t1 = enqueueWrite('a', async () => { await new Promise((r) => setTimeout(r, 20)); order.push('a') })
    const t2 = enqueueWrite('b', async () => { order.push('b') })
    await Promise.all([t1, t2])
    expect(order[0]).toBe('b') // 'b' didn't wait on slow 'a'
  })
})
