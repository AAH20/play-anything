import {type Snapshot,indexGraph,LIMITS} from './graph';
export const ROLES=['cartographer','dependencies','evidence'] as const;
export type Role=typeof ROLES[number];
export type Finding={title:string;detail:string;severity:'info'|'attention';nodeIds:string[];confidence:'observed'|'inferred'};
export type Analysis={role:Role;summary:string;findings:Finding[];metrics:Record<string,number>;durationMs:number};
export function analyze(role:Role,g:Snapshot):Analysis{
 const start=performance.now(),{nodes,out,incoming}=indexGraph(g);let findings:Finding[]=[],metrics:Record<string,number>={},summary='';
 if(role==='cartographer'){
  const counts:Record<string,number>={};for(const n of g.nodes)counts[n.kind]=(counts[n.kind]||0)+1;
  const ranked=g.nodes.filter(n=>n.kind!=='external'&&n.kind!=='module').map(n=>({n,degree:(out.get(n.id)||[]).filter(e=>!['contains','defines'].includes(e.relation)).length+(incoming.get(n.id)||[]).filter(e=>!['contains','defines'].includes(e.relation)).length})).sort((a,b)=>b.degree-a.degree||a.n.id.localeCompare(b.n.id));
  findings=ranked.slice(0,5).filter(x=>x.degree>0).map(({n,degree})=>({title:n.name,detail:`${degree} incident semantic relationships. A useful inspection starting point; degree does not establish business importance.`,severity:'info',nodeIds:[n.id],confidence:'observed'}));metrics=counts;summary=`${counts.file||0} files, ${counts.function||0} functions, ${counts.class||0} classes. Ranked structural entry points from indexed relationships.`;
 }
 if(role==='dependencies'){
  // Iterative Kosaraju: bounded by the graph, avoids recursive stack overflow.
  const adjacency=new Map<string,string[]>(),reverse=new Map<string,string[]>();
  for(const e of g.edges)if(['imports','calls','inherits'].includes(e.relation)&&['parsed','observed'].includes(e.confidence)){if(!adjacency.has(e.source))adjacency.set(e.source,[]);if(!reverse.has(e.target))reverse.set(e.target,[]);adjacency.get(e.source)!.push(e.target);reverse.get(e.target)!.push(e.source);}
  const visited=new Set<string>(),order:string[]=[];
  for(const root of nodes.keys()){if(visited.has(root))continue;visited.add(root);const stack:{id:string;cursor:number}[]=[{id:root,cursor:0}];while(stack.length){const top=stack[stack.length-1],neighbors=adjacency.get(top.id)||[];if(top.cursor<neighbors.length){const next=neighbors[top.cursor++];if(!visited.has(next)){visited.add(next);stack.push({id:next,cursor:0});}}else{order.push(top.id);stack.pop();}}}
  visited.clear();const components:string[][]=[];
  for(const root of order.reverse()){if(visited.has(root))continue;const group:string[]=[],stack=[root];visited.add(root);while(stack.length){const id=stack.pop()!;group.push(id);for(const next of reverse.get(id)||[])if(!visited.has(next)){visited.add(next);stack.push(next);}}if(group.length>1||(adjacency.get(root)||[]).includes(root))components.push(group);}
  components.sort((a,b)=>b.length-a.length||a[0].localeCompare(b[0]));findings=components.slice(0,8).map(ids=>({title:ids.length===1?'Recursive relationship':`${ids.length}-node dependency cycle`,detail:'Strongly connected component in parsed/observed imports, calls or inheritance. Recursion may be intentional; inspect the cited source before refactoring.',severity:'attention',nodeIds:ids.slice(0,20),confidence:'observed'}));metrics={cycles:components.length,semanticEdges:[...adjacency.values()].reduce((s,v)=>s+v.length,0)};summary=components.length?`${components.length} cyclic components to inspect. No inferred dispatch included.`:'No cycles found in the resolved semantic subgraph. Unresolved calls can hide additional relationships.';
 }
 if(role==='evidence'){
  const counts:Record<string,number>={};for(const e of g.edges)counts[e.confidence]=(counts[e.confidence]||0)+1;
  const inferred=g.edges.filter(e=>e.confidence==='inferred'),unresolved=Number(g.summary?.unresolved||0);
  if(inferred.length)findings.push({title:'Inferred relationships need review',detail:`${inferred.length} relationships depend on lexical hints or inferred dispatch. They are not runtime traces.`,severity:'attention',nodeIds:[...new Set(inferred.flatMap(e=>[e.source,e.target]))].slice(0,12),confidence:'inferred'});
  if(unresolved)findings.push({title:'Unresolved references',detail:`${unresolved} references could not be resolved. Absence of an edge is not proof that no dependency exists.`,severity:'attention',nodeIds:[],confidence:'observed'});
  if(g.truncated||g.warnings.length)findings.push({title:'Coverage constraints',detail:[g.truncated?'The source inventory was truncated.':'',...g.warnings].filter(Boolean).join(' ').slice(0,1200),severity:'attention',nodeIds:[],confidence:'observed'});
  metrics={...counts,unresolved};summary=`Evidence audit: ${counts.parsed||0} parsed, ${counts.observed||0} observed, ${counts.inferred||0} inferred relationships. Coverage limits remain attached to every report.`;
 }
 return {role,summary,findings:findings.slice(0,LIMITS.findings),metrics,durationMs:Math.round((performance.now()-start)*100)/100};
}
export function reconcile(g:Snapshot,results:Analysis[]){const ids=new Set(g.nodes.map(n=>n.id));const accepted:Finding[]=[],rejected:Finding[]=[];for(const result of results)for(const finding of result.findings)(finding.nodeIds.every(id=>ids.has(id))?accepted:rejected).push(finding);return {accepted:accepted.slice(0,LIMITS.findings),rejected,summary:`${results.length} specialists completed; ${accepted.length} evidence-linked findings, ${rejected.length} rejected for invalid references. Agreement does not upgrade inferred evidence to a fact.`};}
