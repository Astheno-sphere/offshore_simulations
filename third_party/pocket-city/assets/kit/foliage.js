// Leaf sprays are small drawing planes arranged in a volume. The plane faces the reader,
// while its height, position and illumination stay attached to the registered tree.
function makeSprays(tr){
  const fm=TREE_FORM[tr.style],H=tr.h,count=PHONE?24:43,sprays=[];
  const seed=tr.i*172.3+4.2, width=H*fm.w, zMid=tr.base+H*.672;
  for(let i=0;i<count;i++){
    const v=(i+.5)/count*2-1,a=i*2.39996323+rnd(seed)*6.28+(rnd(seed+i*9)-.5)*.33;
    const n=norm([Math.cos(a)*Math.sqrt(1-v*v),Math.sin(a)*Math.sqrt(1-v*v),v]);
    const girth=width*(.80+.11*rnd(seed+i*13))*(1+(fm.vase||0)*(v-.1));
    const c=[tr.x+n[0]*girth+width*.07*v,tr.y+n[1]*girth,tr.base+H*(.672+.248*v)];
    const r=width*(PHONE?.39:.295)*(.88+.21*rnd(seed+i+.7)),ry=H*(PHONE?.111:.087)*(.92+.14*rnd(seed+i+.5));
    const outline=new Path2D(),accent=new Path2D(),points=[];
    const lobes=tr.style===3?7:tr.style===4?11:9;
    for(let k=0;k<lobes*2;k++){
      const a=k*Math.PI/lobes, b=k%2?(.74+.14*rnd(seed+i*97+k)):(.98+.13*rnd(seed+i+k));
      points.push([Math.cos(a)*b,Math.sin(a)*b]);
    }
    const last=points.at(-1),first=points[0];outline.moveTo((last[0]+first[0])/2,(last[1]+first[1])/2);
    for(let k=0;k<points.length;k++){const u=points[k],v=points[(k+1)%points.length];outline.quadraticCurveTo(...u,(u[0]+v[0])/2,(u[1]+v[1])/2)}
    outline.closePath();
    for(let j=0;j<(PHONE?2:4);j++){
      const x=(rnd(seed+i*7+j)-.5)*1.2,y=(rnd(seed+i+j*21)-.5)*1.05,dx=(j%2?1:-1)*.22;
      accent.moveTo(x,y);accent.quadraticCurveTo(x+dx*.18,y-.19,x+dx,y-.18);accent.quadraticCurveTo(x+dx*.87,y-.01,x,y);accent.closePath();
    }
    sprays.push({c,n,r,ry,outline,accent,tilt:(rnd(seed+i*4)-.5)*.57,j:rnd(seed+i*23.2),k:rnd(seed+i*18.1)});
  }
  return sprays;
}
function paintCrown(ctx,index){
  const tr=TREES[index],look=treeLook(tr);if(!look.keep)return;
  const sprays=tr.sprays||(tr.sprays=makeSprays(tr));
  const size=.74+.26*look.keep;
  const order=sprays.filter(s=>s.k<.56+.44*look.keep).sort((a,b)=>dot(a.c,CAM_V)-dot(b.c,CAM_V));
  for(const s of order){
    const pal=look.m2&&s.j<look.share?look.m2:look.m||tr.m;
    const light=dot(s.n,SUN)+.19*(s.j-.5);
    const shade=light>.4?mix(pal.l,'#fff1c4',.12):light>-.05?pal.l:light>-.43?mix(pal.m,'#86768b',.13):mix(pal.d,'#776c80',.18);
    const XY=P(...s.c),rx=s.r*size*CAM_K,ry=s.ry*size*CAM_K;
    ctx.save();ctx.translate(...XY);ctx.rotate(s.tilt);ctx.scale(rx,ry);
    ctx.fillStyle=shade;ctx.fill(s.outline);
    if(rx/UPX>4.5){ctx.strokeStyle=mix(shade,'#585156',.32);ctx.lineWidth=.46*UPX/Math.max(rx,ry);ctx.stroke(s.outline);}   // no outline on a spray only a few pixels wide: it cannot be seen, and it doubles the drawing
    if(rx/UPX>5){ctx.fillStyle=mix(shade,light<0?'#726365':'#fff4c7',.24);ctx.fill(s.accent)}
    ctx.restore();
  }
}
