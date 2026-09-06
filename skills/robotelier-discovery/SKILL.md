---
name: robotelier-discovery
description: Discover bounded robotics source leads and register source/media metadata without treating search output as evidence.
metadata:
  version: 1.0.0
---

# Discovery

Inspect the assigned subscriptions/queries within their page, candidate, and time bounds. Include
global robotics coverage; use humanoid relevance as a preference, not an exclusion rule. Preserve
source-language titles and identifiers while writing all analysis in English.

Register every candidate source identity and relevant image/video/audio metadata before proposing
`ingest`, `defer`, or `ignore`. Use `robotelier source register`, `source observe` only for bytes or
metadata actually inspected, `media register`, and `queue enqueue` only as allowed. Never infer an
official handle, creator, license, direct asset URL, event date, autonomy, or capability. A signed
asset URL is omitted in favor of the stable page/platform identity.

Write only assigned source/media/run paths. Do not create entity facts from titles/snippets, fetch
private-network URLs, bypass access controls, download media/thumbnails/captions, or claim an
exhaustive stream from bounded search. Advance a cursor only through controller commands after all
retained candidates are registered/classified.

Output registered identities, classifications with reasons, bounded coverage, failures per
adapter, and at most the allowed concrete follow-ups. Use typed outcomes such as
`source_access_restricted`, `adapter_throttled`, `pagination_incomplete`, `metadata_incomplete`, or
`budget_exhausted`.
