(() => {
 if(new URLSearchParams(location.search).get('embed')!=='1')return;
 document.body.classList.add('embedded-demo');
 const controls=document.getElementById('ctl');
 // Native buttons keep keyboard activation and use a readable, explicit state.
 for(const id of ['tMode','tRain']){
  const original=document.getElementById(id);
  const button=document.createElement('button');
  button.type='button';button.id=id;button.className=original.className;
  button.onclick=original.onclick;original.replaceWith(button);
 }
 const mode=document.getElementById('tMode'),rain=document.getElementById('tRain');
 const labels={pbr:'View: 3D',semantic:'View: Materials',radio:'View: Radio',lidar:'View: LiDAR'};
 function syncLabels(){
  const label=labels[VIEW_MODE]||'Change view';
  if(mode.textContent!==label)mode.textContent=label;
  mode.title='Change display: 3D, materials, radio or LiDAR';
  const rainLabel=RAIN?'Rain: on':'Rain: off';
  if(rain.textContent!==rainLabel)rain.textContent=rainLabel;
  rain.setAttribute('aria-pressed',String(RAIN));
 }
 new MutationObserver(syncLabels).observe(mode,{childList:true});
 new MutationObserver(syncLabels).observe(rain,{attributes:true,attributeFilter:['class']});
 syncLabels();
 const reset=document.createElement('button');reset.className='tg';reset.textContent='Reset view';reset.onclick=resetView;controls.appendChild(reset);
 const hint=document.createElement('span');hint.className='embed-hint';hint.textContent='Drag to rotate · click a surface';controls.appendChild(hint);
 const dismiss=document.createElement('button');dismiss.className='tg embed-dismiss';dismiss.textContent='Close details';dismiss.onclick=()=>select(null,null,null);
 const info=document.getElementById('info');
 new MutationObserver(()=>{
  if(info.style.display!=='none'&&!info.contains(dismiss))info.prepend(dismiss);
 }).observe(info,{childList:true});
})();
