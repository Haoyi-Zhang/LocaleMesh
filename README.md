# LocaleMesh

Contract-aware, obligation-sliced checking of multilingual Web releases.
The checker compares declared content identity, locale and discovery contracts
with emitted HTML, headers, sitemaps and publication state. It does not infer
translation identity from text similarity.

## Run

Run from this `artifact/` directory with Python 3.11 or newer:

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

For optional `--browser` extraction, install `python -m pip install -e '.[browser]'`
and set `LOCALEMESH_CHROMIUM` to the local executable (`export
LOCALEMESH_CHROMIUM=/path/to/chromium` on POSIX, or
`$env:LOCALEMESH_CHROMIUM = 'C:/path/to/chrome.exe'` in PowerShell).
`docs/BROWSER-EXTRACTION.md` describes the extraction boundary. The full measurement/plot driver additionally uses
`requirements-analysis.txt`, `coverage` and `fonttools`; these are not dependencies
of the base checker. Its full-run scripts execute the retained experiment
families, so they are not lightweight smoke commands. On systems without the
POSIX CPU-affinity API, the execution record reports that field as unavailable.
Before a full run, set `LOCALEMESH_PLOT_FONT` to the existing Linux Libertine TTF
described in the plot section below. The driver forwards it to sliced plotting
and rejects an absent file before launching the experiment stages; the plotter
still checks the actual font's family, outline type and embedding permission.

The offline suite includes batch-join, differential-maintenance, and plot-font
regressions. The command above reports its actual test and skip counts.
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

The complete runner requires the full project bundle, with this directory at
`artifact/` beside `paper/`; the standalone artifact-root repository does not
contain the manuscript builder and is not sufficient for this full-run command.
It uses `python ../paper/build.py` to produce the anonymous `paper/main.pdf`.
Use the base checker and offline tests above in the standalone repository; the
full runner does not skip the missing manuscript stages or certify a partial
run as complete. PDF preflight checks that output without requiring a retained
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

`scripts/evaluate_alias_report.py` separately runs the original minimal site
attached to [Hugo issue14365](https://github.com/gohugoio/hugo/issues/14365).
Acquire the public `hugo-alias-test.zip` linked in that report; the runner checks
its inspected input identity and member set before local extraction. It invokes
only Hugo, without a server, external modules or downloaded scripts:

```sh
python scripts/evaluate_alias_report.py --hugo /path/to/hugo-0.147.9 --source-archive /path/to/hugo-alias-test.zip --output results/native-alias-new
```

The retained `results/native-alias-case/summary.json` describes four native builds
over two paired French-language toggles of one independently supplied minimal
site. Every target is reachable. The two multilingual outputs redirect the fixed
English alias to French; the two English-only outputs satisfy that alias policy.
Full, validated sliced and ordinary same-information target comparisons agree.
This is report-led native mechanism evidence, not a complete Docsy rebuild,
four independent faults, a performance study or a uniquely superior detector.
The upstream attachment is acquired separately; this repository's MIT license
does not grant a license over that external source. Its version marker names
the reported0.154.5; the local study explicitly records the executed0.147.9.

## Cache membership maintenance

The sliced engine now retains equal dependency memberships and finding references
after mandatory rule reevaluation. `docs/MAINTENANCE-RESULTS.md` gives the paired
comparison with the previous refresh routine, including slower small cases,
unchanged retained memory and checking-only replay of native outputs. The older
scale and native whole-workflow numbers remain measurements of the previous
refresh routine; they were not overwritten or silently relabeled.

## Re-export the statistical plots

The workflow schematic is generated directly with Matplotlib, with embedded
fonts and no TeX rendering. In the full project bundle, `paper/build.py`
regenerates it before compiling. From this artifact root:

```sh
python plots/draw_architecture.py --output-dir ../paper/figures
```

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
