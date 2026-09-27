import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,mkdirSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {IntegrationRuntime,INTEGRATION_LIMITS,getIntegrationCatalog,isIntegrationAuthorized,hasIntegrationSafeOrigin} from '../lib/integration-runtime';
import type {Snapshot} from '../lib/graph';

function graph(count=2):Snapshot{const nodes=Array.from({length:count},(_,i)=>({id:`n${i}`,name:`Node ${i}`,kind:'file' as const,path:`src/${i}.ts`,summary:'',confidence:'parsed' as const}));return {version:1,name:'Fixture',nodes,edges:nodes.slice(1).map((node,i)=>({source:nodes[i].id,target:node.id,relation:'imports',confidence:'parsed' as const})),warnings:[],truncated:false};}
const env={OPENROUTER_API_KEY:'secret',OPENROUTER_MODEL:'test/model',VLLM_BASE_URL:'http://localhost:8000',VLLM_MODEL:'local-model',INTEGRATION_ACCESS_TOKEN:'test-token'};
const request=(body:unknown)=>({integrationId:'openrouter',operation:'review',input:{goal:'Review this graph',graph:graph(),parameters:{}}});
const waitFor=async(fn:()=>boolean)=>{for(let i=0;i<100;i++){if(fn())return;await new Promise(resolve=>setTimeout(resolve,2));}throw new Error('Timed out waiting for job state.');};

test('catalog exposes only configured providers and reports the non-secret model id',()=>{
 const entries=getIntegrationCatalog(env);assert.equal(entries.find(item=>item.id==='openrouter')?.modelId,'test/model');assert.equal(entries.find(item=>item.id==='vllm')?.modelId,'local-model');assert.equal(entries.find(item=>item.id==='langgraph')?.configured,false);assert.equal(entries.find(item=>item.id==='graph-rag-kernel')?.configured,false);assert.equal(entries.find(item=>item.id==='kernel-suite')?.configured,false);
});

test('framework panel fields pass through the runtime request validator',async()=>{
 const frameworkEnv={...env,COGNEE_BASE_URL:'https://cognee.example',COGNEE_DATASET:'default',MIROFISH_BASE_URL:'https://mirofish.internal',LANGGRAPH_BASE_URL:'https://langgraph.example',LANGGRAPH_ASSISTANT_ID:'assistant-1',LANGGRAPH_API_KEY:'lg-secret-123456',CREWAI_BASE_URL:'https://crewai.example',CREWAI_TOKEN:'crew-secret-123456'};const started:Record<string,Record<string,string|number>>={};const runtime=new IntegrationRuntime({env:frameworkEnv,execute:async(id,_operation,input)=>{started[id]=input.parameters;return {result:{ok:true}};}});const cases=[['cognee','add',{dataset:'fixture-data'}],['mirofish','status',{simulationId:'sim-123'}],['langgraph','status',{threadId:'thread-1',runId:'run-2'}],['crewai','status',{kickoffId:'kickoff-3'}]] as const;for(const [integrationId,operation,parameters] of cases){const job=runtime.start({integrationId,operation,input:{goal:'Check configured framework',parameters}});await waitFor(()=>runtime.get(job.id)?.status==='succeeded');}assert.deepEqual(started.cognee,{dataset:'fixture-data'});assert.deepEqual(started.mirofish,{simulationId:'sim-123'});assert.deepEqual(started.langgraph,{threadId:'thread-1',runId:'run-2'});assert.deepEqual(started.crewai,{kickoffId:'kickoff-3'});
});

test('request auth is timing-safe, origin-bound when present, and rejects unknown fields',()=>{
 const req=new Request('https://studio.example/api/integrations',{headers:{authorization:'Bearer test-token',origin:'https://studio.example',host:'studio.example'}});assert.equal(isIntegrationAuthorized(req,env.INTEGRATION_ACCESS_TOKEN),true);assert.equal(hasIntegrationSafeOrigin(req),true);
 const badOrigin=new Request('https://studio.example/api/integrations',{headers:{authorization:'Bearer test-token',origin:'https://attacker.example',host:'studio.example'}});assert.equal(hasIntegrationSafeOrigin(badOrigin),false);
 const runtime=new IntegrationRuntime({env,execute:async()=>({result:{ok:true}})});assert.throws(()=>runtime.start({...request({}),input:{...request({}).input,extra:'no'}}),/Input field is not supported/);
});

test('model and kernel request sizes are rejected rather than silently projected',()=>{
 const runtime=new IntegrationRuntime({env,execute:async()=>({result:{ok:true}})});assert.throws(()=>runtime.start({integrationId:'openrouter',operation:'review',input:{goal:'x',graph:graph(INTEGRATION_LIMITS.modelInputNodes+1),parameters:{}}}),/at most 300 nodes and 900 edges/);
 const temporary=mkdtempSync(path.join(tmpdir(),'kernel-cap-')),root=path.join(temporary,'.integration-sources','graph-rag-np-hard-kernel');try{mkdirSync(path.join(root,'graph_rag_np_hard_kernel'),{recursive:true});writeFileSync(path.join(root,'graph_rag_np_hard_kernel','engine.py'),'');writeFileSync(path.join(temporary,'.integration-sources','sources.json'),JSON.stringify([{name:'graph-rag-np-hard-kernel',revision:'35b1bb93a04d419fc1167480d93a1eed711fb711',path:root}]));const kernelEnv={...env,GRAPH_RAG_KERNEL_PATH:root};assert.throws(()=>new IntegrationRuntime({env:kernelEnv}).start({integrationId:'graph-rag-kernel',operation:'communities',input:{goal:'x',graph:graph(INTEGRATION_LIMITS.kernelNodes+1),parameters:{}}}),/limited/);}finally{rmSync(temporary,{recursive:true,force:true});}
});

test('jobs preserve graph identity, expose actual completion, and enforce output cap',async()=>{
 const runtime=new IntegrationRuntime({env,execute:async(_id,_op,input)=>({result:{goal:input.goal,snapshot:input.graph?.name},usage:{inputTokens:11,outputTokens:9}})});const job=runtime.start(request({}));assert.equal(job.snapshot?.name,'Fixture');await waitFor(()=>runtime.get(job.id)?.status==='succeeded');const done=runtime.get(job.id)!;assert.deepEqual(done.result,{goal:'Review this graph',snapshot:'Fixture'});assert.deepEqual(done.usage,{inputTokens:11,outputTokens:9});
 const tooBig=new IntegrationRuntime({env,execute:async()=>({result:{content:'x'.repeat(INTEGRATION_LIMITS.outputBytes+1)}})});const overflow=tooBig.start(request({}));await waitFor(()=>['failed','succeeded'].includes(tooBig.get(overflow.id)!.status));assert.equal(tooBig.get(overflow.id)?.status,'failed');assert.match(tooBig.get(overflow.id)?.error||'',/output limit/);
});

test('running cancellation settles even when an adapter ignores AbortSignal; timeout bounds are advertised',async()=>{
 const runtime=new IntegrationRuntime({env,execute:async()=>new Promise(()=>{})});const job=runtime.start(request({}));await waitFor(()=>runtime.get(job.id)?.status==='running');const cancelled=await runtime.cancel(job.id);assert.equal(cancelled?.status,'cancelled');await waitFor(()=>runtime.get(job.id)?.status==='cancelled');assert.equal(INTEGRATION_LIMITS.timeoutMs,45_000);
});

test('bounded queue concurrency never exceeds two jobs',async()=>{
 let active=0,maxActive=0;const releases:(()=>void)[]=[];const runtime=new IntegrationRuntime({env,execute:async()=>{active++;maxActive=Math.max(maxActive,active);await new Promise<void>(resolve=>releases.push(resolve));active--;return {result:{ok:true}};}});const jobs=[runtime.start(request({})),runtime.start(request({})),runtime.start(request({}))];await waitFor(()=>releases.length===2);assert.equal(runtime.get(jobs[2].id)?.status,'queued');releases.splice(0).forEach(resolve=>resolve());await waitFor(()=>releases.length===1);releases.splice(0).forEach(resolve=>resolve());await waitFor(()=>jobs.every(job=>runtime.get(job.id)?.status==='succeeded'));assert.equal(maxActive,2);
});

test('trusted local bridge receives fixed profile fields and redacts secrets from output',async()=>{
 let body:Record<string,unknown>|undefined,authorization='';const bridgeSecret='runner-secret-do-not-echo',originalFetch=globalThis.fetch;globalThis.fetch=async(input,init)=>{assert.equal(String(input),'http://127.0.0.1:8765/run');authorization=String(new Headers(init?.headers).get('authorization'));body=JSON.parse(String(init?.body));return new Response(JSON.stringify({status:'succeeded',workspace:'fixture',profile:'openmanus',output:`echo ${bridgeSecret}`,exitCode:0,usage:null}),{status:200,headers:{'content-type':'application/json'}});};try{const bridgeEnv={...env,LOCAL_RUNNER_URL:'http://127.0.0.1:8765',LOCAL_RUNNER_ACCESS_TOKEN:bridgeSecret};const runtime=new IntegrationRuntime({env:bridgeEnv});const job=runtime.start({integrationId:'openmanus',operation:'run',input:{goal:'Run a trusted profile',parameters:{harnessId:'openmanus',authMode:'subscription'}}});await waitFor(()=>runtime.get(job.id)?.status==='succeeded');assert.equal(body?.integrationId,'openmanus');assert.equal(body?.operation,'run');assert.equal(body?.harnessId,'openmanus');assert.equal(body?.authMode,'subscription');assert.equal(body?.requestId,job.id);assert.deepEqual(Object.keys(body||{}).sort(),['authMode','goal','harnessId','integrationId','operation','requestId'].sort());assert.equal(authorization,`Bearer ${bridgeSecret}`);assert.equal((runtime.get(job.id)?.result as {output:string}).output,'echo [redacted]');}finally{globalThis.fetch=originalFetch;}
});

test('bridge cancellation sends DELETE with the same server-generated job UUID',async()=>{
 const originalFetch=globalThis.fetch,calls:string[]=[];globalThis.fetch=async(input,init)=>{const url=String(input),method=init?.method||'GET';calls.push(`${method} ${url}`);if(method==='DELETE')return new Response(JSON.stringify({status:'cancelling'}),{status:202});return await new Promise<Response>((_resolve,reject)=>{const signal=init?.signal;signal?.addEventListener('abort',()=>reject(new DOMException('aborted','AbortError')),{once:true});});};try{const bridgeEnv={...env,LOCAL_RUNNER_URL:'http://127.0.0.1:8765',LOCAL_RUNNER_ACCESS_TOKEN:'runner-token-do-not-print'};const runtime=new IntegrationRuntime({env:bridgeEnv});const job=runtime.start({integrationId:'understand-anything',operation:'run',input:{goal:'Stop through bridge',parameters:{harnessId:'codex',authMode:'local'}}});await waitFor(()=>runtime.get(job.id)?.status==='running');assert.equal((await runtime.cancel(job.id))?.status,'cancelled');await waitFor(()=>calls.some(call=>call.startsWith('DELETE ')));assert.ok(calls.includes(`DELETE http://127.0.0.1:8765/run/${job.id}`));}finally{globalThis.fetch=originalFetch;}
});
