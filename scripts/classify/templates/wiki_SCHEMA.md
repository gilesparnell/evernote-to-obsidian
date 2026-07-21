---
title: Wiki Schema
type: schema
updated: 2026-07-21
---

# Wiki conventions

Topic pages compile everything the vault knows about one subject. Write plain,
factual British English. Every claim must come from a source; never invent
detail. If sources disagree, keep both and flag it — a contradiction is
information, not a problem to smooth over.

## Provenance is mandatory

- Every sentence in a synthesised section ends with a source pointer `(src: Bn)`
  where `Bn` is a numbered source block (B1, B2, …) listed at the foot of the page.
- Anything you cannot tie to a source goes under `## Inferences (not in the
  source)` — never inside the factual sections. Say plainly it is inference.
- Do not cite a block number that does not exist. Only use B1…B<count>.

## Sections (in order)

`## Summary` · `## Timeline` · `## Key facts` · `## Open questions`. A
`> [!contradiction]` callout appears only when sources genuinely conflict. The
`## Inferences (not in the source)` and `## Source blocks` sections are appended
by the tool.

## Links

Only link to wiki pages that already exist — a whitelist is supplied with each
run. Never invent `[[wikilinks]]`; any link not on the whitelist is stripped.

## Slugs and aliases

One canonical slug per topic (lower-case, hyphenated, NFKD-folded — `Julie's`
→ `julies`). Aliases resolve to the slug; two topics may never share an alias.

Topic stubs may also carry `exclude:` patterns. Each entry is matched as a
glob against both the vault-relative POSIX path and the filename, and it wins
before alias matching. Use this to keep source material that mentions a topic
out of that topic page without weakening the alias list.

## Source-note backlinks

Matched source notes may carry a `topics:` frontmatter list such as
`topics: ["[[julie-finances]]"]`. Entries whose slug is a registered topic are
managed by the chain: the chain adds missing matches and removes registered
topics that no longer match. Entries whose slug is not registered are
hand-written and preserved exactly.

## Sentinels — machine vs human regions

The block between `<!-- @generated:start -->` and `<!-- @generated:end -->` is
owned by the tool and rewritten on every run. The block between
`<!-- @user:start -->` and `<!-- @user:end -->` is yours — the tool never
touches it. Put your own notes there; they survive re-synthesis.

## This file is human-owned

The model never edits SCHEMA.md. Change conventions here by hand; the engine
reads them but never writes them.
