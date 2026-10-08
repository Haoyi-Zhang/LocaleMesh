import publication from '../../../publication.json';
export const dynamicParams=false;
export function generateStaticParams(){return publication.pages.map(p=>({locale:p.locale,slug:p.key}));}
function findPage(locale,slug){const p=publication.pages.find(p=>p.locale===locale && p.key===slug);if(!p)throw new Error('Unknown content');return p;}
export async function generateMetadata({params}){const {locale,slug}=await params;const p=findPage(locale,slug);return {title:p.title,alternates:{canonical:p.url,languages:p.alternates}};}
export default async function Page({params}){const {locale,slug}=await params;const p=findPage(locale,slug);return <main data-content-key={p.key}><h1>{p.title}</h1><p>{p.body}</p></main>;}
