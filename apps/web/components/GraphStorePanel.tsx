'use client';
import {useEffect,useRef,useState} from 'react';
import {Database,LoaderCircle} from 'lucide-react';
import {type Snapshot} from '@/lib/graph';

export default function GraphStorePanel({graph,onLoad}:{graph:Snapshot|null;onLoad:(value:unknown,label:string)=>void}){
 const [enabled,setEnabled]=useState(false),[token,setToken]=useState(''),[busy,setBusy]=useState(''),[message,setMessage]=useState('');
 const active=useRef<AbortController|null>(null),current=useRef(graph);current.current=graph;
 useEffect(()=>{const controller=new AbortController();fetch('/api/graph-store',{signal:controller.signal}).then(r=>r.json()).then(v=>setEnabled(v.enabled===true)).catch(()=>{});return()=>{controller.abort();active.current?.abort();};},[]);
 async function run(action:'load'|'save'){
  const controller=new AbortController();active.current?.abort();active.current=controller;const snapshot=graph;
  setBusy(action);setMessage('');
  try{
   const response=await fetch('/api/graph-store',{method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${token}`},body:JSON.stringify({action,...(action==='save'?{graph:snapshot}:{})}),signal:controller.signal});
   const result=await response.json();if(!response.ok)throw Error(result.error||'Graph storage request failed.');
   if(controller.signal.aborted)return;
   if(action==='load'){
    if(current.current!==snapshot){setMessage('A newer repository is open. Load again to replace it with the saved snapshot.');return;}
    onLoad(result.graph,'Neo4j · saved repository');
   }
   setMessage(`${action==='save'?'Saved':'Loaded'} ${action==='save'?snapshot?.name:'repository'} · revision ${String((typeof result.revision==='object'?result.revision?.revision:result.revision)||'').slice(0,12)}. ${action==='save'?'The configured workspace now points to this revision.':''}`);
  }catch(error){if(!controller.signal.aborted)setMessage(error instanceof Error?error.message:'Graph storage failed.');}
  finally{if(active.current===controller){active.current=null;setBusy('');}}
 }
 return <details className="graph-store-panel"><summary><Database size={15}/><strong>Neo4j graph storage</strong><span>{enabled?'Configured · connect on demand':'Optional · server configuration required'}</span></summary><div className="graph-store-body"><p>Save a versioned repository graph and load it back into this workspace. Database credentials stay on the server. Saving updates the active revision in the configured namespace.</p>{enabled?<><label>Workspace access token<input type="password" autoComplete="off" value={token} onChange={e=>setToken(e.target.value)} placeholder="Kept in memory for this session"/></label><div className="heading-actions"><button className="secondary-button" disabled={!token||!!busy||!graph} onClick={()=>run('save')}>{busy==='save'?<LoaderCircle size={14}/>:<Database size={14}/>}Save current graph</button><button className="secondary-button" disabled={!token||!!busy} onClick={()=>run('load')}>Load saved graph</button>{busy&&<button className="text-button" onClick={()=>{active.current?.abort();active.current=null;setBusy('');setMessage('Request cancelled. A save already committed by the server may still exist.');}}>Cancel</button>}</div></>:<p className="help-text">Set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, GRAPH_STORE_NAMESPACE and GRAPH_STORE_ACCESS_TOKEN in the optional web app’s server environment. This connection is separate from the export menu.</p>}<p role="status">{message}</p></div></details>;
}
