// Live localhost verification; never invokes paid models or external frameworks.
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {parseSnapshot,filterGraph} from '../lib/graph.ts';
const app=fileURLToPath(new URL('../',import.meta.url));
const env=readFileSync(`${app}.env.local`,'utf8');
const token=env.split('\n').find(line=>line.startsWith('INTEGRATION_ACCESS_TOKEN='))?.split('=').slice(1).join('=').trim();
assert.ok(token,'Configure INTEGRATION_ACCESS_TOKEN first.');
const base='http://127.0.0.1:3000';
const request=async(path,options={})=>fetch(`${base}${path}`,{redirect:'error',...options});
const catalog=await (await request('/api/integrations')).json();
assert.ok(Array.isArray(catalog.integrations),'Public registry must load.');
const unauthorized=await request('/api/integrations',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
assert.equal(unauthorized.status,401);
const foreign=await request('/api/integrations',{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`,Origin:'https://untrusted.example'},body:'{}'});
assert.ok([401,403].includes(foreign.status),'Foreign origins must be rejected.');
const full=parseSnapshot(JSON.parse(readFileSync(`${app}public/repository-graph.json`,'utf8')));
const view=filterGraph(full,{query:'',kind:'all',relation:'all',evidence:'all',directory:'all',view:'modules',focus:null,hops:1,direction:'both'});
const graph={version:1,name:`${full.name} · module view`,nodes:view.nodes,edges:view.edges,warnings:['Filtered module view for integration smoke verification.'],truncated:true};
for(const integrationId of ['graph-rag-kernel','agentic-kernel','mirofish-optimizer','graph-swarm-kernel','kernel-suite']){
 const entry=catalog.integrations.find(item=>item.id===integrationId);assert.ok(entry?.configured,`${integrationId} must be configured.`);
 const started=await request('/api/integrations',{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify({integrationId,operation:entry.operations[0].id,input:{goal:'Measure the current module graph without external model calls.',graph,parameters:{}}})});
 const body=await started.json();assert.ok(started.ok,`${integrationId}: ${body.error||started.status}`);
 let job=body.job;const deadline=Date.now()+50_000;
 while(['queued','running'].includes(job.status)&&Date.now()<deadline){
  await new Promise(resolve=>setTimeout(resolve,300));
  const response=await request(`/api/integrations/jobs/${job.id}`,{headers:{Authorization:`Bearer ${token}`}});const state=await response.json();assert.ok(response.ok,state.error||'Job poll failed');job=state.job;
 }
 assert.equal(job.status,'succeeded',`${integrationId}: ${job.error||job.status}`);
 if(integrationId==='kernel-suite'){
  assert.equal(job.result.results.length,4);
  for(const result of job.result.results)assert.equal(result.status,'succeeded',`${result.integrationId}: ${result.error||result.status}`);
 }
 console.log(JSON.stringify({integrationId,status:job.status,nodes:graph.nodes.length,edges:graph.edges.length,resultKeys:Object.keys(job.result||{}),usage:job.usage||null}));
}
console.log('PASS: public registry, unauthorized and foreign-origin rejection, and five live local kernel operations.');
