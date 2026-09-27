import {ROLES,type Role,type Analysis,reconcile} from './analysis';
import {describeSnapshot,type Snapshot,type SnapshotDescriptor} from './graph';
export const MAX_RUN_TIMEOUT_MS=45_000;
export type TaskStatus='queued'|'running'|'complete'|'failed'|'canceled';
export type Task={role:Role;status:TaskStatus;elapsedMs?:number;error?:string};
export type RunEvent={at:string;role:string;message:string};
export type RunState={id:string;snapshot:SnapshotDescriptor;status:'running'|'complete'|'canceled'|'partial';tasks:Task[];events:RunEvent[];results:Analysis[];report:ReturnType<typeof reconcile>|null};
function validAnalysis(value:unknown,role:Role):value is Analysis{
 if(!value||typeof value!=='object')return false;
 const result=value as Analysis;
 return result.role===role&&typeof result.summary==='string'&&Number.isFinite(result.durationMs)&&Array.isArray(result.findings)&&result.findings.every(f=>!!f&&typeof f.title==='string'&&typeof f.detail==='string'&&['info','attention'].includes(f.severity)&&['observed','inferred'].includes(f.confidence)&&Array.isArray(f.nodeIds)&&f.nodeIds.every(id=>typeof id==='string'))&&!!result.metrics&&typeof result.metrics==='object'&&!Array.isArray(result.metrics)&&Object.values(result.metrics).every(metric=>Number.isFinite(metric));
}
export function orchestrate(graph:Snapshot,options:{concurrency:number;timeoutMs:number;signal:AbortSignal;onUpdate:(state:RunState)=>void;workerFactory?:()=>Worker}){
 const state:RunState={id:crypto.randomUUID(),snapshot:describeSnapshot(graph),status:'running',tasks:ROLES.map(role=>({role,status:'queued'})),events:[],results:[],report:null};
 const publish=()=>{try{options.onUpdate({...state,tasks:state.tasks.map(t=>({...t})),events:[...state.events],results:[...state.results]});}catch{/* A UI observer failure must not leave workers alive. */}};
 const log=(role:string,message:string)=>{state.events.push({at:new Date().toISOString(),role,message});publish();};
 let cursor=0,timedOut=false;const runController=new AbortController();const cancelRun=()=>runController.abort();if(options.signal.aborted)cancelRun();else options.signal.addEventListener('abort',cancelRun,{once:true});
 const runTimer=setTimeout(()=>{timedOut=true;runController.abort();},MAX_RUN_TIMEOUT_MS);
 const one=async()=>{while(cursor<state.tasks.length&&!runController.signal.aborted){const task=state.tasks[cursor++];task.status='running';const start=performance.now();log(task.role,'Started on the immutable graph snapshot.');await new Promise<void>(resolve=>{
  let worker:Worker;try{worker=options.workerFactory?options.workerFactory():new Worker(new URL('./analysis.worker.ts',import.meta.url));}catch(error){task.status='failed';task.elapsedMs=Math.round(performance.now()-start);task.error=error instanceof Error?error.message:'Worker creation failed.';log(task.role,task.error);resolve();return;}
  let finished=false;let timer:ReturnType<typeof setTimeout>;const abort=()=>finish(timedOut?'failed':'canceled',undefined,timedOut?'Run time budget exceeded.':'Canceled by the user.');const finish=(status:TaskStatus,result?:Analysis,error?:string)=>{if(finished)return;finished=true;clearTimeout(timer);runController.signal.removeEventListener('abort',abort);worker.onmessage=null;worker.onerror=null;worker.terminate();task.status=status;task.elapsedMs=Math.round(performance.now()-start);task.error=error;if(result)state.results.push(result);log(task.role,error||status);resolve();};
  timer=setTimeout(()=>finish('failed',undefined,'Worker time budget exceeded.'),Math.min(30000,Math.max(100,Number.isFinite(options.timeoutMs)?options.timeoutMs:10000)));
  runController.signal.addEventListener('abort',abort,{once:true});worker.onmessage=e=>{const data=e.data;if(!data||typeof data!=='object'){finish('failed',undefined,'Worker returned an invalid response.');return;}if(data.ok===true&&validAnalysis(data.result,task.role))finish('complete',data.result);else finish('failed',undefined,typeof data.error==='string'?data.error:'Worker returned an invalid analysis.');};worker.onerror=e=>finish('failed',undefined,e.message||'Worker failed.');try{worker.postMessage({role:task.role,graph});}catch(error){finish('failed',undefined,error instanceof Error?error.message:'Could not send graph to worker.');}if(runController.signal.aborted)abort();
 });}};
 const concurrency=Number.isFinite(options.concurrency)?Math.min(3,Math.max(1,Math.floor(options.concurrency))):1;
 publish();
 return Promise.all(Array.from({length:concurrency},one)).then(()=>{clearTimeout(runTimer);options.signal.removeEventListener('abort',cancelRun);if(options.signal.aborted){state.tasks.forEach(t=>{if(t.status==='queued')t.status='canceled';});state.status='canceled';}else{if(timedOut)state.tasks.forEach(t=>{if(t.status==='queued'){t.status='failed';t.error='Run time budget exceeded.';}});state.status=state.tasks.every(t=>t.status==='complete')?'complete':'partial';}state.report=reconcile(graph,state.results);log('coordinator',state.report.summary);return state;});
}
