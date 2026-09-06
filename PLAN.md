# PLAN.md — Robotelier implementation plan

Specification date: 2026-09-06.  
Status: requirements finalized; implementation milestones are not yet completed.  
Authority: [AGENTS.md](AGENTS.md). Read it in full before executing this plan.

## 1. Outcome and fixed requirements

Build a public, autonomous robotics research system with a humanoid focus. Reuse PaperTrader's native Hermes LLMWiki, bounded ephemeral agents, Git-native state, provider profiles, script/TTS validation, and Telegram delivery pattern. Research daily from X through Grok OAuth and from other primary and credible sources. Register sources and media metadata, maintain durable knowledge, generate and rank podcast ideas, independently review priorities, select the highest-ranked eligible idea, and produce a source-traceable English episode.

The show has one narrator and a measured duration of ten to twenty minutes. Publish at most one new episode per Europe/Rome date and work proactively toward at least one per rolling seven-local-day interval. There must be enough evidence-backed content; do not pad, fabricate, or recycle narration to satisfy cadence. Aim for 06:00 Europe/Rome listener release. Save transcripts, show notes, evidence, and metadata; send temporary audio through Telegram and delete it. Do not retain any source image/video/audio, generated audio, or derived media frames, and do not build an audio archive, RSS feed, or video renderer.

All authored project and publication content is English. Discovery may be multilingual; exact source identifiers/titles/names retain original fidelity. The repository and Quartz wiki are public. No investment system or multilingual podcast path is required.

### Initial project state

- [x] User product decisions are recorded in `AGENTS.md`.
- [x] The implementation approach and acceptance criteria are specified in this plan.
- [ ] Runtime source code, schemas, skills, tests, workflows, credentials, source subscriptions, and live deployment are implemented and verified.

These first two completed items mean that the documents exist, not that Robotelier is running. Do not alter the final checkbox or individual milestone status without evidence.

## 2. Execution rules

Implement milestones in dependency order. Each milestone ends with code, relevant tests, updated operator documentation, and an evidence note in this file or a linked implementation log. A milestone is complete only when its tests actually ran and passed. Distinguish offline tests, live provider probes, delivery tests, and reasoning-based review.

Do not ask again about language, scope, format, storage, publication channel, public visibility, provider approach, or target time. Keep new engineering details configurable and choose conservative defaults consistent with `AGENTS.md`. Record decisions with rationale. Missing secrets or account setup are external blockers with actionable instructions, not permission to fake integration or switch providers.

Inspect the workspace before modifying it. Do not overwrite a pre-existing project, upstream instructions, user files, or credentials. Selectively adapt licensed PaperTrader components; do not clone its investment data or auth state into the new public repository. Never use a moving upstream dependency at runtime.

Runtime operations remain sequential and audited. Implement local fixture-based development first, then live smoke checks, then end-to-end tests. Scheduled production requires completed bootstrap, configured destinations, live integration checks, and explicitly enabled workflows. Once enabled, ordinary research, editorial decisions, and publication are autonomous and require no per-episode approval.

All CLI examples below are planned interfaces until implemented. Do not report an example command as successfully executed merely because it appears here.

## 3. Milestone map and dependencies

| Milestone | Deliverable | Depends on |
|---|---|---|
| M0 | Minimal repository, pinned upstream inventory, configuration | None |
| M1 | Provenance-first schemas, identities, transactions, validation | M0 |
| M2 | Sequential queue, ephemeral Hermes, scoped auth and audited harness | M0–M1 |
| M3 | Working Grok OAuth X adapter with explicit evidence/degradation behavior | M1–M2 |
| M4 | Multi-source discovery, media metadata registry, triage | M1–M3 |
| M5 | Robotics LLMWiki and evidence-backed knowledge maintenance | M1–M4 |
| M6 | Editorial queue, independent ranking review, cadence controller | M1–M2, M5 |
| M7 | Frozen evidence, segment-linked writing and independent fact-checking | M5–M6 |
| M8 | Temporary TTS, script-bound rendering, Telegram outbox and cleanup | M2, M7 |
| M9 | 06:00 workflows, public wiki, safe Git boundaries, recovery | M4–M8 |
| M10 | Adversarial/end-to-end acceptance, controlled activation | M0–M9 |

M3 is an early risk-reduction milestone. Failure to obtain evidence-bearing X responses must not be hidden behind a complete UI or a plausible podcast. Other implementation can continue using offline fixtures and non-X adapters, but live X acceptance stays blocked until the intended integration is demonstrated.

## 4. M0 — Bootstrap a minimal, attributable project

- [ ] Inspect the working tree and initialize the layout in `AGENTS.md` without importing domain data.
- [ ] Create `README.md`, `pyproject.toml`, `uv.lock`, the `robotelier` package/CLI entry point, test directories, configuration documentation, and ignored temporary paths.
- [ ] Read PaperTrader in /home/tux/personalbuild/PaperTrader.
- [ ] Create `docs/UPSTREAM.md` with the exact adopted paths, commits, licensing, adaptation notes, and paired tests. Preserve license notices for copied code.
- [ ] Inspect native Hermes `llm-wiki` availability and the isolated runtime/container configuration. Pin immutable versions/digests; do not install latest in production.
- [ ] Extract generic queue, atomic I/O, audit, wiki, podcast, Telegram, and workflow patterns. Remove investment-specific validators, state, terminology, symbols, and all credential payloads.
- [ ] Define configuration schemas with units, defaults, override precedence, and unknown-cost behavior. Implement `config validate` before live operations.
- [ ] Pin the upstream reasoning profiles and Edge TTS voice/dependency as starting values; verify provider/model availability later rather than claiming it here.
- [ ] Record engineering choices: JSON canonical records; Markdown knowledge; no database service; two logical queues; media metadata only; repository-local issues; source/model/delivery trust boundaries.

Configuration must cover providers/profiles, budget accounting, source limits, overlap/backfill, page/quotation limits, lease/retry policy, ranking policy, weekly preparation, ten-to-twenty-minute audio limits, local scheduling slots, late window, Telegram aliases, and publication features. Inherit the PaperTrader USD 5 known-metered ceiling, weighted budget 100, total twenty-operation ceiling, and five substantive research investigations per cycle without allocating them twice across workflows.

Do not automatically import newly added PaperTrader translation support. Do not copy its sixteen-to-twenty-four-minute validation constants or its two-thousand-four-hundred-word minimum. Robotelier's measured-duration requirement is authoritative.

**Exit evidence:** a clean checkout installs from the lockfile, imports the CLI, runs a minimal offline test, validates configuration, and contains no portfolio, source media, or credentials. `docs/UPSTREAM.md` names what was reused and what was intentionally excluded.

## 5. M1 — Implement identity, provenance, and atomic storage first

### Canonical contracts

- [ ] Create versioned JSON Schemas for entities, relationships, source identities/revisions, evidence items, atomic claims/revisions, developments, media metadata, operations/results, editorial ideas/reviews/scores, episode bundles/segments/renders, publication intents/receipts, and run summaries.
- [ ] Implement stable identity allocation, immutable revisions, alias redirects, canonical URL handling, origin groups, and explicit date precision/access status.
- [ ] Implement transaction staging, file locks, atomic replacement, recovery journaling, append-only history, and compare-and-swap revision checks.
- [ ] Implement CLI request validation and deterministic write receipts. Agents must not write structured files directly.
- [ ] Build forward and reverse reference indexes, including source-to-episode impact traversal. Generated indexes must rebuild from canonical records.
- [ ] Add source-level quotation accounting and public-data/media exclusion checks. Retain permitted short textual evidence, never entire articles/captions in debug traces.
- [ ] Add record-level migrations with schema-version tests; do not add a PaperTrader data migration project.

### Evidence semantics

Represent source identity separately from access observations and content revisions. Record fetched-content hashes only when the bytes were actually retrieved, with hash scope. Preserve event date, post/article publication date, modification date, and retrieval date separately. Preserve unsupported or inaccessible primary-source references without labeling them inspected.

An evidence item must locate its support precisely. A claim must name the evidence that supports each material clause and distinguish announcement, observed fact, maker assertion, inference, forecast, and dispute. Contradictions append evidence and revision relationships rather than destructively rewriting the prior assertion. Definitions/background are also cited where factual; nonfactual narrative is explicitly typed.

Create synthetic, clearly labeled fixtures for two robot versions, a maker announcement, a repost, secondary reporting, an independent test, a later correction, a deleted source, an expiring media URL, and a short source-video time locator. No persistent binary fixture is necessary; generate any TTS-test bytes in temporary test directories and delete them.

**Exit evidence:** tests prove stable IDs across renamed handles/robots, correct origin grouping, unit/date validation, no false body hashes, atomic multi-file recovery, invalid-reference rejection, and a source → claim → wiki → segment trace in both directions. A reachable URL with unrelated text must fail semantic-support review in the later evaluation fixture, not be counted as a successful provenance fact-check.

## 6. M2 — Adapt the deterministic controller and ephemeral Hermes harness

- [ ] Implement operation enqueue/dedupe, dependency validation, leased claims, fencing tokens, heartbeats, priorities, deadlines, retries, blocked reasons, cancellation, and immutable attempt history.
- [ ] Enforce a single live agent lease and a shared cycle budget across scheduled research, editorial, publication, and local runs.
- [ ] Build isolated OpenAI and Grok Hermes homes with the pinned native `llm-wiki` skill and repository `skills.external_dirs`.
- [ ] Configure the pinned `hermes chat --quiet --yolo` invocation with narrowly allowed toolsets. Disable delegation, memory, messaging, hooks, self-modification, worktrees, automatic skill installation, unneeded MCP, and media generation.
- [ ] Add controller and per-operation skill contracts, allowed commands, allowed paths, frozen input manifests, and operation-specific model routing.
- [ ] Adapt the before/after content-addressed baseline and audited CLI receipt system. Accept or roll back each complete operation from observed effects, not model claims.
- [ ] Implement local `agent harness start|finish` so Codex can execute the same skills without bypassing state controls.
- [ ] Add provider-auth provisioning documentation, isolated encrypted envelopes, refresh persistence, ciphertext-only recovery, and cross-repository refresh-token safety.
- [ ] Implement offline preflight, explicit live provider checks, typed failures, bounded retries, and sanitized logs.

Auth setup reuses the PaperTrader account/provider approach, not its secret bytes or unreviewed refresh-token file. Grok OAuth exists according to the user; bootstrap must attach usable auth state to the isolated profile. Never ask for plaintext tokens in source files or conversational output. If a one-time login is required on the operator machine, give exact verified commands in `docs/OPERATIONS.md`; scheduled runs cannot complete interactive device-code approval.

Treat model OAuth as the narrowly necessary agent capability; it is not accurate to say agents receive no credentials at all. GitHub write, Telegram, decryption keys, and deployment credentials stay in trusted stages. Validate this isolation with a canary test that tries to read unrelated environment variables, host paths, and retained auth values through source instructions.

**Exit evidence:** a synthetic operation succeeds once; duplicate enqueue does not duplicate work; an expired agent is fenced; a forbidden file edit is rejected; model-declared fake receipts are ignored/rejected; a failed research attempt can still preserve a legitimately rotated encrypted token without accepting research mutations. Two concurrent invocations never launch two agents.

## 7. M3 — Prove Grok OAuth X research works with evidence

- [ ] Read the pinned Hermes native X-search code and current official provider contract; do not rely solely on prose documentation where it conflicts.
- [ ] Configure the Grok X-research profile with `xai-oauth`, a tested pinned inference model, and a tested X-search model/tool configuration.
- [ ] Explicitly exclude `XAI_API_KEY` from this profile, including inherited host environment. A key must not silently override OAuth.
- [ ] Implement a normalized X response contract with citations, inline citations, stable post IDs, account identity, publication dates where verified, query/filter metadata, credential source, access level, degradation reason, and safely obtainable media metadata.
- [ ] Independently classify an uncited answer as an unsourced lead even if the provider reports success or omits its degraded flag.
- [ ] Validate canonical post URLs and original-source relationships; do not accept a profile URL as proof of an asserted post.
- [ ] Add tests for unknown media URLs and non-exhaustive search windows. Search output is not an exhaustive account timeline.
- [ ] Run an explicitly bounded live probe with the configured account, checking at least a known publicly inspectable post and a current topic query. Verify evidence against the referenced post/primary page where accessible.
- [ ] Record sanitized capability results and the exact Hermes/provider/model versions. No source media, raw auth, or full provider conversation may be committed.

The live probe must separate login success, model inference, search-tool availability, actual post citations, useful metadata, and successful token refresh. A positive result in one does not imply all others. Current official Hermes material documents both OAuth support and possible uncited X-search degradation; Robotelier must handle the actual account/version result.

When live X evidence is unavailable, record `x_search_unsourced`, `x_search_unavailable`, or an equivalent typed failure, continue supported non-X research, and keep M3 incomplete. Do not invent results, install a scraper that bypasses access restrictions, or enable a paid API as an unapproved workaround. Other milestones can use clearly labeled recorded/synthetic fixtures without pretending the live test passed.

**Exit evidence:** an actual OAuth-routed query produces resolvable post evidence or M3 remains visibly blocked. Failure-mode fixtures for empty citations, invalid dates/handles, expired auth, 403, throttling, signed media URLs, and unknown fields pass. There are no X write capabilities.

## 8. M4 — Add multi-source discovery and metadata capture

- [ ] Build adapter interfaces for official RSS/Atom and website announcements, general web discovery, research metadata, relevant repositories/releases, event sources, and video-platform metadata/captions where permitted.
- [ ] Start with a compact, verified source set across humanoid and non-humanoid robotics. Verify each official identity rather than seeding guessed handles.
- [ ] Research in relevant source languages while authoring all synthesis in English.
- [ ] Implement per-adapter cursors, attempted/successful windows, bounded pagination, overlap, retries, error isolation, and explicit backfill.
- [ ] Register source and media metadata before triage. Add zero-byte-download policy enforcement and unknown-metadata reasons.
- [ ] Add cheap ingest/defer/ignore classification with deterministic admission and auditable reasons.
- [ ] Deduplicate platform identities; separately cluster repeated reporting into developments with source-origin groups.
- [ ] Queue bounded evidence research and identity-resolution work. Preserve deferred candidates when the daily budget is exhausted.
- [ ] Track coverage by category, source type, and geography/language; allow bounded registry expansion and periodic revalidation.

Use the initial 48-hour overlap, seven-day bootstrap, 100-candidate daily bound, and twenty-new-subscription weekly bound from `AGENTS.md`. Implement provider-specific narrower bounds where necessary, record them, and do not imply complete coverage. Advance a successful cursor only after durable registration/classification, not after a search request starts.

For YouTube or similar video sources, retrieve only permitted text/metadata. No audio/video download or ASR dependency that silently downloads media. A caption contains speaker claims, not automatic independent verification. Media links must include original page/post and IDs, known creators/rights, dimensions/duration when supplied, claim/entity relationships, availability, and metadata verification times. No thumbnail file fetching, content-addressed binary cache, preview-generation job, or object store.

**Exit evidence:** duplicate feeds and reposts produce one development with multiple sources; a crash before cursor commit does not lose candidates; provider failure does not erase a successful sibling adapter; old footage reposted today retains its old event date; every discovered relevant media item is registered without retained media bytes. A malicious URL redirect to an internal endpoint is blocked.

## 9. M5 — Build the robotics LLMWiki and research loop

- [ ] Define native-compatible `data/wiki/SCHEMA.md`, frontmatter, tags, page templates, catalogs, daily reports, and logs.
- [ ] Create company, robot family/version, technology, relationship, event, news, research, comparison, source, media-metadata, idea, and episode page types.
- [ ] Implement evidence-backed research operations with source registration, prior-knowledge review, changed/unchanged conclusions, conflict handling, explicit unknowns, and refresh dates.
- [ ] Add the robotics evaluation checklist: autonomy, teleoperation, human interventions, test conditions, repetitions, failure evidence, configuration, pilot/deployment status, production versus shipments, and economics claims.
- [ ] Make factual wiki sections bind to claim revisions and render readable external citations. Generate reverse links automatically.
- [ ] Support qualified secondary reporting when the primary work is unavailable. Do not block accurate reporting of an announcement merely because its performance claim lacks independent testing.
- [ ] Preserve asserted versus independently observed capability and all meaningful contradictions through immutable history and a current view.
- [ ] Implement weekly native `llm-wiki` maintenance without a redundant custom maintenance skill. Limit writes to wiki organization/links, use no web tools, and protect production capacity.
- [ ] Add strict validation for broken/ambiguous links, orphan maintained pages, unsupported factual sections, source/claim staleness, and oversized pages/log rotation.

Research work completes within a bounded operation. It may enqueue concrete follow-ups but cannot recursively expand an unlimited industry map. A refresh reads prior evidence and stores a change record; “no material change” is valid research but must not become a new podcast story automatically.

The public wiki must be useful independently of the show: entity history, product versions, technology explanations, deployments, comparative research, evidence and media catalogs, and dated uncertainty are navigable. Unknown or disputed claims remain visible rather than converted into empty confident summaries.

**Exit evidence:** the synthetic robotics dataset creates a fully connected wiki with distinct robot versions, properly attributed demonstrations, corrected claims, and intact historical citations. Source-media pages contain external links and metadata only. A native maintenance run cannot edit claims, episode history, schemas, or structured queue state.

## 10. M6 — Implement editorial ideas, ranking review, and weekly readiness

- [ ] Create the separate editorial idea state machine and revision history.
- [ ] Generate ideas from new research, older uncovered findings, relevant background, and the coverage ledger; update or merge existing ideas before creating duplicates.
- [ ] Implement versioned component scoring and deterministic priority arithmetic exactly as defined in `AGENTS.md`.
- [ ] Require a separate fresh review operation over the entire active queue using bounded pagination. Validate that pagination covered the intended snapshot.
- [ ] Record score changes, merges, rejected ideas, readiness failures, source gaps, and expiry decisions with reasons.
- [ ] Implement atomic highest-priority eligible selection, deterministic tie-breaks, one episode reservation, and targeted research when a higher-ranked idea is blocked.
- [ ] Track coverage per development, claim revision, and editorial angle, not only the last episode's date.
- [ ] Implement daily release caps, seven-local-day deadlines, day-four/week-candidate preparation, day-five research priority, day-six outline readiness, and day-seven target.
- [ ] Add the independent outline gates: density, novelty, evidence readiness, standalone value, and a credible ten-to-twenty-minute plan.
- [ ] Add explicit `no_episode_insufficient_material` and `cadence_breach` outcomes, with distinct routine status and operator alert behavior.

Do not make source-count or headline-count thresholds the primary quality gate. A single well-evidenced story may suffice. A collection of shallow repetitions may not. A weekly candidate can connect several accumulated developments or answer a researched evergreen question; it cannot relabel old evidence as new or replay previous narration.

Prevent priority inflation and starvation with bounded modifiers, origin/coverage dedupe, expired-news handling, and typed revalidation dates. Humanoid focus influences relevance; it must not suppress significant broader robotics developments forever. Ages and weekly pressure affect ordering only after evidence and density pass.

**Exit evidence:** a lower-ranked ready idea proceeds when the top idea is blocked; a reviewer can lower inflated scores but cannot change the scoring formula; semantically duplicate proposals merge; unreported older findings remain eligible; day-four-to-day-seven simulations prepare and release a dense weekly story without daily filler. Lack of qualifying evidence causes an explicit breach, never a fabricated episode.

## 11. M7 — Freeze evidence and produce traceable scripts

- [ ] Implement a content-addressed episode package from the selected idea, source/claim/wiki revisions, editorial review, research cutoff, and coverage history.
- [ ] Verify every referenced file/hash/path and record the exact source commit. Store no unrestricted source bodies or media.
- [ ] Create stable script segments with semantic role, spoken text, factual claim references, media candidates, and revisions.
- [ ] Generate the human-readable Markdown transcript and show notes from the canonical segment data; validate synchronization.
- [ ] Add a writing skill using only frozen evidence. It cannot browse, change accepted research, or choose a different idea.
- [ ] Add a separate fact-checking/editorial review skill with clause-level support checks, robotics caveats, English listening quality, novelty, and density.
- [ ] Implement at most two bounded revision rounds and targeted evidence-gap feedback.
- [ ] Implement final semantic and deterministic preflight, including a check for material corrections/retractions accepted after the freeze.
- [ ] Create direct original-source show-note citations, segment-level evidence maps, reverse source-to-episode indexes, and future media-selection metadata.

Treat 1,400–2,800 words as an initial planning range only. Calibrate using the actual selected voice; the hard output limit is measured audio duration of 600–1,200 seconds. Do not lower uncertainty, remove important attribution, or lengthen the script with generic introductions just to reach a word target.

The final transcript must work for a listener unfamiliar with the wiki and past episodes. It explains the interesting robotics question, supporting evidence, what cannot yet be concluded, and why the result matters. No machine IDs, raw URLs, tables, or operational workflow narration in spoken prose. Notes/citations remain visible outside narration. Proper names and foreign source titles are preserved where necessary but explanations remain English.

**Exit evidence:** a valid script has complete segment → claim → evidence → source links, readable show notes, explicit nonfactual segment types, no unsupported factual clause, and no repeated story presented as new. A later source correction finds affected segments without silently changing released text. The writer cannot add a new fact simply because it sounds plausible.

## 12. M8 — Render temporary audio and deliver safely

- [ ] Adapt the deterministic PaperTrader renderer and pin its backend, chunk policy, voice, and inspection tools.
- [ ] Render only after editorial/evidence preflight, using a controller-selected temporary directory outside the repository.
- [ ] Implement one renderer invocation per render-attempt ID, bounded internal retries, and at most three render attempts per episode across safe recoveries.
- [ ] Measure actual duration, byte size, type, and audio hash. Reject outputs outside ten to twenty minutes; fix/review the script rather than inserting silence or unnatural speed.
- [ ] Bind the audio to the exact committed transcript and settings. Record render-specific timing metadata from observed boundaries; label approximations.
- [ ] Implement durable, separately tracked Telegram text/audio outbox intents and acknowledgments, with logical destination aliases and no private configuration in public state.
- [ ] Validate current Telegram message/audio limits; do not reuse a rich-text limit intended for a different API method without checking it.
- [ ] Add `delivery_unknown` for ambiguous timeout/crash cases, safe retry classification, and explicit reconciliation commands.
- [ ] Keep the untrusted agent, trusted Git write, and trusted Telegram stages capability-separated while rendering and sending on the same temporary runner.
- [ ] Delete temporary audio, chunks, subtitle intermediates, and transient manifests after every outcome. Retain metadata, not media or Telegram audio file references.

A successful upload may be followed by a failed receipt commit. This is ambiguous, not an excuse to resend automatically. Commit the outbox intent before sending, retain the provider acknowledgment when available, and block blind retries after uncertainty. The system cannot promise exactly-once delivery to an external API without a suitable provider primitive.

A definitive delivery failure may leave a valid public transcript. Keep that success and the delivery error separately. A later safe recovery may synthesize the same script again in a new render attempt because the old audio was intentionally deleted. It is the same episode, not new content, and it does not produce a second editorial reservation. If audio timing changes, save a distinct timing-map revision.

**Exit evidence:** a controlled Telegram test delivers the exact validated script/audio, records metadata, and leaves no local or workflow-artifact media. Simulated TTS failure, out-of-range duration, upload rejection, upload timeout, post-send crash, script hash mismatch, cancellation, and receipt-write failure follow their specified state transitions without duplicate automatic sends.

## 13. M9 — Schedule, publish the wiki, and recover independently

- [ ] Create manually dispatchable research, publication, recovery/status, Pages, and offline CI workflows.
- [ ] Add IANA-aware schedules: research at 03:17, publication at 05:07, recovery/status at 06:17, all Europe/Rome. Protect the 06:00 listener-release target.
- [ ] Enforce the 04:45 discretionary-research soft cutoff and reserve shared cycle budget for editorial/release work.
- [ ] Serialize agents and Git writers across workflows; recover from delayed triggers using intended slot identity and phase receipts.
- [ ] Keep temporary rendering and Telegram delivery in the same publication job/runner, with no media transfer artifacts.
- [ ] Implement a clean allowlisted Git boundary: exact-base patch, validation, controlled rebase, renewed validation, and push after untrusted agents terminate.
- [ ] Build Quartz from an exact committed revision; generate public catalogs, source/media metadata pages, transcript pages, show notes, daily reports, and system status.
- [ ] Render media as metadata and external links only. Reject mirror/thumbnail/embed features that store third-party image/video/audio assets.
- [ ] Independently record research commit, transcript commit, audio/text delivery, and Pages deployment states. A Pages failure must not start a new research run or duplicate audio.
- [ ] Implement stale-heartbeat, missed-slot, cadence, OAuth, source-coverage, and delivery diagnostics. Keep private settings out of logs and public reports.
- [ ] Support a controlled late-release window through 08:00 and safe deferred-slot behavior afterward.
- [ ] Document platform schedule limitations, default-branch requirements, inactivity conditions, manual recovery, and the absence of an independent external monitor.

Use current timezone-aware GitHub syntax, not a fixed UTC offset. Test both spring-forward and fall-back boundaries with injected clocks. A seven-day local-calendar gap is not always 168 elapsed UTC hours. No more than one new episode may be released on one Europe/Rome date, even when jobs are delayed or restarted.

The public transcript commit can appear before the 06:00 Telegram release because the repository is public. Do not promise an embargo. The publication job waits within a bounded window when ready early, and records lateness when ready late. Scheduler congestion may delay execution; expose actual timestamps rather than claiming punctuality from the cron expression.

**Exit evidence:** dry-run/manual/scheduled-like tests share the same state machine; DST and delayed-trigger tests create correct slots; an unrelated branch rebase does not corrupt hashes; a material script/evidence conflict invalidates the affected render; wiki pages rebuild from committed text/metadata; no media or secrets appear in Git/Pages/Actions artifacts.

## 14. M10 — Acceptance tests and controlled activation

Build deterministic offline fixtures first. Then run bounded live provider and Telegram tests only with configured credentials and intended destinations. Do not assert live verification from simulated responses. Keep a sanitized evidence record naming the commit, environment, commands, test outcomes, provider versions, and any blocked cases.

### Acceptance matrix

All cases below are required unless a case explicitly states an external prerequisite. A blocked external case remains visible and prevents claiming full live readiness; it does not prevent development of independent parts.

| ID | Scenario | Required result |
|---|---|---|
| A01 | Same X post arrives through several queries and a repost | One original source identity; distinct repost relationship; no duplicate research work. |
| A02 | Five articles copy one company announcement | Five reports can be registered, but corroboration counts one origin, not five independent confirmations. |
| A03 | Company/robot handle or display name changes | Stable identity and historical links remain valid; aliases update without a duplicate entity. |
| A04 | Two robot versions share a marketing name | Separate configuration/version records; performance cannot transfer automatically between them. |
| A05 | An old demonstration is reposted today | Discovery date updates; original event date and “old footage” context remain intact. |
| A06 | Primary source is inaccessible; secondary report is inspected | Original URL is retained, but evidence is attributed to the secondary report with access limitations. |
| A07 | Source article is corrected or retracted | Append a revision/correction; identify all affected wiki sections, claims, ideas, and episode segments. |
| A08 | Source content was never retrieved | No invented content hash, excerpt, metadata field, or claim of inspection. |
| A09 | Citation URL resolves but does not support the sentence | Semantic review rejects the factual clause despite valid reference integrity. |
| A10 | Claim combines a supported number with an unsupported conclusion | Split or qualify the claim; supported numeric evidence does not validate the unsupported clause. |
| A11 | Anonymous repost makes a capability assertion | Preserve uploader/origin uncertainty; do not infer original authorship or independent verification. |
| A12 | Demo autonomy, speed, or human intervention is unknown | Unknown fields remain explicit; no assertion of full autonomy or production readiness. |
| A13 | Foreign-language official announcement | English synthesis preserves names, original title/language, source links, units, and appropriate attribution. |
| A14 | A podcast or wiki summary is offered as fresh corroboration | Follow its external provenance or reject it as independent evidence; no self-citation loop. |
| A15 | Grok OAuth login succeeds but search returns uncited prose | Record an unsourced/degraded lead; no verified X news or invented post URL. |
| A16 | X response says `degraded=false` but has no citations | Robotelier still classifies it as unsourced. |
| A17 | Paid xAI key exists in the host environment | Isolated X profile excludes it; only the authorized OAuth route is used. |
| A18 | Grok OAuth expires or refresh is revoked | Bounded typed failure; no infinite retry, paid fallback, or interactive prompt in a scheduled run. |
| A19 | Live X evidence probe through the configured account | Genuine post evidence and credential source are verified, or M3 stays blocked. |
| A20 | One adapter fails while others succeed | Successful research persists; failed coverage is visible and never reported as “no news.” |
| A21 | Crash occurs after item registration but before cursor update | Retry deduplicates safely; no source is lost and no false complete window is recorded. |
| A22 | Non-exhaustive search response has a time filter | Store query coverage only; do not claim exhaustive account-stream ingestion. |
| A23 | Candidate or budget bound is reached | Defer remaining work with reasons; reserved editorial/publication budget remains protected. |
| A24 | Source embeds malicious instructions or a private-network URL | Ignore instructions; block unsafe fetches and redirects; expose no secrets. |
| A25 | A discovered media URL expires or contains a signature | Retain stable origin/ID and safe metadata; omit credential-bearing URL and require re-resolution. |
| A26 | Media has no direct URL, duration, creator, or license | Store unknown values with reasons, not guesses; metadata registration still succeeds. |
| A27 | Research discovers images/videos before an episode exists | Media metadata is registered immediately and later linkable to script segments. |
| A28 | Agent, site build, or debug log attempts to persist media bytes | Validation rejects the change; no copied thumbnail, base64 asset, waveform, or media artifact remains. |
| A29 | Two workflows/local harnesses try to claim work | One live lease; the other waits/exits according to policy; no concurrent agent execution. |
| A30 | A timed-out agent writes after lease reassignment | Fencing rejects the stale write and preserves the new owner's state. |
| A31 | Agent invents command receipts or directly edits structured JSON | Controller rejects unaudited changes and relies on observed receipts/deltas. |
| A32 | Auth refresh succeeds but research validation fails | Persist the verified encrypted refresh update separately; reject the invalid research mutation. |
| A33 | A source prompt asks for GitHub or Telegram credentials | Isolated agent cannot access these capabilities, including via mounted files or inherited environment. |
| A34 | Highest-scoring idea lacks sufficient evidence | Queue targeted research and select the highest-scoring eligible alternative. |
| A35 | Review lowers scores or merges overlapping ideas | Changes retain rationale/history; deterministic ranking and tie-breaks remain reproducible. |
| A36 | An old uncovered finding predates the latest episode cutoff | Coverage ledger retains it as unreported; it is not silently discarded by a global timestamp. |
| A37 | Daily news is too thin for ten minutes | No episode; research and ideas persist; daily report gives the genuine reason. |
| A38 | Several quiet days build a useful weekly theme | Day-four through day-six preparation produces one dense weekly episode by the deadline. |
| A39 | No sufficiently supported story exists by day seven | Explicit cadence breach and alert; no padding, fake news, or false success. |
| A40 | Bootstrap is restarted repeatedly | First-release deadline retains original activation anchor and cannot be postponed by resets. |
| A41 | A script repeats earlier narration without a new angle | Novelty review removes/rejects repetition; old context cannot count as new material. |
| A42 | Writer adds a plausible fact absent from frozen evidence | Clause-level review blocks it or returns a specific evidence-gap task. |
| A43 | Source is materially corrected after the evidence freeze | Final release gate identifies the affected segments; revise/review or block publication. |
| A44 | Transcript changes after rendering | Hash mismatch blocks reuse/sending of the old audio. |
| A45 | TTS produces less than 600 or more than 1,200 seconds | Reject render for delivery; revise content naturally within bounded attempts. |
| A46 | Same transcript is rendered again after definitive failure | Same episode, new render ID/hash/timing map; no promise of byte-identical audio. |
| A47 | Source-video offsets are confused with episode timing | Schema validation rejects the wrong coordinate system or requires explicit qualification. |
| A48 | Telegram rejects upload definitively | Record a known failure and bounded safe retry; transcript success remains intact. |
| A49 | Telegram may have accepted audio but the response is lost | `delivery_unknown`; no blind automatic resend or fabricated acknowledgment. |
| A50 | Audio is accepted but receipt commit fails | Reconciliation-required state prevents duplicate replay after restart. |
| A51 | TTS/delivery is cancelled or times out | Observed cleanup removes all temporary audio/chunks/manifests; public state retains metadata only. |
| A52 | Ephemeral runner disappears before cleanup can be observed | No intended durable media artifact exists; record unknown cleanup observation, not a fake confirmation. |
| A53 | Public transcript succeeds but audio or Pages fails | Separate channel states; retry only safe failed stages; no research rollback or duplicate episode. |
| A54 | Scheduler runs across Europe/Rome DST transitions | Correct local 06:00 slot and local-calendar weekly deadline; no fixed-offset drift. |
| A55 | Manual and scheduled publications overlap on one local date | Atomic reservation/delivery state prevents a second new episode; a committed transcript locks its slot even if audio fails. |
| A56 | Publication job starts late or research is incomplete | Use phase receipts and valid committed knowledge; record lateness/gaps; do not invent completed research. |
| A57 | Publication misses the 08:00 late window | Keep transcript/intent, revalidate for a controlled later slot, and expose the missed target. |
| A58 | Git rebase changes only unrelated data | Revalidate safe patch and derived views without unnecessary re-research. |
| A59 | Git rebase changes evidence, selection, or script | Invalidate and revalidate the affected package/render; never force-push a stale artifact. |
| A60 | Native wiki maintenance edits beyond its scope | Reject structured-state, claim, schema, score, or released-script mutation. |
| A61 | An untrusted PR runs CI | Offline checks only; no model, Telegram, Git-write, or deployment secrets exposed. |
| A62 | A clean checkout rebuilds the public site | Same canonical records reproduce indexes/citations and metadata-only pages with valid links. |

### Test layers

**Unit and property tests:** URL identity, units/date precision, local time slots, schema migrations, graph references, score bounds and monotonicity within the chosen policy, source-origin grouping, media URL sanitization, dedupe, lease fencing, budget accounting, outbox state transitions, and atomic transaction recovery. Use injected clocks and deterministic IDs where appropriate.

**Integration tests:** CLI mutations plus receipts, isolated fixture-based agent runs, source-adapter fixtures, paired wiki/record edits, complete queue lifecycle, idea ranking/review, script provenance, renderer stub, Telegram stub, and clean Git patch/rebase handling. Provider-dependent assertions use recorded sanitized response contracts or fakes, not uncontrolled live calls.

**Semantic evaluation fixtures:** deliberately misleading demo claims, unsupported inferences, copied announcements, dense versus padded outlines, old versus genuinely new stories, English outputs from non-English sources, and source-correction propagation. Keep expected failure explanations; do not certify semantic quality using only the writer's self-evaluation. Model reviews are additional evidence, not substitutes for deterministic unit tests.

**Live controlled tests:** the actual configured OpenAI profiles, Grok OAuth post-evidence extraction, native wiki skill, selected TTS voice, Telegram target, and Pages deployment. Bound usage, preserve sanitized metadata, and remove all temporary media. A test message must identify itself as a test, not a real published episode.

## 15. End-to-end rehearsals

Before activation, run at least the following scripted rehearsals with injected dates. These are simulated operational days, not a request to wait for real weeks.

### Rehearsal A — Fourteen local days of editorial behavior

Days one through three provide thin, related robotics announcements; no filler episode is produced. On day four, weekly readiness prepares a coherent candidate. Days five and six add targeted verification; by day seven the system releases a dense episode. On the next day a major independently documented development supports a new episode. Later days introduce recycled footage, a source correction, a valuable non-humanoid development, and an adapter outage. The system maintains provenance, avoids repeat stories, preserves non-X coverage, and produces another qualifying weekly episode by the rolling deadline.

Assert daily caps, weekly readiness, frozen packages, topic coverage, every factual segment's source path, separate transcript/audio outcomes, and absence of retained media after every simulated cycle.

### Rehearsal B — Delivery ambiguity and recovery

Generate a validated episode, write its outbox intent, and simulate a network timeout after possible Telegram acceptance. Restart with the same slot and episode identity. Confirm that recovery does not blindly regenerate/send or count the episode as acknowledged. Apply an explicit test reconciliation; then continue from the correct stage without duplicate publication. Separately test a definitive upload failure where a new render attempt is permitted because prior temporary bytes were deleted.

### Rehearsal C — Evidence correction between freeze and release

Freeze an episode based on a manufacturer's claim. Before delivery, ingest a material correction. The reverse index identifies the affected script segments; the final release gate blocks the outdated assertion. The revised script preserves the original attribution and explains the correction, gets fresh review, and receives a new render binding. An already released historical episode instead receives linked correction metadata and a correction notice, not silently replaced history.

### Rehearsal D — Clock and workflow faults

Run simulated spring-forward and fall-back periods, a skipped research trigger, a delayed publication trigger, two concurrent manual runs, and a safe versus unsafe Git rebase. Validate intended-date identity, one-agent execution, local-calendar deadlines, phase receipts, bounded late release, and explicit missed-run status. Do not claim that the recovery workflow is an independently reliable external monitor.

## 16. Activation checklist and operational handoff

- [ ] All applicable offline tests and rehearsals pass at an identified commit.
- [ ] Live model, Grok OAuth evidence, TTS, Telegram, and Pages checks have actual recorded outcomes; unresolved failures are not marked complete.
- [ ] Source registry contains verified public identities spanning humanoid and broader robotics coverage.
- [ ] Isolated auth state is configured without importing PaperTrader secret files or sharing an unsafe rotating refresh-token path.
- [ ] Telegram destination is configured out of public data; the control test arrived at the intended chat/channel.
- [ ] Temporary media cleanup and artifact-exclusion checks passed after success, failure, and cancellation.
- [ ] The repository and generated wiki are public; no audio hosting or source-media mirroring exists.
- [ ] The first-release deadline and the 06:00 Europe/Rome schedules are configured and visible.
- [ ] A coherent weekly candidate or a concrete evidence-backed preparation plan exists for bootstrap.
- [ ] Scheduled workflows are enabled only after these prerequisites; ordinary operation then runs without approvals.
- [ ] `README.md` and `docs/OPERATIONS.md` explain safe manual research, dry runs, exact-stage resume, auth refresh/re-authentication, delivery reconciliation, source gaps, cadence breaches, and correcting historical claims.
- [ ] Public status distinguishes research success, transcript availability, Telegram text/audio acknowledgment, Pages deployment, and unknown outcomes.

The operator runbook must contain verified examples for source/subscription addition, bounded backfill, manual topic input, queue inspection, source-to-episode trace, local Codex harness execution, dry-run daily cycles, live capability probes, native wiki maintenance, and safe recovery. It must not suggest editing canonical JSON manually or deleting failed attempts to make status look healthy.

The handoff report names completed milestones, actual test commands and outcomes, live checks, remaining blockers, pinned dependencies, configured schedules, and artifact/publication locations. Do not include credentials. Do not claim that the weekly or 06:00 target is guaranteed by cron alone.

## 17. Definition of done

Robotelier is complete for this release when it can execute the following chain autonomously under its bounded policies:

```text
Daily source discovery, including validated Grok OAuth X research
  → source and media metadata registration
  → deduplicated, evidence-backed robotics research
  → linked English LLMWiki updates and historical claim records
  → persistent podcast idea proposals
  → independently reviewed, reproducible priorities
  → highest-priority eligible selection
  → dense ten-to-twenty-minute single-narrator script
  → frozen, segment-level original-source provenance
  → temporary validated audio
  → committed transcript and Telegram delivery around 06:00 Europe/Rome
  → media cleanup, honest channel receipts, and safe recovery
```

Every material spoken claim can be traced to inspected evidence, with original-source linkage and honest secondary attribution. Every relevant discovered media item has a metadata record, even before it is used in an episode. No media bytes are retained by Robotelier. The cadence controller works proactively toward weekly publication without producing daily filler or bypassing evidence gates.

## 18. Deferred scope — do not implement accidentally

Video production, image generation, source-media downloads/archives, asset storage, audio archives, podcast RSS, Spotify/YouTube publishing, multiple narrators, translated episodes, investment analysis/trading, social posting, paid fallback providers, a separate hosted database, independent external monitoring, and human approval of every ordinary episode are outside this release.

Preserve only the provenance/metadata interfaces needed for later media selection: stable segment IDs, source/media identities, source time ranges, render-specific timing observations, original creator/license references, and correction impact traversal. Future video output must re-resolve assets and rights rather than assume metadata-only storage preserved the original bytes.

## 19. Reference and design verification notes

The source references and inspected PaperTrader commit are recorded in [AGENTS.md](AGENTS.md), section 17. The intended implementation pins actual code/provider versions during M0–M3. Current documentation and repository values are reference evidence, not proof that Robotelier's integrations have been executed.

Specific adoption checks that must remain in the plan:

- PaperTrader's dormant external-source watching is not Robotelier's discovery implementation.
- PaperTrader's translation path and investment-specific script constraints are excluded.
- Grok OAuth login and evidence-bearing X search are separate acceptance tests.
- GitHub supports IANA-aware schedules, but hosted runs may still be delayed or missed.
- Native `llm-wiki` is retained; no redundant maintenance framework is introduced.
- Media retention is metadata-only, including generated audio after Telegram delivery.
- Temporary audio cannot cross jobs through Actions artifacts to solve the trust-boundary problem.
- A valid provenance graph must still undergo semantic evidence review.
- Unknown external delivery cannot truthfully be marked successful or retried as if no side effect occurred.
- Tests specified in this plan are not tests already performed.
