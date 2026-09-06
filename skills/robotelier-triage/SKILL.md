---
name: robotelier-triage
description: Classify registered robotics candidates for bounded research admission with auditable reasons and coverage diversity.
metadata:
  version: 1.0.0
---

# Triage

Read registered metadata, recent developments, queue summaries, category coverage, and shared-cycle
budget. Assign exactly one decision: `ingest`, `defer`, or `ignore`, with a concise English reason.
Prioritize meaningful changes and primary material; engagement is not evidence. Rotate categories
so one prolific humanoid company does not monopolize work, while retaining the humanoid focus.

Use only `robotelier queue enqueue` for admitted bounded investigations. A research request names a
specific question, source references, dependencies, deadline, and resource ceiling. Do not edit
sources, claims, scores, cursors, or queue state directly. Preserve candidates deferred by limits;
reserve the required publication/editorial capacity.

Return decisions, category/coverage rationale, admitted operation IDs, and typed reasons including
`duplicate_transport`, `outside_robotics_scope`, `insufficient_metadata`, `research_bound_reached`,
or `budget_reserved`. Do not research the candidate inside triage.
