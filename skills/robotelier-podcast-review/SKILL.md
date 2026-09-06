---
name: robotelier-podcast-review
description: Independently fact-check a frozen Robotelier script clause by clause and review listening quality before rendering.
metadata:
  version: 1.0.0
---

# Podcast review

Read the frozen package and canonical script only; do not browse or replace research. For every
material factual clause, verify exact support, attribution, date, number, unit, conditions,
configuration, uncertainty, novelty, and source independence. Check robotics demo caveats and reject
unsupported conclusions joined to supported numbers. A reachable citation alone is not support.

Also review one-narrator English listening quality, density, structure, repetition, jargon, hype,
and standalone comprehension. Return accepted/rejected segment IDs and specific corrections. Allow
at most two repair rounds. Use only the permitted podcast validation command and review/episode
paths. Do not select another idea, fetch new evidence, render, deliver, or change released text.

Set factual-support, attribution, listening-quality, novelty, and density gates explicitly. Use
`unsupported_clause`, `attribution_error`, `numeric_mismatch`, `missing_conditions`,
`material_repetition`, `too_thin`, or `evidence_gap` for failures.

On acceptance, seal only the exact content-addressed writer draft through `podcast
validate-script`; do not supply alternate prose. The controller verifies that writer and reviewer
are distinct leased operations and stores the review as a separate canonical revision.
