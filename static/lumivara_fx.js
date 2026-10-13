/* lumivara_fx.js — เอฟเฟกต์สกิล/ท่าไม้ตาย/ตีบวก (วาดบน canvas ซ้อนทับเกม)
 * สมมติฐาน: มีตัวแปร global `socket` (socket.io client) และ <canvas> ของเกมที่พิกัดโลก 800x600
 * ถ้า canvas เกมมี id อื่น ให้ตั้ง  window.LUMI_FX_CANVAS = document.getElementById('...')  ก่อนโหลดไฟล์นี้
 * ใช้งาน: <script src="/static/lumivara_fx.js"></script> ท้าย index.html
 */
(function () {
  const WORLD_W = 800, WORLD_H = 600;
  const game = window.LUMI_FX_CANVAS || document.querySelector('canvas');
  if (!game || typeof socket === 'undefined') { console.warn('[fx] ไม่พบ canvas/socket'); return; }
  const cv = document.createElement('canvas');
  Object.assign(cv.style, { position: 'absolute', pointerEvents: 'none', zIndex: 50 });
  game.parentElement.style.position = game.parentElement.style.position || 'relative';
  game.parentElement.appendChild(cv);
  const ctx = cv.getContext('2d');
  let fxs = [], flash = 0, flashColor = '#fff';

  function fit() {
    const r = game.getBoundingClientRect(), pr = game.parentElement.getBoundingClientRect();
    cv.style.left = (r.left - pr.left) + 'px'; cv.style.top = (r.top - pr.top) + 'px';
    cv.width = r.width; cv.height = r.height;
  }
  const sx = () => cv.width / WORLD_W, sy = () => cv.height / WORLD_H;
  const add = (o) => fxs.push(Object.assign({ t: 0, life: 0.6 }, o));

  socket.on('combat_fx', (d) => {
    if (d.type === 'skill_cast' && d.fx) castFx(d);
    if (d.type === 'player_died') add({ kind: 'ring', x: 0, y: 0, color: '#ff4444', r: 60, life: 0.8, follow: d.sid });
  });
  socket.on('boss_slam', (d) => add({ kind: 'ring', x: d.x, y: d.y, color: '#ff6a3d', r: d.radius, life: 0.7, fill: true }));
  socket.on('smith_result', (d) => {
    const ok = d.result === 'success';
    add({ kind: 'burst', x: 400, y: 300, color: ok ? '#ffe45c' : '#ff5555', n: ok ? 36 : 14, life: 0.9, speed: 160 });
    if (ok && d.enhance >= 9) { flash = 0.5; flashColor = '#ffe45c'; }
  });

  function castFx(d) {
    const f = d.fx, big = f.size || 1, c = f.color;
    const R = (d.radius || 160) * big / (f.ultimate ? 1.3 : 1);
    if (f.ultimate) { flash = 0.55; flashColor = c; }
    switch (f.shape) {
      case 'aura':      add({ kind: 'ring', x: d.x, y: d.y, color: c, r: 46 * big, life: 1.0, rise: true }); break;
      case 'heal_ring': add({ kind: 'ring', x: d.x, y: d.y, color: c, r: 50 * big, life: 0.9, rise: true });
                        add({ kind: 'burst', x: d.x, y: d.y, color: c, n: 14, life: 0.9, speed: 50, up: true }); break;
      case 'nova':      add({ kind: 'ring', x: d.x, y: d.y, color: c, r: R, life: 0.65, fill: true });
                        (d.target_pos || []).forEach(p => add({ kind: 'burst', x: p.x, y: p.y, color: c, n: 14 * big, life: 0.6, speed: 110 })); break;
      case 'shockwave': add({ kind: 'ring', x: d.x, y: d.y, color: c, r: R, life: 0.5 });
                        (d.target_pos || []).forEach(p => add({ kind: 'burst', x: p.x, y: p.y, color: c, n: 10 * big, life: 0.5, speed: 90 })); break;
      default: // slash / pierce / bolt : เส้นพุ่งจากผู้ใช้ไปเป้า
        (d.target_pos || []).forEach(p => add({ kind: f.shape === 'slash' ? 'slash' : 'beam', x: d.x, y: d.y, x2: p.x, y2: p.y,
                                                 color: c, w: 3 * big, life: f.shape === 'bolt' ? 0.35 : 0.25 }));
        (d.target_pos || []).forEach(p => add({ kind: 'burst', x: p.x, y: p.y, color: c, n: 12 * big, life: 0.5, speed: 100 }));
    }
    if (d.magic) add({ kind: 'ring', x: d.x, y: d.y, color: c, r: 26, life: 0.35 }); // วงร่ายเวท
  }

  let last = performance.now();
  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    fit(); ctx.clearRect(0, 0, cv.width, cv.height);
    const X = sx(), Y = sy();
    fxs = fxs.filter(o => (o.t += dt) < o.life);
    for (const o of fxs) {
      const k = o.t / o.life, a = 1 - k;
      ctx.globalAlpha = a; ctx.strokeStyle = ctx.fillStyle = o.color;
      if (o.kind === 'ring') {
        const r = o.r * (0.25 + 0.75 * k) * X, y = (o.y - (o.rise ? 30 * k : 0)) * Y;
        ctx.lineWidth = 3; ctx.beginPath(); ctx.arc(o.x * X, y, r, 0, 6.283); ctx.stroke();
        if (o.fill) { ctx.globalAlpha = a * 0.18; ctx.fill(); }
      } else if (o.kind === 'burst') {
        o.p = o.p || Array.from({ length: Math.min(60, o.n | 0) }, () => ({ a: Math.random() * 6.283, s: (0.4 + Math.random()) * o.speed }));
        for (const q of o.p) {
          const d = q.s * o.t, px = o.x * X + Math.cos(q.a) * d * X, py = o.y * Y + (o.up ? -d : Math.sin(q.a) * d) * Y;
          ctx.fillRect(px - 2, py - 2, 4, 4);
        }
      } else if (o.kind === 'beam' || o.kind === 'slash') {
        const e = o.kind === 'beam' ? Math.min(1, k * 3) : 1;
        ctx.lineWidth = o.w * (o.kind === 'slash' ? 1 + 2 * a : 1);
        ctx.beginPath(); ctx.moveTo(o.x * X, o.y * Y);
        ctx.lineTo((o.x + (o.x2 - o.x) * e) * X, (o.y + (o.y2 - o.y) * e) * Y); ctx.stroke();
      }
    }
    if (flash > 0) { ctx.globalAlpha = Math.min(0.5, flash); ctx.fillStyle = flashColor; ctx.fillRect(0, 0, cv.width, cv.height); flash -= dt * 1.2; }
    ctx.globalAlpha = 1;
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();
