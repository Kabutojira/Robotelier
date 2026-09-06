# Configuration

`config.ini` is the checked-in baseline. Precedence is: built-in validation contract, repository
INI, then the established environment names `WIKI_PATH`, `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, and `OPENAI_OAUTH_SECRET` for local paths and secrets. Public records store only
the Telegram destination alias. Tokens and destination IDs remain environment or encrypted-controller
state. A repository-local `.env` is ignored and may be sourced for local commands; workflows map the
same names from GitHub secrets. `X_API_KEY` is deliberately unsupported.

The checked-in publication channel intent enables `publish_pages` and `send_telegram`, while the
separate `publication.enabled` and repository `ROBOTELIER_PRODUCTION_ENABLED` gates remain false
until live model acceptance. `ROBOTELIER_PAGES_ENABLED` controls deployment independently so the
metadata-only wiki can remain available even when model production is paused. Daily Telegram
summaries use only `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`; neither value is written to a report
or delivery receipt.

Numbers carry units in their key names. Cost accounting distinguishes known metered USD from
unknown subscription cost. Unknown does not mean free; operation, turn, time, and weighted limits
remain enforced.

`profile_x.model` intentionally starts as `UNCONFIGURED_PIN_REQUIRED`. Bootstrap must validate and
pin the model available through the user's Grok OAuth account. There is no `XAI_API_KEY` fallback.
Production stays disabled until explicit live probes pass.

The scheduled runtime image and native skill version are immutable values under `[hermes]`.
Repository workflows additionally pin all third-party actions by full commit. `profile_x.model`
must be replaced only after the live account reports and successfully exercises an exact model;
there is no automatic model or billing fallback.

The checked-in source registry is public and contains no auth state. Admissions go through
`robotelier subscription add`, which enforces the rolling seven-day limit; never hand-edit the
canonical registry during an autonomous run. Discovery cursors remain adapter-specific and describe
bounded/non-exhaustive coverage rather than complete timelines.
