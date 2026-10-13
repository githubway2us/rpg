/* ============================================================
   skydrop.js — มอนเกิดแบบ "หล่นจากหน้าจอ" ให้ Lumivara Online
   เฟส: พุ่งชิดกล้อง (ตัวยักษ์) → หล่นหดเข้าฉาก → ดิ่งกระแทก → ยู่ตัวเด้ง
   วิธีใช้: ใส่ต่อจาก <script> ของเกม (ต้องอยู่หลังสุด)
       <script src="skydrop.js"></script>
   ไม่ต้องแก้โค้ดเดิม — hook ทับ updateFX / drawEntities
   ปิด/เปิด: SkyDrop.enabled = false / true
   ============================================================ */
(() => {
'use strict';
const EM = 0.34, FA = 1.05, DR = 0.24, IM = 0.5, HOVER = 80, MAXF = 8;
const falls = [], cracks = [];
const R = (a, b) => a + Math.random() * (b - a);
const lerp = (a, b, t) => a + (b - a) * t;
const eo = t => 1 - Math.pow(1 - t, 3);
const rad = m => m.boss ? 24 : 13;
const cam = () => myData.map === 'town' ? { x: 400, y: 300 } : { x: myData.x, y: myData.y };
window.SkyDrop = { enabled: true };

function mk(m, idx) { return { m, t: -idx * 0.18, ph: 'em', u: 0, seed: R(0, 6.28), started: false, landed: false, cx0: 0, ey0: 0, ey1: 0 }; }

function land(f) {
  const m = f.m, r = rad(m), x = m.rx, y = m.ry + r, b = m.boss;
  doShake(b ? 15 : 9, 0.4); hitstop(0.05);
  if (b) whiteFlash(0.2);
  ring(x, y, b ? 110 : 70, '#ffffff', 3); ring(x, y, b ? 170 : 115, 'rgba(240,228,200,.8)', 2);
  shock(x, y, b ? 130 : 90, '#e8d9b0');
  spawnParticles(x, y, '#c9a86b', b ? 34 : 20, 1.1);
  const cols = ['#8d8272', '#7b7162', '#a3988a'];
  for (let i = 0; i < 9; i++) FX.particles.push({ x, y, vx: R(-190, 190), vy: R(-330, -120), life: 0.8, max: 0.8, size: R(2.5, 5), color: cols[i % 3], grav: 900 });
  const lines = []; const n = 7 + (Math.random() * 3 | 0);
  for (let i = 0; i < n; i++) lines.push([i / n * 6.283 + R(-0.25, 0.25), R(24, 64)]);
  cracks.push({ x, y, t: 0, lines, s: b ? 1.5 : 1 }); if (cracks.length > 12) cracks.shift();
  SND.noise(0.18, 0.5, 900); SND.tone(130, 0.32, 'sine', 0.7, 36);
  if (b) SND.slam();
  f.landed = true;
}

function scanAndUpdate(dt) {
  if (!myData || !window.SkyDrop.enabled) return;
  let idx = 0;
  for (const m of Object.values(monsters)) {
    if (m.alive) {
      if (!m._sd) { // เกิดใหม่: server ย้ายมอนไป home ใหม่ → snap rx/ry กันตัวไถลมาจากจุดตาย
        m._sd = true; m.rx = m.x; m.ry = m.y; m._prx = m.x; m._pry = m.y;
        if (falls.length < MAXF) falls.push(mk(m, idx++));
      }
    }
    else m._sd = false;
  }
  for (let i = falls.length - 1; i >= 0; i--) {
    const f = falls[i], m = f.m;
    if (!m.alive || monsters[String(m.id)] !== m) { falls.splice(i, 1); continue; }
    m.rx = m.x; m.ry = m.y; // ตำแหน่งจริงจาก server (ไม่ให้ interpolation ลากตัวไปที่อื่น)
    f.t += dt; const T = f.t; if (T < 0) continue;
    if (!f.started) {
      f.started = true; const c = cam();
      f.cx0 = c.x + R(-70, 70); f.ey0 = c.y + 120; f.ey1 = c.y + 90;
      SND.noise(1.1, 0.3, 1600); SND.tone(180, 1.0, 'sawtooth', 0.07, 900);
    }
    if (T < EM) { f.ph = 'em'; f.u = T / EM; }
    else if (T < EM + FA) { f.ph = 'fa'; f.u = (T - EM) / FA; }
    else if (T < EM + FA + DR) { f.ph = 'dr'; f.u = (T - EM - FA) / DR; }
    else if (T < EM + FA + DR + IM) { f.ph = 'im'; f.u = (T - EM - FA - DR) / IM; if (!f.landed) land(f); }
    else falls.splice(i, 1);
  }
  for (let i = cracks.length - 1; i >= 0; i--) if ((cracks[i].t += dt) > 8) cracks.splice(i, 1);
}

function drawCracks() {
  for (const c of cracks) {
    ctx.save(); ctx.globalAlpha = Math.min(1, (8 - c.t) / 2); ctx.translate(c.x, c.y); ctx.scale(c.s, 0.45 * c.s);
    ctx.fillStyle = 'rgba(40,30,20,.45)'; ctx.beginPath(); ctx.arc(0, 0, 14, 0, 7); ctx.fill();
    ctx.strokeStyle = 'rgba(20,14,8,.6)'; ctx.lineWidth = 2; ctx.lineCap = 'round';
    for (const [a, len] of c.lines) { ctx.beginPath(); ctx.moveTo(Math.cos(a) * 6, Math.sin(a) * 6); ctx.lineTo(Math.cos(a) * len * 0.55, Math.sin(a) * len * 0.55); ctx.lineTo(Math.cos(a + 0.1) * len, Math.sin(a + 0.1) * len); ctx.stroke(); }
    ctx.restore();
  }
}

function body(m, cx, cy, S, sx, sy, rot) {
  const r = rad(m);
  ctx.save();
  ctx.translate(cx, cy + r * S); ctx.scale(sx, sy); ctx.rotate(rot); ctx.translate(0, -r * S); ctx.scale(S, S);
  drawMonsterBody({ rx: 0, ry: 0, boss: m.boss, enraged: m.enraged, aggro: true }, null);
  ctx.restore();
}

function drawFalls() {
  for (const f of falls) {
    if (f.t < 0 || !f.started) continue;
    const m = f.m, r = rad(m), u = f.u, T = f.t, tx = m.rx, ty = m.ry;
    const S0 = m.boss ? 6 : 9, S1 = m.boss ? 5 : 7.5;
    let cx, cy, S = 1, sx = 1, sy = 1, rot = 0, near = 0;
    if (f.ph === 'em') {
      const e = eo(u); S = lerp(S0, S1, e); cx = f.cx0; cy = lerp(f.ey0, f.ey1, e); rot = 0.05 * Math.sin(T * 9);
    } else if (f.ph === 'fa') {
      const e = eo(u); S = lerp(S1, 1.12, e); cx = lerp(f.cx0, tx, e) + Math.sin(T * 8.5 + f.seed) * 15 * (1 - e);
      cy = lerp(f.ey1, ty - HOVER, e); rot = Math.sin(T * 5.2 + f.seed) * 0.13 * (1 - e); near = e * 0.62;
    } else if (f.ph === 'dr') {
      S = lerp(1.12, 1, u); cx = tx; cy = ty - HOVER * (1 - u * u); sy = 1 + 0.2 * u; sx = 1 - 0.13 * u; near = 0.62 + 0.38 * u;
    } else {
      const s = Math.exp(-u * 5.2); sy = 1 - 0.3 * s * Math.cos(u * 13.5); sx = 1 + (1 - sy) * 0.85; cx = tx; cy = ty; near = 1;
    }
    if (f.ph !== 'em') { // เงาบนพื้น โตขึ้นตามความใกล้
      ctx.fillStyle = `rgba(0,0,0,${(0.06 + 0.3 * near).toFixed(3)})`;
      ctx.beginPath(); ctx.ellipse(tx, ty + r + 4, (12 + 14 * near) * (m.boss ? 1.8 : 1), (5 + 5 * near) * (m.boss ? 1.6 : 1), 0, 0, 7); ctx.fill();
    }
    body(m, cx, cy, S, sx, sy, rot);
  }
}

// ---- hook เข้าเกมเดิม ----
const _updateFX = updateFX;
updateFX = function (dt) { _updateFX(dt); scanAndUpdate(dt); };

const _drawEntities = drawEntities;
drawEntities = function (now) {
  drawCracks();
  const hid = [];
  for (const f of falls) if (f.m.alive) { hid.push(f.m); f.m.alive = false; } // ซ่อนตัวจริงระหว่างตก
  _drawEntities(now);
  for (const m of hid) m.alive = true;
  drawFalls();
};

// ---- มอนที่กำลังตกลงมา = ยังโจมตี/ล็อกเป้า/ให้บอทตีไม่ได้ ----
const hideFalling = () => { const h = []; for (const f of falls) if (f.m.alive) { h.push(f.m); f.m.alive = false; } return h; };
const withHidden = fn => function (...a) {
  const h = hideFalling();
  try { return fn.apply(this, a); } finally { for (const m of h) m.alive = true; }
};
autoBotTick = withHidden(autoBotTick);
manualAttackAction = withHidden(manualAttackAction);
castSkill = withHidden(castSkill);
const _tryAttack = tryAttack;
tryAttack = function (mid) { if (falls.some(f => String(f.m.id) === String(mid))) return; _tryAttack(mid); };
canvas.addEventListener('pointerdown', () => { // คลิกบนแคนวาส (ตัวจัดการเดิมรันแบบ sync ก่อน setTimeout)
  const h = hideFalling(); setTimeout(() => { for (const m of h) m.alive = true; }, 0);
}, true);
})();