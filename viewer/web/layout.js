(() => {
 const ui=document.getElementById('viewerUI'),cards=document.getElementById('viewerCards');
 const views=document.createElement('nav');views.id='mobileViews';views.setAttribute('aria-label','Viewer panels');
 views.innerHTML='<button class="tg" data-view="scene" aria-pressed="true">3D scene</button><button class="tg" data-view="graph" aria-pressed="false">Graph</button><button class="tg" data-view="details" aria-expanded="false">Legend / details</button>';
 cards.before(views);
 views.addEventListener('click',event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.view==='details'){
   const open=document.body.classList.toggle('show-details');button.setAttribute('aria-expanded',String(open));
  }else{
   document.body.classList.toggle('graph-view',button.dataset.view==='graph');
   for(const b of views.querySelectorAll('[aria-pressed]'))b.setAttribute('aria-pressed',String(b===button));
  }
 });
 new MutationObserver(()=>{
  if(document.getElementById('info').style.display!=='none'&&matchMedia('(max-width:680px)').matches){
   document.body.classList.add('show-details');
   views.querySelector('[data-view=details]').setAttribute('aria-expanded','true');
  }
 }).observe(document.getElementById('info'),{attributes:true,attributeFilter:['style']});
 let frame;
 function layout(){
  cancelAnimationFrame(frame);
  frame=requestAnimationFrame(()=>{
   const top=Math.round(cards.getBoundingClientRect().top);
   document.documentElement.style.setProperty('--viewer-top',top+'px');
  });
 }
 new ResizeObserver(layout).observe(document.getElementById('viewerHeader'));
 new ResizeObserver(layout).observe(views);
 for(const nav of ui.querySelectorAll(':scope > nav'))new ResizeObserver(layout).observe(nav);
 // Resize the render targets when panels expand, not only on window resize.
 new ResizeObserver(()=>resize()).observe(document.getElementById('wrap'));
 addEventListener('resize',layout);layout();
})();

