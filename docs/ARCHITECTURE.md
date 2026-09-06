# Architecture

Robotelier treats canonical JSON revisions under `data/records/` as authoritative structured state
and Markdown under `data/wiki/` as the human-readable knowledge projection. Replaceable indexes and
site output live under `data/published/`. There is no second authoritative database.

The trusted controller validates request files, performs atomic transactions, leases one operation
at a time, accounts for a single publication-cycle budget, ranks reviewed ideas, freezes episode
evidence, renders reviewed scripts in a temporary directory, and records publication/delivery
receipts. Untrusted bounded agents receive only a role-specific provider profile and submit changes
through the CLI. Git, Telegram, deployment, envelope-decryption, and unrelated host credentials are
not passed to them.

Traceability is bidirectional: source identity → observation → evidence locator → claim revision →
wiki section → idea revision → frozen bundle → script segment → render timing. Corrections append
new revisions and impact links; released text is never silently replaced.

Every external channel is independent. Research, transcript, Telegram text, Telegram audio, and
Pages states can succeed or fail separately. An ambiguous Telegram side effect is reconciled by an
operator and is never blindly repeated.

