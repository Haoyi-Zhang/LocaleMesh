#!/usr/bin/env python3
"""Derive revision tables, macros, and vector plots from unedited raw measurements."""
from __future__ import annotations
import argparse, collections, csv, json, re, statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/'results'; P=ROOT.parent/'paper'
KINDS=['local_canonical','deleted_page','unused_alias','global_link_policy','hub_canonical','hub_status']
NAMES={'local_canonical':'Local canonical','deleted_page':'Page deletion','unused_alias':'Unused alias',
       'global_link_policy':'Global link policy','hub_canonical':'Hub canonical','hub_status':'Hub status'}
def stats(v):
    v=sorted(v); q=statistics.quantiles(v,n=4,method='inclusive')
    return dict(median=statistics.median(v),q1=q[0],q3=q[2],min=v[0],max=v[-1],n=len(v))
def table(cols,headers,rows):
    return '\n'.join([r'\begin{tabular}{'+cols+'}',r'\toprule',' & '.join(headers)+r' \\',r'\midrule']+
        [' & '.join(map(str,x))+r' \\' for x in rows]+[r'\bottomrule',r'\end{tabular}',''])
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--plots',action='store_true');args=ap.parse_args()
    summary=[];mem=[]
    for n in (100,1000,10000):
        d=json.loads((R/f'projected-{n}.json').read_text())
        assert len(d['rows'])==72 and all(x['agreement'] for x in d['rows'])
        for kind in KINDS:
            rr=[x for x in d['rows'] if x['kind']==kind];assert len(rr)==12
            row={'routes':n,'kind':kind,'source':f'projected-{n}.json'}
            for metric in ('full_ns','record_ns','projected_ns','safe_projected_ns','snapshot_diff_ns'):
                row[metric.replace('_ns','_ms')]=stats([x[metric]/1e6 for x in rr])
            row['combined_ms']=stats([(x['snapshot_diff_ns']+x['safe_projected_ns'])/1e6 for x in rr])
            row['paired_full_over_combined']=stats([x['full_ns']/(x['snapshot_diff_ns']+x['safe_projected_ns']) for x in rr])
            row['ratio_medians_combined']=row['full_ms']['median']/row['combined_ms']['median']
            for metric in ('record_owners','projected_owners','compared_projections','changed_projections'):
                row[metric]=stats([x[metric] for x in rr])
            summary.append(row)
        mem.append({'routes':n,**d['memory']})
    external=json.loads((R/'external-page-summary.json').read_text())
    pandoc=json.loads((R/'pandoc-run.json').read_text())
    ingestion=json.loads((R/'ingestion-replay.json').read_text())
    pcounts=collections.Counter(x['label'] for x in pandoc['rows'])
    assert all(x['compiler_exit_zero'] and x['agreement'] for x in pandoc['rows'])
    assert all(x['returncode']==0 for x in pandoc['commands'])
    assert pcounts=={'clean':4,'defect':6,'ambiguity':1}
    old=json.loads((R/'summary.json').read_text())
    tests=int(re.search(r'Ran (\d+) tests',(R/'tests.log').read_text()).group(1))
    out=P/'generated';out.mkdir(exist_ok=True)
    rs={x['kind']:x for x in summary if x['routes']==10000}
    numbers={'TestMethods':tests,'PandocReleases':len(pandoc['rows']),'PandocCalls':pandoc['native_compile_calls'],
      'PandocSources':pandoc['source_files'],'ProjectionUpdates':sum(x['full_ms']['n'] for x in summary),
      'ReleaseSnapshots':174+40+96+len(pandoc['rows']),
      'ExternalPages':external['page_invocations'],'ExternalFetches':external['local_response_requests'],
      'IngestionCases':len(ingestion['regressions']),
      'PandocBuildMin':f"{min(x['native_pipeline_ns'] for x in pandoc['rows'])/1e6:.1f}",
      'PandocBuildMax':f"{max(x['native_pipeline_ns'] for x in pandoc['rows'])/1e6:.1f}",
      'PandocParseMedian':f"{statistics.median(x['parse_ns'] for x in pandoc['rows'])/1e6:.2f}",
      'PandocCheckMedian':f"{statistics.median(x['full_ns'] for x in pandoc['rows'])/1e6:.3f}"}
    # Owned caches include their copied facts; separate from earlier index-only reports.
    for kind,prefix in [('local_canonical','PLocal'),('hub_canonical','PHub'),('hub_status','PStatus'),('global_link_policy','PGlobal'),('unused_alias','PAlias')]:
        row=rs[kind]
        for metric,suffix in [('full_ms','Full'),('record_ms','Record'),('projected_ms','Core'),('safe_projected_ms','Safe'),('snapshot_diff_ms','Diff'),('combined_ms','Combined')]:
            numbers[prefix+suffix]=f"{row[metric]['median']:.3f}" if metric in ('record_ms','projected_ms','safe_projected_ms') else f"{row[metric]['median']:.2f}"
        numbers[prefix+'Ratio']=f"{row['ratio_medians_combined']:.2f}"
    print('MEMORY KEYS',mem[-1])
    for key,prefix in [('record','Record'),('projected','Projected')]:
        numbers[prefix+'OwnedMiB']=f"{mem[-1][key]['live_python_bytes']/2**20:.2f}"
        numbers[prefix+'Edges']=f"{mem[-1][key]['dependency_edges']:,}"
    (out/'revision-numbers.tex').write_text(''.join(f'\\newcommand{{\\{k}}}{{{v}}}\n' for k,v in numbers.items()))
    timingrows=[]
    for k in KINDS:
        r=rs[k]
        timingrows.append([NAMES[k],f"{r['full_ms']['median']:.2f}",f"{r['record_ms']['median']:.3f}",
            f"{r['safe_projected_ms']['median']:.3f}",f"{r['combined_ms']['median']:.2f}",f"{r['ratio_medians_combined']:.2f}",
            f"{int(r['record_owners']['median']):,} / {int(r['projected_owners']['median']):,}"])
    (out/'projected-times.tex').write_text(table('lrrrrrl',['Change','Full','Record','Projected API','Diff + API','Full / combined','Owners R / P'],timingrows))
    spread=[]
    for k in ('local_canonical','hub_canonical','hub_status','global_link_policy'):
        r=rs[k];q=r['paired_full_over_combined'];a=r['safe_projected_ms']
        spread.append([NAMES[k],f"{a['q1']:.2f}--{a['q3']:.2f}",f"{q['median']:.2f}",f"{q['q1']:.2f}--{q['q3']:.2f}"])
    (out/'projected-dispersion.tex').write_text(table('lrrr',['Change','API IQR (ms)','Ratio','Ratio IQR'],spread))
    extrows=[['Shared stale targets','15','15','15']]
    for k,caption in [('coherent_identity_swap','Coherent identity swap'),('cross_locale_canonical_allowed','Allowed cross-locale canonical'),('partial_coverage','Partial coverage'),('missing_translation_allowed','Missing translation allowed'),('optional_xdefault','Optional x-default'),('no_optional_channels','Optional channels absent')]:
        a=external['contrasts'][k];extrows.append([caption,a['releases'],a['upstream_errors'],a['localemesh_errors']])
    (out/'external-contrast.tex').write_text(table('lrrr',['Case family','Cases','API','Contract'],extrows))
    pr=[]
    for x in pandoc['rows']:
        pr.append([x['case'].replace('_',' '),x['routes'],f"{x['native_pipeline_ns']/1e6:.1f}",
            f"{(x['parse_ns']+x['full_ns'])/1e6:.2f}",x['label']])
    (out/'pandoc-times.tex').write_text(table('lrrrl',['Release','Pages','Build ms','Gate ms','Expected'],pr))
    compact=[]
    for r in old['scores']:
        if r['key']=='incremental_detected':continue
        compact.append([r['method'],f"{r['tp']}/{r['positives']}",f"{r['fp']}/{r['clean']}"])
    (out/'scope-contrast.tex').write_text(table('lrr',['Authored control','Defects detected','Clean rejected'],compact))
    result={'projected':summary,'owned_memory':mem,'external':external,'pandoc_counts':dict(pcounts),
      'pandoc_writer_invocations':pandoc['native_compile_calls'],'numbers':numbers,
      'uncertainty':'12 paired alternating measurements per size/change in one process; IQR and range, not independent-process confidence intervals.',
      'scope':'Authored laboratory releases, one actual Pandoc pipeline over the same PJ public sources, and an executed dependency-pruned upstream page API. No deployment or native i18n-framework result.'}
    (R/'revision-summary.json').write_text(json.dumps(result,indent=2)+'\n')
    # Human-readable result guide; links inside archive are relative.
    lines=['# Measured revision results','',result['scope'],'','## 10,000-route matched timings (ms)','',
      '| Change | Full | Record | Validated projected API | Full diff + API | Full/combined | Owners record/projected |',
      '|---|---:|---:|---:|---:|---:|---|']
    lines += ['| '+' | '.join(row)+' |' for row in timingrows]
    lines += ['',result['uncertainty'],'','Memory is the owned live Python allocation measured by tracemalloc, including fact copies; not process RSS.',
      f"Record: {numbers['RecordOwnedMiB']} MiB / {numbers['RecordEdges']} edges. Projected: {numbers['ProjectedOwnedMiB']} MiB / {numbers['ProjectedEdges']} edges.",
      '',f"Pandoc {pandoc['version']}: {len(pandoc['rows'])} releases, {pandoc['native_compile_calls']} successful native writer invocations; no native Jekyll build.",
      '',f"External page API: {external['page_invocations']} local page calls; {external['local_response_requests']} fixture requests; zero external requests.",
      'Only upstream severity=error is a rejection. Unsupported obligations are not counted as shared misses.',
      '',f"Ingestion: {len(ingestion['regressions'])} legacy-implementation failures replayed; current expectations pass. This is a same-project regression, not an upstream historical bug."]
    (ROOT/'docs'/'MEASURED-RESULTS.md').write_text('\n'.join(lines)+'\n')
    if args.plots:
        import matplotlib;matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        # Each figure is a separate plot, exported as a vector PDF.
        for kind,filename in [('hub_canonical','projected-hub'),('hub_status','projected-status')]:
            rr=[next(x for x in summary if x['routes']==n and x['kind']==kind) for n in (100,1000,10000)]
            fig,ax=plt.subplots(figsize=(3.30,2.36))
            for metric,label,marker in [('full_ms','Full','o'),('record_ms','Record cache','s'),('safe_projected_ms','Projected API','^'),('combined_ms','Full difference + API','D')]:
                y=[x[metric]['median'] for x in rr];lo=[x[metric]['median']-x[metric]['q1'] for x in rr];hi=[x[metric]['q3']-x[metric]['median'] for x in rr]
                ax.errorbar([100,1000,10000],y,yerr=[lo,hi],marker=marker,label=label,capsize=2,linewidth=1)
            ax.set_xscale('log');ax.set_yscale('log');ax.set_xticks([100,1000,10000],labels=['100','1,000','10,000'])
            ax.set_xlabel('Emitted routes',fontsize=9);ax.set_ylabel('Time (ms), median and IQR',fontsize=9)
            ax.tick_params(labelsize=8);ax.legend(fontsize=7,loc='best');fig.tight_layout(pad=.65)
            fig.savefig(P/'figures'/f'{filename}.pdf');fig.savefig(P/'figures'/f'{filename}.png',dpi=180);plt.close(fig)
    print(json.dumps(numbers,indent=2))
if __name__=='__main__':main()
