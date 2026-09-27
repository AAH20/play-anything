import test from 'node:test';
import assert from 'node:assert/strict';
import {describeSnapshot,parseSnapshot} from '../lib/graph';
import {runModelSwarm,type ModelSwarmReviewer,type ModelSwarmRole} from '../lib/model-swarm';

const graph=parseSnapshot({version:1,name:'swarm fixture',nodes:[
 {id:'a',name:'A',kind:'module',path:'a',summary:'entry',confidence:'parsed'},
 {id:'b',name:'B',kind:'function',path:'b',summary:'worker',confidence:'observed'}
],edges:[{source:'a',target:'b',relation:'calls',confidence:'parsed'}],warnings:[],truncated:false});
const output=(role:ModelSwarmRole,invalidCitation=false)=>role==='critic'?{summary:'The reviews agree on the directed boundary but disagree on risk.',agreements:['Both reviews cite the same boundary.'],disagreements:[{topic:'Risk level',structureView:'The boundary is clear.',dependencyView:'The call edge may be risky.',nodeIds:['a','b']}],findings:[{title:'Inspect the call boundary',detail:'Verify how this call is used.',nodeIds:[invalidCitation?'ghost':'a']}] }:{summary:`${role} review`,findings:[{title:`${role} finding`,detail:'A graph-grounded observation.',nodeIds:[invalidCitation?'ghost':'a']}]};
const reviewer:ModelSwarmReviewer=async(role)=>({output:output(role),usage:{inputTokens:10,outputTokens:20},model:'test/injected'});

test('runs two specialist calls concurrently and starts critic after both settle',async()=>{
 const started:ModelSwarmRole[]=[],settled=new Set<ModelSwarmRole>();let active=0,maxActive=0;
 const injected:ModelSwarmReviewer=async(role,_graph,_prompt,signal)=>{started.push(role);active++;maxActive=Math.max(maxActive,active);if(role==='critic')assert.ok(settled.has('structure')&&settled.has('dependency-risk'));await new Promise<void>((resolve,reject)=>{const timer=setTimeout(resolve,role==='structure'?25:10);signal.addEventListener('abort',()=>{clearTimeout(timer);reject(Error('aborted'));},{once:true});});active--;settled.add(role);return {output:output(role),usage:{inputTokens:10,outputTokens:20},model:'test/injected'};};
 const result=await runModelSwarm(graph,'Inspect coupling',new AbortController().signal,injected);
 assert.deepEqual(started,['structure','dependency-risk','critic']);
 assert.equal(maxActive,2);
 assert.equal(result.critic?.disagreements.length,1);
 assert.equal(result.critic?.findings[0].confidence,'model-suggestion');
 assert.equal(result.agentRuns,3);
 assert.equal(result.maxModelSteps,9);
 assert.equal(result.maxOutputTokens,5400);
 assert.equal(result.usage.outputTokens,60);
 assert.equal(result.snapshot.name,graph.name);
 assert.equal(result.snapshot.id,describeSnapshot(graph).id);
});

test('critic sees failed specialist states and invalid citations never enter the report',async()=>{
 const result=await runModelSwarm(graph,'Review',new AbortController().signal,async role=>({output:output(role,role==='structure'),usage:{inputTokens:1,outputTokens:1}}));
 assert.equal(result.specialists.structure.status,'failed');
 assert.equal(result.specialists.structure.findings.length,0);
 assert.equal(result.specialists['dependencyRisk'].status,'complete');
 assert.ok(result.critic);
 assert.ok(result.critic.findings.every(f=>f.nodeIds.every(id=>graph.nodes.some(n=>n.id===id))));
});

test('cancellation aborts outstanding reviews promptly',async()=>{
 const controller=new AbortController();let aborted=0;
 const injected:ModelSwarmReviewer=async(_role,_graph,_prompt,signal)=>new Promise((resolve,reject)=>signal.addEventListener('abort',()=>{aborted++;reject(Error('aborted'));},{once:true}));
 const pending=runModelSwarm(graph,'Review',controller.signal,injected);setTimeout(()=>controller.abort(),5);
 await assert.rejects(pending,/canceled/i);
 assert.equal(aborted,2);
});

test('reviewer errors do not leak into public specialist text',async()=>{
 const result=await runModelSwarm(graph,'Review',new AbortController().signal,async role=>{if(role==='structure')throw Error('secret provider body');return {output:output(role),usage:{inputTokens:1,outputTokens:1}};});
 assert.equal(result.specialists.structure.status,'failed');
 assert.ok(!JSON.stringify(result).includes('secret provider body'));
});
