# Manifest and local observation schema (version 1)

The contract is read from `manifest.json`, not reconstructed from the HTML being checked. In the laboratory fixtures both contract and publication input are initially created by the same generator, then modified separately. This supplies an executable contract but not independent editorial truth.

```json
{
  "schema": 1,
  "config": {
    "origins": {"https://example.test": "main"},
    "locales": ["en", "de"],
    "aliases": {},
    "complete_manifest": true,
    "check_links": true
  },
  "pages": {
    "https://example.test/guide/": {
      "key": "guide",
      "locale": "en",
      "state": "published",
      "canonical_allowed": ["https://example.test/guide/"],
      "canonical_channels": ["html"],
      "sitemap": true,
      "discovery": {"html": {"required": ["en", "de"], "reciprocal": true}},
      "agree_channels": [],
      "fallbacks": {}
    }
  }
}
```

Every origin is explicitly mapped to a directory below the build root. `.test` URLs are identities, never network destinations. A real multi-domain build would mount each downloaded origin separately. Mapping two distinct domains to different local directories does not establish DNS or deployment correctness.

A page has a stable content `key`, declared `locale`, and `state` (`published`, `draft`, `removed`, or `redirect`). `represented_locales` optionally admits a declared language fallback; absent this field the HTML language must equal the page locale. `fallbacks` maps an advertised locale to allowed target locales. It does not judge whether the text is an accurate translation.

`canonical_allowed` lists exact permitted canonical targets. `canonical_required` overrides whether presence is required; absent it, the existence of an allowed-target list makes the selected canonical channels required. `canonical_channels` defaults to HTML. LocaleMesh verifies contract membership and local reachability, not duplicated-content equivalence from RFC 6596. It does not follow canonical chains as URL equivalence.

`discovery` selects zero or more of `html`, `http`, and `sitemap`. Each selected channel has a `required` locale-label list and a `reciprocal` flag. Unselected channels are not made mandatory. Partial translation sets are admitted by choosing a smaller required list. Emitted alternatives in selected channels must resolve to an appropriate declared identity; the absence of an unrequired translation is not an error. `x_default` is optional: it constrains an emitted x-default destination only when explicitly supplied; no x-default is universally required.

`agree_channels` requests exact pair-set agreement when both named channels have nonempty annotations. **It does not require either channel to exist.** To require presence, set the channel's `required` list. `sitemap: true` separately requires a URL entry; sitemap alternate annotations are checked only when sitemap discovery is selected.

For redirects, use `redirect_to` or an explicit `redirect_allowed` list. The observed first redirect destination must be permitted and its local chain must terminate. A redirect may be omitted from the sitemap unless the contract explicitly includes it. Route `aliases` are exact, declared equivalences; slash, path-case and arbitrary query differences are not silently collapsed.

`ambiguous: true` records a conflicting declaration. More than one published primary route with the same key/locale produces an identity-collision ambiguity. Model aliases should be declared as aliases rather than accidentally creating two primary identities. Targets outside the mounted origins produce an unmounted-target ambiguity, not proof of a missing remote page.

## Emitted files

HTML extraction reads `<html lang>`, head canonical/alternate links, optional `data-content-key`, body anchors and HTML-refresh redirects. An emitted content key is a cross-check, not a prerequisite for checking alternate destinations against the independent manifest. The default event parser is not an HTML5 browser parser. The optional `--browser` path uses native inert DOMParser; neither path executes input JavaScript. The comparison shares URL normalization and does not imply complete browser or URL conformance.

All local `*.xml` URL sets are inspected, including XHTML alternate links. DTD/entity declarations are rejected. Remote sitemap-index references are not fetched. The implementation is not a complete sitemap schema validator.

`build/_headers.json` maps route URLs to locally supplied objects with `status`, optional `location`, and a `link` list of HTTP Link field strings. These are local HTTP-response fixtures, not captured production responses. Header parsing honors quoted delimiters, retains repeated hreflang, uses the first rel parameter, and ignores an entire anchored link because alternate anchor contexts are outside this profile. It does not claim the whole RFC grammar.

## Ingestion and structural rejection

The supported HTML profile requires an explicit head. The first active base applies to HTML references, including links encountered earlier; HTTP Link references remain response-relative. Template and other inert/raw-text contexts do not supply active declarations. Duplicate HTML attributes retain the first value. Conflicting content markers become ambiguity instead of last-write-wins identity. Unsupported relevant references and recovery/foreign-content constructs produce explicit diagnostics. Irrelevant non-Web icon references are ignored.

Duplicate JSON members, normalized route collisions, invalid schema version/type, invalid policy field types and out-of-mount files are rejected. Unknown extension fields are not universally rejected: this is hand-written boundary validation, not a claim of complete JSON Schema coverage. XML DTD/entities and malformed XML are rejected; remote indexes are not retrieved.

## Incremental API obligations

`snapshot(manifest, observations, sitemaps)` creates cfg, m, o, s and derived g facts. `delta(old,new)` compares complete snapshots and represents deletion by `None`. Lower-level caches expect a complete normalized delta including group changes. Both cache constructors and updates copy input; `.facts` returns detached copies.

Prefer `ReleaseSession(facts, engine_class=Incremental)` or `FacetedIncremental`. Its `apply(primary_changes)` accepts only cfg/m/o/s, validates before mutation, and derives affected g buckets from old and new declarations. Clients cannot directly submit g facts through this interface. A failed validation does not increment its revision. Completeness of the supplied primary change set remains the caller's responsibility. A changed predicate version requires a new session. Internal/private engine attributes are not an extension API.

The field-sensitive engine tracks leaf values, mapping keys/membership and missing paths for the current read-only owner predicate. It treats lists as atomic, may overinvalidate, and is not an automatic full/incremental dispatcher. The conditional trace argument in the paper assumes all observations are mediated and no in-place mutation occurs during evaluation.

`Issue` records category (`release` or `ambiguity`), code, source route, channel and detail. CLI exit codes: 0 satisfied, 1 release violation, 2 ambiguity without a release violation, 3 structural input failure. No persistent watcher or production HTTP server is included.

## Strict policy boundary in implementation 0.4

Unknown names in `config`, a page declaration, or a selected discovery-channel policy raise a structural input error. This prevents misspelled requirements from becoming silently unused metadata. Nonsemantic additions at these boundaries must be placed in an `extensions` object; its contents do not affect obligations. Top-level manifest metadata and extensible observation records are not all rejected by this policy.

`config.locales`, when present, must be a list of nonempty strings, not a string, null or numeric list. A page with `state: "redirect"` must provide `redirect_to` or a nonempty `redirect_allowed` list. Declaring only that a route is a redirect does not name a checkable target.

Validation completes before a `ReleaseSession` transaction is installed. A rejected mixed transaction leaves its revision, owned facts and findings unchanged, including any otherwise valid changes in that transaction. Thirteen archived-validator acceptances are replayed in `results/contract-boundary.json`; they are this project's own schema regressions, not external historical defects.
