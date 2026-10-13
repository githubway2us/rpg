/* ============================================================
   LUMIVARA TOWN — ฉากเมืองหลวง (วาดบน canvas เดิม 800×600)
   ============================================================ */
const TownScene=(()=>{
"use strict";
if(!CanvasRenderingContext2D.prototype.roundRect){
  CanvasRenderingContext2D.prototype.roundRect=function(x,y,w,h,r){r=Math.min(r,w/2,h/2);
    this.moveTo(x+r,y);this.arcTo(x+w,y,x+w,y+h,r);this.arcTo(x+w,y+h,x,y+h,r);
    this.arcTo(x,y+h,x,y,r);this.arcTo(x,y,x+w,y,r);this.closePath();return this;};
}
const W=1600,H=1200;
let t=0,petals=[];
const cam={x:0,y:0};

/* ---------- ข้อมูลแผนที่ ---------- */
const labels=[
  {t:'ปราสาทหลวง',x:800,y:238},{t:'ลานน้ำพุ',x:800,y:540},{t:'ลานเมือง',x:800,y:1006}];
const signs=[           // ป้ายร้าน → เชื่อม openShop ผ่าน Hooks
  {icon:'🧺',t:'ตลาด',x:262,y:660,shop:'market'},
  {icon:'🧪',t:'ร้านยา',x:1298,y:566,shop:'potion'},
  {icon:'🏦',t:'ธนาคาร',x:1444,y:706,shop:'bank'},
  {icon:'⚒️',t:'ร้านฟอร์จวัน',x:206,y:908,shop:'forge'},
  {icon:'🏺',t:'ฟอร์จของโบราณ',x:1330,y:968,shop:'antique'}];
const npcs=[
  {id:'captain',name:'ท่านกัปตัน',x:610,y:724,hair:'#4a2c17',cloth:'#e67e22',quest:1},
  {id:'keeper',name:'ผู้ดูแลเควส',x:1046,y:648,hair:'#7a1f3d',cloth:'#e91e63',quest:1},
  {id:'guard1',name:'ทหารรักษาการ',x:688,y:436,hair:'#263238',cloth:'#607d8b'},
  {id:'guard2',name:'ทหารรักษาการ',x:912,y:436,hair:'#263238',cloth:'#607d8b'}];
const portals=[
  {t:'เข้าปราสาท',x:800,y:306,w:140,h:30,to:'castle'},
  {t:'ทุ่งร้างลัก',x:800,y:1164,w:220,h:30,to:'field'}];
const solid=[
  {x:430,y:0,w:740,h:268},{x:52,y:470,w:352,h:340},{x:1120,y:352,w:352,h:216},
  {x:1284,y:560,w:300,h:280},{x:36,y:756,w:312,h:266},{x:1112,y:844,w:416,h:240},
  {x:700,y:556,w:200,h:196}];
const deco=[            // ผู้เล่นตัวประกอบ (เดินสุ่ม)
  {name:'Zeroth',x:430,y:700,hair:'#101418',cloth:'#455a64'},
  {name:'FireBlade',x:760,y:890,hair:'#c62828',cloth:'#b71c1c'},
  {name:'MoonLight',x:1010,y:862,hair:'#eceff1',cloth:'#5e35b1'},
  {name:'Euna',x:1150,y:694,hair:'#8d6e63',cloth:'#00897b'},
  {name:'FryoRhydon',x:640,y:822,hair:'#546e7a',cloth:'#0277bd'},
  {name:'Sakura',x:1084,y:760,hair:'#f48fb1',cloth:'#d81b60'}];
deco.forEach(p=>{p.tx=p.x;p.ty=p.y;p.wait=Math.random()*3;p.face=1});

/* ---------- อัปเดต ---------- */
function update(dt,player){
  t+=dt;
  deco.forEach(p=>{
    if(p.wait>0){p.wait-=dt;return;}
    const dx=p.tx-p.x,dy=p.ty-p.y,d=Math.hypot(dx,dy);
    if(d<8){
      p.tx=560+Math.random()*480; p.ty=470+Math.random()*600;
      if(blocked(p.tx,p.ty)){p.tx=p.x;p.ty=p.y;}
      p.wait=1+Math.random()*4;
    }else{
      const nx=p.x+dx/d*48*dt,ny=p.y+dy/d*48*dt;
      if(!blocked(nx,p.y))p.x=nx; if(!blocked(p.x,ny))p.y=ny;
      p.face=dx>=0?1:-1;
    }});
  cam.x=Math.max(0,Math.min(W-800,player.x-400));
  cam.y=Math.max(0,Math.min(H-600,player.y-300));
  if(Math.random()<0.10)petals.push({x:cam.x+Math.random()*800,y:cam.y-12,v:26+Math.random()*26,ph:Math.random()*6});
  petals.forEach(s=>{s.y+=s.v*dt;s.x+=Math.sin(s.y/36+s.ph)*20*dt;});
  petals=petals.filter(s=>s.y<cam.y+640);
  if(petals.length>140)petals.splice(0,petals.length-140);
}
function blocked(x,y,r=14){
  for(const s of solid) if(x>s.x-r&&x<s.x+s.w+r&&y>s.y-r&&y<s.y+s.h+r)return true;
  return false;
}
function nearest(player){
  let best=null,bd=80;
  signs.forEach(s=>{const d=Math.hypot(s.x-player.x,s.y-40-player.y);if(d<bd){bd=d;best={type:'shop',data:s}}});
  npcs.forEach(n=>{const d=Math.hypot(n.x-player.x,n.y-player.y);if(d<bd){bd=d;best={type:'npc',data:n}}});
  return best;
}

/* ---------- ตัวช่วยวาด ---------- */
function rr(c,x,y,w,h,r){c.beginPath();c.roundRect(x,y,w,h,r);}
function pill(c,x,y,txt,icon,fs=13,bg='rgba(10,20,44,.88)',bc='rgba(130,175,255,.9)',fg='#fff'){
  c.font=`600 ${fs}px Kanit, sans-serif`;
  const w=c.measureText(txt).width+(icon?fs+10:0)+24,h=fs+14;
  c.fillStyle=bg;c.strokeStyle=bc;c.lineWidth=1.5;
  c.beginPath();c.roundRect(x-w/2,y-h/2,w,h,h/2);c.fill();c.stroke();
  c.fillStyle=fg;c.textAlign='center';c.textBaseline='middle';
  c.fillText((icon?icon+'  ':'')+txt,x,y+1);
}
function roofTri(c,x,y,w,col){
  c.fillStyle=col;c.beginPath();c.moveTo(x-16,y+10);c.lineTo(x+w/2,y-26);c.lineTo(x+w+16,y+10);c.closePath();c.fill();
  c.fillStyle='rgba(255,255,255,.18)';c.beginPath();c.moveTo(x+w/2,y-26);c.lineTo(x+w+16,y+10);c.lineTo(x+w/2,y+10);c.closePath();c.fill();
}
function tree(c,x,y,s=1,pink=false){
  c.fillStyle='#6d4c2f';c.fillRect(x-6*s,y-34*s,12*s,34*s);
  const cs=pink?['#e786b0','#f39ec2','#f9c1d8']:['#2f7a33','#43a047','#66bb6a'];
  c.fillStyle=cs[0];c.beginPath();c.arc(x,y-58*s,36*s,0,7);c.fill();
  c.fillStyle=cs[1];c.beginPath();c.arc(x-15*s,y-66*s,27*s,0,7);c.arc(x+17*s,y-62*s,25*s,0,7);c.fill();
  c.fillStyle=cs[2];c.beginPath();c.arc(x-4*s,y-76*s,18*s,0,7);c.fill();
}
function lamp(c,x,y){
  c.fillStyle='#3a4750';c.fillRect(x-3,y-58,6,58);
  const g=c.createRadialGradient(x,y-66,2,x,y-66,30);
  g.addColorStop(0,'rgba(255,224,130,.85)');g.addColorStop(1,'rgba(255,224,130,0)');
  c.fillStyle=g;c.beginPath();c.arc(x,y-66,30,0,7);c.fill();
  c.fillStyle='#ffe082';rr(c,x-9,y-78,18,22,5);c.fill();
  c.strokeStyle='#3a4750';c.lineWidth=2;c.beginPath();c.roundRect(x-9,y-78,18,22,5);c.stroke();
}
function flowerbed(c,x,y,rx,ry){
  c.fillStyle='#7a5230';c.beginPath();c.ellipse(x,y,rx,ry,0,0,7);c.fill();
  const cols=['#ff5b7f','#ffd166','#7bd3ff','#c78bff'];
  for(let i=0;i<10;i++){const a=i/10*Math.PI*2;c.fillStyle=cols[i%4];
    c.beginPath();c.arc(x+Math.cos(a)*rx*.7,y+Math.sin(a)*ry*.7,4,0,7);c.fill();}
}
function bench(c,x,y){
  c.fillStyle='#7a4a21';c.fillRect(x-24,y-10,48,5);c.fillRect(x-24,y-2,48,5);
  c.fillRect(x-22,y-4,5,10);c.fillRect(x+17,y-4,5,10);
}
function house(c,x,y,w,h,roof,wall){
  c.fillStyle=wall;rr(c,x,y,w,h,6);c.fill();
  c.fillStyle='rgba(0,0,0,.12)';c.fillRect(x,y+h-10,w,10);
  roofTri(c,x-6,y,w+12,roof);
  c.fillStyle='#ffe082';c.globalAlpha=.9;
  rr(c,x+w*.16,y+h*.28,18,20,4);c.fill();rr(c,x+w*.66,y+h*.28,18,20,4);c.fill();
  c.globalAlpha=1;
}
function awning(c,x,y,w,col){
  const n=Math.round(w/22);
  for(let i=0;i<n;i++){c.fillStyle=i%2?col:'#f7f3e8';
    c.beginPath();c.roundRect(x+i*w/n,y,w/n+1,18,4);c.fill();
    c.beginPath();c.arc(x+(i+.5)*w/n,y+18,w/n/2,0,Math.PI);c.fill();}
}
function stall(c,x,y,col){
  c.fillStyle='#8d5a2b';rr(c,x,y+18,92,30,4);c.fill();
  c.fillStyle='#a9743b';c.fillRect(x,y+14,92,7);
  for(let i=0;i<5;i++){c.fillStyle=i%2?col:'#f7f3e8';
    c.beginPath();c.roundRect(x-8+i*22,y-6,22,20,3);c.fill();}
  c.fillStyle='#e74c3c';c.beginPath();c.arc(x+20,y+8,7,0,7);c.fill();
  c.fillStyle='#f1c40f';c.fillRect(x+40,y+2,13,12);
  c.fillStyle='#27ae60';c.beginPath();c.arc(x+68,y+8,7,0,7);c.fill();
}
function tower(c,x,y,w,h){
  c.fillStyle='#eceaf6';rr(c,x,y,w,h,6);c.fill();
  c.fillStyle='rgba(0,0,0,.10)';c.fillRect(x,y+h-12,w,12);
  c.fillStyle='#3f5cd0';c.beginPath();
  c.moveTo(x-14,y);c.lineTo(x+w/2,y-h*.55);c.lineTo(x+w+14,y);c.closePath();c.fill();
  c.fillStyle='#ffd166';c.fillRect(x+w/2-2.5,y-h*.55-16,5,16);
  c.beginPath();c.arc(x+w/2,y-h*.55-18,7,0,7);c.fill();
  c.fillStyle='#274060';rr(c,x+w/2-8,y+16,16,26,8);c.fill();
}
function banner(c,x,y){
  c.fillStyle='#caa84c';c.fillRect(x-2,y,4,54);
  c.fillStyle='#2f4fc0';c.beginPath();
  c.moveTo(x-14,y);c.lineTo(x+14,y);c.lineTo(x+14,y+30);c.lineTo(x,y+24);c.lineTo(x-14,y+30);c.closePath();c.fill();
  c.fillStyle='#ffd166';c.beginPath();c.arc(x,y+12,5,0,7);c.fill();
}

/* ---------- องค์ประกอบฉาก ---------- */
function drawBase(c){
  const g=c.createLinearGradient(0,0,0,H);g.addColorStop(0,'#7cc654');g.addColorStop(1,'#5db03f');
  c.fillStyle=g;c.fillRect(0,0,W,H);
  c.fillStyle='rgba(50,130,55,.25)';
  for(let i=0;i<26;i++){c.beginPath();c.ellipse((i*217)%W,(i*379)%H,60,26,0,0,7);c.fill();}
  c.fillStyle='#dccfb2';
  c.fillRect(700,250,200,H-250);c.fillRect(120,600,1360,110);c.fillRect(160,830,1280,90);
  c.fillStyle='#e6dcc4';c.beginPath();c.ellipse(800,680,340,250,0,0,7);c.fill();
  c.strokeStyle='rgba(160,140,100,.45)';c.lineWidth=3;
  for(let r=80;r<=320;r+=60){c.beginPath();c.ellipse(800,680,r,r*.72,0,0,7);c.stroke();}
}
function drawCastle(c){
  house(c,452,196,250,116,'#3f5cd0','#e8e6f4');
  house(c,898,196,250,116,'#3f5cd0','#e8e6f4');
  c.fillStyle='#f0eefa';rr(c,590,128,420,190,10);c.fill();
  c.fillStyle='rgba(0,0,0,.10)';c.fillRect(590,296,420,22);
  roofTri(c,566,128,468,'#3f5cd0');
  c.fillStyle='#ffd166';c.beginPath();c.arc(800,196,20,0,7);c.fill();
  c.fillStyle='#274060';c.beginPath();c.arc(800,196,14,0,7);c.fill();
  c.strokeStyle='#fff';c.lineWidth=2.5;
  c.beginPath();c.moveTo(800,196);c.lineTo(800,187);c.moveTo(800,196);c.lineTo(807,199);c.stroke();
  tower(c,546,44,86,286);tower(c,968,44,86,286);
  banner(c,589,60);banner(c,1011,60);
  c.fillStyle='#d9d5ea';rr(c,742,296,116,96,10);c.fill();
  const g=c.createLinearGradient(0,306,0,392);
  g.addColorStop(0,'#a8f4ff');g.addColorStop(1,'#2b6cff');
  c.fillStyle=g;c.beginPath();
  c.moveTo(764,392);c.lineTo(764,338);c.arc(800,338,36,Math.PI,0);c.lineTo(836,392);c.closePath();c.fill();
  c.strokeStyle='#ffd166';c.lineWidth=4;c.stroke();
  for(let i=0;i<6;i++){const p=(t*1.3+i/6)%1;
    c.globalAlpha=(1-p)*.9;c.fillStyle='#d9fbff';
    c.beginPath();c.arc(800+Math.sin(i*2.4+t*1.5)*26,392-p*66,2.6,0,7);c.fill();}
  c.globalAlpha=1;
  for(let i=0;i<5;i++){c.fillStyle=i%2?'#d8cfba':'#cfc4ab';c.fillRect(664,392+i*16,272,16);}
  c.fillStyle='#b9a97f';c.fillRect(648,392,16,80);c.fillRect(936,392,16,80);
}
function drawShops(c){
  house(c,60,470,220,150,'#c0392b','#f3e9d2');awning(c,78,516,184,'#e74c3c');
  stall(c,120,700,'#3f6fd8');stall(c,238,668,'#e74c3c');stall(c,70,762,'#43a047');
  house(c,1120,352,352,216,'#2e7d32','#f3e9d2');
  c.fillStyle='#e1f5fe';rr(c,1268,486,56,82,8);c.fill();
  c.fillStyle='#ff7043';rr(c,1214,392,26,34,6);c.fill();
  c.fillStyle='#42a5f5';rr(c,1352,392,26,34,6);c.fill();
  house(c,1284,560,300,250,'#f9a825','#f5efdc');
  c.fillStyle='#ffd166';c.beginPath();c.arc(1434,646,26,0,7);c.fill();
  c.fillStyle='#8d6e63';c.font='800 30px Kanit';c.textAlign='center';c.textBaseline='middle';
  c.fillText('฿',1434,648);
  c.fillStyle='#6d4c41';rr(c,1394,712,80,98,8);c.fill();
  house(c,36,780,300,242,'#6d4c41','#e8dcc8');
  c.fillStyle='#5d4037';rr(c,140,946,64,76,6);c.fill();
  c.fillStyle='#ff8a50';rr(c,236,880,44,60,6);c.fill();
  house(c,1120,868,392,216,'#7b1fa2','#ead9f5');
  c.fillStyle='#4a148c';rr(c,1268,962,70,86,6);c.fill();
}
function drawProps(c){
  tree(c,110,410,1.15);tree(c,410,398,.95);tree(c,540,430,.8);
  tree(c,60,640,1.2);tree(c,350,790,1);tree(c,540,824,.9);
  tree(c,1500,330,1);tree(c,1180,318,.85);tree(c,1560,660,1.1);
  tree(c,1030,734,1.25,true);tree(c,1170,812,1.05,true);tree(c,960,934,.95,true);
  tree(c,420,1070,1.1);tree(c,700,1124,.9);tree(c,980,1070,1.05);tree(c,1240,1130,.95);
  tree(c,40,1010,1);tree(c,30,150,1.1);tree(c,1570,150,1.1);
  flowerbed(c,560,600,46,22);flowerbed(c,1040,600,46,22);
  flowerbed(c,560,760,46,22);flowerbed(c,1040,760,46,22);flowerbed(c,800,930,60,26);
  bench(c,660,778);bench(c,940,778);
  lamp(c,672,520);lamp(c,928,520);lamp(c,672,946);lamp(c,928,946);lamp(c,180,610);lamp(c,1420,620);
}
function drawFountain(c){
  const fx=800,fy=660;
  c.fillStyle='#cfd6de';c.beginPath();c.ellipse(fx,fy,110,74,0,0,7);c.fill();
  c.fillStyle='#e8edf2';c.beginPath();c.ellipse(fx,fy-6,96,62,0,0,7);c.fill();
  const wg=c.createRadialGradient(fx,fy-10,10,fx,fy,86);
  wg.addColorStop(0,'#9fe8ff');wg.addColorStop(1,'#1e88e5');
  c.fillStyle=wg;c.beginPath();c.ellipse(fx,fy-4,86,54,0,0,7);c.fill();
  c.fillStyle='#eef6fa';rr(c,fx-12,fy-92,24,64,8);c.fill();
  c.beginPath();c.ellipse(fx,fy-98,34,16,0,0,7);c.fill();
  c.strokeStyle='rgba(190,235,255,.9)';c.lineWidth=3;
  for(let i=0;i<8;i++){const a=Math.PI+i/7*Math.PI,sp=1+.15*Math.sin(t*3+i);
    c.beginPath();c.moveTo(fx,fy-92);
    c.quadraticCurveTo(fx+Math.cos(a)*60*sp,fy-110,fx+Math.cos(a)*78*sp,fy-30+Math.sin(t*4+i)*4);c.stroke();}
  for(let i=0;i<3;i++){const p=(t*.7+i/3)%1;
    c.globalAlpha=(1-p)*.5;c.strokeStyle='#dff4ff';
    c.beginPath();c.ellipse(fx,fy-4,86*p,54*p,0,0,7);c.stroke();}
  c.globalAlpha=1;
}
function chara(c,x,y,hair,cloth,face,name,quest){
  const bob=Math.sin(t*3+x*.1)*1.6;
  c.fillStyle='rgba(0,0,0,.22)';c.beginPath();c.ellipse(x,y+2,13,5,0,0,7);c.fill();
  c.fillStyle=cloth;rr(c,x-11,y-32+bob,22,30,8);c.fill();
  rr(c,x-17,y-26+bob,7,17,4);c.fill();rr(c,x+10,y-26+bob,7,17,4);c.fill();
  c.fillStyle='#ffd9b3';c.beginPath();c.arc(x,y-45+bob,12.5,0,7);c.fill();
  c.fillStyle=hair;c.beginPath();c.arc(x,y-48+bob,12.5,Math.PI*.95,Math.PI*2.05);c.fill();
  c.fillRect(x-12.5,y-50+bob,25,7);
  c.fillStyle='#222';c.beginPath();c.arc(x+(face>0?4:-4),y-45+bob,1.8,0,7);c.fill();
  if(name){c.font='600 12px Kanit, sans-serif';c.textAlign='center';c.textBaseline='alphabetic';
    c.lineWidth=3;c.strokeStyle='rgba(0,0,0,.75)';c.strokeText(name,x,y-64+bob);
    c.fillStyle='#fff';c.fillText(name,x,y-64+bob);}
  if(quest){const q=Math.sin(t*4)*4;
    c.font='800 22px Kanit, sans-serif';c.textAlign='center';
    c.lineWidth=4;c.strokeStyle='rgba(0,0,0,.7)';c.strokeText('!',x,y-86+bob+q);
    c.fillStyle='#ffd166';c.fillText('!',x,y-86+bob+q);}
}
function portalSwirl(c,x,y,w,h,name){
  const g=c.createRadialGradient(x,y,4,x,y,w/2);
  g.addColorStop(0,'rgba(190,240,255,.95)');g.addColorStop(.55,'rgba(41,121,255,.55)');g.addColorStop(1,'rgba(41,121,255,0)');
  c.fillStyle=g;c.beginPath();c.ellipse(x,y,w/2,h/2,0,0,7);c.fill();
  c.strokeStyle='rgba(140,220,255,.8)';c.lineWidth=2;
  for(let i=0;i<3;i++){const p=(t*.8+i/3)%1;
    c.globalAlpha=1-p;c.beginPath();c.ellipse(x,y,w/2*p,h/2*p,0,0,7);c.stroke();}
  c.globalAlpha=1;
  pill(c,x,y-34+Math.sin(t*3)*4,name,null,13);
  c.fillStyle='#9be7ff';c.font='700 14px Kanit';c.textAlign='center';c.textBaseline='alphabetic';
  c.fillText('▲',x,y+34);
}

/* ---------- วาดทั้งฉาก ---------- */
function draw(c,player){
  c.save();c.translate(-cam.x|0,-cam.y|0);
  drawBase(c);drawCastle(c);drawShops(c);drawProps(c);drawFountain(c);
  signs.forEach(s=>pill(c,s.x,s.y-86,s.t,s.icon,13,'rgba(10,18,40,.9)','rgba(255,209,102,.9)','#ffe9a8'));
  const near=nearest(player);
  const all=[
    ...deco.map(p=>({y:p.y,f:()=>chara(c,p.x,p.y,p.hair,p.cloth,p.face,p.name)})),
    ...npcs.map(n=>({y:n.y,f:()=>chara(c,n.x,n.y,n.hair,n.cloth,1,n.name,n.quest)})),
    {y:player.y,f:()=>chara(c,player.x,player.y,player.hair||'#222',player.cloth||'#37474f',player.face||1,player.name)}];
  all.sort((a,b)=>a.y-b.y).forEach(o=>o.f());
  if(near){const d=near.data;
    pill(c,d.x,d.y-(near.type==='shop'?116:114),'💬 กด E หรือแตะเพื่อคุย',null,12,
      'rgba(6,12,26,.92)','rgba(0,255,204,.9)','#aef7e6');}
  labels.forEach(l=>pill(c,l.x,l.y,l.t,null,15,'rgba(8,14,34,.85)','rgba(255,209,102,.95)','#ffe9a8'));
  portalSwirl(c,800,1150,200,44,'ทุ่งร้างลัก');
  c.fillStyle='#f8bbd0';
  petals.forEach(p=>{c.globalAlpha=.85;c.beginPath();c.arc(p.x,p.y,2.4,0,7);c.fill();});
  c.globalAlpha=1;
  c.restore();
}

/* ---------- มินิแมพ ---------- */
function drawMini(c,pw,ph,player){
  const sx=pw/W,sy=ph/H;
  c.clearRect(0,0,pw,ph);
  c.fillStyle='#4d8a44';c.fillRect(0,0,pw,ph);
  c.fillStyle='#d9ccab';
  c.fillRect(700*sx,250*sy,200*sx,(H-250)*sy);
  c.fillRect(120*sx,600*sy,1360*sx,110*sy);
  c.fillRect(160*sx,830*sy,1280*sx,90*sy);
  c.fillStyle='#e6dcc4';c.beginPath();c.ellipse(800*sx,680*sy,340*sx,250*sy,0,0,7);c.fill();
  const R=(x,y,w,h,col)=>{c.fillStyle=col;c.beginPath();c.roundRect(x*sx,y*sy,w*sx,h*sy,3);c.fill();};
  R(430,0,740,268,'#5b79e0');R(52,470,352,340,'#c0392b');R(1120,352,352,216,'#2e7d32');
  R(1284,560,300,280,'#f9a825');R(36,756,312,266,'#6d4c41');R(1120,844,416,240,'#7b1fa2');
  c.fillStyle='#4fc3f7';c.beginPath();c.ellipse(800*sx,660*sy,16,10,0,0,7);c.fill();
  npcs.forEach(n=>{c.fillStyle='#ff5252';c.beginPath();c.arc(n.x*sx,n.y*sy,3,0,7);c.fill();});
  c.fillStyle='#fff';c.strokeStyle='#2b6cff';c.lineWidth=2;
  c.beginPath();c.arc(player.x*sx,player.y*sy,4.5,0,7);c.fill();c.stroke();
}
return {W,H,cam,update,draw,drawMini,blocked,nearest,npcs,signs,portals,solid};
})();