# Robotelier

Robotelier is a public, Git-native robotics research and single-narrator podcast system. Its
permanent output is an evidence-backed English knowledge base; podcast transcripts are versioned
editorial projections of that knowledge. Robotics is covered broadly with special attention to
humanoid systems and their enabling technologies and value chains.

The controller owns identities, structured records, queue transitions, budgets, ranking,
publication slots, rendering, and delivery receipts. Bounded research agents run sequentially and
can submit only validated requests. Source and generated media bytes are never retained. Temporary
TTS audio exists outside the checkout only long enough to validate and deliver it through Telegram.

## Local setup

Python 3.12–3.14 and `uv` are required.

```bash
uv sync --locked --all-groups
uv run robotelier config validate
uv run robotelier doctor --offline
uv run pytest -m "not live"
npm ci --prefix site --ignore-scripts
npm run build --prefix site
```

Substantial mutations use request JSON files under `data/operations/requests/`:

```bash
uv run robotelier source register --request data/operations/requests/source.json
uv run robotelier queue enqueue --request data/operations/requests/research.json
uv run robotelier integrity check --strict
```

Run `uv run robotelier --help` for the implemented command tree. Live probes and delivery are
explicit; dry runs do not perform inference, research, rendering, commits, pushes, or sends.

The product contract is [AGENTS.md](AGENTS.md), the delivery plan is [PLAN.md](PLAN.md), and safe
operation is documented in [docs/OPERATIONS.md](docs/OPERATIONS.md).
External contracts and revalidation notes are in
[docs/EXTERNAL-CONTRACTS.md](docs/EXTERNAL-CONTRACTS.md).

## Current activation state

Production is disabled in `config.ini`. Offline implementation and tests do not imply that Grok
OAuth X evidence, OpenAI profiles, Edge TTS service access, Telegram delivery, or Pages deployment
have passed live checks. See [docs/IMPLEMENTATION.md](docs/IMPLEMENTATION.md) for executed evidence
and blockers.
