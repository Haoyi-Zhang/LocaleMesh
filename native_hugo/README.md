# Native Hugo adaptation and same-information cost experiment

This adapter runs the official standard Hugo 0.147.9 executable over the five
supplied, pinned public Polyglot Markdown files in `pandoc_integration/source/`.
It is one small source adaptation, not a full upstream Jekyll rebuild, a new
independent site, production use or adoption.

From `artifact/`, using a local 0.147.9 executable:

```sh
python scripts/evaluate_native_hugo.py --hugo /path/to/hugo --output results/native-hugo-new --repeats 12
```

The output directory must not exist and must be inside this artifact. The script
never deletes or overwrites a previous experiment. Dependency acquisition is
separate: obtain the matching standard executable and checksum file from
[Hugo's official 0.147.9 release](https://github.com/gohugoio/hugo/releases/tag/v0.147.9),
verify the release checksum, and keep the binary with its bundled license in a
local ignored runtime directory. No Python package installation is needed. The
retained run used Python 3.12.14 on Windows amd64, `PYTHONHASHSEED=118`, and
`GOMAXPROCS=1` for Hugo. The downloaded native executable stays in ignored local
`.deps/`, with its bundled Apache-2.0 license. This old measurement pin is not a
current deployment recommendation.

The runner verifies every original source's Git blob ID before adapting front
matter. Baseline Markdown bodies remain byte-identical after the front-matter
boundary. The separately retained source-index record supplies content keys,
locale and permitted paths to the contract; it is not independent adjudication.
The template uses Hugo language assignment, custom permalinks and
`AllTranslations`, not an authored list of alternate URLs.

The policy is direct-URL HTML canonicals and alternates. Generated
home/section/taxonomy/404 pages, sitemaps, content aliases and Hugo's default-
language redirect are disabled explicitly. No themes, modules, remote resources,
external commands, JavaScript, server or publication step are invoked. Liquid
examples remain literal. Ordinary body-link obligations are disabled because the
excerpts omit the upstream target universe. The output-only control's excluded
body-link findings are retained, not erased or counted as annotation failures.
Existing checker redirect, sitemap, XML, mount and other policy checks are unchanged.

Eight configurations are a clean seed, three legitimate changes (body edit,
partial translation, permitted cross-locale canonical) and four injected faults
(wrong canonical, missing alternate, omitted source, translation-group swap).
For the grouping swap, coverage is predeclared optional on all five pages to
isolate identity from unequal family sizes. It produces six identity findings in
one release, not six field incidents. The body edit appends one authored paragraph;
other variants alter adapted metadata or source inclusion. The original files
are never edited.

`localemesh.contract_join.evaluate_html_contract` is an authored batch join with
the same facts and contract as LocaleMesh. It imports no checker or cache rule.
Its profile covers published unique identities, HTML language/markers, canonical
policy, required labels, direct target availability, identity, locale and
reciprocity. It rejects unsupported policy, including aliases, redirects,
fallback, multi-channel rules and ordinary links. It is not an augmented Crawl
Cove, an external oracle or a general competitor.

## Retained 12-pair run

These whole-workflow timings use the earlier all-membership-replacement refresh.
The current membership-retaining engine was checked and timed by replaying these
outputs without new native builds; see `../docs/MAINTENANCE-RESULTS.md`. The old
build commands and costs are not attributed to a newly generated experiment.

`results/native-hugo-12/results.json` retains 92 native build commands with zero
return codes, source checks, seven diagnostic cohorts, 84 measured updates, cold
starts, component times and inclusive IQRs. All eight source configurations and
emitted candidates are retained beneath that run. The clean seed is checked
separately. Complete findings agree among join, full scan, validated route-wide
cache and validated sliced cache.

Whole costs charge subprocess generation, full extraction/normalization,
checking and deterministic JSON issue export. Cached paths also pay full
snapshot difference and validated apply. Methods share the same measured
generation/extraction sample per repetition; checking order rotates. Cold
construction/export is charged once per 12-update sequence. The initial clean
build was measured once and reused in seven component-accounted startup totals.
These are not four independently timed build pipelines or multi-machine
confidence intervals. Warm-up, dependency download, source preparation,
assertions, reporting and publication are outside the totals.

Summed finite costs are 6.946849 s (join), 6.948246 s (full), 6.981114 s
(route-wide), and 6.978221 s (sliced). Generator medians are 69.27--74.46 ms;
extraction medians are 4.19--4.61 ms. The body edit changes no checking fact and
allows a cheap transaction, but its whole-path reduction is only about 0.04 ms
in a 74 ms workflow. There is no material end-to-end cache benefit or production
threshold. Batch contract checking is the useful small-release mode.

The old 321-snapshot, Pandoc, Crawl Cove, Chromium and synthetic scale results
remain separate; this experiment does not reexecute or replace them.
