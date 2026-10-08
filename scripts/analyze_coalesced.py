#!/usr/bin/env python3
"""Recompute lossless-footprint tables and figures from paired raw observations."""
from pathlib import Path
import argparse,json,statistics
ROOT=Path(__file__).resolve().parents[1];R=ROOT/'results';P=ROOT.parent/'paper'
KINDS=['local_canonical','deleted_page','unused_alias','global_link_policy','hub_canonical','hub_status']
NAMES=dict(zip(KINDS,['Local canonical','Page deletion','Unused alias','Global link policy','Hub canonical','Hub status']))
def stats(v):
    v=sorted(v);q=statistics.quantiles(v,n=4,method='inclusive')
    return dict(median=statistics.median(v),q1=q[0],q3=q[2],min=v[0],max=v[-1],n=len(v))
def tab(cols,heads,rows):
    return '\n'.join([r'\begin{tabular}{'+cols+'}',r'\toprule',' & '.join(heads)+r' \\',r'\midrule']+[' & '.join(map(str,x))+r' \\' for x in rows]+[r'\bottomrule',r'\end{tabular}',''])
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--plots',action='store_true');args=ap.parse_args();summary=[];memory=[]
    for n in (100,1000,10000):
        raw=json.loads((R/f'coalesced-{n}.json').read_text());assert len(raw['rows'])==72
        assert all(x['agreement'] and x['projected_owners']==x['coalesced_owners'] and x['expanded_edges_projected']==x['expanded_edges_coalesced'] for x in raw['rows'])
        memory.append({'routes':n,**raw['memory']})
        for kind in KINDS:
            rows=[x for x in raw['rows'] if x['kind']==kind];assert len(rows)==12
            s={'routes':n,'kind':kind,'source':f'coalesced-{n}.json'}
            for key in ('full','projected','coalesced','safe_projected','safe_coalesced','snapshot_diff'):
                s[key+'_ms']=stats([x[key+'_ns']/1e6 for x in rows])
            s['combined_ms']=stats([(x['snapshot_diff_ns']+x['safe_coalesced_ns'])/1e6 for x in rows])
            s['paired_full_over_combined']=stats([x['full_ns']/(x['snapshot_diff_ns']+x['safe_coalesced_ns']) for x in rows])
            s['paired_P_over_C']=stats([x['safe_projected_ns']/x['safe_coalesced_ns'] for x in rows])
            s['ratio_of_medians']=s['full_ms']['median']/s['combined_ms']['median']
            s['owners']=stats([x['coalesced_owners'] for x in rows]);summary.append(s)
    rs={x['kind']:x for x in summary if x['routes']==10000};out=P/'generated';out.mkdir(exist_ok=True)
    numbers={'CoalescedUpdates':sum(s['full_ms']['n'] for s in summary)}
    for kind,prefix in [('local_canonical','CLocal'),('hub_canonical','CHub'),('hub_status','CStatus'),('global_link_policy','CGlobal'),('unused_alias','CAlias')]:
        row=rs[kind]
        for metric,suffix in [('full_ms','Full'),('safe_projected_ms','Projected'),('safe_coalesced_ms','Safe'),('snapshot_diff_ms','Diff'),('combined_ms','Combined')]:
            numbers[prefix+suffix]=f"{row[metric]['median']:.3f}" if metric.startswith('safe') else f"{row[metric]['median']:.2f}"
        numbers[prefix+'Ratio']=f"{row['ratio_of_medians']:.2f}"
        numbers[prefix+'PairedRatio']=f"{row['paired_full_over_combined']['median']:.2f}"
    for key,prefix in [('record','CMRecord'),('projected','CMProjected'),('coalesced','CMCoalesced')]:
        m=memory[-1][key];numbers[prefix+'MiB']=f"{m['live_python_bytes']/2**20:.2f}";numbers[prefix+'Edges']=f"{m['dependency_edges']:,}"
    numbers['CMReduction']=f"{100*(1-memory[-1]['coalesced']['live_python_bytes']/memory[-1]['projected']['live_python_bytes']):.2f}"
    numbers['CMExpanded']=f"{memory[-1]['coalesced']['logical_projection_edges']:,}"
    numbers['CMFootprints']=f"{memory[-1]['coalesced']['interned_footprints']:,}"
    browser=json.loads((R/'browser-differential.json').read_text());contract=json.loads((R/'contract-boundary.json').read_text())
    # Counts in the raw evidence files are audited separately, not inferred from captions.
    (out/'coalesced-numbers.tex').write_text(''.join(f'\\newcommand{{\\{k}}}{{{v}}}\n' for k,v in numbers.items()))
    timing=[];dispersion=[]
    for k in KINDS:
        s=rs[k]
        timing.append([NAMES[k],f"{s['full_ms']['median']:.2f}",f"{s['safe_projected_ms']['median']:.3f}",f"{s['safe_coalesced_ms']['median']:.3f}",f"{s['combined_ms']['median']:.2f}",f"{s['ratio_of_medians']:.2f}",f"{int(s['owners']['median']):,}"])
        q=s['paired_full_over_combined'];a=s['safe_coalesced_ms']
        dispersion.append([NAMES[k],f"{a['q1']:.2f}--{a['q3']:.2f}",f"{q['median']:.2f}",f"{q['q1']:.2f}--{q['q3']:.2f}"])
    (out/'coalesced-times.tex').write_text(tab('lrrrrrr',['Change','Full','P API','C API','Diff + C','Full / (diff + C)','Owners P = C'],timing))
    (out/'coalesced-dispersion.tex').write_text(tab('lrrr',['Change','C API IQR (ms)','Ratio','Ratio IQR'],dispersion))
    memrows=[]
    for key,label in [('record','Record (R)'),('projected','Field (P)'),('coalesced','Coalesced (C)')]:
        x=memory[-1][key];memrows.append([label,f"{x['dependency_edges']:,}",f"{x['live_python_bytes']/2**20:.2f}"])
    (out/'coalesced-memory.tex').write_text(tab('lrr',['Owned cache','Stored owner edges','Live MiB'],memrows))
    result={'matched':summary,'memory':memory,'numbers':numbers,
      'uncertainty':'12 alternating paired updates per kind/size; rotating core and safe-engine order; median and inclusive IQR in one process, not independent-site estimates.',
      'memory_scope':'Separate tracemalloc measurements including owned fact copies and cache; existing input excluded. Neither process RSS nor browser memory.',
      'measurement_scope':'Complete normalized snapshot difference plus validated cache transaction. Page parsing, native builders and event acquisition excluded.'}
    (R/'coalesced-summary.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Coalesced field reads: measured results','',result['measurement_scope'],'',
      '| Change | Full ms | P API ms | C API ms | Diff + C ms | Full / combined | Owners P=C |',
      '|---|---:|---:|---:|---:|---:|---:|']+['| '+' | '.join(x)+' |' for x in timing]
    lines+=['',result['uncertainty'],'',result['memory_scope'],'']+[' / '.join(x) for x in memrows]
    lines+=['',f"C retains {numbers['CMExpanded']} expanded field reads in {numbers['CMCoalescedEdges']} owner/fact edges and {numbers['CMFootprints']} interned footprints.",
      f"Live allocation reduction relative to P: {numbers['CMReduction']}%. No constant-space claim.",
      'The unused-alias update is a negative result for C versus P; both broad-update cases remain slower than full checking. No automatic switching is implemented.']
    (ROOT/'docs'/'COALESCED-RESULTS.md').write_text('\n'.join(lines)+'\n')
    if args.plots:
        import matplotlib;matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        for kind,filename in [('hub_canonical','coalesced-hub'),('hub_status','coalesced-status')]:
            rr=[next(x for x in summary if x['routes']==n and x['kind']==kind) for n in (100,1000,10000)]
            fig,ax=plt.subplots(figsize=(3.30,2.60))
            for metric,label,marker in [('full_ms','Full','o'),('safe_projected_ms','P API','s'),('safe_coalesced_ms','C API','^'),('combined_ms','Difference + C','D')]:
                y=[x[metric]['median'] for x in rr];lo=[x[metric]['median']-x[metric]['q1'] for x in rr];hi=[x[metric]['q3']-x[metric]['median'] for x in rr]
                ax.errorbar([100,1000,10000],y,yerr=[lo,hi],marker=marker,markersize=4,label=label,capsize=2,linewidth=1)
            ax.set_xscale('log');ax.set_yscale('log');ax.set_xticks([100,1000,10000],labels=['100','1,000','10,000'])
            ax.set_xlabel('Emitted routes',fontsize=9);ax.set_ylabel('Time (ms), median and IQR',fontsize=9);ax.tick_params(labelsize=8)
            ax.legend(fontsize=7.5,loc='lower center',bbox_to_anchor=(.5,1.01),ncol=2,frameon=False,columnspacing=1.2)
            fig.tight_layout(pad=.7)
            fig.savefig(P/'figures'/f'{filename}.pdf');fig.savefig(P/'figures'/f'{filename}.png',dpi=200);plt.close(fig)
    print(json.dumps(numbers,indent=2))
if __name__=='__main__':main()
