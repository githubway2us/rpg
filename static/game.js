/* ===== FIT TO SCREEN (Mobile = FULL, Desktop = scale) ===== */
const BASE_W=800,BASE_H=600;
const IS_MOBILE=('ontouchstart' in window)||navigator.maxTouchPoints>0
  ||matchMedia('(pointer:coarse)').matches;

function fitToScreen(){
  const wrap=document.getElementById('game-wrapper');
  if(!wrap||wrap.style.display==='none')return;
  const vv=window.visualViewport;
  const vw=vv?vv.width:window.innerWidth;
  const vh=vv?vv.height:window.innerHeight;

  if(IS_MOBILE){
    /* 📱 มือถือ → เต็มจอทุกด้านเสมอ */
    wrap.style.width=vw+'px';
    wrap.style.height=vh+'px';
    wrap.style.transform='none';
    wrap.style.borderRadius='0';
  }else{
    /* 🖥️ คอม → ขยายสูงสุดโดยไม่บิดสัดส่วน */
    const s=Math.min(vw/BASE_W,vh/BASE_H);
    wrap.style.width=BASE_W+'px';
    wrap.style.height=BASE_H+'px';
    wrap.style.transform='scale('+s+')';
  }
}

window.addEventListener('resize',fitToScreen);
window.addEventListener('orientationchange',()=>setTimeout(fitToScreen,250));
if(window.visualViewport)window.visualViewport.addEventListener('resize',fitToScreen);
window.addEventListener('load',fitToScreen);

/* 🔓 ขอ Fullscreen จริงตอนแตะจอครั้งแรก (ทำงานบน Android/Chrome) */
document.addEventListener('touchstart',function once(){
  if(!document.fullscreenElement){
    const el=document.documentElement;
    const req=el.requestFullscreen||el.webkitRequestFullscreen;
    if(req){const p=req.call(el);if(p&&p.catch)p.catch(()=>{});}
  }
  fitToScreen();
  document.removeEventListener('touchstart',once);
},{once:true});

document.addEventListener('fullscreenchange',()=>setTimeout(fitToScreen,120));
// ================= STATE =================
let isRegisterMode=false,socket=null,myData=null,allPlayers={};
const moveSpeed=3.4,ATTACK_RANGE=120;
let currentChatTab='all',chatHistory=[];
let autoBotActive=false,myInventory=[],SKILLS={};
let monsters={},groundItems={},NPCS_STATE={};
let moveTarget=null,chaseId=null,pendingAttackId=null,walkNPCId=null,walkPickupId=null;
let keys={},dpadDir={x:0,y:0},lastMoveSent=0,atkCdUntil=0,selfSynced=false;
let joinSentThisConn=false,kicked=false;
let autoLoot=true,autoSell=false,shopTab='buy';
let botState='farm',botHomeMap='forest',botBusy=false,lastRestockAt=0,lastSellAt=0;
let botDeathAt=0,botLastPot=0,botLastSkill=0;
let MAPS_META=[],MAP_LABELS={};
let MK={open:false,price:1000,hist:[],position:null,orders:[],lastPrice:1000};
const canvas=document.getElementById('gameCanvas');
const ctx=canvas.getContext('2d');
const JOB_ICONS={Novice:'🌱',Swordsman:'⚔️',Mage:'🔮',Archer:'🏹',Thief:'🗡️',Acolyte:'✝️',Knight:'🛡️',Wizard:'🧙',Hunter:'🎯',Assassin:'🥷',Priest:'📜',Warrior:'⚔️'};
const SKILL_ICONS={single:'🗡️',aoe:'💥',heal:'💚',buff:'⭐'};
const KILL_WORDS=['K.O.!','DESTROYED!','สวยงาม!','หมดลม!','SPLAT!'];

// ================= SOUND ENGINE (Web Audio API — สังเคราะห์เสียงสด) =================
const SND = {
  ctx: null,
  master: null,
  musicGain: null,
  enabled: true,
  volume: 0.6,
  musicOn: true,
  _mtimer: null,

  init() {
    if (this.ctx) return;
    try {
      this.ctx = new (window.AudioContext || window.webkitAudioContext)();
      this.master = this.ctx.createGain();
      this.master.gain.value = this.volume;
      this.master.connect(this.ctx.destination);

      this.musicGain = this.ctx.createGain();
      this.musicGain.gain.value = 0.22; // ดังขึ้นชัดเจน
      this.musicGain.connect(this.master);

      this.startMusic();
    } catch (e) {
      console.warn('Audio init failed', e);
    }
  },

  resume() {
    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
  },

  setVolume(v) {
    this.volume = v;
    if (this.master) this.master.gain.value = v;
    const lb = document.getElementById('snd-vol-label');
    if (lb) lb.textContent = Math.round(v * 100) + '%';
  },

  tone(freq, dur, type = 'sine', vol = 0.5, slideTo = null, delay = 0) {
    if (!this.ctx || !this.enabled) return;
    try {
      const t = this.ctx.currentTime + delay;
      const o = this.ctx.createOscillator();
      const g = this.ctx.createGain();
      o.type = type;
      o.frequency.setValueAtTime(freq, t);
      if (slideTo) o.frequency.exponentialRampToValueAtTime(Math.max(1, slideTo), t + dur);
      g.gain.setValueAtTime(vol, t);
      g.gain.exponentialRampToValueAtTime(0.001, t + dur);
      o.connect(g);
      g.connect(this.master);
      o.start(t);
      o.stop(t + dur + 0.02);
    } catch (e) {}
  },

  noise(dur, vol = 0.4, filterFreq = 800, delay = 0) {
    if (!this.ctx || !this.enabled) return;
    try {
      const t = this.ctx.currentTime + delay;
      const len = Math.max(1, Math.floor(this.ctx.sampleRate * dur));
      const buf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
      const data = buf.getChannelData(0);
      for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / len);
      const src = this.ctx.createBufferSource();
      src.buffer = buf;
      const f = this.ctx.createBiquadFilter();
      f.type = 'lowpass';
      f.frequency.value = filterFreq;
      const g = this.ctx.createGain();
      g.gain.setValueAtTime(vol, t);
      g.gain.exponentialRampToValueAtTime(0.001, t + dur);
      src.connect(f);
      f.connect(g);
      g.connect(this.master);
      src.start(t);
    } catch (e) {}
  },

  // ---- เสียงเอฟเฟกต์ ----
  hit() { this.noise(0.08, 0.32, 2500); this.tone(180, 0.1, 'square', 0.22, 80); },
  crit() { this.noise(0.12, 0.45, 3000); this.tone(320, 0.15, 'sawtooth', 0.28, 120); this.tone(660, 0.12, 'square', 0.18, 220, 0.03); },
  miss() { this.tone(500, 0.08, 'sine', 0.15, 900); },
  kill() { this.tone(400, 0.3, 'sawtooth', 0.28, 60); this.noise(0.25, 0.35, 1200); },
  hurt() { this.tone(140, 0.18, 'sawtooth', 0.32, 70); this.noise(0.1, 0.22, 600); },
  potion() { this.tone(300, 0.08, 'sine', 0.28, 500); this.tone(500, 0.08, 'sine', 0.28, 700, 0.08); this.tone(700, 0.12, 'sine', 0.28, 900, 0.16); },
  heal() { [523, 659, 784].forEach((f, i) => this.tone(f, 0.2, 'sine', 0.2, null, i * 0.07)); },
  buff() { this.tone(220, 0.3, 'sawtooth', 0.18, 440); this.tone(330, 0.3, 'sine', 0.14, 660, 0.05); },
  skill() { this.noise(0.15, 0.28, 4000); this.tone(500, 0.2, 'sine', 0.22, 150); },
  levelup() { [523, 659, 784, 1047].forEach((f, i) => this.tone(f, 0.25, 'triangle', 0.28, null, i * 0.09)); },
  pickup() { this.tone(880, 0.08, 'sine', 0.22); this.tone(1320, 0.12, 'sine', 0.22, null, 0.07); },
  buy() { this.tone(700, 0.07, 'square', 0.22); this.tone(1050, 0.1, 'square', 0.22, null, 0.08); },
  sell() { this.tone(1050, 0.07, 'square', 0.22); this.tone(700, 0.1, 'square', 0.22, null, 0.08); },
  death() { [392, 330, 262, 196].forEach((f, i) => this.tone(f, 0.4, 'triangle', 0.28, null, i * 0.18)); },
  respawn() { [262, 392, 523, 784].forEach((f, i) => this.tone(f, 0.2, 'sine', 0.22, null, i * 0.08)); },
  click() { this.tone(600, 0.04, 'square', 0.12); },
  slam() { this.noise(0.5, 0.55, 300); this.tone(80, 0.5, 'sine', 0.45, 30); },
  enrage() { this.noise(0.4, 0.45, 500); this.tone(120, 0.4, 'sawtooth', 0.28, 60); },
  trade() { this.tone(880, 0.06, 'sine', 0.22); this.tone(1174, 0.06, 'sine', 0.22, null, 0.06); this.tone(1568, 0.1, 'sine', 0.22, null, 0.12); },
  quest() { [659, 784, 988].forEach((f, i) => this.tone(f, 0.18, 'triangle', 0.22, null, i * 0.08)); },
  jobchange() { [523, 659, 784, 1047, 1319].forEach((f, i) => this.tone(f, 0.3, 'triangle', 0.26, null, i * 0.1)); this.noise(0.4, 0.18, 2000, 0.2); },
  travel() { this.noise(0.3, 0.22, 1000); this.tone(200, 0.25, 'sine', 0.18, 600); },
  msg() { this.tone(900, 0.05, 'sine', 0.1); },

  // ---- เพลงพื้นหลัง (เวอร์ชันดัง + สนุก) ----
  startMusic() {
    if (this._mtimer) return;

    const chords = [
      [220.00, 261.63, 329.63, 440.00], // Am
      [174.61, 220.00, 261.63, 349.23], // F
      [261.63, 329.63, 392.00, 523.25], // C
      [196.00, 246.94, 293.66, 392.00]  // G
    ];

    const pattern = [1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1];

    let step = 0;
    let chordIdx = 0;

    this._mtimer = setInterval(() => {
      // บังคับ resume ทุกครั้ง (สำคัญมาก)
      if (this.ctx && this.ctx.state === 'suspended') {
        this.ctx.resume();
      }

      if (!this.ctx || !this.enabled || !this.musicOn) return;

      try {
        const t = this.ctx.currentTime;
        const chord = chords[chordIdx];

        // เบส
        if (step % 4 === 0) {
          const bass = this.ctx.createOscillator();
          const bg = this.ctx.createGain();
          bass.type = 'sine';
          bass.frequency.value = chord[0] / 2;
          bg.gain.setValueAtTime(0.0001, t);
          bg.gain.exponentialRampToValueAtTime(0.55, t + 0.04);
          bg.gain.exponentialRampToValueAtTime(0.0001, t + 0.6);
          bass.connect(bg);
          bg.connect(this.musicGain);
          bass.start(t);
          bass.stop(t + 0.65);
        }

        // เมโลดี้
        if (pattern[step % pattern.length]) {
          const noteIdx = step % chord.length;
          const freq = chord[noteIdx] * (step % 16 >= 10 ? 2 : 1);

          const o = this.ctx.createOscillator();
          const g = this.ctx.createGain();
          o.type = (step % 8 === 3) ? 'triangle' : 'sine';
          o.frequency.value = freq;

          g.gain.setValueAtTime(0.0001, t);
          g.gain.exponentialRampToValueAtTime(0.28, t + 0.03);
          g.gain.exponentialRampToValueAtTime(0.0001, t + 0.35);

          o.connect(g);
          g.connect(this.musicGain);
          o.start(t);
          o.stop(t + 0.38);
        }

        // ไฮแฮท
        if (step % 2 === 1) {
          const noise = this.ctx.createBufferSource();
          const buffer = this.ctx.createBuffer(1, this.ctx.sampleRate * 0.04, this.ctx.sampleRate);
          const data = buffer.getChannelData(0);
          for (let i = 0; i < data.length; i++) {
            data[i] = (Math.random() * 2 - 1) * (1 - i / data.length);
          }
          noise.buffer = buffer;

          const filter = this.ctx.createBiquadFilter();
          filter.type = 'highpass';
          filter.frequency.value = 6000;

          const ng = this.ctx.createGain();
          ng.gain.setValueAtTime(0.07, t);
          ng.gain.exponentialRampToValueAtTime(0.0001, t + 0.04);

          noise.connect(filter);
          filter.connect(ng);
          ng.connect(this.musicGain);
          noise.start(t);
        }

        step++;
        if (step % 16 === 0) {
          chordIdx = (chordIdx + 1) % chords.length;
        }
      } catch (e) {}
    }, 280);
  }
};

// เริ่มเสียงเมื่อผู้เล่นแตะจอครั้งแรก
document.addEventListener('pointerdown', () => {
  SND.init();
  SND.resume();
});

// เสียงคลิกปุ่ม UI
document.addEventListener('pointerdown', e => {
  const b = e.target.closest('.menu-btn,.close-btn,.action-btn,.action-btn-sm,.chat-tab,.switch-toggle,.auth-btn,.mk-btns button,#chat-send,#attack-action-btn,.quick-slot');
  if (b) SND.click();
}, true);

// ================= FX ENGINE =================
const FX={shake:{t:0,dur:0,power:0},hitstop:0,zoom:0,white:0,
particles:[],floaters:[],rings:[],slashes:[],shocks:[],ambient:[],combo:{n:0,last:0}};
for(let i=0;i<26;i++)FX.ambient.push({x:Math.random()*800,y:Math.random()*600,s:.4+Math.random()*1.4,v:4+Math.random()*10,a:.06+Math.random()*.16});
function doShake(p,d){const s=FX.shake;if(s.t<=0||p>=s.power){s.power=p;s.dur=d;s.t=d;}}
function whiteFlash(a){FX.white=Math.max(FX.white,a);}
function hitstop(t){FX.hitstop=Math.max(FX.hitstop,t);}
function zoomPunch(z){FX.zoom=Math.min(.14,FX.zoom+z);}
function vignetteHurt(){const v=document.getElementById('fx-vignette');v.classList.remove('lowhp');v.classList.add('hurt');
setTimeout(()=>{v.classList.remove('hurt');checkLowHP();},160);}
function checkLowHP(){const v=document.getElementById('fx-vignette');
if(myData&&myData.hp>0&&myData.hp<myData.maxHp*.3)v.classList.add('lowhp');else v.classList.remove('lowhp');}
function floatText(x,y,txt,color,size=16,crit=false){FX.floaters.push({x,y,txt,color,size,life:1,vy:-52,vx:(Math.random()-.5)*24,crit});}
function spawnParticles(x,y,color,n=10,pow=1){for(let i=0;i<n;i++){const a=Math.random()*6.283,s=(70+Math.random()*190)*pow;
FX.particles.push({x,y,vx:Math.cos(a)*s,vy:Math.sin(a)*s-40*pow,life:.45+Math.random()*.5,max:.9,size:1.5+Math.random()*3*pow,color,grav:280});}}
function ring(x,y,max,color,lw=3){FX.rings.push({x,y,r:8,max,color,lw,life:1});}
function shock(x,y,max,color='#fff'){FX.shocks.push({x,y,r:6,max,color,life:1});}
function slashAt(x,y,big=false){const n=big?3:1;for(let i=0;i<n;i++)FX.slashes.push({x,y,ang:Math.random()*6.283,len:big?46:30,life:1,dec:3.2+i*.8,w:big?5:3,color:big?'#ffd166':'#fff'});}
function comboKill(){const now=performance.now();FX.combo.n=(now-FX.combo.last<4000)?FX.combo.n+1:1;FX.combo.last=now;
if(FX.combo.n>=2)floatText(400,150,'COMBO x'+FX.combo.n+'!','#6ee7ff',26,true);}
function levelUpFX(){whiteFlash(.4);doShake(9,.45);zoomPunch(.05);SND.levelup();
for(let i=0;i<3;i++)setTimeout(()=>ring(myData.x,myData.y,90+i*26,'#ffd166',4),i*120);
for(let i=0;i<42;i++){const a=Math.random()*6.283,s=90+Math.random()*200;
FX.particles.push({x:myData.x,y:myData.y,vx:Math.cos(a)*s,vy:-Math.abs(Math.sin(a))*s-120,life:.8+Math.random()*.6,max:1.3,size:2+Math.random()*3.5,color:['#ffd166','#ffe9a8','#fff7d6'][i%3],grav:160});}
floatText(myData.x,myData.y-56,'⭐ LEVEL UP!','#ffd166',30,true);}
function killFX(m){m.alive=false;m.dying=1;m.fadeT=performance.now();SND.kill();
spawnParticles(m.rx,m.ry,m.boss?'#ff6b6b':'#8f8',m.boss?46:26,m.boss?1.5:1);
shock(m.rx,m.ry,m.boss?120:70);doShake(m.boss?16:12,m.boss?.5:.35);hitstop(.1);zoomPunch(.06);
floatText(m.rx,m.ry-36,KILL_WORDS[Math.random()*KILL_WORDS.length|0],'#ff8a5c',22,true);comboKill();}
function hitFX(m,dmg,crit,dodged){if(dodged){floatText(m.rx,m.ry-26,'หลบ!','#9aa7bd',14);return;}
m.flashT=performance.now();slashAt(m.rx,m.ry,crit);
spawnParticles(m.rx,m.ry,crit?'#ffd166':'#ff9f43',crit?16:7,crit?1.15:.8);
if(crit){shock(m.rx,m.ry,44,'#ffd166');doShake(11,.28);hitstop(.085);zoomPunch(.04);}else doShake(4.5,.16);
floatText(m.rx+(Math.random()-.5)*14,m.ry-26,'-'+dmg,crit?'#ffd166':'#fff',crit?24:16,crit);}
function hurtSelfFX(dmg){vignetteHurt();doShake(6,.2);SND.hurt();
floatText(myData.x,myData.y-30,'-'+dmg,'#ff6b6b',17);
spawnParticles(myData.x,myData.y,'#ff4d6d',6,.7);checkLowHP();}

// ================= AUTH =================
function selectJob(job,el){document.querySelectorAll('.job-card').forEach(c=>c.classList.remove('active'));
el.classList.add('active');document.getElementById('auth-job').value=job;}
function toggleAuthMode(){isRegisterMode=!isRegisterMode;
document.getElementById('auth-title').innerText=isRegisterMode?'สร้างตัวละครใหม่ (Register)':'เข้าสู่ระบบ (Login)';
document.getElementById('auth-submit-btn').innerText=isRegisterMode?'ยืนยันสร้างตัวละคร':'เข้าสู่เกม';
document.getElementById('auth-toggle-txt').innerText=isRegisterMode?'มีตัวละครแล้ว? เข้าสู่ระบบ':'ยังไม่มีตัวละคร? สมัครสมาชิกใหม่';
document.getElementById('register-fields').style.display=isRegisterMode?'block':'none';}
async function submitAuth(){
  const user=document.getElementById('auth-user').value.trim();
  const pass=document.getElementById('auth-id').value.trim();
  const job=document.getElementById('auth-job').value;
  const msgEl=document.getElementById('auth-msg');
  const btn=document.getElementById('auth-submit-btn');
  if(btn.disabled)return;btn.disabled=true;
  if(!user||!pass){msgEl.innerText='กรุณากรอกข้อมูลให้ครบ';btn.disabled=false;return;}
  try{
    const endpoint=isRegisterMode?'/api/register':'/api/login';
    const payload=isRegisterMode?{username:user,password:pass,job}:{username:user,password:pass};
    const res=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await res.json();
    if(data.success){
      if(isRegisterMode){SND.quest();alert('สร้างตัวละครสำเร็จ! เข้าสู่ระบบเลย');toggleAuthMode();btn.disabled=false;}
      else{SND.init();SND.respawn();
        myData=data.user;myData.isDead=myData.hp<=0;
        document.getElementById('auth-screen').style.display='none';
        document.getElementById('game-wrapper').style.display='block';
        fitToScreen();   // 👈 เพิ่มบรรทัดนี้
        updateTownBackground(myData.map);   // ← เพิ่มตรงนี้
        document.getElementById('hud-avatar-icon').innerText=JOB_ICONS[myData.job]||'👤';
        initGameSocket();}
    }else msgEl.innerText=data.message;
  }catch(e){msgEl.innerText='เชื่อมต่อเซิร์ฟเวอร์ไม่ได้';}
  btn.disabled=false;
}

// ================= API HELPER =================
async function apiPost(url,payload){
  const res=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  let d=null;try{d=await res.json();}catch(e){}
  if(!res.ok||!d)throw new Error('Server '+res.status+(d&&d.message?' — '+d.message:''));
  return d;}

// ================= SOCKET =================
function initGameSocket(){
  socket=io({reconnectionDelayMax:5000});
  socket.on('connect',()=>{joinSentThisConn=false;
    if(myData&&!joinSentThisConn&&!kicked){socket.emit('join_game',{id:myData.id});joinSentThisConn=true;
    if(myData._reconnected)showNotice('🔄 เชื่อมต่อใหม่สำเร็จ');}});
  socket.on('disconnect',()=>{joinSentThisConn=false;if(myData)myData._reconnected=true;});
  socket.on('force_disconnect',()=>{kicked=true;SND.death();alert('บัญชีถูกถอดออก (ล็อกอินจากที่อื่น หรือถูกแบน)');location.reload();});

  socket.on('players_in_map',data=>{allPlayers=data;const me=allPlayers[socket.id];
    if(me){myData.x=me.x;myData.y=me.y;selfSynced=true;}});
  socket.on('move_player',p=>{
    if(!allPlayers[p.sid])allPlayers[p.sid]={...p,rx:p.x,ry:p.y};
    else{const q=allPlayers[p.sid];q.rx=(q.rx==null)?p.x:q.rx;q.ry=(q.ry==null)?p.y:q.ry;Object.assign(q,p);}
    if(p.sid===socket.id){myData.x=p.x;myData.y=p.y;selfSynced=true;}});
  socket.on('remove_player',d=>delete allPlayers[d.sid]);
  socket.on('player_left_map',d=>delete allPlayers[d.sid]);

  socket.on('monsters_sync',d=>{monsters={};
    (d.monsters||[]).forEach(m=>{monsters[String(m.id)]={...m,rx:m.x,ry:m.y};});
    myData.map=d.map;updateMapUI();
  updateTownBackground(d.map);   // ← เพิ่มตรงนี้
  });
  socket.on('monsters_update',d=>(d.monsters||[]).forEach(m=>{
    const cur=monsters[String(m.id)];
    if(cur){Object.assign(cur,m);if(m.alive)cur.dying=0;}
    else monsters[String(m.id)]={...m,rx:m.x,ry:m.y};}));
  socket.on('monster_killed',d=>{const m=monsters[String(d.monster_id)];if(m&&!m.dying)killFX(m);});

  socket.on('npcs_sync',d=>{NPCS_STATE[d.map]=d.npcs||[];});
  socket.on('ground_items_sync',d=>{if(myData&&d.map===myData.map){groundItems={};(d.items||[]).forEach(g=>groundItems[g.id]=g);}});
  socket.on('item_dropped',g=>{groundItems[g.id]=g;floatText(g.x,g.y-26,'✨ '+g.name,'#ffe9a8',12);});
  socket.on('item_picked',d=>{const g=groundItems[d.item_id];delete groundItems[d.item_id];
    if(walkPickupId===d.item_id)walkPickupId=null;});

  socket.on('attack_result',res=>{
    if(!res.success){showNotice(res.message||'โจมตีไม่สำเร็จ');return;}
    // 🔊 เสียงโจมตีของเรา
    if(res.dodged)SND.miss();
    else if(res.crit)SND.crit();
    else SND.hit();
    const m=monsters[String(res.monster_id)];
    if(m){m.hp=res.monster_hp_left;hitFX(m,res.dmg,res.crit,res.dodged);if(res.monster_died)killFX(m);}
    if(res.user)Object.assign(myData,res.user);
    myData.hp=res.player_hp_left;
    if(res.monster_died&&pendingAttackId===String(res.monster_id)){pendingAttackId=null;if(!moveTarget)chaseId=null;}
    updateUIValues();});

  socket.on('skill_result',r=>{
    const slot=document.querySelector('.quick-slot[data-skill="'+r.skill+'"]');
    if(!r.success){if(slot)slot.dataset.cdUntil=0;showNotice(r.message);return;}
    if(slot)slot.dataset.cdUntil=performance.now()+r.cd*1000;
    if(myData)myData.mp=r.mp;
    // 🔊 เสียงสกิล
    if(r.type==='heal'){SND.heal();ring(myData.x,myData.y,64,'#2ecc71',4);spawnParticles(myData.x,myData.y,'#7bed9f',14,.8);
      floatText(myData.x,myData.y-40,'+'+r.heal,'#7bed9f',19);}
    else if(r.type==='buff'){SND.buff();ring(myData.x,myData.y,58,'#f1c40f',4);whiteFlash(.15);
      floatText(myData.x,myData.y-40,'✨ BUFF!','#f1c40f',18);}
    else{SND.skill();
      let anyKill=false;
      (r.hits||[]).forEach(h=>{const m=monsters[String(h.monster_id)];
        if(m){m.hp=h.monster_hp_left;hitFX(m,h.dmg,h.crit,false);if(h.monster_died){killFX(m);anyKill=true;}}});
      if(r.type==='aoe'){ring(myData.x,myData.y,150,'#e67e22',5);whiteFlash(.12);doShake(12,.3);}
      if(anyKill&&r.user)Object.assign(myData,r.user);
      if(r.leveled_up)levelUpFX();}
    updateUIValues();});

  socket.on('monster_attack',a=>{
    if(a.target_sid===socket.id){myData.hp=a.hp_left;hurtSelfFX(a.dmg);
      floatText(myData.x,myData.y-44,'👹 '+a.monster_name,'#ff9f8a',11);}
    else{const q=allPlayers[a.target_sid];
      if(q){floatText(q.rx,q.ry-28,'-'+a.dmg,'#ff6b6b',14);spawnParticles(q.rx,q.ry,'#ff4757',5,.6);}}});
  socket.on('pvp_hit',a=>{myData.hp=a.hp;hurtSelfFX(a.dmg);floatText(myData.x,myData.y-40,'⚔️ '+a.attacker,'#ff9f43',13);});
  socket.on('pvp_result',r=>{if(!r.success)showNotice(r.message);});

  socket.on('boss_slam',s=>{SND.slam();whiteFlash(.5);doShake(16,.55);zoomPunch(.07);
    shock(s.x,s.y,s.radius,'#c0392b');ring(s.x,s.y,s.radius,'#ff6b6b',5);
    for(let i=0;i<26;i++){const a=Math.random()*6.283,d=30+Math.random()*90;
      FX.particles.push({x:s.x+Math.cos(a)*d,y:s.y+Math.sin(a)*d,vx:Math.cos(a)*160,vy:-140-Math.random()*120,life:.7+Math.random()*.4,max:1,size:2+Math.random()*4,color:'#8d6e63',grav:420});}
    floatText(s.x,s.y-46,'💥 SLAM!','#ff6b6b',26,true);});
  socket.on('screen_shake',d=>{doShake(d.intensity||5,d.duration||.25);
    if(d.hurt)vignetteHurt();
    if(d.type==='levelup')levelUpFX();
    if(d.type==='enrage')SND.enrage();});

  socket.on('combat_fx',fx=>{
    if(fx.type==='hit'){if(myData&&fx.by===myData.username)return;
      const m=monsters[String(fx.monster_id)];
      if(m){m.flashT=performance.now();
        floatText(m.rx,m.ry-24,fx.dodged?'หลบ!':'-'+fx.dmg,fx.crit?'#ffd166':'#ccc',fx.crit?17:12);
        spawnParticles(m.rx,m.ry,'#ccc',4,.6);}}
    else if(fx.type==='miss')floatText(myData.x,myData.y-34,'พลาด!','#9aa7bd',13);
    else if(fx.type==='immune')floatText(myData.x,myData.y-34,'ล่องหน!','#9ad9ff',13);
    else if(fx.type==='player_died'){const q=allPlayers[fx.sid];if(q)ring(q.rx,q.ry,52,'#95a5a6',3);}});

  socket.on('kill_reward',r=>{
    if(r.user){const wasLv=myData.level;Object.assign(myData,r.user);
      if(myData.level>wasLv)levelUpFX();}
    showNotice(`+${r.exp_gain||0} EXP +${r.gold_gain||0} G${r.leveled_up?' ⭐ LEVEL UP!':''}`);
    updateUIValues();});

  socket.on('stats_update',r=>{if('hp'in r)myData.hp=r.hp;if('mp'in r)myData.mp=r.mp;updateUIValues();});
  socket.on('gold_update',d=>{if(myData){myData.gold=d.gold;updateUIValues();}});

  socket.on('item_result',res=>{
    if(!res.success){showNotice(res.message);return;}
    // 🔊 เสียงเก็บของ / ใช้ยา
    if(res.picked)SND.pickup();
    else SND.potion();
    showNotice(res.message||`ใช้ ${res.name} +${res.heal||0}HP +${res.mana||0}MP`);
    ring(myData.x,myData.y,res.picked?26:40,res.picked?'#ffd166':'#7bed9f',3);
    loadInventory();});
  socket.on('respawn_error',d=>showNotice(d.message));

  socket.on('player_died',d=>{
    myData.isDead=true;myData.hp=0;stopAllMovement();
    SND.death();vignetteHurt();doShake(12,.5);whiteFlash(.25);
    document.getElementById('death-info').textContent=`ถูก ${d.killer} ปราบ — เสีย ${d.exp_lost} EXP, ${d.gold_lost} G`;
    document.getElementById('death-modal').style.display='block';
    updateUIValues();});
  socket.on('respawned',d=>{
    myData.isDead=false;Object.assign(myData,d.user);
    myData.x=400;myData.y=300;myData.map='town';selfSynced=true;checkLowHP();
    document.getElementById('death-modal').style.display='none';
    updateMapUI();
    updateTownBackground('town');   // ← เพิ่มตรงนี้
    updateUIValues();
    SND.respawn();ring(myData.x,myData.y,60,'#00ffcc',4);
    showNotice('✨ เกิดใหม่ที่เมือง — อมตะ 3 วิ');});

  socket.on('chat_message',d=>{appendChatMessage(d.channel,d.username,d.message,d.time,d.to);
    if(d.channel==='whisper')SND.msg();});
  socket.on('system_message',d=>{appendChatMessage('sys','ระบบ',d.message);
    showNotice('📢 '+d.message);if(myData)floatText(400,110,d.message,'#ffe8a3',13);});

  // Market events
  socket.on('market_tick',d=>{MK.lastPrice=MK.price;MK.price=d.price;
    MK.hist.push(d.price);if(MK.hist.length>240)MK.hist.shift();
    if(MK.open){drawChart();updateMkUI();}});
  socket.on('market_state',d=>{
    MK.position=d.position;MK.orders=d.orders||[];
    if(myData&&d.gold!==undefined){myData.gold=d.gold;updateUIValues();}
    if(d.msg){showNotice(d.msg);SND.trade();}
    if(MK.open){renderMkOrders();updateMkUI();}});
  socket.on('market_closed',d=>{
    const cls=d.pnl>=0?'#7bed9f':'#ff6b6b';
    SND.trade();
    showNotice(`📈 ปิดสถานะ (${d.reason}) ${d.pnl>=0?'กำไร':'ขาดทุน'} ${d.pnl>=0?'+':''}${d.pnl} G`);
    floatText(myData.x,myData.y-50,(d.pnl>=0?'📈 +':'📉 ')+d.pnl+' G',cls,20,true);
    spawnParticles(myData.x,myData.y,cls,12,1);});
  socket.on('market_notice',d=>showNotice(d.msg));

  if(myData.isAdmin)document.getElementById('admin-menu-btn').style.display='inline-block';
  updateUIValues();
  loadMaps();loadInventory();loadSkills();loadShop();loadQuests();
  fitGameToScreen();
  setInterval(autoBotTick,350);
  setInterval(autoPickupTick,280);
  requestAnimationFrame(gameLoop);
}

// ================= UI helpers =================
function showNotice(text){if(!text)return;const n=document.getElementById('game-notice');
n.innerText=text;n.style.display='block';clearTimeout(n._t);n._t=setTimeout(()=>n.style.display='none',2500);}
function openModal(id){document.getElementById(id).style.display='block';refreshModal(id);}
function closeModal(id){document.getElementById(id).style.display='none';}
function refreshModal(id){
  if(id==='statusModal'){['job','atk','def','maxhp','maxmp','gold','maxexp'].forEach(k=>{
    const el=document.getElementById('val-'+k);if(!el)return;
    el.innerText={job:(JOB_ICONS[myData.job]||'')+' '+myData.job,atk:myData.atk,def:myData.def,
      maxhp:myData.maxHp,maxmp:myData.maxMp,gold:myData.gold,maxexp:myData.maxExp}[k];});}
  if(id==='bagModal')renderBag();
  if(id==='questModal')loadQuests();
  if(id==='shopModal'){if(shopTab==='sell')renderSellList();else loadShop();}
  if(id==='jobModal')renderJobModal();}
function updateUIValues(){if(!myData)return;
  document.getElementById('ui-name').innerText=myData.username;
  document.getElementById('ui-job').innerText=myData.job;
  document.getElementById('ui-level').innerText=myData.level;
  document.getElementById('ui-hp').innerText=myData.hp+'/'+myData.maxHp;
  document.getElementById('ui-mp').innerText=myData.mp+'/'+myData.maxMp;
  document.getElementById('ui-exp').innerText=myData.exp+'/'+myData.maxExp;
  document.getElementById('ui-gold').innerText=myData.gold;
  document.getElementById('bar-hp').style.width=Math.max(0,myData.hp/myData.maxHp*100)+'%';
  document.getElementById('bar-mp').style.width=Math.max(0,myData.mp/myData.maxMp*100)+'%';
  document.getElementById('bar-exp').style.width=Math.min(100,myData.exp/myData.maxExp*100)+'%';
  document.getElementById('wrap-hp').classList.toggle('low',myData.hp<myData.maxHp*.3);
  checkLowHP();
  const pc=myInventory.filter(i=>i.type==='potion').reduce((s,i)=>s+i.quantity,0);
  document.getElementById('ui-potion-count').innerText=pc;}
function updateMapUI(){
  document.getElementById('ui-mapname').innerText=MAP_LABELS[myData.map]||myData.map;
  const sel=document.getElementById('map-select');if(sel)sel.value=myData.map;}
function fitGameToScreen(){
  const s=Math.max(.42,Math.min(1.1,(window.innerWidth-8)/800,(window.innerHeight-8)/600));
  document.getElementById('game-wrapper').style.transform=`scale(${s})`;}
window.addEventListener('resize',fitGameToScreen);
function clampN(v,a,b){return Math.max(a,Math.min(b,v));}
function escHtml(s){const d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML;}

// ================= SOUND TOGGLES =================
function toggleSound(){SND.enabled=!SND.enabled;
document.getElementById('snd-toggle-switch').classList.toggle('on',SND.enabled);
showNotice(SND.enabled?'🔊 เสียงเอฟเฟกต์: ON':'🔇 เสียงเอฟเฟกต์: OFF');}
function toggleMusic(){SND.musicOn=!SND.musicOn;
document.getElementById('music-toggle-switch').classList.toggle('on',SND.musicOn);
showNotice(SND.musicOn?'🎵 เพลงพื้นหลัง: ON':'🎵 เพลงพื้นหลัง: OFF');}

// ================= MAPS =================
async function loadMaps(){
  try{
    const d=await(await fetch('/api/maps')).json();
    MAPS_META=d.maps||[];
    MAP_LABELS={};const sel=document.getElementById('map-select');sel.innerHTML='';
    MAPS_META.forEach(m=>{MAP_LABELS[m.key]=m.label;
      const opt=document.createElement('option');opt.value=m.key;
      opt.textContent=(m.level>0?`Lv.${m.level}+ `:'🏠 ')+m.label;
      sel.appendChild(opt);});
    sel.value=myData.map;
  }catch(e){}}
async function loadMonsters(){
  try{const d=await(await fetch('/api/monsters/'+myData.map)).json();
    monsters={};(d.monsters||[]).forEach(m=>{monsters[String(m.id)]={...m,rx:m.x,ry:m.y};});}catch(e){}}
function changeMap(map,fromBot){
  if(!map)return;
  if(myData.isDead){showNotice('💀 คุณสลบอยู่ — กดเกิดใหม่ก่อน');updateMapUI();return;}
  if(map===myData.map){updateMapUI();return;}
  const meta=MAPS_META.find(m=>m.key===map);
  if(!fromBot&&meta&&meta.level>0&&myData.level<meta.level-5){
    if(!confirm(`⚠️ แมพนี้แนะนำ Lv.${meta.level}+ (คุณ Lv.${myData.level}) อาจตายง่าย! จะเข้าไปเลย?`)){updateMapUI();return;}}
  stopAllMovement();
  myData.map=map;selfSynced=false;
  const sp=(map==='town')?[400,300]:[90,300];
  myData.x=sp[0];myData.y=sp[1];
  monsters={};allPlayers={};groundItems={};walkNPCId=null;walkPickupId=null;
  updateMapUI();
  updateTownBackground(map);   // ← เพิ่มตรงนี้
  loadMonsters();
  socket.emit('move',{x:sp[0],y:sp[1],map:myData.map});
  if(autoBotActive&&!fromBot){
    if(map==='town'){botState='idle';showNotice('🤖 บอทพักที่เมือง — เลือกแมพล่ามอนเพื่อให้บอททำงานต่อ');return;}
    botHomeMap=map;botState='farm';
    showNotice('🤖 บอทย้ายโซนฟาร์ม: '+(MAP_LABELS[map]||map));return;}
  if(!fromBot){SND.travel();showNotice('🚪 เดินทาง: '+(MAP_LABELS[map]||map));}
}

// ================= INVENTORY / SKILLS =================
async function loadInventory(){
  try{const d=await(await fetch('/api/inventory/'+myData.id)).json();
    myInventory=d.inventory||[];updateUIValues();
    if(document.getElementById('bagModal').style.display==='block')renderBag();
    if(document.getElementById('shopModal').style.display==='block'&&shopTab==='sell')renderSellList();}catch(e){}}
async function loadSkills(){
  try{const d=await(await fetch('/api/skills?job='+encodeURIComponent(myData.job))).json();
    SKILLS=d.skills||{};
    const bar=document.getElementById('skill-row');bar.innerHTML='';
    Object.entries(SKILLS).slice(0,4).forEach(([id,sk],i)=>{
      const el=document.createElement('div');
      el.className='quick-slot';el.dataset.skill=id;el.dataset.cdUntil=0;
      el.title=sk.name+' (MP '+sk.mp+')';
      el.innerHTML=`<span class="skill-key">${i+1}</span>${SKILL_ICONS[sk.type]||'✨'}<div class="cd-overlay" style="display:none">0</div>`;
      el.onclick=()=>castSkill(id);bar.appendChild(el);});}catch(e){}}
function castSkill(id){
  if(!myData||myData.isDead||myData.map==='town')return;
  const now=performance.now();
  const el=document.querySelector('.quick-slot[data-skill="'+id+'"]');
  if(el&&now<(el.dataset.cdUntil||0))return;
  const sk=SKILLS[id];if(!sk)return;
  const payload={skill:id};
  if(sk.type==='single'){const m=nearestAliveMonster(sk.range||220);
    if(!m){showNotice('ไม่มีเป้าหมายในระยะ');return;}payload.monster_id=m.id;}
  if(el)el.dataset.cdUntil=now+sk.cd*1000;
  socket.emit('use_skill',payload);}

// ================= SHOP: ซื้อ =================
async function loadShop(){
  try{const d=await(await fetch('/api/shop')).json();
    const list=document.getElementById('shop-buy-list');
    list.innerHTML='<div class="shop-note">🧪 ซื้อของต้องอยู่ใกล้ "ยายพอใจ" ในเมือง (💰 '+myData.gold+' G)</div>';
    (d.items||[]).forEach(it=>{
      const row=document.createElement('div');row.className='item-row';
      const eff=[];
      if(it.heal_pct)eff.push('❤️ HP '+Math.round(it.heal_pct*100)+'%');
      if(it.mana_pct)eff.push('✦ MP '+Math.round(it.mana_pct*100)+'%');
      if(it.level_req)eff.push('Lv.'+it.level_req+'+');
      row.innerHTML=`<div class="item-main"><div class="item-icon">🧪</div>
        <div><div>${it.name}</div><div class="meta">${eff.join(' • ')}</div></div></div><span class="price">💰 ${it.price}</span>`;
      const btn=document.createElement('button');btn.className='action-btn-sm';btn.textContent='ซื้อ';
      btn.onclick=()=>buyItem(it.id,it.name,it.price);row.appendChild(btn);list.appendChild(row);});}catch(e){}}
function nearNPC(type){if(!myData)return false;
  const npc=(NPCS_STATE[myData.map]||[]).find(n=>n.type===type);
  return npc&&Math.hypot(npc.x-myData.x,npc.y-myData.y)<=110;}
async function buyItem(id,name,price){
  if(!nearNPC('shop')){showNotice('🧪 ต้องเข้าใกล้ "ยายพอใจ" ก่อน! (คลิก NPC เพื่อเดินไปหา)');return;}
  if(myData.gold<price){showNotice('💰 Gold ไม่พอ!');return;}
  try{const d=await apiPost('/api/shop/buy',{user_id:myData.id,item_id:id});
    if(d.success){SND.buy();Object.assign(myData,d.user);updateUIValues();loadInventory();
      showNotice('🛒 ซื้อ '+name+' สำเร็จ! (เหลือ '+myData.gold+' G)');if(shopTab==='buy')loadShop();}
    else showNotice(d.message);}catch(e){showNotice('❌ '+e.message);}}

// ================= SELL (รวมกอง + ขายได้ทุกที่) =================
function switchShopTab(t){shopTab=t;
  document.getElementById('shop-buy-list').style.display=(t==='buy')?'block':'none';
  document.getElementById('shop-sell-list').style.display=(t==='sell')?'block':'none';
  document.getElementById('shopTabBuy').classList.toggle('active',t==='buy');
  document.getElementById('shopTabSell').classList.toggle('active',t==='sell');
  if(t==='sell')renderSellList();else loadShop();}
function mergeInventory(filterFn){
  const merged={};
  myInventory.forEach(it=>{
    if(it.quantity<=0)return;
    if(filterFn&&!filterFn(it))return;
    if(merged[it.name]){merged[it.name].qty+=it.quantity;merged[it.name].ids.push(it.id);}
    else merged[it.name]={...it,qty:it.quantity,ids:[it.id]};});
  return Object.values(merged);}
function renderSellList(){
  const list=document.getElementById('shop-sell-list');
  const sellables=mergeInventory(i=>(i.sell_price||0)>0);
  let total=0;sellables.forEach(i=>total+=(i.sell_price||0)*i.qty);
  list.innerHTML='<div class="shop-note">🤖 บอทรับซื้อ BE-1 — ขายได้ทุกที่ • รวม ~💰 '+total+' G</div>';
  if(!sellables.length){list.innerHTML+='<div class="empty-state">ไม่มีของขาย — ไปล่ามอนเก็บวัสดุ!</div>';return;}
  sellables.forEach(it=>{
    const row=document.createElement('div');row.className='item-row';
    row.innerHTML=`<div class="item-main"><div class="item-icon">${it.type==='potion'?'🧪':'📦'}</div>
      <div><div>${escHtml(it.name)} <b style="color:#ffd166">×${it.qty}</b></div>
      <div class="meta">ชิ้นละ 💰 ${it.sell_price} G</div></div></div>`;
    const b1=document.createElement('button');b1.className='action-btn-sm';b1.textContent='ขาย 1';
    b1.onclick=()=>sellFromItem(it,1);
    const b2=document.createElement('button');b2.className='action-btn-sm gold';b2.textContent=`ขายทั้งหมด (${it.qty})`;
    b2.onclick=()=>sellFromItem(it,it.qty);
    row.appendChild(b1);row.appendChild(b2);list.appendChild(row);});
  const allBtn=document.createElement('button');allBtn.className='action-btn gold';
  allBtn.textContent='💰 ขายวัสดุทั้งหมดในกระเป๋า';
  allBtn.onclick=()=>sellAllMaterials();list.appendChild(allBtn);}
async function sellFromItem(it,qty){
  if(!myData||!it||qty<1)return;
  try{
    let remaining=qty,earned=0;
    for(const invId of (it.ids||[it.id])){
      if(remaining<=0)break;
      const row=myInventory.find(r=>r.id===invId);
      const q=Math.min(remaining,row?row.quantity:0);
      if(q<=0)continue;
      const d=await apiPost('/api/shop/sell',{user_id:myData.id,inventory_id:invId,quantity:q});
      earned+=d.earned;remaining-=q;Object.assign(myData,d.user);}
    if(earned>0){SND.sell();updateUIValues();
      showNotice(`💰 ขาย ${it.name} ×${qty-remaining} ได้ ${earned} G (รวม ${myData.gold} G)`);
      await loadInventory();}
  }catch(e){showNotice('❌ ขายไม่สำเร็จ: '+e.message);}}
async function sellAllMaterials(){
  const mats=mergeInventory(i=>i.type==='material');
  if(!mats.length){showNotice('ไม่มีวัสดุให้ขาย');return 0;}
  let earned=0;
  for(const m of mats){
    for(const invId of m.ids){
      const row=myInventory.find(r=>r.id===invId);
      if(!row||row.quantity<=0)continue;
      try{const d=await apiPost('/api/shop/sell',{user_id:myData.id,inventory_id:invId,quantity:row.quantity});
        earned+=d.earned;Object.assign(myData,d.user);}catch(e){}}}
  await loadInventory();
  SND.sell();
  showNotice(`🤖 ขายวัสดุหมด! ได้ 💰 ${earned} G (รวม ${myData.gold} G)`);
  if(document.getElementById('bagModal').style.display==='block')renderBag();
  if(document.getElementById('shopModal').style.display==='block'&&shopTab==='sell')renderSellList();
  return earned;}

// ================= BAG (รวมกอง) =================
function renderBag(){
  const list=document.getElementById('bag-list');
  if(!myInventory.length){list.innerHTML='<div class="empty-state">กระเป๋าว่างเปล่า</div>';return;}
  list.innerHTML='';
  const items=mergeInventory();
  let total=0;items.forEach(i=>{if((i.sell_price||0)>0)total+=(i.sell_price||0)*i.qty;});
  const head=document.createElement('div');head.className='shop-note';
  head.textContent='💼 มูลค่าขายรวม ~💰 '+total+' G (ขายได้ทุกที่)';
  list.appendChild(head);
  items.forEach(it=>{
    const row=document.createElement('div');row.className='item-row';
    const meta=[];
    if(it.type==='potion')meta.push('ใช้เพื่อฟื้นฟู');
    if((it.sell_price||0)>0)meta.push('ขาย 💰'+it.sell_price+'/ชิ้น');
    row.innerHTML=`<div class="item-main"><div class="item-icon">${it.type==='potion'?'🧪':'📦'}</div>
      <div><div>${escHtml(it.name)} <b style="color:#ffd166">×${it.qty}</b></div>
      <div class="meta">${meta.join(' • ')||'ไอเทม'}</div></div></div>`;
    if(it.type==='potion'){
      const b=document.createElement('button');b.className='action-btn-sm';b.textContent='ใช้';
      b.onclick=()=>socket.emit('use_item',{inventory_id:it.ids[0]});row.appendChild(b);}
    if((it.sell_price||0)>0){
      const b1=document.createElement('button');b1.className='action-btn-sm gold';b1.textContent='ขาย 1';
      b1.onclick=()=>sellFromItem(it,1);row.appendChild(b1);
      if(it.qty>1){const b2=document.createElement('button');b2.className='action-btn-sm gold';
        b2.textContent='ขายทั้งหมด';b2.onclick=()=>sellFromItem(it,it.qty);row.appendChild(b2);}}
    list.appendChild(row);});
  if(items.some(i=>i.type==='material')){
    const allBtn=document.createElement('button');allBtn.className='action-btn gold';
    allBtn.textContent='💰 ขายวัสดุทั้งหมด';
    allBtn.onclick=()=>sellAllMaterials();list.appendChild(allBtn);}}
function usePotionItem(){
  if(!myData||myData.isDead)return;
  const pots=myInventory.filter(i=>i.type==='potion'&&i.quantity>0);
  if(!pots.length){showNotice('ไม่มีโพชั่น! ไปซื้อที่ร้านยายพอใจ');return;}
  const hpPct=myData.hp/myData.maxHp,mpPct=myData.mp/myData.maxMp;
  if(hpPct>0.98&&mpPct>0.98){showNotice('เต็มอยู่แล้ว');return;}
  let pick=(hpPct<=mpPct)?(pots.find(p=>p.name.includes('HP'))||pots[0])
    :(pots.find(p=>p.name.includes('MP'))||pots[0]);
  socket.emit('use_item',{inventory_id:pick.id});}

// ================= JOB SYSTEM =================
let JOBS_DATA={};
async function renderJobModal(){
  if(!Object.keys(JOBS_DATA).length){
    try{const d=await(await fetch('/api/jobs')).json();JOBS_DATA=d.jobs||{};}catch(e){return;}}
  const cur=JOBS_DATA[myData.job];
  document.getElementById('job-current').innerHTML=
    `อาชีพปัจจุบัน: <b style="color:var(--neon)">${JOB_ICONS[myData.job]||''} ${myData.job}</b> • Lv.${myData.level} • 💰 ${myData.gold} G`;
  const list=document.getElementById('job-list');list.innerHTML='';
  const adv=(cur&&cur.advance)||{};
  const keys=Object.keys(adv);
  if(!keys.length){list.innerHTML='<div class="empty-state">คุณอยู่ในสายอาชีพสูงสุดแล้ว! 🎉</div>';return;}
  keys.forEach(target=>{
    const reqLv=adv[target][0],reqGold=adv[target][1];
    const okLv=myData.level>=reqLv,okGold=myData.gold>=reqGold;
    const row=document.createElement('div');row.className='item-row';
    row.innerHTML=`<div class="item-main"><div class="item-icon">${JOB_ICONS[target]||'🏅'}</div>
      <div><div>${target}</div><div class="meta">ต้องการ Lv.${reqLv} • 💰 ${reqGold} G</div></div></div>`;
    const btn=document.createElement('button');
    btn.className='action-btn-sm'+(okLv&&okGold?'':' gold');
    btn.textContent=(okLv&&okGold)?'เลื่อนอาชีพ!':(okLv?'Gold ไม่พอ':'Lv. ไม่พอ');
    btn.disabled=!(okLv&&okGold);
    btn.onclick=()=>doJobChange(target);
    row.appendChild(btn);list.appendChild(row);});}
async function doJobChange(target){
  try{
    const d=await apiPost('/api/job/change',{user_id:myData.id,job:target});
    if(d.success){SND.jobchange();Object.assign(myData,d.user);
      document.getElementById('hud-avatar-icon').innerText=JOB_ICONS[myData.job]||'👤';
      updateUIValues();await loadSkills();
      showNotice('🏅 '+d.message);
      whiteFlash(.5);doShake(10,.5);zoomPunch(.06);
      for(let i=0;i<3;i++)setTimeout(()=>ring(myData.x,myData.y,100+i*30,'#a78bfa',5),i*150);
      renderJobModal();}
    else showNotice(d.message);}catch(e){showNotice('❌ '+e.message);}}

// ================= QUESTS =================
async function loadQuests(){
  try{const d=await(await fetch('/api/quests/'+myData.id)).json();
    const list=document.getElementById('quest-list');
    if(!d.quests||!d.quests.length){list.innerHTML='<div class="empty-state">ไม่มีเควส</div>';return;}
    list.innerHTML='';
    d.quests.forEach(q=>{
      const card=document.createElement('div');card.className='quest-card';
      const st=q.status==='done'?'<span class="quest-status st-done">สำเร็จ!</span>'
        :q.status==='claimed'?'<span class="quest-status st-claimed">รับแล้ว</span>'
        :'<span class="quest-status st-progress">กำลังทำ</span>';
      const pct=Math.min(100,q.progress/q.target_count*100);
      card.innerHTML=`<div class="quest-head"><b>${q.name}</b>${st}</div>
        <div class="quest-desc">${q.desc}</div>
        <div class="quest-progress"><div class="qp-fill" style="width:${pct}%"></div><span>${q.progress}/${q.target_count}</span></div>
        <div class="quest-reward">🎁 ${q.reward_exp} EXP • 💰 ${q.reward_gold} G</div>`;
      if(q.status==='done'){const btn=document.createElement('button');btn.className='action-btn';
        btn.textContent='รับรางวัล';btn.onclick=()=>claimQuest(q.id);card.appendChild(btn);}
      list.appendChild(card);});}catch(e){}}
async function claimQuest(qid){
  try{const d=await apiPost('/api/quests/claim',{user_id:myData.id,quest_id:qid});
    if(d.success){SND.quest();Object.assign(myData,d.user);updateUIValues();
      if(d.leveled_up)levelUpFX();
      showNotice('📜 รับรางวัลเควส!');loadQuests();}
    else showNotice(d.message);}catch(e){showNotice('❌ '+e.message);}}

// ================= ADMIN =================
async function adminBroadcast(){
  const msg=document.getElementById('admin-broadcast-text').value.trim();
  if(!msg){showNotice('พิมพ์ข้อความก่อน');return;}
  try{const d=await apiPost('/api/admin/broadcast',{message:msg});
    showNotice(d.success?'📢 สำเร็จ':d.message);
    if(d.success)document.getElementById('admin-broadcast-text').value='';}catch(e){showNotice('❌ '+e.message);}}
async function adminBan(){
  const name=document.getElementById('admin-ban-user').value.trim();
  if(!name){showNotice('ระบุชื่อผู้เล่น');return;}
  try{const d=await apiPost('/api/admin/ban',{username:name});
    showNotice(d.message||'เสร็จสิ้น');}catch(e){showNotice('❌ '+e.message);}}

// ================= CHAT =================
function toggleChatWindow(){const c=document.getElementById('chat-container');
c.style.display=(c.style.display==='none')?'flex':'none';}
function switchChatTab(tab,el){document.querySelectorAll('.chat-tabs .chat-tab').forEach(t=>t.classList.remove('active'));
el.classList.add('active');currentChatTab=tab;
document.getElementById('chat-target').style.display=(tab==='whisper')?'block':'none';renderChat();}
function chatLineEl(m){const d=document.createElement('div');
const cls={global:'ch-global',map:'ch-map',whisper:'ch-whisper',sys:'ch-sys'}[m.channel]||'';
d.className='chat-line '+cls;
const t=m.time?`<span class="chat-time">${escHtml(m.time)}</span>`:'';
if(m.channel==='sys')d.innerHTML=t+escHtml(m.msg);
else if(m.channel==='whisper')d.innerHTML=t+`[Whisper] <b>${escHtml(m.user)}</b> → ${escHtml(m.to||'?')}: ${escHtml(m.msg)}`;
else d.innerHTML=t+`<b>${escHtml(m.user)}:</b> ${escHtml(m.msg)}`;return d;}
function renderChat(){const box=document.getElementById('chat-messages');box.innerHTML='';
chatHistory.filter(m=>currentChatTab==='all'||m.channel===currentChatTab)
.slice(-60).forEach(m=>box.appendChild(chatLineEl(m)));box.scrollTop=box.scrollHeight;}
function appendChatMessage(channel,username,message,time,to){
chatHistory.push({channel,user:username,msg:message,time,to});
if(chatHistory.length>250)chatHistory.shift();
if(currentChatTab==='all'||currentChatTab===channel){
  const box=document.getElementById('chat-messages');
  box.appendChild(chatLineEl({channel,user:username,msg:message,time,to}));
  while(box.children.length>100)box.removeChild(box.firstChild);
  box.scrollTop=box.scrollHeight;}}
function sendChat(e){e.preventDefault();
const inp=document.getElementById('chat-input');
const msg=inp.value.trim();if(!msg)return;
const channel=(currentChatTab==='whisper')?'whisper':(currentChatTab==='map'?'map':'global');
const payload={message:msg,channel};
if(channel==='whisper')payload.target=document.getElementById('chat-target').value.trim();
socket.emit('chat',payload);inp.value='';}
function startDragChat(e){
if(e.target.classList.contains('chat-close'))return;
const c=document.getElementById('chat-container');
const rect=c.getBoundingClientRect();
const dx=e.clientX-rect.left,dy=e.clientY-rect.top;
c.style.left=rect.left+'px';c.style.top=rect.top+'px';c.style.bottom='auto';
function mv(ev){c.style.left=clampN(ev.clientX-dx,0,window.innerWidth-120)+'px';
c.style.top=clampN(ev.clientY-dy,0,window.innerHeight-50)+'px';}
function up(){window.removeEventListener('pointermove',mv);window.removeEventListener('pointerup',up);}
window.addEventListener('pointermove',mv);window.addEventListener('pointerup',up);}

// ================= CONTROLS =================
const heldDirs=new Set();
function updateDpad(){dpadDir.x=(heldDirs.has('right')?1:0)-(heldDirs.has('left')?1:0);
dpadDir.y=(heldDirs.has('down')?1:0)-(heldDirs.has('up')?1:0);}
document.querySelectorAll('.dpad-btn').forEach(b=>{
const dir=b.dataset.dir;
const on=e=>{e.preventDefault();heldDirs.add(dir);b.classList.add('held');updateDpad();};
const off=()=>{heldDirs.delete(dir);b.classList.remove('held');updateDpad();};
b.addEventListener('pointerdown',on);b.addEventListener('pointerup',off);
b.addEventListener('pointerleave',off);b.addEventListener('pointercancel',off);});
window.addEventListener('keydown',e=>{
const a=document.activeElement;
if(a&&(a.tagName==='INPUT'||a.tagName==='TEXTAREA'||a.tagName==='SELECT'))return;
keys[e.key.toLowerCase()]=true;
if(e.key===' '){e.preventDefault();manualAttackAction();}
if(['1','2','3','4'].includes(e.key)){
const el=document.querySelectorAll('.quick-slot[data-skill]')[+e.key-1];if(el)el.click();}});
window.addEventListener('keyup',e=>{keys[e.key.toLowerCase()]=false;});

canvas.addEventListener('pointerdown',e=>{
if(!myData||myData.isDead)return;
const r=canvas.getBoundingClientRect();
const x=(e.clientX-r.left)*(canvas.width/r.width);
const y=(e.clientY-r.top)*(canvas.height/r.height);
for(const n of (NPCS_STATE[myData.map]||[])){
  if(Math.hypot(n.x-x,n.y-y)<26){
    if(Math.hypot(n.x-myData.x,n.y-myData.y)<=110)openNPC(n);
    else{moveTarget={x:n.x,y:n.y};walkNPCId=n.id;chaseId=null;}
    return;}}
let hit=null;
for(const m of Object.values(monsters)){if(!m.alive)continue;
  if(Math.hypot(m.x-x,m.y-y)<(m.boss?34:24)){hit=m;break;}}
if(hit){moveTarget=null;walkNPCId=null;walkPickupId=null;
  chaseId=String(hit.id);pendingAttackId=String(hit.id);
  if(Math.hypot(hit.x-myData.x,hit.y-myData.y)<=ATTACK_RANGE)tryAttack(hit.id);return;}
for(const g of Object.values(groundItems)){
  if(Math.hypot(g.x-x,g.y-y)<17){chaseId=null;
    if(Math.hypot(g.x-myData.x,g.y-myData.y)<=50)socket.emit('pickup_item',{item_id:g.id});
    else{moveTarget={x:g.x,y:g.y};walkPickupId=g.id;}
    return;}}
chaseId=null;walkNPCId=null;walkPickupId=null;
moveTarget={x:clampN(x,20,780),y:clampN(y,20,580)};});
function openNPC(n){
if(n.type==='shop'){openModal('shopModal');switchShopTab('buy');}
else if(n.type==='sell'){openModal('shopModal');switchShopTab('sell');}
else if(n.type==='job'){openModal('jobModal');}}
function tryAttack(mid){const now=performance.now();
if(now<atkCdUntil)return;atkCdUntil=now+780;
socket.emit('attack_monster',{monster_id:mid});}
function nearestAliveMonster(range){range=range||ATTACK_RANGE;
let best=null,bd=range;
for(const m of Object.values(monsters)){if(!m.alive)continue;
const d=Math.hypot(m.x-myData.x,m.y-myData.y);if(d<bd){bd=d;best=m;}}return best;}
function manualAttackAction(){
if(!myData||myData.isDead)return;
if(myData.map==='town'){showNotice('ในเมืองต่อสู้ไม่ได้');return;}
let target=(chaseId&&monsters[chaseId]&&monsters[chaseId].alive)?monsters[chaseId]:null;
if(!target)target=nearestAliveMonster();
if(!target){showNotice('ไม่มีมอนสเตอร์ในระยะ');return;}
chaseId=String(target.id);pendingAttackId=String(target.id);
if(Math.hypot(target.x-myData.x,target.y-myData.y)<=ATTACK_RANGE)tryAttack(target.id);}
function stopAllMovement(){moveTarget=null;chaseId=null;pendingAttackId=null;
walkNPCId=null;walkPickupId=null;keys={};heldDirs.clear();updateDpad();}
function respawnTown(){if(socket)socket.emit('respawn');}

// ================= AUTO PICKUP =================
function autoPickupTick(){
if(!myData||myData.isDead||!autoLoot||!socket)return;
for(const g of Object.values(groundItems)){
if(Math.hypot(g.x-myData.x,g.y-myData.y)<46){socket.emit('pickup_item',{item_id:g.id});return;}}}
function toggleAutoLoot(){autoLoot=!autoLoot;
document.getElementById('loot-toggle-switch').classList.toggle('on',autoLoot);
showNotice(autoLoot?'🎒 เก็บของ: ON':'🎒 เก็บของ: OFF');}
function toggleAutoSell(){autoSell=!autoSell;
document.getElementById('sell-toggle-switch').classList.toggle('on',autoSell);
showNotice(autoSell?'💰 ออโต้ขาย: ON':'💰 ออโต้ขาย: OFF');}

// ================= BOT v2 (เมือง = เขตปลอดบอท) =================
function toggleAutoBot(){
autoBotActive=!autoBotActive;
document.getElementById('combat-toggle-switch').classList.toggle('on',autoBotActive);
document.getElementById('bot-badge').style.display=autoBotActive?'block':'none';
botState='farm';
if(autoBotActive){
if(myData&&myData.map==='town'){botState='idle';
showNotice('🤖 บอท: ON (พักที่เมือง — เลือกแมพล่ามอนเพื่อเริ่มทำงาน)');}
else{botHomeMap=(myData&&myData.map)?myData.map:'forest';
showNotice('🤖 บอท: ON — ฟาร์ม '+(MAP_LABELS[botHomeMap]||botHomeMap));}
if(myData&&myData.isDead)respawnTown();
}else{showNotice('🤖 บอท: OFF');stopAllMovement();}}
function potCount(){return myInventory.filter(i=>i.type==='potion'&&i.quantity>0).reduce((s,i)=>s+i.quantity,0);}
function matCount(){return myInventory.filter(i=>i.type==='material'&&i.quantity>0).reduce((s,i)=>s+i.quantity,0);}
function autoBotTick(){
if(!myData||!autoBotActive||!socket)return;
const now=performance.now();
if(myData.isDead){if(!botDeathAt)botDeathAt=now;
if(now-botDeathAt>4200){respawnTown();botDeathAt=0;}return;}
botDeathAt=0;
if(now-botLastPot>1200){
const hpPct=myData.hp/myData.maxHp*100,mpPct=myData.mp/myData.maxMp*100;
let pick=null;
if(hpPct<45)pick=myInventory.find(i=>i.type==='potion'&&i.quantity>0&&i.name.includes('HP'))
||myInventory.find(i=>i.type==='potion'&&i.quantity>0);
else if(mpPct<30)pick=myInventory.find(i=>i.type==='potion'&&i.quantity>0&&i.name.includes('MP'));
if(pick){botLastPot=now;socket.emit('use_item',{inventory_id:pick.id});}}
if(botState==='idle')return;
if(botState==='restock'){botRestockTick();return;}
if(botState==='sell'){botSellTick();return;}
if(myData.map==='town'){
if(potCount()>0)changeMap(botHomeMap||'forest',true);
else if(myData.gold>=20)botState='restock';
return;}
if(!botBusy){
if(now-lastRestockAt>15000&&potCount()===0&&myData.gold>=20){
lastRestockAt=now;botState='restock';changeMap('town',true);return;}
if(autoSell&&now-lastSellAt>20000&&matCount()>=8){
lastSellAt=now;botState='sell';changeMap('town',true);return;}}
if(autoLoot&&!chaseId){
let nearG=null,gd=90;
for(const g of Object.values(groundItems)){
const d=Math.hypot(g.x-myData.x,g.y-myData.y);if(d<gd){gd=d;nearG=g;}}
if(nearG&&gd>46){const danger=nearestAliveMonster(110);
if(!danger){moveTarget={x:nearG.x,y:nearG.y};walkPickupId=nearG.id;return;}}}
let best=null,bd=1e9;
for(const m of Object.values(monsters)){if(!m.alive)continue;
const d=Math.hypot(m.x-myData.x,m.y-myData.y);if(d<bd){bd=d;best=m;}}
if(!best){
if(!moveTarget||Math.hypot(moveTarget.x-myData.x,moveTarget.y-myData.y)<14)
moveTarget={x:60+Math.random()*720,y:80+Math.random()*440};return;}
chaseId=String(best.id);pendingAttackId=String(best.id);
if(bd>ATTACK_RANGE-8){moveTarget={x:best.x,y:best.y};return;}
moveTarget=null;
if(now>=atkCdUntil){atkCdUntil=now+800;socket.emit('attack_monster',{monster_id:best.id});}
if(now-botLastSkill>5000&&myData.mp>=12){
for(const[id,sk]of Object.entries(SKILLS)){
if(sk.type==='heal'||sk.type==='buff')continue;
const el=document.querySelector('.quick-slot[data-skill="'+id+'"]');
if(el&&now<(el.dataset.cdUntil||0))continue;
if(sk.type==='single'&&bd>=(sk.range||220))continue;
if(sk.type==='aoe'&&bd>=(sk.radius||150))continue;
botLastSkill=now;castSkill(id);break;}}}
async function botBuyPotions(){
if(botBusy)return;botBusy=true;
try{
const shop=(await(await fetch('/api/shop')).json()).items||[];
const hpItem=shop.find(it=>it.type==='potion'&&it.name.includes('HP')&&(!it.level_req||myData.level>=it.level_req));
const mpItem=shop.find(it=>it.type==='potion'&&it.name.includes('MP'));
let bought=0;
for(let i=0;i<5;i++){if(!hpItem||myData.gold<hpItem.price)break;
const d=await apiPost('/api/shop/buy',{user_id:myData.id,item_id:hpItem.id});
if(!d.success)break;Object.assign(myData,d.user);bought++;}
for(let i=0;i<3;i++){if(!mpItem||myData.gold<mpItem.price)break;
const d=await apiPost('/api/shop/buy',{user_id:myData.id,item_id:mpItem.id});
if(!d.success)break;Object.assign(myData,d.user);bought++;}
await loadInventory();
showNotice('🛒 บอทซื้อยา '+bought+' ขวด (💰 '+myData.gold+' G)');}catch(e){}
botBusy=false;}
function botRestockTick(){
if(botBusy)return;
if(myData.map!=='town'){changeMap('town',true);return;}
const npc=(NPCS_STATE['town']||[]).find(n=>n.type==='shop');
if(!npc){botState='farm';return;}
const d=Math.hypot(npc.x-myData.x,npc.y-myData.y);
if(d>75){moveTarget={x:npc.x,y:npc.y};return;}
moveTarget=null;
botBuyPotions().then(()=>{
if(botState!=='restock')return;
botState='farm';
if(botHomeMap&&botHomeMap!=='town')changeMap(botHomeMap,true);});}
function botSellTick(){
if(botBusy)return;
if(myData.map!=='town'){changeMap('town',true);return;}
const npc=(NPCS_STATE['town']||[]).find(n=>n.type==='sell');
if(!npc){botState='farm';return;}
const d=Math.hypot(npc.x-myData.x,npc.y-myData.y);
if(d>75){moveTarget={x:npc.x,y:npc.y};return;}
moveTarget=null;botBusy=true;
sellAllMaterials().finally(()=>{botBusy=false;
if(botState!=='sell')return;
botState='farm';
if(botHomeMap&&botHomeMap!=='town')changeMap(botHomeMap,true);});}

// ================= MARKET (BTC-like) =================
function openMarket(){MK.open=true;openModal('marketModal');loadMarketState();}
function closeMarket(){MK.open=false;closeModal('marketModal');}
async function loadMarketState(){
try{const d=await(await fetch('/api/market/state')).json();
if(d.success){MK.price=d.price;MK.hist=d.hist||[];
MK.position=d.position;MK.orders=d.orders||[];
drawChart();renderMkOrders();updateMkUI();}}catch(e){}}
async function placeOrder(side){
const qty=parseInt(document.getElementById('mk-qty').value)||1;
const limitV=document.getElementById('mk-limit').value;
const tpV=document.getElementById('mk-tp').value;
const slV=document.getElementById('mk-sl').value;
try{
const d=await apiPost('/api/market/order',{side,otype:limitV?'limit':'market',qty,
limit_price:limitV?parseFloat(limitV):null});
if(d.success){
if((tpV||slV)&&MK.position){
await apiPost('/api/market/tpsl',{tp:tpV?parseFloat(tpV):null,sl:slV?parseFloat(slV):null});}
showNotice(side==='long'?'📈 ส่งคำสั่งซื้อ (Long) แล้ว':'📉 ส่งคำสั่งขาย (Short) แล้ว');
loadMarketState();}
else showNotice(d.message);}catch(e){showNotice('❌ '+e.message);}}
async function closePosition(){
try{const d=await apiPost('/api/market/close',{});
if(!d.success)showNotice(d.message);}catch(e){showNotice('❌ '+e.message);}}
async function cancelAllOrders(){
try{for(const o of MK.orders)await apiPost('/api/market/cancel',{order_id:o.id});
loadMarketState();}catch(e){showNotice('❌ '+e.message);}}
async function cancelOrder(oid){
try{await apiPost('/api/market/cancel',{order_id:oid});loadMarketState();}catch(e){}}
function renderMkOrders(){
const el=document.getElementById('mk-orders');
let html='';
if(MK.position){
const p=MK.position;
const pnl=(MK.price-p.entry)*p.qty*(p.side==='long'?1:-1);
const pnlPct=pnl/(p.entry*p.qty)*100;
html+=`<div class="item-row" style="border-left-color:${p.side==='long'?'#26de81':'#fc5c65'}">
<div class="item-main"><div class="item-icon">${p.side==='long'?'📈':'📉'}</div>
<div><div>${p.side==='long'?'LONG':'SHORT'} ×${p.qty} @ ${p.entry.toFixed(2)}</div>
<div class="meta">Margin ${Math.round(p.margin)} G • TP:${p.tp||'-'} SL:${p.sl||'-'}</div></div></div>
<span class="price" style="color:${pnl>=0?'#7bed9f':'#ff6b6b'}">${pnl>=0?'+':''}${pnl.toFixed(0)} G (${pnlPct.toFixed(1)}%)</span></div>`;}
if(MK.orders.length){
MK.orders.forEach(o=>{html+=`<div class="item-row">
<div class="item-main"><div class="item-icon">📋</div>
<div><div>${o.side==='long'?'ซื้อ':'ขาย'} ×${o.qty} เมื่อราคา ${o.side==='long'?'≤':'≥'} ${o.limit}</div></div></div>
<button class="action-btn-sm" style="background:rgba(255,255,255,.1);color:#93a1b8" onclick="cancelOrder('${o.id}')">ยกเลิก</button></div>`;});}
if(!html)html='<div class="shop-note">ไม่มีสถานะ/ออเดอร์ — ใส่จำนวนแล้วกดซื้อ/ขายได้เลย</div>';
el.innerHTML=html;}
function updateMkUI(){
const pe=document.getElementById('mk-price');
pe.textContent=MK.price.toFixed(2);
const up=MK.price>=MK.lastPrice;
pe.style.color=up?'#7bed9f':'#ff6b6b';
const posEl=document.getElementById('mk-pos');
if(MK.position){const p=MK.position;
const pnl=(MK.price-p.entry)*p.qty*(p.side==='long'?1:-1);
posEl.innerHTML=`${p.side==='long'?'📈 LONG':'📉 SHORT'} <span style="color:${pnl>=0?'#7bed9f':'#ff6b6b'}">${pnl>=0?'+':''}${pnl.toFixed(0)} G</span>`;}
else posEl.textContent='';}
function drawChart(){
const cv=document.getElementById('mchart');
const c=cv.getContext('2d');
const W=cv.width,H=cv.height;
c.clearRect(0,0,W,H);
const hist=MK.hist.slice(-120);
if(hist.length<2)return;
const mn=Math.min(...hist)*.998,mx=Math.max(...hist)*1.002;
const px=i=>i/(hist.length-1)*(W-10)+5;
const py=v=>H-8-(v-mn)/(mx-mn)*(H-16);
c.strokeStyle='rgba(255,255,255,.06)';c.lineWidth=1;
for(let i=1;i<4;i++){c.beginPath();c.moveTo(0,H*i/4);c.lineTo(W,H*i/4);c.stroke();}
const grad=c.createLinearGradient(0,0,0,H);
grad.addColorStop(0,'rgba(0,255,204,.25)');grad.addColorStop(1,'rgba(0,255,204,0)');
c.beginPath();c.moveTo(px(0),py(hist[0]));
hist.forEach((v,i)=>c.lineTo(px(i),py(v)));
c.lineTo(px(hist.length-1),H);c.lineTo(px(0),H);c.closePath();
c.fillStyle=grad;c.fill();
c.beginPath();c.moveTo(px(0),py(hist[0]));
hist.forEach((v,i)=>c.lineTo(px(i),py(v)));
c.strokeStyle='#00ffcc';c.lineWidth=2;c.stroke();
if(MK.position){
const y=py(MK.position.entry);
c.strokeStyle='rgba(255,209,102,.7)';c.setLineDash([5,4]);
c.beginPath();c.moveTo(0,y);c.lineTo(W,y);c.stroke();c.setLineDash([]);
c.fillStyle='#ffd166';c.font='9px Kanit';c.textAlign='left';
c.fillText('entry '+MK.position.entry.toFixed(1),4,y-3);}
const lx=px(hist.length-1),ly=py(MK.price);
c.beginPath();c.arc(lx,ly,4,0,7);
c.fillStyle=MK.price>=MK.lastPrice?'#7bed9f':'#ff6b6b';c.fill();}

// ================= GAME LOOP =================
let lastT=performance.now();
function gameLoop(){
const now=performance.now();
const dt=Math.min(.05,(now-lastT)/1000);lastT=now;
if(FX.hitstop>0)FX.hitstop-=dt;else updateMovement(dt);
updateFX(dt);render(now);updateCooldownUI(now);
requestAnimationFrame(gameLoop);}
function updateMovement(dt) {
  if (!myData || myData.isDead) return;

  // ===== เดินไปหาของที่ตกพื้น =====
  if (walkPickupId) {
    const g = groundItems[walkPickupId];
    if (!g) {
      walkPickupId = null;
    } else {
      const d = Math.hypot(g.x - myData.x, g.y - myData.y);
      if (d <= 50) {
        socket.emit('pickup_item', { item_id: g.id });
        walkPickupId = null;
        moveTarget = null;
      } else {
        moveTarget = { x: g.x, y: g.y };
      }
    }
  }

  // ===== เดินไปหา NPC =====
  if (walkNPCId) {
    const n = (NPCS_STATE[myData.map] || []).find(v => v.id === walkNPCId);
    if (!n) {
      walkNPCId = null;
    } else {
      const d = Math.hypot(n.x - myData.x, n.y - myData.y);
      if (d <= 100) {
        openNPC(n);
        walkNPCId = null;
        moveTarget = null;
      } else {
        moveTarget = { x: n.x, y: n.y };
      }
    }
  }

  // ===== คำนวณทิศทางจากคีย์บอร์ด + D-pad =====
  let dx = 0, dy = 0;
  if (keys['w'] || keys['arrowup'])    dy -= 1;
  if (keys['s'] || keys['arrowdown'])  dy += 1;
  if (keys['a'] || keys['arrowleft'])  dx -= 1;
  if (keys['d'] || keys['arrowright']) dx += 1;
  dx += dpadDir.x;
  dy += dpadDir.y;

  const l = Math.hypot(dx, dy);

  if (l > 0) {
    // เดินด้วยคีย์บอร์ด / D-pad
    moveTarget = null;
    chaseId = null;
    walkNPCId = null;
    walkPickupId = null;

    const nextX = myData.x + (dx / l) * moveSpeed;
    const nextY = myData.y + (dy / l) * moveSpeed;

    if (myData.map === 'town') {
      // เมือง → เช็ค collision แยกแกน (กันติดมุม)
      if (!isBlockedInTown(nextX, myData.y)) myData.x = nextX;
      if (!isBlockedInTown(myData.x, nextY)) myData.y = nextY;
    } else {
      myData.x = clampN(nextX, 20, 780);
      myData.y = clampN(nextY, 20, 580);
    }
  }
  else if (moveTarget) {
    // เดินตามจุดที่คลิก
    const mdx = moveTarget.x - myData.x;
    const mdy = moveTarget.y - myData.y;
    const md = Math.hypot(mdx, mdy);

    if (md < 4) {
      moveTarget = null;
    } else {
      const step = Math.min(moveSpeed, md);
      const nextX = myData.x + (mdx / md) * step;
      const nextY = myData.y + (mdy / md) * step;

      if (myData.map === 'town') {
        if (!isBlockedInTown(nextX, myData.y)) myData.x = nextX;
        if (!isBlockedInTown(myData.x, nextY)) myData.y = nextY;
      } else {
        myData.x = nextX;
        myData.y = nextY;
      }
    }
  }
  else if (chaseId) {
    // ไล่ตามมอนสเตอร์
    const m = monsters[chaseId];
    if (!m || !m.alive) {
      chaseId = null;
    } else {
      const cdx = m.x - myData.x;
      const cdy = m.y - myData.y;
      const cd = Math.hypot(cdx, cdy);
      if (cd > ATTACK_RANGE - 12) {
        const step = Math.min(moveSpeed, cd - (ATTACK_RANGE - 12));
        myData.x += cdx / cd * step;
        myData.y += cdy / cd * step;
      }
    }
  }

  // ===== ส่งตำแหน่งไป server =====
  if (Date.now() - lastMoveSent > 80) {
    lastMoveSent = Date.now();
    socket.emit('move', {
      x: Math.round(myData.x * 10) / 10,
      y: Math.round(myData.y * 10) / 10,
      map: myData.map
    });
  }

  // ===== อัปเดตตำแหน่งผู้เล่นอื่น + มอนสเตอร์ (interpolation) =====
  for (const q of Object.values(allPlayers)) {
    if (q.sid === socket.id) continue;
    if (q.rx == null) { q.rx = q.x; q.ry = q.y; }
    q.rx += (q.x - q.rx) * 0.18;
    q.ry += (q.y - q.ry) * 0.18;
  }

  for (const m of Object.values(monsters)) {
    if (m.rx == null) { m.rx = m.x; m.ry = m.y; }
    m.rx += (m.x - m.rx) * 0.15;
    m.ry += (m.y - m.ry) * 0.15;
  }

  // ===== อัปเดต animation การเดิน =====
  const mvMe = Math.hypot(myData.x - (myData._px ?? myData.x), myData.y - (myData._py ?? myData.y));
  if (mvMe > 0.12) {
    myData._moving = true;
    myData._anim = (myData._anim || 0) + dt * 13;
  } else {
    myData._moving = false;
  }
  myData._px = myData.x;
  myData._py = myData.y;

  for (const q of Object.values(allPlayers)) {
    if (q.sid === socket.id) continue;
    const mv = Math.hypot(q.rx - (q._prx ?? q.rx), q.ry - (q._pry ?? q.ry));
    if (mv > 0.12) {
      q._moving = true;
      q._anim = (q._anim || 0) + dt * 13;
    } else {
      q._moving = false;
    }
    q._prx = q.rx;
    q._pry = q.ry;
  }

  for (const m of Object.values(monsters)) {
    const mv = Math.hypot(m.rx - (m._prx ?? m.rx), m.ry - (m._pry ?? m.ry));
    if (mv > 0.08) {
      m._moving = true;
      m._anim = (m._anim || 0) + dt * 13;
    } else {
      m._moving = false;
    }
    m._prx = m.rx;
    m._pry = m.ry;
  }
}
function updateFX(dt){
const s=FX.shake;
if(s.t>0){s.t-=dt;if(s.t<=0)s.power=0;}
if(FX.zoom>0)FX.zoom=Math.max(0,FX.zoom-dt*.6);
if(FX.white>0)FX.white=Math.max(0,FX.white-dt*2.2);
document.getElementById('fx-white').style.opacity=FX.white;
for(let i=FX.particles.length-1;i>=0;i--){const p=FX.particles[i];p.life-=dt;
if(p.life<=0){FX.particles.splice(i,1);continue;}
p.vy+=p.grav*dt;p.x+=p.vx*dt;p.y+=p.vy*dt;}
for(let i=FX.floaters.length-1;i>=0;i--){const f=FX.floaters[i];
f.life-=dt*1.1;f.y+=f.vy*dt;f.x+=f.vx*dt;f.vy*=.96;
if(f.life<=0)FX.floaters.splice(i,1);}
for(let i=FX.rings.length-1;i>=0;i--){const r=FX.rings[i];
r.life-=dt*1.8;r.r+=(r.max-r.r)*Math.min(1,dt*8);
if(r.life<=0)FX.rings.splice(i,1);}
for(let i=FX.shocks.length-1;i>=0;i--){const s2=FX.shocks[i];
s2.life-=dt*2.6;s2.r+=(s2.max-s2.r)*Math.min(1,dt*10);
if(s2.life<=0)FX.shocks.splice(i,1);}
for(let i=FX.slashes.length-1;i>=0;i--){const sl=FX.slashes[i];
sl.life-=dt*sl.dec;if(sl.life<=0)FX.slashes.splice(i,1);}}
function updateCooldownUI(now){
document.querySelectorAll('.quick-slot[data-skill]').forEach(el=>{
const until=+el.dataset.cdUntil||0;
const ov=el.querySelector('.cd-overlay');if(!ov)return;
if(until>now){ov.style.display='flex';ov.textContent=Math.ceil((until-now)/1000);}
else ov.style.display='none';});}



// ================= RENDER: ฉาก =================
const MAP_THEME={
town:{bg1:'#16281c',bg2:'#0d1a12',grid:'rgba(0,255,204,.05)',decor:'tree',col:'#1d3a26'},
forest:{bg1:'#0f2418',bg2:'#08150e',grid:'rgba(0,255,204,.05)',decor:'tree',col:'#16382a'},
meadow:{bg1:'#1c2e14',bg2:'#0e1a0a',grid:'rgba(0,255,204,.05)',decor:'tree',col:'#26401c'},
cave:{bg1:'#241d16',bg2:'#120e0a',grid:'rgba(255,209,102,.04)',decor:'rock',col:'#33291d'},
beach:{bg1:'#123240',bg2:'#081820',grid:'rgba(0,255,204,.05)',decor:'rock',col:'#1a4454'},
desert:{bg1:'#3a2e14',bg2:'#1c1608',grid:'rgba(255,209,102,.05)',decor:'rock',col:'#554420'},
dungeon:{bg1:'#1c1230',bg2:'#0d0918',grid:'rgba(167,139,250,.05)',decor:'rock',col:'#2a1f4a'},
swamp:{bg1:'#14261a',bg2:'#0a120c',grid:'rgba(0,255,204,.04)',decor:'tree',col:'#1e3a26'},
mine:{bg1:'#26201a',bg2:'#120e0a',grid:'rgba(255,209,102,.04)',decor:'rock',col:'#3a3226'},
temple:{bg1:'#2a2416',bg2:'#141008',grid:'rgba(255,209,102,.05)',decor:'rock',col:'#443a22'},
snowfield:{bg1:'#1a2a3a',bg2:'#0c141e',grid:'rgba(255,255,255,.05)',decor:'tree',col:'#2a4258'},
jungle:{bg1:'#0e2416',bg2:'#06120a',grid:'rgba(0,255,204,.05)',decor:'tree',col:'#143a22'},
volcano:{bg1:'#301410',bg2:'#180806',grid:'rgba(255,100,60,.05)',decor:'rock',col:'#4a2018'},
ghost_town:{bg1:'#1a1822',bg2:'#0c0b12',grid:'rgba(167,139,250,.05)',decor:'rock',col:'#2a2638'},
ruins:{bg1:'#26221a',bg2:'#12100a',grid:'rgba(255,209,102,.04)',decor:'rock',col:'#3c362a'},
labyrinth:{bg1:'#221a2a',bg2:'#100c14',grid:'rgba(167,139,250,.05)',decor:'rock',col:'#342a40'},
oasis:{bg1:'#1e3226',bg2:'#0e1812',grid:'rgba(0,255,204,.05)',decor:'tree',col:'#2c4a38'},
dragon_valley:{bg1:'#2c1418',bg2:'#160a0c',grid:'rgba(255,77,109,.05)',decor:'rock',col:'#442026'},
sky_tower:{bg1:'#141e34',bg2:'#0a0f1c',grid:'rgba(110,231,255,.05)',decor:'rock',col:'#1e3050'},
glacier:{bg1:'#14283a',bg2:'#0a141e',grid:'rgba(255,255,255,.06)',decor:'rock',col:'#204050'},
abyss:{bg1:'#120e1e',bg2:'#080610',grid:'rgba(167,139,250,.06)',decor:'rock',col:'#1e1832'},
hell:{bg1:'#321008',bg2:'#180804',grid:'rgba(255,77,40,.06)',decor:'rock',col:'#4e1a10'},
moonlight:{bg1:'#101a2e',bg2:'#080d18',grid:'rgba(200,220,255,.05)',decor:'tree',col:'#1c2c48'}};
const mapDecorCache={};
function getDecor(map){
if(mapDecorCache[map])return mapDecorCache[map];
let seed=[...map].reduce((a,c)=>a+c.charCodeAt(0),11);
const rnd=()=>{seed=(seed*9301+49297)%233280;return seed/233280;};
const arr=[];for(let i=0;i<30;i++)arr.push({x:rnd()*800,y:rnd()*600,s:12+rnd()*30});
mapDecorCache[map]=arr;return arr;}
function drawBackground() {
  // ถ้าอยู่เมือง → ไม่วาดพื้นหลังทึบ (ให้เห็นภาพ CSS ด้านหลัง)
  if (myData.map === 'town') {
    // วาดแค่เงาบาง ๆ หรือไม่วาดเลยก็ได้
    // ถ้าอยากให้มีเงาต้นไม้นิดหน่อย เปิดบรรทัดล่างได้
    /*
    ctx.fillStyle = 'rgba(0,0,0,0.15)';
    for (const o of getDecor('town')) {
      ctx.beginPath();
      ctx.arc(o.x, o.y, o.s * 0.7, 0, 7);
      ctx.fill();
    }
    */
    return; // ← สำคัญ: ไม่วาดพื้นหลังทึบ
  }

  // แมพอื่น ๆ วาดตามปกติ
  const th = MAP_THEME[myData.map] || MAP_THEME.town;
  const g = ctx.createLinearGradient(0, 0, 0, 600);
  g.addColorStop(0, th.bg1);
  g.addColorStop(1, th.bg2);

  ctx.fillStyle = g;
  ctx.fillRect(-400, -400, 1600, 1400);

  ctx.fillStyle = th.col || '#16382a';
  for (const o of getDecor(myData.map)) {
    ctx.beginPath();
    ctx.arc(o.x, o.y, o.s, 0, 7);
    ctx.fill();
  }
}
/* ===== เขตห้ามเดินในเมือง ===== */
const TOWN_BOUNDS = {
  minX: 80,
  maxX: 720,
  minY: 60,
  maxY: 540,

  blocked: [
    // ปราสาทใหญ่
    { x: 420, y: 40,  w: 220, h: 160 },
    // บ้านหลังคาแดงซ้ายบน
    { x: 140, y: 80,  w: 110, h: 90 },
    // บ้านหลังคาแดงซ้ายกลาง
    { x: 90,  y: 180, w: 100, h: 80 },
    // โรงสี (Windmill)
    { x: 620, y: 220, w: 110, h: 130 },
    // บ้านหลังคาน้ำเงินขวา
    { x: 520, y: 320, w: 100, h: 90 },
    // บ้านหลังคาน้ำเงินเล็ก
    { x: 480, y: 380, w: 80,  h: 70 },
    // ตลาด / เต็นท์
    { x: 160, y: 300, w: 90,  h: 70 },
    // ท่าเรือ (กันตกน้ำ)
    { x: 40,  y: 380, w: 180, h: 120 },
    // ขอบผาซ้าย
    { x: 20,  y: 200, w: 80,  h: 180 },
    // ขอบผาขวาล่าง
    { x: 650, y: 400, w: 120, h: 120 },
  ]
};

function isBlockedInTown(x, y) {
  if (!myData || myData.map !== 'town') return false;

  const b = TOWN_BOUNDS;
  if (x < b.minX || x > b.maxX || y < b.minY || y > b.maxY) return true;

  for (const box of b.blocked) {
    if (x > box.x && x < box.x + box.w &&
        y > box.y && y < box.y + box.h) {
      return true;
    }
  }
  return false;
}
function isBlockedInTown(x, y) {
  if (myData.map !== 'town') return false;

  const b = TOWN_BOUNDS;

  // กันตกแมพ
  if (x < b.minX || x > b.maxX || y < b.minY || y > b.maxY) {
    return true;
  }

  // กันชนบ้าน / สิ่งปลูกสร้าง
  for (const box of b.blocked) {
    if (x > box.x && x < box.x + box.w &&
        y > box.y && y < box.y + box.h) {
      return true;
    }
  }
  return false;
}
function drawGroundItems(now){
for(const g of Object.values(groundItems)){
const pulse=1+Math.sin(now/220+g.x)*.18;
ctx.fillStyle='rgba(0,0,0,.3)';
ctx.beginPath();ctx.ellipse(g.x,g.y+8,8,3,0,0,7);ctx.fill();
ctx.save();ctx.translate(g.x,g.y);ctx.rotate(now/900%(Math.PI*2));
ctx.fillStyle='#ffd166';ctx.strokeStyle='rgba(255,255,255,.5)';ctx.lineWidth=1;
ctx.beginPath();ctx.moveTo(0,-7*pulse);ctx.lineTo(6*pulse,0);
ctx.lineTo(0,7*pulse);ctx.lineTo(-6*pulse,0);ctx.closePath();ctx.fill();ctx.stroke();ctx.restore();
ctx.font='10px Kanit,sans-serif';ctx.textAlign='center';
ctx.strokeStyle='rgba(0,0,0,.7)';ctx.lineWidth=3;
ctx.strokeText(g.name,g.x,g.y-13);
ctx.fillStyle='#ffe9a8';ctx.fillText(g.name,g.x,g.y-13);}}

// ================= ตัวละคร CHIBI เต็มรูปแบบ =================
function rr(x,y,w,h,r){ctx.beginPath();ctx.moveTo(x+r,y);
ctx.arcTo(x+w,y,x+w,y+h,r);ctx.arcTo(x+w,y+h,x,y+h,r);
ctx.arcTo(x,y+h,x,y,r);ctx.arcTo(x,y,x+w,y,r);ctx.closePath();}

function jobStyle(job){
  const base={skin:'#ffe3c4',pants:'#3a3f4c',eye:'#2b2b33'};
  const S={
    Novice:    {body:['#e8b06a','#b97f3c'],hair:'#5a3b23',weapon:'none'},
    Warrior:   {body:['#7a8ba6','#4a5a74'],hair:'#5a3b23',weapon:'sword'},
    Swordsman: {body:['#7a8ba6','#4a5a74'],hair:'#5a3b23',weapon:'sword'},
    Knight:    {body:['#aab7c9','#5c6b82'],hair:'#3b2b1e',weapon:'sword',helm:true,cape:'#8b1e2d'},
    Mage:      {body:['#8b7ae0','#5a48b8'],hair:'#e9e7ff',weapon:'staff',hat:'#5a48b8'},
    Wizard:    {body:['#6a58d6','#3a2c8e'],hair:'#f2f0ff',weapon:'staff',hat:'#3a2c8e',cape:'#3a2c8e'},
    Archer:    {body:['#4a9e66','#2e6e44'],hair:'#7a4a22',weapon:'bow'},
    Hunter:    {body:['#3a8a56','#215c36'],hair:'#2e2418',weapon:'bow',cape:'#215c36'},
    Thief:     {body:['#5a6070','#3a3f4c'],hair:'#2b2b2b',weapon:'dagger'},
    Assassin:  {body:['#34394a','#20242f'],hair:'#15151a',weapon:'dagger',hood:'#20242f'},
    Acolyte:   {body:['#f4f1e6','#d0c9b2'],hair:'#caa24a',weapon:'mace'},
    Priest:    {body:['#fffaf0','#ded6bc'],hair:'#e8c96a',weapon:'mace',cape:'#c9b26a',halo:true},
  };
  return Object.assign({},base,S[job]||S.Novice);
}

function drawWeapon(type,x,y,t){
  ctx.save();ctx.translate(x,y);
  if(type==='sword'){
    ctx.rotate(-0.55+Math.sin(t/400)*0.06);
    ctx.fillStyle='#8b6b3a';ctx.fillRect(-1.5,-1,3,6);
    ctx.fillStyle='#d8dee9';ctx.fillRect(-4.5,-2,9,2.4);
    const g=ctx.createLinearGradient(-2,-18,2,0);
    g.addColorStop(0,'#f6faff');g.addColorStop(1,'#9fb2c8');
    ctx.fillStyle=g;ctx.beginPath();
    ctx.moveTo(-2,-2);ctx.lineTo(2,-2);ctx.lineTo(2,-13);
    ctx.lineTo(0,-17.5);ctx.lineTo(-2,-13);ctx.closePath();ctx.fill();
  }else if(type==='staff'){
    ctx.rotate(0.18);
    ctx.fillStyle='#7a5a34';ctx.fillRect(-1.4,-15,2.8,21);
    const glow=0.5+Math.sin(t/300)*0.25;
    ctx.fillStyle='#6ee7ff';ctx.shadowColor='#6ee7ff';ctx.shadowBlur=10*glow;
    ctx.beginPath();ctx.arc(0,-17.5,3.4,0,7);ctx.fill();ctx.shadowBlur=0;
    ctx.fillStyle='rgba(255,255,255,.8)';
    ctx.beginPath();ctx.arc(-1,-18.5,1,0,7);ctx.fill();
  }else if(type==='bow'){
    ctx.rotate(0.25);
    ctx.strokeStyle='#8a6a3c';ctx.lineWidth=2.4;
    ctx.beginPath();ctx.arc(0,0,9,-1.15,1.15);ctx.stroke();
    ctx.strokeStyle='#e8e8e8';ctx.lineWidth=1;
    ctx.beginPath();ctx.moveTo(3.7,-8.2);ctx.lineTo(3.7,8.2);ctx.stroke();
  }else if(type==='dagger'){
    ctx.rotate(-0.7+Math.sin(t/350)*0.1);
    ctx.fillStyle='#3a3f4c';ctx.fillRect(-1.2,-1,2.4,5);
    ctx.fillStyle='#c8d2e0';ctx.beginPath();
    ctx.moveTo(-1.5,-1);ctx.lineTo(1.5,-1);ctx.lineTo(0,-10);ctx.closePath();ctx.fill();
  }else if(type==='mace'){
    ctx.rotate(0.2);
    ctx.fillStyle='#8a6a3c';ctx.fillRect(-1.3,-9,2.6,12);
    const glow=0.6+Math.sin(t/320)*0.2;
    ctx.fillStyle='#ffd166';ctx.shadowColor='#ffe9a8';ctx.shadowBlur=8*glow;
    ctx.beginPath();ctx.arc(0,-11,3.2,0,7);ctx.fill();ctx.shadowBlur=0;
  }
  ctx.restore();
}

function drawChibi(x,y,st,isMe,dead,anim,moving){
  const t=performance.now();
  const bob=moving?Math.abs(Math.sin(anim))*2.4:Math.sin(t/520+x)*1.1;
  const legS=moving?Math.sin(anim)*3:0;
  const armS=moving?-Math.sin(anim)*2.4:Math.sin(t/520+x)*0.7;
  const gy=y-bob;
  const G=c=>dead?'#9aa0a8':c;
  ctx.fillStyle='rgba(0,0,0,.35)';
  ctx.beginPath();ctx.ellipse(x,y+15,10,3.6,0,0,7);ctx.fill();
  if(st.cape&&!dead){
    ctx.fillStyle=G(st.cape);
    ctx.beginPath();
    ctx.moveTo(x-8,gy-6);ctx.quadraticCurveTo(x-11.5,gy+8,x-7+legS*.3,gy+13);
    ctx.lineTo(x+7-legS*.3,gy+13);ctx.quadraticCurveTo(x+11.5,gy+8,x+8,gy-6);
    ctx.closePath();ctx.fill();
  }
  ctx.fillStyle=G(st.pants);
  const lift1=moving?Math.max(0,legS)*-1.6:0, lift2=moving?Math.max(0,-legS)*-1.6:0;
  rr(x-5.4+legS*.45,gy+8+lift1,4.2,7.5,2);ctx.fill();
  rr(x+1.2-legS*.45,gy+8+lift2,4.2,7.5,2);ctx.fill();
  const bg=ctx.createLinearGradient(0,gy-6,0,gy+12);
  bg.addColorStop(0,G(st.body[0]));bg.addColorStop(1,G(st.body[1]));
  ctx.fillStyle=bg;
  rr(x-8.5,gy-6,17,16,6);ctx.fill();
  ctx.strokeStyle='rgba(0,0,0,.28)';ctx.lineWidth=1.4;ctx.stroke();
  ctx.fillStyle='rgba(0,0,0,.2)';ctx.fillRect(x-8.5,gy+3,17,3);
  ctx.fillStyle=G(st.hair||'#888');ctx.fillRect(x-2,gy+3.4,4,2.2);
  ctx.fillStyle=G(st.body[1]);
  ctx.beginPath();ctx.arc(x-9.5,gy+1+armS,2.8,0,7);ctx.fill();
  ctx.beginPath();ctx.arc(x+9.5,gy+1-armS,2.8,0,7);ctx.fill();
  ctx.fillStyle=G(st.skin||'#ffe3c4');
  ctx.beginPath();ctx.arc(x-9.5,gy+3.2+armS,1.7,0,7);ctx.fill();
  ctx.beginPath();ctx.arc(x+9.5,gy+3.2-armS,1.7,0,7);ctx.fill();
  if(st.weapon&&st.weapon!=='none'&&!dead)drawWeapon(st.weapon,x+11,gy+2-armS,t);
  const hy=gy-11;
  const hg=ctx.createRadialGradient(x-2,hy-3,2,x,hy,9);
  hg.addColorStop(0,'#fff2e2');hg.addColorStop(1,G(st.skin||'#ffe3c4'));
  ctx.fillStyle=hg;
  ctx.beginPath();ctx.arc(x,hy,8.8,0,7);ctx.fill();
  ctx.strokeStyle='rgba(0,0,0,.25)';ctx.lineWidth=1.3;ctx.stroke();
  if(st.hood){
    ctx.fillStyle=G(st.hood);
    ctx.beginPath();ctx.arc(x,hy,9.6,Math.PI*0.82,Math.PI*2.18);ctx.fill();
    ctx.fillRect(x-9.6,hy-2.5,19.2,3.6);
    ctx.fillStyle='rgba(0,0,0,.3)';ctx.fillRect(x-6.5,hy-4.5,13,2.6);
  }else if(st.helm){
    ctx.fillStyle=G('#b8c4d6');
    ctx.beginPath();ctx.arc(x,hy-0.5,9.2,Math.PI,Math.PI*2);ctx.fill();
    ctx.fillRect(x-9.2,hy-1,18.4,2.6);
    ctx.fillStyle=G('#ffd166');ctx.fillRect(x-1,hy-9,2,6.5);
  }else{
    ctx.fillStyle=G(st.hair||'#5a3b23');
    ctx.beginPath();ctx.arc(x,hy-0.8,9.1,Math.PI*1.02,Math.PI*1.98);ctx.fill();
    ctx.beginPath();
    ctx.moveTo(x-9,hy-1);
    ctx.quadraticCurveTo(x-5,hy-5.5,x-1.5,hy-3.2);
    ctx.quadraticCurveTo(x+2,hy-6,x+9,hy-1.5);
    ctx.lineTo(x+9,hy-4);ctx.quadraticCurveTo(x,hy-11.5,x-9,hy-4);
    ctx.closePath();ctx.fill();
    ctx.fillRect(x-9.4,hy-2,2.4,6.5);ctx.fillRect(x+7,hy-2,2.4,6.5);
  }
  if(st.hat){
    ctx.fillStyle=G(st.hat);
    ctx.beginPath();
    ctx.moveTo(x-10,hy-4);ctx.quadraticCurveTo(x,hy-8,x+10,hy-4);
    ctx.lineTo(x+8,hy-6.5);ctx.lineTo(x-8,hy-6.5);ctx.closePath();ctx.fill();
    ctx.beginPath();
    ctx.moveTo(x-7.5,hy-5.5);ctx.quadraticCurveTo(x-1,hy-9,x+2,hy-19);
    ctx.quadraticCurveTo(x+5,hy-9,x+7.5,hy-5.5);ctx.closePath();ctx.fill();
    ctx.fillStyle=G('#ffd166');ctx.beginPath();ctx.arc(x+2,hy-19.5,2,0,7);ctx.fill();
  }
  if(st.halo&&!dead){
    ctx.strokeStyle='#ffe9a8';ctx.lineWidth=2;
    ctx.beginPath();ctx.ellipse(x,hy-13.5,6,2,0,0,7);ctx.stroke();
  }
  if(dead){
    ctx.strokeStyle='#4a4a4a';ctx.lineWidth=1.6;
    [-3.4,3.4].forEach(dx=>{
      ctx.beginPath();
      ctx.moveTo(x+dx-1.8,hy-1.6);ctx.lineTo(x+dx+1.8,hy+1.8);
      ctx.moveTo(x+dx+1.8,hy-1.6);ctx.lineTo(x+dx-1.8,hy+1.8);ctx.stroke();});
    ctx.beginPath();ctx.arc(x,hy+5,1.6,Math.PI,Math.PI*2);ctx.stroke();
  }else{
    const blink=((t+x*97)%3600)<90;
    [-3.3,3.3].forEach(dx=>{
      if(blink){ctx.strokeStyle=st.eye;ctx.lineWidth=1.4;
        ctx.beginPath();ctx.moveTo(x+dx-1.7,hy-0.2);ctx.lineTo(x+dx+1.7,hy-0.2);ctx.stroke();}
      else{
        ctx.fillStyle='#fff';ctx.beginPath();ctx.ellipse(x+dx,hy-0.2,2,2.4,0,0,7);ctx.fill();
        ctx.fillStyle=st.eye;ctx.beginPath();ctx.arc(x+dx,hy+0.3,1.15,0,7);ctx.fill();
        ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(x+dx-0.5,hy-0.6,0.55,0,7);ctx.fill();}});
    ctx.strokeStyle='#b06a4a';ctx.lineWidth=1.2;
    ctx.beginPath();ctx.arc(x,hy+3,1.8,0.15*Math.PI,0.85*Math.PI);ctx.stroke();
    if(isMe){ctx.fillStyle='rgba(255,130,140,.35)';
      ctx.beginPath();ctx.arc(x-5.4,hy+2.6,1.5,0,7);ctx.fill();
      ctx.beginPath();ctx.arc(x+5.4,hy+2.6,1.5,0,7);ctx.fill();}
  }
}

function drawPlayer(x,y,name,level,hp,maxHp,isMe,dead,job,anim,moving){
  const st=jobStyle(job||'Novice');
  if(isMe&&!dead){ctx.save();ctx.shadowColor='rgba(0,255,204,.55)';ctx.shadowBlur=10;}
  drawChibi(x,y,st,isMe,dead,anim||0,moving);
  if(isMe&&!dead)ctx.restore();
  const bob=moving?Math.abs(Math.sin(anim||0))*2.4:Math.sin(performance.now()/520+x)*1.1;
  const hy=y-bob-11;
  if(!dead&&maxHp){
    const bw=46,by=hy-17;
    ctx.fillStyle='rgba(0,0,0,.55)';rr(x-bw/2,by,bw,5,2.5);ctx.fill();
    ctx.fillStyle=isMe?'#7bed9f':'#7dc4ff';
    if(hp>0){rr(x-bw/2,by,bw*Math.max(0,hp/maxHp),5,2.5);ctx.fill();}
  }
  ctx.font='bold 11px Kanit,sans-serif';ctx.textAlign='center';
  ctx.fillStyle=isMe?'#00ffcc':'#dbe9ff';
  ctx.strokeStyle='rgba(0,0,0,.65)';ctx.lineWidth=3;
  ctx.strokeText(name+' Lv.'+level,x,hy-24);
  ctx.fillText(name+' Lv.'+level,x,hy-24);
}

// ================= มอนสเตอร์ SLIME เด้งๆ =================
function drawMonsterBody(m,col){
  const x=m.rx,y=m.ry;
  const r=m.boss?24:13;
  const t=performance.now();
  const sq=1+Math.sin(t/240+x*.07)*.06;
  const w=r*(2-sq),h=r*sq;
  if(m.enraged){
    ctx.fillStyle='rgba(255,110,40,'+(0.14+Math.sin(t/140)*0.06)+')';
    ctx.beginPath();ctx.arc(x,y,r*1.8,0,7);ctx.fill();
  }
  ctx.fillStyle='rgba(0,0,0,.32)';
  ctx.beginPath();ctx.ellipse(x,y+r+4,w*.85,4,0,0,7);ctx.fill();
  const g=ctx.createRadialGradient(x-w*.3,y-h*.5,2,x,y,r*1.2);
  if(col){g.addColorStop(0,'#ffffff');g.addColorStop(1,col);}
  else if(m.boss){g.addColorStop(0,'#ff8a7a');g.addColorStop(1,'#a4262c');}
  else if(m.enraged){g.addColorStop(0,'#ffb27a');g.addColorStop(1,'#c0561f');}
  else{g.addColorStop(0,'#e0929f');g.addColorStop(1,'#8e3d46');}
  ctx.fillStyle=g;
  ctx.beginPath();ctx.ellipse(x,y+h*.06,w,h,0,0,7);ctx.fill();
  ctx.beginPath();ctx.arc(x-w*.45,y-h*.5,w*.34,0,7);ctx.fill();
  ctx.beginPath();ctx.arc(x+w*.05,y-h*.75,w*.28,0,7);ctx.fill();
  ctx.beginPath();ctx.arc(x+w*.5,y-h*.42,w*.3,0,7);ctx.fill();
  ctx.strokeStyle='rgba(0,0,0,.32)';ctx.lineWidth=2;
  ctx.beginPath();ctx.ellipse(x,y+h*.06,w,h,0,0,7);ctx.stroke();
  if(m.boss){
    ctx.fillStyle='#e8d9b0';
    [-1,1].forEach(s=>{
      ctx.beginPath();
      ctx.moveTo(x+s*w*.55,y-h*.72);
      ctx.quadraticCurveTo(x+s*w*.95,y-h*1.6,x+s*w*.42,y-h*1.9);
      ctx.quadraticCurveTo(x+s*w*.48,y-h*1.15,x+s*w*.22,y-h*.82);
      ctx.closePath();ctx.fill();
      ctx.strokeStyle='rgba(0,0,0,.3)';ctx.lineWidth=1.2;ctx.stroke();});
    ctx.beginPath();ctx.moveTo(x-4,y-h*.98);ctx.lineTo(x,y-h*2.05);ctx.lineTo(x+4,y-h*.98);ctx.closePath();ctx.fill();
    ctx.strokeStyle='rgba(0,0,0,.3)';ctx.lineWidth=1;ctx.stroke();
  }
  const lookX=clampN(((myData?myData.x:x)-x)*0.05,-2.4,2.4);
  const lookY=clampN(((myData?myData.y:y)-y)*0.04,-1.8,1.8);
  const ey=y-h*.12,ex=w*.42,er=m.boss?5.2:3.5;
  [-1,1].forEach(s=>{
    ctx.fillStyle='#fff';
    ctx.beginPath();ctx.ellipse(x+s*ex,ey,er,er*1.15,0,0,7);ctx.fill();
    ctx.fillStyle=m.aggro?'#c0392b':'#2b2b33';
    ctx.beginPath();ctx.arc(x+s*ex+lookX,ey+lookY,er*.5,0,7);ctx.fill();
    ctx.fillStyle='#fff';
    ctx.beginPath();ctx.arc(x+s*ex+lookX-er*.25,ey+lookY-er*.3,er*.17,0,7);ctx.fill();});
  if(m.aggro){
    ctx.strokeStyle='#7a1f1f';ctx.lineWidth=2;
    ctx.beginPath();ctx.moveTo(x-ex-er,ey-er-3);ctx.lineTo(x-ex+er*.5,ey-er+0.5);ctx.stroke();
    ctx.beginPath();ctx.moveTo(x+ex+er,ey-er-3);ctx.lineTo(x+ex-er*.5,ey-er+0.5);ctx.stroke();}
  ctx.strokeStyle='rgba(0,0,0,.55)';ctx.lineWidth=1.6;
  if(m.boss||m.enraged){
    ctx.beginPath();ctx.arc(x,y+h*.1,w*.34,0.12*Math.PI,0.88*Math.PI);ctx.stroke();
    ctx.fillStyle='#fff';
    [[-0.2,-0.12,-0.04],[0.06,0.14,0.22]].forEach(a=>{
      ctx.beginPath();
      ctx.moveTo(x+w*a[0],y+h*.26);ctx.lineTo(x+w*a[1],y+h*.46);ctx.lineTo(x+w*a[2],y+h*.26);
      ctx.closePath();ctx.fill();});
  }else{
    ctx.beginPath();ctx.arc(x,y+h*.12,w*.2,0.15*Math.PI,0.85*Math.PI);ctx.stroke();}
}

// ================= NPC ตัวละครเดินได้ =================
function drawNPCs(now){
  const npcStyles={
    shop:{body:['#e6a23c','#b5761f'],hair:'#d8d8d8',weapon:'none',apron:true},
    sell:{body:['#6e7b8f','#4a5468'],hair:'#9fb2c8',weapon:'none',antenna:true},
    job: {body:['#8b6bd9','#5a3fa8'],hair:'#f0e8ff',weapon:'staff',hat:'#5a3fa8'}};
  for(const n of (NPCS_STATE[myData.map]||[])){
    const st=Object.assign({skin:'#ffe3c4',pants:'#3a3f4c',eye:'#2b2b33'},npcStyles[n.type]||npcStyles.shop);
    ctx.save();
    ctx.shadowColor='rgba(255,209,102,.45)';ctx.shadowBlur=9;
    drawChibi(n.x,n.y+2,st,false,false,now/300+n.x,false);
    ctx.restore();
    const bob=Math.sin(now/520+n.x)*1.1;
    const hy=n.y+2-bob-11;
    if(st.antenna){
      ctx.strokeStyle='#9fb2c8';ctx.lineWidth=1.5;
      ctx.beginPath();ctx.moveTo(n.x,hy-8.5);ctx.lineTo(n.x,hy-15);ctx.stroke();
      ctx.fillStyle='#ff6b6b';ctx.beginPath();ctx.arc(n.x,hy-16.5,2.2,0,7);ctx.fill();
      ctx.fillStyle='rgba(255,107,107,'+(0.25+Math.sin(now/200)*0.15)+')';
      ctx.beginPath();ctx.arc(n.x,hy-16.5,5,0,7);ctx.fill();}
    if(st.apron){
      ctx.fillStyle='#fffaf0';
      ctx.beginPath();
      ctx.moveTo(n.x-5,n.y-bob-2);ctx.lineTo(n.x+5,n.y-bob-2);
      ctx.lineTo(n.x+4,n.y-bob+9);ctx.lineTo(n.x-4,n.y-bob+9);ctx.closePath();ctx.fill();}
    ctx.font='bold 11px Kanit,sans-serif';ctx.textAlign='center';
    ctx.strokeStyle='rgba(0,0,0,.7)';ctx.lineWidth=3;
    ctx.strokeText(n.name,n.x,hy-24);
    ctx.fillStyle='#ffd166';ctx.fillText(n.name,n.x,hy-24);
    ctx.font='10px Kanit,sans-serif';ctx.fillStyle='#00ffcc';
    ctx.fillText('💬 คลิกคุย',n.x,n.y+30);
  }
}

// ================= วาด entities + FX =================
function drawEntities(now){
  for(const m of Object.values(monsters)){
    if(m.dying){
      const age=(now-m.fadeT)/600;
      if(age<1){ctx.globalAlpha=1-age;drawMonsterBody(m,'#888');ctx.globalAlpha=1;}
      continue;
    }
    if(!m.alive)continue;
    drawMonsterBody(m,null);
    if(m.flashT&&now-m.flashT<120){ctx.globalAlpha=.7;drawMonsterBody(m,'#fff');ctx.globalAlpha=1;}
    const bw=m.boss?70:46,by=m.ry-(m.boss?44:30);
    ctx.fillStyle='rgba(0,0,0,.55)';rr(m.rx-bw/2,by,bw,5,2.5);ctx.fill();
    ctx.fillStyle=m.boss?'#ffd166':'#ff6b6b';
    if(m.hp>0){rr(m.rx-bw/2,by,bw*Math.max(0,m.hp/m.max_hp),5,2.5);ctx.fill();}
    ctx.font=(m.boss?'bold 12px':'11px')+' Kanit,sans-serif';ctx.textAlign='center';
    ctx.fillStyle='#fff';ctx.strokeStyle='rgba(0,0,0,.65)';ctx.lineWidth=3;
    ctx.strokeText(m.name,m.rx,by-6);ctx.fillText(m.name,m.rx,by-6);
    if(m.enraged){ctx.font='13px sans-serif';ctx.fillText('😡',m.rx+(m.boss?32:24),by-8);}
  }
  for(const q of Object.values(allPlayers)){
    if(q.sid===socket.id)continue;
    if(q.rx==null){q.rx=q.x;q.ry=q.y;}
    drawPlayer(q.rx,q.ry,q.username,q.level,q.hp,q.max_hp,false,false,q.job,q._anim||0,q._moving);
  }
  if(myData){
    if(!myData.isDead)drawPlayer(myData.x,myData.y,myData.username,myData.level,myData.hp,myData.maxHp,true,false,myData.job,myData._anim||0,myData._moving);
    else drawPlayer(myData.x,myData.y,'☠ '+myData.username,myData.level,0,myData.maxHp,true,true,myData.job,0,false);
  }
  const t=chaseId?monsters[chaseId]:null;
  if(t&&t.alive){
    ctx.strokeStyle='rgba(255,209,102,.85)';ctx.lineWidth=2;
    ctx.beginPath();ctx.arc(t.rx,t.ry,(t.boss?30:19)+3+Math.sin(now/180)*2,0,7);ctx.stroke();
  }
}
function drawFXLayer(){
for(const r of FX.rings){ctx.globalAlpha=Math.max(0,r.life)*.9;
ctx.strokeStyle=r.color;ctx.lineWidth=r.lw;
ctx.beginPath();ctx.arc(r.x,r.y,r.r,0,7);ctx.stroke();}
for(const s of FX.shocks){ctx.globalAlpha=Math.max(0,s.life)*.5;
ctx.strokeStyle=s.color;ctx.lineWidth=2;
ctx.beginPath();ctx.arc(s.x,s.y,s.r,0,7);ctx.stroke();}
ctx.lineCap='round';
for(const s of FX.slashes){ctx.globalAlpha=Math.max(0,s.life);
ctx.strokeStyle=s.color;ctx.lineWidth=s.w;
ctx.beginPath();
ctx.moveTo(s.x-Math.cos(s.ang)*s.len/2,s.y-Math.sin(s.ang)*s.len/2);
ctx.lineTo(s.x+Math.cos(s.ang)*s.len/2,s.y+Math.sin(s.ang)*s.len/2);ctx.stroke();}
ctx.lineCap='butt';
for(const p of FX.particles){ctx.globalAlpha=Math.max(0,p.life/p.max);
ctx.fillStyle=p.color;ctx.fillRect(p.x-p.size/2,p.y-p.size/2,p.size,p.size);}
for(const f of FX.floaters){ctx.globalAlpha=Math.max(0,Math.min(1,f.life*1.4));
ctx.font=(f.crit?'bold ':'')+f.size+'px Kanit,sans-serif';ctx.textAlign='center';
ctx.strokeStyle='rgba(0,0,0,.7)';ctx.lineWidth=3;
ctx.strokeText(f.txt,f.x,f.y);ctx.fillStyle=f.color;ctx.fillText(f.txt,f.x,f.y);}
ctx.globalAlpha=1;}
function render(now) {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, 800, 600);
  
  if (!myData) return;

  ctx.save();
  
  const s = FX.shake; 
  let ox = 0, oy = 0;
  if (s.t > 0) {
    const k = s.power * (s.t / Math.max(.001, s.dur));
    ox = (Math.random() - .5) * k; 
    oy = (Math.random() - .5) * k;
  }
  
  const z = 1 + FX.zoom;

  // ===== กล้อง =====
  if (myData.map === 'town') {
    // 🏙️ เมือง → กล้องนิ่งตรงกลาง ไม่ตามตัวละคร
    ctx.translate(400 + ox, 300 + oy);
    ctx.scale(z, z);
    ctx.translate(-400, -300);   // ล็อกที่จุดกลางแมพ (400, 300)
  } else {
    // 🗺️ แมพอื่น → กล้องตามตัวละครตามปกติ
    ctx.translate(400 + ox, 300 + oy);
    ctx.scale(z, z);
    ctx.translate(-myData.x, -myData.y);
  }

  drawBackground();
  drawGroundItems(now);
  drawNPCs(now);
  drawEntities(now);
  drawFXLayer();

  ctx.restore();
}
/* ============================================
   🌠 LUMIVARA — SkyFall Monster Spawner
   มอนสเตอร์ตกจากท้องฟ้า!
   ============================================ */
const SkyFall = (() => {
  const GRAVITY = 2200;       // แรงโน้มถ่วง px/s²
  const LAND_TIME = 0.45;     // เวลาจังหวะตกกระแทก
  const MAX_FALLING = 6;      // กันฝนมอนตอนโหลดแมพเปลี่ยนแมพ

  const items = [], particles = [], rings = [];
  let shakeTime = 0, shakePower = 0, enabled = true;

  // ฟังก์ชันวาดมอนของเกมคุณ (ตั้งค่าทีหลังได้)
  // SkyFall.painter = (ctx, mob, x, y) => { ...วาดมอน... }
  let painter = null;

  function burstDust(x, y, color) {
    for (let i = 0; i < 16; i++) {
      const dir = Math.random() < .5 ? -1 : 1;
      particles.push({
        x, y,
        vx: dir * (60 + Math.random() * 200),
        vy: -(40 + Math.random() * 160),
        life: .45 + Math.random() * .4, t: 0,
        r: 2 + Math.random() * 3, color
      });
    }
  }

  function drop(mob, groundX, groundY) {
    if (!enabled) return false;
    if (items.length >= MAX_FALLING) return false; // เกินลิมิต → ให้ปรากฏปกติ
    mob._skyfall = true;              // 🚩 ยังไม่ให้วาด/ขยับ/โดนตีบนพื้น
    mob.x = groundX; mob.y = groundY;
    items.push({
      mob, groundX, groundY,
      x: groundX + (Math.random() - .5) * 60,
      y: -90 - Math.random() * 80,
      vy: -60,
      rot: (Math.random() - .5) * 1.2,
      rotV: (Math.random() - .5) * 7,
      state: 'fall', t: 0,
      color: mob.boss ? '#ff6b4a' : '#ffd27a'
    });
    return true;
  }

  function update(dt) {
    if (shakeTime > 0) shakeTime -= dt;

    for (let i = items.length - 1; i >= 0; i--) {
      const f = items[i];
      if (f.state === 'fall') {
        f.vy += GRAVITY * dt;
        f.y += f.vy * dt;
        f.rot += f.rotV * dt;
        // หางไฟตอนร่วง
        particles.push({
          x: f.x + (Math.random() - .5) * 22, y: f.y - 8,
          vx: (Math.random() - .5) * 30, vy: -30 - Math.random() * 40,
          life: .3, t: 0, r: 2 + Math.random() * 2, color: f.color
        });
        if (f.y >= f.groundY) {          // 💥 ถึงพื้น!
          f.y = f.groundY; f.state = 'land'; f.t = 0;
          burstDust(f.groundX, f.groundY, '#c9a86b');
          rings.push({ x: f.groundX, y: f.groundY, t: 0, life: .4 });
          shakeTime = f.mob.boss ? .3 : .16;
          shakePower = f.mob.boss ? 9 : 5;
          try { SND?.play?.('monster_land'); } catch (e) {}
        }
      } else {                            // จังหวะตกกระแทก → ค่อยตั้งศรี
        f.t += dt;
        f.rot *= Math.max(0, 1 - f.t * 6);
        if (f.t >= LAND_TIME) {
          f.mob._skyfall = false;         // 🔓 ปล่อยให้มอนทำงานปกติ
          items.splice(i, 1);
        }
      }
    }
    for (let i = particles.length - 1; i >= 0; i--) {
      const p = particles[i];
      p.t += dt; p.x += p.vx * dt; p.y += p.vy * dt; p.vy += 500 * dt;
      if (p.t >= p.life) particles.splice(i, 1);
    }
    for (let i = rings.length - 1; i >= 0; i--)
      if ((rings[i].t += dt) >= rings[i].life) rings.splice(i, 1);
  }

  function draw(ctx) {
    // เงาบนพื้น (ใหญ่ขึ้นเรื่อยๆ ตอนมอนใกล้พื้น)
    for (const f of items) {
      const h = Math.max(0, f.groundY - f.y);
      const prog = 1 - Math.min(1, h / 400);
      ctx.save();
      ctx.globalAlpha = .1 + prog * .4;
      ctx.fillStyle = '#000';
      ctx.beginPath();
      ctx.ellipse(f.groundX, f.groundY, 14 + prog * 16, 5 + prog * 6, 0, 0, 7);
      ctx.fill();
      ctx.restore();
    }
    // ตัวมอน (หมุนตอนร่วง)
    for (const f of items) {
      ctx.save();
      ctx.translate(f.x, f.y - 16);
      ctx.rotate(f.rot);
      if (painter) painter(ctx, f.mob, 0, 0);
      else { // fallback: ใช้อีโมจิของมอน
        ctx.font = '26px serif';
        ctx.textAlign = 'center';
        ctx.fillText(f.mob.icon || f.mob.emoji || '👾', 0, 8);
      }
      ctx.restore();
    }
    // คลื่นกระแทก
    for (const r of rings) {
      const k = r.t / r.life;
      ctx.save();
      ctx.globalAlpha = (1 - k) * .8;
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2.5 * (1 - k);
      ctx.beginPath();
      ctx.ellipse(r.x, r.y, 50 * k, 50 * k * .45, 0, 0, 7);
      ctx.stroke();
      ctx.restore();
    }
    // ฝุ่น/ประกาย
    for (const p of particles) {
      const k = 1 - p.t / p.life;
      ctx.save();
      ctx.globalAlpha = k;
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(p.x, p.y, Math.max(.1, p.r * k), 0, 7);
      ctx.fill();
      ctx.restore();
    }
  }

  function applyShake(ctx) {
    if (shakeTime > 0)
      ctx.translate((Math.random() - .5) * shakePower * 2,
                    (Math.random() - .5) * shakePower * 2);
  }

  // 🪝 แถม: ดัก array มอน — push มอนตัวไหนเข้ามา = ตกจากฟ้าอัตโนมัติ
  function watch(arr) {
    const origPush = arr.push.bind(arr);
    arr.push = (...mobs) => {
      const r = origPush(...mobs);
      for (const m of mobs) if (!m._skyfall) drop(m, m.x, m.y);
      return r;
    };
  }

  return { drop, update, draw, applyShake, watch,
           set painter(fn) { painter = fn; },
           get enabled() { return enabled; },
           set enabled(v) { enabled = v; } };
})();
// ฟังก์ชันเรียกฉากคัตซีนอนิเมะ
function playAnimeCutin(skillName, jobName) {
  const cutin = document.getElementById('anime-cutin');
  const nameEl = document.getElementById('cutin-skill-name');
  const charEl = document.getElementById('cutin-char-name');
  const avatarEl = document.getElementById('cutin-avatar');
  
  if (!cutin) return;

  nameEl.textContent = skillName;
  charEl.textContent = myData.username || "Hero";
  
  // เปลี่ยนไอคอนตามอาชีพ
  const icons = { Swordsman: "⚔️", Mage: "🔮", Archer: "🏹", Thief: "🗡️", Acolyte: "✨", Knight: "🛡️", Wizard: "🌟", Hunter: "🎯", Assassin: "🥷", Priest: "⛪", Novice: "🌱" };
  avatarEl.textContent = icons[myData.job] || "⚔️";

  // เปิดอนิเมชัน
  cutin.classList.remove('active');
  void cutin.offsetWidth; // trigger reflow
  cutin.classList.add('active');

  // สั่นจอเพิ่มความมันส์
  if (typeof triggerScreenShake === 'function') {
    triggerScreenShake(12, 0.4);
  }

  // ปิดฉากคัตซีนอัตโนมัติหลังผ่านไป 1.1 วินาที
  setTimeout(() => {
    cutin.classList.remove('active');
  }, 1100);
}

// ผูกเข้ากับระบบกดใช้สกิลเดิมของคุณ
// (ในการใช้งานจริง ให้เรียก playAnimeCutin("ชื่อสกิล") ไว้ข้างในฟังก์ชันกดใช้สกิลฝั่ง JS)
function toggleHudMenu() {
  const menu = document.getElementById('hud-menu');
  const btn = document.getElementById('menu-toggle-btn');
  if (!menu || !btn) return;

  menu.classList.toggle('collapsed');

  if (menu.classList.contains('collapsed')) {
    btn.textContent = '☰';
    btn.title = 'ขยายเมนู';
  } else {
    btn.textContent = '✕';
    btn.title = 'ย่อเมนู';
  }
}

// เริ่มต้นย่อเมนูไว้ (ถ้าต้องการ)
document.addEventListener('DOMContentLoaded', () => {
  // ถ้าอยากให้เริ่มต้นย่ออยู่แล้ว ให้ uncomment บรรทัดล่าง
  // document.getElementById('hud-menu')?.classList.add('collapsed');
});

// อัปเดตข้อมูลใน Modal ธนาคาร
function refreshBankModal() {
  document.getElementById('bank-pocket-gold').innerText = (myData.gold || 0) + ' G';
  document.getElementById('bank-vault-gold').innerText = (myData.vault_gold || 0) + ' G'; // (หรือดึงจากข้อมูลตัวละคร)
}

// ผูกเข้ากับระบบ Modal เดิม
const originalRefreshModal = window.refreshModal || function(){};
window.refreshModal = function(id) {
  originalRefreshModal(id);
  if(id === 'bankModal') refreshBankModal();
};

async function bankDeposit() {
  const amt = parseInt(document.getElementById('bank-amount').value) || 0;
  if (amt <= 0) return;
  showNotice('🏦 ระบบธนาคารกำลังพัฒนา เร็วๆ นี้!');
}

async function bankWithdraw() {
  const amt = parseInt(document.getElementById('bank-amount').value) || 0;
  if (amt <= 0) return;
  showNotice('🏦 ระบบธนาคารกำลังพัฒนา เร็วๆ นี้!');
}
function updateTownBackground(mapName) {
  const wrapper = document.getElementById('game-wrapper');
  if (!wrapper) return;

  if (mapName === 'town') {
    wrapper.classList.add('town-bg');
  } else {
    wrapper.classList.remove('town-bg');
  }
}