# Robotelier LLMWiki schema

This file is the native LLMWiki orientation contract. All maintained prose is English. Original
proper names, identifiers, source titles, and source-language metadata may be preserved for
fidelity and explained in English.

## Required frontmatter

Maintained pages use YAML frontmatter with these fields:

```yaml
---
page_id: wiki_<20 lowercase hex characters>
title: English title
type: company | robot | technology | relationship | event | news | research | comparison | source | media | podcast_idea | podcast | daily_report
language: en
status: maintained | historical | disputed | stale
created_at: YYYY-MM-DD
updated_at: YYYY-MM-DD
as_of: YYYY-MM-DD | null
review_at: YYYY-MM-DD | null
entity_ids: []
claim_revision_ids: []
provenance_revision_ids: []
---
```

Every factual section starts with an HTML metadata comment immediately below its heading:

```markdown
## Supported capability
<!-- claims: rev_0123456789abcdefabcd -->
```

The referenced claim revision must exist and resolve through evidence to a source access
observation and source identity. A source title or search result is not evidence by itself.
Greeting, navigation, and editorial-transition sections use `<!-- nonfactual -->`; they must not
contain material factual assertions.

## Links and citations

Use ordinary relative Markdown links for wiki navigation and direct HTTPS links for external
sources. Machine IDs remain in frontmatter/comments rather than readable prose. Source and media
pages retain metadata and external links only. Never add images, audio, video, thumbnails, embeds,
base64 data, full articles, full caption bodies, provider conversations, or secret-bearing URLs.

## Page topology

Maintained pages live in `companies/`, `robots/`, `technologies/`, `relationships/`, `events/`,
`news/`, `research/`, `comparisons/`, `sources/`, `media/`, `podcast-ideas/`, `podcasts/`, and
`daily-reports/`. `_meta/` contains deterministic indexes; `_archive/` contains historical pages.
`index.md`, `research-catalog.md`, and `log.md` are deterministic navigation views.

Revisions and corrections are append-only in canonical records. A released transcript is never
silently edited; a correction notice links the historical episode to the new evidence.

