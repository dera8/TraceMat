/* Public demo: canonical query selection, browser execution, no model service. */
(() => {
 const entries=[
  {id:'brick',question:'Which surfaces are brick?',query:{op:'filter',material_class:'brick'}},
  {id:'unresolved',question:'Show unresolved surfaces.',query:{op:'provenance_filter',evidence_tier:'unresolved'}},
  {id:'wet',question:'Which roofs change state when wet?',query:{op:'filter',surface:'roof',has_wet_state:true}},
  {id:'geometry',question:'Show geometrically recovered assignments.',query:{op:'provenance_filter',evidence_tier:'geometric'}},
  {id:'radio',question:'Which surfaces have supported EM properties?',query:{op:'radio_materials',frequency_ghz:3.5,state:'dry'}},
  {id:'lidar',question:'Show road reflectance priors.',query:{op:'lidar_pseudoreflectance',surface:'road'}},
  {id:'provenance',question:'Inspect the recorded provenance of building 915551373.',query:{op:'provenance',osm_id:'915551373'}}
 ];
 const panel=document.getElementById('nlq'),bar=document.getElementById('nlqBar'),input=document.getElementById('nlqQ');
 input.type='hidden';
 document.getElementById('nlqToggle').style.display='none';
 document.getElementById('nlqHelp').style.display='none';
 const heading=document.createElement('label');heading.textContent='Try a controlled query';heading.htmlFor='controlledQuery';heading.style.cssText='align-self:flex-start;font-weight:600;font-size:16px';panel.prepend(heading);
 const pick=document.createElement('select');pick.id='controlledQuery';pick.style.cssText='min-width:0;flex:1;width:100%;font-size:15px;padding:9px;border:1px solid #c7d0d8;border-radius:8px;background:white;color:#1b242c';
 entries.forEach(e=>pick.add(new Option(e.question,e.id)));bar.prepend(pick);
 const note=document.createElement('div');note.textContent='This review demo executes frozen typed queries locally. No account, model service or internet connection is required.';note.style.cssText='font-size:13px;line-height:1.4;color:#46525c;background:#fff;padding:6px 8px;border-radius:6px';panel.appendChild(note);
 window.nlqDirectQuery=question=>{
  const e=entries.find(x=>x.question===question);
  return e?{think:'Frozen typed query, executed over the published graph.',query:structuredClone(e.query)}:null;
 };
 const execute=id=>{const entry=entries.find(e=>e.id===id);if(!entry||nlqBusy)return;pick.value=id;input.value=entry.question;return nlqAsk();};
 const run=document.getElementById('nlqGo');run.textContent='Run';run.onclick=()=>execute(pick.value);
 pick.onchange=()=>{input.value=entries.find(e=>e.id===pick.value).question;};pick.onchange();
 const guide=document.createElement('nav');guide.setAttribute('aria-label','Guided exploration');guide.style.cssText='display:flex;flex-wrap:wrap;gap:6px;pointer-events:auto';
 const setMode=mode=>{VIEW_MODE=mode;updateModeUI();applyMode();drawGraph();};
 const steps=[
  ['1. Inspect grounding',()=>{setMode('semantic');return execute('unresolved');}],
  ['2. Check provenance',()=>{setMode('pbr');return execute('provenance');}],
  ['3. Switch physical layer',()=>{nlqClearHighlight();setMode(VIEW_MODE==='radio'?'lidar':'radio');}],
  ['4. Try a query',()=>{pick.focus();return execute('brick');}]
 ];
 steps.forEach(([label,action])=>{const button=document.createElement('button');button.className='tg';button.textContent=label;button.onclick=action;guide.appendChild(button);});
 document.getElementById('viewerHeader').after(guide);
 // Load the graph at startup; the large radio/LiDAR overlays remain deferred.
 loadNlqGraph().catch(()=>{note.textContent='The graph could not be loaded. Reload the page to retry.';});
 fetch('assets/frozen_queries.json').then(r=>{if(!r.ok)throw new Error('Query list unavailable');return r.json();}).then(data=>{
  for(const q of data.questions||[]){
   // The complete frozen benchmark also contains Python-only operations.
   try{nlqValidateQuery(q.query);}catch(error){continue;}
   const entry={...q,id:'benchmark-'+q.id};entries.push(entry);pick.add(new Option(q.id+' - '+q.question,entry.id));
  }
  const full=document.createElement('a');full.href='assets/frozen_queries.json';full.textContent='Full benchmark query set (including Python-only operations)';full.style.cssText='display:block;font-size:12px;margin-top:4px';note.appendChild(full);
 }).catch(()=>{});
})();
