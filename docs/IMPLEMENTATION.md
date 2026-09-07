# Implementation evidence

This file records executed implementation evidence. A documented contract is not a passed test.

## Current run

- Workspace baseline: only `AGENTS.md` and `PLAN.md`; no prior code or credentials.
- PaperTrader object `99540f74e1712f500bae0da309772c36b5bb4454` was present and inspected.
- Hermes executable: not observed on the local `PATH`; the exact scheduled runtime image was
  live-probed on 2026-09-07 with `openai-codex` / `gpt-5.6-sol` and returned `OK`.
- Locked Python environment: `uv sync --locked --all-groups` passed with uv 0.12.2 and Python
  3.14.4.
- Python verification: Ruff passed; strict mypy passed for `src`; pytest passed all 80
  offline tests.
- Controller verification: all 18 JSON Schemas parsed; configuration, offline doctor, strict
  integrity, and mutation-free daily dry-run passed.
- Skill verification: the skill-creator quick validator passed all nine repository skills. It
  required the skill package version to be expressed under the supported `metadata` field.
- Site verification: the pinned Quartz TypeScript/Prettier check and local build passed, producing
  16 disposable files from four Markdown inputs. The untracked-date warnings are expected because
  this newly initialized workspace has no Git commit.
- Media audit: no retained source/generated media exists outside ignored disposable dependency and
  build trees.
- OAuth artifact verification: system age 1.2.1 encrypted the external `/tmp/auth.json`; immediate
  decryption matched byte-for-byte. Real decrypts exposed only `openai-codex` to isolated homes with
  mode 0600; unchanged reseals preserved the exact ciphertext. Scheduled jobs install
  checksum-pinned age 1.3.1, matching PaperTrader's baseline.
- Activation update (2026-09-07): the user replaced the blocked Grok route with the validated
  `openai-codex` / `gpt-5.6-sol` profile and explicitly authorized provisioning the age identity and
  Telegram values as GitHub Actions secrets. GitHub confirmed all three secret names without
  exposing their values.

The implementation and its encrypted OAuth artifact are prepared for the initial reviewed commit.
The source plaintext and age identity remain outside Git; the repository credentials directory
allowlists only the verified age ciphertext.

## Implemented offline milestones

- M0–M2: package/configuration, attributable upstream inventory, schemas, atomic storage,
  deterministic queue/budgets/fencing, isolated Hermes homes, encrypted credential envelopes,
  audited harness, and scoped skills.
- M3: normalized OpenAI-backed X evidence/degradation contract and adversarial fixtures. The model
  inference probe passed; inspected originating-post evidence remains a separate live check.
- M4–M6: bounded source adapters/cursors, immediate metadata-only media registration, source
  registry, native-compatible wiki projections, editorial review/ranking, and Europe/Rome cadence.
- M7–M9: committed frozen bundles, separate writer/reviewer operations, segment provenance,
  temporary measured TTS, independent Telegram channel state, exact-hash publication slots,
  Quartz, IANA-aware serialized workflows, and recovery diagnostics.
- M10: deterministic offline unit, integration, semantic-contract, and workflow tests. Provider,
  delivery, and deployment acceptance remains live-blocked as listed below.

## Live blockers

The earlier Grok OAuth route was superseded by the user's 2026-09-07 provider decision after xAI
returned `personal-team-blocked:spending-limit`. No paid fallback was enabled. The replacement
`openai-codex` / `gpt-5.6-sol` inference probe passed in the exact pinned container. Inspected X
originating-post evidence, native LLMWiki invocation, Edge TTS service rendering, controlled
Telegram delivery, and GitHub Pages deployment still require their explicit live receipts.
Production is enabled for the requested controlled workflow run; failures remain typed and visible.

See `docs/ACCEPTANCE.md` for the offline acceptance coverage and deliberately open live cases.
