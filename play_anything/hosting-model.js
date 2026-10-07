/* List-price scenario model. Keep parity with core/hosting_costs.py. */
const HostingModel = (() => {
const defaults={web:'local',database:'none',commercial:true,seats:1,builds:30,requests:10000,cpu_ms:5,mau:1000,db_gb:.1,storage_gb:.1,egress_gb:1,cached_gb:0,vercel_usage:0,extra:0};
const sources={'Vercel Pro':'https://vercel.com/docs/plans/pro-plan','Vercel Hobby':'https://vercel.com/docs/plans/hobby','Cloudflare Pages':'https://developers.cloudflare.com/pages/platform/limits/','Cloudflare Workers':'https://developers.cloudflare.com/workers/platform/pricing/','Supabase':'https://supabase.com/pricing'};
function estimate(settings={}) {
 if(!isRecord(settings))throw Error('Hosting settings must be an object.');
 const a={...defaults,...settings},rows=[],warnings=[];
 if(Object.keys(a).some(k=>!Object.prototype.hasOwnProperty.call(defaults,k)))throw Error('Unknown hosting setting.');
 if(!['local','cloudflare_free','cloudflare_workers','vercel_hobby','vercel_pro'].includes(a.web)||!['none','free','pro'].includes(a.database))throw Error('Unknown hosting plan.');
 if(typeof a.commercial!=='boolean')throw Error('Commercial use must be true or false.');
 Object.keys(a).filter(k=>!['web','database','commercial'].includes(k)).forEach(k=>{if(!isNumericInput(a[k])||!Number.isFinite(Number(a[k]))||isNonzeroUnderflow(a[k])||Number(a[k])<0||Number(a[k])>1e12)throw Error('Invalid hosting input: '+k);a[k]=Number(a[k]);if(['seats','builds','requests','mau'].includes(k)&&!Number.isInteger(a[k]))throw Error(k+' must be a whole number.');});
 if(a.seats<1)throw Error('At least one deploying seat is required.');
 const add=(name,amount,formula)=>rows.push({name,amount,formula}),excess=(k,limit,rate)=>Math.max(0,a[k]-limit)*rate;
 if(a.web==='vercel_hobby'&&a.commercial)warnings.push('Vercel Hobby is restricted to personal, non-commercial use. Choose Pro for this business.');
 if(a.web.startsWith('cloudflare')&&a.builds>500)warnings.push('Cloudflare Pages Free exceeds 500 builds/month. Upgrade or reduce builds; extra build pricing is not estimated.');
 if(a.web==='vercel_pro'){add('Vercel platform and deploying seats',a.seats*20,'$20 × deploying seats; first seat included in platform fee');add('Vercel metered usage after credit',Math.max(0,a.vercel_usage-20),'max(0, entered eligible metered usage − $20 credit); excludes add-ons');}
 if(a.web==='cloudflare_workers'){add('Optional Workers paid base',5,'$5/month; static Pages deployment itself needs no Worker');add('Optional Worker requests',excess('requests',1e7,.0000003),'max(0, monthly requests − 10M) × $0.30/M');add('Optional Worker CPU',Math.max(0,a.requests*a.cpu_ms-3e7)*.00000002,'max(0, requests × CPU ms − 30M ms) × $0.02/M ms');}
 if(a.database==='free')Object.entries({mau:50000,db_gb:.5,storage_gb:1,egress_gb:5,cached_gb:5}).forEach(([k,l])=>{if(a[k]>l)warnings.push(`Supabase Free exceeds ${k} allowance (${l}); upgrade required, no automatic free-tier overage price assumed.`);});
 if(a.database==='pro'){add('Supabase Pro + one Micro project',25,'$25 organization + $10 Micro compute − $10 compute credit');[['mau',100000,.00325],['db_gb',8,.125],['storage_gb',100,.0213],['egress_gb',250,.09],['cached_gb',250,.03]].forEach(([k,l,r])=>add('Supabase '+k,excess(k,l,r),`max(0, ${k} − ${l}) × $${r}`));}
 add('Other hosting and add-ons allowance',a.extra,'Editable allowance: domains, email, backups, extra projects, observability, taxes as applicable');
 return {settings:a,monthly:Math.round(rows.reduce((s,r)=>s+r.amount,0)*1e6)/1e6,rows,warnings,eligible:!warnings.length,estimate_type:'illustrative',price_verified:false,verified_on:null,estimate_basis:'Editable planning scenario using modeled rates; not a quote or live-verified provider price list.',sources,scope:'Static site hosting and one Supabase project. Git clones and agent connections run locally. Free Supabase can pause after one inactive week; 2 active free projects maximum. Realtime, functions, large compute, email and other add-ons need separate allowances.'};
}
function isRecord(value){if(value===null||typeof value!=='object'||Array.isArray(value))return false;const prototype=Object.getPrototypeOf(value);return prototype===Object.prototype||prototype===null;}
function isNumericInput(value){return (typeof value==='number'||typeof value==='string')&&!(typeof value==='string'&&value.trim()==='');}
function isNonzeroUnderflow(value){if(typeof value!=='string'||Number(value)!==0)return false;const match=value.trim().match(/^([+-]?(?:\d+(?:\.\d*)?|\.\d+))(?:e[+-]?\d+)?$/i);return !!match&&/[1-9]/.test(match[1]);}
return {defaults,sources,estimate};
})();
if(typeof module!=='undefined')module.exports=HostingModel;
