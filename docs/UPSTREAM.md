# Upstream inventory

## PaperTrader baseline

- Repository: `Kabutojira/PaperTrader`
- Inspected commit: `99540f74e1712f500bae0da309772c36b5bb4454`
- Local object verified: 2026-09-06
- License: MIT; the upstream copyright notice is preserved in `LICENSE`.
- The local PaperTrader worktree was at `c77d2f961196342c76c7882f03546dad2f69ff90` during
  inspection. No code was taken from that moving revision.

## Adapted foundations

| Upstream path | Local path | Adaptation | Paired verification |
|---|---|---|---|
| `src/papertrader/atomic_io.py` | `src/robotelier/storage.py` | Safe path checks, fsync, atomic replacement; expanded with locks, journals and JSONL | `tests/unit/test_storage_audit.py` |
| `src/papertrader/repository_state.py` | `src/robotelier/audit.py` | Content-addressed snapshots and deltas | `tests/unit/test_storage_audit.py` |
| `src/papertrader/command_audit.py` | `src/robotelier/audit.py` | Operation-scoped CLI receipts with Robotelier paths | `tests/integration/test_agent_harness.py` |
| `src/papertrader/queue.py` | `src/robotelier/operations.py` | Reimplemented JSON-record queue, dependency graph, single lease, fencing, budgets | `tests/unit/test_operations.py` |
| `src/papertrader/agent_runner.py` | `src/robotelier/agent_runner.py` | Reimplemented isolated homes, provider routing, environment allowlist and bounded execution | `tests/integration/test_agent_harness.py` |
| `docs/OPERATIONS.md`, `.github/workflows/reusable-llm.yml`, `src/papertrader/oauth_credentials.py` | `src/robotelier/credentials.py`, `.github/workflows/{research,publish}.yml` | Same single-file age handoff at pinned commit: `OPENAI_OAUTH_SECRET`, derived recipient, ciphertext-only Git path, refresh change detection, decrypt-and-compare verification, and plaintext cleanup; extended with per-provider filtering/merge for combined OpenAI and Grok OAuth | `tests/integration/test_credentials.py` and workflow contract tests |
| `src/papertrader/result_validator.py` | `src/robotelier/result_validator.py` | Reimplemented scope/delta/receipt validation for robotics roles | `tests/integration/test_agent_harness.py` |
| `src/papertrader/podcast.py` | `src/robotelier/podcast.py` | Adapted temporary, script-bound Edge TTS flow; 600–1,200 second gate | `tests/integration/test_podcast_delivery.py` |
| `src/papertrader/telegram.py` | `src/robotelier/telegram.py` | Reimplemented split text/audio outbox and ambiguous delivery handling | `tests/integration/test_podcast_delivery.py` |
| `src/papertrader/publication.py` | `src/robotelier/publication.py` | Adapted exact-base allowlisted binary patch boundary | publication and workflow contract tests |
| `data/wiki/SCHEMA.md` | `data/wiki/SCHEMA.md` | Rewritten for evidence-backed robotics records and native LLMWiki | `tests/unit/test_provenance_integrity.py` |
| controller/research skills | `skills/robotelier-*/SKILL.md` | New robotics-specific, bounded skill contracts | skill quick-validation plus agent harness tests |
| `.github/workflows/reusable-llm.yml` and Pages workflow | `.github/workflows/` | Adapted immutable Hermes image/action pins, encrypted OAuth staging, serialized writers and trusted push boundary; all finance phases removed | `tests/integration/test_cli_daily_workflows.py` |
| `site/prepare-quartz.mjs`, `site/package.json` and Quartz configuration | `site/` | Adapted pinned Quartz materialization/build pattern; finance components and ECharts removed; RSS disabled | executed TypeScript/Prettier check and local Quartz build |

## Deliberately excluded

No securities universe, portfolio, valuation, ratings, order/fill logic, financial datasets,
YouTube media downloading, Seeking Alpha coupling, translations, multilingual scripts, credentials,
auth ciphertext, or historical research was copied. PaperTrader's 16–24 minute and 2,400-word
podcast constraints were not adopted. Robotelier has its own discovery design and retains media
metadata only. No PaperTrader credential value, identity, plaintext auth file, or ciphertext was
copied; only the inspected mechanism was adapted.

## Other pinned interfaces

- Hermes native `llm-wiki`: required version `2.1.0`; runtime presence must be probed.
- Edge TTS: Python dependency and expected executable version `7.2.8`.
- Hermes runtime container: release `0.18.2` / upstream image digest
  `sha256:9c841866021c54c4596849f6135717e8a4d52ba510b7f52c50aef1de1a283973`,
  inherited from the inspected PaperTrader baseline. A live bootstrap must still verify its reported
  version and native skill content.
- Quartz: `jackyzha0/quartz` commit `4923affa7722dfc751f1074348e6dad214fe0c08`,
  resolved by `site/package-lock.json`. The site exposes Markdown and metadata only and has no RSS.
