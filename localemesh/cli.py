from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from .io import load_build
from .full import evaluate

def main():
    p=argparse.ArgumentParser(description='Offline multilingual release-contract checker')
    p.add_argument('manifest',type=Path);p.add_argument('build',type=Path)
    p.add_argument('--output',type=Path)
    p.add_argument('--browser',action='store_true',help='Use installed Chromium for offline inert HTML tree extraction')
    a=p.parse_args()
    try:
        if a.browser:
            from .browser import BrowserExtractor
            with BrowserExtractor() as browser:
                facts=load_build(a.manifest,a.build,html_extractor=browser.extract)
        else: facts=load_build(a.manifest,a.build)
        issues=sorted(evaluate(facts))
    except (ValueError,OSError,KeyError,RuntimeError,ImportError) as e:
        print(f'Input failure: {e}',file=sys.stderr);return 3
    report={'release_errors':sum(i.category=='release' for i in issues),
            'policy_ambiguities':sum(i.category=='ambiguity' for i in issues),
            'findings':[i.json() for i in issues]}
    text=json.dumps(report,indent=2)
    if a.output:a.output.write_text(text+'\n',encoding='utf8')
    else:print(text)
    return 1 if report['release_errors'] else 2 if report['policy_ambiguities'] else 0
if __name__=='__main__':raise SystemExit(main())
