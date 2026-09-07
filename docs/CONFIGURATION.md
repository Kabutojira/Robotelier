# Configuration

`config.ini` is the checked-in baseline. Precedence is: built-in validation contract, repository
INI, then the established environment names `WIKI_PATH`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, and `OPENAI_OAUTH_SECRET` for local paths and secrets. Public records store only
the Telegram destination alias. Tokens and destination IDs remain environment or encrypted-controller
state. A repository-local `.env` is ignored and may be sourced for local commands; workflows map the
same names from GitHub secrets. `X_API_KEY` is deliberately unsupported.

The checked-in publication channel intent enables `publication.enabled`, `publish_pages`, and
`send_telegram` following the user's 2026-09-07 activation decision. The repository
`ROBOTELIER_PRODUCTION_ENABLED` variable remains the independent operational gate.
`ROBOTELIER_PAGES_ENABLED` controls deployment independently. Daily Telegram summaries use only
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`; neither value is written to a report or delivery
receipt.

Numbers carry units in their key names. Cost accounting distinguishes known metered USD from
unknown subscription cost. Unknown does not mean free; operation, turn, time, and weighted limits
remain enforced.

`profile_x` is pinned to `openai-codex` / `gpt-5.6-sol`, with the X-specific 32-turn, 600-second,
eight-query, and sixteen-tool-call bounds and cost weight 5. A bounded inference probe passed in the
exact pinned Hermes container on 2026-09-07. There is no `XAI_API_KEY`, xAI OAuth, or paid X API
fallback.

The scheduled runtime image and native skill version are immutable values under `[hermes]`.
Repository workflows additionally pin all third-party actions by full commit. Model changes require
another explicit decision and live probe; there is no automatic model or billing fallback.

The checked-in source registry is public and contains no auth state. Admissions go through
`robotelier subscription add`, which enforces the rolling seven-day limit; never hand-edit the
canonical registry during an autonomous run. Discovery cursors remain adapter-specific and describe
bounded/non-exhaustive coverage rather than complete timelines.
