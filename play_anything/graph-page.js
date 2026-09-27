(() => {
  const viewer=document.querySelector('repo-graph'),status=document.getElementById('graph-status');
  function show(graph){
    if(!graph||!Array.isArray(graph.nodes)||!Array.isArray(graph.edges)||graph.nodes.length>65000||graph.edges.length>250000||graph.nodes.some(n=>!n||typeof n.id!=='string'||typeof n.name!=='string'||typeof n.path!=='string'||!['module','file','function','class','external'].includes(n.kind)))throw Error('Invalid graph snapshot.');
    const ids=new Set(graph.nodes.map(n=>n.id));
    if(ids.size!==graph.nodes.length||graph.edges.some(e=>!e||!ids.has(e.source)||!ids.has(e.target)||typeof e.relation!=='string')||(graph.warnings&&!Array.isArray(graph.warnings))||(graph.unresolved&&!Array.isArray(graph.unresolved)))throw Error('Invalid graph relationships.');
    viewer.graph=graph;status.textContent='Loaded '+graph.name+'. Select a detail level or inspect a node.';
  }
  async function load(){try{if(window.PlayCloudConfig?.mode==='static')throw Error('Hosted snapshot');const r=await fetch('/api/session');if(!r.ok)throw Error('Hosted snapshot');const session=await r.json();const response=await fetch('/api/graph',{method:'POST',headers:{'Content-Type':'application/json','X-Play-Token':session.token},body:'{}'});if(!response.ok)throw Error('Analysis failed');show(await response.json());}catch(_){try{const response=await fetch('repository-graph.json');if(!response.ok)throw Error();show(await response.json());}catch(_){status.textContent='Start the local creator server to analyze source, or import an exported graph snapshot.';}}}
  document.getElementById('graph-local').onclick=load;
  if(window.PlayCloudConfig?.mode==='static')document.getElementById('graph-local').textContent='Reload project snapshot';
  document.getElementById('graph-saved').onclick=()=>{try{const graph=JSON.parse(localStorage.getItem('play-anything.graph.v1'));if(!graph)throw Error('Analyze a repository in Creator Studio first.');show(graph);}catch(error){status.textContent=error.message;}};
  document.getElementById('graph-file').onchange=async event=>{try{const file=event.target.files[0];if(!file)return;if(file.size>15000000)throw Error('Graph files must be below 15 MB.');show(JSON.parse(await file.text()));}catch(error){status.textContent=error.message;}};
  load();
})();
