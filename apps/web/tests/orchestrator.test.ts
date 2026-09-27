import test from 'node:test';
import assert from 'node:assert/strict';
import {analyze} from '../lib/analysis';
import {orchestrate} from '../lib/orchestrator';
import {describeSnapshot,parseSnapshot} from '../lib/graph';

const graph=parseSnapshot({version:1,name:'empty',nodes:[],edges:[],warnings:[],truncated:false});
class FakeWorker {
 onmessage:((event:MessageEvent)=>void)|null=null;
 onerror:((event:ErrorEvent)=>void)|null=null;
 terminated=false;
 constructor(private delay:number,private respond=true,private track?:(delta:number)=>void){this.track?.(1);}
 postMessage(data:{role:Parameters<typeof analyze>[0];graph:typeof graph}){if(this.respond)setTimeout(()=>{if(!this.terminated)this.onmessage?.({data:{ok:true,result:analyze(data.role,data.graph)}} as MessageEvent);},this.delay);}
 terminate(){if(!this.terminated){this.terminated=true;this.track?.(-1);}}
}
const run=(factory:()=>Worker,concurrency=2,timeoutMs=500,signal=new AbortController().signal)=>orchestrate(graph,{concurrency,timeoutMs,signal,onUpdate:()=>{},workerFactory:factory});

test('orchestrator respects worker cap and returns all specialist results',async()=>{
 let active=0,maxActive=0;
 const state=await run(()=>new FakeWorker(15,true,d=>{active+=d;maxActive=Math.max(maxActive,active);}) as unknown as Worker,2);
 assert.equal(maxActive,2);
 assert.equal(state.status,'complete');
 assert.equal(state.results.length,3);
 assert.deepEqual(state.tasks.map(t=>t.status),['complete','complete','complete']);
 assert.ok(state.report?.summary.includes('3 specialists completed'));
 assert.equal(state.snapshot.name,'empty');
 assert.equal(state.snapshot.nodeCount,0);
 assert.equal(state.snapshot.id,describeSnapshot(graph).id);
});

test('worker timeout and invalid concurrency settle as partial work',async()=>{
 const state=await run(()=>new FakeWorker(0,false) as unknown as Worker,Number.NaN,100);
 assert.equal(state.status,'partial');
 assert.ok(state.tasks.every(t=>t.status==='failed'));
 assert.ok(state.tasks.every(t=>t.error==='Worker time budget exceeded.'));
});

test('cancellation terminates active workers and marks queued work canceled',async()=>{
 const controller=new AbortController();let terminated=0;
 const promise=run(()=>new FakeWorker(0,false,delta=>{if(delta<0)terminated++;}) as unknown as Worker,1,500,controller.signal);
 setTimeout(()=>controller.abort(),10);
 const state=await promise;
 assert.equal(state.status,'canceled');
 assert.equal(terminated,1);
 assert.equal(state.tasks[0].status,'canceled');
 assert.deepEqual(state.tasks.slice(1).map(t=>t.status),['canceled','canceled']);
});

test('cancellation preserves already completed specialist evidence',async()=>{
 const controller=new AbortController();let created=0;
 const promise=run(()=>new FakeWorker(++created===1?5:0,created===1) as unknown as Worker,1,500,controller.signal);
 setTimeout(()=>controller.abort(),25);
 const state=await promise;
 assert.equal(state.status,'canceled');
 assert.equal(state.results.length,1);
 assert.equal(state.tasks[0].status,'complete');
 assert.equal(state.tasks[1].status,'canceled');
 assert.equal(state.report?.summary.startsWith('1 specialists completed'),true);
});

test('observer exceptions do not prevent worker completion',async()=>{
 const state=await orchestrate(graph,{concurrency:1,timeoutMs:500,signal:new AbortController().signal,onUpdate:()=>{throw Error('closed view');},workerFactory:()=>new FakeWorker(0,true) as unknown as Worker});
 assert.equal(state.status,'complete');
});
