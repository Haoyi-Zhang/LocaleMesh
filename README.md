# LocaleMesh

Contract-aware, obligation-sliced checking of multilingual Web releases.
The checker compares declared content identity, locale and discovery contracts
with emitted HTML, headers, sitemaps and publication state. It does not infer
translation identity from text similarity.

## Run

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

The current suite contains 84 offline tests, including seven batch-join tests
and two differential-maintenance regressions.
The retained executed count of 73
and its coverage figures in `RESULTS-SUMMARY.json` describe an earlier run.
`inputs/`, `integrations/`,
`independent_sources/`, and `results/` retain the study inputs and measurements.
`RESULTS-SUMMARY.json` gives the paired timing calculation and measurement
scope. Combined-cost medians are computed from paired samples, not by adding
unrelated medians. The retained native Chromium result is 25/30 matching boundary
cases. The current offline browser-tree projection records 26/30 under
`results/local-validation/`; it is not a new Chromium run and does not reanalyze
the 53 compiled-output checks or 11 native-gate checks.

The complete runner uses `python ../paper/build.py` to produce the anonymous
`paper/main.pdf`. PDF preflight checks that output without requiring a retained
TeX log or an identified-author copy. The builder checks its temporary log before
installing the PDF; preflight alone does not verify those build diagnostics or
visual layout. See `docs/METHODOLOGY.md` for the full-run boundaries.

Browser reconstruction, Pandoc compilation, and full timing experiments have
additional dependencies documented with their scripts. The portable CI tests
the checker; it does not silently substitute model checks for those experiments.
Third-party sources retain their licenses and `THIRD-PARTY-NOTICES.md`.

## Native generator and equal-information comparison

`native_hugo/README.md` describes the executed Hugo 0.147.9 adaptation over the
five supplied public Markdown sources. Run `scripts/evaluate_native_hugo.py`
with a local Hugo binary and a new artifact-local output directory. The retained
12-pair result is `results/native-hugo-12/results.json`: 92 successful native
builds, 84 measured updates and exact agreement among the same-information batch
join, full scan and two validated caches. Whole costs include generation,
extraction, issue export, cached differencing and cold setup. Caching has no
material whole-workflow benefit on this small input. These are controlled changes
on the same upstream used by Pandoc, not field incidents or adoption.

## Cache membership maintenance

The sliced engine now retains equal dependency memberships and finding references
after mandatory rule reevaluation. `docs/MAINTENANCE-RESULTS.md` gives the paired
comparison with the previous refresh routine, including slower small cases,
unchanged retained memory and checking-only replay of native outputs. The older
scale and native whole-workflow numbers remain measurements of the previous
refresh routine; they were not overwritten or silently relabeled.

## Re-export the statistical plots

The two published cost plots use the retained paired medians and inclusive IQRs.
With Matplotlib and fontTools installed, pass an existing embeddable Linux
Libertine TrueType font containing glyf/loca outlines:

```sh
python scripts/analyze_sliced.py --plots --font-file /path/to/LinLibertine_R.ttf
```

This command also regenerates the sliced tables and summaries from the retained
raw records. PDF text is bound to that font file, rather than resolved through a
same-family name; CFF/OpenType outlines are rejected for type-42 PDF output.
The PDFs are vector graphics, and PNG exports use 600 dpi. The font itself is an
external dependency, not a bundled project asset.

The optional font tests use existing TTF/CFF fixtures selected by
`P118_TEST_TTF` and `P118_TEST_CFF`. The missing-font contract test runs without
plotting dependencies. Rebuilding the paper from the delivered vector figures
does not require those external font fixtures.
