/* Pocket City page: one place, everything about it from city.json (#cityData). The drawing itself runs in workers
   built from the text blocks: projection, models, streetFigures, data, landmarks, city, foliage, painter. */
const $=id=>document.getElementById(id);
const CITY=JSON.parse($('cityData').textContent),META=JSON.parse($('sceneMeta').textContent);
const canvas=$('fig'),stage=$('stage');
const phoneProfile=()=>innerWidth<=760 || (matchMedia('(pointer:coarse)').matches && Math.min(window.screen.width,window.screen.height)<=760);
let phone=phoneProfile();
const smallerMotion=matchMedia('(prefers-reduced-motion:reduce)').matches;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const link=(label,url)=>url?'<a href="'+esc(url)+'" target="_blank" rel="noopener">'+esc(label)+'</a>':esc(label);

/* ---------- the place ---------- */
const size=Math.round(META.size),fmt=(v,p,n)=>Math.abs(v).toFixed(5)+'° '+(v>=0?p:n);
document.title='Pocket City · '+(CITY.title||CITY.name);
$('cityName').textContent=CITY.name;$('placeTab').textContent=CITY.name;
document.querySelector('.stamp-line span').textContent=CITY.region||'';
const flag=document.querySelector('.flag');
if(CITY.flag){flag.className='flag cn';flag.innerHTML=CITY.flag}else flag.hidden=true;
document.querySelector('.location').textContent=CITY.place||'';
document.querySelector('.coords').lastChild.textContent=' '+fmt(META.lat,'N','S')+'　'+fmt(META.lon,'E','W');
document.querySelector('.metric').lastChild.textContent=' '+size+' × '+size+' m';
canvas.setAttribute('aria-label','Interactive diorama of '+CITY.name+'. Use arrow keys to turn, plus and minus to zoom, and Home to reset.');

/* ---------- seasons and occasions ---------- */
const SEASONS=CITY.seasons||[],OCCASIONS=CITY.occasions||[];
const NOTES={};for(const s of SEASONS.concat(OCCASIONS))NOTES[s.id]=s.note||{text:'',source:'',url:''};
const icons={};document.querySelectorAll('#chips [data-s]').forEach(b=>{const svg=b.querySelector('svg');if(svg)icons[b.dataset.s]=svg.outerHTML});
const chipSeasons=SEASONS.filter(s=>!s.sub),subSeason=SEASONS.find(s=>s.sub);
document.querySelector('.season-box .subhead').textContent=CITY.seasonLabel||'Season';
$('chips').setAttribute('aria-label',CITY.seasonLabel||'Season');
$('chips').replaceChildren(...chipSeasons.map(s=>{const b=document.createElement('button');b.className='chip';b.dataset.s=s.id;b.innerHTML=(icons[s.icon||s.id]||'')+' '+esc(s.label);return b}));
if(chipSeasons.length%2&&$('chips').lastElementChild)$('chips').lastElementChild.style.gridColumn='1 / -1';   // an odd last season fills its row
$('event').replaceChildren(new Option(CITY.occasionLabel||'Special scenes',''),...OCCASIONS.map(o=>new Option(o.label,o.id)));
$('event').parentElement.hidden=!OCCASIONS.length;
if(subSeason)$('snow').textContent='+ '+subSeason.label.replace(/^\+\s*/,'');
const tz=CITY.timezone||Intl.DateTimeFormat().resolvedOptions().timeZone;
const localMonth=Number(new Intl.DateTimeFormat('en',{timeZone:tz,month:'numeric'}).format(new Date()));
const months=CITY.months&&CITY.months.length===12?CITY.months:Array(12).fill(chipSeasons[0].id);
let season=months[localMonth-1], ordinary=season, playing=!smallerMotion, time=0, movie=0, view='cine';
const wobble=0, finish='wash';   // one look for every city: the Colour wash finish (richer colour; April 2026-11-20), drawn precisely

/* ---------- cameras and views ---------- */
const autoZoom=+(302/(size*1.62)).toFixed(3);
const iso={yaw:-35,pitch:33,zoom:autoZoom,x:0,y:0,z:4,...((CITY.cameras||{}).iso||{})};
const maxZoom=iso.zoom*10,minZoom=iso.zoom*.55;
const cameras={iso,bird:{yaw:iso.yaw-5,pitch:72,zoom:iso.zoom*.95,x:0,y:0,z:4,...((CITY.cameras||{}).bird||{})}};
const focusCameras={};
const viewList=[['cine','Cinematic']];   // Cinematic opens the page (it starts on the whole-plate camera and drifts); no separate Overview tab (April, 2026-11-20)
for(const v of CITY.views||[]){cameras[v.id]={...iso,...v.camera};viewList.push([v.id,v.label])}
viewList.push(['bird','Bird’s-eye'],['free','Free view']);
$('view').replaceChildren(...viewList.map(([id,label])=>new Option(label,id)));$('view').lastElementChild.hidden=true;

/* ---------- legend ---------- */
const LEGEND_ICONS={
  buildings:'<path d="m11 16 13-6 12 5-13 6Z" fill="#eadcc3" stroke="#867a6c"/><path d="m11 16 12 5v22l-12-6Z" fill="#e7c79e" stroke="#867a6c"/><path d="m23 21 13-6v21l-13 7Z" fill="#bba997" stroke="#867a6c"/>',
  trees:'<circle cx="24" cy="18" r="11" fill="#a9c58c" stroke="#6f8a5c"/><path d="M24 29v13" stroke="#8a6a4f" stroke-width="3"/>',
  streets:'<path d="m3 27 13-6 3-10 7-3 2 8 11-5 5 6-14 7 1 10-9 5-3-10-12 6Z" fill="#cbbab3" stroke="#948383"/><path d="m10 28 8-4m8-4 11-5" fill="none" stroke="#fff3c9" stroke-dasharray="3 2"/>',
  landmark:'<path d="m13 39 1-15 5-3 4-17 4 17 5 3 1 15-10 3Z" fill="#f5e9d3" stroke="#998d83"/>',
  water:'<path d="M4 30c6-4 10 4 16 0s10 4 16 0 8 3 8 3" fill="none" stroke="#6aa3b0" stroke-width="3"/><path d="M4 22c6-4 10 4 16 0s10 4 16 0" fill="none" stroke="#9cc3c4" stroke-width="3"/>',
  shops:'<path d="M9 20h30v20H9Z" fill="#efe3cd" stroke="#8b7f74"/><path d="M7 14h34l-3 7H10Z" fill="#b5735f" stroke="#8b5a4c"/><path d="M14 27h8v13h-8Z" fill="#8fb0ad"/>'
};
const legend=(CITY.legend||[]).slice(0,4),rows=[...document.querySelectorAll('[data-f]')];
rows.forEach((b,i)=>{const it=legend[i];if(!it){b.hidden=true;return}
  b.dataset.f='f'+i;b.setAttribute('aria-label','Fly to '+it.name);b.querySelector('strong').textContent=it.name;
  b.querySelector('small').textContent=it.source||'';b.querySelector('.count').textContent=it.count??'';
  b.querySelector('svg').innerHTML=LEGEND_ICONS[it.icon]||LEGEND_ICONS.buildings;focusCameras['f'+i]={...iso,...it.camera}});
if(!legend.length)document.querySelector('.field-key').hidden=true;

/* ---------- footer and field notes ---------- */
const osm='<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors</a>';
document.querySelector('.foot > div:last-child').innerHTML=osm+(CITY.credits?' · '+CITY.credits.map(c=>link(c.label,c.url)).join(' · '):'');
const notes=(CITY.notes||[]).map(n=>'<dt>'+esc(n.title)+'</dt><dd>'+esc(n.text)+(n.links&&n.links.length?' '+n.links.map(l=>link(l.label,l.url)).join(' · '):'')+'</dd>').join('');
document.querySelector('.dialog-body').innerHTML='<dl class="source-list">'+notes+
  '<dt>Map data</dt><dd>Footprints, heights where mapped, streets, trees and shop names come from the '+esc(META.osm_base?META.osm_base.slice(0,10):'')+' OpenStreetMap extract. The '+size+' m square is turned '+Math.round(META.rotation)+'° to follow the streets. Unmapped heights, façades, colours, street furniture, trips and weather are illustrative. '+osm+' · ODbL</dd>'+
  '<dt>Drawing</dt><dd>Pocket City by April Zhu. Colorfigures builds on Tolga Cohce’s iso-figure.</dd></dl>';

/* ---------- interaction (the same as the Pocket City atlas) ---------- */
let camera={...iso},goal={...iso},focus=null,revision=0;
function redraw(){revision++}
function markFocus(){document.querySelectorAll('[data-f]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.f===focus))}
function setView(name){
  view=name;focus=null;markFocus();$('view').value=name;markViews();
  if(cameras[name])goal={...cameras[name]};
  if(name==='cine'){movie=0;setPlay(true)}
  $('viewName').textContent=name==='free'?'Free view':$('view').selectedOptions[0].text;
  redraw();
}
function freeView(){if(view!=='free')setView('free')}
function zoomBy(factor){freeView();goal.zoom=Math.max(minZoom,Math.min(maxZoom,goal.zoom*factor));redraw()}
function setPlay(on){playing=on;
  $('play').innerHTML=on?'<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M8 5v14M16 5v14" stroke-width="3.3"/></svg>':'<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="m7 4 12 8-12 8Z" fill="currentColor" stroke="none"/></svg>';$('play').title=on?'Pause simulation':'Play simulation';$('play').setAttribute('aria-label',$('play').title);
  $('status').classList.toggle('paused',!on);$('status').lastElementChild.textContent=on?'Simulation live':'Simulation paused';redraw();
}
$('play').onclick=()=>setPlay(!playing);$('view').onchange=e=>setView(e.target.value);
function buildViews(){
  $('views').replaceChildren(...[...$('view').options].filter(o=>!o.hidden).map(o=>{
    const b=document.createElement('button');b.type='button';b.className='vbtn';b.textContent=o.text;b.dataset.v=o.value;
    b.setAttribute('aria-pressed',o.value===view);b.onclick=()=>setView(o.value);return b}));
}
function markViews(){
  const bar=$('views');let on=null;
  bar.querySelectorAll('.vbtn').forEach(b=>{const p=b.dataset.v===view;b.setAttribute('aria-pressed',p);if(p)on=b});
  if(on&&bar.scrollWidth>bar.clientWidth){const l=on.offsetLeft-8,r=on.offsetLeft+on.offsetWidth+8;
    if(l<bar.scrollLeft)bar.scrollLeft=l;else if(r>bar.scrollLeft+bar.clientWidth)bar.scrollLeft=r-bar.clientWidth;}
}
buildViews();$('view').value=view;$('viewName').textContent='Cinematic';
function viewFades(){const b=$('views'),m=b.scrollWidth-b.clientWidth;b.classList.toggle('more-l',b.scrollLeft>2);b.classList.toggle('more-r',m>2&&b.scrollLeft<m-2)}
$('views').addEventListener('scroll',viewFades,{passive:true});addEventListener('resize',viewFades);viewFades();
$('zIn').onclick=()=>zoomBy(1.25);$('zOut').onclick=()=>zoomBy(.8);
function toggleLegend(open){$('keyToggle').setAttribute('aria-expanded',open);$('keyBody').hidden=!open}
toggleLegend(!phone);$('keyToggle').onclick=()=>toggleLegend($('keyBody').hidden);
document.querySelectorAll('[data-f]').forEach(b=>b.onclick=()=>{
  if(focus===b.dataset.f){setView('cine');return}
  setView('free');focus=b.dataset.f;goal={...focusCameras[focus]};markFocus();$('viewName').textContent=b.querySelector('strong').textContent;
  if(phone)toggleLegend(false);
});
function selectSeason(s){
  if(!(s in NOTES))s=chipSeasons[0].id;
  if(months.includes(s))ordinary=s;
  const change=s!==season;season=s;if(change){time=0;generation++}
  const parent=subSeason&&s===subSeason.id?subSeason.sub:s;
  document.querySelectorAll('[data-s]').forEach(b=>b.setAttribute('aria-pressed',b.dataset.s===parent));
  $('event').value=OCCASIONS.some(o=>o.id===s)?s:'';$('event').parentElement.classList.toggle('on',!!$('event').value);
  if(subSeason){$('snow').hidden=parent!==subSeason.sub;$('snow').setAttribute('aria-pressed',s===subSeason.id)}
  const n=NOTES[s]||{};const a=document.createElement('a');a.href=n.url||'#';a.target='_blank';a.rel='noopener';a.textContent=(n.source||'')+' ↗';
  $('note').replaceChildren(document.createTextNode((n.text||'')+' '),...(n.source?[a]:[]));redraw();
}
$('chips').onclick=e=>{const b=e.target.closest('[data-s]');if(b)selectSeason(b.dataset.s)};
$('snow').onclick=()=>selectSeason(season===subSeason.id?subSeason.sub:subSeason.id);$('event').onchange=e=>selectSeason(e.target.value||ordinary);
$('notesBtn').onclick=()=>$('notes').showModal();$('closeNotes').onclick=()=>$('notes').close();$('notes').onclick=e=>{if(e.target===$('notes')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close()}};
$('hint').textContent=phone?'Drag to turn · Pinch to zoom':'Drag to turn · Scroll to zoom';
const touches=new Map();let baseline=null;
function resetTouch(){const p=[...touches.values()];baseline=p.length?{x:p[0].x,y:p[0].y,yaw:goal.yaw,pitch:goal.pitch,zoom:goal.zoom,dist:p[1]?Math.max(1,Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y)):0}:null}
canvas.onpointerdown=e=>{if(e.button!==0)return;canvas.setPointerCapture(e.pointerId);touches.set(e.pointerId,{x:e.clientX,y:e.clientY});resetTouch()};
canvas.onpointermove=e=>{
  if(!touches.has(e.pointerId))return;touches.set(e.pointerId,{x:e.clientX,y:e.clientY});const p=[...touches.values()],b=baseline;
  if(p.length===2){freeView();goal.zoom=Math.max(minZoom,Math.min(maxZoom,b.zoom*Math.hypot(p[0].x-p[1].x,p[0].y-p[1].y)/b.dist))}
  else if(p.length===1 && Math.hypot(p[0].x-b.x,p[0].y-b.y)>2){freeView();goal.yaw=b.yaw-(p[0].x-b.x)*.36;goal.pitch=Math.max(12,Math.min(74,b.pitch+(p[0].y-b.y)*.22))}
  redraw();
};
canvas.onlostpointercapture=canvas.onpointerup=canvas.onpointercancel=e=>{touches.delete(e.pointerId);resetTouch()};
canvas.addEventListener('wheel',e=>{e.preventDefault();zoomBy(Math.exp(-Math.max(-120,Math.min(120,e.deltaY*(e.deltaMode===1?16:1)))*.0018))},{passive:false});
for(const evt of ['gesturestart','gesturechange'])canvas.addEventListener(evt,e=>e.preventDefault(),{passive:false});
canvas.ondblclick=()=>setView('cine');
canvas.onkeydown=e=>{const key=e.key;if(!['+','=','-','Home',' ','ArrowDown','ArrowUp','ArrowLeft','ArrowRight'].includes(key))return;e.preventDefault();
  if(key==='Home')setView('cine');else if(key===' ')setPlay(!playing);else if(['+','=','-'].includes(key))zoomBy(key==='-'?.8:1.25);
  else{freeView();goal.yaw+=key==='ArrowRight'?-10:key==='ArrowLeft'?10:0;goal.pitch=Math.max(12,Math.min(74,goal.pitch+(key==='ArrowDown'?5:key==='ArrowUp'?-5:0)));redraw()}
};
/* At most two frames are in flight. A stale season or resized bitmap is discarded immediately. */
const engine=['projection','models','streetFigures','data','landmarks','city','foliage','painter'].map(id=>$(id).textContent).join('\n');
function profileConfig(){return 'self.PHONE_PROFILE='+phone+';self.PAGE_SEARCH="";\n'}
let extraWorker=null,workers=[],generation=0,seq=0,shown=0,lastKey='',lastRequest=-Infinity,lastTime=0,mainRenderer=null,attemptedFallback=false;
const screen=canvas.getContext('2d',{alpha:true});
function display(frame,g){
  if(frame.seq<=shown || g!==generation){frame.bitmap.close?.();return}
  shown=frame.seq;const img=frame.bitmap;if(extraWorker)setTimeout(()=>extraWorker&&extraWorker(),1500);
  if(canvas.width!==img.width||canvas.height!==img.height){canvas.width=img.width;canvas.height=img.height}
  screen.clearRect(0,0,canvas.width,canvas.height);screen.drawImage(img,0,0);img.close?.();
  $('loading').hidden=true;$('needle').setAttribute('transform','rotate('+frame.angle+' 34 39)');$('scaleLine').style.width=frame.scale+'px';
}
function fallback(reason){
  for(const slot of workers)slot.worker.terminate();workers=[];
  if(attemptedFallback)return;attemptedFallback=true;console.warn(reason);
  try{mainRenderer=new Function(profileConfig()+engine+'\nreturn renderFrame;')();lastKey='';redraw()}catch(e){$('loading').textContent='The drawing could not start. Reload to try again.';console.error(reason,e)}
}
function startWorkers(){
  const workerCode=profileConfig()+engine+'\nself.onmessage=({data:m})=>{try{const r=renderFrame(m);postMessage({...r,seq:m.seq,generation:m.generation},[r.bitmap])}catch(error){postMessage({error:String(error.stack||error)})}};postMessage({ready:true});';
  try{
    const url=URL.createObjectURL(new Blob([workerCode],{type:'text/javascript'})),pool=workers;
    const make=()=>{const worker=new Worker(url),slot={worker,busy:true};pool.push(slot);
      worker.onmessage=({data:d})=>{if(d.error){fallback(d.error);return}slot.busy=false;if(!d.ready)display(d,d.generation)};
      worker.onerror=e=>fallback(e.message);
    };
    make();make();
    // more drawing threads on bigger machines: a turning camera redraws everything, and frames are independent, so threads add up.
    // 6 cores: 3 threads, 8: 4, 10 or more: 5. They start one at a time, 1.5 s apart, after the first picture is up.
    const cores=navigator.hardwareConcurrency||2;let extra=phone?0:cores>=10?3:cores>=8?2:cores>=6?1:0,starting=false;
    if(extra)extraWorker=()=>{if(starting||workers!==pool)return;starting=true;make();extra--;
      setTimeout(()=>{starting=false;if(extra<=0){extraWorker=null;URL.revokeObjectURL(url)}},1500)};
    else URL.revokeObjectURL(url);
  }catch(e){fallback(e)}
}
startWorkers();
let W=0,H=0;
function resize(){
  W=stage.clientWidth;H=stage.clientHeight;generation++;
  const next=phoneProfile();
  if(phone!==next){phone=next;for(const slot of workers)slot.worker.terminate();workers=[];mainRenderer=null;attemptedFallback=false;lastKey='';time=0;
    toggleLegend(!phone);$('hint').textContent=phone?'Drag to turn · Pinch to zoom':'Drag to turn · Scroll to zoom';startWorkers()}
  redraw();
}
new ResizeObserver(resize).observe(stage);resize();
function tick(now){
  requestAnimationFrame(tick);
  const dt=Math.min(.1,(now-(lastTime||now))/1000);lastTime=now;
  if(document.hidden || !W || !H)return;
  if(playing){time+=dt;if(view==='cine')movie+=dt}
  if(view==='cine'){const k=(1-Math.cos(movie*.095))*.5;goal={yaw:iso.yaw+38*k,pitch:iso.pitch-9*k,zoom:iso.zoom*(1+.44*k),x:iso.x,y:iso.y,z:iso.z}}
  const smooth=smallerMotion?1:1-Math.exp(-dt*(touches.size?19:6.5));
  for(const k of Object.keys(camera)){let delta=goal[k]-camera[k];if(k==='yaw')delta=((delta+180)%360+360)%360-180;
    camera[k]=Math.abs(delta)<.001 ? goal[k] : camera[k]+delta*smooth;}
  $('zoom').textContent=Math.round(camera.zoom/iso.zoom*100)+'%';$('zIn').disabled=goal.zoom>=maxZoom;$('zOut').disabled=goal.zoom<=minZoom;
  const interval=1000/(phone?20:30);if(now-lastRequest<interval-.3)return;
  const key=[revision,playing?time:0,...Object.values(camera).map(v=>v.toFixed(4))].join('|');
  if(key===lastKey)return;const slot=workers.find(s=>!s.busy);if(!slot&&!mainRenderer)return;
  lastRequest=now-lastRequest>=2*interval?now:lastRequest+interval;lastKey=key;
  const m={width:W,height:H,dpr:Math.min(devicePixelRatio||1,phone?1.6:2),camera:{...camera},frontage:false,entrance:false,time,wobble,finish,season,seq:++seq,generation};
  if(slot){slot.busy=true;slot.worker.postMessage(m)}else{try{const r=mainRenderer(m);display({...r,seq:m.seq},generation)}catch(e){console.error(e);mainRenderer=null;$('loading').textContent='The drawing could not start. Reload to try again.'}}
}
selectSeason(season);setPlay(playing);requestAnimationFrame(tick);
