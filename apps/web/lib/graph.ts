export const LIMITS={nodes:25000,edges:100000,bytes:15000000,visible:1800,visibleEdges:12000,findings:24};
export const KINDS=['module','file','function','class','external'] as const;
export type Kind=typeof KINDS[number];
export type Evidence='parsed'|'observed'|'inferred'|'illustrative'|'aggregated';
export type GraphNode={id:string;name:string;kind:Kind;path:string;summary:string;confidence:Evidence;line?:number;connections?:number};
export type GraphEdge={source:string;target:string;relation:string;confidence:Evidence;line?:number;count?:number};
export type Snapshot={version:number;name:string;nodes:GraphNode[];edges:GraphEdge[];warnings:string[];truncated:boolean;summary?:{unresolved?:number;[key:string]:unknown};unresolved?:{path:string;line:number;expression:string}[]};
export type SnapshotDescriptor={id:string;version:number;name:string;nodeCount:number;edgeCount:number;nodeEvidence:Record<Evidence,number>;edgeEvidence:Record<Evidence,number>;constraints:{truncated:boolean;warnings:string[];warningCount:number;unresolved:number;unresolvedTruncated:boolean}};
const evidence=new Set(['parsed','observed','inferred','illustrative','aggregated']);
function string(v:unknown,max:number){return typeof v==='string'&&v.length<=max;}
export function parseSnapshot(value:unknown):Snapshot{
 if(!value||typeof value!=='object')throw Error('Expected a graph object.');
 const g=value as Snapshot;
 let size:number;try{size=new TextEncoder().encode(JSON.stringify(value)).length;}catch{throw Error('Graph must be valid JSON data.');}
 if(size>LIMITS.bytes||!Number.isInteger(g.version)||g.version<1||!string(g.name,500)||!Array.isArray(g.nodes)||!Array.isArray(g.edges)||g.nodes.length>LIMITS.nodes||g.edges.length>LIMITS.edges)throw Error('Graph exceeds its size limits, or has an invalid shape.');
 const ids=new Set<string>();
 for(const n of g.nodes){if(!n||!string(n.id,2000)||!n.id||ids.has(n.id)||!string(n.name,2000)||!string(n.path,4000)||!KINDS.includes(n.kind)||!evidence.has(n.confidence)||!string(n.summary??'',10000)||(n.line!==undefined&&(!Number.isInteger(n.line)||n.line<1))||(n.connections!==undefined&&(!Number.isInteger(n.connections)||n.connections<0)))throw Error('Invalid or duplicate graph node.');ids.add(n.id);}
 for(const e of g.edges)if(!e||!string(e.source,2000)||!string(e.target,2000)||!ids.has(e.source)||!ids.has(e.target)||!string(e.relation,100)||!e.relation||!evidence.has(e.confidence)||(e.line!==undefined&&(!Number.isInteger(e.line)||e.line<1&&!(e.line===0&&e.relation==='contains')))||(e.count!==undefined&&(!Number.isInteger(e.count)||e.count<1)))throw Error('Graph has a missing endpoint or invalid relationship.');
 if(g.warnings!==undefined&&(!Array.isArray(g.warnings)||g.warnings.length>1000||g.warnings.some(w=>!string(w,10000))))throw Error('Invalid coverage warnings.');
 if(g.summary!==undefined&&(!g.summary||typeof g.summary!=='object'||Array.isArray(g.summary)||(g.summary.unresolved!==undefined&&(!Number.isInteger(g.summary.unresolved)||Number(g.summary.unresolved)<0))))throw Error('Invalid graph summary.');
 if(g.unresolved!==undefined&&(!Array.isArray(g.unresolved)||g.unresolved.length>200||g.unresolved.some(item=>!item||!string(item.path,4000)||!Number.isInteger(item.line)||item.line<1||!string(item.expression,2000))))throw Error('Invalid unresolved-reference list.');
 return {...g,nodes:g.nodes.map(n=>({...n,summary:n.summary||''})),warnings:g.warnings||[],truncated:!!g.truncated};
}
export function describeSnapshot(g:Snapshot):SnapshotDescriptor{
 const source=JSON.stringify(g);let first=0x811c9dc5,second=0x9e3779b9;
 for(let i=0;i<source.length;i++){const code=source.charCodeAt(i);first=Math.imul(first^code,0x01000193);second=Math.imul(second^code,0x85ebca6b);}
 const count=(items:{confidence:Evidence}[])=>items.reduce((result,item)=>{result[item.confidence]++;return result;},{parsed:0,observed:0,inferred:0,illustrative:0,aggregated:0} as Record<Evidence,number>);
 return {id:`graph-v${g.version}-${(first>>>0).toString(16).padStart(8,'0')}${(second>>>0).toString(16).padStart(8,'0')}`,version:g.version,name:g.name,nodeCount:g.nodes.length,edgeCount:g.edges.length,nodeEvidence:count(g.nodes),edgeEvidence:count(g.edges),constraints:{truncated:g.truncated,warnings:g.warnings.slice(0,20).map(w=>w.slice(0,500)),warningCount:g.warnings.length,unresolved:Number(g.summary?.unresolved||0),unresolvedTruncated:Boolean((g as Snapshot&{unresolved_truncated?:boolean}).unresolved_truncated)}};
}
export function indexGraph(g:Snapshot){const nodes=new Map(g.nodes.map(n=>[n.id,n]));const out=new Map<string,GraphEdge[]>(),incoming=new Map<string,GraphEdge[]>();for(const e of g.edges){if(!out.has(e.source))out.set(e.source,[]);if(!incoming.has(e.target))incoming.set(e.target,[]);out.get(e.source)!.push(e);incoming.get(e.target)!.push(e);}return {nodes,out,incoming};}
export function neighborhood(g:Snapshot,start:string,hops:number,direction:'both'|'out'|'in'='both',max=LIMITS.visible){const index=indexGraph(g),seen=new Set<string>();if(!index.nodes.has(start))return seen;seen.add(start);let frontier=[start];for(let depth=0;depth<Math.min(4,Math.max(0,hops));depth++){const next:string[]=[];for(const id of frontier){const edges=[...(direction!=='in'?index.out.get(id)||[]:[]),...(direction!=='out'?index.incoming.get(id)||[]:[])];for(const e of edges){const other=e.source===id?e.target:e.source;if(!seen.has(other)){if(seen.size>=max)return seen;seen.add(other);next.push(other);}}}frontier=next;}return seen;}
export function shortestPath(g:Snapshot,start:string,target:string){const {out,nodes}=indexGraph(g);if(!nodes.has(start)||!nodes.has(target))return [];const parent=new Map<string,string|null>([[start,null]]),queue=[start];for(let i=0;i<queue.length;i++){const id=queue[i];if(id===target){const path:string[]=[];let next:string|null=id;while(next!==null){path.push(next);next=parent.get(next)??null;}return path.reverse();}for(const e of out.get(id)||[])if(!parent.has(e.target)){parent.set(e.target,id);queue.push(e.target);}}return [];}
export function evidenceMatches(confidence:Evidence,filter:string){return filter==='all'||(filter==='grounded'?confidence==='parsed'||confidence==='observed':confidence===filter);}
export function semanticEdges(g:Snapshot,evidence='all'){return g.edges.filter(e=>!['contains','defines'].includes(e.relation)&&evidenceMatches(e.confidence,evidence));}
export type Filters={query:string;kind:string;relation:string;evidence:string;directory:string;view:'modules'|'files'|'symbols'|'all';focus:string|null;hops:number;direction:'both'|'out'|'in'};
export function filterGraph(g:Snapshot,f:Filters){let edges=g.edges.filter(e=>(f.relation==='all'||e.relation===f.relation)&&(f.evidence==='all'||(f.evidence==='grounded'?['parsed','observed'].includes(e.confidence):e.confidence===f.evidence)));
 let nodes=g.nodes;
 if(f.view==='modules'&&!f.focus){const byId=new Map(nodes.map(n=>[n.id,n]));const owner=(id:string)=>{const n=byId.get(id);if(!n||!n.path)return null;return n.kind==='module'?n.id:'module:'+(n.path.includes('/')?n.path.slice(0,n.path.lastIndexOf('/')):'.');};const grouped=new Map<string,GraphEdge>();for(const e of edges){const source=owner(e.source),target=owner(e.target);if(source&&target&&source!==target&&byId.has(source)&&byId.has(target)){const key=JSON.stringify([source,target,e.relation]);const old=grouped.get(key);grouped.set(key,{source,target,relation:e.relation,confidence:'aggregated',count:(old?.count||0)+1});}}edges=[...grouped.values()];nodes=nodes.filter(n=>n.kind==='module');}
 else if(!f.focus){nodes=nodes.filter(n=>f.view==='all'||(f.view==='symbols'?['function','class'].includes(n.kind):n.kind==='file'));}
 if(f.focus){const ids=neighborhood({...g,edges},f.focus,f.hops,f.direction);nodes=nodes.filter(n=>ids.has(n.id));}
 const q=f.query.toLocaleLowerCase().trim();
 const inDirectory=(path:string)=>f.directory==='all'||(f.directory==='.'?(path==='.'||!path.includes('/')):(path===f.directory||path.startsWith(f.directory+'/')));
 nodes=nodes.filter(n=>evidenceMatches(n.confidence,f.evidence)&&(f.kind==='all'||n.kind===f.kind)&&inDirectory(n.path)&&(!q||(n.name+' '+n.path+' '+n.summary).toLocaleLowerCase().includes(q)));
 nodes=[...nodes].sort((a,b)=>(b.connections||0)-(a.connections||0)||a.id.localeCompare(b.id));const matching=nodes.length;nodes=nodes.slice(0,LIMITS.visible);const ids=new Set(nodes.map(n=>n.id));edges=edges.filter(e=>ids.has(e.source)&&ids.has(e.target));const matchingEdges=edges.length;edges=edges.slice(0,LIMITS.visibleEdges);return {nodes,edges,matching,capped:matching>nodes.length,matchingEdges,edgeCapped:matchingEdges>edges.length};
}
export function downloadJSON(name:string,value:unknown){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
