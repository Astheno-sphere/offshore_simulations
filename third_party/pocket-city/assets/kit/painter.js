/* Each worker builds the same fixed-tick simulation. Its projected model uses a small vector vocabulary.
   Compile those shapes directly to Canvas paths. The DOM contains one scene canvas at every zoom. */
let frontageCutaway=false,entranceView=false;
let frameCanvas, paintTime=0, paintScale = 1, lastCameraKey = '', repeats = 0;
const stamps = new Map();
function makeSurface(w,h){return typeof OffscreenCanvas === 'function' ? new OffscreenCanvas(w,h) : Object.assign(document.createElement('canvas'),{width:w,height:h});}
function stamp(key, build, fp, z0, z1){
  if (!stamps.has(key)){
    const pts = fp.flatMap(p => [P(p[0],p[1],z0),P(p[0],p[1],z1)]);
    const xs = pts.map(p=>p[0]), ys = pts.map(p=>p[1]), pad=Math.ceil((1.5+WOBBLE*.35)*UPX*paintScale);
    const x = Math.max(0,Math.floor(Math.min(...xs)*paintScale)-pad), y = Math.max(0,Math.floor(Math.min(...ys)*paintScale)-pad);
    const w = Math.min(frameCanvas.width,Math.ceil(Math.max(...xs)*paintScale)+pad)-x, h = Math.min(frameCanvas.height,Math.ceil(Math.max(...ys)*paintScale)+pad)-y;
    const ops=w>0&&h>0?compileInk(build()):[];
    stamps.set(key,{ops,x,y,w,h});
  }
  return '<stamp id="'+key+'"/>';
}
function compileInk(markup){
  const ops=[], clips=new Map(); let clip=null;
  for(const tag of markup.matchAll(/<(\/?[A-Za-z]+)\b([^>]*)>/g)){
    const kind=tag[1], a={};
    if(kind==='/clipPath'){clip=null;continue}
    if(kind==='/g'){ops.push({kind:'pop'});continue}
    for(const attr of tag[2].matchAll(/([\w-]+)="([^"]*)"/g)) a[attr[1]]=attr[2];
    if(kind==='clipPath'){clip=new Path2D();clips.set(a.id,clip);continue}
    if(kind==='g'){ops.push({kind:'push',clip:clips.get((a['clip-path']||'').slice(5,-1)),alpha:Number(a.opacity||1)});continue}
    if(kind==='label'){ops.push({kind:'label',name:a.name,x:+a.x,y:+a.y,angle:+a.a});continue}
    if(kind==='canal'){ops.push({kind,t:+a.t});continue}
    if(kind==='rooftile'||kind==='streetfinish'){ops.push({kind,id:+a.id,sign:+a.sign});continue}
    if(kind==='archbrick'||kind==='quaybrick'){ops.push({kind,id:+a.id});continue}
    if(kind==='frontage'||kind==='laundry'||kind==='streetlight'){ops.push({kind,key:a.key});continue}
    if(kind==='treads'){ops.push({kind,lane:+a.lane});continue}
    if(kind==='sheet'){ops.push({kind,name:a.name,path:new Path2D(a.d),matrix:a.matrix.split(' ').map(Number),bounds:a.bounds.split(' ').map(Number)});continue}
    if(kind==='elevation'||kind==='pavementink'){ops.push({kind,id:+a.id});continue}
    if(kind==='beds'){ops.push({kind});continue}
    if(kind==='pavers'){ops.push({kind,id:+a.id});continue}
    if(kind==='crown'){ops.push({kind:'crown',id:+a.id});continue}
    if(kind==='face'){ops.push({kind:'face',id:+a.id});continue}
    if(kind==='stamp'){ops.push({kind:'stamp',key:a.id});continue}
    let path;
    if(kind==='path'){path=new Path2D(a.d||'')}
    else if(kind==='ellipse'||kind==='circle'){path=new Path2D();path.ellipse(+a.cx,+a.cy,Number(a.r||a.rx),Number(a.r||a.ry),0,0,Math.PI*2)}
    else continue;
    if(clip){clip.addPath(path);continue}
    const fill=a.fill==='none'?null:a.fill||null, raw=a.stroke;
    const marker=raw==='#231e15'||raw==='#231e16'||raw==='#231e17';
    const detail=marker && !fill;
    const stroke=marker ? fill ? lineOf(fill,raw===PLANT_INK) : '#5d5064' : raw;
    const style=a.style && a.style.match(/stroke-width:([\d.]+)/);
    const width=style ? +style[1] : (marker && fill ? .8 : +(a['stroke-width']||1))*INK_K;
    ops.push({kind:'shape',path,fill,stroke,width,alpha:Number(a.opacity||1),strokeAlpha:Number(a['stroke-opacity']||1)*(raw===PLANT_INK?.47:detail?.65:1),rule:a['fill-rule']||'nonzero'});
  }
  return ops;
}
function paintOps(ctx,ops){
  let opacity=ctx.globalAlpha;
  for(const op of ops){
    if(op.kind==='push'){ctx.save();if(op.clip)ctx.clip(op.clip);ctx.globalAlpha*=op.alpha;opacity=ctx.globalAlpha;continue}
    if(op.kind==='pop'){ctx.restore();opacity=ctx.globalAlpha;continue}
    if(op.kind==='canal'){paintCanal(ctx,op.t);continue}
    if(op.kind==='rooftile'){paintRoofTile(ctx,op.id,op.sign);continue}
    if(op.kind==='streetfinish'){paintStreetFinish(ctx);continue}
    if(op.kind==='archbrick'){paintBridgeBrick(ctx,op.id);continue}
    if(op.kind==='quaybrick'){paintQuayBrick(ctx);continue}
    if(op.kind==='frontage'){paintFrontage(ctx,op.key);continue}
    if(op.kind==='laundry'){paintLaundry(ctx,op.key);continue}
    if(op.kind==='streetlight'){streetLight(ctx);continue}
    if(op.kind==='treads'){paintEscalatorTreads(ctx,op.lane);continue}
    if(op.kind==='sheet'){paintSheet(ctx,op);continue}
    if(op.kind==='elevation'){paintSingaporeElevation(ctx,op.id);continue}
    if(op.kind==='pavementink'){paintSingaporeGround(ctx);continue}
    if(op.kind==='beds'){paintBeds(ctx);continue}
    if(op.kind==='pavers'){paintStreet(ctx,op.id);continue}
    if(op.kind==='crown'){paintCrown(ctx,op.id);continue}
    if(op.kind==='face'){paintFace(ctx,op.id);continue}
    if(op.kind==='label'){
      ctx.save();ctx.translate(op.x,op.y);ctx.rotate(op.angle);
      const size=Math.min(2.6,14*UPX);
      if(size/UPX>6){ctx.font='italic '+size+'px Georgia,serif';ctx.fillStyle=SEASON.ice?'#64838c':'#396f70';ctx.globalAlpha=.78;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(op.name,0,0)}
      ctx.restore();continue;
    }
    if(op.kind==='stamp'){
      const s=stamps.get(op.key);if(!s||s.w<=0||s.h<=0)continue;
      if(repeats && !s.layers){
        // Laundry moves between stationary wall and roof layers. Cache the ink on
        // either side in its original draw order, including on animated buildings.
        s.layers=[];let start=0;
        for(let i=0;i<=s.ops.length;i++){
          if(i<s.ops.length && s.ops[i].kind!=='laundry' && s.ops[i].kind!=='treads')continue;
          if(start<i){
            const raster=makeSurface(s.w,s.h),g=raster.getContext('2d');
            g.setTransform(paintScale,0,0,paintScale,-s.x,-s.y);g.lineCap=g.lineJoin='round';
            paintOps(g,s.ops.slice(start,i));s.layers.push({raster});
          }
          if(i<s.ops.length)s.layers.push(s.ops[i]);
          start=i+1;
        }
        s.ops=[];
      }
      if(s.layers)for(const layer of s.layers){
        if(layer.raster)ctx.drawImage(layer.raster,s.x/paintScale,s.y/paintScale,s.w/paintScale,s.h/paintScale);
        else if(layer.kind==='treads')paintEscalatorTreads(ctx,layer.lane);
        else paintLaundry(ctx,layer.key);
      }else paintOps(ctx,s.ops);
      continue;
    }
    if(op.fill){ctx.globalAlpha=opacity*op.alpha;ctx.fillStyle=op.fill;ctx.fill(op.path,op.rule)}
    if(op.stroke && op.width>0){ctx.globalAlpha=opacity*op.alpha*op.strokeAlpha;ctx.strokeStyle=op.stroke;ctx.lineWidth=op.width;ctx.stroke(op.path)}
    ctx.globalAlpha=opacity;
  }
}
function renderFrame(m){
  FIG_W=m.width;FIG_H=m.height;paintTime=m.time;
  const book=m.finish==='book',changed=book!==pictureBook;
  pictureBook=book;
  if(SEASON_ID!==m.season)setSeason(m.season);
  else if(changed)setGroundColours(SEASON);
  const width=Math.max(1,Math.round(FIG_W*m.dpr)),height=Math.max(1,Math.round(FIG_H*m.dpr));
  if(!frameCanvas || frameCanvas.width!==width || frameCanvas.height!==height)frameCanvas=makeSurface(width,height);
  const cm=m.camera;
  entranceView=!!m.entrance;
  frontageCutaway=!!m.frontage && cm.zoom>4.5 && Math.sin(cm.yaw*Math.PI/180)>.55;
  setCam(cm.yaw,cm.pitch); RC=[0,0];RCZ=0;OX=OY=0;
  const pixelsPerUnit=Math.min(FIG_W/302,FIG_H/202)*m.camera.zoom;
  const vbW=FIG_W/pixelsPerUnit,vbH=FIG_H/pixelsPerUnit;
  const center=P(cm.x,cm.y,cm.z);
  OX=vbW*.5-center[0];OY=vbH*.50-center[1];
  VIEW_BOX=[vbW,vbH];INK_K=.83/pixelsPerUnit;UPX=1/pixelsPerUnit;WOBBLE=m.wobble;
  paintScale=width/vbW;pathPrecision=paintScale>16?1000:100;
  washEnabled=pictureBook||m.finish==='wash';
  const key=[width,height,cm.yaw,cm.pitch,cm.x,cm.y,cm.z,cm.zoom,WOBBLE,m.season,m.finish,frontageCutaway,entranceView].join(',');
  if(key!==lastCameraKey){stamps.clear();repeats=0;lastCameraKey=key}else repeats++;
  const g=frameCanvas.getContext('2d');g.setTransform(1,0,0,1,0,0);g.clearRect(0,0,width,height);
  g.setTransform(paintScale,0,0,paintScale,0,0);g.lineCap=g.lineJoin='round';
  // A print-style contact shadow belongs to the cutaway model, outside its measured terrain.
  for(let i=6;i>0;i--){
    const corners=BASE_CORNERS.map(([x,y])=>P(x*(1+i*.003),y*(1+i*.003),-SLAB-1-i*.3));
    g.fillStyle='rgba(87,78,91,.028)';g.beginPath();corners.forEach(([x,y],j)=>j?g.lineTo(x,y):g.moveTo(x,y));g.closePath();g.fill();
  }
  _clipN=0;
  paintOps(g,compileInk(scene(m.time)));
  if(SEASON.haze){
    g.save();g.globalCompositeOperation='source-atop';g.fillStyle='rgba(224,207,176,.38)';
    g.fillRect(0,0,vbW,vbH);g.restore();
  }
  const north=Dv(...NORTH);
  return {angle:Math.atan2(north[1],north[0])*180/Math.PI+90,scale:20*CAM_K*pixelsPerUnit,bitmap:frameCanvas.transferToImageBitmap ? frameCanvas.transferToImageBitmap() : frameCanvas};
}
setLight(112);
