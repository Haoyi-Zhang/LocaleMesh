# Executed Pandoc publication pipeline

Run from artifact: `python scripts/evaluate_pandoc.py`.

This executes installed Pandoc with `--sandbox`, its Markdown reader and HTML5 writer, using the authored publisher.html template and generated local headers. Five complete unchanged public Markdown files are verified against the pinned source-index records before execution. A separately retained source-index contract is compared with emitted output. There are five metadata reads and 53 HTML writer invocations across 11 releases.

The source-index facts and contracts are not an external human oracle. Sources come from the same Polyglot upstream as the PJ adaptation. Liquid constructs are not executed, the whole upstream site is not rebuilt, and ordinary body links are outside the selected five-page contract. This is not Jekyll, Astro, Hugo or Next.js execution.

Every command, return code, elapsed time and stderr is in results/pandoc-run.json. Installed Pandoc emits language-resource warnings for some non-English outputs; these remain visible rather than being represented as warning-free builds. All reported writer invocations returned zero. Individual builds, contracts and header fragments are retained under builds/. The MIT source notice is UPSTREAM-LICENSE.
