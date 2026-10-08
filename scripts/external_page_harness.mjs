import {readFileSync} from 'node:fs';
globalThis.fetch = async () => { throw new Error('External network disabled in this harness'); };
const {checkPage} = await import('../vendor/crawlcove/page-core.mjs');
const input = JSON.parse(readFileSync(0,'utf8'));
const responses = input.responses;
let requests = 0;
const fetchLocal = async (url, options) => {
  requests++;
  const r = responses[url];
  if (!r) return new Response('not present in local build', {status:404});
  const body = [101,204,205,304].includes(r.status) ? null : r.body;
  return new Response(body, {status:r.status,headers:r.headers});
};
const results = [];
for (const route of input.routes) {
  const result = await checkPage(route, {fetch:fetchLocal,maxAlternates:500,concurrency:4});
  if (result.truncated) throw new Error('Unexpected truncated cluster');
  results.push(result);
}
process.stdout.write(JSON.stringify({node:process.version,requests,results}));
