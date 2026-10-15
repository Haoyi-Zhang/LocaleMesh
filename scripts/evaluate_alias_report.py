"""Native local execution of the independently supplied Hugo issue14365 site.

Input is acquired separately, verified, inspected, and never executed as scripts.
This measures release decisions, not latency, field prevalence or a whole Docsy
deployment. The equal-information control directly checks the same alias target.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from localemesh.full import evaluate
from localemesh.io import PageParser, load_build
from localemesh.model import delta
from localemesh.sliced import SlicedIncremental
from localemesh.transaction import ReleaseSession

ARCHIVE_ID='c08c77ac7240d54a2e1912f39c19b7f48eda7546820a1544ab318de6d4b12e02'
SOURCE_URL='https://github.com/user-attachments/files/24555916/hugo-alias-test.zip'
ISSUE_URL='https://github.com/gohugoio/hugo/issues/14365'
ORIGIN='https://example.org'
MEMBERS={'.hvm','hugo.yaml','layouts/all.html','content/en/about.md','content/en/_index.md'}

def extract_inspected(archive,site):
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=ARCHIVE_ID:
        raise ValueError('Public source archive differs from the inspected input')
    seen=set()
    with zipfile.ZipFile(archive) as z:
        for i in z.infolist():
            if i.is_dir() or i.filename.startswith('__MACOSX/'):continue
            p=PurePosixPath(i.filename)
            if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0]!='hugo-alias-test':
                raise ValueError('Unexpected source path')
            rel=p.relative_to('hugo-alias-test').as_posix()
            if rel not in MEMBERS or rel in seen or i.file_size>100_000 or ((i.external_attr>>16)&0o170000)==0o120000:
                raise ValueError('Uninspected, duplicate, oversized or symbolic archive member')
            dst=site.joinpath(*PurePosixPath(rel).parts).resolve()
            if not dst.is_relative_to(site.resolve()):raise ValueError('Archive path escapes source')
            dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(z.read(i));seen.add(rel)
    if seen!=MEMBERS:raise ValueError('Inspected source is incomplete')

def contract(disabled_fr):
    pages={ORIGIN+'/about/':dict(key='about',locale='en',canonical_required=False),
           ORIGIN+'/info/':dict(key='info-alias',locale='en',state='redirect',redirect_to=ORIGIN+'/about/')}
    if not disabled_fr:pages[ORIGIN+'/fr/about/']=dict(key='about',locale='fr',canonical_required=False)
    return dict(schema=1,config=dict(origins={ORIGIN:'.'},locales=['en'] if disabled_fr else ['en','fr'],
                            aliases={},complete_manifest=False,check_links=False),pages=pages)

def alias_observation(text):
    parser=PageParser(ORIGIN+'/info/');parser.feed(text);parser.close()
    return parser.obs

def same_information_target_control(obs):
    """Ordinary comparison to the same predeclared English-alias destination."""
    return obs.get('redirect')!=ORIGIN+'/about/'

def run(hugo,archive,output):
    output=output.resolve();hugo=hugo.resolve(strict=True);archive=archive.resolve(strict=True)
    if not output.is_relative_to((ROOT/'results').resolve()) or output==(ROOT/'results').resolve():
        raise ValueError('Use a new artifact/results child directory')
    output.mkdir(parents=True,exist_ok=False)
    site=output/'source';site.mkdir();extract_inspected(archive,site)
    env={k:v for k,v in os.environ.items() if not k.startswith('HUGO_')}
    env['GOMAXPROCS']='1'
    version=subprocess.run([str(hugo),'version'],capture_output=True,text=True,encoding='utf-8',check=True,timeout=10).stdout.strip()
    if not version.startswith('hugo v0.147.9-'):raise ValueError('This study requires the declared0.147.9 executable')
    records=[];session=None;previous=None
    for index,disabled in enumerate((False,True,False,True)):
        current_env=dict(env)
        if disabled:current_env['HUGO_DISABLELANGUAGES']='fr'
        build=output/f'build-{index}'
        command=[str(hugo),'--source',str(site),'--destination',str(build),'--cacheDir',str(output/'cache'),'--noBuildLock']
        proc=subprocess.run(command,capture_output=True,text=True,encoding='utf-8',env=current_env,timeout=30)
        if proc.returncode:raise RuntimeError(proc.stderr)
        manifest=output/f'contract-{index}.json'
        manifest.write_text(json.dumps(contract(disabled),indent=2)+'\n',encoding='utf-8')
        facts=load_build(manifest,build);issues=evaluate(facts)
        if session is None:session=ReleaseSession(facts,engine_class=SlicedIncremental)
        else:session.apply({k:v for k,v in delta(previous,facts).items() if k[0]!='g'})
        if issues!=session.issues():raise AssertionError('Full and validated sliced findings disagree')
        alias=(build/'info/index.html').read_text(encoding='utf-8');obs=alias_observation(alias)
        control=same_information_target_control(obs)
        if control!=bool(issues):raise AssertionError('Equal-information control disagrees')
        # Reachability alone cannot distinguish these two permitted-language targets.
        target=obs.get('redirect');reachable=target in {k[1] for k in facts if k[0]=='o'}
        records.append(dict(index=index,disabled_fr=disabled,command=command,returncode=proc.returncode,
            stdout=proc.stdout,stderr=proc.stderr,observed_alias=obs,alias_target_reachable=reachable,
            findings=[i.json() for i in sorted(issues)],same_information_target_rejects=control,
            full_and_incremental_agree=True,html_files=sorted(p.relative_to(build).as_posix() for p in build.rglob('*.html'))))
        previous=facts
    summary=dict(source_issue=ISSUE_URL,source_archive_url=SOURCE_URL,source_identity=ARCHIVE_ID,
        native_version=version,reported_issue_version='0.154.5 macOS, not executed here',
        python=sys.version,platform=platform.platform(),hugo_executable_identity=hashlib.sha256(hugo.read_bytes()).hexdigest(),
        builds=len(records),rejected=sum(bool(r['findings']) for r in records),
        admitted=sum(not r['findings'] for r in records),same_information_decisions_agree=True,
        all_targets_reachable=all(r['alias_target_reachable'] for r in records),
        publication_policy='The retained English /info/ route must redirect to /about/ when French fallback is enabled or disabled.',
        scope='One independently supplied minimal native site; two paired toggles, not four independent defects, full Docsy, deployed impact, or a speedup. No output fault injected; native generated bytes were not edited.',
        records=records)
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--hugo',type=Path,required=True)
    parser.add_argument('--source-archive',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();r=run(a.hugo,a.source_archive,a.output)
    print(json.dumps({k:r[k] for k in ('builds','rejected','admitted','same_information_decisions_agree','all_targets_reachable')}))
