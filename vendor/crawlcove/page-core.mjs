/**
 * hreflang checker — the core, pure where it can be.
 *
 * Reads hreflang from the three places Google documents: <link rel="alternate"
 * hreflang> tags in the <head>, the HTTP `Link` response header, and
 * <xhtml:link> annotations inside a sitemap's <url> entries. Validates each
 * code, then checks the things that make a correct-looking set get ignored:
 * no self-referencing tag, no return tag on the alternate, a noindex on the
 * page, or a canonical pointing somewhere else.
 *
 * Same semantics as the hosted tool at crawlcove.com/tools/hreflang-checker
 * and the `hreflang` check in the Crawl Cove desktop crawler, so a finding
 * here means the same thing there.
 */
export const DEFAULT_OPTIONS = {
    timeoutMs: 10_000,
    userAgent: 'crawlcove-hreflang-checker/1.0 (+https://crawlcove.com/tools/hreflang-checker)',
    maxAlternates: 20,
    maxSitemapUrls: 500,
    maxChildSitemaps: 5,
    concurrency: 4,
    fetch: globalThis.fetch
};
const MAX_BODY_BYTES = 2_000_000;
/** The complete ISO 639-1 alpha-2 language code set. */
export const ISO_639_1 = new Set([
    'aa', 'ab', 'ae', 'af', 'ak', 'am', 'an', 'ar', 'as', 'av', 'ay', 'az',
    'ba', 'be', 'bg', 'bh', 'bi', 'bm', 'bn', 'bo', 'br', 'bs',
    'ca', 'ce', 'ch', 'co', 'cr', 'cs', 'cu', 'cv', 'cy',
    'da', 'de', 'dv', 'dz',
    'ee', 'el', 'en', 'eo', 'es', 'et', 'eu',
    'fa', 'ff', 'fi', 'fj', 'fo', 'fr', 'fy',
    'ga', 'gd', 'gl', 'gn', 'gu', 'gv',
    'ha', 'he', 'hi', 'ho', 'hr', 'ht', 'hu', 'hy', 'hz',
    'ia', 'id', 'ie', 'ig', 'ii', 'ik', 'io', 'is', 'it', 'iu',
    'ja', 'jv',
    'ka', 'kg', 'ki', 'kj', 'kk', 'kl', 'km', 'kn', 'ko', 'kr', 'ks', 'ku', 'kv', 'kw', 'ky',
    'la', 'lb', 'lg', 'li', 'ln', 'lo', 'lt', 'lu', 'lv',
    'mg', 'mh', 'mi', 'mk', 'ml', 'mn', 'mr', 'ms', 'mt', 'my',
    'na', 'nb', 'nd', 'ne', 'ng', 'nl', 'nn', 'no', 'nr', 'nv', 'ny',
    'oc', 'oj', 'om', 'or', 'os',
    'pa', 'pi', 'pl', 'ps', 'pt',
    'qu',
    'rm', 'rn', 'ro', 'ru', 'rw',
    'sa', 'sc', 'sd', 'se', 'sg', 'si', 'sk', 'sl', 'sm', 'sn', 'so', 'sq', 'sr', 'ss', 'st', 'su', 'sv', 'sw',
    'ta', 'te', 'tg', 'th', 'ti', 'tk', 'tl', 'tn', 'to', 'tr', 'ts', 'tt', 'tw', 'ty',
    'ug', 'uk', 'ur', 'uz',
    've', 'vi', 'vo',
    'wa', 'wo',
    'xh',
    'yi', 'yo',
    'za', 'zh', 'zu'
]);
/**
 * Validate one hreflang value: `x-default`, or language[-script][-region]
 * where a 2-letter language must be a real ISO 639-1 code (3-letter subtags
 * pass on shape alone, so rare-but-real tags are never false-flagged). The
 * note names the specific mistake when it is one people actually make.
 */
export function validateCode(code) {
    const raw = code.trim();
    const s = raw.toLowerCase();
    if (s === '')
        return { valid: false, note: 'Empty hreflang value.' };
    if (s === 'x-default')
        return { valid: true };
    if (s.includes('_'))
        return { valid: false, note: `"${raw}" uses an underscore; hreflang separates subtags with a hyphen (e.g. "${raw.replace(/_/g, '-')}").` };
    const m = /^([a-z]{2,3})(?:-([a-z]{4}))?(?:-([a-z]{2}|\d{3}))?$/.exec(s);
    if (m === null) {
        if (/^[a-z]{2}-[a-z]{2}-[a-z]{2}$/.test(s))
            return { valid: false, note: `"${raw}" has three two-letter subtags; the shape is language[-Script][-REGION], e.g. "zh-Hant-TW".` };
        if (/^[a-z]{4,}$/.test(s))
            return { valid: false, note: `"${raw}" is a language name, not a code; use the ISO 639-1 code (e.g. "en", "de").` };
        return { valid: false, note: `"${raw}" doesn't match a language code (e.g. "fr") or a language-region code (e.g. "fr-ca").` };
    }
    const lang = m[1];
    const region = m[3];
    if (lang.length === 2 && !ISO_639_1.has(lang)) {
        if (lang === 'gb')
            return { valid: false, note: `"${raw}": "gb" is a region, not a language. British English is "en-gb".` };
        return { valid: false, note: `"${raw}": "${lang}" is not an ISO 639-1 language code.` };
    }
    if (region === 'uk')
        return { valid: false, note: `"${raw}": there is no region "uk". The United Kingdom's region code is "gb" (e.g. "${lang}-gb").` };
    if (region === 'eu')
        return { valid: false, note: `"${raw}": "eu" is not a region (there is no ISO country code for the EU). Use one tag per country, or a bare language code.` };
    if (region === undefined && lang === 'uk')
        return { valid: true, note: '"uk" is Ukrainian, not the United Kingdom. If this page is British English, use "en-gb".' };
    return { valid: true };
}
/** Fragment stripped, scheme+host lower-cased, default port dropped; unparseable input returned as-is. */
export function normalizeUrl(value) {
    try {
        const u = new URL(value);
        u.hash = '';
        return u.toString();
    }
    catch {
        return value;
    }
}
function decodeEntities(s) {
    return s
        .replace(/&amp;/gi, '&')
        .replace(/&lt;/gi, '<')
        .replace(/&gt;/gi, '>')
        .replace(/&quot;/gi, '"')
        .replace(/&#39;|&apos;/gi, "'");
}
function attr(tag, name) {
    const m = new RegExp(`\\b${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)'|([^\\s"'>]+))`, 'i').exec(tag);
    if (m === null)
        return null;
    return decodeEntities((m[1] ?? m[2] ?? m[3] ?? '').trim());
}
function isAbsolute(href) {
    return /^https?:\/\//i.test(href.trim());
}
function resolve(base, href) {
    try {
        const u = new URL(href, base);
        if (u.protocol !== 'http:' && u.protocol !== 'https:')
            return null;
        return u.toString();
    }
    catch {
        return null;
    }
}
/** Only the <head> counts (falling back to the whole document when there is none). */
function headOf(html) {
    const m = /<head\b[^>]*>([\s\S]*?)<\/head>/i.exec(html);
    return m ? m[1] : html;
}
/** `<link rel="alternate" hreflang="…" href="…">` tags from the document head. */
export function extractHreflangTags(baseUrl, html) {
    const out = [];
    for (const tag of headOf(html).match(/<link\b[^>]*>/gi) ?? []) {
        const rel = attr(tag, 'rel');
        if (rel === null || !rel.toLowerCase().split(/\s+/).includes('alternate'))
            continue;
        const hreflang = attr(tag, 'hreflang');
        const hrefRaw = attr(tag, 'href');
        if (!hreflang || !hrefRaw)
            continue;
        const href = resolve(baseUrl, hrefRaw);
        if (href === null)
            continue;
        const v = validateCode(hreflang);
        out.push({ hreflang, href, source: 'html', valid: v.valid, note: v.note, absolute: isAbsolute(hrefRaw) });
    }
    return out;
}
/** `Link: <url>; rel="alternate"; hreflang="en", <url2>; …` from the response header. */
export function extractHreflangFromLinkHeader(header, baseUrl) {
    if (!header || header.trim() === '')
        return [];
    const out = [];
    for (const part of header.split(/,(?=\s*<)/)) {
        const m = /^\s*<([^>]*)>\s*((?:;[^;]*)*)$/.exec(part);
        if (m === null)
            continue;
        const params = {};
        for (const p of m[2].split(';')) {
            const kv = /^\s*([a-z-]+)\s*=\s*(?:"([^"]*)"|([^\s"]+))\s*$/i.exec(p);
            if (kv)
                params[kv[1].toLowerCase()] = (kv[2] ?? kv[3] ?? '').trim();
        }
        if (!(params.rel ?? '').toLowerCase().split(/\s+/).includes('alternate'))
            continue;
        if (!params.hreflang)
            continue;
        const href = resolve(baseUrl, m[1]);
        if (href === null)
            continue;
        const v = validateCode(params.hreflang);
        out.push({ hreflang: params.hreflang, href, source: 'header', valid: v.valid, note: v.note, absolute: isAbsolute(m[1]) });
    }
    return out;
}
/** The page's `<link rel="canonical">`, resolved; null when absent or unparseable. */
export function extractCanonical(baseUrl, html) {
    for (const tag of headOf(html).match(/<link\b[^>]*>/gi) ?? []) {
        const rel = attr(tag, 'rel');
        if (rel === null || !rel.toLowerCase().split(/\s+/).includes('canonical'))
            continue;
        const href = attr(tag, 'href');
        if (href)
            return resolve(baseUrl, href);
    }
    return null;
}
/** True when either the X-Robots-Tag header or a robots/googlebot meta says noindex. */
export function isNoindex(xRobotsTag, html) {
    if (xRobotsTag && /\bnoindex\b/i.test(xRobotsTag))
        return true;
    for (const tag of headOf(html).match(/<meta\b[^>]*>/gi) ?? []) {
        const name = (attr(tag, 'name') ?? '').toLowerCase();
        if (name !== 'robots' && name !== 'googlebot')
            continue;
        if (/\bnoindex\b/i.test(attr(tag, 'content') ?? ''))
            return true;
    }
    return false;
}
function dedupeTags(tags) {
    const seen = new Set();
    const out = [];
    for (const t of tags) {
        const key = `${t.hreflang.toLowerCase()}|${normalizeUrl(t.href)}`;
        if (seen.has(key))
            continue;
        seen.add(key);
        out.push(t);
    }
    return out;
}
/** Self-reference, x-default and conflicting-code analysis of one page's tag set. Pure. */
export function analyseCluster(pageUrl, tags) {
    const self = normalizeUrl(pageUrl);
    const urlsByCode = new Map();
    let selfReferencing = false;
    let hasXDefault = false;
    for (const t of tags) {
        const code = t.hreflang.toLowerCase();
        if (code === 'x-default')
            hasXDefault = true;
        if (normalizeUrl(t.href) === self)
            selfReferencing = true;
        const set = urlsByCode.get(code) ?? new Set();
        set.add(normalizeUrl(t.href));
        urlsByCode.set(code, set);
    }
    const duplicates = [...urlsByCode.entries()].filter(([, urls]) => urls.size > 1).map(([code]) => code);
    return { tags, selfReferencing, hasXDefault, duplicates };
}
/** The findings a cluster analysis implies, the same for page and sitemap mode. Pure. */
export function clusterFindings(url, a, reciprocity) {
    const out = [];
    for (const t of a.tags) {
        if (!t.valid)
            out.push({ code: 'invalid-code', severity: 'error', url, message: `hreflang="${t.hreflang}" (${t.source}): ${t.note ?? 'invalid'}` });
        else if (t.note)
            out.push({ code: 'suspicious-code', severity: 'warning', url, message: `hreflang="${t.hreflang}" (${t.source}): ${t.note}` });
        if (!t.absolute)
            out.push({ code: 'relative-href', severity: 'error', url, message: `hreflang="${t.hreflang}" points at a relative URL; Google requires absolute URLs including the scheme (resolved here to ${t.href}).` });
    }
    if (!a.selfReferencing)
        out.push({ code: 'missing-self-reference', severity: 'error', url, message: 'No hreflang tag points at this URL itself. Every page in a cluster must list itself, or Google ignores the set.' });
    if (!a.hasXDefault)
        out.push({ code: 'missing-x-default', severity: 'warning', url, message: 'No x-default tag. Without one, visitors whose language matches nothing in the set get whatever Google picks.' });
    for (const code of a.duplicates)
        out.push({ code: 'duplicate-code', severity: 'error', url, message: `hreflang="${code}" is declared for more than one URL; each language/region may name only one page.` });
    for (const r of reciprocity) {
        if (r.status === 'missing')
            out.push({ code: 'missing-return-tag', severity: 'error', url, message: `${r.href} (hreflang="${r.hreflang}") does not link back to ${url}. Both pages must reference each other or Google ignores the pair.` });
        else if (r.status === 'unreachable')
            out.push({ code: 'alternate-unreachable', severity: 'error', url, message: `${r.href} (hreflang="${r.hreflang}") could not be fetched${r.note ? `: ${r.note}` : ''}.` });
        else if (r.status === 'redirected')
            out.push({ code: 'alternate-redirects', severity: 'warning', url, message: `${r.href} (hreflang="${r.hreflang}") redirects; hreflang should name the final URL, not a redirect.` });
        else if (r.status === 'not-in-sitemap')
            out.push({ code: 'not-in-sitemap', severity: 'warning', url, message: `${r.href} (hreflang="${r.hreflang}") is not its own <url> entry in this sitemap, so its return tag cannot be confirmed from here.` });
    }
    return out;
}
async function fetchOne(url, opts, followRedirects) {
    let current = url;
    for (let hop = 0; hop < 6; hop++) {
        let res;
        try {
            res = await opts.fetch(current, {
                redirect: 'manual',
                headers: { 'user-agent': opts.userAgent, accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8' },
                signal: AbortSignal.timeout(opts.timeoutMs)
            });
        }
        catch (e) {
            return { status: null, finalUrl: current, redirected: current !== url, body: '', linkHeader: null, xRobotsTag: null, contentType: null, error: e instanceof Error ? e.message : String(e) };
        }
        if (res.status >= 300 && res.status < 400 && res.headers.get('location')) {
            const next = resolve(current, res.headers.get('location'));
            if (!followRedirects || next === null) {
                return { status: res.status, finalUrl: next ?? current, redirected: true, body: '', linkHeader: null, xRobotsTag: null, contentType: null };
            }
            current = next;
            continue;
        }
        const buf = Buffer.from(await res.arrayBuffer());
        return {
            status: res.status,
            finalUrl: current,
            redirected: current !== url,
            body: buf.subarray(0, MAX_BODY_BYTES).toString('utf8'),
            linkHeader: res.headers.get('link'),
            xRobotsTag: res.headers.get('x-robots-tag'),
            contentType: res.headers.get('content-type')
        };
    }
    return { status: null, finalUrl: current, redirected: true, body: '', linkHeader: null, xRobotsTag: null, contentType: null, error: 'too many redirects' };
}
async function mapLimit(items, limit, fn) {
    const out = new Array(items.length);
    let next = 0;
    const workers = Array.from({ length: Math.max(1, Math.min(limit, items.length)) }, async () => {
        while (next < items.length) {
            const i = next++;
            out[i] = await fn(items[i]);
        }
    });
    await Promise.all(workers);
    return out;
}
function ensureScheme(input) {
    const s = input.trim();
    return /^https?:\/\//i.test(s) ? s : `https://${s}`;
}
/** Page mode: one URL's own tags, then each alternate fetched for its return tag. */
export async function checkPage(input, options = {}) {
    const opts = { ...DEFAULT_OPTIONS, ...options };
    const url = ensureScheme(input);
    const base = {
        mode: 'page', url, finalUrl: url, status: null, tags: [], selfReferencing: false, hasXDefault: false,
        duplicates: [], reciprocity: [], totalAlternates: 0, checked: 0, truncated: false, canonical: null, noindex: false, findings: []
    };
    const page = await fetchOne(url, opts, true);
    base.status = page.status;
    base.finalUrl = page.finalUrl;
    if (page.error || page.status === null || page.status >= 400) {
        base.fetchError = page.error ?? `HTTP ${page.status}`;
        base.findings.push({ code: 'fetch-error', severity: 'error', url, message: `Could not read the page: ${base.fetchError}.` });
        return base;
    }
    const pageUrl = page.finalUrl;
    const tags = dedupeTags([...extractHreflangTags(pageUrl, page.body), ...extractHreflangFromLinkHeader(page.linkHeader, pageUrl)]);
    const canonical = extractCanonical(pageUrl, page.body);
    const canonicalConflict = canonical !== null && normalizeUrl(canonical) !== normalizeUrl(pageUrl);
    base.canonical = canonicalConflict ? canonical : null;
    base.noindex = isNoindex(page.xRobotsTag, page.body);
    if (page.redirected)
        base.findings.push({ code: 'page-redirects', severity: 'warning', url, message: `${url} redirects to ${pageUrl}; the tags below were read from the final URL, and alternates should point there.` });
    if (tags.length === 0) {
        base.findings.push({ code: 'no-hreflang', severity: 'warning', url, message: 'No hreflang tags found in the <head> or the HTTP Link header.' });
        if (base.noindex)
            base.findings.push({ code: 'noindex', severity: 'warning', url, message: 'This page carries a noindex directive.' });
        return base;
    }
    const a = analyseCluster(pageUrl, tags);
    Object.assign(base, { tags: a.tags, selfReferencing: a.selfReferencing, hasXDefault: a.hasXDefault, duplicates: a.duplicates });
    const self = normalizeUrl(pageUrl);
    const seen = new Set([self]);
    const alternates = [];
    for (const t of tags) {
        const n = normalizeUrl(t.href);
        if (seen.has(n))
            continue;
        seen.add(n);
        alternates.push(t);
    }
    base.totalAlternates = alternates.length;
    const toCheck = alternates.slice(0, opts.maxAlternates);
    base.checked = toCheck.length;
    base.truncated = alternates.length > toCheck.length;
    base.reciprocity = await mapLimit(toCheck, opts.concurrency, async (t) => {
        const r = await fetchOne(t.href, opts, false);
        if (r.redirected)
            return { href: t.href, hreflang: t.hreflang, status: 'redirected', note: `redirects to ${r.finalUrl}` };
        if (r.error || r.status === null || r.status >= 400)
            return { href: t.href, hreflang: t.hreflang, status: 'unreachable', note: r.error ?? `HTTP ${r.status}` };
        const theirs = [...extractHreflangTags(t.href, r.body), ...extractHreflangFromLinkHeader(r.linkHeader, t.href)];
        const linksBack = theirs.some((x) => normalizeUrl(x.href) === self);
        return { href: t.href, hreflang: t.hreflang, status: linksBack ? 'ok' : 'missing', note: linksBack ? undefined : 'its own hreflang tags do not list this page' };
    });
    base.findings.push(...clusterFindings(pageUrl, a, base.reciprocity));
    if (base.noindex)
        base.findings.push({ code: 'noindex', severity: 'error', url, message: 'This page carries a noindex directive. A noindexed page is never served from search, so its hreflang tags are ignored whether or not they are correct.' });
    if (canonicalConflict)
        base.findings.push({ code: 'canonical-conflict', severity: 'error', url, message: `The canonical tag points at ${canonical}, not this page. Google reads hreflang from the canonical URL, so the tags here may be disregarded in favour of whatever that page declares.` });
    if (base.truncated)
        base.findings.push({ code: 'alternates-truncated', severity: 'warning', url, message: `Only the first ${base.checked} of ${base.totalAlternates} alternates were fetched for the return-tag check (--max-alternates raises it).` });
    return base;
}
