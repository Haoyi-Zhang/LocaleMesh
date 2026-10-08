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

The current suite contains 75 offline tests. The retained executed count of 73
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
