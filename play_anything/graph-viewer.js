/* Reusable source graph: keyboard-accessible SVG and relationship lists. */
globalThis.playAnythingCreateRequestGate=globalThis.playAnythingCreateRequestGate||function(){
  let revision=0;
  return {begin:()=>++revision,invalidate:()=>++revision,isCurrent:value=>value===revision};
};
function validateGraphSnapshot(graph){
  const fail=message=>{throw new TypeError(`Invalid graph snapshot: ${message}`);};
  const text=(value,label,max,optional=false)=>{
    if(optional&&value==null)return;
    if(typeof value!=='string'||value.length>max)fail(`${label} must be text of at most ${max} characters.`);
  };
  const count=(value,label,optional=false)=>{
    if(optional&&value==null)return;
    if(!Number.isSafeInteger(value)||value<0)fail(`${label} must be a nonnegative safe integer.`);
  };
  const bool=(value,label,optional=false)=>{if(optional&&value==null)return;if(typeof value!=='boolean')fail(`${label} must be a boolean.`);};
  const exactInteger=(value,label)=>{
    if(typeof value!=='string'||value.length<16||value.length>19||! /^(0|[1-9][0-9]*)$/.test(value)||
      (value.length===19&&value>'9223372036854775807')||
      (value.length===16&&value<='9007199254740991'))fail(`${label} must be a canonical decimal integer above JavaScript's safe range and at most 9223372036854775807.`);
  };
  const countWithExact=(record,key,label,{optional=true,nullable=false}={})=>{
    const exactKey=`${key}_exact`,hasExact=Object.prototype.hasOwnProperty.call(record,exactKey);
    if(hasExact){if(record[key]!==null)fail(`${label} must be null when ${exactKey} is present.`);exactInteger(record[exactKey],exactKey);return;}
    const value=record[key];
    if(value===undefined&&optional)return;
    if(value===null&&nullable)return;
    count(value,label,false);
  };
  const validateSourceMetrics=(record,label)=>{
    bool(record.source_metrics_available,`${label} source_metrics_available`,true);
    if(record.source_metrics_available===false){
      for(const key of ['source_budget_bytes','source_bytes_read','source_budget_exceeded_files']){
        if(Object.prototype.hasOwnProperty.call(record,`${key}_exact`))fail(`${label} ${key}_exact cannot appear when source metrics are unavailable.`);
        if(Object.prototype.hasOwnProperty.call(record,key)&&record[key]!==null)fail(`${label} ${key} must be null when source metrics are unavailable.`);
      }
      if(Object.prototype.hasOwnProperty.call(record,'source_budget_exhausted')&&record.source_budget_exhausted!==null)fail(`${label} source_budget_exhausted must be null when source metrics are unavailable.`);
      return;
    }
    if(record.source_metrics_available===true){
      for(const key of ['source_bytes_read','source_budget_exceeded_files']){
        if(!Object.prototype.hasOwnProperty.call(record,key))fail(`${label} ${key} is required when source metrics are available.`);
        countWithExact(record,key,`${label} ${key}`);
      }
      if(!Object.prototype.hasOwnProperty.call(record,'source_budget_bytes'))fail(`${label} source_budget_bytes is required when source metrics are available.`);
      countWithExact(record,'source_budget_bytes',`${label} source_budget_bytes`,{nullable:true});
      bool(record.source_budget_exhausted,`${label} source_budget_exhausted`);
    }
  };
  if(!graph||typeof graph!=='object'||Array.isArray(graph))fail('the root must be an object.');
  if(graph.version!=null&&graph.version!==1)fail('only version 1 snapshots are supported.');
  if(!Array.isArray(graph.nodes)||!Array.isArray(graph.edges))fail('nodes and edges must be arrays.');
  if(graph.nodes.length>65000)fail('no more than 65,000 nodes are supported.');
  if(graph.edges.length>250000)fail('no more than 250,000 edges are supported.');
  text(graph.name??'Repository','name',512);
  if(graph.name==='')fail('name must not be empty.');
  const ids=new Set();
  for(const [i,node] of graph.nodes.entries()){
    if(!node||typeof node!=='object'||Array.isArray(node))fail(`node ${i+1} must be an object.`);
    text(node.id,`node ${i+1} id`,8192);text(node.name,`node ${i+1} name`,4096);text(node.path,`node ${i+1} path`,8192);
    if(!node.id||!node.name||!['module','file','function','class','external'].includes(node.kind))fail(`node ${i+1} has an unsupported identity or kind.`);
    if(ids.has(node.id))fail(`duplicate node id “${node.id.slice(0,80)}”.`);ids.add(node.id);
    text(node.summary,`node ${i+1} summary`,8192,true);text(node.confidence,`node ${i+1} confidence`,128,true);
    count(node.line,`node ${i+1} line`,true);count(node.connections,`node ${i+1} connections`,true);
  }
  for(const [i,edge] of graph.edges.entries()){
    if(!edge||typeof edge!=='object'||Array.isArray(edge))fail(`edge ${i+1} must be an object.`);
    text(edge.source,`edge ${i+1} source`,8192);text(edge.target,`edge ${i+1} target`,8192);text(edge.relation,`edge ${i+1} relation`,128);
    if(!edge.relation)fail(`edge ${i+1} relation must not be empty.`);
    if(!ids.has(edge.source)||!ids.has(edge.target))fail(`edge ${i+1} refers to a missing node.`);
    text(edge.confidence,`edge ${i+1} confidence`,128,true);count(edge.line,`edge ${i+1} line`,true);count(edge.count,`edge ${i+1} count`,true);
  }
  if(graph.summary!=null){
    if(!graph.summary||typeof graph.summary!=='object'||Array.isArray(graph.summary))fail('summary must be an object.');
    for(const key of ['files','modules','functions','classes','relationships','unresolved'])count(graph.summary[key],`summary ${key}`,true);
    if(graph.summary.hubs!=null&&(!Array.isArray(graph.summary.hubs)||graph.summary.hubs.length>100))fail('summary hubs must contain at most 100 entries.');
    for(const [i,hub] of (graph.summary.hubs||[]).entries())text(hub,`summary hub ${i+1}`,4096);
  }
  if(graph.warnings!=null){if(!Array.isArray(graph.warnings)||graph.warnings.length>10000)fail('warnings must contain at most 10,000 entries.');graph.warnings.forEach((item,i)=>text(item,`warning ${i+1}`,8192));}
  if(graph.unresolved!=null){if(!Array.isArray(graph.unresolved)||graph.unresolved.length>200)fail('unresolved references must contain at most 200 entries.');graph.unresolved.forEach((item,i)=>{if(!item||typeof item!=='object'||Array.isArray(item))fail(`unresolved reference ${i+1} must be an object.`);text(item.path,`unresolved path ${i+1}`,8192);text(item.expression,`unresolved expression ${i+1}`,8192);count(item.line,`unresolved line ${i+1}`);text(item.relation,`unresolved relation ${i+1}`,128,true);});}
  for(const key of ['truncated','unresolved_truncated'])bool(graph[key],key,true);
  if(graph.analysis!=null){
    const a=graph.analysis;if(!a||typeof a!=='object'||Array.isArray(a))fail('analysis must be an object.');
    text(a.status,'analysis status',64,true);text(a.source_kind,'analysis source kind',128,true);text(a.message,'analysis message',2048,true);
    for(const key of ['complete','sample_fallback'])bool(a[key],`analysis ${key}`,true);
    for(const key of ['file_count','matching_files','returned_files','analyzed_files','unparsed_files','parse_errors','unreadable_files','too_large_files','graph_source_bytes_read','graph_source_budget_bytes','graph_source_budget_exceeded_files','graph_file_count','graph_unparsed_files','graph_parse_errors','graph_unreadable_files','graph_too_large_files','graph_file_limit','graph_symbol_limit'])count(a[key],`analysis ${key}`,true);
    for(const key of ['file_limit','max_file_bytes','source_budget_bytes','source_bytes_read','source_budget_exceeded_files'])countWithExact(a,key,`analysis ${key}`,{nullable:['file_limit','max_file_bytes','source_budget_bytes'].includes(key)||a.source_metrics_available!==true});
    for(const key of ['file_limit_reached','source_budget_exhausted','graph_source_budget_exhausted','graph_file_limit_reached','graph_symbol_limit_reached'])bool(a[key],`analysis ${key}`,true);
    validateSourceMetrics(a,'analysis');
    const analysisExclusions=a.source_budget_exceeded_files_exact??a.source_budget_exceeded_files;
    if(a.complete===true&&analysisExclusions!=null&&analysisExclusions!=='0'&&analysisExclusions!==0)fail('complete analysis cannot include source-budget exclusions.');
    if(a.warnings!=null&&(!Array.isArray(a.warnings)||a.warnings.length>10000))fail('analysis warnings must contain at most 10,000 entries.');
  }
  if(graph.coverage!=null){
    const c=graph.coverage;if(!c||typeof c!=='object'||Array.isArray(c))fail('coverage must be an object.');
    text(c.status,'coverage status',64);if(!['complete','partial'].includes(c.status))fail('coverage status must be complete or partial.');
    text(c.generation,'coverage generation',256);
    for(const key of ['complete','has_previous','has_next','filtered','source_partial','imports_partial','scan_truncated'])bool(c[key],`coverage ${key}`);
    for(const key of ['total_nodes','matching_nodes','offset','page_size','returned_nodes','total_import_edges','returned_page_edges','omitted_page_edges','omitted_cross_page_edges','max_edges'])count(c[key],`coverage ${key}`);
    for(const key of ['max_files','max_file_bytes','max_total_source_bytes','source_budget_bytes'])countWithExact(c,key,`coverage ${key}`,{nullable:true});
    for(const key of ['source_bytes_read','source_budget_exceeded_files'])countWithExact(c,key,`coverage ${key}`,{nullable:c.source_metrics_available!==true});
    bool(c.source_budget_exhausted,'coverage source_budget_exhausted',true);
    validateSourceMetrics(c,'coverage');
    if(c.source_metrics_available!==false&&Object.prototype.hasOwnProperty.call(c,'max_total_source_bytes')&&Object.prototype.hasOwnProperty.call(c,'source_budget_bytes')){
      const configured=c.max_total_source_bytes===null?null:(c.max_total_source_bytes_exact??String(c.max_total_source_bytes));
      const measured=c.source_budget_bytes===null?null:(c.source_budget_bytes_exact??String(c.source_budget_bytes));
      if(configured!==measured)fail('coverage total source-byte cap fields disagree.');
    }
    if(c.returned_nodes!==graph.nodes.length||c.returned_page_edges!==graph.edges.length)fail('coverage returned counts must match nodes and edges lengths.');
    if(!c.page_size||c.matching_nodes>c.total_nodes||(c.offset>c.matching_nodes&&c.returned_nodes>0)||c.returned_nodes>c.page_size||(c.returned_nodes>0&&c.offset+c.returned_nodes>c.matching_nodes)||c.returned_page_edges>c.total_import_edges)fail('coverage counts are inconsistent.');
    if(c.has_previous!==(c.offset>0&&c.matching_nodes>0)||c.has_next!==(c.offset+c.returned_nodes<c.matching_nodes)||c.complete!==(c.status==='complete'))fail('coverage status or page flags are inconsistent.');
    const coverageExclusions=c.source_budget_exceeded_files_exact??c.source_budget_exceeded_files;
    if(coverageExclusions!=null&&coverageExclusions!=='0'&&coverageExclusions!==0&&!c.source_partial)fail('known source-budget exclusions require source_partial coverage.');
    if(c.complete&&(c.filtered||c.has_previous||c.has_next||c.source_partial||c.imports_partial||c.scan_truncated||c.omitted_page_edges||c.omitted_cross_page_edges||
      (coverageExclusions!=null&&coverageExclusions!=='0'&&coverageExclusions!==0)))fail('complete coverage cannot include filters, partial scans, pagination, omitted imports, or source-budget exclusions.');
  }
  return graph;
}
function safeExactDisplay(value,exact){
  if(Number.isSafeInteger(value)&&value>=0)return String(value);
  if(value===null&&typeof exact==='string'&&exact.length>=16&&exact.length<=19&&/^(0|[1-9][0-9]*)$/.test(exact)&&
    !(exact.length===16&&exact<='9007199254740991')&&!(exact.length===19&&exact>'9223372036854775807'))return exact;
  return null;
}

class RepoGraph extends HTMLElement {
  connectedCallback(){if(!this.ready){this.ready=true;this.renderShell();if(this._graph)this.draw();}}
  set graph(value){this._graph=validateGraphSnapshot(value);this.selected=null;this.focused=false;this.page=0;this.incidentEdges=new Map();for(const edge of this._graph.edges){for(const id of [edge.source,edge.target]){if(!this.incidentEdges.has(id))this.incidentEdges.set(id,[]);this.incidentEdges.get(id).push(edge);}}if(this.ready){if(this._graph.coverage&&this._graph.nodes.every(n=>n.kind==='file'))this.querySelector('.graph-level').value='file';this.draw();}}
  get graph(){return this._graph;}
  clear(){this._graph=null;this.selected=null;this.focused=false;this.page=0;this.lookup=null;this.visible=null;this.visibleEdges=null;this.incidentEdges=new Map();this.moduleEdges=[];if(this.ready)this.renderShell();}
  escape(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
  formatAnalysis(analysis){
    if(!analysis)return 'Source-analysis completeness is unavailable in this graph snapshot.';
    if(analysis.source_kind==='synthetic_demo')return analysis.message||'Illustrative synthetic demo; no repository files were analyzed.';
    const message=analysis.message||(analysis.status==='complete'?'Complete within the reported analysis scope.':analysis.status==='empty'?'No supported source files were found.':'Partial analysis; review the coverage details.');
    const details=[];
    const count=(label,value,exact)=>{const shown=safeExactDisplay(value,exact);if(shown!==null)details.push(`${shown} ${label}`);};
    count('files indexed',analysis.file_count);
    count('Python files parsed by AST',analysis.analyzed_files);
    count('files outside Python AST parsing',analysis.unparsed_files);
    count('Python parse failures',analysis.parse_errors);
    count('unreadable files',analysis.unreadable_files);
    count('files above the summary byte cap',analysis.too_large_files);
    count('files skipped by the total source byte budget',analysis.source_budget_exceeded_files,analysis.source_budget_exceeded_files_exact);
    count('source bytes read',analysis.source_bytes_read,analysis.source_bytes_read_exact);
    const sourceBudget=safeExactDisplay(analysis.source_budget_bytes,analysis.source_budget_bytes_exact);
    if(sourceBudget!==null)details.push(`total source byte budget ${sourceBudget} bytes`);
    if(analysis.source_metrics_available===false)details.push('source-byte metrics are unavailable for this older index generation');
    if(analysis.source_budget_exhausted)details.push('the total source byte budget was exhausted');
    count('graph files parsed',analysis.graph_file_count);
    count('graph files outside its language parsers',analysis.graph_unparsed_files);
    count('graph parse failures',analysis.graph_parse_errors);
    count('graph unreadable files',analysis.graph_unreadable_files);
    count('graph files above its byte cap',analysis.graph_too_large_files);
    count('graph files skipped by the total source byte budget',analysis.graph_source_budget_exceeded_files);
    count('graph source bytes read',analysis.graph_source_bytes_read);
    if(Number.isSafeInteger(analysis.graph_source_budget_bytes)&&analysis.graph_source_budget_bytes>=0)details.push(`graph total source byte budget ${analysis.graph_source_budget_bytes} bytes`);
    if(analysis.graph_source_budget_exhausted)details.push('the graph source byte budget was exhausted');
    const fileLimit=safeExactDisplay(analysis.file_limit,analysis.file_limit_exact);
    if(analysis.file_limit_reached)details.push(`the ${fileLimit??'configured'}-file summary limit was reached`);
    const fileBytes=safeExactDisplay(analysis.max_file_bytes,analysis.max_file_bytes_exact);
    if(fileBytes!==null)details.push(`summary per-file byte cap ${fileBytes}`);
    if(analysis.graph_file_limit_reached)details.push('the graph file limit was reached');
    if(analysis.graph_symbol_limit_reached)details.push('the graph symbol limit was reached');
    if(Array.isArray(analysis.warnings)&&analysis.warnings.length)details.push(`${analysis.warnings.length} graph warnings (see coverage details)`);
    return details.length?`${message} ${details.join('; ')}.`:message;
  }
  formatCoverage(coverage){
    if(!coverage)return '';
    const first=coverage.offset+1,last=coverage.offset+coverage.returned_nodes;
    const pageLabel=coverage.returned_nodes?`${first}–${last}`:coverage.matching_nodes?`at offset ${coverage.offset} (no rows returned)`:'with no matching paths';
    const parts=[`Imported SQLite graph page ${pageLabel} of ${coverage.matching_nodes} matching / ${coverage.total_nodes} indexed files.`];
    parts.push('Canvas paging stays inside this imported page.');
    if(coverage.filtered)parts.push('A path filter was applied when this page was exported.');
    if(coverage.omitted_page_edges)parts.push(`${coverage.omitted_page_edges} imports within this page were omitted by its edge cap.`);
    if(coverage.omitted_cross_page_edges)parts.push(`${coverage.omitted_cross_page_edges} imports cross this page boundary.`);
    if(coverage.source_partial||coverage.imports_partial||coverage.scan_truncated)parts.push('The source inventory or static import scan is partial; see the warnings below.');
    if(coverage.has_next)parts.push(`Export the next database page with query-repository --view graph --offset ${coverage.offset+coverage.page_size}.`);
    if(coverage.has_previous)parts.push(`A previous database page starts at offset ${Math.max(0,coverage.offset-coverage.page_size)}.`);
    if(!coverage.has_previous&&!coverage.has_next&&coverage.complete)parts.push('This export covers all indexed files and represented imports.');
    if(coverage.source_metrics_available===false){
      parts.push('Source-byte measurements are unavailable for this older index generation.');
      const configuredCap=safeExactDisplay(coverage.max_total_source_bytes,coverage.max_total_source_bytes_exact);
      if(configuredCap!==null)parts.push(`Configured total source-read cap: ${configuredCap} bytes; measured usage is unavailable.`);
    }
    else if(coverage.source_metrics_available===true){
      const bytes=safeExactDisplay(coverage.source_bytes_read,coverage.source_bytes_read_exact);
      const budget=safeExactDisplay(coverage.source_budget_bytes,coverage.source_budget_bytes_exact);
      const totalBudget=safeExactDisplay(coverage.max_total_source_bytes,coverage.max_total_source_bytes_exact);
      const skipped=safeExactDisplay(coverage.source_budget_exceeded_files,coverage.source_budget_exceeded_files_exact);
      const fileCap=safeExactDisplay(coverage.max_files,coverage.max_files_exact);
      const fileByteCap=safeExactDisplay(coverage.max_file_bytes,coverage.max_file_bytes_exact);
      if(bytes!==null)parts.push(`${bytes} source bytes were read for this index generation.`);
      if(budget!==null)parts.push(`Its source-byte budget was ${budget} bytes.`);
      if(totalBudget!==null&&totalBudget!==budget)parts.push(`The configured total source-byte cap was ${totalBudget} bytes.`);
      if(fileCap!==null||fileByteCap!==null)parts.push(`Configured file limits: ${fileCap??'uncapped'} files; ${fileByteCap??'uncapped'} bytes per file.`);
      if(skipped!==null&&skipped!=='0')parts.push(`${skipped} files were excluded by the total source-byte budget.`);
      if(coverage.source_budget_exhausted&&skipped==='0')parts.push('The source-byte budget boundary was reached; no excluded files are reported.');
    }
    return parts.join(' ');
  }
  formatNarrative(g){
    const summary=g.summary||{};
    const name=g.name||'Repository';
    if(g.analysis?.source_kind==='sqlite_file_import_page'&&g.coverage){const c=g.coverage,first=c.offset+1,last=c.offset+c.returned_nodes,pageLabel=c.returned_nodes?`${first}–${last}`:c.matching_nodes?`at offset ${c.offset} (no rows returned)`:'with no matching paths';return `${name}: file and static-import snapshot, page ${pageLabel} of ${c.matching_nodes} matching paths across ${c.total_nodes} indexed files. ${c.total_import_edges} static Python import relationships are indexed overall. This export contains file nodes only; modules, functions, and classes are not represented.`;}
    return `${name}: ${summary.files||0} files across ${summary.modules||0} directories, with ${summary.functions||0} functions and ${summary.classes||0} classes. ${summary.relationships||g.edges.length} recorded relationships. Start with ${summary.hubs?.slice(0,3).join(', ')||'the root module'}, then follow imports into the implementation.`;
  }
  renderShell(){
    this.innerHTML=`<div class="graph-shell"><div class="graph-heading"><div><span class="eyebrow">REPOSITORY INTELLIGENCE</span><h3>See the structure. Follow the relationships.</h3></div><button class="secondary graph-export">Export graph ↗</button></div><div class="graph-narrative" role="status">Analyze a repository or load a graph snapshot to begin.</div><div class="graph-controls"><label>Detail<select class="graph-level"><option value="module">Modules · simplified</option><option value="file">Files</option><option value="symbol">Functions & classes</option><option value="all">All kinds</option></select></label><label>Find a node<input class="graph-search" placeholder="Path, function, or module…" type="search"></label><label>Relationship<select class="graph-relation"><option value="all">All relationships</option><option>imports</option><option>calls</option><option>inherits</option><option>contains</option><option>defines</option></select></label><label class="graph-check"><input class="graph-inferred" type="checkbox" checked>Show inferred edges</label></div><div class="graph-layout"><div><div class="graph-canvas"><svg viewBox="0 0 920 510" role="group" aria-label="Interactive repository relationships"></svg><div class="graph-empty" aria-hidden="true" hidden></div></div><div class="graph-caption" role="status" aria-live="polite" aria-atomic="true"></div><div class="graph-actions"><button class="quiet graph-prev">← Previous nodes</button><button class="quiet graph-reset">Show overview</button><button class="quiet graph-next">Next nodes →</button></div><div class="graph-legend"><span>● Module</span><span>■ File</span><span>◆ Function / class</span><span>Solid = parsed/observed · dashed = inferred/aggregated</span></div></div><aside class="graph-inspector"><h4>Choose a node</h4><p>Start with a module, then inspect its files, functions, and relationships.</p></aside></div><details class="graph-evidence"><summary>Coverage, unresolved references & analysis boundaries</summary><div></div></details></div>`;
    this.querySelector('.graph-narrative').insertAdjacentHTML('afterend','<p class="graph-analysis help" role="status" aria-live="polite"></p>');
    this.querySelectorAll('select,input').forEach(el=>el.addEventListener('input',()=>{this.page=0;this.draw();}));
    this.querySelector('.graph-prev').onclick=()=>{this.page=Math.max(0,(this.page||0)-1);this.draw();};
    this.querySelector('.graph-next').onclick=()=>{this.page=(this.page||0)+1;this.draw();};
    this.querySelector('.graph-reset').onclick=()=>{this.focused=false;this.selected=null;this.page=0;this.draw();};
    this.querySelector('.graph-export').onclick=()=>{if(!this._graph)return;const url=URL.createObjectURL(new Blob([JSON.stringify(this._graph,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='repository-graph.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  }
  select(id){this.selected=id;this.inspect();this.drawCanvas();}
  draw(){
    const g=this._graph;if(!g)return;
    const summary=g.summary||{};
    this.lookup=new Map(g.nodes.map(n=>[n.id,n]));
    this.querySelector('.graph-analysis').textContent=[this.formatAnalysis(g.analysis),this.formatCoverage(g.coverage)].filter(Boolean).join(' ');
    this.querySelector('.graph-narrative').textContent=this.formatNarrative(g);
    const level=this.querySelector('.graph-level').value, query=this.querySelector('.graph-search').value.toLowerCase(),relation=this.querySelector('.graph-relation').value;
    const allowed=this.querySelector('.graph-inferred').checked;
    const focusedEdges=this.focused&&this.selected&&level!=='module'?(this.incidentEdges?.get(this.selected)||[]):g.edges;
    let edges=focusedEdges.filter(e=>(relation==='all'||e.relation===relation)&&(allowed||e.confidence!=='inferred'));
    let nodes=g.nodes.filter(n=>level==='all'||(level==='symbol'?['function','class'].includes(n.kind):n.kind===level));
    if(level==='module'){
      const owner=id=>{const n=this.lookup.get(id);if(!n||!n.path)return null;if(n.kind==='module')return n.id;const p=n.path.includes('/')?n.path.slice(0,n.path.lastIndexOf('/')):'.';return 'module:'+p;};
      const aggregated=new Map();
      edges.forEach(e=>{const source=owner(e.source),target=owner(e.target);if(source&&target&&source!==target){const key=source+'|'+target+'|'+e.relation;const previous=aggregated.get(key);aggregated.set(key,{source,target,relation:e.relation,confidence:'aggregated',count:(previous?.count||0)+1});}});
      edges=[...aggregated.values()];this.moduleEdges=edges.filter(e=>!['contains','defines'].includes(e.relation));
    }
    if(query)nodes=nodes.filter(n=>(n.name+' '+n.path).toLowerCase().includes(query));
    if(this.focused&&this.selected){const neighbors=new Set([this.selected]);edges.forEach(e=>{if(e.source===this.selected)neighbors.add(e.target);if(e.target===this.selected)neighbors.add(e.source);});nodes=nodes.filter(n=>neighbors.has(n.id));edges=edges.filter(e=>neighbors.has(e.source)&&neighbors.has(e.target));}
    nodes.sort((a,b)=>(b.connections||0)-(a.connections||0)||a.id.localeCompare(b.id));
    this.page=Math.min(this.page||0,Math.max(0,Math.ceil(nodes.length/36)-1));
    this.visible=nodes.slice(this.page*36,this.page*36+36);const ids=new Set(this.visible.map(n=>n.id));this.visibleEdges=edges.filter(e=>ids.has(e.source)&&ids.has(e.target));
    const emptyMessage=!nodes.length?(g.nodes.length?'No nodes match the current filters.':'No source nodes were found.'):'';
    const scope=this.focused&&this.selected?' in the selected neighborhood':'';
    this.querySelector('.graph-caption').textContent=`Showing ${this.visible.length} of ${nodes.length} matching nodes${scope} · canvas page ${this.page+1}/${Math.max(1,Math.ceil(nodes.length/36))}. ${this.visibleEdges.length} links on this page.${g.coverage?' Canvas paging stays inside this imported database page.':''}${emptyMessage?` ${emptyMessage} Change the search, detail, or relationship filters to continue.`:''} Export retains the full imported graph.`;
    this.querySelector('.graph-prev').disabled=this.page===0;this.querySelector('.graph-next').disabled=(this.page+1)*36>=nodes.length;
    const empty=this.querySelector('.graph-empty');empty.hidden=!!this.visible.length;empty.textContent=emptyMessage;
    const truncationEvidence=g.coverage
      ?(g.coverage.scan_truncated?'Repository scan stopped at its configured file limit. ':'')
      :(g.truncated?'Graph data is truncated; review coverage details. ':'');
    this.querySelector('.graph-evidence div').innerHTML=`<p>${truncationEvidence}${this.escape((g.warnings||[]).join(' '))}</p><p>Python: AST declarations, imports, lexical calls and inheritance. Self/cls dispatch is inferred. JavaScript/TypeScript: lexical declaration/import hints only. Other files: inventory and containment. Runtime dispatch and unresolved references are not fabricated. Git-ignored untracked files, generated/vendor directories and symbolic links are excluded.</p><p>${summary.unresolved||0} references unresolved; ${(g.unresolved||[]).length>40?'first 40 shown; export includes up to 200':'listed below'}.</p><ul>${(g.unresolved||[]).slice(0,40).map(x=>`<li>${this.escape(x.path)}:${x.line} · ${this.escape(x.expression)}</li>`).join('')}</ul>`;
    this.drawCanvas();this.inspect();
  }
  drawCanvas(){
    if(!this.visible)return;const svg=this.querySelector('svg'),e=this.escape.bind(this);
    const focusedNode=svg.contains(document.activeElement)?document.activeElement.dataset.node:null;
    const inspectorHadFocus=this.querySelector('.graph-inspector').contains(document.activeElement);
    const positions=new Map();const columns=Math.min(6,Math.max(2,Math.ceil(Math.sqrt(this.visible.length))));const rows=Math.max(1,Math.ceil(this.visible.length/columns));
    this.visible.forEach((n,i)=>positions.set(n.id,{x:40+(i%columns)*(840/columns),y:35+Math.floor(i/columns)*(430/rows)}));
    const color=n=>({module:'#277965',file:'#557ab0',function:'#9560a6',class:'#b58037',external:'#8b9094'}[n.kind]);
    svg.innerHTML=`<defs><marker id="graph-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#95aaa0"/></marker></defs>`+this.visibleEdges.map(x=>{const a=positions.get(x.source),b=positions.get(x.target);return `<path d="M${a.x+45} ${a.y+20} Q${(a.x+b.x)/2+70} ${Math.min(a.y,b.y)-10} ${b.x+45} ${b.y+20}" fill="none" stroke="${this.selected&&(x.source===this.selected||x.target===this.selected)?'#277965':'#c4d4ca'}" stroke-width="1.4" ${['inferred','aggregated'].includes(x.confidence)?'stroke-dasharray="5 4"':''} marker-end="url(#graph-arrow)"><title>${e(x.relation)} · ${e(x.confidence)}${x.count?' · '+x.count+' links':''}</title></path>`;}).join('')+this.visible.map(n=>{const p=positions.get(n.id);return `<g role="button" tabindex="0" aria-pressed="${this.selected===n.id}" aria-label="Inspect ${e(n.kind)} ${e(n.name)}" data-node="${e(n.id)}" transform="translate(${p.x},${p.y})"><rect width="126" height="56" rx="10" fill="${this.selected===n.id?'#e0efd7':'#fff'}" stroke="${color(n)}" stroke-width="${this.selected===n.id?3:1}"/><circle cx="13" cy="16" r="4" fill="${color(n)}"/><text x="23" y="20" font-size="9" fill="#627168">${e(n.kind.toUpperCase())}</text><text x="10" y="40" font-size="10" fill="#1d352c">${e(n.name.length>18?n.name.slice(0,16)+'…':n.name)}</text><title>${e(n.path)}${n.line?':'+n.line:''} · ${e(n.name)}</title></g>`;}).join('');
    svg.querySelectorAll('[data-node]').forEach(n=>{n.onclick=()=>this.select(n.dataset.node);n.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();this.select(n.dataset.node);}};});
    if(focusedNode){[...svg.querySelectorAll('[data-node]')].find(node=>node.dataset.node===focusedNode)?.focus();}
    else if(inspectorHadFocus&&this.focused&&this.selected){[...svg.querySelectorAll('[data-node]')].find(node=>node.dataset.node===this.selected)?.focus();}
  }
  inspect(){
    const target=this.querySelector('.graph-inspector');const n=this.lookup?.get(this.selected);if(!n){target.innerHTML='<h4>Choose a node</h4><p>Inspect its summary, source location, incoming dependencies, and outgoing relationships.</p>';return;}
    const e=this.escape.bind(this),links=[...(this.incidentEdges?.get(n.id)||[]),...(n.kind==='module'?(this.moduleEdges||[]).filter(x=>x.source===n.id||x.target===n.id):[])];
    target.innerHTML=`<span class="badge">${e(n.kind)} · ${e(n.confidence)}</span><h4>${e(n.name)}</h4><code>${e(n.path)}${n.line?':'+n.line:''}</code><p>${e(n.summary)}</p><button class="secondary graph-focus">Focus neighborhood</button><h5>${links.length} relationships</h5><ul>${links.slice(0,70).map(x=>{const other=this.lookup.get(x.source===n.id?x.target:x.source);return `<li><button class="quiet" data-related="${e(other.id)}">${x.source===n.id?'→':'←'} ${e(x.relation)} · ${e(other.name)}</button><small>${e(x.confidence)}${x.count?' · '+x.count+' links':''}${x.line?' · line '+x.line:''}</small></li>`;}).join('')}</ul>`;
    target.querySelector('.graph-focus').onclick=()=>{this.focused=true;this.page=0;this.draw();};
    target.querySelectorAll('[data-related]').forEach(b=>b.onclick=()=>{this.selected=b.dataset.related;this.focused=true;this.page=0;this.draw();});
  }
}
customElements.define('repo-graph',RepoGraph);
