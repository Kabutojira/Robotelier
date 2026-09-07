# Operations

Model production is opt-in and remains controlled by `publication.enabled` plus
`ROBOTELIER_PRODUCTION_ENABLED`. Pages and daily-report Telegram summaries have independent channel
flags and receipts, so publishing the metadata-only wiki does not imply that live model probes passed.

## Offline validation

```bash
uv sync --locked --all-groups
uv run robotelier config validate
uv run robotelier doctor --offline
uv run robotelier integrity check --strict
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -m "not live"
npm ci --prefix site --ignore-scripts
npm run check --prefix site
npm run build --prefix site
```

`daily prepare --dry-run` validates inputs and describes work without inference, network research,
rendering, commits, pushes, or delivery. Manual workflows accept an intended Europe/Rome slot and a
resume ID; they cannot bypass reservation, evidence, or daily-cap checks.

## Requests and queues

Create a JSON request under `data/operations/requests/`, validate it, then pass it to the relevant
CLI command. Do not edit canonical JSON records or queue state by hand.

```bash
uv run robotelier source register --request data/operations/requests/source.json
uv run robotelier subscription add --request data/operations/requests/subscription.json
uv run robotelier subscription validate
uv run robotelier discovery backfill --request data/operations/requests/backfill.json --dry-run
uv run robotelier queue enqueue --request data/operations/requests/research.json
uv run robotelier queue prepare --cycle-id 2026-09-06
uv run robotelier queue claim --run-id manual-20260906 --cycle-id 2026-09-06
uv run robotelier claim trace --claim-id <claim-id>
```

## Isolated Hermes profiles

Provision dedicated Robotelier homes; never point either variable at a personal or PaperTrader
home. Both profiles use capability-scoped `openai-codex` OAuth. The scheduled research workflow
reconfigures one home sequentially so two copies cannot race a rotating refresh token.

```bash
uv run robotelier agent configure --profile scout --hermes-home /safe/robotelier-openai
uv run robotelier agent configure --profile x --hermes-home /safe/robotelier-x
HERMES_HOME=/safe/robotelier-openai hermes skills opt-in --sync
HERMES_HOME=/safe/robotelier-x hermes skills opt-in --sync
HERMES_HOME=/safe/robotelier-openai hermes auth add openai-codex
uv run robotelier agent preflight --profile scout --hermes-home /safe/robotelier-openai --live
uv run robotelier agent preflight --profile x --hermes-home /safe/robotelier-x --live
uv run robotelier doctor --live
```

Run the `hermes auth add` command only in a dedicated home and verify it against the installed
pinned Hermes CLI before entering a code. Scheduled jobs never prompt. Do not configure
`XAI_API_KEY`; the controller allowlist excludes it if it exists in the host environment. After
login, run a bounded known-post and current-topic X operation. Authentication and successful Sol
inference alone do not pass the X evidence check.

Hermes stores all provider OAuth state in one `auth.json`. After the one-time login, keep that
plaintext outside the checkout (for example `/tmp/auth.json`) and encrypt it with the same
ciphertext-only age handoff used by the pinned PaperTrader baseline:

```bash
set -a
. ./.env
set +a
uv run robotelier credential bootstrap --auth-file /tmp/auth.json
uv run robotelier credential verify --auth-file /tmp/auth.json
git add .robotelier/credentials/oauth-auth.json.age
```

`.env` supplies `OPENAI_OAUTH_SECRET`, the private age identity also used by PaperTrader. The CLI
derives its public recipient with `age-keygen -y`; no separate recipient setting is accepted.
Only `.robotelier/credentials/oauth-auth.json.age` is allowlisted in the credentials directory.
Never add `/tmp/auth.json`, a decrypted copy, `.env`, the age identity, or a refresh snapshot.

Trusted jobs briefly decrypt the document, copy only `openai-codex` into the isolated home, and
delete the age identity before launching Hermes. After execution, the controller recreates the
identity, merges only that provider's refresh state, encrypts it, and decrypts the proposed
ciphertext for a byte-for-byte check before replacement. Unchanged auth does not rewrite the
ciphertext. Plaintext home auth and temporary identities are removed on every job exit. `X_API_KEY`
is ignored even if present locally; paid X API fallback remains forbidden.

Local Telegram commands use the existing `.env` names `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID`. `WIKI_PATH` may be supplied but must resolve to this checkout's `data/wiki`.

A daily summary is derived only from the report at an exact committed Git SHA. Preparing it writes
an idempotent public intent with a logical destination alias; the trusted workflow commits that
intent before it introduces Telegram secrets. An ambiguous response blocks a different workflow run
from resending until it is reconciled.

```bash
uv run robotelier report prepare-summary --local-date 2026-09-06 --source-commit <full-sha> \
  --report-url https://kabutojira.github.io/Robotelier/daily-reports/daily-report_20260906 \
  --delivery-run-id manual-20260906
uv run robotelier report deliver-summary --local-date 2026-09-06 --delivery-run-id manual-20260906
uv run robotelier report verify-summary --local-date 2026-09-06
```

## Local audited harness

```bash
uv run robotelier agent harness start --run-id <run> --operation-id <operation> --cycle-id <local-date>
# Read AGENTS.md and the returned role skill; use only returned paths/commands.
uv run robotelier agent harness finish --run-id <run> --operation-id <operation> --cycle-id <local-date>
```

## Publication and recovery

Use `publication reserve` before transcript commitment. A committed transcript permanently owns
its intended local-date slot. `delivery_unknown` and post-send receipt failures require explicit
`telegram reconcile`; never rerun `deliver-audio` blindly. Recovery resumes the same episode/stage.

```bash
uv run robotelier podcast prepare --local-date 2026-09-06
uv run robotelier publication prepare --local-date 2026-09-06
uv run robotelier publication deliver --local-date 2026-09-06
uv run robotelier recovery inspect --slot 2026-09-06
uv run robotelier telegram reconcile --request data/operations/requests/reconcile.json
uv run robotelier recovery resume --request data/operations/requests/resume.json
```

Historical factual corrections append source/claim revisions, rebuild the reverse impact index,
and add correction metadata to released episodes. Do not rewrite a released script.

`podcast prepare` freezes only a committed selected idea. Writing and deep review then execute as
different leased operations. `publication prepare` reserves the local date and commits the exact
transcript intent; the trusted workflow pushes that text before `publication deliver` renders and
sends. If the job is outside the 06:00–08:00 controlled window, recovery reports the missed slot
instead of sending blindly.

## Schedules and activation

Research, publication, and recovery target 03:17, 05:07, and 06:17 in `Europe/Rome`; the listener
release target is 06:00 and the controlled late window ends at 08:00. GitHub's timezone-aware
scheduler runs only from the default branch and may be delayed or skipped. Public-repository
scheduled workflows can be disabled after inactivity. Recovery is an in-repository status pass, not
an independent monitor.

Set `ROBOTELIER_PRODUCTION_ENABLED=true` only with a reviewed activation commit and configured
Actions secrets. `ROBOTELIER_PAGES_ENABLED=true` publishes the Quartz
wiki after successful research/publication workflows. Set `ROBOTELIER_SEND_TELEGRAM=true` only for
the identified destination. Manual research dispatch defaults to dry-run and exposes both channel
flags explicitly.
Unknown Telegram delivery must be reconciled with provider message IDs or an operator-verified
not-delivered result before the stage can resume.

GitHub Pages uses Actions as its build source and publishes the default branch at
`https://kabutojira.github.io/Robotelier/`. The Pages workflow can also be dispatched manually with
`publish_pages=true`; its artifact contains only generated Quartz HTML/static assets and is retained
for one day by the deployment service.

Create the immutable cadence anchor once, in the reviewed activation commit, immediately before
enabling production:

```bash
uv run robotelier cadence activate
git add data/history/activation.json
```

Read-only `cadence status` reports `activation_required` without creating state when this step has
not happened. A real non-dry daily cycle also initializes the anchor exactly once.

Weekly native wiki maintenance uses a dedicated queued `wiki_maintenance` operation, the pinned
native `llm-wiki`, and only file/terminal tools. Run its dry check with:

```bash
uv run robotelier wiki maintain --dry-run
uv run robotelier wiki validate
```
