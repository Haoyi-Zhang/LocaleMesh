"""Optional offline DOM extraction using an actual Chromium HTML parser.

Input strings enter inert DOMParser documents; no input script is evaluated and
no document is navigated to a publication URL. CDP blocks all resource requests.
This adapter shares LocaleMesh's URL normalizer, not its HTML tokenizer/tree.
It selects static HTML-namespace metadata, excludes template contents and marks
noscript-dependent declarations ambiguous (scripting mode is not inferred).
"""
from __future__ import annotations
import json, os, shutil, subprocess, tempfile, time, urllib.request
from pathlib import Path
from urllib.parse import urlsplit
from .model import url

EXTRACT_JS = r'''(texts) => texts.map(text => {
 const d = new DOMParser().parseFromString(text, 'text/html');
 const htmlNS='http://www.w3.org/1999/xhtml';
 const selected = node => node.namespaceURI===htmlNS && !node.closest('noscript');
 const attrs = node => Object.fromEntries(Array.from(node.attributes).map(x=>[x.name,x.value]));
 return {
  lang:d.documentElement.getAttribute('lang')||'',
  markers:Array.from(d.querySelectorAll('[data-content-key]')).filter(selected).map(n=>n.getAttribute('data-content-key')),
  bases:Array.from(d.querySelectorAll('base[href]')).filter(selected).map(n=>n.getAttribute('href')),
  links:Array.from(d.head.querySelectorAll('link')).filter(selected).map(attrs),
  anchors:Array.from(d.querySelectorAll('a[href]')).filter(selected).map(n=>n.getAttribute('href')),
  refresh:Array.from(d.head.querySelectorAll('meta')).filter(selected).map(attrs).filter(a=>(a['http-equiv']||'').toLowerCase()==='refresh'),
  has_noscript:!!d.querySelector('noscript'),
  head:d.head.outerHTML,
  input_script_executed:globalThis.__localemeshInputExecuted===true
 };
})'''

class BrowserExtractor:
    """One local browser process, reusable across files. Optional dependency.

    Requires Chromium and websocket-client; failures raise RuntimeError. Never
    falls back silently. ``raw_many`` exposes tree facts for differential tests.
    """
    def __init__(self, executable=None, timeout=15):
        self.executable=executable or os.environ.get('LOCALEMESH_CHROMIUM') or shutil.which('chromium')
        if not self.executable: raise RuntimeError('Chromium is not installed; select the static extractor or install Chromium')
        self.timeout=timeout;self.temp=None;self.process=None;self.ws=None;self.sequence=0
        self.events=[];self.commands=[];self.version=None

    def __enter__(self):
        try:
            import websocket
            self.temp=tempfile.TemporaryDirectory(prefix='localemesh-chromium-')
            self.log=open(Path(self.temp.name)/'browser.log','w')
            args=[self.executable,'--headless','--no-sandbox','--disable-dev-shm-usage','--disable-gpu',
                  '--disable-background-networking','--no-first-run','--disable-component-update',
                  '--disable-sync','--disable-extensions','--metrics-recording-only',
                  '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost',
                  '--remote-debugging-address=127.0.0.1','--remote-debugging-port=0',
                  '--user-data-dir='+self.temp.name,'about:blank']
            self.process=subprocess.Popen(args,stdout=self.log,stderr=self.log)
            f=Path(self.temp.name)/'DevToolsActivePort';deadline=time.monotonic()+self.timeout
            while not f.exists():
                if self.process.poll() is not None or time.monotonic()>deadline:
                    raise RuntimeError('Chromium did not open a local DevTools endpoint')
                time.sleep(.05)
            port=int(f.read_text().splitlines()[0])
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f'http://127.0.0.1:{port}/json',timeout=self.timeout) as r:targets=json.load(r)
            target=next(t for t in targets if t.get('type')=='page')
            self.ws=websocket.create_connection(target['webSocketDebuggerUrl'],suppress_origin=True,timeout=self.timeout)
            self.version=self.call('Browser.getVersion')
            self.call('Network.enable')
            self.call('Network.setBlockedURLs',{'urls':['*']})
            self.call('Network.setBypassServiceWorker',{'bypass':True})
            self.call('Network.setCacheDisabled',{'cacheDisabled':True})
            return self
        except Exception:
            self.close();raise

    def call(self, method, params=None):
        self.sequence+=1;seq=self.sequence
        self.ws.send(json.dumps({'id':seq,'method':method,'params':params or {}}))
        self.commands.append(method)
        while True:
            response=json.loads(self.ws.recv())
            if response.get('id')!=seq:
                self.events.append(response);continue
            if 'error' in response:raise RuntimeError(f'CDP {method}: {response["error"]}')
            return response.get('result',{})

    def raw_many(self, texts):
        if not isinstance(texts,list) or not all(isinstance(t,str) for t in texts):
            raise ValueError('Expected a list of local HTML strings')
        result=self.call('Runtime.evaluate',{'expression':'('+EXTRACT_JS+')('+json.dumps(texts)+')','returnByValue':True})
        if 'exceptionDetails' in result:raise RuntimeError(str(result['exceptionDetails']))
        raw=result['result']['value']
        if any(r['input_script_executed'] for r in raw):raise RuntimeError('Inert parsing invariant failed')
        return raw

    def extract(self, text, response_url):
        return normalize_dom(self.raw_many([text])[0],response_url)

    def close(self):
        if self.ws is not None:
            try:self.ws.close()
            except Exception:pass
            self.ws=None
        if self.process is not None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
            self.process=None
        if getattr(self,'log',None):self.log.close()
        if self.temp:
            try:self.temp.cleanup()
            except OSError:shutil.rmtree(self.temp.name,ignore_errors=True)
            self.temp=None

    def __exit__(self,*args):self.close()


def normalize_dom(raw, response_url):
    """Separate tree selection; URL resolution deliberately uses model.url."""
    import re
    out={'status':200,'lang':raw['lang'],'key':None,'canonical':{'html':[]},'alternates':{'html':[]},'links':[]}
    diagnostics=set();markers=set(raw['markers']);base=url(response_url)
    if '' in markers:diagnostics.add(('CONTENT_MARKER_CONFLICT','Empty content marker'))
    markers.discard('')
    if len(markers)==1:out['key']=next(iter(markers))
    elif len(markers)>1:diagnostics.add(('CONTENT_MARKER_CONFLICT','|'.join(sorted(markers))))
    if raw['has_noscript']:diagnostics.add(('HTML_PROFILE','noscript requires an explicit scripting-mode contract'))
    if raw['bases']:
        try:base=url(raw['bases'][0],base)
        except ValueError:diagnostics.add(('HTML_REFERENCE','Unsupported base href'))
    refs=[]
    for a in raw['links']:
        rel=a.get('rel','').lower().split();canonical='canonical' in rel
        alternate='alternate' in rel and 'stylesheet' not in rel and bool(a.get('hreflang'))
        if not canonical and not alternate:continue
        if 'href' not in a:diagnostics.add(('HTML_REFERENCE','Relevant link lacks href'));continue
        if canonical:refs.append(('canonical','',a['href']))
        if alternate:
            if a.get('media','').strip():diagnostics.add(('HTML_PROFILE','Media-qualified language alternate'))
            refs.append(('alternate',a['hreflang'].lower(),a['href']))
    refs.extend(('link','',a.strip()) for a in raw['anchors'] if a.strip() and not a.strip().startswith('#')
                and urlsplit(a.strip()).scheme.lower() in ('','http','https'))
    for a in raw['refresh']:
        match=re.fullmatch(r'\s*0(?:\.0*)?\s*;\s*url\s*=\s*(.+?)\s*',a.get('content',''),re.I)
        if match:refs.append(('redirect','',match.group(1).strip('\"\'')))
        else:diagnostics.add(('HTML_PROFILE','Only zero-delay URL refresh is modeled'))
    redirects=set()
    for kind,label,href in refs:
        try:target=url(href,base)
        except ValueError:diagnostics.add(('HTML_REFERENCE',kind+':'+href));continue
        if kind=='canonical':out['canonical']['html'].append(target)
        elif kind=='alternate':out['alternates']['html'].append([label,target])
        elif kind=='link':out['links'].append(target)
        else:redirects.add(target)
    if len(redirects)==1:out['redirect']=next(iter(redirects));out['redirect_transport']='html-refresh'
    elif len(redirects)>1:diagnostics.add(('HTML_REFERENCE','Conflicting refresh targets'))
    if diagnostics:out['diagnostics']=[list(x) for x in sorted(diagnostics)]
    return out
