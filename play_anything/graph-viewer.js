/* Reusable source graph: keyboard-accessible SVG and relationship lists. */
class RepoGraph extends HTMLElement {
  connectedCallback(){if(!this.ready){this.ready=true;this.renderShell();if(this._graph)this.draw();}}
  set graph(value){this._graph=value;this.selected=null;this.focused=false;if(this.ready)this.draw();}
  get graph(){return this._graph;}
  escape(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  renderShell(){
    this.innerHTML=`<div class="graph-shell"><div class="graph-heading"><div><span class="eyebrow">REPOSITORY INTELLIGENCE</span><h3>See the structure. Follow the relationships.</h3></div><button class="secondary graph-export">Export graph ↗</button></div><div class="graph-narrative" role="status">Analyze a repository or load a graph snapshot to begin.</div><div class="graph-controls"><label>Detail<select class="graph-level"><option value="module">Modules · simplified</option><option value="file">Files</option><option value="symbol">Functions & classes</option><option value="all">All kinds</option></select></label><label>Find a node<input class="graph-search" placeholder="Path, function, or module…" type="search"></label><label>Relationship<select class="graph-relation"><option value="all">All relationships</option><option>imports</option><option>calls</option><option>inherits</option><option>contains</option><option>defines</option></select></label><label class="graph-check"><input type="checkbox" class="graph-inferred" checked>Show inferred edges</label></div><div class="graph-layout"><div><div class="graph-canvas"><svg viewBox="0 0 920 510" role="group" aria-label="Interactive repository relationships"></svg><div class="graph-empty" hidden>No matching nodes. Try another detail level or search.</div></div><div class="graph-caption"></div><div class="graph-actions"><button class="quiet graph-prev">← Previous nodes</button><button class="quiet graph-reset">Show overview</button><button class="quiet graph-next">Next nodes →</button></div><div class="graph-legend"><span>● Module</span><span>■ File</span><span>◆ Function / class</span><span>Solid = parsed/observed · dashed = inferred/aggregated</span></div></div><aside class="graph-inspector"><h4>Choose a node</h4><p>Start with a module, then inspect its files, functions, and relationships.</p></aside></div><details class="graph-evidence"><summary>Coverage, unresolved references & analysis boundaries</summary><div></div></details></div>`;
    this.querySelectorAll('select,input').forEach(el=>el.addEventListener('input',()=>{this.page=0;this.draw();}));
    this.querySelector('.graph-prev').onclick=()=>{this.page=Math.max(0,(this.page||0)-1);this.draw();};
    this.querySelector('.graph-next').onclick=()=>{this.page=(this.page||0)+1;this.draw();};
    this.querySelector('.graph-reset').onclick=()=>{this.focused=false;this.selected=null;this.page=0;this.draw();};
    this.querySelector('.graph-export').onclick=()=>{if(!this._graph)return;const url=URL.createObjectURL(new Blob([JSON.stringify(this._graph,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='repository-graph.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  }
  select(id){this.selected=id;this.inspect();this.drawCanvas();}
  draw(){
    const g=this._graph;if(!g)return;
    this.lookup=new Map(g.nodes.map(n=>[n.id,n]));
    const summary=g.summary||{};
    this.querySelector('.graph-narrative').textContent=`${g.name}: ${summary.files||0} files across ${summary.modules||0} directories, with ${summary.functions||0} functions and ${summary.classes||0} classes. ${summary.relationships||g.edges.length} recorded relationships. Start with ${summary.hubs?.slice(0,3).join(', ')||'the root module'}, then follow imports into the implementation.`;
    const level=this.querySelector('.graph-level').value, query=this.querySelector('.graph-search').value.toLowerCase(),relation=this.querySelector('.graph-relation').value;
    const allowed=this.querySelector('.graph-inferred').checked;
    let edges=g.edges.filter(e=>(relation==='all'||e.relation===relation)&&(allowed||e.confidence!=='inferred'));
    let nodes=g.nodes.filter(n=>level==='all'||(level==='symbol'?['function','class'].includes(n.kind):n.kind===level));
    if(level==='module'){
      const owner=id=>{const n=this.lookup.get(id);if(!n||!n.path)return null;if(n.kind==='module')return n.id;const p=n.path.includes('/')?n.path.slice(0,n.path.lastIndexOf('/')):'.';return 'module:'+p;};
      const aggregated=new Map();
      edges.forEach(e=>{const source=owner(e.source),target=owner(e.target);if(source&&target&&source!==target){const key=source+'|'+target+'|'+e.relation;const previous=aggregated.get(key);aggregated.set(key,{source,target,relation:e.relation,confidence:'aggregated',count:(previous?.count||0)+1});}});
      edges=[...aggregated.values()];this.moduleEdges=edges.filter(e=>!['contains','defines'].includes(e.relation));
    }
    if(query)nodes=nodes.filter(n=>(n.name+' '+n.path).toLowerCase().includes(query));
    if(this.focused&&this.selected){const neighbors=new Set([this.selected]);g.edges.forEach(e=>{if(e.source===this.selected)neighbors.add(e.target);if(e.target===this.selected)neighbors.add(e.source);});nodes=g.nodes.filter(n=>neighbors.has(n.id));edges=g.edges.filter(e=>neighbors.has(e.source)&&neighbors.has(e.target)&&(relation==='all'||e.relation===relation)&&(allowed||e.confidence!=='inferred'));}
    nodes.sort((a,b)=>(b.connections||0)-(a.connections||0)||a.id.localeCompare(b.id));
    this.page=Math.min(this.page||0,Math.max(0,Math.ceil(nodes.length/36)-1));
    this.visible=nodes.slice(this.page*36,this.page*36+36);const ids=new Set(this.visible.map(n=>n.id));this.visibleEdges=edges.filter(e=>ids.has(e.source)&&ids.has(e.target));
    this.querySelector('.graph-caption').textContent=`Showing ${this.visible.length} of ${nodes.length} matching nodes · page ${this.page+1}/${Math.max(1,Math.ceil(nodes.length/36))}. ${this.visibleEdges.length} links on this page. Search or inspect a neighborhood to simplify; export retains the full indexed graph.`;
    this.querySelector('.graph-prev').disabled=this.page===0;this.querySelector('.graph-next').disabled=(this.page+1)*36>=nodes.length;
    this.querySelector('.graph-empty').hidden=!!this.visible.length;
    this.querySelector('.graph-evidence div').innerHTML=`<p>${g.truncated?'File limit reached. ':''}${this.escape((g.warnings||[]).join(' '))}</p><p>Python: AST declarations, imports, lexical calls and inheritance. Self/cls dispatch is inferred. JavaScript/TypeScript: lexical declaration/import hints only. Other files: inventory and containment. Runtime dispatch and unresolved references are not fabricated. Git-ignored untracked files, generated/vendor directories and symbolic links are excluded.</p><p>${summary.unresolved||0} references unresolved; ${(g.unresolved||[]).length>40?'first 40 shown; export includes up to 200':'listed below'}.</p><ul>${(g.unresolved||[]).slice(0,40).map(x=>`<li>${this.escape(x.path)}:${x.line} · ${this.escape(x.expression)}</li>`).join('')}</ul>`;
    this.drawCanvas();this.inspect();
  }
  drawCanvas(){
    if(!this.visible)return;const svg=this.querySelector('svg'),e=this.escape.bind(this);
    const positions=new Map();const columns=Math.min(6,Math.max(2,Math.ceil(Math.sqrt(this.visible.length))));const rows=Math.max(1,Math.ceil(this.visible.length/columns));
    this.visible.forEach((n,i)=>positions.set(n.id,{x:40+(i%columns)*(840/columns),y:35+Math.floor(i/columns)*(430/rows)}));
    const color=n=>({module:'#277965',file:'#557ab0',function:'#9560a6',class:'#b58037',external:'#8b9094'}[n.kind]);
    svg.innerHTML=`<defs><marker id="graph-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#95aaa0"/></marker></defs>`+this.visibleEdges.map(x=>{const a=positions.get(x.source),b=positions.get(x.target);return `<path d="M${a.x+45} ${a.y+20} Q${(a.x+b.x)/2+70} ${Math.min(a.y,b.y)-10} ${b.x+45} ${b.y+20}" fill="none" stroke="${this.selected&&(x.source===this.selected||x.target===this.selected)?'#277965':'#c4d4ca'}" stroke-width="1.4" ${['inferred','aggregated'].includes(x.confidence)?'stroke-dasharray="5 4"':''} marker-end="url(#graph-arrow)"><title>${e(x.relation)} · ${e(x.confidence)}${x.count?' · '+x.count+' links':''}</title></path>`;}).join('')+this.visible.map(n=>{const p=positions.get(n.id);return `<g role="button" tabindex="0" aria-label="Inspect ${e(n.kind)} ${e(n.name)}" data-node="${e(n.id)}" transform="translate(${p.x},${p.y})"><rect width="126" height="56" rx="10" fill="${this.selected===n.id?'#e0efd7':'#fff'}" stroke="${color(n)}" stroke-width="${this.selected===n.id?3:1}"/><circle cx="13" cy="16" r="4" fill="${color(n)}"/><text x="23" y="20" font-size="9" fill="#627168">${e(n.kind.toUpperCase())}</text><text x="10" y="40" font-size="10" fill="#1d352c">${e(n.name.length>18?n.name.slice(0,16)+'…':n.name)}</text><title>${e(n.path)}${n.line?':'+n.line:''} · ${e(n.name)}</title></g>`;}).join('');
    svg.querySelectorAll('[data-node]').forEach(n=>{n.onclick=()=>this.select(n.dataset.node);n.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();this.select(n.dataset.node);}};});
  }
  inspect(){
    const target=this.querySelector('.graph-inspector');const n=this.lookup?.get(this.selected);if(!n){target.innerHTML='<h4>Choose a node</h4><p>Inspect its summary, source location, incoming dependencies, and outgoing relationships.</p>';return;}
    const e=this.escape.bind(this),links=[...this._graph.edges.filter(x=>x.source===n.id||x.target===n.id),...(n.kind==='module'?(this.moduleEdges||[]).filter(x=>x.source===n.id||x.target===n.id):[])];
    target.innerHTML=`<span class="badge">${e(n.kind)} · ${e(n.confidence)}</span><h4>${e(n.name)}</h4><code>${e(n.path)}${n.line?':'+n.line:''}</code><p>${e(n.summary)}</p><button class="secondary graph-focus">Focus neighborhood</button><h5>${links.length} relationships</h5><ul>${links.slice(0,70).map(x=>{const other=this.lookup.get(x.source===n.id?x.target:x.source);return `<li><button class="quiet" data-related="${e(other.id)}">${x.source===n.id?'→':'←'} ${e(x.relation)} · ${e(other.name)}</button><small>${e(x.confidence)}${x.count?' · '+x.count+' links':''}${x.line?' · line '+x.line:''}</small></li>`;}).join('')}</ul>`;
    target.querySelector('.graph-focus').onclick=()=>{this.focused=true;this.page=0;this.draw();};
    target.querySelectorAll('[data-related]').forEach(b=>b.onclick=()=>{this.selected=b.dataset.related;this.focused=true;this.page=0;this.draw();});
  }
}
customElements.define('repo-graph',RepoGraph);
