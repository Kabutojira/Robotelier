# External contracts

Verified on 2026-09-06. These references constrain adapters and workflows; they are not proof that
the configured accounts passed live checks.

- [OpenAI GPT-5.6 Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol) documents the exact
  selected model and its web-search support. Robotelier still treats search results as discovery
  leads until the originating source is inspected.
- [Hermes providers](https://hermes-agent.nousresearch.com/docs/integrations/providers) documents
  `hermes auth add openai-codex` and automatic refresh behavior. The pinned container and configured
  account remain the authoritative runtime acceptance surface.
- [GitHub scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
  documents IANA `timezone`, default-branch execution, possible delays/drops, and the public-repo
  inactivity condition. The schedule is a target, never an exact-time guarantee.
- [Telegram `sendAudio`](https://core.telegram.org/bots/api#sendaudio) currently accepts MP3/M4A
  audio with a 50 MB bot limit and a 1,024-character caption. `sendMessage` has a 4,096-character
  text limit. Robotelier commits intent before the side effect and treats lost responses as unknown.
- [Edge TTS 7.2.8](https://github.com/rany2/edge-tts/releases/tag/7.2.8) is pinned for the initial
  voice path. Output is measured with `ffprobe`; availability and bytes are not reproducible.
- [Quartz commit 4923affa](https://github.com/jackyzha0/quartz/tree/4923affa7722dfc751f1074348e6dad214fe0c08)
  is locked by the site package. RSS is disabled and only canonical Markdown/metadata are built.

The starter registry was checked against official company/lab pages. The Boston Dynamics and
Agility X handles were followed from their official sites; those X subscriptions remain inactive
until a live OpenAI Sol operation returns resolvable inspected originating-post evidence.
