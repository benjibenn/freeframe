/**
 * Starter structured brief, shaped after the team's real briefs: static-ad
 * adaptations of a reference ad, varied by language and price.
 *
 * One copy shared by every surface that offers it (submissions page, in-project
 * request dialog, request detail) so the starting point cannot drift apart.
 */
export const SAMPLE_BRIEF_JSON = `{
  "title": "Static - iPhone",
  "overview": "Adapt the reference ad below into 2 localised static variations. Layout, composition and product framing stay as-is — only the copy and the price change.\\n\\nReference ad: https://app.gethookd.ai/share/ad/131405144",
  "output_languages": ["German", "Swedish"],
  "final_deliverable": {
    "label": "2 static images — German and Swedish — matching the reference ad's dimensions",
    "hook_variations": [
      {
        "variation": "German",
        "script_voiceover": "All copy translated to German",
        "shot": "Identical to reference ad — same scene, model and composition",
        "on_screen_text": "Price: 255 EUR"
      },
      {
        "variation": "Swedish",
        "script_voiceover": "All copy translated to Swedish",
        "shot": "Identical to reference ad — same scene, model and composition",
        "on_screen_text": "Price: 2800 SEK"
      }
    ]
  },
  "guidelines": [
    "Work from the reference ad linked in the overview — do not redesign it",
    "Only the copy language and the price differ between variations",
    "Keep the original scene, model, product framing and layout unchanged",
    "Match the reference ad's dimensions and safe areas",
    "Deliver each variation as a separate file, named by language"
  ]
}`

/**
 * Output languages live inside the brief JSON (key: output_languages) — one source
 * of truth shared by the setup forms' dedicated input and the JSON textarea. These
 * helpers translate between the comma-separated input and the JSON array.
 */
export function languagesFromBrief(brief: unknown): string {
  if (typeof brief !== 'object' || brief === null || Array.isArray(brief)) return ''
  const raw = (brief as Record<string, unknown>).output_languages
  if (!Array.isArray(raw)) return ''
  return raw.filter((l): l is string => typeof l === 'string' && !!l.trim()).join(', ')
}

export function parseLanguages(input: string): string[] {
  return input
    .split(',')
    .map((l) => l.trim())
    .filter(Boolean)
}

/**
 * Merge the languages input into a brief object before saving. A non-empty input
 * wins over whatever the JSON textarea says (the input is the visible control);
 * an empty input removes the key. Returns null only if brief is null AND no
 * languages were given — languages alone are enough to warrant a brief object.
 */
export function withLanguages(
  brief: Record<string, unknown> | null,
  languagesInput: string,
): Record<string, unknown> | null {
  const langs = parseLanguages(languagesInput)
  if (!brief) return langs.length > 0 ? { output_languages: langs } : null
  const next = { ...brief }
  if (langs.length > 0) next.output_languages = langs
  else delete next.output_languages
  return next
}
