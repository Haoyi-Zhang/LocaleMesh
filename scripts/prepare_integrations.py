#!/usr/bin/env python3
"""Create authored source kits, not framework outputs. Does not invoke a builder."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[1]/'integrations'
def put(path,text):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf8')
def js(path,data):put(path,json.dumps(data,indent=2)+'\n')
def common(name,origin,prefix):
    root=ROOT/name;locales=['en','de'];pages=[];contract={}
    for key in ['intro','guide']:
        pairs={l:origin+('/'+l if prefix or l!='en' else '')+'/'+key+'/' for l in locales}
        for l,url in pairs.items():
            path=url[len(origin):].strip('/')
            pages.append({'key':key,'locale':l,'path':path,'url':url,'alternates':pairs,'title':key.title()+' ('+l+')','body':'Authored source kit. No industrial release claim.'})
            contract[url]={'key':key,'locale':l,'state':'published','canonical_allowed':[url],
                'canonical_channels':['html'],'sitemap':False,'discovery':{'html':{'required':locales,'reciprocal':True}}}
    js(root/'publication.json',{'pages':pages})
    js(root/'manifest.json',{'schema':1,'source_kind':'authored-unbuilt-integration','config':{'origins':{origin:'.'},'locales':locales,'aliases':{},'complete_manifest':False,'check_links':True},'pages':contract})
    return root,pages
r,p=common('astro','https://astro.localemesh.test',False)
js(r/'package.json',{'name':'localemesh-astro-source-kit','private':True,'version':'0.0.0','type':'module','scripts':{'build':'astro build'},'dependencies':{'astro':'5.13.2'}})
put(r/'astro.config.mjs',"""import {defineConfig} from 'astro/config';
export default defineConfig({site:'https://astro.localemesh.test', output:'static',
  i18n:{defaultLocale:'en',locales:['en','de'],routing:{prefixDefaultLocale:false}}});
""")
put(r/'src/pages/[...path].astro',"""---
import publication from '../../publication.json';
export function getStaticPaths() {
  return publication.pages.map(page => ({params:{path:page.path},props:{page}}));
}
const {page}=Astro.props;
---
<!doctype html><html lang={page.locale}><head><meta charset="utf-8" />
<title>{page.title}</title><link rel="canonical" href={page.url} />
{Object.entries(page.alternates).map(([locale,url]) => <link rel="alternate" hreflang={locale} href={url} />)}
</head><body><main data-content-key={page.key}><h1>{page.title}</h1><p>{page.body}</p></main></body></html>
""")
# Correct import location: src/pages -> project root is ../..; file is at that root.
# JSON name above uses ../../ which resolves from src/pages to root.
r,p=common('hugo','https://hugo.localemesh.test',False)
put(r/'hugo.toml',"""baseURL = 'https://hugo.localemesh.test/'
defaultContentLanguage = 'en'
defaultContentLanguageInSubdir = false
disableKinds = ['taxonomy', 'term', 'RSS']
[languages.en]
languageCode = 'en'
contentDir = 'content/en'
weight = 1
[languages.de]
languageCode = 'de'
contentDir = 'content/de'
weight = 2
""")
put(r/'VERSION','0.147.9\n')
put(r/'layouts/_default/single.html',"""<!doctype html><html lang="{{ .Language.Lang }}"><head><meta charset="utf-8">
<title>{{ .Title }}</title><link rel="canonical" href="{{ .Permalink }}">
{{ range .AllTranslations }}<link rel="alternate" hreflang="{{ .Language.Lang }}" href="{{ .Permalink }}">{{ end }}
</head><body><main data-content-key="{{ .Params.content_key }}"><h1>{{ .Title }}</h1>{{ .Content }}</main></body></html>
""")
put(r/'layouts/_default/list.html',"""<!doctype html><html lang="{{ .Language.Lang }}"><head><meta charset="utf-8"><title>Index</title></head><body>{{ range .Pages }}<a href="{{ .RelPermalink }}">{{ .Title }}</a>{{ end }}</body></html>
""")
for page in p:
    put(r/f"content/{page['locale']}/{page['key']}.md",f"+++\ntitle = '{page['title']}'\ntranslationKey = '{page['key']}'\ncontent_key = '{page['key']}'\n+++\n\n{page['body']}\n")
r,p=common('nextjs','https://next.localemesh.test',True)
js(r/'package.json',{'name':'localemesh-nextjs-source-kit','private':True,'version':'0.0.0','scripts':{'build':'next build'},'dependencies':{'next':'15.5.9','react':'19.1.0','react-dom':'19.1.0'}})
put(r/'next.config.mjs',"""/** Offline-only static export source kit, not a production-security recommendation. */
export default {output:'export',trailingSlash:true,experimental:{cpus:2}};
""")
put(r/'app/[locale]/layout.js',"""export default async function LocaleLayout({children,params}) {
  const {locale}=await params;
  return <html lang={locale}><body>{children}</body></html>;
}
""")
put(r/'app/[locale]/[slug]/page.js',"""import publication from '../../../publication.json';
export const dynamicParams=false;
export function generateStaticParams(){return publication.pages.map(p=>({locale:p.locale,slug:p.key}));}
function findPage(locale,slug){const p=publication.pages.find(p=>p.locale===locale && p.key===slug);if(!p)throw new Error('Unknown content');return p;}
export async function generateMetadata({params}){const {locale,slug}=await params;const p=findPage(locale,slug);return {title:p.title,alternates:{canonical:p.url,languages:p.alternates}};}
export default async function Page({params}){const {locale,slug}=await params;const p=findPage(locale,slug);return <main data-content-key={p.key}><h1>{p.title}</h1><p>{p.body}</p></main>;}
""")
for name in ['astro','hugo','nextjs']:
    put(ROOT/name/'STATUS.md',f"# {name}: authored source kit, NOT BUILT\n\nPinned top-level versions were selected from primary release/documentation sources.\nThese files are not independently sourced public sites. No successful native build\nor deployment has been measured in this environment. A failed dependency probe is\nin `../../results/integration-probes.json`. Do not treat source presence as integration success.\n\nManifest and publication files are stored separately but were initially authored\ntogether; this is not independent editorial ground truth. No lockfile was fabricated.\nAfter a successful install, preserve the generated lockfile and record resolved versions.\n\nRun from artifact/: `python scripts/build_integration.py {name}`.\nOpt-in dependency installation: append `--allow-install`. It downloads public build\ndependencies only; the checker never fetches production sites. Do not deploy these pins\nwithout a new current security review.\n")
print('Created three authored source kits; native execution NOT performed.')
