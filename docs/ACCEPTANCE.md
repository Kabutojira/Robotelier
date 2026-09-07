# Acceptance evidence

This is the offline acceptance ledger for the 2026-09-06 implementation. A passing fixture proves
the controller state transition or validation contract; it does not claim that a model, provider,
Telegram, or GitHub accepted a live operation.

## Executed offline coverage

| Acceptance cases | Evidence |
|---|---|
| A01–A08, A11–A16, A20–A28 | Synthetic multilingual announcement, syndicated-origin, old-repost, independent-test, unsafe-URL, signed-media, source-hash, discovery failure/cursor, X citation, and metadata fixtures in `test_research_fixtures.py`, `test_sources_media_x.py`, and `test_provenance_integrity.py`. |
| A09–A10, A12, A14, A41–A43, A47 | Explicit semantic rejection fixtures plus frozen-claim/segment gates and correction impact tests. Final natural-language quality still requires the independent live reviewer. |
| A17–A18, A29–A33, A60–A61 | Environment allowlisting, OAuth-only response checks, private encrypted envelope tests, sequential lease/fencing, audited result rollback, scope controls, and workflow secret isolation. |
| A34–A40 | Deterministic score bounds, readiness-first selection, one-date ownership, immutable activation anchor, and injected local-calendar cadence phases. |
| A44–A53, A55 | Exact transcript/render binding, duration rejection, new render attempts, independent channel state, definitive/ambiguous Telegram outcomes, reconciliation, receipt failure, and observed temporary cleanup. |
| A54, A56–A57 | Europe/Rome spring/fall UTC conversion, intended-date manifests, phase receipts, and the controlled 06:00–08:00 workflow window. |
| A58–A59, A62 | Exact-base allowlisted Git bundle code, post-rebase integrity gates, deterministic wiki indexes, and an executed clean-input Quartz build. A remote concurrent-push rehearsal remains part of controlled activation. |

The suite passed 80 tests. Tests use no provider credentials, source media, generated audio archive,
paid API, or uncontrolled web call.

## Open controlled checks

- A19 is open: the exact pinned container successfully exercised `openai-codex` /
  `gpt-5.6-sol`, but no live operation has yet demonstrated inspected, resolvable originating-post
  evidence from X.
- The semantic reviewer has not run with the live deep profile; fixture expectations are not a
  substitute for model evaluation.
- Edge TTS is installed locally, but a controlled full-duration live render and Telegram delivery
  have not been performed against the intended destination.
- The local Quartz build passed; GitHub Pages has not been deployed from a public committed
  repository.
- A remote safe/unsafe concurrent rebase rehearsal and the fourteen-day composite rehearsal must
  be recorded at an identified commit before activation. Their individual deterministic state
  transitions are covered offline.

None of these open cases is silently converted to success. They keep the final activation checkbox
in `PLAN.md` incomplete while the user-authorized production run records real typed outcomes.
