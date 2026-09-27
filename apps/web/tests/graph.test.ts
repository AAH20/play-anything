import test from 'node:test';
import assert from 'node:assert/strict';
import {filterGraph,neighborhood,parseSnapshot,semanticEdges,shortestPath,type Filters,type Snapshot} from '../lib/graph';
import {analyze,reconcile} from '../lib/analysis';

const graph=():Snapshot=>parseSnapshot({version:1,name:'sample',nodes:[
 {id:'m:.',name:'root',kind:'module',path:'.',summary:'',confidence:'observed'},
 {id:'f:a',name:'a.py',kind:'file',path:'a.py',summary:'alpha',confidence:'observed'},
 {id:'f:b',name:'b.py',kind:'file',path:'pkg/b.py',summary:'beta',confidence:'observed'},
 {id:'fn:a',name:'start',kind:'function',path:'a.py',summary:'entry',confidence:'parsed'},
 {id:'fn:b',name:'finish',kind:'function',path:'pkg/b.py',summary:'exit',confidence:'inferred'}
],edges:[
 {source:'m:.',target:'f:a',relation:'contains',confidence:'observed'},
 {source:'m:.',target:'f:b',relation:'contains',confidence:'observed'},
 {source:'f:a',target:'fn:a',relation:'defines',confidence:'parsed'},
 {source:'fn:a',target:'fn:b',relation:'calls',confidence:'parsed'},
 {source:'fn:b',target:'fn:a',relation:'calls',confidence:'observed'},
 {source:'fn:a',target:'fn:b',relation:'dispatch',confidence:'inferred'}
],warnings:[],truncated:false,summary:{unresolved:2},unresolved:[]});

test('parseSnapshot rejects malformed, dangling, oversized and invalid metadata',()=>{
 const base={version:1,name:'x',nodes:[],edges:[],warnings:[],truncated:false};
 assert.throws(()=>parseSnapshot({...base,version:0}));
 assert.throws(()=>parseSnapshot({...base,nodes:[{id:'x',name:'x',kind:'file',path:'x',confidence:'bogus'}]}));
 assert.throws(()=>parseSnapshot({...base,nodes:[{id:'x',name:'x',kind:'file',path:'x',confidence:'parsed'}],edges:[{source:'x',target:'missing',relation:'calls',confidence:'parsed'}]}));
 assert.throws(()=>parseSnapshot({...base,summary:{unresolved:-1}}));
 assert.throws(()=>parseSnapshot({...base,name:'x'.repeat(15_000_001)}));
});

test('neighborhood directions, shortest path direction and filters are deterministic',()=>{
 const g=graph();
 assert.deepEqual([...neighborhood(g,'fn:a',1,'out')].sort(),['fn:a','fn:b']);
 assert.deepEqual([...neighborhood(g,'fn:a',1,'in')].sort(),['f:a','fn:a','fn:b']);
 assert.deepEqual(shortestPath(g,'fn:a','fn:b'),['fn:a','fn:b']);
 assert.deepEqual(shortestPath(g,'fn:b','fn:a'),['fn:b','fn:a']);
 const filtered=filterGraph(g,{query:'entry',kind:'all',relation:'all',evidence:'grounded',directory:'all',view:'symbols',focus:null,hops:1,direction:'both'});
 assert.deepEqual(filtered.nodes.map(n=>n.id),['fn:a']);
 assert.equal(filtered.edges.length,0);
});

test('grounded evidence filters nodes and edges, and root directory includes root files only',()=>{
 const g=graph();const base:Filters={query:'',kind:'all',relation:'all',evidence:'grounded',directory:'all',view:'all',focus:null,hops:1,direction:'both'};
 const grounded=filterGraph(g,base);
 assert.ok(grounded.nodes.every(n=>['parsed','observed'].includes(n.confidence)));
 assert.ok(grounded.edges.every(e=>['parsed','observed'].includes(e.confidence)));
 const inferred=filterGraph(g,{...base,evidence:'inferred'});
 assert.ok(inferred.nodes.every(n=>n.confidence==='inferred'));
 assert.ok(inferred.edges.every(e=>e.confidence==='inferred'));
 const root=filterGraph(g,{...base,evidence:'all',directory:'.'});
 assert.ok(root.nodes.some(n=>n.id==='f:a'));
 assert.ok(!root.nodes.some(n=>n.id==='f:b'));
 assert.ok(semanticEdges(g,'grounded').every(e=>!['contains','defines'].includes(e.relation)));
});

test('shortestPath follows directed edges and semantic evidence selection',()=>{
 const g=parseSnapshot({version:1,name:'directed',nodes:[
  {id:'a',name:'a',kind:'file',path:'a',confidence:'parsed'},
  {id:'b',name:'b',kind:'file',path:'b',confidence:'parsed'},
  {id:'c',name:'c',kind:'file',path:'c',confidence:'parsed'}
 ],edges:[{source:'a',target:'b',relation:'calls',confidence:'parsed'},{source:'b',target:'c',relation:'calls',confidence:'inferred'}],warnings:[],truncated:false});
 assert.deepEqual(shortestPath({...g,edges:semanticEdges(g,'grounded')},'a','b'),['a','b']);
 assert.deepEqual(shortestPath({...g,edges:semanticEdges(g,'grounded')},'b','a'),[]);
 assert.deepEqual(shortestPath({...g,edges:semanticEdges(g,'grounded')},'a','c'),[]);
 assert.deepEqual(shortestPath({...g,edges:semanticEdges(g,'all')},'a','c'),['a','b','c']);
});

test('filtered view caps rendered relationships independently from nodes',()=>{
 const graphWithDenseEdgeSet=parseSnapshot({version:1,name:'dense',nodes:[{id:'a',name:'A',kind:'file',path:'a',confidence:'parsed'},{id:'b',name:'B',kind:'file',path:'b',confidence:'parsed'}],edges:Array.from({length:12_001},()=>({source:'a',target:'b',relation:'calls',confidence:'parsed'})),warnings:[],truncated:false});
 const result=filterGraph(graphWithDenseEdgeSet,{query:'',kind:'all',relation:'all',evidence:'all',directory:'all',view:'all',focus:null,hops:1,direction:'both'});
 assert.equal(result.edges.length,12_000);
 assert.equal(result.matchingEdges,12_001);
 assert.equal(result.edgeCapped,true);
});

test('dependency and evidence analysis labels cycles and unresolved coverage',()=>{
 const g=graph();const cycles=analyze('dependencies',g);
 assert.equal(cycles.metrics.cycles,1);assert.match(cycles.findings[0].detail,/Strongly connected/);
 const audit=analyze('evidence',g);
 assert.equal(audit.metrics.unresolved,2);assert.ok(audit.findings.some(f=>f.title==='Inferred relationships need review'));
 assert.ok(audit.findings.some(f=>f.title==='Unresolved references'));
 const reconciled=reconcile(g,[{...audit,findings:[...audit.findings,{...audit.findings[0],nodeIds:['unknown']}]}]);
 assert.equal(reconciled.rejected.length,1);
 assert.ok(reconciled.summary.includes('Agreement does not upgrade inferred evidence'));
});
