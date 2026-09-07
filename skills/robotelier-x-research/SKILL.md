---
name: robotelier-x-research
description: Perform bounded read-only X-focused discovery with OpenAI Sol and resolvable originating-post evidence.
metadata:
  version: 1.1.0
---

# X research

Use only the controller-provisioned `openai-codex` profile pinned to `gpt-5.6-sol` and read-only
web/file/terminal tools. Never use `XAI_API_KEY`, xAI OAuth, xurl writes, posting, likes, replies,
DMs, account creation, paid fallback, scraping, or interactive scheduled authentication.

Stay within the operation's query/tool-call/date/account bounds. Accept a result as X evidence only
when it supplies a resolvable originating `x.com/<account>/status/<numeric-id>` citation whose post
identity matches returned metadata. A search answer, title, snippet, or model synthesis without an
inspected originating post remains an unsourced lead. Results represent bounded query coverage,
never an exhaustive timeline.

Use permitted source/media/evidence CLI commands. Distinguish login, inference, tool availability,
citations, metadata, and token refresh. Preserve uploader/origin uncertainty and capture accessible
media metadata without downloads or invented asset URLs. Independently corroborate material
details where the permitted path allows it.

Output sanitized citation metadata and typed status. Use `x_search_unsourced`,
`x_search_unavailable`, `x_auth_expired`, `x_throttled`, `post_identity_invalid`, or
`metadata_incomplete` when appropriate. Never retain raw auth or the full provider conversation.
