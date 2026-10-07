(() => {
  const viewer=document.querySelector('repo-graph'),status=document.getElementById('graph-status');
  const loadGate=globalThis.playAnythingCreateRequestGate();
  function show(graph){
    try{viewer.graph=graph;status.textContent='Loaded '+(graph.name||'Repository')+'. Select a detail level or inspect a node.';return true;}
    catch(error){const detail=String(error?.message||'').slice(0,180);status.textContent=`Graph could not be loaded (${error?.name||'Error'}): ${detail}`;return false;}
  }
  async function load(){
    const revision=loadGate.begin(),isCurrent=()=>loadGate.isCurrent(revision);let apiError=null;
    try{
      if(window.PlayCloudConfig?.mode==='static')throw Error('Hosted snapshot');
      const r=await fetch('/api/session');if(!isCurrent())return;if(!r.ok)throw Error('Hosted snapshot');
      const session=await r.json();if(!isCurrent())return;
      const response=await fetch('/api/graph',{method:'POST',headers:{'Content-Type':'application/json','X-Play-Token':session.token},body:'{}'});
      if(!isCurrent())return;if(!response.ok)throw Error('Analysis failed');
      const graph=await response.json();if(!isCurrent())return;show(graph);return;
    }catch(error){apiError=error;}
    if(!isCurrent())return;
    if(String(apiError?.message||'').startsWith('Invalid graph snapshot:')){status.textContent=`${apiError.message} The previous graph remains displayed.`;return;}
    try{
      const response=await fetch('repository-graph.json');if(!isCurrent())return;
      if(!response.ok)throw Error('No bundled graph snapshot is available.');
      const graph=await response.json();if(!isCurrent())return;show(graph);
    }catch(error){if(isCurrent()){const invalid=String(error?.message||'').startsWith('Invalid graph snapshot:');status.textContent=invalid?`${error.message} The previous graph remains displayed.`:'Start the local creator server to analyze source, or import an exported graph snapshot.';}}
  }
  document.getElementById('graph-local').onclick=load;
  if(window.PlayCloudConfig?.mode==='static')document.getElementById('graph-local').textContent='Reload project snapshot';
  document.getElementById('graph-saved').onclick=()=>{loadGate.invalidate();try{const graph=JSON.parse(localStorage.getItem('play-anything.graph.v1'));if(!graph)throw Error('Analyze a repository in Creator Studio first.');show(graph);}catch(error){status.textContent=`${error.message}${String(error?.message||'').startsWith('Invalid graph snapshot:')?' The previous graph remains displayed.':''}`;}};
  document.getElementById('graph-file').onchange=async event=>{const revision=loadGate.begin(),file=event.target.files[0];if(!file)return;event.target.value='';try{if(file.size>15000000)throw Error('Graph files must be below 15 MB.');const text=await file.text();if(!loadGate.isCurrent(revision))return;show(JSON.parse(text));}catch(error){if(loadGate.isCurrent(revision))status.textContent=`${error.message}${String(error?.message||'').startsWith('Invalid graph snapshot:')?' The previous graph remains displayed.':''}`;}};
  load();
})();
