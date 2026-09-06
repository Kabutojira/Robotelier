---
name: robotelier-podcast-write
description: Write one English single-narrator script using only a controller-frozen evidence package.
metadata:
  version: 1.0.0
---

# Podcast writing

Read only the selected frozen package and relevant script request. Do not browse, change research,
choose another idea, or introduce a plausible fact absent from the package. Return a specific
evidence-gap request when the package cannot support a needed sentence.

Write natural English spoken prose for robotics listeners: open with the question and stakes,
explain necessary terms, distinguish demonstrations from deployable capability, attribute maker
claims and disagreement, and close with useful conclusions and uncertainty. One narrator only. Do
not narrate IDs, URLs, repository bookkeeping, source counts, tables, investment ratings, or generic
padding. The 1,400–2,800 word range is planning guidance; measured audio must ultimately be
600–1,200 seconds.

Provide stable segment IDs, semantic role, spoken text, exact factual claim revisions, and optional
source-media candidates with source time coordinates. Greeting/transitions are explicitly
nonfactual. Use only the permitted podcast validation command and episode/wiki paths. Do not render
audio or edit an independent transcript copy.

Submit canonical segments and show-note prose as a draft with `podcast validate-script`; never set
`seal` and never claim an independent review. Use `evidence_gap`, `outline_not_dense`, or
`frozen_context_invalid` instead of speculation.
