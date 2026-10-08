#!/usr/bin/env python3
"""Derive every quantitative paper value from raw result files.

Raw measurements are never edited here.  The named authored corpus, the four
separately implemented local emitter/adaptation families, synthetic scale runs, and the fan-out sweep
remain separate populations; the script does not pool their rates as field estimates.
"""
from __future__ import annotations
import argparse,collections,csv,json,statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PAPER=ROOT.parent/'paper'
RESULT=ROOT/'results'

def readcsv(name:str):
    with (RESULT/name).open(newline='',encoding='utf8') as f:
        return list(csv.DictReader(f))

def stat(values):
    values=sorted(values);q=statistics.quantiles(values,n=4,method='inclusive')
    return {'median':statistics.median(values),'q1':q[0],'q3':q[2],
            'min':values[0],'max':values[-1],'n':len(values)}

def ratio(a,b):
    return a/b if b else None

def score_rows(rows,methods):
    counts=collections.Counter(x['label'] for x in rows)
    defect_types={x['case'] for x in rows if x['label']=='defect'}
    result=[]
    for col,name in methods.items():
        tp=sum(int(x[col]) for x in rows if x['label']=='defect')
        fp=sum(int(x[col]) for x in rows if x['label']=='clean')
        detected_types={x['case'] for x in rows if x['label']=='defect' and int(x[col])}
        result.append({'key':col,'method':name,'tp':tp,'positives':counts['defect'],
            'fp':fp,'clean':counts['clean'],'precision':ratio(tp,tp+fp),
            'recall':ratio(tp,counts['defect']),'fpr':ratio(fp,counts['clean']),
            'type_tp':len(detected_types),'types':len(defect_types)})
    return result,counts

def tex_table(columns,headers,rows):
    lines=[r'\begin{tabular}{'+columns+'}',r'\toprule',' & '.join(headers)+r' \\',r'\midrule']
    lines += [' & '.join(map(str,row))+r' \\' for row in rows]
    return '\n'.join(lines+[r'\bottomrule',r'\end{tabular}',''])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plots',action='store_true');args=parser.parse_args()
    releases=readcsv('releases.csv');hold=readcsv('composition_holdout.csv');sites=readcsv('sites.csv')
    independent=readcsv('independent_releases.csv');independent_sites_raw=readcsv('independent_sites.csv')
    methods=collections.OrderedDict([
      ('full_detected','Full contract'),('incremental_detected','Incremental contract'),
      ('manifest_detected','Route/state only'),('deadlink_detected','Reachability only'),
      ('html_detected','HTML annotation only'),('joint_detected','Joint output only'),
      ('blind_detected','Strict policy-blind'),('no_identity_detected','Full without identity'),
      ('no_crosschannel_detected','Full without agreement')])
    independent_methods=collections.OrderedDict((k,v) for k,v in methods.items()
        if k in independent[0])
    scores,counts=score_rows(releases,methods)
    independent_scores,independent_counts=score_rows(independent,independent_methods)

    scale=[];memory=[]
    for n in [100,1000,10000]:
        for kind in ['local_canonical','deleted_page','global_alias_policy','hub_observation']:
            source=f'scale-{n}-{kind}.json';d=json.loads((RESULT/source).read_text());raw=d['rows']
            assert len(raw)==12 and all(x['agreement']==1 for x in raw)
            row={'routes':n,'kind':kind,'source':source}
            for metric in ['full_ns','update_ns','snapshot_diff_ns','invalidation_ns']:
                row[metric.replace('_ns','_ms')]=stat([x[metric]/1e6 for x in raw])
            row['diff_update_ms']=stat([(x['snapshot_diff_ns']+x['update_ns'])/1e6 for x in raw])
            row['paired_speedup_update_only']=stat([x['full_ns']/x['update_ns'] for x in raw])
            row['paired_speedup_with_diff']=stat([x['full_ns']/(x['update_ns']+x['snapshot_diff_ns']) for x in raw])
            row['invalidated_owners']=stat([x['invalidated_owners'] for x in raw])
            row['speedup_ratio_medians_update_only']=row['full_ms']['median']/row['update_ms']['median']
            row['speedup_ratio_medians_with_diff']=row['full_ms']['median']/row['diff_update_ms']['median']
            row['wall_s']=d['wall_s'];scale.append(row)
            if kind=='local_canonical':
                memory.append({'routes':n,'index_init_ms':d['index_init_ns']/1e6,
                  'index_live_mib':d['index_live_python_bytes']/2**20,
                  'index_peak_mib':d['index_peak_python_bytes']/2**20,
                  'process_maxrss_mib':d['maxrss_kib']/1024,
                  'edges':d['dependency_edges'],
                  'parse_ms':stat([x['parse_snapshot_ns']/1e6 for x in d['io']]),
                  'cold_check_ms':stat([(x['parse_snapshot_ns']+x['full_ns'])/1e6 for x in d['io']]),
                  'disk_bytes':d['disk_build_bytes']})

    grouped=[]
    for site in sites:
        sid=site['site'];rr=[x for x in releases if x['site']==sid];g=dict(site)
        for col in methods:
            g[col+'_tp']=sum(int(x[col]) for x in rr if x['label']=='defect')
            g[col+'_fp']=sum(int(x[col]) for x in rr if x['label']=='clean')
        g['drop_old_disagreements']=sum(x['drop_old_agreement']=='0' for x in rr);grouped.append(g)

    independent_grouped=[]
    for site in independent_sites_raw:
        sid=site['site'];rr=[x for x in independent if x['site']==sid];g=dict(site)
        for col in independent_methods:
            g[col+'_tp']=sum(int(x[col]) for x in rr if x['label']=='defect')
            g[col+'_fp']=sum(int(x[col]) for x in rr if x['label']=='clean')
        g['agreement']=sum(x['agreement']=='1' for x in rr)
        independent_grouped.append(g)

    fanout=json.loads((RESULT/'fanout-sweep-10000.json').read_text())
    assert fanout.get('complete') is True
    assert all(x['agreement']==1 for x in fanout['rows'])
    fan_summary=fanout['summary']
    first_total=fanout['first_measured_diff_plus_update_not_faster']
    first_update=fanout['first_measured_update_only_not_faster']
    def previous_point(first):
        vals=[x['declared_fanout'] for x in fan_summary]
        
        if first is None: return vals[-1]
        i=vals.index(first);return vals[i-1] if i else None

    result={
      'scope':'Laboratory evidence: six generator-derived configurations, three separate original emitters, and one pinned public-source front-matter adaptation; no native framework build, live-site observation, or industrial deployment.',
      'counts':dict(counts),'named_releases':len(releases),'composition_holdout':len(hold),
      'sites':grouped,'full_incremental_named_agreement':sum(x['agreement']=='1' for x in releases),
      'holdout_agreement':sum(x['agreement']=='1' for x in hold),
      'no_old_readers_disagreements':sum(x['drop_old_agreement']=='0' for x in releases),
      'scores':scores,
      'independent_counts':dict(independent_counts),'independent_releases':len(independent),
      'independent_sites':independent_grouped,
      'independent_full_incremental_agreement':sum(x['agreement']=='1' for x in independent),
      'independent_scores':independent_scores,
      'scale':scale,'memory':memory,
      'fanout_sweep':{'source':'fanout-sweep-10000.json','routes':fanout['routes'],
          'repeats':fanout['repeats'],'summary':fan_summary,
          'last_measured_diff_plus_update_faster':previous_point(first_total),
          'first_measured_diff_plus_update_not_faster':first_total,
          'last_measured_update_only_faster':previous_point(first_update),
          'first_measured_update_only_not_faster':first_update,
          'interpretation_limit':fanout['interpretation_limit']},
      'total_benchmark_wall_s':sum(x['wall_s'] for x in scale)+fanout['wall_s'],
      'execution_qualification':'Only complete benchmark and fan-out JSON files enter analysis. Completion of the current aggregate invocation is recorded separately in execution-status.json and run-full-stages.json.',
      'uncertainty':'Scale medians/IQRs use 12 alternating updates in one fresh process per size/class. Fan-out points use 12 alternating updates. They are repeated measurements, not independent site samples or confidence intervals.'}

    out=PAPER/'generated';out.mkdir(parents=True,exist_ok=True)
    def macro(key,value):return f'\\newcommand{{\\{key}}}{{{value}}}\n'
    local=next(x for x in scale if x['routes']==10000 and x['kind']=='local_canonical')
    global_row=next(x for x in scale if x['routes']==10000 and x['kind']=='global_alias_policy')
    hub=next(x for x in scale if x['routes']==10000 and x['kind']=='hub_observation')
    mem=memory[-1]
    sc={x['key']:x for x in scores};isc={x['key']:x for x in independent_scores}
    values={
      'NamedReleases':len(releases),'SeededDefects':counts['defect'],'CleanCases':counts['clean'],
      'AmbiguousCases':counts['ambiguity'],'HeldoutCases':len(hold),
      'IndependentReleases':len(independent),'IndependentDefects':independent_counts['defect'],
      'IndependentClean':independent_counts['clean'],'IndependentAmbiguous':independent_counts['ambiguity'],
      'IndependentRoutes':sum(int(x['routes']) for x in independent_sites_raw),
      'AllNamedReleases':len(releases)+len(independent),'AllCheckedTransitions':len(releases)+len(independent)+len(hold),
      'BaseRoutes':sum(int(x['routes']) for x in sites),'OldMiss':result['no_old_readers_disagreements'],
      'StrictMainFP':sc['blind_detected']['fp'],'StrictIndependentFP':isc['blind_detected']['fp'],
      'JointMainTP':sc['joint_detected']['tp'],'JointIndependentTP':isc['joint_detected']['tp'],
      'LocalFull':f"{local['full_ms']['median']:.2f}",
      'LocalIncremental':f"{local['update_ms']['median']:.3f}",
      'LocalDiff':f"{local['snapshot_diff_ms']['median']:.2f}",
      'LocalCombined':f"{local['diff_update_ms']['median']:.2f}",
      'LocalSpeed':f"{local['speedup_ratio_medians_with_diff']:.2f}",
      'GlobalCombined':f"{global_row['diff_update_ms']['median']:.2f}",
      'HubCombined':f"{hub['diff_update_ms']['median']:.2f}",
      'IndexMemory':f"{mem['index_live_mib']:.2f}",
      'ParseTenK':f"{mem['parse_ms']['median']/1000:.2f}",
      'FanoutTotalLastFast':previous_point(first_total),
      'FanoutTotalFirstSlow':first_total,
      'FanoutUpdateLastFast':previous_point(first_update),
      'FanoutUpdateFirstSlow':first_update,
      'FullBenchmarkWall':f"{result['total_benchmark_wall_s']:.1f}"}
    (out/'numbers.tex').write_text(''.join(macro(k,v) for k,v in values.items()))

    # Main authored corpus: selected complete controls and diagnostic ablations.
    selected=['full_detected','manifest_detected','deadlink_detected','html_detected',
              'joint_detected','blind_detected','no_identity_detected','no_crosschannel_detected']
    display={'full_detected':'Full contract','manifest_detected':'Route/state',
      'deadlink_detected':'Reachability','html_detected':'HTML only',
      'joint_detected':'Joint output','blind_detected':'Strict policy',
      'no_identity_detected':'No identity','no_crosschannel_detected':'No agreement'}
    compact=[]
    for key in selected:
        r=sc[key];compact.append([display[key],r['tp'],r['type_tp'],r['fp'],f"{r['recall']:.3f}"])
    (out/'detection-compact.tex').write_text(tex_table('lrrrr',
      ['Method','TP/96','Types/16','FP/60','Recall'],compact))

    # Kept for artifact readers who prefer precision/FPR details.
    detailed=[]
    for key in selected:
        r=sc[key];detailed.append([display[key],r['tp'],r['fp'],f"{r['precision']:.3f}",f"{r['recall']:.3f}",f"{r['fpr']:.3f}"])
    (out/'detection.tex').write_text(tex_table('lrrrrr',
      ['Method','TP/96','FP/60','Prec.','Recall','FPR'],detailed))

    fam_name={'JH':'JSON/HTML','TS':'TOML/sitemap','CH':'CSV/HTTP','PJ':'Polyglot adapt.'}
    rows=[]
    for r in independent_grouped:
        rows.append([fam_name[r['site']],r['routes'],r['channel'],
          f"{r['full_detected_tp']}/5",f"{r['joint_detected_tp']}/5",f"{r['blind_detected_fp']}/3"])
    (out/'independent-compact.tex').write_text(tex_table('lrlrrr',
      ['Source family','Routes','Channel','Full','Joint','Strict FP'],rows))

    rows=[]
    for r in grouped:
        rows.append([r['site'],r['routes'],r['full_detected_tp'],r['deadlink_detected_tp'],
                     r['joint_detected_tp'],r['blind_detected_fp']])
    (out/'per-site-compact.tex').write_text(tex_table('lrrrrr',
      ['Config.','Routes','Full','Reach','Joint','FP'],rows))

    names={'local_canonical':'Local canonical','deleted_page':'Page deletion',
      'global_alias_policy':'Global policy','hub_observation':'Hub observation'}
    rows=[]
    for r in scale:
        rows.append([f"{r['routes']:,}",names[r['kind']],f"{r['full_ms']['median']:.2f}",
          f"{r['update_ms']['median']:.3f}",f"{r['snapshot_diff_ms']['median']:.2f}",
          f"{r['diff_update_ms']['median']:.2f}",f"{int(r['invalidated_owners']['median']):,}"])
    (out/'timing.tex').write_text(tex_table('llrrrrr',
      ['Routes','Update','Full','Inc.','Diff','Diff+Inc.','Invalid.'],rows))

    rows=[[f"{r['routes']:,}",f"{r['index_live_mib']:.2f}",f"{r['edges']:,}",
           f"{r['index_init_ms']:.2f}",f"{r['parse_ms']['median']:.2f}"] for r in memory]
    (out/'memory-compact.tex').write_text(tex_table('rrrrr',
      ['Routes','Index (MiB)','Edges','Init. (ms)','Parse (ms)'],rows))

    selected_fan={0,512,2048,3072,6144,9999}
    rows=[]
    for r in fan_summary:
        if r['declared_fanout'] in selected_fan:
            rows.append([f"{int(r['invalidated_owners']['median']):,}",
              f"{r['full_ms']['median']:.2f}",f"{r['update_ms']['median']:.2f}",
              f"{r['diff_update_ms']['median']:.2f}",f"{r['with_diff_ratio']:.2f}"])
    (out/'fanout-compact.tex').write_text(tex_table('rrrrr',
      ['Invalidated','Full','Inc.','Diff+Inc.','Full/(D+I)'],rows))

    # Human-readable case matrix from raw rows, not hand-entered counts.
    lines=['# Measured case matrix','',
      'All cells describe authored cases, not upstream or production failures.','',
      '| Change | Label | Full | Route/state | Reach | HTML | Joint | Strict | Old-reader disagreement |',
      '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for case in dict.fromkeys(x['case'] for x in releases):
        rr=[x for x in releases if x['case']==case]
        cells=[str(sum(int(x[c]) for x in rr))+'/6' for c in
          ['full_detected','manifest_detected','deadlink_detected','html_detected','joint_detected','blind_detected']]
        lines.append('| '+case+' | '+rr[0]['label']+' | '+' | '.join(cells)+' | '+
          str(sum(x['drop_old_agreement']=='0' for x in rr))+'/6 |')
    (ROOT/'docs'/'case-matrix.md').write_text('\n'.join(lines)+'\n')

    # Denominator and agreement checks fail loudly before any paper value is accepted.
    assert len(releases)==174 and len(hold)==96 and len(independent)==40
    assert counts==collections.Counter({'defect':96,'clean':60,'ambiguity':18})
    assert independent_counts==collections.Counter({'defect':20,'clean':12,'ambiguity':8})
    assert result['full_incremental_named_agreement']==174
    assert result['independent_full_incremental_agreement']==40
    assert result['holdout_agreement']==96
    assert sc['full_detected']['tp']==96 and sc['full_detected']['fp']==0
    assert isc['full_detected']['tp']==20 and isc['full_detected']['fp']==0
    # Crossover locations are measurements, not hard-coded expected outputs.

    if args.plots:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        xs=[100,1000,10000]
        localrows=[next(x for x in scale if x['routes']==n and x['kind']=='local_canonical') for n in xs]
        fig,ax=plt.subplots(figsize=(3.35,2.35))
        for metric,label,marker in [('full_ms','Full check','o'),('update_ms','Incremental update only','s'),('diff_update_ms','Difference + update','^')]:
            ax.plot(xs,[x[metric]['median'] for x in localrows],marker=marker,label=label)
        ax.set_xscale('log');ax.set_yscale('log');ax.set_xticks(xs,labels=['100','1,000','10,000'])
        ax.set_xlabel('Emitted routes');ax.set_ylabel('Median time (ms)');ax.legend(fontsize=7,loc='upper left')
        ax.tick_params(labelsize=8);fig.tight_layout(pad=.6)
        fig.savefig(PAPER/'figures'/'local-cost.pdf');fig.savefig(PAPER/'figures'/'local-cost.png',dpi=180);plt.close(fig)

        rs=[x for x in scale if x['routes']==10000];fig,ax=plt.subplots(figsize=(3.35,2.2))
        xx=list(range(4));ax.bar([a-.17 for a in xx],[r['full_ms']['median'] for r in rs],width=.34,label='Full check')
        ax.bar([a+.17 for a in xx],[r['diff_update_ms']['median'] for r in rs],width=.34,label='Difference + update')
        ax.set_xticks(xx,labels=['Local','Deletion','Global','Hub']);ax.set_ylabel('Median time (ms)')
        ax.legend(fontsize=7);ax.tick_params(labelsize=8);fig.tight_layout(pad=.6)
        fig.savefig(PAPER/'figures'/'fanout-cost.pdf');fig.savefig(PAPER/'figures'/'fanout-cost.png',dpi=180);plt.close(fig)

        fig,ax=plt.subplots(figsize=(3.35,2.35))
        x=[r['invalidated_owners']['median'] for r in fan_summary]
        ax.plot(x,[r['full_ms']['median'] for r in fan_summary],marker='o',label='Full check')
        ax.plot(x,[r['update_ms']['median'] for r in fan_summary],marker='s',label='Incremental update')
        ax.plot(x,[r['diff_update_ms']['median'] for r in fan_summary],marker='^',label='Difference + update')
        ax.set_xscale('log');ax.set_yscale('log');ax.set_xlabel('Invalidated owners (10,000 routes)')
        ax.set_ylabel('Median time (ms)');ax.axvline((first_total or 9999)+1,linestyle='--',linewidth=.8)
        ax.text((first_total or 9999)+1,ax.get_ylim()[0]*1.35,'first measured\ncombined slowdown',fontsize=6.5,ha='center')
        ax.legend(fontsize=6.7,loc='upper left');ax.tick_params(labelsize=8);fig.tight_layout(pad=.55)
        fig.savefig(PAPER/'figures'/'fanout-sweep.pdf');fig.savefig(PAPER/'figures'/'fanout-sweep.png',dpi=180);plt.close(fig)
        result['matplotlib_version']=matplotlib.__version__

    (RESULT/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'main_counts':dict(counts),'independent_counts':dict(independent_counts),
      'holdout':len(hold),'fanout_crossings':{'combined':first_total,'update_only':first_update},
      'benchmark_wall_s':result['total_benchmark_wall_s'],'headline':values},indent=2))

if __name__=='__main__':main()
