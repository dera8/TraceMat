(() => {
 if(new URLSearchParams(location.search).get('embed')!=='1')return;
 document.body.classList.add('embedded-demo');
 const controls=document.getElementById('ctl');
 for(const id of ['tMode','tRain']){
  const control=document.getElementById(id);
  control.setAttribute('role','button');control.tabIndex=0;
  control.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();control.click();}});
 }
 const reset=document.createElement('button');reset.className='tg';reset.textContent='Reset view';reset.onclick=resetView;controls.appendChild(reset);
 const hint=document.createElement('span');hint.className='embed-hint';hint.textContent='Drag to rotate · click a surface';controls.appendChild(hint);
 const dismiss=document.createElement('button');dismiss.className='tg embed-dismiss';dismiss.textContent='Close details';dismiss.onclick=()=>select(null,null,null);
 const info=document.getElementById('info');
 new MutationObserver(()=>{
  if(info.style.display!=='none'&&!info.contains(dismiss))info.prepend(dismiss);
 }).observe(info,{childList:true});
})();
