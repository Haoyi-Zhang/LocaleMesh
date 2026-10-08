# Pinned Crawl Cove page-mode baseline

Upstream: https://github.com/CrawlCove/crawlcove-hreflang-checker
Commit: ffa29b71872755977068ad3246000f88450dec22 (2026-09-29).
Package version at this commit: 1.0.0. License: MIT, retained verbatim.
`hreflang-upstream.js` is the complete upstream `dist/hreflang.js`, verified against
its Git blob ID c04911e67622f6ea0b2b766d1cec9c28077a3658.

The execution environment could not download `fast-xml-parser` or npm dependencies.
`prepare.py` removes the XML import and the unexecuted sitemap-only suffix from a
COPY, making `page-core.mjs`. All functions exercised by upstream `checkPage` are
byte-for-byte unchanged. This is a **page-mode API extraction**, not installation
or execution of the complete npm package, its CLI, its XML parser, or its sitemap
mode. The original module is retained for inspection.

The harness calls `checkPage` using its supported `fetch` option. Responses are
read from local HTML and explicit `_headers.json` fixtures. The global fetch is
blocked. No production site, external endpoint, or account is queried. Declared
content keys, policy exceptions, and sitemap data are not supplied to the checker.
Only observed page URLs are starting points. Warnings remain warnings, including
missing x-default; no warning is relabeled as an error. Per-page raw API results
are retained, and nonmatching obligations are excluded from shared-scope counts.
