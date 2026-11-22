/* Pocket City Singapore (North Bridge Road x Coleman Street): the engine code, without its map data.
   A worked example of hand-built landmarks with the same kit. section() here is the ancestor of walls() in city.js.
   Not runnable on its own; read buildFunan() and the cathedral (nave, transept, spire, pinnacles). */

/* Singapore. Metres in a local plane rotated to North Bridge Road.
   The footprint, road and tree extract is embedded for offline rendering. */
const BASE_CORNERS=SCENE.corners, NORTH=[-.5,.8660254,0], SLAB=4;
let FIG_W=540, FIG_H=675, WOBBLE=2, UPX=1, pictureBook=true, washEnabled=true;
const rnd=s=>{const v=Math.sin(s*127.1+311.7)*43758.5453;return v-Math.floor(v)};
const soft=c=>({l:c,m:mix(c,'#887997',.18),d:mix(c,'#705f81',.33)});
const PLANT_INK='#231e17', lineOf=(c,plant)=>mix(c,'#51465a',plant?.38:.53);
const groundZ=()=>0, atZ=(r,z)=>r.map(p=>[p[0],p[1],z]);
// The ink repeat has a physical pitch on each surface. Project the two in-plane
// axes separately so perforations and roof courses turn with the building.
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
      for(let row=0;row<24;row++)for(let col=0;col<24;col++){
        const x=(col+(row%2)*.5)*size/24,y=(row+.5)*size/24;
        ink.fillStyle='rgba(117,63,57,.47)';ink.beginPath();ink.arc(x,y,1.45,0,Math.PI*2);ink.fill();
      }
      for(let i=0;i<4;i++){ink.fillStyle=i%2?'rgba(255,209,172,.10)':'rgba(129,73,71,.08)';ink.fillRect(i*64,0,32,256)}
      ink.fillStyle='rgba(104,64,62,.34)';ink.fillRect(0,0,1.2,256);ink.fillRect(0,0,256,1.1);
    }else{
      for(let row=0;row<12;row++)for(let col=-1;col<8;col++){
        const x=(col+(row%2)*.5)*32,y=row*size/12;
        const r=rnd(row*17+col+103);
        ink.fillStyle=r>.48?'rgba(247,229,204,'+(.04+r*.11)+')':'rgba(68,72,82,'+(.06+r*.15)+')';
        ink.fillRect(x+.75,y+.75,30.8,size/12-1.3);
        ink.fillStyle='rgba(62,68,77,.23)';ink.fillRect(x,y+size/12-1.25,32,1.25);ink.fillRect(x,y,1,size/12);
      }
    }
    tile=c;sheetTiles.set(op.name,tile);
  }
  const [l,t,r,b]=op.bounds,pitch=op.name==='copper'?3.6:4.6;
  g.save();g.clip(op.path);g.transform(...op.matrix);g.scale(pitch/tile.width,pitch/tile.height);
  const scale=tile.width/pitch;
  g.fillStyle=g.createPattern(tile,'repeat');g.fillRect(l*scale,t*scale,(r-l)*scale,(b-t)*scale);g.restore();
}

// Interior garden planting is illustrative. Keep the TreesSG rows and their indices intact.
const gardenPlanting=[[12,69,12],[18,56,8],[30,70,10],[47,21,13],[66,19,10],[92,17,13],[85,39,12],[69,50,9],[92,54,11]];
const TREES=SCENE.trees.concat(gardenPlanting.map(([x,y,h])=>[x,y,-1,String(h)+'-'+h])).map(([x,y,s,band],i)=>{
  const ns=band.match(/\d+/g).map(Number),h=ns.length===2?(ns[0]+ns[1])/2:ns[0]*.72;
  const species=SCENE.species[s]||'Garden tree';
  const style=/Rain Tree|Angsana|Yellow Flame|Garden tree/i.test(species)?6:/Nutmeg|Plumeria|Gardenia|Ardisia/i.test(species)?3:/Derum|Memecylon|Mangosteen/i.test(species)?4:5;
  const m=soft((style===6?['#89ba6a','#adcc6e']:style===4?['#b0cf77','#99bd6f']:style===3?['#83b775','#a4c676']:['#8ab673','#adca7c'])[i%2]);
  const geo=makeTree(style,{x,y,H:h,seed:i+1,m,lod:TREE_LOD});
  return {x,y,i,h,base:0,style,m,geo,ext:geo.ext,zTop:geo.zTop};
});
const treeLook=tr=>({keep:1,m:tr.m});
const clothes=['#d68070','#538e91','#e2ad59','#7994b4','#b991a3','#efe3cd'];
const bikeLook=k=>({k,shirt:clothes[k%6],frame:['#387779','#ba7663','#629684'][k%3]});
const pedDressed=k=>({skin:soft(['#c48d65','#dcaa82','#f0c5a1','#a87154'][k%4]),shirt:clothes[k%6],pants:'#515c70',hair:'#4b3c42',tall:.96+.10*rnd(k+2),umb:SEASON.wet&&rnd(k+14)<.79?soft(clothes[(k+2)%6]):null});
const vehicles=['sedan','suv','hatch','mpv','sedan'].map((kind,i)=>makeCar(kind,{plate:'#f7e1a1',frontPlate:'#f2efe0',sign:i===4?'#fbefd5':null}));
const carModel=k=>vehicles[k%vehicles.length],carProps=k=>({mesh:carModel(k),m:soft(k%5===4?'#4ba1cc':['#d48a79','#eff0da','#90b7ab','#a5afcb'][k%4])});
const phase=(north,t)=>{const s=((t%38)+38)%38;return north?s<20:s>=23&&s<35};
const feeds=SCENE.routes.map(r=>{
  const path=measuredLane({...r,junctions:[r.stop+12]});
  if(r.kind!=='ped'){path.lightAt=r.stop;path.green=t=>phase(r.name==='North Bridge Road',t)}
  return {kind:r.kind,paths:[path],interval:(r.kind==='car'?5.4:r.kind==='bike'?12:8.5)*(PHONE?1.4:1)};
});
let SEASON={},TRAFFIC=null,roadColor,grassColor;
function setGroundColours(){
  roadColor=SEASON.wet?'#8994a0':SEASON.haze?'#b6ab9f':pictureBook?'#b8aeb2':'#aaa6ac';
  grassColor=SEASON.wet?'#98bc87':SEASON.haze?'#bac683':'#b4d784';
}
function setSeason(id){
  SEASON_ID=id;SEASON={wet:id==='wet',race:id==='f1',haze:id==='haze'};
  setGroundColours();
  const flow=feeds.map((f,i)=>({...f,walkSpeed:1.05+.05*(i%3),
    interval:f.interval*(f.kind==='ped'?(SEASON.haze?14:SEASON.race?.36:.62):SEASON.haze&&f.kind==='bike'?5:SEASON.race?1.22:1)}));
  // Start with a populated district. Pedestrians can take seven minutes to
  // cross the square, so the short canal-scene lead-in leaves its centre empty.
  TRAFFIC=streetSimulation(flow,SEASON.race?(PHONE?135:230):(PHONE?98:150),700);
}
setSeason(SEASON_Q||'dry');
const findBuilding=id=>SCENE.buildings.find(b=>b.id===id);
const models=[],facades=[];
// Shop uses are drawn from building directories. Individual displays and bay
// locations are illustrated. Select the street elevations, keeping service walls plain.
function shopStreet(id,n,len){
  if(len<5)return null;
  if(id==='adelphi'&&(n[0]<-.65||n[1]>.70))return 'audio';
  if(id==='46594832'&&(n[0]>.72||n[1]<-.72))return 'plaza';
  if(id==='699183715'&&(n[1]>.72||n[0]<-.76))return 'instruments';
  if((id==='46594830'||id==='46594831')&&n[0]>.72)return 'arcade';
  return null;
}
const shopArt={
  audio:{bands:['#526e75','#9f6554','#50776e'],signs:['HI-FI','LISTENING ROOM','RECORDS'],name:'THE ADELPHI'},
  plaza:{bands:['#a55649','#287b70','#b77c36','#687aa0'],signs:['TEXTILES','PROVISIONS','PHOTO','EXCHANGE'],name:'PENINSULA PLAZA'},
  instruments:{bands:['#59647d','#ab684b','#457b72'],signs:['GUITARS','MUSIC SHOP','STRINGS'],name:'PENINSULA SHOPPING CENTRE'},
  arcade:{bands:['#446967','#82775b','#995f54'],signs:['ATELIER','WATCHES','ARCADE'],name:'CAPITOL'}
};
function drawShopWindows(g,kind,L,H,seed,shade){
  const spec=shopArt[kind],height=Math.min(4.1,H),count=Math.max(1,Math.round(L/(kind==='arcade'?7.1:6.0))),bay=L/count;
  const ink=shade('#526662'),ivory=shade('#f5e8cc'),brass=shade('#c9ac78');
  g.save();g.translate(0,H-height);
  const box=(x,y,w,h,c)=>{g.fillStyle=c;g.fillRect(x,y,w,h)};
  const oval=(x,y,rx,ry,c)=>{g.fillStyle=c;g.beginPath();g.ellipse(x,y,rx,ry,0,0,Math.PI*2);g.fill()};
  const name=(str,x,y,w,h,c,font='Arial')=>{g.fillStyle=c;g.font='bold '+h+'px '+font;g.textAlign='center';g.textBaseline='middle';wallText(g,str,x,y,w)};
  for(let j=0;j<count;j++){
    g.save();g.translate(j*bay,0);
    const v=(j+seed)%spec.bands.length,fascia=shade(spec.bands[v]),entry=count>=3&&j===Math.floor(count*.5);
    box(0,0,bay,height,shade('#a79180'));box(.10,.13,bay-.20,height-.13,ink);
    box(.20,.82,bay-.40,height-1.11,shade(entry?'#647c78':'#eed3a2'));
    box(.24,.86,bay-.48,.22,shade('#9c8f7d'));
    const sx=.36,sw=bay*(entry?.18:.64),doorX=entry?bay*.25:sw+.39;
    if(UPX<.78){
      if(kind==='audio'){
        for(let i=0;i<3;i++){const x=sx+sw*(i+.15)/3,w=Math.min(.66,sw*.24);
          box(x,1.65+i%2*.34,w,1.7-i%2*.34,shade(i%2?'#ad8164':'#655d55'));
          oval(x+w/2,2.2+i%2*.22,w*.23,w*.23,ink);oval(x+w/2,2.96,w*.34,w*.34,shade('#b5aba0'));oval(x+w/2,2.96,w*.14,w*.14,ink);}
      }else if(kind==='instruments'){
        for(let i=0;i<3;i++){let x=sx+sw*(i+.5)/3,y=2.72+(i%2)*.22;
          box(x-.045,y-1.28,.09,1.35,ink);box(x-.09,y-1.35,.18,.22,ink);
          const c=shade(['#cb8a4c','#ae5f4b','#d4b479'][i]);oval(x,y,.19,.25,c);oval(x,y+.26,.29,.34,c);oval(x,y+.08,.083,.083,ink);}
      }else if(kind==='plaza'&&v===2){
        box(sx,1.12,sw,1.02,shade('#b1c7c1'));
        for(let k=0;k<3;k++){const x=sx+(k+.13)*sw/3;
          box(x,1.21,sw*.25,.72,ivory);box(x+.055,1.27,sw*.25-.11,.47,shade(['#809d91','#c99978','#839da8'][k]));}
        for(let k=0;k<4;k++){const x=sx+(k+.16)*sw/4,y=2.42+k%2*.27;
          box(x,y,sw*.19,.34,ink);box(x+.07,y-.07,.16,.09,ink);
          oval(x+sw*.095,y+.17,.12,.12,brass);oval(x+sw*.095,y+.17,.076,.076,ink);}
        box(sx,3.11,sw,.14,brass);
      }else if(kind==='plaza'&&v===3){
        box(sx+.10,1.36,sw-.20,1.21,shade('#446762'));
        for(let k=0;k<4;k++){const y=1.47+k*.25;box(sx+.24,y,sw*.23,.07,ivory);
          box(sx+sw*.53,y,sw*.13,.07,brass);box(sx+sw*.76,y,sw*.11,.07,brass);}
        box(sx,2.84,sw,.34,shade('#b79d7b'));box(sx,2.82,sw,.10,ivory);
      }else if(kind==='plaza'&&v===1){
        const jars=['#be8558','#8eac8f','#c17b6c','#d9bd78'];
        for(let k=0;k<3;k++){const y=1.43+k*.71;
          for(let i=0;i<7;i++){const x=sx+(i+.1)*sw/7,w=sw*.095;
            box(x+w*.19,y,w*.62,.10,ivory);box(x,y+.10,w,.36,shade(jars[(i+k)%4]));
            box(x+.02,y+.23,w-.04,.09,ivory);}
          box(sx,y+.49,sw,.10,brass);}
      }else if(kind==='plaza'){
        const cloth=['#bc6756','#cfad65','#708c8e','#7e8d69','#b4828b'];
        for(let k=0;k<3;k++){const y=1.46+k*.69;
          for(let i=0;i<5;i++){const x=sx+i*sw/5,w=sw/5-.06,c=shade(cloth[(i+k+v)%5]);
            box(x,y,w,.42,c);box(x+.02,y+.24,w-.04,.05,ivory);}
          box(sx,y+.45,sw,.095,brass);}
      }else{
        for(let i=0;i<3;i++){const x=sx+sw*(i+.5)/3;
          box(x-.28,2.74,.56,.39,ivory);box(x-.21,2.60,.42,.17,brass);oval(x,2.46,.13,.18,ink);oval(x,2.46,.085,.11,ivory);}
      }
    }
    const dw=(entry?bay*.5:bay-doorX-.23);
    box(doorX,.95,dw,height-1.04,shade('#729995'));box(doorX+.1,1.08,dw-.20,.40,shade('#adc9bd'));
    box(doorX+dw*.5,1.44,.09,height-1.53,ivory);box(doorX+.06,1.49,dw-.12,.075,ivory);
    box(doorX+dw*.5-.12,2.45,.055,.40,brass);box(doorX+dw*.5+.15,2.45,.055,.40,brass);
    box(.15,height-.37,sw+.14,.28,fascia);box(.14,.18,bay-.28,.62,fascia);
    if(UPX<.37)name(entry?spec.name:spec.signs[v],bay*.5,.49,bay-.6,entry?.37:.30,ivory,kind==='arcade'?'Georgia':'Arial');
    box(.11,.77,bay-.22,.07,brass);box(0,.03,.15,height-.03,ivory);
    if(!entry){box(sx+sw*.51,.85,.08,height-1.2,ink);box(sx,1.29,sw,.065,ivory)}
    g.restore();
  }
  g.restore();
}

function retailCanopies(face){
  const {shop:kind,len,start,along,n}=face;
  const bays=Math.max(1,Math.round(len/(kind==='arcade'?7.1:6.0))),bay=len/bays;
  const at=(s,depth,z)=>[start[0]+along[0]*s+n[0]*depth,start[1]+along[1]*s+n[1]*depth,z];
  let svg='';
  for(let i=0;i<bays;i++){
    const entry=i===Math.floor(bays*.5);
    if(!entry && (kind==='arcade'?i%2===0:kind==='audio'||i%3!==1))continue;
    const a=bay*i+.2,b=bay*(i+1)-.2;
    const projection=entry?1.06:.72,height=entry?3.62:3.18,front=height-(kind==='plaza'?.27:.12);
    const colour=kind==='plaza'?['#af7762','#688d86','#b59972'][i%3]:kind==='instruments'?'#72878c':kind==='audio'?'#9caeaa':'#ad9878';
    svg+=shape([at(a,0,height),at(b,0,height),at(b,projection,front),at(a,projection,front)],colour,.36);
    if(kind==='plaza'&&!entry&&UPX<.55){
      for(let t=a+.13;t<b-.25;t+=.72){
        const u=Math.min(b,t+.26);
        svg+=shape([at(t,0,height+.012),at(u,0,height+.012),at(u,projection,front+.012),at(t,projection,front+.012)],'#eddec0',0);
      }
    }
    svg+=shape([at(a,projection,front),at(b,projection,front),at(b,projection,front-.16),at(a,projection,front-.16)],mix(colour,'#726d78',.3),.3);
    if(UPX<.33)for(const u of [a+.3,b-.3])svg+=edge(at(u,0,height-.67),at(u,projection-.10,front-.1),'#838b84',.06);
  }
  return svg;
}
function section(r,z,h,style,body,roof,seam=null,retailId=null,skip=null){
  const area=r.reduce((s,p,i)=>{const q=r[(i+1)%r.length];return s+p[0]*q[1]-q[0]*p[1]},0);
  const faces=r.map((a,i)=>{
    const b=r[(i+1)%r.length],len=Math.hypot(b[0]-a[0],b[1]-a[1]);
    const u=[(b[0]-a[0])/len,(b[1]-a[1])/len],n=[u[1]*Math.sign(area),-u[0]*Math.sign(area),0];
    // Orient the elevation left-to-right as seen from outside. Its lettering stays legible in every visible view.
    const flip=area>0,start=flip?b:a,along=flip?u.map(v=>-v):u;
    const cut=BASE_CORNERS.some((v,j)=>{const w=BASE_CORNERS[(j+1)%4];return v[0]===w[0]?a[0]===v[0]&&b[0]===v[0]:a[1]===v[1]&&b[1]===v[1]});
    const id=facades.push({start,along,n,len,z,h,style:cut?'cut':style,shop:cut?null:shopStreet(retailId,n,len),body})-1;
    return {a,b,n,id};
  });
  return ()=>faces.filter(q=>vis(q.n)&&!(seam!==null&&q.a[0]===seam&&q.b[0]===seam)&&!(skip&&skip(q.a,q.b))).sort((a,b)=>depthOf([...a.a,0])-depthOf([...b.a,0])).map(q=>{
    const wall=[...atZ([q.a,q.b],z),...atZ([q.b,q.a],h)];
    const fac=facades[q.id];
    return shape(wall,tone(q.n,soft(body)),.7)+'<elevation id="'+q.id+'"/>'+(fac.shop?retailCanopies(fac):'');
  }).join('')+shape(atZ(r,h),roof,.8);
}
const obj=(fp,h,draw)=>({fp,h,draw});
function rect(x,y,w,d){return [[x-w/2,y-d/2],[x+w/2,y-d/2],[x+w/2,y+d/2],[x-w/2,y+d/2]]}
const polygon=(x,y,r,n,angle=0)=>Array.from({length:n},(_,i)=>[x+r*Math.cos(i*2*Math.PI/n+angle),y+r*Math.sin(i*2*Math.PI/n+angle)]);
function peak(r,base,tip,col){
  return r.map((a,i)=>{const b=r[(i+1)%r.length],p=[[...a,base],[...b,base],tip];const n=vNewell(p);return {p,n,at:avg(p)}}).filter(p=>vis(p.n)).sort((a,b)=>depthOf(a.at)-depthOf(b.at)).map(p=>shape(p.p,tone(p.n,soft(col)),.65)).join('');
}
const baseStyles=[
  ['46594832',18,'plaza','#e0cba7','#c8c4b8'],
  ['257192963',4,'low','#eee2ca','#b8b9a7'],['173132990',4,'low','#ddddcb','#bfc3ba'],
  ['adelphi',25,'adelphi','#e7c7b3','#d8c7b6'],['699183715',23,'plaza','#d6c4ab','#c3babe'],
  ['257192962',4,'low','#ece3ce','#b8bdb9']
];
function inside(p,r){let c=false;for(let i=0,j=r.length-1;i<r.length;j=i++){const a=r[i],b=r[j];if((a[1]>p[1])!==(b[1]>p[1])&&p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0])c=!c}return c}
function roofFixtures(r,h,style){
  const parts=[];const pts=r.map(p=>p[0]),ys=r.map(p=>p[1]);
  for(let x=Math.ceil(Math.min(...pts)/7)*7;x<Math.max(...pts);x+=7)for(let y=Math.ceil(Math.min(...ys)/10)*10;y<Math.max(...ys);y+=10){
    if(rnd(x+y*9)>.18)continue;
    const fp=rect(x,y,3,2.3);if(!fp.every(p=>inside(p,r)))continue;
    const cap=section(fp,h,h+.82,'metal','#bbc1bd','#dce0cf');
    parts.push({fp,z1:h+1,svg:()=>cap()+shape(atZ(rect(x,y,2,.95),h+.93),'#929fa0',.35)});
  }
  return ()=>planSort(parts.map(p=>({...p,svg:p.svg()})));
}
for(const [id,h,style,body,roof] of baseStyles){
  const r=findBuilding(id).ring,shell=section(r,0,h,style,body,roof,null,id),fixtures=roofFixtures(r,h,style);
  const parts=[];
  // Folded parapets give the roof a silhouette; the edge of the cut remains open.
  for(let j=0;j<r.length;j++){
    const a=r[j],b=r[(j+1)%r.length],l=Math.hypot(b[0]-a[0],b[1]-a[1]);if(l<2)continue;
    const rim=.54;
    parts.push({fp:[a,b],z1:h+rim,draw:()=>shape([...atZ([a,b],h),...atZ([b,a],h+rim)],'#cbbfb0',.5)+edge([...a,h+rim],[...b,h+rim],'#eee5cf',.17)});
  }
  if(id==='699183715')for(const hotelId of ['44414530','334127049']){
    const hotel=findBuilding(hotelId),top=hotel.h||hotel.lv*3.5;
    parts.push({fp:hotel.ring,z1:top,draw:section(hotel.ring,h,top,'residence','#b7c4ba','#dbd5c4')});
  }
  if(id==='46594832')for(const [key,z,hh] of [['257193900',18,21],['257193902',18,111]]){
    const part=findBuilding(key).ring;
    parts.push({fp:part,z1:hh,draw:section(part,z,hh,'tower','#e3d4b5','#cbc6b8')});
  }
  models.push(obj(r,Math.max(h+1,...parts.map(p=>p.z1)),()=>shell()+fixtures()+planSort(parts.map(p=>({...p,svg:p.draw()})))));
}
// Buildings on the additional blocks retain their clipped map footprints.
// Overlapping podiums and their mapped upper volumes draw together.
const surroundings=[
  ['46594825',18,'civic','#d7dfd9','#b9c8c4'],['46595597',25,'hall','#f0e4cd','#d3c6b1'],
  ['170960936',25,'hall','#e3dac3','#bfbab1'],['46594826',10,'civic','#ccc7bb','#c5c7ba'],
  ['46594830',34,'hall','#ebd8be','#b9a89a'],['46594831',55,'civic','#d0ced3','#cec7bf'],
  ['95762799',42,'civic','#e4cfb6','#c4b8a9'],['103110145',34,'hall','#e1d0b5','#baad9f'],
  ['103110146',72,'residence','#9fb8b7','#b1bfb6'],['103110147',34,'hall','#e8ceb4','#bbaa9d'],
  ['612174812',13,'civic','#e5d4c0','#c1b9ab'],['172368086',20,'civic','#c99b88','#b78e7c'],
  ['172368091',20,'civic','#e0d2bc','#bcb19e'],['243430556',43,'civic','#c8c1b7','#bbb4a8'],
  ['723676572',13,'civic','#e5d9b9','#c5bfaa'],['878100291',12,'low','#e4d9c5','#bfbbab'],
  ['484664357',13,'low','#e5d9cb','#b8b1a8'],['466885625',10,'low','#e1d8bf','#bdbbab'],
  ['1149827304',12,'low','#dbceb8','#bcae98']
];
for(const [id,height,style,wall,roof] of surroundings){
  const b=findBuilding(id);if(!b)continue;
  const shells=section(b.ring,0,height,style,wall,roof,null,id),parts=[];
  const add=(key,z,top,style,wall,roof)=>{
    const part=findBuilding(key);if(!part)return;
    parts.push({fp:part.ring,z1:top,draw:section(part.ring,z,top,style,wall,roof)});
  };
  if(id==='46594825'){
    add('334127043',height,26,'office','#a7bec0','#c6ccc7');add('334127050',26,28,'metal','#a3aba6','#bdc7bf');
    add('172368145',28,30,'metal','#a0aeac','#d0d9cf');
  }
  if(id==='46594826')add('699168479',height,43,'office','#a5b6be','#c8cdca');
  if(id==='612174812')for(const key of ['699183708','699183709','699183710','699183711','699183712','699183713','699183714']){
    const part=findBuilding(key);if(part && (part.h||part.lv*3.6)>height)add(key,height,part.h||part.lv*3.6,'civic',wall,roof);
  }
  if(id==='170960936'){
    const cx=140,cy=-185,r=9.5;
    const drum=section(polygon(cx,cy,r,20),height,28,'hall','#e6d7bf','#c2c3ae');
    parts.push({fp:rect(cx,cy,20,20),z1:42,draw:()=>{
      let svg=drum(),last=atZ(polygon(cx,cy,r,20),28);
      for(let j=1;j<=6;j++){const t=j*Math.PI/13,next=atZ(polygon(cx,cy,r*Math.cos(t),20),28+9*Math.sin(t));svg+=loft(last,next,n=>tone(n,soft('#97b8a8')));last=next}
      return svg+stick([cx,cy,36.8],[cx,cy,41.9],.44,'#96a59b');
    }});
  }
  models.push(obj(b.ring,Math.max(height,...parts.map(p=>p.z1)),()=>shells()+planSort(parts.map(p=>({...p,svg:p.draw()})))));
}
const capitolRoof=findBuilding('475416264').ring;
models.push(obj(capitolRoof,8,section(capitolRoof,7.5,8,'metal','#ded7c8','#c7c7bc')));

// Map the different storeys independently. The east end of the three-storey
// retail footprint steps back underneath the larger six-storey volume.
// The entrance banks rise away from the exposed corner under the copper soffit.
// Both flights share a landing. Distances are interpreted from the exterior photograph.
const escalatorRun=14.4,escalatorRise=5.45;
function stairPoint(s,w,z){
  return [-38.2-.115*s+.993*w,-31.8-.993*s-.115*w,z];
}
function treadHeight(s){return .12+escalatorRise*Math.max(0,Math.min(1,s/escalatorRun))}
function escalatorBank(){
  const run=escalatorRun;
  const at=(s,w,h=0)=>stairPoint(s,w,treadHeight(s)+h);
  const profile=[-1.65,-.45,0,run,run+.55,run+1.8];
  const lining=(w,offset,colour)=>shape([...profile.map(s=>at(s,w,offset)),...profile.slice().reverse().map(s=>at(s,w,-.04))],colour,.45);
  const balustrade=w=>{
    let out=lining(w,-.53,'#869793');
    const rim=[[-1.59,.18],[-1.55,.53],[-1.36,.82],[-1.02,.96],[0,.96],[run,.96],[run+1.16,.96],[run+1.50,.87],[run+1.65,.62],[run+1.70,.20]];
    const points=rim.map(([s,z])=>at(s,w,z));
    out+='<g opacity=".46">'+shape([...points,...profile.slice().reverse().map(s=>at(s,w,.03))],'#a8ccc9',.24)+'</g>';
    for(let s=1.9;s<run;s+=2.1)out+=edge(at(s,w,.10),at(s,w,.87),'#7c9b99',.045);
    for(let i=1;i<points.length;i++)out+=edge(points[i-1],points[i],'#405453',.125);
    return out+edge(at(0,w,.17),at(run,w,.17),'#d6ddd3',.11);
  };
  const lanes=[-.85,.85].sort((a,b)=>depthOf(at(4,a))-depthOf(at(4,b)));
  let svg='';
  for(const [i,w] of lanes.entries()){
    const far=w+Math.sign(lanes[0]-lanes[1])*.74,near=2*w-far;
    svg+=balustrade(far);
    svg+=shape([at(-1.65,w-.72),at(run+1.8,w-.72),at(run+1.8,w+.72),at(-1.65,w+.72)],'#647678',.34);
    if(UPX<.45)svg+='<treads lane="'+w+'"/>';
    else svg+=edge(at(0,w),at(run,w),'#b6c2bb',.35);
    for(const s of [-1.64,run+.04]){
      svg+=shape([at(s,w-.72,.02),at(s+1.58,w-.72,.02),at(s+1.58,w+.72,.02),at(s,w+.72,.02)],'#b1bcb6',.35);
      const comb=s<0?s+1.5:s+.08;
      svg+=edge(at(comb,w-.69,.03),at(comb,w+.69,.03),'#ebc568',.10);
    }
    svg+=balustrade(near);
  }
  return svg;
}
function paintEscalatorTreads(g,lane){
  const step=escalatorRun/32,phase=((paintTime*.43/step)%1)*step*(lane<0?1:-1);
  const face=(points,colour)=>{g.fillStyle=colour;g.beginPath();points.forEach((v,i)=>{const q=P(...v);i?g.lineTo(...q):g.moveTo(...q)});g.closePath();g.fill()};
  const steps=[];
  for(let j=-1;j<=32;j++){
    const a=Math.max(0,j*step+phase),b=Math.min(escalatorRun,(j+1)*step+phase);
    if(b<=a)continue;
    const z=treadHeight(b);
    steps.push({depth:depthOf(stairPoint(a,lane,z)),a,b,z});
  }
  for(const {a,b,z} of steps.sort((u,v)=>u.depth-v.depth)){
    const point=(s,w,h)=>stairPoint(s,lane+w,h);
    face([point(a,-.69,z),point(b,-.69,z),point(b,.69,z),point(a,.69,z)],'#a5b5b0');
    face([point(a,-.69,treadHeight(a)),point(a,-.69,z),point(a,.69,z),point(a,.69,treadHeight(a))],'#5e7071');
    face([point(a,-.69,z+.004),point(a+.042,-.69,z+.004),point(a+.042,.69,z+.004),point(a,.69,z+.004)],'#d6c89a');
  }
}

function buildFunan(){
  const ring=id=>findBuilding(id).ring,fp=ring('432515092');
  const low=ring('699175605'),upper=ring('699175602');
  // The L-shaped mall wraps around another parcel. Its frontage and rear
  // need separate depth ordering as the camera moves past the adjoining hotel.
  const seam=-54;
  const half=(ring,east)=>{
    const result=[];
    for(let i=0;i<ring.length;i++){
      const a=ring[i],b=ring[(i+1)%ring.length],side=v=>east?v[0]>=seam:v[0]<=seam;
      if(side(a))result.push(a);
      if(side(a)!==side(b))result.push([seam,a[1]+(b[1]-a[1])*(seam-a[0])/(b[0]-a[0])]);
    }return result;
  };
  const glass=ring=>section(ring,13.2,25.8,'curtain','#83a9af','#d5d4bd',seam);
  const retail=ring=>section(ring,0,13.2,'copper','#cb8971','#c0ab97',seam);
  const upperEast=half(upper,true),eastGlass=glass(upperEast),westGlass=glass(half(upper,false));
  const lowEast=half(low,true),eastRetail=retail(lowEast),westRetail=retail(half(low,false));
  const sideWing=section(ring('699175606'),13.2,findBuilding('980460879').h,'residence','#a1b4b9','#dadacb');
  const upperParts=['699175599','699175600','699175601','699175603'].map(id=>{
    const b=findBuilding(id),h=25.8+(b.lv-b.min)*3.75;
    return {fp:b.ring,z1:h,draw:section(b.ring,25.8,h,'office','#93b4be','#ccd5ce')};
  });
  const garden=[];
  for(const [x,y,w,d] of [[-42,-42,9,22],[-43,-67,10,17],[-45,-89,8,14],[-84,-104,20,6],[-108,-104,18,5]]){
    const bed=rect(x,y,w,d);if(!bed.every(p=>inside(p,upper)))continue;
    const rim=section(bed,25.8,26.12,'metal','#baae95','#99ad7a');
    garden.push({fp:bed,z1:29,draw:()=>{
      let svg=rim();
      for(let row=-1;row<=1;row++)svg+=shape(atZ(rect(x+row*w*.28,y,w*.23,d-1),26.14),row?'#8ba581':'#adbc81',.22);
      for(let j=0;j<18;j++){
        const px=x+(rnd(j*11+y)-.5)*(w-2),py=y+(rnd(j*13+x)-.5)*(d-2);
        if(j%5===0){svg+=stick([px,py,26.1],[px,py,27.9],.12,'#a28d73');
          svg+=ball([px,py,28.45],1.18,soft('#94b17d'),.40)+ball([px+.45,py+.25,28.7],.85,soft('#a9bf83'),.25);
        }else svg+=ball([px,py,26.42],.44+rnd(j+y)*.52,soft(['#a9bd79','#91ae7b','#c4c984'][j%3]),.30);
      }return svg;
    }});
  }
  // A separate glazing line, supports and translucent canopy leave a readable
  // open space below the overhang. Their depths are interpreted from exterior photos.
  const portal=rect(-44.6,-41.4,4.1,15.4),doors=section(portal,0,6.8,'doors','#7e9da1','#a8babb');
  const rail=([x,y,z],[u,v,w])=>edge([x,y,z],[u,v,w],'#819b97',.12);
  const canopy=[[-35.8,-32.9],[-30,-29.3],[-28.8,-34.2],[-31.3,-68.4],[-33.9,-73.0],[-39.8,-66.8],[-39,-49.9],[-36,-48.9]];
  const canopySvg=()=>{
    const landing=[stairPoint(escalatorRun+1.5,-1.62,5.56),stairPoint(escalatorRun+1.5,1.62,5.56),[-38.5,-51.9,5.56],[-42,-51.1,5.56]];
    const mouth=(w,z)=>stairPoint(escalatorRun+2.48,w,z);
    let svg=doors()+shape([mouth(-1.97,5.4),mouth(1.97,5.4),mouth(1.97,8.6),mouth(-1.97,8.6)],'#53696d',.48)
      +edge(mouth(-1.97,8.59),mouth(1.97,8.59),'#c5b7a2',.14)
      +shape(landing,'#a1afac',.45)+escalatorBank();
    for(const [x,y] of [[-41,-34],[-41,-48],[-33,-51],[-33.4,-66]])svg+=stick([x,y,0],[x,y,4.45],.16,'#8b9692');
    svg+='<g opacity=".68">'+shape(atZ(canopy,4.5),'#a3c6bc',.7)+'</g>';
    svg+=clipTo(atZ(canopy,4.5),Array.from({length:14},(_,j)=>{
      const y=-29-j*3.3,x=-29-Math.abs(y+35)*.04;
      return rail([-43,y,4.54],[x,y-1.2,4.54])+rail([-43,y-3.3,4.54],[x,y-1.2,4.54]);
    }).join(''));
    for(let j=0;j<canopy.length;j++)svg+=rail([...canopy[j],4.53],[...canopy[(j+1)%canopy.length],4.53]);
    return svg;
  };
  // Follow the change in direction at the street corner with continuous folded
  // panels. The underside and returns belong to the model, so the arcade has depth.
  const streetRun=[[-50.33,-23.06],[-41,-26.14],[-33.48,-28.62],[-33.64,-38],[-33.84,-50],[-34.01,-60],[-34.30,-77],[-34.54,-91],[-34.71,-100.89]];
  const ribbonLevel=[10.2,10.2,10.5,10.4,7.4,7.4,9.5,9.5,8.0];
  const ribbonDepth=[.5,1.2,1.7,1.8,1.4,.8,1.25,1.45,1.1];
  const ribbons=()=>{
    const panels=[];
    for(let i=1;i<streetRun.length;i++){
      const a=streetRun[i-1],b=streetRun[i],delta=[b[0]-a[0],b[1]-a[1]],length=Math.hypot(...delta),n=[-delta[1]/length,delta[0]/length,0];
      if(!vis(n))continue;
      const at=(k,z,depth)=>{const p=streetRun[k];return [p[0]+n[0]*depth,p[1]+n[1]*depth,z]};
      const drawBand=(h1,h2,depth,colour)=>{
        const left=ribbonLevel[i-1],right=ribbonLevel[i],d1=ribbonDepth[i-1]*depth,d2=ribbonDepth[i]*depth;
        const q=[at(i-1,left+h1,d1),at(i,right+h1,d2),at(i,right+h2,d2),at(i-1,left+h2,d1)];
        const tangent=[delta[0]/length,delta[1]/length,0];
        let detail=shape([q[0],q[1],at(i,right+h1-.35,0),at(i-1,left+h1-.35,0)],'#977264',.40)+shape(q,colour,.56)+sheetInk(q,'copper',tangent,[0,0,-1]);
        const count=UPX<.52?Math.round(length/1.45):0;
        for(let j=1;j<count;j++){
          const k=j/count,low=q[0].map((v,c)=>v+(q[1][c]-v)*k),high=q[3].map((v,c)=>v+(q[2][c]-v)*k);
          detail+=edge(low,high,'#c88770',.045);
        }
        return detail;
      };
      const svg=drawBand(-2.45,-.70,.90,'#cd8264')+drawBand(.10,1.92,1.25,'#c47b5f')+
        shape([at(i-1,ribbonLevel[i-1]+2.45,.8),at(i,ribbonLevel[i]+2.45,.8),at(i,13.4,.7),at(i-1,13.4,.7)],'#d89a7d',.55);
      panels.push({at:[(a[0]+b[0])/2,(a[1]+b[1])/2,9],svg});
    }
    return byDepth(panels);
  };
  // CapitaLand specifies a 9 m wide, 13 m tall kinetic wall. Its inset on
  // this elevation is estimated from the exterior reference.
  const frontNormal=[.314,.949],across=[.949,-.314],kineticBase=[-49.1,-28.6];
  const kineticAt=(u,v)=>[kineticBase[0]+across[0]*u,kineticBase[1]+across[1]*u,v+.35];
  const kinetic=()=>{
    if(!vis([...frontNormal,0]))return '';
    let svg=shape([kineticAt(0,0),kineticAt(9,0),kineticAt(9,13),kineticAt(0,13)],'#67767a',.58);
    const rows=UPX<.18?47:22,cols=UPX<.18?27:13;
    for(let j=0;j<rows;j++)svg+=edge(kineticAt(0,(j+.4)*13/rows),kineticAt(9,(j+.4)*13/rows),j%5?'#84928e':'#aab5a4',.09);
    for(let i=1;i<cols;i++)svg+=edge(kineticAt(i*9/cols,0),kineticAt(i*9/cols,13),'#697c7a',.06);
    return svg;
  };
  // Thin perimeter rails and yellow-green planting distinguish the roof terrace
  // from the glass offices in all camera positions.
  const terraceRails=()=>{
    let svg='';for(const [a,b] of [[[-34.25,-29.2],[-35.45,-100.5]],[[-34.25,-29.2],[-49.7,-24.2]]]){
      const len=Math.hypot(a[0]-b[0],a[1]-b[1]),count=Math.ceil(len/2.35);
      svg+=edge([...a,26.9],[...b,26.9],'#758e86',.10);
      for(let i=0;i<=count;i++){const x=a[0]+(b[0]-a[0])*i/count,y=a[1]+(b[1]-a[1])*i/count;svg+=stick([x,y,25.8],[x,y,26.9],.045,'#809087')}
    }return svg;
  };
  const front=half(fp,true).map(([x,y])=>[x> -35?Math.max(x,-28.5):x,y]);
  const gardenSvg=pieces=>planSort(pieces.map(p=>({...p,svg:p.draw()})));
  return [obj(front,29.8,()=>{
    const lower=planSort([{fp:lowEast,z1:13.2,svg:eastRetail()},{fp:rect(-45,-29.7,9,2),z1:13.35,svg:kinetic()},{fp:canopy,z1:6.8,svg:canopySvg()}]);
    return lower+shape(atZ(upperEast,13.15),'#74888a',.6)+ribbons()+eastGlass()+terraceRails()+gardenSvg(garden.filter(p=>p.fp[0][0]>seam));
  }),obj(half(fp,false),Math.max(findBuilding('980460879').h,...upperParts.map(p=>p.z1)),()=>{
    return westRetail()+westGlass()+gardenSvg([...upperParts,...garden.filter(p=>p.fp[0][0]<=seam),{fp:ring('699175606'),z1:findBuilding('980460879').h,draw:sideWing}]);
  })];
}
models.push(...buildFunan());

const cathedral=findBuilding('155980025').ring;
const churchBase=section(cathedral,0,9,'gothic','#faf2dc','#d6d4c6');
const nave=findBuilding('699194167').ring, transeptRing=findBuilding('699194166').ring;
// Insert a corner wherever ring r crosses the outline of 'other', so each wall stops at the crossing.
function splitAt(r,other){
  const out=[];
  for(let i=0;i<r.length;i++){
    const a=r[i],b=r[(i+1)%r.length],cuts=[];out.push(a);
    for(let j=0;j<other.length;j++){
      const c=other[j],d=other[(j+1)%other.length],e=[b[0]-a[0],b[1]-a[1]],f=[d[0]-c[0],d[1]-c[1]],den=e[0]*f[1]-e[1]*f[0];
      if(Math.abs(den)<1e-9)continue;
      const t=((c[0]-a[0])*f[1]-(c[1]-a[1])*f[0])/den,u=((c[0]-a[0])*e[1]-(c[1]-a[1])*e[0])/den;
      if(t>1e-6&&t<1-1e-6&&u>=-1e-6&&u<=1+1e-6)cuts.push(t);
    }
    for(const t of cuts.sort((x,y)=>x-y))out.push([a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]);
  }
  return out;
}
const hiddenIn=other=>(a,b)=>inside([(a[0]+b[0])/2,(a[1]+b[1])/2],other);
const naveWalls=section(splitAt(nave,transeptRing),9,15,'clerestory','#f7efdb','#a6a6a0',null,null,hiddenIn(transeptRing));
function slateFace(q,color,ridgeDirection){
  const u=norm(ridgeDirection),normal=vNewell(q);
  const v=norm(cross(normal,u));
  return shape(q,color,.67)+sheetInk(q,'slate',u,v);
}
const naveRoof=()=>{
  // Split the complete nave at its ridge to get the two roof slopes.
  const ridge=(y)=>77.45-.023*(y-89.4);
  let out='';
  const pieces=[-1,1].map(sign=>{
    const ring=[];for(let i=0;i<nave.length;i++){
      const a=nave[i],b=nave[(i+1)%nave.length],da=sign*(a[0]-ridge(a[1])),db=sign*(b[0]-ridge(b[1]));
      if(da>=0)ring.push(a);if((da>=0)!==(db>=0)){const t=da/(da-db);ring.push([a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t])}
    }
    return {p:ring.map(([x,y])=>[x,y,20.9-Math.abs(x-ridge(y))*1.12]),sign};
  });for(const p of pieces.sort((a,b)=>(a.sign-b.sign)*CAM_V[0]))out+=slateFace(p.p,p.sign>0?'#97989a':'#84868d',[-.023,1,0]);return out;
};
// Both transept ends have a tall gable between slender octagonal pinnacles.
// The mapped end walls and corner-turret positions set the spacing.
const transept=findBuilding('699194166').ring;
const crossWalls=section(splitAt(transept,nave),9,13,'clerestory','#f7f2e3','#c7c7ba',null,null,hiddenIn(nave));
const crossEnds=[-1,1].map(sign=>{
  const end=transept.slice().sort((a,b)=>sign*(b[0]-a[0])).slice(0,2).sort((a,b)=>a[1]-b[1]);
  const mid=end[0].map((v,i)=>(v+end[1][i])*.5),halfWidth=Math.hypot(end[1][0]-end[0][0],end[1][1]-end[0][1])*.5;
  const facade=rect(mid[0]+sign*.24,mid[1],.48,halfWidth*2);
  const window=section(facade,1.8,14.5,'transeptWindow','#f8f3e5','#dfdbce');
  const towers=end.map(([x,y])=>{
    const R=1.27,base=polygon(x,y,R,8,Math.PI/8),lip=polygon(x,y,R+.12,8,Math.PI/8);
    const shaft=section(base,0,15.8,'pinnacle','#f2ebdb','#dedacc');
    const collar=section(lip,11.75,12.15,'metal','#dfd7c4','#faf2dd');
    const lantern=section(base,15.8,18.6,'belfry','#f9f2df','#e1d9c8');
    return {fp:base,z1:25.3,draw:()=>shaft()+collar()+lantern()+peak(base,18.6,[x,y,24.8],'#dcd5c2')+stick([x,y,24.6],[x,y,25.25],.053,'#897e73')};
  });
  return {fp:facade,z1:25.3,draw:()=>{
    const tip=[mid[0],mid[1],18.65],points=[...atZ(end,13),tip];
    let gable='';
    if(vis([sign,0,0])){
      const center=[mid[0]+sign*.30,mid[1],15.85];
      gable=shape(points,'#f2eddf',.65)+edge(points[0],tip,'#c7bfab',.18)+edge(points[1],tip,'#faf1db',.19);
      gable+=shape(Array.from({length:16},(_,i)=>[center[0],center[1]+Math.cos(i*Math.PI/8)*.50,center[2]+Math.sin(i*Math.PI/8)*.50]),'#b7aea0',.40);
      gable+=edge([center[0],center[1]-.33,center[2]],[center[0],center[1]+.33,center[2]],'#fbf0da',.12)+edge([center[0],center[1],center[2]-.33],[center[0],center[1],center[2]+.33],'#fbf0da',.12);
    }
    return window()+gable+planSort(towers.map(o=>({...o,svg:o.draw()})));
  }};
});
const crossRoof=()=>{
  const r=transept.slice().sort((p,q)=>p[0]-q[0]),ends=[r.slice(0,2),r.slice(2)].map(pair=>pair.sort((a,b)=>a[1]-b[1]));
  const [west,east]=ends,ridge=ends.map(([a,b])=>[(a[0]+b[0])/2,(a[1]+b[1])/2,18.65]);
  const faces=[0,1].sort((a,b)=>(a-b)*CAM_V[1]).map(i=>{
    const q=[[...west[i],13],[...east[i],13],ridge[1],ridge[0]];
    return slateFace(q,i?'#96979a':'#a5a29b',sub(q[1],q[0]))+edge(q[0],q[1],'#dcd8c8',.18);
  });
  return crossWalls()+faces.join('')+edge(...ridge,'#777c80',.15);
};
const towerX=78.37,towerY=83.68,towerBase=findBuilding('699194163').ring,towerOct=polygon(towerX,towerY,4.75,8,Math.PI/8);
const porch=section(towerBase,0,22,'porch','#f6f0df','#e5dfd1');
const belfry=section(towerBase,22,30.7,'squareBelfry','#fbf5e6','#ece6d5');
const towerLip=section(rect(towerX,towerY,12.15,11.9),29.8,30.35,'metal','#d5cdbb','#fcf3e1');
const spireBase=section(towerOct,30.7,34,'pinnacle','#e8e3d4','#e9e1d1');
const pinnacles=towerBase.map(([x,y])=>{
  const foot=polygon(x,y,.79,8),shaft=section(foot,19,31.7,'pinnacle','#efe9da','#ded6c6');
  return {fp:foot,z1:35.7,draw:()=>shaft()+peak(foot,31.7,[x,y,35.7],'#ddd7c9')};
});
function spire(){
  const roof=peak(towerOct,34,[towerX,towerY,62.1],'#e5ddcc');
  let metal='';
  for(const z of [40.5,51.15]){
    const R=4.75*(62.1-z)/28.1+.06,lower=atZ(polygon(towerX,towerY,R,8,Math.PI/8),z);
    metal+=loft(lower,lower.map(([x,y])=>[x,y,z+.20]),n=>tone(n,soft('#aa9e87')));
  }
  return roof+metal+stick([towerX,towerY,61.9],[towerX,towerY,63.1],.065,'#7a786e');
}
models.push(obj(cathedral,63.1,()=>{
  // corner pinnacles by how far they stand from the reader compared with the tower's axis: the back one before the
  // whole tower (its body hides it), the side ones between the belfry and the spire, the front one last
  const dd=o=>depthOf([...avg(o.fp.map(p=>[...p,0])).slice(0,2),32])-depthOf([towerX,towerY,32]);
  const pins=f=>planSort(pinnacles.filter(f).map(o=>({...o,svg:o.draw()})));
  const front=pins(o=>dd(o)<-3)+porch()+belfry()+towerLip()+pins(o=>dd(o)>=-3&&dd(o)<0)+spireBase()+spire()+pins(o=>dd(o)>=0);
  return churchBase()+planSort([{fp:transept,z1:19,svg:crossRoof()},{fp:nave,z1:21,svg:naveWalls()+naveRoof()},{fp:towerBase,z1:63.1,svg:front},...crossEnds.map(o=>({...o,svg:o.draw()}))]);
}));
// Elevations are drawn directly on the projected wall at the current device resolution.
// Elevations run right-to-left as seen from outside, so lettering is drawn turned round about its anchor.
function wallText(g,str,x,y,w){const a=g.textAlign;g.save();g.translate(x,y);g.scale(-1,1);g.textAlign=a==='start'||a==='left'?'right':a==='end'||a==='right'?'left':a;g.fillText(str,0,0,w);g.restore()}
function paintSingaporeElevation(g,id){
  const {start,along,n,len:L,z,h,style,body,shop}=facades[id],H=h-z;
  if(L<.38||H<.48)return;
  const X=Dv(...along,0),Y=Dv(0,0,-1),p=P(...start,h);
  g.save();g.transform(...X,...Y,...p);g.beginPath();g.rect(0,0,L,H);g.clip();
  const box=(x,y,w,d,c)=>{g.fillStyle=c;g.fillRect(x,y,w,d)};
  const line=(x,y,u,v,c,w=.09)=>{g.strokeStyle=c;g.lineWidth=w;g.beginPath();g.moveTo(x,y);g.lineTo(u,v);g.stroke()};
  const poly=(ps,c)=>{g.fillStyle=c;g.beginPath();ps.forEach(([x,y],i)=>i?g.lineTo(x,y):g.moveTo(x,y));g.closePath();g.fill()};
  const side=dot(n,SUN)>.14,shade=c=>side?c:mix(c,'#8e839a',.19), cream=shade('#fbedd4');
  const glass=[shade('#b4d3cd'),shade('#c0d7ca'),shade('#a5c6cc'),shade('#d9d6b6')];
  function glazing(x,y,w,d,idx){
    box(x-.12,y-.12,w+.24,d+.24,shade('#837e7c'));box(x,y,w,d,glass[idx%4]);
    poly([[x,y],[x+w*.44,y],[x+w*.16,y+d],[x,y+d]],shade('#dce5d7'));
    box(x+w*.51,y,.09,d,cream);box(x,y+d*.27,w,.075,cream);
  }
  if(style==='cut'){
    box(0,0,L,H,shade('#d3c4b6'));for(let y=3.8;y<H;y+=3.8)box(0,y,L,.12,shade('#e6dac6'));
  }else if(style.startsWith('busTotem:')){
    if(L>.3){g.save();g.translate(L,0);g.scale(-1,1);
      const stop=BUS_STOPS[+style.slice(9)],text=UPX<.07;
      const label=(str,x,y,w,size,c)=>{if(!text)return;g.font='bold '+size+'px Arial';g.textAlign='center';g.textBaseline='middle';g.fillStyle=c;g.fillText(str,x,y,w)};
      box(0,0,L,H,shade('#8b9196'));
      box(.02,0,L-.04,.30,shade('#f7f6f1'));
      poly([[L*.22,.20],[L*.42,.08],[L*.62,.08],[L*.42,.20]],shade('#f39a1f'));
      poly([[L*.40,.24],[L*.60,.12],[L*.80,.12],[L*.60,.24]],shade('#f6c22c'));
      box(.02,.30,L-.04,.44,shade('#2a76b8'));
      box(L*.33,.38,L*.34,.26,shade('#fbfbf7'));box(L*.37,.42,L*.26,.09,shade('#2a76b8'));
      box(L*.36,.60,L*.07,.05,shade('#2a76b8'));box(L*.57,.60,L*.07,.05,shade('#2a76b8'));
      box(.02,.74,L-.04,.16,shade('#22649f'));label(stop.code,L/2,.82,L-.08,.1,'#ffffff');
      box(.02,.90,L-.04,.14,shade('#eef2ec'));label(stop.name,L/2,.97,L-.06,.06,'#26343a');
      const svc=stop.svc.split(' '),cols=svc.length>12?4:3,rows=Math.ceil(svc.length/cols),rh=.56/rows;
      box(.02,1.04,L-.04,.56,shade('#cfe6dc'));
      svc.forEach((v,i)=>label(v,(.02+(L-.04)*((i%cols)+.5)/cols),1.04+rh*(Math.floor(i/cols)+.5),(L-.04)/cols-.02,Math.min(.075,rh*.62),'#21302f'));
      for(let r=1;r<rows;r++)box(.02,1.04+rh*r,L-.04,.006,shade('#a9c6ba'));
      box(.04,1.66,L-.08,.78,shade('#767d81'));box(.07,1.70,L-.14,.70,shade('#f2f2ee'));
    g.restore();}
  }else if(style==='northName'||style==='colemanName'){
    if(L>1){g.font='bold .27px Arial';g.textAlign='center';g.textBaseline='middle';g.fillStyle='#faf3dc';wallText(g,style==='northName'?'NORTH BRIDGE RD':'COLEMAN ST',L/2,H/2,L-.18)}
  }else if(style==='curtain'||style==='office'||style==='residence'||style==='doors'){
    const floors=Math.max(1,Math.round(H/(style==='doors'?5:3.9))),d=H/floors,bays=Math.max(1,Math.round(L/(style==='residence'?2.7:2.2))),w=L/bays;
    const panes=['#9dc0c2','#88acb3','#a6c3c4','#83a7b3','#b4cbca'];
    for(let j=0;j<floors;j++){
      for(let i=0;i<bays;i++){
        const x=w*i,y=d*j,color=shade(panes[(Math.floor(i/7)+Math.floor(j/4))%5]);
        box(x,y,w+.01,d,color);box(x,y,w,d*.15,shade('#78979f'));
        if(i%13===2)poly([[x,y+d*.18],[x+w*.65,y+d*.18],[x+w*.20,y+d*.86],[x,y+d*.86]],shade('#c4d8d2'));
        box(x,y,.09,d,shade('#69838b'));box(x+.10,y,.055,d,shade('#c7d7ce'));
      }
      if(style==='curtain'||style==='office'){
        box(0,j*d+.3,L,d*.40,shade('#698992'));
        for(let i=0;i<bays;i++){
          const x=i*w;box(x+.10,j*d+.32,w-.22,d*.33,shade(i%7<3?'#78969c':'#65838d'));
          box(x+w*.9,j*d+.12,.13,d-.45,shade('#a4bdbd'));box(x+w*.94,j*d+.12,.05,d-.45,shade('#5b7883'));
        }
        box(0,j*d+d*.54,L,.10,shade('#bbcecb'));
      }
      box(0,(j+1)*d-.37,L,.37,shade('#6a8790'));box(0,(j+1)*d-.38,L,.095,shade('#d7e0d1'));
    }
    if(style==='curtain'&&n[0]>.8&&L>40){g.font='bold 2.5px Arial';g.fillStyle=cream;wallText(g,'Funan',L*.09,2.9)}
  }else if(style==='copper'){
    // Broad folded ribbons frame the horizontal openings. Draw each bend as
    // two flat tones so that the metal still reads as pen and coloured paper.
    box(0,0,L,H,shade('#718a8e'));
    const bays=Math.ceil(L/2.65);
    for(let i=0;i<bays;i++)box(i*2.65,H*.2,.11,H*.8,shade('#496b75'));
    const bends=[0,.15,.30,.45,.58,.74,.9,1];
    const levels=[.16,.16,.38,.38,.08,.16,.16,.17];
    for(let j=0;j<3;j++){
      const y=k=>H*(levels[k]*.72+j*.24);
      for(let i=0;i<bends.length-1;i++){
        const a=L*bends[i],b=L*bends[i+1],t=y(i),u=y(i+1),height=H*.19;
        poly([[a,t],[b,u],[b,u+height],[a,t+height]],shade(['#cd8066','#dd997b','#c67d66','#d79174'][(i+j)%4]));
        poly([[a,t+height-.36],[b,u+height-.36],[b,u+height],[a,t+height]],shade('#a76a59'));
        line(a,t,b,u,shade('#ebaf8f'),.10);
        if(UPX<.20)for(let x=a+.45;x<b-.3;x+=1.05){const h=t+(u-t)*(x-a)/(b-a);for(let k=0;k<3;k++)box(x,h+.35+k*.35,.12,.09,shade('#a56e60'))}
      }
    }
    for(let i=0;i<bays;i++){
      const x=i*2.65;box(x,H-3.0,2.60,2.95,shade(i%4===1?'#95b4b0':'#86a6aa'));
      box(x,H-3.0,2.60,.40,shade('#6e8689'));box(x+1.29,H-2.7,.06,2.7,shade('#678087'));
    }
    if(n[0]>.78&&L>26){
      const x=L*.49,w=Math.min(12,L*.34);
      box(x,H*.39,w,H*.19,shade('#9e705e'));g.fillStyle=cream;g.font='bold 2.0px Arial';wallText(g,'Funan',x+.5,H*.55,w-1);
    }
  }else if(['gothic','clerestory','porch','belfry','squareBelfry','transeptWindow','pinnacle'].includes(style)){
    const stone=shade('#f6f0e2'),shadow=shade('#c8c0b0'),reveal=shade('#9c978e');
    function lancet(x,top,bottom,w,col,stroke=null,weight=.09){
      const shoulder=top+Math.min(.82*w,(bottom-top)*.70);
      g.beginPath();g.moveTo(x-w/2,bottom);g.lineTo(x-w/2,shoulder);
      g.quadraticCurveTo(x-w*.47,top+w*.31,x,top);g.quadraticCurveTo(x+w*.47,top+w*.31,x+w/2,shoulder);
      g.lineTo(x+w/2,bottom);g.closePath();
      if(col){g.fillStyle=col;g.fill()}if(stroke){g.strokeStyle=stroke;g.lineWidth=weight;g.stroke()}
    }
    const cornice=(y,w)=>{box(0,y,L,w,shadow);box(0,y-.1,L,.10,stone)};
    const louvre=(x,top,w,bottom)=>{for(let y=top+w*.83;y<bottom-.08;y+=.32){box(x-w*.48,y,w*.96,.13,shade('#a2a398'));box(x-w*.48,y,w*.96,.045,stone)}};
    const window=(x,top,bottom,w,n)=>{
      lancet(x,top-.24,bottom+.17,w+.48,shadow);lancet(x,top-.14,bottom+.09,w+.26,stone);
      lancet(x,top,bottom,w,shade('#949e9b'));
      g.save();g.clip();
      const pane=w/n;
      for(let i=0;i<n;i++){const u=x-w/2+pane*i;
        box(u,top,pane,bottom-top,shade(['#92a6a3','#a8b6ad','#899e9d','#bec2ac'][i%4]));
        lancet(u+pane*.5,top+w*(.44+Math.abs(i-(n-1)/2)*.12),bottom,pane-.06,null,stone,.105);
        line(u,top+w*.7,u,bottom,stone,.12);
      }
      for(let y=bottom-.63;y>top;y-=.78)line(x-w/2,y,x+w/2,y,shade('#758c89'),.04);
      line(x-w/2,bottom-(bottom-top)*.36,x+w/2,bottom-(bottom-top)*.36,stone,.12);
      if(n>=3){for(const sign of [-1,1]){g.beginPath();g.moveTo(x,top+.42);g.quadraticCurveTo(x+sign*w*.31,top+w*.38,x,top+w*.71);g.strokeStyle=stone;g.lineWidth=.12;g.stroke()}}
      g.restore();box(x-w/2-.2,bottom+.11,w+.4,.10,stone);
    };
    if(style==='transeptWindow'&&L>3){
      window(L/2,H*.025,H*.76,L*.69,5);cornice(H*.81,.13);
      for(let k=1;k<=4;k++){const w=L*.095;box(L*k/5-w*.5,H*.87,w,H*.12,shade('#9aa6a1'))}
    }else if(style==='pinnacle'){
      cornice(.23,.1);cornice(H-.65,.14);
      if(L>.65)for(let j=1;j<4;j++){
        const x=L*.5,y=j*H/4,r=Math.min(.20,L*.17);
        poly([[x,y-r],[x+r,y],[x,y+r],[x-r,y]],shadow);
        poly([[x,y-r*.66],[x+r*.66,y],[x,y+r*.66],[x-r*.66,y]],stone);
      }
    }else if(style==='porch'&&L>4){
      const x=L*.5,w=L*.51,bottom=H-.10;
      lancet(x,H*.53,bottom,w+.90,shadow);lancet(x,H*.55,bottom,w+.48,stone);
      lancet(x,H*.58,bottom,w,reveal);lancet(x,H*.60,bottom,w-.34,shade('#82796e'));
      for(let k=0;k<3;k++)window(L*(k+1)/4,H*.12,H*.32,L*.15,2);
      cornice(H*.38,.2);cornice(H*.44,.13);
      for(const f of [.07,.93]){box(L*f-.28,.30,.56,H,stone);line(L*f+.28,.3,L*f+.28,H,shadow,.095)}
    }else if(style==='squareBelfry'||style==='belfry'){
      const n=style==='squareBelfry'?3:1;
      for(let j=0;j<n;j++){const x=(j+.5)*L/n,w=L/n*.68,top=H*.26,bottom=H*.79;
        lancet(x,top-.18,bottom+.15,w+.34,shadow);lancet(x,top,bottom,w,shade('#8f9390'));louvre(x,top,w,bottom)}
      cornice(.42,.16);cornice(H-.88,.14);
      if(n===3)for(let k=0;k<13;k++){const x=(k+.5)*L/13; lancet(x,.73,1.21,.32,shade('#bcb9ab'))}
    }else if(L>2.2){
      const n=Math.max(1,Math.round(L/(style==='clerestory'?3.4:4.2))),bay=L/n;
      for(let k=0;k<n;k++)window((k+.5)*bay,H*.12,H*.88,Math.min(bay*.60,2.75),2);
      cornice(H*.93,.12);
    }
    cornice(.11,.13);
  }else if(style!=='metal'){
    const floors=Math.max(1,Math.round(H/(style==='tower'?3.4:3.8))),rh=H/floors;
    const cols=Math.max(1,Math.round(L/(style==='tower'?2.9:4.2))),bw=L/cols;
    for(let j=0;j<floors;j++){
      const y=j*rh;box(0,y+.11,L,.22,cream);
      for(let i=0;i<cols;i++){
        const x=i*bw;
        if(bw<1.0)continue;
        const shop=z===0&&j===floors-1,margin=style==='hall'?.25:style==='tower'?.16:.11;
        glazing(x+bw*margin,y+rh*.20,bw*(1-margin*2),rh*(shop?.77:style==='hall'?.63:.59),((i*7+j*3+id)%8)<6?2:(i+j)%4);
        if(shop)box(x,y+rh*.07,bw,.39,['#707f7d','#ab7f72','#7d8394'][(i+id)%3]);
        if(style==='tower'||style==='hall')box(x+.02,y,bw*.12,rh,cream);
      }
      if(style==='plaza'||style==='adelphi'){box(0,y+rh*.84,L,.27,shade('#b6a599'));box(0,y+rh*.87,L,.13,cream)}
    }
  }
  if(shop)drawShopWindows(g,shop,L,H,id,shade);
  g.restore();
}
const footprintPath=r=>pd(atZ(r,0)), surface=(rings,color)=>'<path d="'+rings.map(footprintPath).join('')+'" fill="'+color+'" fill-rule="evenodd"/>';
const edge=(a,b,c,width)=>'<path d="'+pd([a,b],false)+'" fill="none" stroke="'+c+'" style="stroke-width:'+f(width)+'"/>';
const center=SCENE.centerlines.map(l=>measuredLane(l));
const crossing=SCENE.markings.map(p=>measuredLane({p}));
function stripeAt(p,d,length,width){
  const n=[-d[1]*width/2,d[0]*width/2],a=[d[0]*length/2,d[1]*length/2];
  return footprintPath([[p[0]-a[0]-n[0],p[1]-a[1]-n[1]],[p[0]+a[0]-n[0],p[1]+a[1]-n[1]],[p[0]+a[0]+n[0],p[1]+a[1]+n[1]],[p[0]-a[0]+n[0],p[1]-a[1]+n[1]]]);
}
// Garden railings stop at the public path and carriage entrances.
const streetFurniture=[];
function gardenFence(a,b){
  const length=Math.hypot(b[0]-a[0],b[1]-a[1]),n=Math.ceil(length/5);
  for(let i=0;i<n;i++){
    const pt=t=>[a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t],start=pt(i/n),end=pt((i+1)/n);
    const pier=rect(...start,.42,.42),stone=section(pier,0,1.57,'metal','#ede0c8','#f4e7cc');
    const fp=[...pier,end];
    streetFurniture.push(obj(fp,1.74,()=>{
      let s=edge([...start,.25],[...end,.25],'#a9a394',.26)+edge([...start,1.28],[...end,1.28],'#788d82',.10);
      for(let j=0;j<9;j++){const p=pt((i+j/9)/n);s+=stick([...p,.3],[...p,1.40],.036,'#72877c')}
      return s+stone()+shape(atZ(rect(...start,.53,.53),1.60),'#f8ecd4',.5);
    }));
  }
}
gardenFence([14,6.2],[100,6.6]);gardenFence([4.5,23],[5.95,73]);
for(const [x,y,dx,dy] of [[-24,-33,1,0],[-24,13,1,0],[-27,51,1,0],[38,-4,0,-1],[65,-6,0,-1]]){
  const fp=rect(x,y,3.7,4.1);
  streetFurniture.push(obj(fp,7.7,()=>stick([x,y,0],[x,y,6.85],.105,'#838a84')+
    stick([x,y,6.85],[x+dx*1.4,y+dy*1.4,7.37],.082,'#8e9891')+
    stick([x+dx*1.4,y+dy*1.4,7.37],[x+dx*2.35,y+dy*2.35,7.37],.13,'#849189')));
}
for(const [x,y] of [[7,34],[7.5,48],[58,8.7]]){
  const fp=rect(x,y,.8,2.5);
  streetFurniture.push(obj(fp,1.2,()=>stick([x,y-.84,0],[x,y-.84,.55],.11,'#727d70')+stick([x,y+.84,0],[x,y+.84,.55],.11,'#727d70')+
    shape(atZ(fp,.58),'#bc9571',.55)+shape([[x+.33,y-1.25,.68],[x+.33,y+1.25,.68],[x+.39,y+1.25,1.05],[x+.39,y-1.25,1.05]],'#c29e77',.5)));
}
const streetSign=rect(-4.6,-2.3,2.7,.11),nameplate=section(streetSign,3.03,3.53,'northName','#547c68','#8da78b');
const otherSign=rect(-4.6,-2.3,.11,2.35),otherPlate=section(otherSign,2.49,2.97,'colemanName','#547c68','#8da78b');
streetFurniture.push(obj(rect(-4.6,-2.3,2.9,2.6),3.7,()=>stick([-4.6,-2.3,0],[-4.6,-2.3,3.56],.07,'#78867d')+otherPlate()+nameplate()));

// Bus stops. Positions, codes, names and services are OpenStreetMap's highway=bus_stop nodes (all mapped with
// shelter=yes, bench=yes; services from route_ref). OSM places the North Bridge Road points 10-13 m back on the
// pavement; the shelters stand at the kerb as in photographs of the LTA design. Look from 2023 photos of central
// stops (Bugis Stn Exit B): a thin dark-grey canopy on square posts, a bench, an info board and the tall stop pole.
// a-b runs along the kerb (12 m), side picks the pavement side, down is the end the bus front stops at, and off sets
// the shelter back behind the pedestrian route so nobody walks under its roof (the painter cannot sort a head under it).
const BUS_STOPS=[
  {code:'04167',name:'City Hall Stn Exit B',a:[-8.72,125],b:[-8.37,137],side:1,down:-1,svc:'61 124 145 166 174 174e 197 NR1 NR2 NR5 NR6 NR8',off:2.4},
  {code:'04168',name:'Aft City Hall Stn Exit B',a:[-8.97,36.3],b:[-8.97,48.3],side:1,down:-1,svc:'32 51 63 63A 80 195 195A 851 851e 961 961M',off:5},
  {code:'04249',name:'Opp The Treasury',a:[-10.48,-173],b:[-10.18,-161],side:1,down:-1,svc:'1N 2N 3N 4N 5N 6N 51 61 63 63A 80 124 145 166 174 174e 197 851 851e 961 961M NR1 NR2 NR5 NR6 NR8',off:2.3},
  {code:'04149',name:'Grand Park City Hall',a:[-185.38,15],b:[-186.98,27],side:1,down:-1,svc:'2 12 12e 33 147 147A 190',off:.6},
  {code:'04142',name:'Armenian Church',a:[-204.32,47],b:[-205.22,59],side:-1,down:1,svc:'2 2A 12 12e 32 33 51 61 63 80 197',off:.6}
];
BUS_STOPS.forEach((stop,index)=>{
  const [ax,ay]=stop.a,len=Math.hypot(stop.b[0]-ax,stop.b[1]-ay),u=[(stop.b[0]-ax)/len,(stop.b[1]-ay)/len];
  const n=[stop.side*u[1],-stop.side*u[0]];
  const at=(s,d)=>[ax+u[0]*s+n[0]*d,ay+u[1]*s+n[1]*d];
  const quad=(s0,s1,d0,d1)=>[at(s0,d0),at(s1,d0),at(s1,d1),at(s0,d1)];
  const grey='#6b7275',post='#858c8f';
  const o=stop.off,canopy=section(quad(.4,len-.4,o,o+2.4),2.78,2.93,'metal','#5e6568','#727a7d');
  const posts=[1.6,len/2,len-1.6].map(s=>({at:at(s,o+2.25),draw:section(quad(s-.08,s+.08,o+2.17,o+2.33),0,2.78,'metal',post,post)}));
  const seats=[[2.1,len/2-.45],[len/2+.45,len-2.1]].map(([s0,s1])=>({at:at((s0+s1)/2,o+1.85),draw:section(quad(s0,s1,o+1.65,o+2.05),.42,.49,'metal','#9aa1a3','#b3b9ba')}));
  const boardS=stop.down<0?len-1.1:1.1;
  const board={at:at(boardS,o+2.3),draw:section(quad(boardS-.5,boardS+.5,o+2.26,o+2.38),.25,2.15,'metal','#8d9396','#a4aaac')};
  const kerbLine=shape([...quad(-3,len+3,-.32,-.18)].map(([x,y])=>[x,y,.03]),'#e6bf3e',.05);
  streetFurniture.push(obj(quad(.4,len-.4,o,o+2.4),2.95,()=>
    kerbLine+[...posts,...seats,board].sort((p,q)=>depthOf([...p.at,1])-depthOf([...q.at,1])).map(p=>p.draw()).join('')+canopy()));
  // The pole stands just past the bus-front end of the shelter, its faces turned to the road and the pavement.
  const poleS=stop.down<0?-.9:len+.9,pole=section(quad(poleS-.07,poleS+.07,.18,.60),0,3.1,'busTotem:'+index,grey,'#7d8487');
  streetFurniture.push(obj(quad(poleS-.3,poleS+.3,.1,.7),3.15,()=>pole()));
});


// Standing groups occupy spare pavement beside the through routes. Positions
// were sampled inside the mapped paths with clearance for walls, trees and trips.
const forecourtAprons=[[[[-90.0,-138.0],[-90.0,-137.26],[-34.23,-137.65],[-34.35,-123.04],[-51.4,-115.58],[-51.41,-106.23],[-34.72,-100.89],[-33.79,-53.23],[-33.48,-28.62],[-50.33,-23.06],[-50.78,-71.0],[-71.68,-70.96],[-52.72,-70.03],[-52.82,-67.98],[-50.77,-67.94],[-51.88,-14.95],[-27.0,-14.33],[-27.0,-19.0],[-23.45,-19.0],[-25.12,-85.8],[-27.41,-87.13],[-27.83,-110.64],[-25.79,-112.54],[-26.42,-138.0]]],[[[-90.0,-67.37],[-72.06,-66.87],[-90.0,-67.75]]],[[[-90.0,-22.0],[-91.0,-22.0],[-91.0,-18.09],[-90.3,-18.55],[-59.03,-17.64],[-55.98,-15.34],[-54.91,-66.03],[-56.25,-66.1],[-57.18,-24.32],[-90.0,-25.24]]],[[[3.0,-18.0],[3.0,-21.33],[1.21,-21.44],[1.58,-94.77],[3.0,-94.79],[3.0,-100.11],[-5.36,-100.05],[-5.06,-135.0],[-9.55,-135.0],[-8.92,-110.1],[-12.0,-110.01],[-8.92,-110.09],[-6.62,-18.0]]]];
const fanGroups=[[[-30.86,-35.07,1],[-31.79,-31.93,0],[-30.2,-33.88,0]],[[-33.69,-23.6,0],[-30.5,-19.92,0],[-33.22,-19.44,1],[-32.08,-23.07,0],[-31.99,-19.06,1],[-33.93,-18.2,0],[-30.67,-22.84,1]],[[-28.14,-27.98,0],[-29.49,-25.39,1],[-28.43,-29.75,0],[-27.37,-25.02,1]],[[-34.91,-24.9,0],[-32.66,-25.19,0],[-30.1,-29.98,0],[-31.41,-24.8,1],[-30.18,-26.93,1],[-33.82,-26.45,0],[-32.38,-26.78,0],[-31.76,-29.6,0],[-30.62,-28.03,1]],[[-29.42,-23.5,0],[-29.23,-20.27,0],[-27.9,-18.86,0]],[[-37.98,-25.42,1],[-37.12,-26.61,0]],[[-27.55,-30.58,1],[-29.42,-32.99,1],[-28.14,-34.67,0],[-29.58,-31.52,0],[-26.67,-35.16,0]],[[-32.51,-38.52,0],[-31.44,-37.28,0],[-30.47,-38.84,0],[-32.9,-36.39,0],[-31.97,-39.87,0],[-32.78,-40.85,0]],[[-32.72,-46.76,1],[-30.13,-47.94,1],[-32.14,-42.21,0],[-32.67,-44.72,0],[-30.26,-43.78,0],[-31.07,-46.84,1]],[[-28.9,-47.08,0],[-27.19,-45.43,0],[-27.64,-47.79,0],[-29.89,-45.37,0],[-28.14,-44.49,1]],[[-32.97,-48.4,0],[-32.47,-49.7,0],[-30.04,-49.13,1],[-30.96,-52.63,0]],[[-28.82,-49.05,1],[-27.55,-52.26,1],[-27.55,-49.19,0],[-28.87,-51.47,0],[-28.6,-52.99,0]],[[-27.7,-40.15,1],[-27.01,-36.33,1],[-29.89,-36.64,1],[-26.43,-40.01,0]],[[-30.92,-61.04,1],[-32.38,-60.98,0],[-30.23,-64.92,0],[-31.68,-64.6,1],[-31.95,-62.17,0],[-30.35,-63.69,1],[-33.3,-63.56,1],[-32.78,-65.29,0],[-30.16,-62.43,0]],[[-33.14,-58.12,0],[-30.17,-59.28,0],[-32.16,-54.38,1],[-30.19,-56.99,1],[-33.25,-59.94,0]],[[-27.29,-58.54,1],[-28.62,-57.15,0],[-28.21,-54.24,0],[-27.52,-56.29,0],[-28.83,-58.82,1]],[[-28.98,-61.75,0],[-27.22,-60.05,0],[-27.63,-64.67,0],[-27.48,-62.81,0]],[[-28.64,-68.82,1],[-28.08,-66.29,1],[-27.98,-70.52,0],[-27.42,-69.38,1]],[[-33.47,-72.8,0],[-30.5,-72.29,0],[-31.28,-75.32,0],[-31.52,-74.04,1],[-31.91,-77.4,0],[-32.95,-75.5,0],[-33.5,-77.81,1],[-30.14,-76.29,0],[-30.57,-77.42,0]],[[-32.25,-68.64,0],[-31.77,-69.69,0],[-30.88,-66.36,0],[-32.88,-70.4,1],[-32.52,-71.82,0],[-33.19,-67.83,1]],[[-29.65,-75.23,1],[-28.95,-77.53,0],[-27.78,-72.15,1],[-27.95,-75.89,0],[-29.81,-73.97,0]],[[-27.85,-78.29,0],[-29.07,-82.28,0],[-27.9,-79.46,0],[-27.85,-81.93,0],[-27.93,-83.09,1]],[[-30.64,-81.58,1],[-31.17,-78.58,0],[-33.18,-82.77,0],[-33.7,-81.43,0],[-32.6,-80.85,0],[-32.41,-83.64,1]],[[-29.8,-88.7,1],[-28.55,-84.08,1],[-28.39,-90.0,0],[-29.35,-86.2,0],[-27.96,-85.23,0],[-28.17,-88.54,0]],[[-28.83,-91.51,0],[-28.58,-93.28,0],[-28.44,-95.76,0],[-29.58,-94.8,0]],[[-33.17,-92.55,0],[-32.28,-90.08,1],[-31.05,-92.91,0],[-30.6,-91.24,1],[-30.21,-95.81,1],[-33.41,-90.35,0],[-32.32,-93.37,0],[-33.4,-93.97,1]],[[-32.74,-87.01,0],[-33.26,-84.82,0],[-30.68,-86.52,0],[-31.89,-85.1,1],[-31.34,-87.57,0],[-32.64,-88.29,0],[-31.26,-89.02,0]],[[-33.32,-96.25,1],[-30.41,-100.84,0],[-33.79,-97.54,1],[-31.22,-98.24,1],[-34.29,-101.37,1],[-31.59,-100.48,0]],[[-35.52,-102.78,0],[-35.77,-103.94,0],[-35.87,-105.48,1],[-39.63,-106.14,0],[-39.36,-104.03,1]],[[-29.25,-104.8,0],[-29.13,-102.23,0],[-29.05,-106.77,0]],[[-29.41,-98.64,0],[-28.48,-100.74,1],[-28.08,-98.78,0]],[[-30.09,-103.08,1],[-33.73,-104.3,1],[-32.38,-104.62,0],[-34.45,-105.58,0],[-32.92,-107.51,0]],[[-40.93,-103.73,0]],[[-35.31,-113.96,0],[-35.32,-110.91,0],[-36.56,-108.13,0],[-38.68,-109.81,1]],[[-34.0,-113.57,0],[-30.1,-112.95,1],[-33.69,-110.74,0],[-30.64,-111.22,1],[-33.67,-108.5,0]],[[-29.48,-108.85,0],[-29.4,-110.86,0]],[[-37.03,-114.15,1],[-37.0,-115.71,1],[-38.59,-117.82,0],[-38.2,-119.13,0],[-38.39,-115.6,1]],[[-33.48,-121.16,0],[-34.88,-120.68,1],[-31.93,-125.02,0],[-33.01,-125.71,0],[-32.88,-123.01,0],[-30.78,-121.34,1],[-30.28,-124.14,1],[-30.5,-125.69,0],[-33.59,-123.94,0]],[[-28.37,-117.3,0],[-29.61,-117.79,1],[-28.85,-116.21,0]],[[-29.93,-122.72,0],[-28.79,-124.75,0]],[[-36.48,-120.35,0]],[[-29.52,-127.3,1],[-29.19,-129.29,1],[-29.51,-130.41,0]],[[-30.63,-119.83,0],[-34.79,-115.72,0]],[[-31.32,-128.13,0],[-31.35,-130.71,0],[-32.95,-127.32,1],[-30.48,-129.27,0],[-32.19,-129.02,0],[-30.87,-131.78,1]],[[-31.0,-133.95,1],[-31.31,-135.54,0],[-31.47,-137.19,0]],[[-29.4,-134.7,0],[-28.85,-135.94,0],[-29.4,-132.88,1]],[[-30.91,-138.77,0],[-30.72,-141.21,1],[-31.18,-139.98,0],[-32.24,-139.14,0],[-32.63,-142.04,0],[-33.84,-140.47,1],[-33.76,-142.85,0],[-30.01,-142.72,1],[-34.61,-141.8,0]],[[-29.65,-140.43,0]],[[-35.18,-20.96,1],[-38.34,-20.85,0],[-39.15,-19.56,0],[-39.66,-23.97,0]],[[-34.97,-17.58,0]],[[-43.16,-21.46,1],[-42.68,-23.6,0],[-41.69,-18.65,0],[-44.96,-23.62,0],[-44.84,-21.32,0],[-43.54,-19.47,1]],[[-29.84,-16.83,0],[-28.25,-17.23,0]],[[-37.77,-17.49,0]],[[-56.49,-19.09,1],[-57.07,-21.45,0],[-58.59,-19.76,0],[-58.41,-18.32,0],[-58.41,-22.93,0],[-56.73,-23.04,0],[-59.9,-19.69,0],[-59.03,-21.53,1]],[[-47.19,-22.59,0],[-46.11,-23.57,1],[-46.9,-20.83,0],[-48.71,-22.83,1],[-46.13,-21.75,0],[-47.49,-19.27,0]],[[-45.29,-17.61,0],[-49.39,-17.43,0],[-46.45,-17.53,0]],[[-51.03,-25.47,1],[-51.06,-28.54,0]],[[-44.09,-17.58,1],[-41.86,-17.42,0]],[[-50.55,-19.3,1],[-50.36,-18.14,0]],[[-64.03,-19.74,1],[-62.46,-20.32,1],[-61.58,-19.24,1],[-61.23,-23.36,0],[-60.7,-21.57,0],[-64.56,-20.92,0],[-63.47,-23.79,0],[-64.92,-18.36,0]],[[-57.48,-17.64,0]],[[-67.04,-18.57,1],[-65.9,-19.31,1],[-66.96,-20.83,0],[-68.05,-20.26,0],[-65.5,-23.91,0],[-69.96,-23.41,1],[-69.65,-20.01,0],[-65.72,-20.86,0],[-68.39,-18.69,0]],[[-56.25,-28.84,0],[-56.4,-24.96,1]],[[-51.35,-17.5,0]],[[-70.82,-21.15,1],[-70.87,-22.53,1],[-70.89,-18.76,0],[-74.99,-22.89,1],[-73.89,-19.65,0],[-72.14,-18.66,1],[-72.21,-23.7,0],[-74.53,-18.57,0]],[[-76.45,-19.79,0],[-78.01,-21.67,0],[-78.39,-19.73,0],[-77.68,-23.62,1],[-79.39,-21.2,0],[-76.33,-21.67,0],[-79.44,-22.65,0],[-78.99,-18.7,1],[-76.2,-18.56,0]],[[-80.04,-19.21,0],[-84.59,-23.18,0],[-83.49,-19.55,0],[-82.33,-22.05,0],[-81.19,-23.01,0],[-84.06,-21.82,0],[-80.64,-20.58,1],[-81.85,-19.44,0],[-82.54,-23.75,1]],[[-76.34,-24.2,1]],[[-85.09,-24.25,1],[-86.32,-24.3,1]],[[-85.35,-20.76,1],[-88.81,-22.34,1],[-85.9,-19.09,0],[-87.91,-23.99,0],[-86.7,-21.82,1],[-85.8,-22.95,0],[-89.44,-23.63,0]],[[-80.67,-24.21,0]],[[-90.48,-21.07,0]],[[-1.88,-39.76,1],[-1.02,-40.75,0],[-0.42,-36.6,1],[-2.27,-38.66,0],[-4.39,-40.92,0]],[[0.63,-38.02,0],[0.1,-39.64,0]],[[-3.16,-27.93,1],[-3.06,-29.39,1],[-0.48,-25.08,1],[-0.31,-29.59,0],[-1.69,-25.89,0],[-4.05,-24.07,0],[-0.73,-27.44,0],[-3.97,-25.68,0]],[[-1.06,-33.83,0],[-0.41,-30.87,0],[-4.21,-32.25,0]],[[-1.27,-43.74,0],[-3.01,-47.09,0]],[[-2.45,-55.05,0],[-4.62,-55.82,0],[-3.47,-57.67,0],[-0.9,-58.74,1],[-3.96,-54.21,1],[-4.76,-58.12,0]],[[0.25,-51.09,1]],[[0.49,-47.13,0],[0.6,-44.7,1]],[[-1.14,-52.84,0],[-3.04,-52.3,1]],[[-0.12,-67.3,1],[-3.88,-70.1,0],[-0.37,-69.14,0],[-0.86,-66.14,0],[-1.74,-68.31,0],[-4.75,-68.9,0]],[[-1.03,-78.59,0],[-4.02,-82.18,0],[-2.58,-78.01,0]],[[-4.95,-65.08,1],[-4.02,-61.23,1],[-2.99,-60.68,0]],[[0.2,-56.32,0]],[[-1.49,-75.51,0],[-1.38,-73.1,1],[-2.89,-74.67,0]],[[-5.33,-80.27,0],[-5.61,-81.49,0],[-5.31,-78.58,1]],[[-5.64,-76.76,0]],[[0.35,-98.27,1],[0.07,-96.16,0]],[[-3.88,-92.56,0],[-0.16,-93.13,1],[-1.71,-90.98,0],[-4.96,-93.74,0],[-4.18,-94.89,0],[-0.94,-94.57,1]],[[-5.09,-89.13,1],[-5.48,-85.65,0]],[[-1.94,-86.66,0],[-3.33,-85.72,0]],[[-5.88,-90.92,1]],[[-5.78,-96.44,0]],[[-4.98,-97.58,1],[-2.1,-96.31,0]],[[-5.92,-132.65,1],[-7.08,-133.0,0],[-6.03,-133.88,0]],[[-6.06,-107.92,0],[-6.36,-105.91,0],[-6.25,-102.57,0],[-6.14,-104.11,1]],[[-6.46,-119.31,0],[-6.19,-117.27,0],[-6.48,-115.36,1],[-5.98,-114.24,0]],[[-6.71,-125.14,1],[-6.33,-123.15,1],[-6.5,-121.15,0]],[[-6.52,-129.44,0],[-5.76,-131.35,0],[-5.84,-127.11,1],[-6.06,-128.35,0]],[[-6.21,-112.41,1],[-6.47,-111.0,0],[-6.01,-109.77,0]],[[-4.96,22.05,1],[-4.87,20.16,1]],[[2.73,7.12,0],[3.69,7.8,1]],[[5.03,21.05,0]],[[-4.49,16.38,1],[-4.42,15.08,1]],[[-4.71,24.85,0],[-4.96,26.31,0],[-4.82,28.83,0]],[[7.33,24.92,0],[8.48,25.55,0]],[[-5.05,31.72,1],[-5.87,32.98,1],[-5.15,34.23,0],[-6.51,34.64,1],[-5.27,30.28,0]],[[3.23,18.02,0],[3.36,20.36,0],[4.68,22.53,1],[3.62,19.13,0]],[[-4.3,9.96,0],[-2.44,10.6,0],[-3.38,11.83,1]],[[-5.48,18.33,0],[-5.92,23.47,0]],[[-6.26,28.19,0],[-6.24,26.4,1],[-5.01,27.59,0]],[[9.67,17.92,1]],[[0.08,4.26,0],[1.36,0.62,0],[0.26,1.42,0],[4.81,1.16,0],[1.47,4.38,0],[0.62,2.58,0]],[[-4.56,54.93,1],[-4.72,56.22,1],[-4.15,57.81,0],[-4.81,59.66,1]],[[-4.36,38.48,0],[-4.32,36.79,1]],[[-4.55,52.21,0],[-4.37,50.37,0],[-5.0,49.13,0]],[[-6.32,55.63,1],[-5.4,57.26,0],[-6.28,54.45,1],[-5.61,58.43,0]],[[-5.54,52.92,0],[-5.51,51.08,0],[-5.72,48.16,0],[-6.22,49.84,0]],[[-4.73,46.59,1]],[[-6.01,37.75,0],[-6.12,36.44,0]],[[-5.43,69.07,1],[-6.25,67.81,0],[-5.29,71.0,0],[-6.58,69.24,0]],[[-5.46,73.4,0],[-6.56,72.27,1],[-5.36,76.32,0]],[[-4.97,77.83,0],[-4.09,73.89,0],[-4.92,72.2,0],[-4.16,76.45,0]],[[-4.97,80.11,1],[-3.8,79.83,0],[-3.82,78.58,1]],[[-6.43,61.22,0],[-6.38,64.03,0]],[[-4.43,70.24,1]],[[-4.13,61.51,1]],[[18.39,0.35,0],[16.56,0.76,0],[15.61,1.41,0],[19.39,1.79,0]],[[-1.47,1.46,0],[-3.43,0.16,0],[-1.81,0.11,1]],[[11.34,0.37,1],[11.61,1.82,0]],[[7.11,0.61,1],[5.72,0.31,1]],[[31.42,-0.61,1],[34.86,-0.66,1]],[[43.18,-0.16,0],[41.03,-0.02,0],[41.66,-1.06,0],[44.79,-1.2,0]],[[49.74,-0.69,0],[46.06,-0.79,1]],[[56.91,-0.98,1],[59.08,-0.55,0]],[[39.68,-0.58,0],[36.19,-0.56,0],[38.3,-0.17,0]],[[30.86,0.48,0],[32.75,0.05,1]],[[48.48,0.09,0]],[[36.94,0.99,0],[35.17,0.83,0]],[[58.04,0.0,1],[59.24,0.65,0]],[[29.02,1.26,0]],[[29.54,-0.2,1]],[[72.3,1.99,1],[70.52,2.94,0],[74.71,2.41,1],[73.56,2.68,0],[73.96,1.33,1]],[[62.92,1.32,0],[63.01,0.13,0],[64.47,1.15,0],[61.65,0.91,0]],[[67.33,0.98,0],[69.97,1.7,0],[65.98,0.77,0],[68.77,1.1,0],[66.83,2.19,0],[69.34,2.86,1],[65.57,1.88,0]],[[61.03,-0.19,1],[64.46,-0.05,0]],[[76.71,2.57,1],[75.77,1.43,1]],[[78.26,74.8,1],[75.73,74.15,1],[78.08,73.57,0],[75.92,72.49,1]],[[69.85,73.4,0]],[[86.39,66.46,0],[87.67,66.71,0]],[[67.69,66.66,1]],[[72.93,66.84,0]],[[88.56,76.08,0],[85.42,74.07,0]],[[83.65,74.42,1],[82.46,74.29,1],[80.51,74.0,1]],[[78.11,66.17,0]],[[63.5,64.96,1],[61.61,64.24,0],[64.59,64.53,0],[62.14,65.84,0]],[[81.42,67.54,0],[84.42,67.37,0]],[[75.67,65.99,0]],[[73.55,73.61,1],[74.62,73.16,0]],[[56.45,63.19,0],[57.72,64.75,0],[56.05,64.71,0]],[[57.67,70.3,0],[56.26,70.32,0]],[[62.76,72.12,1],[61.45,72.34,0]],[[49.52,68.87,0],[48.21,69.35,0]],[[50.13,70.71,1],[52.19,69.89,1],[53.44,70.35,0]],[[54.59,63.82,0]],[[68.12,65.53,1],[69.94,65.77,0],[67.06,64.99,1]],[[59.65,72.32,0]],[[72.88,65.2,0]],[[116.81,-1.23,1],[115.02,-2.87,0]],[[88.61,0.65,0]],[[89.38,-12.87,0]],[[86.42,-3.21,1]],[[112.7,0.4,0]],[[103.21,0.9,0]],[[99.35,-13.67,1]],[[97.88,-1.91,0],[96.24,-3.13,0]],[[107.17,-12.08,0]],[[106.03,-0.42,1]],[[111.74,-13.47,0],[112.99,-12.59,0]],[[104.1,-12.47,0],[101.9,-13.34,0]],[[106.16,5.92,1]],[[109.7,7.14,1]],[[113.84,-0.98,0],[110.73,-1.24,1]],[[91.91,-12.97,0]],[[85.93,-21.26,1],[85.93,-22.68,0],[85.86,-18.42,0],[85.62,-19.71,1]],[[86.03,-27.09,1],[86.02,-25.93,0],[86.12,-24.75,0],[86.03,-28.61,0]],[[86.14,-31.63,0],[86.12,-30.12,1]],[[17.65,-17.16,1],[16.04,-16.82,0]],[[12.93,-17.97,0],[10.22,-17.09,0]],[[20.44,-17.48,1]],[[1.69,-17.91,0],[4.15,-16.28,1]],[[10.56,-18.52,0]],[[6.3,-18.67,1]],[[0.17,-26.12,1]],[[-0.33,-21.31,0],[-1.04,-22.83,1]],[[4.91,-18.31,0],[3.8,-18.94,0]],[[7.46,-17.78,0],[7.35,-16.41,0]],[[-61.65,-4.08,1],[-64.76,-5.27,0]],[[-39.97,-3.12,0],[-36.77,-3.2,1],[-38.97,-4.45,0],[-35.55,-3.37,1]],[[-65.89,-4.75,0],[-66.85,-2.28,0],[-68.91,-5.37,1],[-68.08,-2.94,0],[-68.4,-1.45,1],[-66.95,-3.46,0]],[[-52.44,-4.88,0],[-52.1,-3.14,1],[-54.78,-3.56,1],[-54.35,-4.78,0]],[[-43.19,-2.96,1],[-41.66,-4.41,0],[-41.06,-2.42,0],[-40.32,-4.59,0],[-43.61,-4.53,0]],[[-56.39,-4.64,0],[-59.55,-4.19,0]],[[-34.54,-1.79,1]],[[-49.41,-4.79,0]],[[-79.2,-5.73,1],[-76.14,-5.45,0],[-77.36,-5.4,0]],[[-84.67,-5.89,0],[-83.27,-5.79,1],[-80.55,-5.62,0]],[[-86.92,-4.45,0],[-87.19,-1.9,0],[-85.87,-4.95,1],[-85.95,-3.2,0]],[[-71.8,-5.04,0],[-73.11,-5.53,1]],[[-93.79,-3.95,0],[-93.24,-5.05,0]],[[-37.02,-141.64,1],[-37.97,-139.83,0],[-39.37,-142.54,0],[-39.77,-140.36,1]],[[-39.19,-149.6,0]],[[-34.24,-151.38,1],[-30.09,-152.87,0],[-31.95,-151.41,0]],[[-31.39,-162.14,0],[-31.42,-166.37,1]],[[-31.21,-156.5,1]],[[-29.3,-156.25,0]],[[-42.87,-149.97,0]],[[-29.78,-154.37,0]],[[-29.57,-148.97,0]],[[-40.49,-143.37,0]]];
const meetingPaths=[[[-35.76,-26.65],[-37.2,-20.0]],[[-28.77,-42.03],[-28.93,-38.62]],[[-30.69,-54.75],[-31.71,-57.99]],[[-31.04,-67.57],[-28.97,-73.12]],[[-28.76,-80.66],[-32.73,-79.44]],[[-29.42,-84.92],[-31.8,-82.39]],[[-33.21,-102.3],[-32.39,-97.98]],[[-32.16,-110.83],[-30.25,-107.82]],[[-33.61,-119.42],[-32.64,-114.11]],[[-32.91,-132.88],[-32.73,-136.97]],[[-40.54,-20.06],[-40.9,-23.67]],[[-50.29,-21.1],[-48.35,-17.94]],[[-62.77,-22.01],[-67.67,-23.19]],[[-75.33,-19.47],[-73.56,-23.2]],[[-87.84,-19.93],[-93.81,-19.45]],[[-1.03,-38.0],[-3.52,-34.53]],[[-4.24,-66.8],[-0.49,-61.59]],[[-0.25,-83.85],[-1.03,-89.88]],[[-1.53,13.38],[2.08,17.84]],[[-4.98,44.62],[-5.89,39.93]],[[-5.28,62.56],[-4.64,68.23]],[[3.9,9.41],[8.03,14.61]],[[50.9,-0.5],[54.63,-0.76]],[[69.1,72.32],[64.47,72.6]],[[104.36,-2.47],[109.25,-2.2]],[[-0.57,-19.72],[-3.74,-21.4]],[[-45.21,-3.91],[-50.85,-3.53]]];
const raceColours=['#e36249','#ed914d','#448c91','#f3dfa9','#637599','#e9e1cf','#76a895'];
function raceVisitor(p,d,id){
  const fan={...pedDressed(id),p,d,walked:0,shirt:raceColours[id%raceColours.length]};
  const part=pedestrian(fan,0),h=fan.tall;
  const at=(fwd,side,z)=>[p[0]+d[0]*fwd-d[1]*side,p[1]+d[1]*fwd+d[0]*side,z*h+.04];
  const accent=raceColours[(id+2)%raceColours.length];
  if(id%3!==1){
    part.svg+=shape([at(-.15,-.17,1.72),at(.12,-.19,1.72),at(.31,-.12,1.68),at(.32,.12,1.68),at(.10,.19,1.72),at(-.15,.17,1.72)],accent,.45);
    part.svg+=ball(at(0,0,1.73),.163,soft(accent),.36);
  }
  if(id%4===0){
    // A visitor holding a camera at eye level.
    part.svg+=stick(at(.03,-.23,1.26),at(.22,-.22,1.47),.055,fan.skin.l)
      +stick(at(.23,-.22,1.47),at(.30,-.06,1.52),.055,fan.skin.l)
      +stick(at(.32,-.10,1.53),at(.32,.10,1.53),.095,'#45575d')
      +ball(at(.40,0,1.53),.059,soft('#a3c5c2'),.23);
  }else if(id%4===1){
    part.svg+=stick(at(.15,-.25,.92),at(.10,-.25,.61),.022,'#68726f')
      +stick(at(.08,-.28,.28),at(.12,-.28,.64),.145,accent);
  }else{
    part.svg+=stick(at(.12,-.13,1.37),at(.24,0,1.05),.018,'#edc464')
      +stick(at(.24,0,1.05),at(.12,.13,1.37),.018,'#edc464')
      +shape([at(.244,-.054,1.09),at(.244,.054,1.09),at(.244,.054,.97),at(.244,-.054,.97)],'#f8e8c1',.2);
  }
  return part;
}
// Freestanding fabric pennants mark the illustrated fan gathering.
const eventPoles=[[-30.91,-50.33],[-31.06,-76.52],[-42.59,-18.11],[-4.66,33.06],[71.48,73.03]];
function fanPennant(x,y,i){
  const v=(u,h)=>[x+.07*u,y+u,h];
  const fabric=[[0,4.1],[1.18,4.1],[1.09,1.95],[.67,1.64],[0,1.92]];
  const palette=['#ce6350','#588386','#df9861'],ink='#f4e6cb';
  let svg=stick([x,y,0],[x,y,4.26],.05,'#707e7a')+shape(fabric.map(([u,z])=>v(u,z)),palette[i%3],.55);
  for(let row=0;row<2;row++)for(let col=0;col<6;col++){
    if((row+col)%2)continue;
    const a=col*.19,b=4.04-row*.19;
    svg+=shape([v(a,b),v(a+.19,b),v(a+.19,b-.19),v(a,b-.19)],ink,0);
  }
  for(let j=0;j<3;j++){
    const z=3.18-j*.26;
    svg+=shape([v(.23,z),v(.95-j*.12,z),v(.84-j*.12,z-.14),v(.12,z-.14)],ink,0);
  }
  return svg;
}
// The same places remain occupied on an ordinary day. Race weekend fills
// the space around those groups as well as admitting more through trips.
const raceClusters=fanGroups.map((group,index)=>{
  const fans=group.map(([x,y,daily],i)=>{
    const id=index*23+i,angle=rnd(id+.54)*Math.PI*2;
    return {p:[x,y],id,d:[Math.cos(angle),Math.sin(angle)],daily,phone:rnd(id+.72)<.59};
  });
  const xs=fans.map(f=>f.p[0]),ys=fans.map(f=>f.p[1]);
  const fp=rect((Math.min(...xs)+Math.max(...xs))/2,(Math.min(...ys)+Math.max(...ys))/2,
    Math.max(...xs)-Math.min(...xs)+1.9,Math.max(...ys)-Math.min(...ys)+1.9);
  return {fp,fans,draw:people=>{
    const previous=PED_SH;PED_SH='';
    const figures=people.map(({p,d,id})=>{
      if(UPX>.54){
        const dress=pedDressed(id),[x,y]=p,position=z=>[x,y,z];
        const body=stick(position(.15),position(.85),.14,dress.pants)+stick(position(.82),position(1.32),.23,SEASON.race?raceColours[id%7]:dress.shirt);
        const head=ball(position(1.59),.20,dress.skin,.25);
        return {fp:sq(x,y,.35),z1:2.4,svg:body+head+(dress.umb?shape(atZ(polygon(x,y,.75,7),2.05),dress.umb.l,.3):'')};
      }
      return SEASON.race?raceVisitor(p,d,id):pedestrian({...pedDressed(id),p,d,walked:0},0);
    });
    const shadow=fill(PED_SH,'#ad9d96');PED_SH=previous;
    return shadow+planSort(figures);
  }};
});
function plazaWalkers(parts,t){
  for(const [i,[a,b]] of meetingPaths.entries()){
    if((SEASON.haze&&i%17!==0)||(!SEASON.race&&i%3===1)||(PHONE&&i%3===2))continue;
    const dx=b[0]-a[0],dy=b[1]-a[1],len=Math.hypot(dx,dy),speed=1.08+.18*rnd(i+.8);
    const period=len/speed+1.9,clock=t+rnd(i+22.4)*2*period,back=Math.floor(clock/period)%2===1;
    const distance=Math.min(len,(clock%period)*speed),u=back?1-distance/len:distance/len;
    const d=[dx/len*(back?-1:1),dy/len*(back?-1:1)],p=[a[0]+u*dx,a[1]+u*dy];
    if(offView(sq(...p,1),0,2.8))continue;
    const id=i*19+8,dress=pedDressed(id);
    if(SEASON.race)dress.shirt=raceColours[id%7];
    parts.push(pedestrian({...dress,p,d,walked:distance},t));
  }
}
// OSM road alignments clipped to the square. Saturday afternoon access follows
// the LTA weekend plan. Kerb widths and the temporary equipment are illustrated.
const raceRoads={"track":[[176.16,-216.0],[175.87,-205.68],[173.42,-11.14],[172.62,36.09],[172.05,116.5],[170.82,176.47],[173.33,184.0]],"coleman":[[79.26,-15.59],[81.42,-12.81],[84.76,-10.19],[88.58,-8.39],[93.16,-7.45],[152.86,-6.64],[156.85,-5.33],[160.78,-2.79],[165.02,0.61]],"parliament":[[172.61,-216.0],[175.87,-205.68]],"fences":[[[180.35,-215.7],[176.82,36.15],[176.25,116.52],[175.03,175.83],[177.32,182.67]],[[171.95,-215.7],[168.42,36.06],[167.85,116.44],[166.62,176.38],[166.83,177.8],[168.8,183.7]]]};
const raceEquipment=[];
for(const line of raceRoads.fences){
  const path=measuredLane({p:line});
  for(let s=0;s<path.len;s+=15){
    const end=Math.min(s+15,path.len),start=tAt(path,s).p,finish=tAt(path,end).p;
    const dx=finish[0]-start[0],dy=finish[1]-start[1],len=Math.hypot(dx,dy);
    const at=(u,off,h)=>[start[0]+dx*u-dy*off/len,start[1]+dy*u+dx*off/len,h];
    const fp=[at(0,-.22,0),at(1,-.22,0),at(1,.22,0),at(0,.22,0)].map(p=>p.slice(0,2));
    raceEquipment.push(obj(fp,3.2,()=>{
      let svg='';
      const side=vis([-dy/len,dx/len,0])?.21:-.21;
      svg+=shape([at(0,side,0),at(1,side,0),at(1,side,.82),at(0,side,.82)],'#c1c4ba',.5);
      svg+=shape([at(0,-.21,.82),at(1,-.21,.82),at(1,.21,.82),at(0,.21,.82)],'#e0ded1',.35);
      for(let j=0;j<=5;j++)svg+=edge(at(j/5,0,.82),at(j/5,0,3.1),'#74857d',.085);
      for(const h of [.98,2.02,3.08])svg+=edge(at(0,0,h),at(1,0,h),'#84958d',.067);
      if(UPX<.33)for(let x=0;x<len;x+=.56)svg+=edge(at(x/len,0,.91),at(x/len,0,3.05),'#96a49a',.028);
      return svg;
    }));
  }
}
function closureBoard(center,tangent,width){
  const normal=[-tangent[1],tangent[0]],at=(s,z,offset=0)=>[center[0]+normal[0]*s+tangent[0]*offset,center[1]+normal[1]*s+tangent[1]*offset,z];
  const fp=[at(-width/2,0,-.26),at(width/2,0,-.26),at(width/2,0,.26),at(-width/2,0,.26)].map(p=>p.slice(0,2));
  return obj(fp,1.38,()=>{
    let svg='';
    for(const k of [-.38,.38])svg+=stick(at(width*k,.03,-.21),at(width*k,1.26),.075,'#76847f')+stick(at(width*k,.03,.21),at(width*k,.72),.07,'#76847f');
    svg+=shape([at(-width/2,.53),at(width/2,.53),at(width/2,1.16),at(-width/2,1.16)],'#f1e8d4',.5);
    for(let m=-width/2+.13;m<width/2-.60;m+=.85)svg+=shape([at(m,.56),at(m+.31,.56),at(m+.59,1.13),at(m+.28,1.13)],'#c46b54',.15);
    return svg;
  });
}
const approach=measuredLane({p:raceRoads.coleman}),closure=tAt(approach,11);
raceEquipment.push(closureBoard(closure.p,closure.d,6.2));
const parliamentApproach=measuredLane({p:raceRoads.parliament}),southClosure=tAt(parliamentApproach,3);
raceEquipment.push(closureBoard(southClosure.p,southClosure.d,3.8));

// Small planted islands are visible in the North Bridge Road exterior photo.
const frontageBeds=[[-28.12, -26.22, 0.9], [-28.39, -35.8, 0.6]].map(([x,y,length],i)=>{
  const fp=Array.from({length:12},(_,k)=>[x+.66*Math.cos(k*Math.PI/6),y+length*Math.sin(k*Math.PI/6)]);
  return obj(fp,.72,()=>{
    let svg=loft(atZ(fp,0),atZ(fp,.13),()=> '#c6bda2')+shape(atZ(fp,.13),'#859370',.24);
    const clumps=[];
    for(let j=0;j<11;j++){
      const a=j*2.4,r=.75*Math.sqrt((j+.5)/11),cx=x+.54*r*Math.cos(a),cy=y+length*r*Math.sin(a);
      const h=.26+.15*rnd(j+i*7),colour=['#7e9c72','#91a661','#a8af6d','#93a875'][(j+i)%4];
      clumps.push({at:[cx,cy,h],svg:ball([cx,cy,h],.28,soft(colour),.21)});
      if(j%3===1&&UPX<.44){
        const foliage=Array.from({length:5},(_,k)=>{const angle=k*1.257+j,dx=Math.cos(angle),dy=Math.sin(angle);
          return shape([[cx-.07*dy,cy+.07*dx,h],[cx+dx*.33,cy+dy*.33,h+.32],[cx+.07*dy,cy-.07*dx,h]],'#9dad75',.17)}).join('');
        clumps.push({at:[cx,cy,h+.16],svg:foliage});
      }
    }
    return svg+byDepth(clumps);
  });
});
streetFurniture.push(...frontageBeds);
const signals=SCENE.routes.filter(r=>r.kind==='car').map(r=>{const {p,d}=tAt(measuredLane(r),r.stop),north=r.name==='North Bridge Road',off=north?7.75:3.24;return {p:[p[0]-d[1]*off,p[1]+d[0]*off],d,north}});
function sgGround(){
  const top=atZ(BASE_CORNERS,0);
  let g='';
  for(const p of SCENE.lawns)g+=surface(p.r,p.church?'#d7e29a':grassColor);
  for(const p of forecourtAprons)g+=surface(p,'#e3d4bd');
  for(const p of SCENE.walk)g+=surface(p,'#e6d7be');
  for(const p of SCENE.paths)g+=surface(p,'#ebdfc8');
  for(const p of SCENE.roads)g+=surface(p,roadColor);
  if(SEASON.race){
    const track=measuredLane({p:raceRoads.track}),left=[],right=[];
    for(const s of track.cum){
      const {p,d}=tAt(track,s);left.push([p[0]-d[1]*4.2,p[1]+d[0]*4.2]);right.push([p[0]+d[1]*4.2,p[1]-d[0]*4.2]);
    }
    g+=clipTo(top,shape(atZ(left.concat(right.reverse()),.01),'#a09da4',.4));
  }
  g+='<pavementink/>';
  let paint='';
  for(const lane of center)for(let s=3;s<lane.len-2;s+=7.4){
    const {p,d}=tAt(lane,s);if(Math.hypot(p[0]+15,p[1]+10)>12)paint+=stripeAt(p,d,2.9,.16);
  }
  for(const lane of crossing)for(let s=.4;s<lane.len;s+=1.13){const {p,d}=tAt(lane,s);paint+=stripeAt(p,d,.46,2.4)}
  g+=fill(paint,'#f4ead3');
  let sh='';
  const shadow=(ring,h)=>castShadow([...atZ(ring,0),...atZ(ring,h)]);
  for(const m of models)if(!(entranceView&&m.fp===findBuilding('adelphi').ring))sh+=shadow(m.fp,m.fp===cathedral?16:m.h>=45?18:m.h);
  for(const [id,h] of [['257193902',111],['44414530',84],['334127049',84],['699175600',48.3],['699175601',48.3],['699175606',51.9]])sh+=shadow(findBuilding(id).ring,h);
  for(const tr of TREES)sh+=castShadow([...atZ(sq(tr.x,tr.y,.35),0),...atZ(polygon(tr.x,tr.y,tr.ext*.72,10),tr.h*.68)]);
  const walls=BASE_CORNERS.map((a,i)=>{const b=BASE_CORNERS[(i+1)%BASE_CORNERS.length],n=norm([b[1]-a[1],a[0]-b[0],0]);
    return {at:[(a[0]+b[0])/2,(a[1]+b[1])/2,0],svg:vis(n)?shape([[...a,-SLAB],[...b,-SLAB],[...b,0],[...a,0]],tone(n,soft('#d8c5a3')),.7):''};
  });
  return byDepth(walls)+shape(top,'#eddfc9',.75)+clipTo(top,g+'<g opacity="'+(SEASON.wet?'.18':SEASON.haze?'.14':'.45')+'">'+sh+'</g>');
}
function paintSingaporeGround(ctx){
  const X=Dv(1,0,0),Y=Dv(0,1,0),o=P(0,0,0);
  ctx.save();ctx.transform(...X,...Y,...o);
  function onRings(groups,draw){
    ctx.save();ctx.beginPath();for(const rings of groups)for(const r of rings){ctx.moveTo(...r[0]);for(let i=1;i<r.length;i++)ctx.lineTo(...r[i]);ctx.closePath()}ctx.clip('evenodd');draw();ctx.restore();
  }
  onRings(SCENE.walk.concat(SCENE.paths,forecourtAprons),()=>{
    // square concrete paving slabs, each a slightly different tone, with fine joints (April 2026-11-20: richer pavements; illustrative).
    // One 16 x 16 patch is drawn once and repeated: a single fill, not a rectangle per slab on every redraw.
    const h=.9,ppm=40,n=16;let cv=self.__sgPave;
    if(!cv){cv=self.__sgPave=new OffscreenCanvas(h*ppm*n,h*ppm*n);const g=cv.getContext('2d'),base='#e6d7be',tones=[mix(base,'#ffffff',.08),base,mix(base,'#6f655c',.07),mix(base,'#cdbf9f',.12)],t=h*ppm;
      for(let a=0;a<n;a++)for(let b=0;b<n;b++){g.fillStyle=tones[Math.floor(rnd((a*n+b)*2.91+.3)*4)%4];g.fillRect(a*t,b*t,t,t)}
      g.strokeStyle='#bfb19b';g.lineWidth=1.4;g.beginPath();for(let a=0;a<n;a++){g.moveTo(a*t+.5,0);g.lineTo(a*t+.5,n*t);g.moveTo(0,a*t+.5);g.lineTo(n*t,a*t+.5)}g.stroke()}
    ctx.save();ctx.scale(1/ppm,1/ppm);ctx.fillStyle=ctx.createPattern(cv,'repeat');ctx.fillRect(-218*ppm,-216*ppm,400*ppm,404*ppm);ctx.restore();
  });
  // Keep the pedestrian route clear. The granite margins, drainage slots and
  // tactile landings are illustrative finishes on the mapped pavements.
  for(const groups of [SCENE.walk,forecourtAprons])onRings(groups,()=>{
    for(const tr of TREES){
      ctx.fillStyle='#ae9b79';ctx.fillRect(tr.x-.67,tr.y-.68,1.34,1.36);
      ctx.strokeStyle='#998d7d';ctx.lineWidth=.09;ctx.strokeRect(tr.x-.69,tr.y-.70,1.38,1.40);
      if(UPX<.42){ctx.strokeStyle='#bbaa88';ctx.lineWidth=.046;ctx.beginPath();
        for(let j=-.5;j<=.51;j+=.20){ctx.moveTo(tr.x+j,tr.y-.59);ctx.lineTo(tr.x+j,tr.y+.59)}ctx.stroke();}
    }
    for(const lane of crossing)for(const [s,sign] of [[0,-1],[lane.len,1]]){
      const {p,d}=tAt(lane,s);
      ctx.save();ctx.translate(...p);ctx.rotate(Math.atan2(d[1],d[0]));ctx.scale(sign,1);
      ctx.fillStyle='#cfb778';ctx.fillRect(.05,-.98,.81,1.96);
      if(UPX<.47){
        ctx.fillStyle='#a88b58';
        for(let i=0;i<4;i++)for(let j=0;j<11;j++){
          ctx.beginPath();ctx.arc(.15+i*.19,-.88+j*.175,.033,0,Math.PI*2);ctx.fill();
        }
      }
      ctx.restore();
    }
  });
  onRings(SCENE.lawns.filter(v=>!v.church).map(v=>v.r),()=>{
    ctx.strokeStyle='#99ae81';ctx.lineWidth=.13;ctx.beginPath();
    for(let i=0;i<(PHONE?500:1200);i++){
      let x=rnd(i+.4)*138-15,y=rnd(i+143.4)*142-5;ctx.moveTo(x-.18,y);ctx.lineTo(x,y+.29);ctx.lineTo(x+.16,y+.1);
    }ctx.stroke();
  });
  onRings(SCENE.roads,()=>{
    for(let i=0;i<(PHONE?590:1500);i++){
      const x=rnd(i+.36)*400-218,y=rnd(i+2.41)*400-216;
      ctx.fillStyle=i%2?'#c2b9bc':'#9e9ba2';ctx.fillRect(x,y,.15+rnd(i*9)*.26,.13);
    }
    ctx.lineWidth=.15;ctx.strokeStyle='#e3c477';
    for(const p of SCENE.roads)for(const r of p){
      ctx.beginPath();ctx.moveTo(...r[0]);for(const q of r.slice(1))ctx.lineTo(...q);ctx.closePath();ctx.stroke();
    }
    if(SEASON.wet){
      // Broken reflections follow each kerb, leaving the middle of each lane clear.
      for(const [j,lane] of center.entries())for(let s=2,i=0;s<lane.len-2;s+=3.6+rnd(i++ +j)*5){
        const {p,d}=tAt(lane,s),offset=(j===0?2.3:5.6)*(i%2?1:-1),seed=i+17*j;
        const x=p[0]-d[1]*offset,y=p[1]+d[0]*offset;
        ctx.save();ctx.translate(x,y);ctx.rotate(Math.atan2(d[1],d[0]));
        const length=.8+rnd(seed+5)*2.4;
        ctx.fillStyle='#a5b5bd';ctx.beginPath();ctx.ellipse(0,0,length,.27+rnd(seed)*.4,0,0,Math.PI*2);ctx.fill();
        ctx.fillStyle='#c6d4d3';ctx.fillRect(-length*.65,-.05,length*.74,.085);ctx.restore();
      }
    }
  });
  ctx.restore();
}
function scene(t){
  PED_SH='';let out=stamp('sgGround',sgGround,BASE_CORNERS,-SLAB,1);const parts=[];
  for(const [i,m] of models.entries())if(!(entranceView&&m.fp===findBuilding('adelphi').ring)&&!offView(m.fp,0,m.h))parts.push({fp:m.fp,z1:m.h,svg:stamp('sgBlock'+i,m.draw,m.fp,0,m.h+.2)});
  for(const tr of TREES){
    const fp=sq(tr.x,tr.y,tr.ext*1.4);if(offView(fp,0,tr.zTop+2))continue;
    parts.push({fp:sq(tr.x,tr.y,.48),z1:tr.zTop,svg:stamp('sgTree'+tr.i,()=>drawTree(tr.geo,{ink:PLANT_INK,inkK:INK_K,bark:'#9b795d',keep:0})+'<crown id="'+tr.i+'"/>',fp,0,tr.zTop+2)});
  }
  if(SEASON.race)for(const [i,item] of raceEquipment.entries()){
    if(!offView(item.fp,0,item.h))parts.push({fp:item.fp,z1:item.h,svg:stamp('sgRaceWorks'+i,item.draw,item.fp,0,item.h+.15)});
  }
  if(SEASON.race)for(const [i,[x,y]] of eventPoles.entries()){
    const fp=rect(x,y+.57,.34,1.42);
    if(!offView(fp,0,4.4))parts.push({fp,z1:4.4,svg:stamp('sgEventPole'+i,()=>fanPennant(x,y,i),fp,0,4.4)});
  }
  for(const [i,cluster] of raceClusters.entries()){
    if(offView(cluster.fp,0,2.9))continue;
    const people=cluster.fans.filter(f=>(SEASON.race||f.daily)&&(!PHONE||f.phone)&&(!SEASON.haze||f.id%37===0));
    if(people.length)parts.push({fp:cluster.fp,z1:SEASON.wet?2.8:2.1,svg:stamp('sgPeople'+i,()=>cluster.draw(people),cluster.fp,0,2.9)});
  }
  plazaWalkers(parts,t);
  for(const [i,item] of streetFurniture.entries())if(!offView(item.fp,0,item.h))parts.push({fp:item.fp,z1:item.h,svg:stamp('sgStreet'+i,item.draw,item.fp,0,item.h+.45)});
  for(const {p:[x,y],north} of signals){
    const green=phase(north,t),svg=stick([x,y,0],[x,y,3.6],.085,'#75877d',.5)+stick([x,y,2.9],[x,y,3.54],.20,'#4e6059',.6)+ball([x,y,green?3.00:3.48],.12,soft(green?'#6ad481':'#ed8569'),.4);
    parts.push({fp:sq(x,y,.2),z1:3.8,svg});
  }
  for(const a of TRAFFIC.to(t)){
    if(offView(sq(...a.p,3),0,3))continue;
    const part=a.kind==='car'?carDraw(a):a.kind==='bike'?bikeDraw(a,t):pedestrian(a,t);
    if(a.alpha<1)part.svg='<g opacity="'+a.alpha.toFixed(2)+'">'+part.svg+'</g>';
    parts.push(part);
  }
  if(PED_SH)out+='<path d="'+PED_SH+'" fill="#65576e" opacity=".23"/>';
  return out+planSort(parts)+(SEASON.wet?weather('rain',t,218,groundZ,(x,y)=>inside([x,y],BASE_CORNERS)):'');
}
