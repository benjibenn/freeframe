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
