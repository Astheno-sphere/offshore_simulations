/* Pocket City engine for any place.
   SCENE  measured map data from prep.py (footprints, heights, streets, trees, routes, shops)
   CITY   the researched look from city.json (building styles, palette, people, seasons, occasions)
   LANDMARKS  hand-built famous buildings from landmarks.js (optional; replaces the generic block of those ids)
   Runs inside the render workers with the shared kit: projection, models, streetFigures, foliage, painter. */
const M=SCENE.meta,BASE_CORNERS=SCENE.corners,NORTH=M.north,SLAB=4,HALF=M.half,LEVEL=CITY.level||M.level||3.2;
let FIG_W=540,FIG_H=675,WOBBLE=0,UPX=1,pictureBook=true,washEnabled=true;
const rnd=s=>{const v=Math.sin(s*127.1+311.7)*43758.5453;return v-Math.floor(v)};
const soft=c=>({l:c,m:mix(c,'#887997',.18),d:mix(c,'#705f81',.33)});
const PLANT_INK='#231e17',lineOf=(c,plant)=>mix(c,'#51465a',plant?.38:.53);
const groundZ=()=>0,atZ=(r,z)=>r.map(p=>[p[0],p[1],z]);
const hash=s=>{let h=7;for(const c of String(s))h=(h*31+c.charCodeAt(0))|0;return Math.abs(h)};
const pickOf=(v,seed)=>Array.isArray(v)?v[hash(seed)%v.length]:v;
const PAL={ground:'#eadfc9',road:'#b8aeb2',pavement:'#ebdfc8',walk:'#e6d7be',grass:'#b4d784',water:'#86c6cc',sand:'#ecd9a8',quay:'#d9cfbb',slab:'#d8c5a3',
  marking:'#f4ead3',kerb:'#e3c477',paving:'#c6baa7',rail:'#7d7f86',...(CITY.palette||{})};

/* ---------- textures that turn with a surface (roof tiles, copper, cladding) ---------- */
const sheetTiles=new Map();
function sheetInk(points,name,u,v){
  const origin=points[0],right=Dv(...u),down=Dv(...v),p=P(...origin);
  if(Math.abs(right[0]*down[1]-right[1]*down[0])<.04||UPX>.68)return '';
  const coords=points.map(q=>[dot(sub(q,origin),u),dot(sub(q,origin),v)]),xs=coords.map(q=>q[0]),ys=coords.map(q=>q[1]);
  const bounds=[Math.min(...xs)-1,Math.min(...ys)-1,Math.max(...xs)+1,Math.max(...ys)+1];
  return '<sheet name="'+name+'" d="'+pd(points)+'" matrix="'+[...right,...down,...p].join(' ')+'" bounds="'+bounds.join(' ')+'"/>';
}
function paintSheet(g,op){
  let tile=sheetTiles.get(op.name);
  if(!tile){
    const size=256,c=makeSurface(size,size),ink=c.getContext('2d');
    if(op.name==='copper'){
      for(let row=0;row<24;row++)for(let col=0;col<24;col++){const x=(col+(row%2)*.5)*size/24,y=(row+.5)*size/24;ink.fillStyle='rgba(117,63,57,.47)';ink.beginPath();ink.arc(x,y,1.45,0,Math.PI*2);ink.fill()}
    }else if(op.name==='pantile'||op.name==='kawara'){   // rows of rolled tiles running down the slope
      for(let col=0;col<16;col++){const x=col*16;ink.fillStyle='rgba(60,58,70,.20)';ink.fillRect(x,0,3.2,256);ink.fillStyle='rgba(255,246,226,.10)';ink.fillRect(x+6,0,4,256)}
      for(let row=0;row<8;row++){ink.fillStyle='rgba(60,58,70,.12)';ink.fillRect(0,row*32,256,1.6)}
    }else if(op.name==='slate'){
      for(let row=0;row<16;row++)for(let col=-1;col<12;col++){const x=(col+(row%2)*.5)*24,y=row*16,r=rnd(row*13+col);ink.fillStyle='rgba(58,62,74,'+(.05+r*.12)+')';ink.fillRect(x+.6,y+.6,23,15);ink.fillStyle='rgba(40,44,55,.2)';ink.fillRect(x,y+15,24,1)}
    }else{   // plain tiles or shingles
      for(let row=0;row<12;row++)for(let col=-1;col<8;col++){const x=(col+(row%2)*.5)*32,y=row*size/12,r=rnd(row*17+col+103);
        ink.fillStyle=r>.48?'rgba(247,229,204,'+(.04+r*.11)+')':'rgba(68,72,82,'+(.06+r*.15)+')';ink.fillRect(x+.75,y+.75,30.8,size/12-1.3);
        ink.fillStyle='rgba(62,68,77,.23)';ink.fillRect(x,y+size/12-1.25,32,1.25);ink.fillRect(x,y,1,size/12)}
    }
    tile=c;sheetTiles.set(op.name,tile);
  }
  const [l,t,r,b]=op.bounds,pitch=op.name==='copper'?3.6:op.name==='kawara'||op.name==='pantile'?2.6:4.6;
  g.save();g.clip(op.path);g.transform(...op.matrix);g.scale(pitch/tile.width,pitch/tile.height);
  const scale=tile.width/pitch;g.fillStyle=g.createPattern(tile,'repeat');g.fillRect(l*scale,t*scale,(r-l)*scale,(b-t)*scale);g.restore();
}

/* ---------- small geometry ---------- */
function inside(p,r){let c=false;for(let i=0,j=r.length-1;i<r.length;j=i++){const a=r[i],b=r[j];if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])c=!c}return c}
const inRings=(p,groups)=>groups.some(rs=>{let c=false;for(const r of rs)if(inside(p,r))c=!c;return c});
const obj=(fp,h,draw)=>({fp,h,draw});
function rect(x,y,w,d){return [[x-w/2,y-d/2],[x+w/2,y-d/2],[x+w/2,y+d/2],[x-w/2,y+d/2]]}
const polygon=(x,y,r,n,angle=0)=>Array.from({length:n},(_,i)=>[x+r*Math.cos(i*2*Math.PI/n+angle),y+r*Math.sin(i*2*Math.PI/n+angle)]);
const footprintPath=r=>pd(atZ(r,0)),surface=(rings,color)=>'<path d="'+rings.map(footprintPath).join('')+'" fill="'+color+'" fill-rule="evenodd"/>';
const edge=(a,b,c,width)=>'<path d="'+pd([a,b],false)+'" fill="none" stroke="'+c+'" style="stroke-width:'+f(width)+'"/>';
function stripeAt(p,d,length,width){const n=[-d[1]*width/2,d[0]*width/2],a=[d[0]*length/2,d[1]*length/2];
  return footprintPath([[p[0]-a[0]-n[0],p[1]-a[1]-n[1]],[p[0]+a[0]-n[0],p[1]+a[1]-n[1]],[p[0]+a[0]+n[0],p[1]+a[1]+n[1]],[p[0]-a[0]+n[0],p[1]-a[1]+n[1]]])}
function peak(r,base,tip,col){
  return r.map((a,i)=>{const b=r[(i+1)%r.length],p=[[...a,base],[...b,base],tip];const n=vNewell(p);return {p,n,at:avg(p)}}).filter(p=>vis(p.n)).sort((a,b)=>depthOf(a.at)-depthOf(b.at)).map(p=>shape(p.p,tone(p.n,soft(col)),.65)).join('');
}
// Elevations run right-to-left as seen from outside, so lettering is drawn turned round about its anchor.
function wallText(g,str,x,y,w){const a=g.textAlign;g.save();g.translate(x,y);g.scale(-1,1);g.textAlign=a==='start'||a==='left'?'right':a==='end'||a==='right'?'left':a;g.fillText(str,0,0,w);g.restore()}

/* ---------- the look of each building: city.json rules, then per-building overrides ---------- */
const STYLES=CITY.styles||{};
function matches(c,b){
  if(!c)return true;
  const any=(v,x)=>Array.isArray(v)?v.includes(x):v===x;
  if(c.type&&!any(c.type,b.type))return false;
  if(c.use&&!any(c.use,b.use))return false;
  if(c.mat&&!any(c.mat,b.mat))return false;
  if(c.famous!==undefined&&!!b.famous!==c.famous)return false;
  if(c.cut!==undefined&&!!b.cut!==c.cut)return false;
  if(c.name&&!new RegExp(c.name,'i').test(b.n||''))return false;
  const h=b.h??(b.lv?b.lv*LEVEL:null);
  if(c.minH!==undefined&&!(h>=c.minH))return false;
  if(c.maxH!==undefined&&!(h!==null&&h<=c.maxH))return false;
  if(c.minLevels!==undefined&&!((b.lv??(h?h/LEVEL:0))>=c.minLevels))return false;
  if(c.maxLevels!==undefined&&!((b.lv??(h?h/LEVEL:99))<=c.maxLevels))return false;
  if(c.minArea!==undefined&&!(b.area>=c.minArea))return false;
  if(c.maxArea!==undefined&&!(b.area<=c.maxArea))return false;
  if(c.unknownHeight!==undefined&&(b.h==null&&b.lv==null)!==c.unknownHeight)return false;
  if(c.nearStreet!==undefined&&b.street!==c.nearStreet)return false;
  return true;
}
function styleFor(b){
  let s={facade:'house',wall:['#eee2ca'],roofColour:['#c8c4b8'],roof:'auto',pitch:30,eaves:.45,levels:3,floor:LEVEL,shop:'poi',parapet:.5,...(STYLES.default||{})};
  for(const rule of STYLES.rules||[])if(matches(rule.if,b)){s={...s,...rule.set};if(!rule.more)break}
  return {...s,...((CITY.buildings||{})[b.id]||{})};
}
const POIS=SCENE.pois||[];
const areaOf=r=>Math.abs(r.reduce((s,p,i)=>{const q=r[(i+1)%r.length];return s+p[0]*q[1]-q[0]*p[1]},0)/2);
const nearStreet=b=>b.ring.some((a,i)=>{const c=b.ring[(i+1)%b.ring.length],m=[(a[0]+c[0])/2,(a[1]+c[1])/2];
  return [[3,0],[-3,0],[0,3],[0,-3]].some(([dx,dy])=>inRings([m[0]+dx,m[1]+dy],SCENE.roads))});
for(const b of SCENE.buildings){
  b.area=areaOf(b.ring);b.street=nearStreet(b);b.pois=[];
}
for(const p of POIS){   // a named shop belongs to the building it stands in, or the nearest one within 6 m
  let best=null,bd=6;
  for(const b of SCENE.buildings){if(inside([p.x,p.y],b.ring)){best=b;break}
    for(let i=0;i<b.ring.length;i++){const a=b.ring[i],c=b.ring[(i+1)%b.ring.length],dx=c[0]-a[0],dy=c[1]-a[1],t=Math.max(0,Math.min(1,((p.x-a[0])*dx+(p.y-a[1])*dy)/(dx*dx+dy*dy||1)));
      const d=Math.hypot(a[0]+dx*t-p.x,a[1]+dy*t-p.y);if(d<bd){bd=d;best=b}}}
  if(best)best.pois.push(p);
}
function heightsOf(b,st){
  const pitched=roofKind(b,st)!=='flat';
  const rise=pitched?(b.rh||(ridgeFrame(b,st).W/2+st.eaves)*Math.tan(st.pitch*Math.PI/180)):0;
  let wall;
  if(b.h)wall=pitched?Math.max(2.6,b.h-rise):b.h;
  else if(b.lv)wall=b.lv*st.floor+(pitched?0:.6);
  else wall=(st.levels||3)*st.floor+(pitched?0:.6);
  if(st.height)wall=st.height;
  return {wall:Math.max(wall,(b.min||0)+2.4),top:Math.max(wall,(b.min||0)+2.4)+rise,rise};
}
function roofKind(b,st){
  let k=st.roof==='auto'?(b.roof||'flat'):st.roof;
  if(k==='auto')k='flat';
  if(['gabled','hipped','pyramidal','half-hipped','gambrel','mansard','saltbox','round'].includes(k)){
    if(k==='half-hipped'||k==='mansard'||k==='gambrel'||k==='saltbox')k=k==='mansard'?'hipped':'gabled';
    if(k==='round')k='gabled';
    if(b.obb.fill<(st.rectFill||.78)||b.obb.W<2.5||ridgeFrame(b,st).W>(st.maxSpan||22))return 'flat';
    return k;
  }
  return 'flat';
}

/* ---------- walls: one face per footprint edge, each with a painted elevation ---------- */
const models=[],facades=[];
function walls(r,z,h,info){
  const area=r.reduce((s,p,i)=>{const q=r[(i+1)%r.length];return s+p[0]*q[1]-q[0]*p[1]},0);
  const faces=r.map((a,i)=>{
    const b=r[(i+1)%r.length],len=Math.hypot(b[0]-a[0],b[1]-a[1]);
    if(len<.05)return null;
    const u=[(b[0]-a[0])/len,(b[1]-a[1])/len],n=[u[1]*Math.sign(area),-u[0]*Math.sign(area),0];
    const flip=area>0,start=flip?b:a,along=flip?u.map(v=>-v):u;
    const cut=BASE_CORNERS.some((v,j)=>{const w=BASE_CORNERS[(j+1)%4];return Math.abs(v[0]-w[0])<.01?Math.abs(a[0]-v[0])<.05&&Math.abs(b[0]-v[0])<.05:Math.abs(a[1]-v[1])<.05&&Math.abs(b[1]-v[1])<.05});
    const mid=[(a[0]+b[0])/2,(a[1]+b[1])/2];
    const street=!cut&&[2.2,4.5,7].some(d=>{const q=[mid[0]+n[0]*d,mid[1]+n[1]*d];return inRings(q,SCENE.roads)||inRings(q,SCENE.walk)||inRings(q,SCENE.paths)});
    const st=info.st,bld=info.b;
    const shop=!cut&&z<.5&&len>=3.5&&street&&st.shop!=='none'&&(st.shop==='street'||(st.shop==='poi'&&bld&&bld.pois.length));
    const sign=shop&&bld&&bld.pois.length?(bld.pois[i%bld.pois.length].name):(shop?pickOf((CITY.shops||{}).signs||[''],(bld?bld.id:'')+i):'');
    const id=facades.push({start,along,n,len,z,h,st,cut,shop,sign,seed:hash((bld?bld.id:'')+i),body:info.body,street})-1;
    return {a,b,n,id};
  }).filter(Boolean);
  return ()=>faces.filter(q=>vis(q.n)).sort((a,b)=>depthOf([...a.a,0])-depthOf([...b.a,0])).map(q=>{
    const wall=[...atZ([q.a,q.b],z),...atZ([q.b,q.a],h)],fac=facades[q.id];
    return shape(wall,tone(q.n,soft(info.body)),.7)+'<elevation id="'+q.id+'"/>'+(fac.shop&&fac.st.awning!==false?canopy(fac):'')+(fac.street&&fac.st.eave1&&!fac.cut?midEave(fac):'');
  }).join('');
}
// a shop awning or canopy over each bay of a shopfront
function canopy(F){
  const st=F.st,cols=st.awnings||(CITY.shops||{}).awnings||['#af7762','#688d86','#b59972','#7a8aa8'];
  const bays=Math.max(1,Math.round(F.len/(st.bay||5.5))),bay=F.len/bays,height=Math.min(F.h-F.z-.3,st.shopHeight?st.shopHeight-.2:3.2);
  const at=(s,d,z)=>[F.start[0]+F.along[0]*s+F.n[0]*d,F.start[1]+F.along[1]*s+F.n[1]*d,z];
  let svg='';
  for(let i=0;i<bays;i++){
    if(st.awning==='some'&&(F.seed+i)%3)continue;
    const a=bay*i+.25,b=bay*(i+1)-.25,proj=st.awningDepth||.9,front=height-.42,c=cols[(F.seed+i)%cols.length];
    svg+=shape([at(a,0,height),at(b,0,height),at(b,proj,front),at(a,proj,front)],c,.36);
    if(UPX<.55&&st.stripes!==false)for(let t=a+.12;t<b-.2;t+=.6){const u=Math.min(b,t+.24);svg+=shape([at(t,0,height+.012),at(u,0,height+.012),at(u,proj,front+.012),at(t,proj,front+.012)],'#efe2c6',0)}
    svg+=shape([at(a,proj,front),at(b,proj,front),at(b,proj,front-.16),at(a,proj,front-.16)],mix(c,'#726d78',.3),.3);
  }
  return svg;
}
// a small tiled pent roof between ground and first floor (machiya ichimon-ji eave, shophouse eaves)
function midEave(F){
  const st=F.st,z=F.z+(st.shopHeight||Math.min(3.4,(F.h-F.z)*.5)),proj=st.eave1Depth||.75;
  if(z>F.h-1)return '';
  const at=(s,d,zz)=>[F.start[0]+F.along[0]*s+F.n[0]*d,F.start[1]+F.along[1]*s+F.n[1]*d,zz];
  const col=pickOf(st.roofColour,F.seed);
  return shape([at(0,0,z+.42),at(F.len,0,z+.42),at(F.len,proj,z),at(0,proj,z)],SEASON.snow?snowy(col,.75):col,.45)+edge(at(0,proj,z),at(F.len,proj,z),mix(col,'#3d3a44',.35),.07);
}

/* ---------- painted elevations ---------- */
function paintSingaporeElevation(g,id){
  const F=facades[id],{start,along,n,len:L,z,h,st}=F,H=h-z;
  if(L<.38||H<.48)return;
  const X=Dv(...along,0),Y=Dv(0,0,-1),p=P(...start,h);
  g.save();g.transform(...X,...Y,...p);g.beginPath();g.rect(0,0,L,H);g.clip();
  const box=(x,y,w,d,c)=>{g.fillStyle=c;g.fillRect(x,y,w,d)};
  const poly=(ps,c)=>{g.fillStyle=c;g.beginPath();ps.forEach(([x,y],i)=>i?g.lineTo(x,y):g.moveTo(x,y));g.closePath();g.fill()};
  const side=dot(n,SUN)>.14,shade=c=>nightCol(side?c:mix(c,'#8e839a',.19)),lit=i=>SEASON.night&&rnd(F.seed*.013+i*3.71)<(SEASON.litShare??.55);
  const trim=shade(st.trim||'#f6ead2'),frame=shade(st.frame||'#837e7c'),dark=shade(st.dark||'#526662');
  const glass=(st.glass||['#b4d3cd','#c0d7ca','#a5c6cc','#d9d6b6']).map(shade);
  if(F.cut){box(0,0,L,H,shade('#d3c4b6'));for(let y=st.floor;y<H;y+=st.floor)box(0,y,L,.12,shade('#e6dac6'));g.restore();return}
  if(UPX>1.1){g.restore();return}
  const kind=st.facade,fl=st.floor||LEVEL;
  const shopH=F.shop?Math.min(H,st.shopHeight||Math.max(3.1,fl*1.1)):0,upper=H-shopH;
  const floors=Math.max(1,Math.round(upper/fl)),rh=upper/Math.max(1,floors);
  const bayW=st.bay||(kind==='glass'?2:kind==='office'?2.4:kind==='timber'?1.8:kind==='civic'||kind==='temple'?4.2:kind==='painted'?2.6:3.2);
  const cols=Math.max(1,Math.round(L/bayW)),bw=L/cols;
  function win(x,y,w,d,i){   // one window: frame, glass with a glint, glazing bars
    box(x-.09,y-.09,w+.18,d+.18,frame);
    if(lit(i)){box(x,y,w,d,(i+F.seed)%3?'#ffd98a':'#ffe7a8')}
    else{box(x,y,w,d,glass[(i+F.seed)%glass.length]);poly([[x,y],[x+w*.42,y],[x+w*.14,y+d],[x,y+d]],shade('#e2e8dc'))}
    if(st.bars!==false){box(x+w*.5-.03,y,.06,d,trim);if(d>1.2)box(x,y+d*.32,w,.05,trim)}
  }
  if(kind==='glass'){
    for(let j=0;j<Math.max(1,Math.round(upper/3.6));j++)for(let i=0;i<cols;i++){const x=bw*i,y=j*3.6;
      box(x,y,bw+.01,3.6,glass[(Math.floor(i/5)+Math.floor(j/3)+F.seed)%glass.length]);box(x,y,.08,3.6,frame);box(x,y+3.25,bw,.12,frame);
      if((i+j+F.seed)%11===2)poly([[x,y+.3],[x+bw*.6,y+.3],[x+bw*.2,y+3.1],[x,y+3.1]],shade('#d4e2da'))}
  }else if(kind==='office'){
    for(let j=0;j<floors;j++){const y=j*rh;box(0,y+rh*.24,L,rh*.5,glass[(j+F.seed)%glass.length]);
      for(let i=1;i<cols;i++)box(i*bw,y+rh*.24,.07,rh*.5,frame);box(0,y+rh*.74,L,.08,trim)}
  }else if(kind==='timber'){   // Kyoto-style townhouse: plastered upper storey with slit windows over wooden lattice
    for(let j=0;j<floors;j++){const y=j*rh;
      if(j===floors-1&&!F.shop){   // ground floor without a shop: wooden lattice (koshi) across the front
        box(0,y+rh*.12,L,rh*.88,shade(st.wood||'#6b5241'));
        for(let x=.08;x<L;x+=.11)box(x,y+rh*.14,.045,rh*.84,shade(st.slat||'#8d6e55'));
        const door=Math.min(1.4,L*.3);box(L*.62,y+rh*.12,door,rh*.88,shade('#3e3330'));
        box(L*.62,y+rh*.12,door,rh*.34,shade(pickOf(st.noren||['#2f4a6b','#7a3b3b','#c9b07a'],F.seed)));
      }else{
        const w=Math.min(L*.7,2.6),x=(L-w)/2;box(x,y+rh*.3,w,rh*.45,shade(st.wood||'#6b5241'));
        for(let k=x+.1;k<x+w-.05;k+=.22)box(k,y+rh*.3,.1,rh*.45,trim);
      }
    }
    for(let i=0;i<=Math.round(L/1.8);i++)box(Math.min(L-.08,i*L/Math.max(1,Math.round(L/1.8))),0,.08,upper,shade(st.wood||'#6b5241'));
  }else if(kind==='plain'||kind==='warehouse'){
    for(let j=0;j<floors;j++)for(let i=0;i<cols;i++)if((i+j+F.seed)%(kind==='warehouse'?3:2)===0)win(bw*i+bw*.3,j*rh+rh*.3,bw*.4,rh*.35,i+j);
  }else if(kind==='striped'){   // Ligurian/Genoese church walls: horizontal bands, a few tall arched windows
    const band=st.band||.62,sc=shade(st.stripe||'#a9a8a2');
    for(let y=band;y<upper;y+=band*2)box(0,y,L,band,sc);
    const n=Math.max(1,Math.round(L/(st.bay||5)));
    for(let i=0;i<n;i++){const w=.9,x=(i+.5)*L/n-w/2,y0=upper*.18,d=Math.min(3.4,upper*.32);
      box(x-.18,y0-.18,w+.36,d+.3,trim);box(x,y0+w/2,w,d-w/2,shade('#5b6266'));poly(Array.from({length:9},(_,k)=>[x+w/2+Math.cos(Math.PI+k*Math.PI/8)*w/2,y0+w/2+Math.sin(Math.PI+k*Math.PI/8)*w/2]).concat([[x+w,y0+w/2],[x,y0+w/2]]),shade('#5b6266'))}
    box(0,0,L,.3,trim);
  }else if(kind==='painted'){   // Ligurian / Italian painted front: lots of wall, narrow windows, louvred shutters, painted frames and quoins
    const sh=st.shutters||['#3f6b4c'],tr=shade(st.trim||mix(F.body||'#f0d48c','#ffffff',.55));
    const open=st.shutterOpen??.55;
    for(let j=0;j<floors;j++){const y=j*rh;
      for(let i=0;i<cols;i++){const w=Math.min(1.05,bw*.3),x=bw*i+(bw-w)/2,y0=y+rh*.2,d=rh*.56;if(bw<1.2)continue;
        box(x-.26,y0-.32,w+.52,d+.5,tr);                      // painted surround
        box(x-.36,y0-.46,w+.72,.16,tr);                       // little cornice over the window
        const c=shade(pickOf(sh,F.seed+i+j)),shut=(x0,ww)=>{box(x0,y0,ww,d,c);for(let k=y0+.12;k<y0+d-.05;k+=.16)box(x0+.05,k,ww-.1,.04,mix(c,'#1f2a22',.35))};
        if(rnd(F.seed+i*7.3+j*3.1)<open){win(x,y0,w,d,i*3+j);shut(x-w*.5-.05,w*.5);shut(x+w+.05,w*.5)}
        else shut(x,w);                                       // closed persiane
        if(j===floors-1&&st.balcony&&(i+F.seed)%2===0){box(x-.3,y0+d+.1,w+.6,.08,dark);for(let k=x-.25;k<x+w+.3;k+=.16)box(k,y0+d-.35,.035,.5,dark)}
      }
    }
    for(const x0 of [0,L-.42])for(let k=0;k<upper;k+=.62)box(x0,k,.42,.36,tr);   // painted quoins at the corners
    box(0,0,L,.34,tr);box(0,.34,L,.06,shade(mix(st.trim||'#f6ead2','#6b5a4a',.35)));          // eaves cornice
    if(!F.shop)box(0,upper-.5,L,.5,shade(mix(F.body||'#e9c27a','#7a6a5a',.18)));             // plinth
  }else{   // house, apartment, brick, stucco, civic, temple, shophouse
    const tall=kind==='civic'||kind==='temple'||kind==='stucco',m=kind==='civic'||kind==='temple'?.28:kind==='shophouse'?.2:.24;
    for(let j=0;j<floors;j++){const y=j*rh;
      if(kind==='stucco'||kind==='civic')box(0,y+rh-.16,L,.16,trim);
      for(let i=0;i<cols;i++){const x=bw*i+bw*m,w=bw*(1-2*m),y0=y+rh*(tall?.16:.22),d=rh*(tall?.66:.52);
        if(bw<.9)continue;
        win(x,y0,w,d,i*3+j);
        if(st.shutters){const c=shade(pickOf(st.shutters,F.seed+i));box(x-w*.36,y0,w*.32,d,c);box(x+w*1.04,y0,w*.32,d,c)}
        if(kind==='stucco'||kind==='civic'){box(x-.12,y0-.22,w+.24,.14,trim);box(x-.1,y0+d+.06,w+.2,.1,trim)}
        else box(x-.08,y0+d+.06,w+.16,.09,trim);
        if(st.balcony&&j<floors-1&&(i+F.seed)%(st.balcony===true?1:2)===0){box(x-.25,y0+d+.18,w+.5,.08,dark);for(let k=x-.2;k<x+w+.25;k+=.18)box(k,y0+d-.3,.035,.5,dark)}
      }
      if(kind==='brick'&&UPX<.5)for(let k=y+.25;k<y+rh;k+=.25)box(0,k,L,.012,shade('rgba(80,50,40,.18)'));
    }
    if(kind==='shophouse'||kind==='civic'||kind==='temple')for(let i=0;i<=cols;i++)box(Math.min(L-.18,i*bw-.09),0,.18,upper,trim);
    if(kind!=='house')box(0,0,L,.22,trim);
  }
  if(F.shop)shopfront(g,F,L,H,shopH,shade,box,poly,SEASON.night?['#ffe7a8','#ffd98a','#fde9b0']:glass);
  g.restore();
}
function shopfront(g,F,L,H,sh,shade,box,poly,glass){
  const st=F.st,y0=H-sh,bays=Math.max(1,Math.round(L/(st.bay||5.5))),bay=L/bays;
  const fascias=st.fascia||(CITY.shops||{}).fascias||['#526e75','#9f6554','#50776e','#a55649','#687aa0','#b77c36'];
  const ink=shade('#4f5f5c'),ivory=shade('#f5e8cc');
  box(0,y0,L,sh,shade(st.shopWall||'#a79180'));
  for(let j=0;j<bays;j++){
    g.save();g.translate(j*bay,y0);
    const fascia=shade(fascias[(F.seed+j)%fascias.length]),entry=j===Math.floor(bays/2);
    box(.12,.62,bay-.24,sh-.62,ink);
    box(.2,.7,bay-.4,sh-.82,glass[(F.seed+j)%glass.length]);
    poly([[.2,.7],[.2+(bay-.4)*.4,.7],[.2+(bay-.4)*.12,sh-.12],[.2,sh-.12]],shade('#e6ece2'));
    if(UPX<.6){   // goods on shelves behind the glass
      const goods=['#be8558','#8eac8f','#c17b6c','#d9bd78','#7f95ad'];
      for(let r=0;r<2;r++){const y=1.25+r*.62;box(.3,y+.36,bay-.6,.06,ivory);
        for(let k=0;k<6;k++)box(.36+k*(bay-.8)/6,y,(bay-.8)/6-.06,.34,shade(goods[(k+r+j+F.seed)%5]))}
    }
    const dw=Math.min(1.2,bay*.3),dx=entry?(bay-dw)/2:bay-dw-.3;
    box(dx,.7,dw,sh-.7,shade('#6f8c8a'));box(dx+.08,.8,dw-.16,sh*.35,shade('#b7cdc4'));
    box(.08,.06,bay-.16,.5,fascia);
    const text=entry||bays===1?F.sign:'';
    if(text&&UPX<.33){g.fillStyle=ivory;g.font='bold '+Math.min(.34,(bay-.4)/Math.max(3,text.length)*1.6).toFixed(2)+'px '+((CITY.shops||{}).font||'sans-serif');g.textAlign='center';g.textBaseline='middle';wallText(g,text,bay/2,.31,bay-.3)}
    g.restore();
  }
}

/* ---------- roofs ---------- */
// which way the ridge runs: along the footprint (long), across it (short), or parallel to the street it faces (street)
function ridgeFrame(b,st){
  const o=b.obb;let ax=o.ax,L=o.L,W=o.W;
  let mode=st.ridge||'long';
  if(mode==='street'){
    let best=null,bl=0;
    for(let i=0;i<b.ring.length;i++){const a=b.ring[i],c=b.ring[(i+1)%b.ring.length],len=Math.hypot(c[0]-a[0],c[1]-a[1]);if(len<2)continue;
      const m=[(a[0]+c[0])/2,(a[1]+c[1])/2],u=[(c[0]-a[0])/len,(c[1]-a[1])/len];
      const hit=[3,6].some(d=>[[u[1],-u[0]],[-u[1],u[0]]].some(n=>inRings([m[0]+n[0]*d,m[1]+n[1]*d],SCENE.roads)||inRings([m[0]+n[0]*d,m[1]+n[1]*d],SCENE.walk)));
      if(hit&&len>bl){bl=len;best=u}}
    mode=best&&Math.abs(best[0]*ax[0]+best[1]*ax[1])<.7?'short':'long';
  }
  if(mode==='short'){ax=[-ax[1],ax[0]];[L,W]=[W,L]}
  return {c:o.c,ax,L,W};
}
function pitchedRoof(b,st,wall,rise,kind,col){
  const o=ridgeFrame(b,st),ax=o.ax,nx=[-ax[1],ax[0]],e=st.eaves??.45,L2=o.L/2+e,W2=o.W/2+e,zE=wall-e*rise/(o.W/2+e),zR=wall+rise;
  const C=(s,t,z)=>[o.c[0]+ax[0]*s+nx[0]*t,o.c[1]+ax[1]*s+nx[1]*t,z];
  const planes=[];
  const add=(pts,isWall)=>{let n=vNewell(pts);if(!isWall&&n[2]<0){pts.reverse();n=vNewell(pts)}planes.push({p:pts,n,at:avg(pts),wall:isWall})};
  const ridge=kind==='pyramidal'?0:kind==='hipped'?Math.max(0,L2-W2):L2;
  if(kind==='gabled'){
    add([C(-L2,-W2,zE),C(L2,-W2,zE),C(L2,0,zR),C(-L2,0,zR)]);add([C(L2,W2,zE),C(-L2,W2,zE),C(-L2,0,zR),C(L2,0,zR)]);
    const g1=[C(-o.L/2,-o.W/2,wall),C(-o.L/2,o.W/2,wall),C(-o.L/2,0,zR-.05)],g2=[C(o.L/2,o.W/2,wall),C(o.L/2,-o.W/2,wall),C(o.L/2,0,zR-.05)];
    for(const gp of [g1,g2]){let n=vNewell(gp);const out=dot(n,[ax[0],ax[1],0])*(gp===g1?-1:1);if(out<0){gp.reverse();n=vNewell(gp)}planes.push({p:gp,n,at:avg(gp),wall:true})}
  }else{
    add([C(-L2,-W2,zE),C(L2,-W2,zE),C(ridge,0,zR),C(-ridge,0,zR)]);add([C(L2,W2,zE),C(-L2,W2,zE),C(-ridge,0,zR),C(ridge,0,zR)]);
    add([C(L2,-W2,zE),C(L2,W2,zE),C(ridge,0,zR)]);add([C(-L2,W2,zE),C(-L2,-W2,zE),C(-ridge,0,zR)]);
  }
  const tex=st.roofTex,wallC=pickOf(st.wall,b.id);
  return ()=>{const roofC=SEASON.snow?snowy(col,.82):col;return planes.filter(q=>vis(q.n)).sort((a,b)=>depthOf(a.at)-depthOf(b.at)).map(q=>{
    let s=shape(q.p,tone(q.n,soft(q.wall?wallC:roofC)),.6);
    if(!q.wall&&tex&&!SEASON.snow&&q.p.length===4){const u=norm(sub(q.p[1],q.p[0])),v=norm(sub(q.p[0],q.p[3]));s+=sheetInk(q.p,tex,u,v.map(x=>-x))}
    return s}).join('')+(st.ridgeCap!==false&&kind!=='pyramidal'?edge(C(-ridge,0,zR+.04),C(ridge,0,zR+.04),mix(roofC,'#3a3742',.4),Math.max(.12,(st.ridgeCap||.18))):'')};
}
function flatRoof(b,st,wall,col){
  const r=b.ring,rim=b.cut?0:(st.parapet??.5);
  const fixtures=[];
  if(st.rooftop!=='none'&&b.area>120&&!b.cut){
    const xs=r.map(p=>p[0]),ys=r.map(p=>p[1]);
    for(let x=Math.ceil(Math.min(...xs)/7)*7;x<Math.max(...xs);x+=7)for(let y=Math.ceil(Math.min(...ys)/9)*9;y<Math.max(...ys);y+=9){
      if(rnd(x*3.1+y*9.7+hash(b.id))>.16)continue;const fp=rect(x,y,2.6,1.8);if(!fp.every(p=>inside(p,r)))continue;
      fixtures.push({fp,draw:()=>peak(fp,wall,[x,y,wall+.01],'#c3c8c2')+shape(atZ(fp,wall+.75),'#d7dbd2',.45)+shape(atZ(rect(x,y,1.5,.8),wall+.82),'#9aa5a4',.3)});
    }
  }
  return ()=>{
    const roofC=SEASON.snow?snowy(col,.85):col;let s=shape(atZ(r,wall),roofC,.8);
    if(rim)for(let j=0;j<r.length;j++){const a=r[j],c=r[(j+1)%r.length];if(Math.hypot(c[0]-a[0],c[1]-a[1])<1)continue;
      s+=shape([...atZ([a,c],wall),...atZ([c,a],wall+rim)],mix(pickOf(st.wall,b.id),'#a99d90',.25),.45)+edge([...a,wall+rim],[...c,wall+rim],'#efe6d2',.14)}
    return s+fixtures.sort((p,q)=>depthOf([...p.fp[0],wall])-depthOf([...q.fp[0],wall])).map(x=>x.draw()).join('');
  };
}

/* ---------- helpers for hand-built landmarks (landmarks.js) ---------- */
// a full style object for walls(): the city's defaults with your changes
function makeStyle(o={}){return {facade:'plain',wall:['#eee2ca'],roofColour:['#c8c4b8'],roof:'flat',pitch:30,eaves:.45,levels:3,floor:LEVEL,shop:'none',parapet:.5,...(STYLES.default||{}),shop:'none',eave1:false,...o}}
// a gabled, hipped or pyramidal roof over any rectangle: centre c, ridge axis ax (unit), length L along it, width W
function roofOver({c,ax,L,W},wall,o={}){
  const st=makeStyle(o),b={id:'roof'+c.join(','),ring:[],obb:{c,ax,L,W,fill:1}},kind=o.roof||'gabled';
  const rise=o.rise||(W/2+st.eaves)*Math.tan(st.pitch*Math.PI/180);
  return pitchedRoof(b,{...st,ridge:'long'},wall,rise,kind,pickOf(st.roofColour,b.id));
}
// a flat-roofed block with painted elevations, as one model part: ring, base z, top z, style changes
function block(ring,z0,z1,o={}){const st=makeStyle(o),body=pickOf(st.wall,ring.join());const sides=walls(ring,z0,z1,{st,body});
  return {fp:ring,z1,draw:()=>sides()+shape(atZ(ring,z1),pickOf(o.top||st.flatRoof||st.roofColour,ring.join()),.7)}}

/* ---------- every building: generic block, or a hand-built landmark ---------- */
const REPLACED=new Set();
const LANDMARK_LIST=typeof LANDMARKS==='undefined'?[]:LANDMARKS;
for(const lm of LANDMARK_LIST)for(const id of lm.ids||[])REPLACED.add(id);
const findBuilding=id=>SCENE.buildings.find(b=>b.id===id)||SCENE.buildings.find(b=>b.of===id);   // an outline drawn as its parts: the first part
function buildingModel(b){
  const st=styleFor(b),kind=roofKind(b,st),{wall,top,rise}=heightsOf(b,st),z0=b.min||0;
  const body=pickOf(st.wall,b.id),roofCol=kind==='flat'&&st.roof!=='flat'&&st.roof!=='auto'?pickOf(st.flatRoof||'#c9c4ba',b.id+'r'):pickOf(kind==='flat'&&st.flatRoof?st.flatRoof:st.roofColour,b.id+'r');
  b.top=top;b.wall=wall;b.style=st;b.body=body;b.roofCol=roofCol;
  const shell=walls(b.ring,z0,wall,{st,b,body});
  const roof=kind==='flat'?flatRoof(b,st,wall,roofCol):pitchedRoof(b,st,wall,rise,kind,roofCol);
  return obj(b.ring,top+.3,()=>shell()+roof());
}
for(const b of SCENE.buildings){
  if(REPLACED.has(b.id)||REPLACED.has(b.of))continue;
  models.push(buildingModel(b));
}
for(const lm of LANDMARK_LIST){try{const out=lm.build();for(const m of [].concat(out))if(m)models.push(m)}catch(e){console.error('landmark',lm.name,e)}}

/* ccw(ring): the same outline running counter-clockwise. OSM outlines run either way; faces you build yourself from a ring
   ([a, b, b-up, a-up] for each edge a→b) face outward only on a counter-clockwise ring, so always pass rings through ccw. */
function ccw(r){const a=r.reduce((s,p,i)=>{const q=r[(i+1)%r.length];return s+p[0]*q[1]-q[0]*p[1]},0);return a<0?r.slice().reverse():r}
/* lightPool(x, y, r, colour, strength): light on the ground from a lamp, a fire or a tree, fading softly to its edge
   (stacked thin rings, brightest at the centre). Use a light colour (see LIT) so night does not dim it. */
function lightPool(x,y,r,col='#ffcf7a',a=.5,z=.03){let s='';const n=9;
  for(let k=n;k>=1;k--){const rr=r*k/n;s+='<g opacity="'+(a/n*1.6).toFixed(3)+'">'+shape(atZ(polygon(x,y,rr,Math.max(10,Math.round(rr*4))),z+.001*(n-k)),col,0)+'</g>'}
  return s}

/* standable(x, y): a person or a prop can stand here: inside the plot, not on water, not inside a building, and at least
   `gap` metres from the water's edge (the quay). Use it for any crowd or object a landmarks.js places by hand. */
function standable(x,y,gap=1){
  if(Math.abs(x)>HALF-.6||Math.abs(y)>HALF-.6)return false;
  const inRs=rs=>inside([x,y],rs[0])&&!rs.slice(1).some(h=>inside([x,y],h));
  for(const w of SCENE.water||[]){if(inRs(w))return false;
    if(gap>0)for(const r of w)for(let i=0;i<r.length;i++){const a=r[i],b=r[(i+1)%r.length],dx=b[0]-a[0],dy=b[1]-a[1],l=dx*dx+dy*dy||1,
      t=Math.max(0,Math.min(1,((x-a[0])*dx+(y-a[1])*dy)/l));if(Math.hypot(x-a[0]-dx*t,y-a[1]-dy*t)<gap)return false}}
  return !SCENE.buildings.some(b=>inside([x,y],b.ring));
}

/* ---------- planOrder: back-to-front order for parts that touch (a tower against a nave, wings of one building) ----------
   planSort compares footprints and can guess wrong when volumes touch or differ a lot in size. Here every pair whose
   footprints can be split by a line (allowing tol metres of overlap, e.g. eaves) is ordered by the side of that line
   the reader is on; pairs that overlap in plan go lower-first. Parts: {fp, z1, svg}. Use it for any landmark made of
   several volumes. */
function planOrder(parts,tol=.35){
  const n=parts.length,H=parts.map(p=>hull(p.fp.map(q=>[q[0],q[1]]))),after=parts.map(()=>new Set()),deg=new Array(n).fill(0);
  const sep=(A,B)=>{for(const P of [A,B])for(let i=0;i<P.length;i++){const a=P[i],b=P[(i+1)%P.length],m=norm([b[1]-a[1],a[0]-b[0],0]);
      const pa=A.map(q=>q[0]*m[0]+q[1]*m[1]),pb=B.map(q=>q[0]*m[0]+q[1]*m[1]);
      if(Math.max(...pa)<=Math.min(...pb)+tol)return m;if(Math.max(...pb)<=Math.min(...pa)+tol)return m.map(v=>-v)}return null};
  for(let i=0;i<n;i++)for(let j=i+1;j<n;j++){const m=sep(H[i],H[j]);let first;
    if(m)first=vis([m[0],m[1],0])?i:j;           // m points from i toward j: a reader on j's side sees j in front
    else first=(parts[i].z0||0)+parts[i].z1<=(parts[j].z0||0)+parts[j].z1?i:j;
    const second=first===i?j:i;if(!after[first].has(second)){after[first].add(second);deg[second]++}}
  const out=[],queue=[];for(let i=0;i<n;i++)if(!deg[i])queue.push(i);
  while(queue.length){const i=queue.shift();out.push(i);for(const j of after[i])if(!--deg[j])queue.push(j)}
  if(out.length<n)return planSort(parts);        // a cycle (interlocking shapes): fall back
  return out.map(i=>parts[i].svg).join('');
}

/* ---------- trees ---------- */
const TREE_RULES=(CITY.trees||{}).rules||[],TREE_DEFAULT={style:3,colours:['#8ab673','#adca7c'],height:8,...((CITY.trees||{}).default||{})};
const treeRule=sp=>TREE_RULES.find(r=>new RegExp(r.match,'i').test(sp))||TREE_DEFAULT;
const TREE_SOURCE=SCENE.trees.concat(((CITY.trees||{}).extra||[]).map(([x,y,h,sp])=>[x,y,-2,String(h||''),sp]));
// many trees (a wood): each one gets fewer, larger leaves, since crowns overlap and the detail never shows; this keeps turning smooth
const CITY_LOD=Math.max(.13,TREE_LOD*Math.min(1,220/Math.max(1,TREE_SOURCE.length)));
const TREES=TREE_SOURCE.map(([x,y,s,hs,extraSp],i)=>{
  const species=extraSp||SCENE.species[s]||'',base={...TREE_DEFAULT,...treeRule(species)};
  // a rule may hold a mix (woods: holm oak, pine, cypress): each tree picks one by its position, weighted by share
  let rule=base;if(base.mix){const tot=base.mix.reduce((a,m)=>a+(m.share||1),0);let r=rnd(x*.37+y*1.71)*tot;rule={...base,...(base.mix.find(m=>(r-=(m.share||1))<0)||base.mix[0])}}
  const h=(+hs||rule.height||8)*(rule.vary?1-rule.vary/2+rule.vary*rnd(x*1.3+y*.7):1);
  const style=rule.style||3,cols=rule.colours||TREE_DEFAULT.colours,m=soft(cols[i%cols.length]);
  const geo=makeTree(style,{x,y,H:h,seed:i+1,m,lod:CITY_LOD});
  // limbs: the same tree without its twigs. A tree in leaf is drawn from this, so no twig can poke out of its crown (twigs belong to bare trees)
  return {x,y,i,h,base:0,style,m,geo,limbs:{...geo,twigs:[]},ext:geo.ext,zTop:geo.zTop,rule,species};
});
const LOOK=new Map();
function treeLook(tr){
  let o=LOOK.get(tr);if(o)return o;
  const L=SEASON.leaves||'summer',r=tr.rule;
  o=r.evergreen?{}:L==='bare'?{keep:r.winter?.4:0,m:r.winter?soft(r.winter):undefined}
    :L==='spring'?{keep:.82,m:soft(r.spring||'#c4e481'),m2:soft('#a3d873'),share:.4}
    :L==='blossom'?(r.blossom?{keep:.96,m:soft(r.blossom),m2:soft(mix(r.blossom,'#ffffff',.4)),share:.45}:{keep:.85,m:soft(r.spring||'#c4e481')})
    :L==='autumn'?{keep:.86,m:soft(r.autumn||'#dba646'),m2:soft(mix(r.autumn||'#dba646','#c25a3c',.45)),share:.35}
    :{};
  const lit=SEASON.night&&SEASON.decor&&SEASON.decor.litTrees&&new RegExp(SEASON.decor.litTrees,'i').test(tr.species);   // light-up: these trees stay bright
  o={keep:1,...o};if(SEASON.night&&!lit){o.m=softNight(o.m||tr.m);if(o.m2)o.m2=softNight(o.m2)}LOOK.set(tr,o);return o;
}

/* ---------- people and vehicles ---------- */
const PEOPLE=CITY.people||{};
const SKINS=(PEOPLE.skin||['#f0c5a1','#dcaa82','#c48d65','#a87154','#f6d2b4']).map(soft);
const CLOTHES=PEOPLE.clothes||['#d68070','#538e91','#e2ad59','#7994b4','#b991a3','#efe3cd','#5f9e7f'];
const PANTS=PEOPLE.pants||['#515c70','#3f4a6e','#5a5560','#7a6a58','#2f3a52'],HAIR=PEOPLE.hair||['#2b211c','#3d2c1f','#1f1b22','#5a3a26','#8a6a4a'];
const pk=(list,r)=>list[Math.floor(r*list.length)%list.length];
function pedDressed(k){
  const o={skin:pk(SKINS,rnd(k*5.1)),shirt:pk(CLOTHES,rnd(k*6.3)),pants:pk(PANTS,rnd(k*7.9)),hair:pk(HAIR,rnd(k*8.7)),tall:.96+.1*rnd(k+2)};
  const oc=SEASON.dress;
  if(oc&&rnd(k*3.3+.7)<(oc.share??.6))o.shirt=pk(oc.colours,rnd(k*4.1));
  else if(SEASON.coats)winterWear(o,k);
  if(SEASON.umbrellas&&rnd(k+14)<.78)o.umb=soft(pk(PEOPLE.umbrellas||CLOTHES,rnd(k*2.3)));
  return o;
}
function bikeLook(k){const o={k,shirt:pk(CLOTHES,rnd(k*3.7)),frame:pk(PEOPLE.bikes||['#387779','#ba7663','#629684','#4b4b55'],rnd(k*1.9))};return SEASON.coats?winterWear(o,k):o}
const VEH=CITY.vehicles||{};
const VKINDS=(VEH.kinds||['sedan','hatch','suv','small','mpv']).map(kind=>makeCar(kind,{plate:VEH.plate||'#f2f2ee',frontPlate:VEH.frontPlate||VEH.plate||'#f2f2ee'}));
const TAXI=VEH.taxi?makeCar(VEH.taxi.kind||'sedan',{plate:VEH.plate||'#f2f2ee',sign:VEH.taxi.sign||'#fbefd5'}):null;
const isTaxi=k=>TAXI&&rnd(k*5.1)<(VEH.taxi.share||.2);
const carModel=k=>isTaxi(k)?TAXI:VKINDS[k%VKINDS.length];
const carProps=k=>({mesh:carModel(k),m:soft(isTaxi(k)?pk(VEH.taxi.colours||['#f2c230'],rnd(k*6.1)):pk(VEH.colours||['#d48a79','#eff0da','#90b7ab','#a5afcb','#4b4b55','#f2f2ee'],rnd(k*2.7)))});

/* ---------- seasons, weather and special occasions ---------- */
const SEASONS=(CITY.seasons||[{id:'summer',label:'Summer'}]).concat((CITY.occasions||[]).map(o=>({...o,special:true})));
let SEASON={},TRAFFIC=null,DECOR=null,GROUND,ROAD,PAVE,WALK,GRASS,WATER;
function setGroundColours(){
  const wet=c=>mix(c,'#6f7390',.14),sn=!!SEASON.snow;
  GROUND=sn?snowy(PAL.ground,.9):SEASON.wet?wet(PAL.ground):PAL.ground;
  PAVE=sn?snowy(PAL.pavement,.7):SEASON.wet?wet(PAL.pavement):PAL.pavement;
  WALK=sn?snowy(PAL.walk,.7):SEASON.wet?wet(PAL.walk):PAL.walk;
  ROAD=sn?snowy(PAL.road,.3):SEASON.wet?mix(PAL.road,'#7d82a8',.2):PAL.road;
  GRASS=sn?snowy(PAL.grass,.88):SEASON.grass||(SEASON.leaves==='bare'?mix(PAL.grass,'#c9bf98',.35):PAL.grass);   // "grass": "#hex" on a season overrides it (a Mediterranean winter is green)
  WATER=SEASON.ice?'#dfe9ec':PAL.water;
}
const FEEDS=SCENE.routes.map((r,i)=>({kind:r.kind,paths:[measuredLane({...r,junctions:[]})],interval:(r.kind==='car'?7.5:r.kind==='bike'?11:7)*(PHONE?1.4:1)}));
function setSeason(id){
  const st=SEASONS.find(s=>s.id===id)||SEASONS[0];
  SEASON={...st};SEASON_ID=st.id;LOOK.clear();DECOR=null;setGroundColours();
  const c=SEASON.crowd??1;
  const flow=FEEDS.map((f,i)=>({...f,walkSpeed:1.05+.05*(i%3),interval:f.interval/(f.kind==='ped'?c:Math.max(.4,Math.min(1.4,c)))}));
  TRAFFIC=streetSimulation(flow,Math.round((PHONE?90:150)*Math.min(1.6,c)),500);
}
setSeason(SEASON_Q||SEASONS[0].id);

/* ---------- night (a season or occasion with night: true) ----------
   Every colour the painter fills is turned to dusk; the warm light colours below stay as they are, so windows,
   shopfronts, lamps and fairy lights read as lit. No glow: lights are flat bright marks, like the rest of the style. */
const LIT=new Set(['#ffe6ec','#fbd3dd','#ffd98a','#ffe7a8','#fff3c4','#fbefc8','#f6c445','#ffb85c','#fff8e0','#f2c94c','#fde9b0','#ffcf7a','#ff8a3d','#f26a2e','#ffc069']);
const NIGHTC=new Map();
function nightCol(c){
  if(!SEASON.night||typeof c!=='string'||c[0]!=='#'||LIT.has(c))return c;
  let o=NIGHTC.get(c);if(o)return o;
  let h=c.slice(1);if(h.length===3||h.length===4)h=h.slice(0,3).split('').map(x=>x+x).join('');if(h.length<6)return c;
  const n=parseInt(h.slice(0,6),16),r=n>>16,g=n>>8&255,b=n&255,K=SEASON.night===true?1:+SEASON.night;
  const R=Math.round(r*(1-.5*K)+12*K),G=Math.round(g*(1-.52*K)+16*K),B=Math.round(b*(1-.4*K)+40*K);   // dusk: keep each colour's hue, sink it toward blue
  o='#'+((1<<24)+(Math.min(255,R)<<16)+(Math.min(255,G)<<8)+Math.min(255,B)).toString(16).slice(1);NIGHTC.set(c,o);return o;
}
const softNight=m=>SEASON.night&&m?{l:nightCol(m.l),m:nightCol(m.m),d:nightCol(m.d)}:m;
if(typeof compileInk==='function'){const inkOps=compileInk;compileInk=function(markup){const ops=inkOps(markup);
  if(SEASON.night)for(const op of ops){if(op.fill)op.fill=nightCol(op.fill);if(op.stroke)op.stroke=nightCol(op.stroke)}return ops}}

/* ---------- street furniture ---------- */
const streetFurniture=[];
const LAMP=CITY.lamp||{};
const LAMP_AT=[];   // lamp positions: at night their light pools are painted with the ground, so no part box clips them
function lamp(x,y){
  LAMP_AT.push([x,y]);
  const col=LAMP.colour||'#5d6b66',hgt=LAMP.height||5.2,head=LAMP.head||'#f3e7c4';
  streetFurniture.push(obj(rect(x,y,.5,.5),hgt+.5,()=>stick([x,y,0],[x,y,hgt],.07,col)+ball([x,y,hgt+.15],.24,SEASON.night?{l:'#fff3c4',m:'#fff3c4',d:'#ffd98a'}:soft(head),.4)+stick([x,y,hgt+.32],[x,y,hgt+.42],.1,col)));
}
for(const fu of SCENE.furniture||[]){
  if(fu.k==='lamp')lamp(fu.x,fu.y);
  else if(fu.k==='cafe'){const C=CITY.cafes||{},col=pickOf(C.umbrellas||['#f3efe4','#2f5f8a','#b8483b','#e8c36a'],'u'+fu.i),x=fu.x,y=fu.y,r=1.15;
    streetFurniture.push(Object.assign(obj(rect(x,y,2.3,2.3),2.6,()=>{let g=shape(atZ(polygon(x,y,.36,8),.74),C.table||'#f1ece0',.35)+stick([x,y,0],[x,y,.74],.04,'#6b6660');
      for(const a of [0,Math.PI])g+=shape(atZ(rect(x+Math.cos(a)*.62,y+Math.sin(a)*.62,.36,.36),.45),C.chair||'#8a6f55',.3);
      // "cafes":"closed" on a season folds the umbrellas (rain, off-hours); "cafes":false puts the tables away (see scene)
      const shut=SEASON.cafes==='closed',rr=shut?.2:r;
      g+=stick([x,y,.74],[x,y,2.25],.035,'#d8d2c6');const rim=polygon(x,y,rr,8,.39).map(p=>[...p,shut?1.2:1.95]),apex=[x,y,shut?2.3:2.45];
      for(let i=0;i<8;i++){const a=rim[i],b=rim[(i+1)%8],n=norm(cross(sub(b,a),sub(apex,a)));if(vis(n))g+=shape([a,b,apex],tone(n,soft(i%2&&C.stripes!==false?mix(col,'#ffffff',.55):col)),.35)}
      return g}),{kind:'cafe'}))}
  else if(fu.k==='bench'){const fp=rect(fu.x,fu.y,1.6,.6);streetFurniture.push(obj(fp,.9,()=>shape(atZ(fp,.45),'#a98a68',.45)+shape([[fu.x-.8,fu.y+.28,.48],[fu.x+.8,fu.y+.28,.48],[fu.x+.8,fu.y+.3,.9],[fu.x-.8,fu.y+.3,.9]],'#b39470',.4)))}
  else if(fu.k==='vending'){const fp=rect(fu.x,fu.y,1,.8);streetFurniture.push(obj(fp,1.9,()=>walls(fp,0,1.85,{st:{facade:'plain',floor:2,shop:'none'},body:'#d9dde0'})()+shape(atZ(fp,1.85),'#c9cdd0',.4)))}
  else if(fu.k==='bus_stop'&&fu.shelter){
    let best=null,bd=1e9;for(const r of SCENE.routes)if(r.kind==='car')for(let i=1;i<r.p.length;i++){const a=r.p[i-1],c=r.p[i],dx=c[0]-a[0],dy=c[1]-a[1],t=Math.max(0,Math.min(1,((fu.x-a[0])*dx+(fu.y-a[1])*dy)/(dx*dx+dy*dy||1))),d=Math.hypot(a[0]+dx*t-fu.x,a[1]+dy*t-fu.y);if(d<bd){bd=d;best=[dx,dy]}}
    if(!best)continue;const l=Math.hypot(...best),u=[best[0]/l,best[1]/l],n=[-u[1],u[0]];
    const at=(s,d)=>[fu.x+u[0]*s+n[0]*d,fu.y+u[1]*s+n[1]*d],q=(s0,s1,d0,d1)=>[at(s0,d0),at(s1,d0),at(s1,d1),at(s0,d1)];
    const roofFp=q(-3,3,-.9,.9);
    streetFurniture.push(obj(roofFp,2.9,()=>[-2.6,2.6].map(s=>stick([...at(s,.7),0],[...at(s,.7),2.7],.06,'#6b7275')).join('')+shape(atZ(q(-2.2,2.2,.3,.7),.46),'#9aa1a3',.35)+shape(atZ(roofFp,2.75),'#5e6568',.45)));
  }
}
if(!(SCENE.furniture||[]).some(f=>f.k==='lamp')&&LAMP.auto!==false){   // no mapped lamps: one every 24 m along each pavement edge
  const seen=[];
  for(const r of SCENE.routes){if(r.kind!=='ped')continue;const L=measuredLane({p:r.p,junctions:[]});
    for(let s=6;s<L.len-4;s+=24){const {p,d}=tAt(L,s),q=[p[0]+d[1]*.9,p[1]-d[0]*.9];
      if(seen.some(o=>Math.hypot(o[0]-q[0],o[1]-q[1])<14)||!inRings(q,SCENE.paths.concat(SCENE.walk)))continue;
      if(SCENE.buildings.some(b=>inside(q,b.ring)))continue;seen.push(q);lamp(...q)}}
}

/* ---------- boats moored on the quays and at anchor (prep.py places them; colours from CITY.boats) ---------- */
const BOATCFG={hulls:['#f3efe4','#f3efe4','#2f5f8a','#b8483b','#3f7a5c','#f3efe4'],stripes:['#2f5f8a','#b8483b','#3f7a5c','#e0b04a'],
  covers:['#3f6e9a','#5c8c6a','#c9c2b0'],inside:'#c8a27a',cabin:'#f6f3ea',...(CITY.boats||{})};
const BOATS=(SCENE.boats||[]).map(b=>{
  const L=b.l,W=Math.max(1.5,L*.31),ca=Math.cos(b.a*Math.PI/180),sa=Math.sin(b.a*Math.PI/180),k=b.k;
  const at=(u,v,z)=>[b.x+u*ca-v*sa,b.y+u*sa+v*ca,z];
  const N=7,st=[];for(let i=0;i<=N;i++)st.push(-1+2*i/N);
  const half=t=>Math.pow(Math.max(0,1-Math.pow(Math.abs(t),2.4)),.55);
  const side=sgn=>st.map(t=>({t,w:half(t)*sgn}));
  const outline=[...side(1),...side(-1).reverse()].filter((q,i,arr)=>i===0||Math.abs(q.w)>.01||Math.abs(arr[i-1].w)>.01);
  const sheer=t=>.95+.3*t*t,top=outline.map(q=>at(q.t*L/2,q.w*W/2,sheer(q.t))),low=outline.map(q=>at(q.t*L*.45,q.w*W*.38,.04));
  const hull=pickOf(BOATCFG.hulls,'h'+k),stripe=pickOf(BOATCFG.stripes,'s'+k),big=b.anchor&&L>=9;
  const cover=!big&&rnd(k*3.7)<.45?pickOf(BOATCFG.covers,'c'+k):null,sail=big&&rnd(k*1.3)<.55;
  const fp=rect(b.x,b.y,L,L).map(([x,y])=>[x,y]);
  return obj(polygon(b.x,b.y,L*.5,8),sail?L*1.3:2,()=>{
    let g='';
    for(let i=0;i<top.length;i++){const j=(i+1)%top.length,a1=top[i],b1=top[j],a0=low[i],b0=low[j];
      let n=norm([b1[1]-a1[1],-(b1[0]-a1[0]),-.12]);const mx=(a1[0]+b1[0])/2-b.x,my=(a1[1]+b1[1])/2-b.y;
      if(n[0]*mx+n[1]*my<0)n=[-n[0],-n[1],n[2]];if(!vis(n))continue;   // outward, whichever way the outline runs
      const mid=(p,q,t)=>p.map((v,d)=>v+(q[d]-v)*t);
      g+=shape([a0,b0,mid(b0,b1,.78),mid(a0,a1,.78)],tone(n,soft(hull)),.45)+shape([mid(a0,a1,.78),mid(b0,b1,.78),b1,a1],tone(n,soft(stripe)),.45)}
    g+=shape(top,cover||hull,.5);
    if(!cover){g+=shape(outline.map(q=>at(q.t*L*.4,q.w*W*.3,sheer(q.t)-.05)),BOATCFG.inside,.35);const inner=outline.map(q=>at(q.t*L*.36,q.w*W*.22,.6));g+=shape(inner,mix(BOATCFG.inside,'#5c4632',.25),.3);
      for(const t of [-.3,.2])g+=shape([at(t*L/2-.12,-W*.28,.8),at(t*L/2+.12,-W*.28,.8),at(t*L/2+.12,W*.28,.8),at(t*L/2-.12,W*.28,.8)],BOATCFG.inside,.3)}
    if(big){const cu=-.05*L,cl=L*.32,cw=W*.55,ch=1.1,box=[at(cu-cl/2,-cw/2,.9),at(cu+cl/2,-cw/2,.9),at(cu+cl/2,cw/2,.9),at(cu-cl/2,cw/2,.9)];
      g+=walls(box.map(p=>[p[0],p[1]]),.9,.9+ch,{st:{facade:'plain',floor:9,shop:'none'},body:BOATCFG.cabin})()+shape(box.map(p=>[p[0],p[1],.9+ch]),BOATCFG.cabin,.45)}
    if(sail){const m=at(L*.12,0,0);g+=stick([m[0],m[1],.9],[m[0],m[1],L*1.25],.05,'#8a8478')+stick([m[0],m[1],1.9],[...at(-L*.38,0,0).slice(0,2),1.9],.04,'#8a8478')}
    return g});
});

/* ---------- occasion decorations: bunting across the main streets, lanterns under shop eaves, flags on lamps ---------- */
function decorations(){
  if(DECOR)return DECOR;DECOR=[];const d=SEASON.decor;if(!d)return DECOR;
  const lines=SCENE.centerlines.length?SCENE.centerlines:SCENE.routes.filter(r=>r.kind==='car');
  const long=lines.map(l=>measuredLane({p:l.p,junctions:[]})).sort((a,b)=>b.len-a.len).slice(0,2);
  if(d.bunting)for(const [li,L] of long.entries())for(const k of [.25,.5,.75]){
    const {p,d:dir}=tAt(L,L.len*k),w=d.span||7,n=[-dir[1],dir[0]],a=[p[0]+n[0]*w,p[1]+n[1]*w,d.height||6.5],b=[p[0]-n[0]*w,p[1]-n[1]*w,d.height||6.5];
    const fp=[[a[0]+dir[0]*.2,a[1]+dir[1]*.2],[b[0]+dir[0]*.2,b[1]+dir[1]*.2],[b[0]-dir[0]*.2,b[1]-dir[1]*.2],[a[0]-dir[0]*.2,a[1]-dir[1]*.2]];
    DECOR.push({fp,h:a[2]+.3,anim:true,draw:t=>{
      const pts=[];for(let i=0;i<=14;i++){const u=i/14;pts.push([a[0]+(b[0]-a[0])*u,a[1]+(b[1]-a[1])*u,a[2]-Math.sin(Math.PI*u)*1.1])}
      let s=stick([a[0],a[1],0],a,.08,'#6b7275')+stick([b[0],b[1],0],b,.08,'#6b7275')+edge(pts[0],pts[14],'#6b6470',.05);
      for(let i=0;i<14;i++){const m=[(pts[i][0]+pts[i+1][0])/2,(pts[i][1]+pts[i+1][1])/2,(pts[i][2]+pts[i+1][2])/2],sw=Math.sin(t*3.2+i*.9+li)*.3;
        s+=shape([pts[i],pts[i+1],[m[0]+sw*.3,m[1]+sw*.3,m[2]-.9]],d.bunting[(i+li)%d.bunting.length],.4)}
      return s}});
  }
  if(d.lanterns){let n=0;for(const F of facades){if(!F.shop||n>(PHONE?60:140))continue;
    for(let s=1.2;s<F.len-.8;s+=d.lanternGap||2.6){const z=Math.min(F.h-.6,(F.st.shopHeight||3.2)-.1),x=F.start[0]+F.along[0]*s+F.n[0]*.55,y=F.start[1]+F.along[1]*s+F.n[1]*.55,c=d.lanterns[(n++)%d.lanterns.length];
      DECOR.push({fp:rect(x,y,.5,.5),h:z+.2,draw:()=>stick([x,y,z+.15],[x,y,z-.15],.02,'#3d3a44')+stick([x,y,z-.28],[x,y,z-.78],.2,c)+stick([x,y,z-.24],[x,y,z-.3],.12,'#2f2b33')+stick([x,y,z-.8],[x,y,z-.86],.12,'#2f2b33')})}}}
  if(d.fairy){   // strings of small lights along street fronts (under the eaves and over the shops) and the quay edge
    const cols=d.fairy,dot=(p,c)=>stick(p,[p[0],p[1],p[2]+.02],.075,c);let n=0;
    for(const F of facades){if(!F.street||F.cut||F.len<3||n>(PHONE?90:220))continue;n++;
      const zs=[F.h-.45];if(F.shop)zs.push(F.z+(F.st.shopHeight||3.2)+.25);
      const pts=[];
      for(const z of zs){const segs=Math.max(1,Math.round(F.len/4));for(let k=0;k<segs;k++)for(let s=0;s<=8;s++){const u=(k+s/8)/segs,sag=Math.sin(Math.PI*s/8)*.35;
        pts.push([F.start[0]+F.along[0]*u*F.len+F.n[0]*.18,F.start[1]+F.along[1]*u*F.len+F.n[1]*.18,z-sag])}}
      const fp=[F.start,[F.start[0]+F.along[0]*F.len,F.start[1]+F.along[1]*F.len]].map(p=>[p[0]+F.n[0]*.4,p[1]+F.n[1]*.4]);
      const ring=[fp[0],fp[1],[fp[1][0]-F.n[0]*.5,fp[1][1]-F.n[1]*.5],[fp[0][0]-F.n[0]*.5,fp[0][1]-F.n[1]*.5]];
      DECOR.push({fp:ring,h:F.h,draw:()=>vis([F.n[0],F.n[1],0])?pts.map((p,i)=>dot(p,cols[i%cols.length])).join(''):''})}
    for(const line of SCENE.shore||[]){   // along the water's edge, in short runs so boats and people sort against them
      const pts=[];for(let i=0;i<line.length-1;i++){const a=line[i],b=line[i+1],l=Math.hypot(b[0]-a[0],b[1]-a[1]);for(let s=0;s<l;s+=.6)pts.push([a[0]+(b[0]-a[0])*s/l,a[1]+(b[1]-a[1])*s/l,.3])}
      for(let k=0;k<pts.length;k+=8){const run=pts.slice(k,k+9);if(!run.length)continue;
        const xs=run.map(p=>p[0]),ys=run.map(p=>p[1]),fp=[[Math.min(...xs)-.2,Math.min(...ys)-.2],[Math.max(...xs)+.2,Math.min(...ys)-.2],[Math.max(...xs)+.2,Math.max(...ys)+.2],[Math.min(...xs)-.2,Math.max(...ys)+.2]];
        DECOR.push({fp,h:.45,draw:()=>run.map((p,i)=>dot(p,cols[(i+k)%cols.length])).join('')})}}
  }
  if(d.flags)for(const [i,item] of streetFurniture.entries()){if(i%2)continue;const [x,y]=avg(item.fp.map(p=>[...p,0]));const h=item.h-1,c=d.flags[i%d.flags.length];
    DECOR.push({fp:rect(x,y,.9,.9),h:h+.6,anim:true,draw:t=>{const sw=Math.sin(t*2.6+i)*.12;return shape([[x,y,h+.5],[x+.7,y+sw,h+.45],[x+.7,y+sw,h-.15],[x,y,h-.1]],c,.35)}})}
  return DECOR;
}

/* ---------- the ground: plate, streets, green, water, markings, shadows ---------- */
const CENTER=SCENE.centerlines.map(l=>measuredLane({p:l.p,junctions:[]}));
const CROSSING=SCENE.markings.map(p=>measuredLane({p,junctions:[]}));
function cityGround(){
  const top=atZ(BASE_CORNERS,0);let g='';
  for(const l of SCENE.lawns)g+=surface(l.r,GRASS);
  for(const w of SCENE.water||[])g+=surface(w,WATER);
  for(const w of SCENE.sand||[])g+=surface(w,SEASON.snow?snowy(PAL.sand,.8):PAL.sand);
  for(const w of SCENE.quayShade||[])g+=surface(w,mix(WATER,'#2f6474',.32));   // the quay wall's shadow on the water
  for(const p of SCENE.walk)g+=surface(p,WALK);
  for(const p of SCENE.paths)g+=surface(p,PAVE);
  for(const p of SCENE.roads)g+=surface(p,ROAD);
  for(const p of SCENE.quay||[])g+=surface(p,SEASON.snow?'#f4f1ea':PAL.quay);   // stone coping along the water's edge
  if(SEASON.night)for(const [x,y] of LAMP_AT)g+=lightPool(x,y,3.4,'#ffcf7a',.55);
  if(SEASON.night&&SEASON.decor&&SEASON.decor.litTrees){const re=new RegExp(SEASON.decor.litTrees,'i');for(const tr of TREES)if(re.test(tr.species))g+=lightPool(tr.x,tr.y,tr.ext*1.3+1,'#fff3c4',.5)}
  g+='<pavementink/>';
  let paint='';
  for(const lane of CENTER)for(let s=3;s<lane.len-2;s+=7.4){const {p,d}=tAt(lane,s);paint+=stripeAt(p,d,2.9,.15)}
  for(const lane of CROSSING)for(let s=.4;s<lane.len;s+=1.1){const {p,d}=tAt(lane,s);paint+=stripeAt(p,d,.46,2.4)}
  if(paint)g+=fill(paint,SEASON.snow?'#f7f3ea':PAL.marking);
  for(const r of SCENE.rails||[])for(const off of [-.72,.72]){const L=measuredLane({p:r.p,junctions:[]}),pts=[];for(let s=0;s<=L.len;s+=1){const {p,d}=tAt(L,s);pts.push([p[0]-d[1]*off,p[1]+d[0]*off,.02])}
    if(pts.length>1)g+='<path d="'+pd(pts,false)+'" fill="none" stroke="'+PAL.rail+'" style="stroke-width:'+f(.11)+'"/>'}
  let sh='';
  for(const m of models)sh+=castShadow([...atZ(m.fp,0),...atZ(m.fp,Math.min(m.h,30))]);
  for(const tr of TREES)sh+=castShadow([...atZ(sq(tr.x,tr.y,.35),0),...atZ(polygon(tr.x,tr.y,tr.ext*.72,10),tr.h*.68)]);
  const slabWalls=BASE_CORNERS.map((a,i)=>{const b=BASE_CORNERS[(i+1)%4],n=norm([b[1]-a[1],a[0]-b[0],0]);
    let svg=vis(n)?shape([[...a,-SLAB],[...b,-SLAB],[...b,0],[...a,0]],tone(n,soft(PAL.slab)),.7):'';
    // where the sea or a river reaches the edge, the cut shows water down to a sandy bed
    if(svg&&(SCENE.water||[]).length){const len=Math.hypot(b[0]-a[0],b[1]-a[1]),steps=Math.ceil(len/.8),runs=[];let s0=null;
      for(let k=0;k<=steps;k++){const t=k/steps,q=[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t],inn=[q[0]-n[0]*.3,q[1]-n[1]*.3];
        const w=k<steps&&SCENE.water.some(rs=>inside(inn,rs[0])&&!rs.slice(1).some(h=>inside(inn,h)));
        if(w&&s0===null)s0=t;if(!w&&s0!==null){runs.push([s0,t]);s0=null}}
      const at=(t,z)=>[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,z],deep=-SLAB*.72;
      for(const [t0,t1] of runs)svg+=shape([at(t0,deep),at(t1,deep),at(t1,0),at(t0,0)],tone(n,soft(mix(WATER,'#3f7f95',.28))),.6)+
        shape([at(t0,-SLAB),at(t1,-SLAB),at(t1,deep),at(t0,deep)],tone(n,soft(mix(PAL.sand||'#ecd9a8',PAL.slab,.4))),.5)}
    return {at:[(a[0]+b[0])/2,(a[1]+b[1])/2,0],svg}});
  return byDepth(slabWalls)+shape(top,GROUND,.75)+clipTo(top,g+'<g opacity="'+(SEASON.wet?'.18':SEASON.haze?'.14':SEASON.snow?'.3':'.45')+'">'+sh+'</g>');
}
/* ---------- water: a painted wash, reflections and ripples (the look of the atlas's Amsterdam canals) ----------
   1. a wash: one soft gradient over the whole plate, a darker band that hugs the banks, a bright waterline. Painted once
      per season into a texture and reused on every redraw.
   2. reflections: every waterside building, tree and boat mirrored in the water. A point h metres up is seen in the water
      h * cot(pitch) metres toward the viewer, so each reflection is its footprint swept that way; it fades with distance.
   3. ripples: short light and dark strokes that drift, drawn with each frame (they stop when the simulation is paused).
   Frozen water (a season with "ice") keeps the plain flat fill. */
const WATERS=SCENE.water||[],inW=p=>inRings(p,WATERS);
const WATER_BANK=new Path2D();let WATER_REACH=3,WATER_AREA=0;
{ const edge=p=>Math.max(Math.abs(p[0]),Math.abs(p[1]))>HALF-1.4;let bank=0;   // a side of the water on the plate's edge is open water, not a bank
  for(const rs of WATERS)rs.forEach((r,k)=>{WATER_AREA+=areaOf(r)*(k?-1:1);
    for(let i=0;i<r.length;i++){const a=r[i],b=r[(i+1)%r.length];if(edge(a)&&edge(b))continue;WATER_BANK.moveTo(a[0],a[1]);WATER_BANK.lineTo(b[0],b[1]);bank+=Math.hypot(b[0]-a[0],b[1]-a[1])}});
  WATER_REACH=Math.max(.7,Math.min(3.6,bank?WATER_AREA*2/bank*.3:3)); }   // a narrow canal gets a narrow band
const nearWater=(x,y,r)=>{for(let k=0;k<12;k++){const a=k*Math.PI/6;if(inW([x+Math.cos(a)*r,y+Math.sin(a)*r])||inW([x+Math.cos(a)*r*.5,y+Math.sin(a)*r*.5]))return true}return false};
const WATERSIDE=WATERS.length?SCENE.buildings.filter(b=>{const c=b.obb?b.obb.c:b.ring[0];return nearWater(c[0],c[1],46)}).map(b=>({b,ring:ccw(b.ring),c:b.obb?b.obb.c:b.ring[0]})):[];
let WATER_TREES=null;   // trees close enough to show in the water (worked out on first use: TREES is built later)
const RIPPLES=[];
if(WATERS.length){const want=Math.max(50,Math.min(PHONE?320:760,Math.round(WATER_AREA/13)));
  for(let i=0;i<60000&&RIPPLES.length<want;i++){const x=(rnd(i*2.41+.33)-.5)*2*HALF,y=(rnd(i*4.71+1.5)-.5)*2*HALF;
    if(!inW([x,y]))continue;let ok=true;for(let k=0;k<6&&ok;k++){const a=k*Math.PI/3;ok=inW([x+Math.cos(a)*1.5,y+Math.sin(a)*1.5])}
    if(ok)RIPPLES.push({x,y,len:.42+rnd(i+6)*1.6,ph:rnd(i+.21)*6.28,k:rnd(74+i)})}}
const WASHES=new Map();
function waterWash(){
  const N=c=>SEASON.night?nightCol(c):c,key=WATER+'|'+(SEASON.night||0);let cv=WASHES.get(key);if(cv)return cv;
  const res=PHONE?2.5:4,size=Math.round(2*HALF*res);cv=makeSurface(size,size);const g=cv.getContext('2d');
  g.setTransform(res,0,0,res,HALF*res,HALF*res);
  const wash=g.createLinearGradient(-HALF*.86,HALF*.58,HALF*.92,-HALF*.3);
  [mix(WATER,'#2f8796',.24),mix(WATER,'#e2f6e8',.3),mix(WATER,'#2f8796',.13)].forEach((c,i)=>wash.addColorStop(i*.5,N(c)));
  g.fillStyle=wash;g.fillRect(-HALF,-HALF,2*HALF,2*HALF);
  g.lineCap=g.lineJoin='round';g.strokeStyle=N(mix(WATER,'#1d5b68',.75));g.globalAlpha=.04;
  for(let i=14;i>0;i--){g.lineWidth=2*WATER_REACH*i/14;g.stroke(WATER_BANK)}
  g.globalAlpha=.6;g.strokeStyle=N(mix(WATER,'#ffffff',.62));g.lineWidth=.2;g.stroke(WATER_BANK);
  WASHES.set(key,cv);return cv;
}
function waterInk(ctx){
  const N=c=>SEASON.night?nightCol(c):c,A=(hex,a)=>{const c=N(hex);return 'rgba('+parseInt(c.slice(1,3),16)+','+parseInt(c.slice(3,5),16)+','+parseInt(c.slice(5,7),16)+','+a+')'};
  ctx.drawImage(waterWash(),-HALF,-HALF,2*HALF,2*HALF);
  const deep=mix(WATER,'#1d5b68',.6);
  ctx.fillStyle=A(deep,.3);for(const w of SCENE.quayShade||[]){ctx.beginPath();for(const r of w){ctx.moveTo(r[0][0],r[0][1]);for(let i=1;i<r.length;i++)ctx.lineTo(r[i][0],r[i][1]);ctx.closePath()}ctx.fill('evenodd')}
  let d=[CAM_V[0]/CAM_V[2],CAM_V[1]/CAM_V[2]];   // where a point one metre up is mirrored: toward the viewer
  {const l=Math.hypot(d[0],d[1]);if(l>2.8)d=[d[0]*2.8/l,d[1]*2.8/l]}   // a camera almost level with the water would smear a wall across the whole harbour
  // Reflections are broken up by the ripples. The water is cut into level bands (along CAM_R, level on the screen); the bands
  // fall into a few groups, and each group draws the whole mirror image nudged sideways by its own amount and at its own
  // strength. A wall's straight edge comes out ragged and the image soft, never a ruled sheet
  const rx=CAM_R[0],ry=CAM_R[1],nl=Math.hypot(d[0],d[1])||1,nx=d[0]/nl,ny=d[1]/nl,L=HALF*1.5,G=PHONE?4:6,groups=Array.from({length:G},()=>new Path2D());
  for(let v=-L,i=0;v<L;i++){const th=.26+rnd(i*1.7+.2)*.5,ax=nx*v,ay=ny*v,bx=nx*(v+th),by=ny*(v+th),band=groups[Math.floor(rnd(i*3.1+.9)*G)%G];
    band.moveTo(ax-rx*L,ay-ry*L);band.lineTo(ax+rx*L,ay+ry*L);band.lineTo(bx+rx*L,by+ry*L);band.lineTo(bx-rx*L,by-ry*L);band.closePath();v+=th}
  const TINT='#517f83',K0=SEASON.night?.34:.5;
  // buildings: the footprint swept toward the viewer, the walls in the wall colour and the roof beyond them in the roof colour.
  // Only what lies past the quay lands on the water
  const sweep=(ring,bx,by,ox,oy)=>{ctx.beginPath();
    for(let i=0;i<ring.length;i++){const a=ring[i],e=ring[(i+1)%ring.length],q=[[a[0]+bx,a[1]+by],[e[0]+bx,e[1]+by],[e[0]+bx+ox,e[1]+by+oy],[a[0]+bx+ox,a[1]+by+oy]];
      if((e[0]-a[0])*oy-(e[1]-a[1])*ox<0)q.reverse();   // every piece runs the same way round, so the pieces add up to one shape
      ctx.moveTo(q[0][0],q[0][1]);for(let k=1;k<4;k++)ctx.lineTo(q[k][0],q[k][1]);ctx.closePath()}
    ctx.fill()};
  if(!WATER_TREES)WATER_TREES=TREES.filter(tr=>nearWater(tr.x,tr.y,tr.h*2.2+4));
  const ang=Math.atan2(d[1],d[0]);
  for(let g=0;g<G;g++){
    const K=K0*(.42+.58*rnd(g*7.3+1.1)),sh=Math.sin(g*2.4+.6)*.62+Math.sin(g*1.3+2)*.4;
    ctx.save();ctx.clip(groups[g]);ctx.translate(rx*sh,ry*sh);
    for(const {b,ring} of WATERSIDE){const h=Math.min(b.wall||0,34),top=Math.min(Math.max(b.top||h,h),h+9);if(h<2||REPLACED.has(b.id)||REPLACED.has(b.of))continue;
      ctx.fillStyle=A(mix(b.body||'#e8dcc4',TINT,.4),K);sweep(ring,0,0,d[0]*h,d[1]*h);
      if(top>h+.4){ctx.fillStyle=A(mix(b.roofCol||'#b9b4aa',TINT,.4),K);sweep(ring,d[0]*h,d[1]*h,d[0]*(top-h),d[1]*(top-h))}}
    // trees: the trunk as a line, the crown as a soft blob in the season's leaf colour
    for(const tr of WATER_TREES){const look=treeLook(tr),zc=tr.h*.67,cx=tr.x+d[0]*zc,cy=tr.y+d[1]*zc;
      ctx.strokeStyle=A(mix('#7a6654',TINT,.4),K*.8);ctx.lineWidth=.24;ctx.beginPath();ctx.moveTo(tr.x,tr.y);ctx.lineTo(tr.x+d[0]*tr.h*.5,tr.y+d[1]*tr.h*.5);ctx.stroke();
      if((look.keep??1)<.3)continue;
      ctx.fillStyle=A(mix((look.m||tr.m).m,TINT,.3),K);ctx.beginPath();ctx.ellipse(cx,cy,tr.h*.27*nl+tr.ext*.45,tr.ext*.8,ang,0,Math.PI*2);ctx.fill()}
    ctx.restore()}
  // boats: a dark patch under each hull (solid: it is shade as much as reflection)
  ctx.fillStyle=A(deep,.32);
  (SCENE.boats||[]).forEach((b,i)=>{if(SEASON.boats!=null&&rnd(i*5.31+2.7)>=SEASON.boats)return;
    ctx.beginPath();ctx.ellipse(b.x+d[0]*.5,b.y+d[1]*.5,b.l*.5,Math.max(1.5,b.l*.31)*.52,b.a*Math.PI/180,0,Math.PI*2);ctx.fill()});
}
// ripples: light and dark strokes lying level on the screen, each swaying a little; one path each
function waterRipples(t){
  if(SEASON.ice||!RIPPLES.length)return '';
  let light='',dark='';const step=PHONE?2:1;
  for(let i=0;i<RIPPLES.length;i+=step){const r=RIPPLES[i],q=P(r.x+Math.sin(t*.45+r.ph)*.18,r.y+Math.cos(t*.35+r.ph)*.09,0);
    if(q[0]<-4||q[1]<-4||q[0]>VIEW_BOX[0]+4||q[1]>VIEW_BOX[1]+4)continue;
    const half=r.len*(.56+.16*Math.sin(t*.6+r.ph))*CAM_K,seg='M'+f(q[0]-half)+' '+f(q[1])+'Q'+f(q[0]-.15*half)+' '+f(q[1]-.14*CAM_K)+' '+f(q[0]+half)+' '+f(q[1]+.06*CAM_K);
    if(r.k>.6){light+=seg;if(r.k>.83)light+='M'+f(q[0]-.11*half)+' '+f(q[1]+.29*CAM_K)+'L'+f(q[0]+.51*half)+' '+f(q[1]+.28*CAM_K)}else dark+=seg}
  const w=INK_K;
  return (dark?'<path d="'+dark+'" fill="none" stroke="'+mix(WATER,'#1d5b68',.62)+'" stroke-opacity=".34" style="stroke-width:'+(w*.85).toFixed(2)+'" stroke-linecap="round"/>':'')
    +(light?'<path d="'+light+'" fill="none" stroke="'+mix(WATER,'#f4fbf0',.82)+'" stroke-opacity=".72" style="stroke-width:'+(w*1.05).toFixed(2)+'" stroke-linecap="round"/>':'');
}
function paintSingaporeGround(ctx){
  // at night the paving joints, grass strokes and ripples painted here are dimmed like everything else
  if(SEASON.night){const proto=Object.getPrototypeOf(ctx);for(const k of ['strokeStyle','fillStyle']){const d=Object.getOwnPropertyDescriptor(proto,k);
    Object.defineProperty(ctx,k,{configurable:true,get(){return d.get.call(this)},set(v){d.set.call(this,typeof v==='string'?nightCol(v):v)}})}
    try{paintGroundInk(ctx)}finally{delete ctx.strokeStyle;delete ctx.fillStyle}return}
  paintGroundInk(ctx);
}
/* pavingInk: the joints and stones of the pavements, in CITY.paving.style
   'grid'       square joints only (the old look; size = slab size)
   'slabs'      stone slabs in running bond, each a slightly different tone (piazzas, Mediterranean towns)
   'ishidatami' long narrow granite slabs in running bond (Kyoto lanes)
   'tiles'      square concrete tiles with a faint tone change (modern city pavements)
   colour = joint colour; stone = slab colour (defaults from the walk colour) */
function pavingInk(ctx,groups,pv,H){
  const st=pv.style||'tiles',snow=SEASON.snow,joint=snow?'#e2ddd2':pv.colour||PAL.paving;
  let x0=H,y0=H,x1=-H,y1=-H;for(const rings of groups)for(const r of rings)for(const [x,y] of r){x0=Math.min(x0,x);y0=Math.min(y0,y);x1=Math.max(x1,x);y1=Math.max(y1,y)}
  if(st==='grid'){ctx.strokeStyle=joint;ctx.lineWidth=.05;ctx.beginPath();const s=pv.size||2.4;
    for(let i=-H;i<H;i+=s){ctx.moveTo(i,-H);ctx.lineTo(i,H);ctx.moveTo(-H,i);ctx.lineTo(H,i)}ctx.stroke();return}
  const spec={slabs:{h:.62,a:.7,b:1.5,var:.09},ishidatami:{h:.45,a:1.0,b:2.1,var:.11},tiles:{h:.6,a:.6,b:.6,var:.05}}[st]||{h:.6,a:.8,b:1.4,var:.08};
  const h=pv.size||spec.h,base=snow?'#f1eee8':pv.stone||WALK,N=x=>SEASON.night?nightCol(x):x;
  // one patch of paving (16 rows) is drawn once and repeated: a single fill instead of a rectangle per stone on every redraw
  const ppm=[12,24,36,48,72].find(v=>v>=1.6/UPX)||72,key=[st,h,base,joint,ppm,!!SEASON.night].join('|');
  let cv=PAVE_PATCH.get(key);
  if(!cv){
    const rows=16,Wm=spec.a===spec.b?spec.a*16:spec.b*9,W=Math.round(Wm*ppm),Hh=Math.round(h*ppm)*rows;cv=new OffscreenCanvas(W,Hh);const g=cv.getContext('2d');
    const tones=[mix(base,'#ffffff',spec.var),base,mix(base,'#5e564f',spec.var*.8),mix(base,'#d8b98c',spec.var)].map(N);
    g.strokeStyle=N(mix(joint,'#4f4740',.15));g.lineWidth=Math.max(1,(st==='tiles'?.03:.045)*ppm);let k=0;
    for(let r=0;r<rows;r++){const y=r*Hh/rows,hh=Hh/rows;let x=-rnd(r*3.7+h)*spec.b*ppm;
      while(x<W){const L=(spec.a===spec.b?spec.a:spec.a+rnd(k*1.37+r)*(spec.b-spec.a))*ppm,x2=spec.a===spec.b?x+L:Math.min(x+L,W+1);
        g.fillStyle=tones[Math.floor(rnd(k*2.91+.3)*4)%4];g.fillRect(x,y,x2-x,hh);if(x<0)g.fillRect(x+W,y,x2-x,hh);   // the stone cut by the left edge finishes at the right edge
        for(const jx of x<0?[x+W]:[x]){g.beginPath();g.moveTo(Math.round(jx)+.5,y);g.lineTo(Math.round(jx)+.5,y+hh);g.stroke()}x=x2;k++}
      g.beginPath();g.moveTo(0,Math.round(y)+.5);g.lineTo(W,Math.round(y)+.5);g.stroke()}
    PAVE_PATCH.set(key,cv)}
  ctx.save();ctx.scale(1/ppm,1/ppm);ctx.fillStyle=ctx.createPattern(cv,'repeat');ctx.fillRect(x0*ppm,y0*ppm,(x1-x0)*ppm,(y1-y0)*ppm);ctx.restore();
}
const PAVE_PATCH=new Map();
function paintGroundInk(ctx){
  const X=Dv(1,0,0),Y=Dv(0,1,0),o=P(0,0,0),H=HALF+2;
  ctx.save();ctx.transform(...X,...Y,...o);
  function onRings(groups,draw){ctx.save();ctx.beginPath();for(const rings of groups)for(const r of rings){ctx.moveTo(...r[0]);for(let i=1;i<r.length;i++)ctx.lineTo(...r[i]);ctx.closePath()}ctx.clip('evenodd');draw();ctx.restore()}
  if(!SEASON.ice&&WATERS.length)onRings(WATERS,()=>waterInk(ctx));
  const pv=CITY.paving||{};
  if(UPX<.6)onRings(SCENE.walk.concat(SCENE.paths),()=>pavingInk(ctx,SCENE.walk.concat(SCENE.paths),pv,H));
  if(SEASON.wet)onRings(SCENE.walk.concat(SCENE.paths),()=>{   // rain: shallow puddles on squares and pavements, each a pale patch with a bright edge
    for(let i=0;i<(PHONE?220:520);i++){const x=rnd(i+5.2)*2*H-H,y=rnd(i+71.9)*2*H-H,l=.5+rnd(i*3.3)*1.5,w=.18+rnd(i*1.7)*.2;
      ctx.save();ctx.translate(x,y);ctx.rotate(rnd(i*9.1)*3.14);ctx.fillStyle='rgba(170,188,202,.55)';ctx.beginPath();ctx.ellipse(0,0,l,w,0,0,Math.PI*2);ctx.fill();
      ctx.strokeStyle='rgba(236,242,246,.7)';ctx.lineWidth=.035;ctx.beginPath();ctx.ellipse(0,0,l*.6,w*.45,0,3.4,5.6);ctx.stroke();ctx.restore()}});
  if(!SEASON.snow)onRings(SCENE.lawns.map(l=>l.r),()=>{ctx.strokeStyle=mix(GRASS,'#5d7a58',.25);ctx.lineWidth=.12;ctx.beginPath();
    for(let i=0;i<(PHONE?500:1200);i++){const x=rnd(i+.4)*2*H-H,y=rnd(i+143.4)*2*H-H;ctx.moveTo(x-.18,y);ctx.lineTo(x,y+.29);ctx.lineTo(x+.16,y+.1)}ctx.stroke()});
  onRings(SCENE.roads,()=>{
    for(let i=0;i<(PHONE?500:1300);i++){const x=rnd(i+.36)*2*H-H,y=rnd(i+2.41)*2*H-H;ctx.fillStyle=i%2?mix(ROAD,'#ffffff',.18):mix(ROAD,'#5d5867',.15);ctx.fillRect(x,y,.15+rnd(i*9)*.26,.13)}
    ctx.lineWidth=.15;ctx.strokeStyle=PAL.kerb;for(const p of SCENE.roads)for(const r of p){ctx.beginPath();ctx.moveTo(...r[0]);for(const q of r.slice(1))ctx.lineTo(...q);ctx.closePath();ctx.stroke()}
    if(SEASON.wet)for(const [j,lane] of CENTER.entries())for(let s=2,i=0;s<lane.len-2;s+=3.6+rnd(i++ +j)*5){const {p,d}=tAt(lane,s),off=2.4*(i%2?1:-1);
      ctx.save();ctx.translate(p[0]-d[1]*off,p[1]+d[0]*off);ctx.rotate(Math.atan2(d[1],d[0]));const l=.8+rnd(i+j*17)*2.4;ctx.fillStyle='#a5b5bd';ctx.beginPath();ctx.ellipse(0,0,l,.3,0,0,Math.PI*2);ctx.fill();ctx.restore()}
  });
  if(SEASON.night&&SEASON.decor&&SEASON.decor.fairy&&(SCENE.water||[]).length)onRings(SCENE.water,()=>{   // lit quays shimmer on the water
    ctx.save();ctx.globalAlpha=.55;ctx.strokeStyle='#ffcf7a';ctx.lineWidth=.12;ctx.beginPath();let i=0;
    for(const rs of SCENE.quay||[])for(const q of rs[0]){if((i++)%3)continue;for(let k=0;k<4;k++){const x=q[0]+(rnd(i*3.1+k)-.5)*9,y=q[1]+(rnd(i*7.7+k*1.3)-.5)*9,l=.5+rnd(i+k*5)*1.6;ctx.moveTo(x,y);ctx.lineTo(x+l,y+l*.2)}}
    ctx.stroke();ctx.restore()});
  if(SEASON.ice&&WATERS.length)onRings(WATERS,()=>{ctx.strokeStyle='#f2f6ef';ctx.lineWidth=.08;ctx.beginPath();for(let i=0;i<260;i++){const x=rnd(i+7.1)*2*H-H,y=rnd(i+3.3)*2*H-H,l=.6+rnd(i)*1.4;ctx.moveTo(x,y);ctx.lineTo(x+l,y)}ctx.stroke()});   // ice keeps a few scratches
  ctx.restore();
}

/* ---------- the frame ---------- */
const EXTRA=typeof CITY_EXTRA==='function'?CITY_EXTRA:null;   // landmarks.js may add its own parts per frame
/* many trees (a wood): each crown is painted from fewer, larger leaf sprays. A crown is 43 sprays; with 500 trees that is 21 000
   fills and strokes on every redraw. Crowns overlap in a wood, so thinning them keeps the look and makes turning smooth. */
let CROWNS_READY=false;
function thinCrowns(){
  CROWNS_READY=true;const q=Math.min(1,110/Math.max(1,TREES.length));if(q>=1)return;   // a budget of about 110 full crowns for the whole city
  for(const tr of TREES){const all=makeSprays(tr),n=Math.max(9,Math.round(all.length*q)),step=all.length/n,k=Math.sqrt(all.length/n)*.97;
    tr.sprays=Array.from({length:n},(_,i)=>all[Math.floor(i*step)]).map(sp=>({...sp,r:sp.r*k,ry:sp.ry*k}))}
}
function scene(t){
  if(!CROWNS_READY)thinCrowns();
  PED_SH='';let out=stamp('ground',cityGround,BASE_CORNERS,-SLAB,1)+waterRipples(t);const parts=[];
  for(const [i,m] of models.entries())if(!offView(m.fp,0,m.h))parts.push({fp:m.fp,z1:m.h,svg:stamp('block'+i,m.draw,m.fp,0,m.h+.3)});
  for(const tr of TREES){const fp=sq(tr.x,tr.y,tr.ext*1.4);if(offView(fp,0,tr.zTop+2))continue;
    parts.push({fp:sq(tr.x,tr.y,.48),z1:tr.zTop,svg:stamp('tree'+tr.i,()=>drawTree(treeLook(tr).keep>=.5?tr.limbs:tr.geo,{ink:PLANT_INK,inkK:INK_K,bark:tr.rule.bark||'#9b795d',keep:0})+'<crown id="'+tr.i+'"/>',fp,0,tr.zTop+2)})}
  for(const [i,item] of streetFurniture.entries())if(!(item.kind==='cafe'&&SEASON.cafes===false)&&!offView(item.fp,0,item.h))parts.push({fp:item.fp,z1:item.h,svg:stamp('street'+i,item.draw,item.fp,0,item.h+.45)});
  for(const [i,item] of BOATS.entries())if(!(SEASON.boats!=null&&rnd(i*5.31+2.7)>=SEASON.boats)&&!offView(item.fp,0,item.h))parts.push({fp:item.fp,z1:item.h,svg:stamp('boat'+i,item.draw,item.fp,0,item.h+.4)});
  for(const [i,item] of decorations().entries())if(!offView(item.fp,0,item.h))parts.push({fp:item.fp,z1:item.h,svg:item.anim?item.draw(t):stamp('decor'+i,item.draw,item.fp,0,item.h+.4)});
  if(EXTRA)for(const p of [].concat(EXTRA(t)||[]))if(p&&!offView(p.fp,0,p.h||p.z1||3))parts.push({fp:p.fp,z1:p.h||p.z1,svg:typeof p.draw==='function'?p.draw(t):p.svg});
  for(const a of TRAFFIC.to(t)){if(offView(sq(...a.p,3),0,3))continue;
    const part=a.kind==='car'?carDraw(a):a.kind==='bike'?bikeDraw(a,t):pedestrian(a,t);
    if(a.alpha<1)part.svg='<g opacity="'+a.alpha.toFixed(2)+'">'+part.svg+'</g>';parts.push(part)}
  if(PED_SH)out+='<path d="'+PED_SH+'" fill="#65576e" opacity=".23"/>';
  const wx=SEASON.wx||(SEASON.wet?'rain':SEASON.snow?'snow':null);
  return out+planSort(parts)+(SEASON.petals?petals(t):'')+(wx?weather(wx,t,HALF+2,groundZ,(x,y)=>inside([x,y],BASE_CORNERS)):'');
}
/* petals: "petals": true on a season or occasion with blossom. Each blossoming tree sheds a few petals that drift down
   from its crown and sideways in the wind, then start again. One path in two pinks (kept bright at night: they are in LIT). */
function petals(t){
  if(SEASON.leaves!=='blossom')return '';
  const h=(i,k)=>{const x=Math.sin(i*127.1+k*311.7)*43758.5453;return x-Math.floor(x)};
  const per=PHONE?14:30;let a='',b='';
  for(const tr of TREES){
    if(!tr.rule.blossom||offView(sq(tr.x,tr.y,tr.ext),0,tr.zTop))continue;
    for(let k=0;k<per;k++){
      const i=tr.i*31+k,top=tr.zTop*.85,fall=top+.3,v=.35+h(i,3)*.25,ph=(t*v/fall+h(i,4))%1;   // ph: 0 at the crown, 1 on the ground
      const r=tr.ext*(.4+h(i,1)*.8),an=h(i,2)*6.283,w=t*.9+h(i,5)*6.3,dr=ph*2.4;
      const x=tr.x+Math.cos(an)*r+Math.sin(w)*.35+dr,y=tr.y+Math.sin(an)*r+Math.cos(w*.8)*.25+dr*.4,z=top*(1-ph);
      if(!inside([x,y],BASE_CORNERS))continue;
      const [X,Y]=P(x,y,z+groundZ(x,y)),seg='M'+f(X)+' '+f(Y)+'h0';
      if(k%3)a+=seg;else b+=seg;
    }
  }
  const [ax,ay]=P(0,0,0),[bx,by]=P(.32,0,0),w=Math.max(4*INK_K,Math.hypot(bx-ax,by-ay)),dot=   // a petal is about 32 cm across on screen, never smaller than 4 ink units
  (d,c,k)=>d?'<path d="'+d+'" fill="none" stroke="#c98a9c" stroke-opacity=".7" style="stroke-width:'+(w*k+Math.max(.5*INK_K,w*.14)).toFixed(2)+'" stroke-linecap="round"/><path d="'+d+'" fill="none" stroke="'+c+'" style="stroke-width:'+(w*k).toFixed(2)+'" stroke-linecap="round"/>':'';
  return dot(a,'#ffe6ec',1)+dot(b,'#fbd3dd',.8);
}
