'use client'

/**
 * Renders a structured JSON brief (title / overview / script+storyboard / guidelines /
 * final deliverable). Deliberately defensive: every section is optional and only shown
 * when present and well-shaped, so briefs can vary without breaking the page.
 */

type Shot = {
  variation?: string
  name?: string
  script?: string
  shot?: string
  on_screen_text?: string
}

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function StoryboardRows({ rows }: { rows: Shot[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[36rem] border-collapse text-sm">
        <thead>
          <tr className="bg-bg-tertiary text-left text-xs text-text-tertiary">
            <th className="w-8 px-3 py-2 font-medium">#</th>
            <th className="px-3 py-2 font-medium">Script</th>
            <th className="px-3 py-2 font-medium">Shot</th>
            <th className="px-3 py-2 font-medium">On-screen text</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border align-top">
              <td className="px-3 py-2.5 text-xs text-text-tertiary">{i + 1}</td>
              <td className="px-3 py-2.5 text-text-primary">{r.script}</td>
              <td className="px-3 py-2.5 text-text-secondary">{r.shot}</td>
              <td className="px-3 py-2.5 text-text-secondary">{r.on_screen_text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">{title}</h3>
      {children}
    </section>
  )
}

export function BriefView({ data }: { data: Record<string, unknown> }) {
  if (!isObj(data)) return null

  const title = typeof data.title === 'string' ? data.title : null
  const overview = typeof data.overview === 'string' ? data.overview : null
  const storyboard: Shot[] = Array.isArray(data.script_with_storyboard)
    ? (data.script_with_storyboard.filter(isObj) as Shot[])
    : []
  const guidelines = isObj(data.guidelines) ? data.guidelines : null
  const hardRules =
    guidelines && Array.isArray(guidelines.hard_rules)
      ? (guidelines.hard_rules as unknown[]).filter((x): x is string => typeof x === 'string')
      : []
  const deliverable = isObj(data.final_deliverable) ? data.final_deliverable : null
  const concept = deliverable && typeof deliverable.concept === 'string' ? deliverable.concept : null
  const hooks: Shot[] =
    deliverable && Array.isArray(deliverable.hook_variations)
      ? (deliverable.hook_variations.filter(isObj) as Shot[])
      : []

  return (
    <div className="flex flex-col gap-6">
      {title && <h2 className="text-lg font-semibold text-text-primary">{title}</h2>}

      {overview && (
        <Section title="Overview">
          <p className="text-sm leading-relaxed text-text-secondary">{overview}</p>
        </Section>
      )}

      {storyboard.length > 0 && (
        <Section title="Script & storyboard">
          <StoryboardRows rows={storyboard} />
        </Section>
      )}

      {hardRules.length > 0 && (
        <Section title="Guidelines">
          <ul className="flex flex-col gap-1.5">
            {hardRules.map((rule, i) => (
              <li key={i} className="flex gap-2 text-sm text-text-secondary">
                <span className="mt-0.5 shrink-0 text-status-error">•</span>
                <span>{rule}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {(concept || hooks.length > 0) && (
        <Section title="Final deliverable">
          {concept && (
            <p className="text-sm text-text-primary">
              <span className="text-text-tertiary">Concept: </span>
              {concept}
            </p>
          )}
          {hooks.length > 0 && (
            <div className="mt-1 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {hooks.map((h, i) => (
                <div key={i} className="flex flex-col gap-1 rounded-lg border border-border bg-bg-secondary p-3">
                  <p className="text-xs font-semibold text-text-primary">
                    {h.variation || `Hook ${i + 1}`}
                    {h.name ? ` — ${h.name}` : ''}
                  </p>
                  {h.script && <p className="text-sm text-text-secondary">{h.script}</p>}
                  {h.shot && (
                    <p className="text-xs text-text-tertiary">
                      <span className="font-medium">Shot: </span>
                      {h.shot}
                    </p>
                  )}
                  {h.on_screen_text && (
                    <p className="text-xs text-text-tertiary">
                      <span className="font-medium">On-screen: </span>
                      {h.on_screen_text}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </Section>
      )}
    </div>
  )
}
