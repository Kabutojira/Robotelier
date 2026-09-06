# Implementation evidence

This file records executed implementation evidence. A documented contract is not a passed test.

## Current run

- Workspace baseline: only `AGENTS.md` and `PLAN.md`; no prior code or credentials.
- PaperTrader object `99540f74e1712f500bae0da309772c36b5bb4454` was present and inspected.
- Hermes executable: not observed on the local `PATH`; the scheduled runtime is pinned by image
  digest but has not been live-probed.
- Locked Python environment: `uv sync --locked --all-groups` passed with uv 0.12.2 and Python
  3.14.4.
- Python verification: Ruff passed; strict mypy passed for `src`; pytest passed all 76
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
  decryption matched byte-for-byte. Separate real decrypts exposed only `openai-codex` to the scout
  home and only `xai-oauth` to the X home, both mode 0600; unchanged reseals preserved the exact
  ciphertext. Scheduled jobs install checksum-pinned age 1.3.1, matching PaperTrader's baseline.

The implementation and its encrypted OAuth artifact are prepared for the initial reviewed commit.
The source plaintext and age identity remain outside Git; the repository credentials directory
allowlists only the verified age ciphertext.

## Implemented offline milestones

- M0–M2: package/configuration, attributable upstream inventory, schemas, atomic storage,
  deterministic queue/budgets/fencing, isolated Hermes homes, encrypted credential envelopes,
  audited harness, and scoped skills.
- M3: normalized OAuth-only X evidence/degradation contract and adversarial fixtures. The required
  live evidence probe remains blocked.
- M4–M6: bounded source adapters/cursors, immediate metadata-only media registration, source
  registry, native-compatible wiki projections, editorial review/ranking, and Europe/Rome cadence.
- M7–M9: committed frozen bundles, separate writer/reviewer operations, segment provenance,
  temporary measured TTS, independent Telegram channel state, exact-hash publication slots,
  Quartz, IANA-aware serialized workflows, and recovery diagnostics.
- M10: deterministic offline unit, integration, semantic-contract, and workflow tests. Provider,
  delivery, and deployment acceptance remains live-blocked as listed below.

## Live blockers

The live Grok OAuth evidence probe, actual OpenAI model profiles, native LLMWiki invocation, Edge
TTS service rendering, controlled Telegram delivery, and GitHub Pages deployment require the
initial public commit and configured external credentials/services. `profile_x.model` deliberately
remains `UNCONFIGURED_PIN_REQUIRED`; production flags remain false. The encrypted OAuth envelope is
present, but authentication and evidence behavior are not accepted until their explicit live
commands succeed.

See `docs/ACCEPTANCE.md` for the offline acceptance coverage and deliberately open live cases.
