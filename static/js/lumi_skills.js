/* =====================================================================
 * lumi_skills.js — Lumivara Skill UI + FX Engine v1.0
 * - แถบสกิลลัด 8 ช่อง (ปุ่ม 1–8) ลาก-วาง/คลิกขวาเพื่อล้าง
 * - สมุดสกิล (ปุ่ม K): แท็บแยกอาชีพ, เงื่อนไข ✔/✖, ปุ่มปลดล็อก
 * - เอฟเฟกต์ Canvas ทับบนจอเกม: วงเวท เสาแสง สายฟ้า อุกกาบาต พายุหิมะ หนามเงา ฯลฯ
 * ใช้งาน: LumiSkills.init({ socket })   ทดสอบเอฟเฟกต์: LumiSkills.demo('meteor')
 * ===================================================================== */
(function () {
  'use strict';
  if (window.LumiSkills) return;

  const CFG = {
    worldW: 800, worldH: 600,
    canvas: null,          // selector/element ของ canvas เกม (null = ใช้ canvas ที่ใหญ่สุด)
    camera: null,          // () => ({x, y}) ถ้าเกมมีกล้องเลื่อน
    hotkeys: ['Digit1', 'Digit2', 'Digit3', 'Digit4', 'Digit5', 'Digit6', 'Digit7', 'Digit8'],
    bookKey: 'KeyK',       // ใช้ e.code → กดได้แม้คีย์บอร์ดเป็นภาษาไทย
  };
  const S = { socket: null, tree: [], byId: {}, groups: [], me: null, bar: [], barKey: null,
              cd: {}, mp: 0, target: null, pos: { x: 400, y: 300 }, monsters: {}, map: null, tab: null };
  const UI = { slots: [] };
  const FX = { cv: null, ctx: null, list: [], parts: [], sx: 1, sy: 1, last: 0, game: null, gameAt: -1e9 };

  const TYPE_TH = { single: 'โจมตีเดี่ยว', aoe: 'โจมตีหมู่', heal: 'ฟื้นฟู', buff: 'บัฟ' };
  const FIRE = ['#fff1b8', '#ffd166', '#ff7b00', '#ff3d00'];
  const ICE = ['#ffffff', '#bff3ff', '#7ad7ff', '#3fa9ff'];
  const HOLY = ['#ffffff', '#fff6c2', '#ffe680', '#ffd166'];
  const SHADOW = ['#d6b8ff', '#9b5cff', '#6a2cff'];
  const POISON = ['#d4ff8a', '#9dff57', '#4fd14f', '#b46cff'];
  const NATURE = ['#f3ffd1', '#c8ff7a', '#7dff9a'];
  const ELEC = ['#ffffff', '#d8f1ff', '#9fd8ff', '#5aa9ff'];

  // ---------------- utils ----------------
  const $ = (q, el = document) => el.querySelector(q);
  function h(tag, cls, html) { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; }
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = n => Number(n || 0).toLocaleString('en-US');
  const pick = c => Array.isArray(c) ? c[(Math.random() * c.length) | 0] : (c || '#ffffff');
  const later = (sec, fn) => setTimeout(fn, Math.max(0, sec * 1000));
  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  const keyLabel = code => code.replace('Digit', '').replace('Key', '');
  const mon = id => S.monsters[String(id)];
  const skill = id => (id ? S.byId[id] : null);
  const ease = { out: t => 1 - Math.pow(1 - t, 3), in: t => t * t * t };
  function rgba(hex, a) { const n = parseInt(hex.slice(1), 16); return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${Math.max(0, a)})`; }
  function glow(c, x, y, r, col, a = 1) {
    if (r <= 0) return;
    const g = c.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, rgba(col, a)); g.addColorStop(1, rgba(col, 0));
    c.fillStyle = g; c.beginPath(); c.arc(x, y, r, 0, 6.283); c.fill();
  }

  // =================== FX ENGINE ===================
  function add(life, draw, delay = 0) {
    if (document.hidden) return null;
    const e = { t: -(delay || 0), life, draw }; FX.list.push(e); return e;
  }
  function particle(o) {
    if (FX.parts.length > 1800 || document.hidden) return;
    FX.parts.push(Object.assign({ x: 0, y: 0, vx: 0, vy: 0, life: 0.8, t: 0, size: 3, color: '#ffffff', g: 0,
      drag: 0.92, shape: 'dot', blend: 'lighter', rot: Math.random() * 6, spin: (Math.random() - 0.5) * 10 }, o));
  }
  function burst(x, y, o = {}) {
    const n = o.n || 24;
    for (let i = 0; i < n; i++) {
      const a = o.spread != null ? (o.angle || 0) + (Math.random() - 0.5) * o.spread : Math.random() * 6.283;
      const sp = (o.speed || 180) * (0.35 + Math.random() * 0.75);
      particle({ x, y, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp, life: (o.life || 0.7) * (0.6 + Math.random() * 0.6),
        size: (o.size || 3) * (0.6 + Math.random() * 0.8), color: pick(o.color), g: o.g || 0,
        drag: o.drag != null ? o.drag : 0.92, shape: o.shape || 'dot' });
    }
  }
  function ring(x, y, o = {}) {
    const r0 = o.r0 != null ? o.r0 : 10, r1 = o.r1 || 120, col = o.color || '#ffffff', w = o.width || 6, fl = o.flat || 1;
    add(o.life || 0.5, (c, k) => {
      const r = Math.max(0.1, r0 + (r1 - r0) * ease.out(k));
      c.globalCompositeOperation = 'lighter';
      c.strokeStyle = rgba(col, (1 - k) * 0.9); c.lineWidth = w * (1 - k) + 1;
      c.beginPath(); c.ellipse(x, y, r, r * fl, 0, 0, 6.283); c.stroke();
    }, o.delay);
  }
  function magicCircle(x, y, o = {}) {
    const R = o.r || 80, col = o.color || '#7ad7ff', fl = o.flat != null ? o.flat : 0.5;
    add(o.life || 1.2, (c, k) => {
      const appear = Math.min(1, k * 5), a = appear * (k > 0.75 ? (1 - k) / 0.25 : 1), rot = k * (o.spin || 3);
      const r = R * (0.6 + 0.4 * ease.out(appear));
      c.globalCompositeOperation = 'lighter';
      c.translate(x, y); c.scale(1, fl);
      glow(c, 0, 0, r * 1.15, col, 0.25 * a);
      c.strokeStyle = rgba(col, 0.95 * a); c.lineWidth = 2.2;
      c.beginPath(); c.arc(0, 0, r, 0, 6.283); c.stroke();
      c.beginPath(); c.arc(0, 0, r * 0.82, 0, 6.283); c.stroke();
      c.rotate(rot);
      for (const off of [0, Math.PI / 3]) {
        c.beginPath();
        for (let i = 0; i < 3; i++) { const an = off + i * 2.094; const px = Math.cos(an) * r * 0.82, py = Math.sin(an) * r * 0.82; i ? c.lineTo(px, py) : c.moveTo(px, py); }
        c.closePath(); c.stroke();
      }
      c.rotate(-rot * 2);
      for (let i = 0; i < 24; i++) {
        const an = i * Math.PI / 12, r2 = r * (i % 2 ? 0.94 : 0.99);
        c.beginPath(); c.moveTo(Math.cos(an) * r * 0.86, Math.sin(an) * r * 0.86); c.lineTo(Math.cos(an) * r2, Math.sin(an) * r2); c.stroke();
      }
    }, o.delay);
  }
  function jag(x1, y1, x2, y2, amp, seg) {
    const pts = [[x1, y1]], dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy) || 1, nx = -dy / L, ny = dx / L;
    for (let i = 1; i < seg; i++) { const t = i / seg, off = (Math.random() - 0.5) * amp * Math.sin(Math.PI * t); pts.push([x1 + dx * t + nx * off, y1 + dy * t + ny * off]); }
    pts.push([x2, y2]); return pts;
  }
  function bolt(x1, y1, x2, y2, o = {}) {
    const col = o.color || '#bfe6ff';
    add(o.life || 0.3, (c, k) => {
      const pts = jag(x1, y1, x2, y2, o.jag || 24, 12);
      c.globalCompositeOperation = 'lighter';
      for (const [w, a, cc] of [[11, 0.18, col], [4, 0.6, col], [1.6, 1, '#ffffff']]) {
        c.strokeStyle = rgba(cc, a * (1 - k)); c.lineWidth = w;
        c.beginPath(); pts.forEach((p, i) => (i ? c.lineTo(p[0], p[1]) : c.moveTo(p[0], p[1]))); c.stroke();
      }
    }, o.delay);
  }
  function projectile(x1, y1, x2, y2, o = {}) {
    const col = o.color || '#ffffff', dur = o.dur || 0.25, trail = [];
    add(dur, (c, k) => {
      const t = o.ease ? o.ease(k) : k;
      const x = x1 + (x2 - x1) * t, y = y1 + (y2 - y1) * t - (o.arc || 0) * Math.sin(Math.PI * k);
      trail.push([x, y]); if (trail.length > (o.trail || 10)) trail.shift();
      c.globalCompositeOperation = 'lighter';
      for (let i = 1; i < trail.length; i++) {
        const a = i / trail.length;
        c.strokeStyle = rgba(col, a * 0.85); c.lineWidth = (o.size || 4) * a;
        c.beginPath(); c.moveTo(trail[i - 1][0], trail[i - 1][1]); c.lineTo(trail[i][0], trail[i][1]); c.stroke();
      }
      glow(c, x, y, (o.size || 4) * 3, col, 0.9);
      if (o.sparks && Math.random() < 0.8) particle({ x, y, vx: (Math.random() - 0.5) * 60, vy: (Math.random() - 0.5) * 60, life: 0.45, size: 3, color: pick(o.sparks) });
      if (o.kind === 'arrow' && trail.length > 1) {
        const [px, py] = trail[trail.length - 2];
        c.translate(x, y); c.rotate(Math.atan2(y - py, x - px)); c.fillStyle = '#ffffff';
        c.beginPath(); c.moveTo(9, 0); c.lineTo(-4, -3.5); c.lineTo(-4, 3.5); c.closePath(); c.fill();
        c.fillRect(-18, -0.8, 14, 1.6);
      }
    }, o.delay);
    if (o.onHit) later((o.delay || 0) + dur, o.onHit);
  }
  function explosion(x, y, o = {}) {
    const s = o.scale || 1, cols = o.colors || FIRE;
    add(0.45, (c, k) => { c.globalCompositeOperation = 'lighter'; glow(c, x, y, 90 * s * (0.5 + k), cols[2], (1 - k) * 0.9); glow(c, x, y, 40 * s, '#ffffff', (1 - k) * (1 - k)); });
    ring(x, y, { r0: 10, r1: 120 * s, color: cols[1], life: 0.5, width: 8, flat: 0.55 });
    burst(x, y, { n: (40 * s) | 0, color: cols, speed: 320 * s, life: 0.8, size: 4, g: 220, shape: 'spark' });
    for (let i = 0; i < 10; i++) particle({ x: x + (Math.random() - 0.5) * 30 * s, y, vx: (Math.random() - 0.5) * 50, vy: -20 - Math.random() * 50, life: 1.2, size: 10 * s, color: '#2a2a2a', blend: 'source-over', drag: 0.96 });
  }
  function pillar(x, y, o = {}) {
    const col = o.color || '#fff6c2', w = o.w || 40, H = o.h || 600;
    add(o.life || 0.9, (c, k) => {
      const a = k < 0.15 ? k / 0.15 : 1 - (k - 0.15) / 0.85;
      const ww = w * (k < 0.15 ? ease.out(k / 0.15) : 1 - (k - 0.15) * 0.6);
      if (ww <= 0.5) return;
      c.globalCompositeOperation = 'lighter';
      const g = c.createLinearGradient(x - ww, 0, x + ww, 0);
      g.addColorStop(0, rgba(col, 0)); g.addColorStop(0.5, rgba(col, 0.85 * a)); g.addColorStop(1, rgba(col, 0));
      c.fillStyle = g; c.fillRect(x - ww, y - H, ww * 2, H + 8);
      c.fillStyle = rgba('#ffffff', 0.7 * a); c.fillRect(x - ww * 0.18, y - H, ww * 0.36, H + 8);
      c.translate(x, y); c.scale(1, 0.4); glow(c, 0, 0, ww * 2, col, a);
    }, o.delay);
  }
  function slash(x, y, o = {}) {
    const col = o.color || '#ffffff', R = o.r || 50, ang = o.angle != null ? o.angle : -0.6, sweep = o.sweep || 2.4;
    add(o.life || 0.28, (c, k) => {
      const a0 = ang - sweep / 2, a1 = a0 + sweep * ease.out(k);
      c.globalCompositeOperation = 'lighter'; c.translate(x, y);
      for (const [w, al, cc] of [[14, 0.25, col], [6, 0.7, col], [2, 1, '#ffffff']]) {
        c.strokeStyle = rgba(cc, al * (1 - k)); c.lineWidth = w * (1 - k * 0.5);
        c.beginPath(); c.arc(0, 0, R, Math.max(a0, a1 - 1.6), a1); c.stroke();
      }
    }, o.delay);
  }
  function charge(x, y, o = {}) {
    const col = o.color || '#ffffff';
    add(o.life || 0.4, () => {
      for (let i = 0; i < 3; i++) {
        const a = Math.random() * 6.283, r = 70 + Math.random() * 30;
        particle({ x: x + Math.cos(a) * r, y: y + Math.sin(a) * r * 0.6, vx: -Math.cos(a) * r * 2.2, vy: -Math.sin(a) * r * 1.3,
          life: 0.42, size: 2.5, color: pick([col, '#ffffff']), drag: 1, shape: 'spark' });
      }
    });
  }
  function aura(x, y, o = {}) {
    const col = o.color || '#7dff9a';
    add(o.life || 1.2, (c, k) => {
      c.globalCompositeOperation = 'lighter'; c.translate(x, y); c.scale(1, 0.45); glow(c, 0, 0, 60, col, 0.5 * (1 - k));
      if (Math.random() < 0.7) particle({ x: x + (Math.random() - 0.5) * 50, y: y + 10, vy: -60 - Math.random() * 90, life: 0.9, size: 3, color: pick([col, '#ffffff']), drag: 0.98, shape: 'shard' });
    });
    ring(x, y, { r0: 70, r1: 15, color: col, life: 0.6, width: 4, flat: 0.45 });
    ring(x, y, { r0: 15, r1: 90, color: col, life: 0.7, width: 5, flat: 0.45, delay: 0.55 });
  }
  function flash(col, a = 0.35, life = 0.25) {
    add(life, (c, k) => { c.setTransform(1, 0, 0, 1, 0, 0); c.fillStyle = rgba(col, a * (1 - k)); c.fillRect(0, 0, FX.cv.width, FX.cv.height); });
  }
  function glowHit(x, y, col, r) {
    add(0.3, (c, k) => { c.globalCompositeOperation = 'lighter'; glow(c, x, y, r * (0.6 + k * 0.6), col, 0.9 * (1 - k)); glow(c, x, y, r * 0.35, '#ffffff', 1 - k); });
  }
  function shield(x, y, col, life = 1.4) {
    add(life, (c, k) => {
      const a = k < 0.15 ? k / 0.15 : (k > 0.7 ? (1 - k) / 0.3 : 1), r = 42 + Math.sin(k * 20) * 2;
      c.globalCompositeOperation = 'lighter'; glow(c, x, y - 14, r, col, 0.35 * a);
      c.strokeStyle = rgba(col, 0.9 * a); c.lineWidth = 2;
      c.beginPath(); c.arc(x, y - 14, r, 0, 6.283); c.stroke();
      for (let i = 0; i < 6; i++) { const an = i * 1.047 + k * 2; c.beginPath(); c.arc(x + Math.cos(an) * r * 0.5, y - 14 + Math.sin(an) * r * 0.5, r * 0.28, 0, 6.283); c.stroke(); }
    });
  }
  function darkPuff(x, y, r) {
    add(0.7, (c, k) => {
      const g = c.createRadialGradient(x, y, 0, x, y, r * (0.6 + k * 0.6));
      g.addColorStop(0, `rgba(20,0,40,${0.75 * (1 - k)})`); g.addColorStop(1, 'rgba(20,0,40,0)');
      c.fillStyle = g; c.beginPath(); c.arc(x, y, r * 1.2, 0, 6.283); c.fill();
    });
    for (let i = 0; i < 14; i++) particle({ x: x + (Math.random() - 0.5) * r, y: y + (Math.random() - 0.5) * r * 0.5, vx: (Math.random() - 0.5) * 40, vy: -20 - Math.random() * 40, life: 0.9, size: 10, color: '#1a0830', blend: 'source-over', drag: 0.97 });
  }
  function spike(x, y, s = 1) {
    add(0.5, (c, k) => {
      const up = k < 0.25 ? ease.out(k / 0.25) : 1 - (k - 0.25) / 0.75, hg = 46 * s * up, w = 9 * s;
      c.fillStyle = '#16052b'; c.beginPath(); c.moveTo(x - w, y); c.lineTo(x, y - hg); c.lineTo(x + w, y); c.closePath(); c.fill();
      c.globalCompositeOperation = 'lighter'; c.strokeStyle = rgba('#b06cff', 0.9 * up); c.lineWidth = 1.5; c.stroke();
      glow(c, x, y - hg * 0.5, 18 * s, '#9b5cff', 0.35 * up);
    });
  }
  function crossMark(x, y, R, life) {
    add(life, (c, k) => {
      const a = k < 0.15 ? k / 0.15 : 1 - (k - 0.15) / 0.85, w = R * 0.12;
      c.translate(x, y); c.scale(1, 0.5); c.globalCompositeOperation = 'lighter'; c.fillStyle = rgba('#fff6c2', 0.55 * a);
      c.fillRect(-w / 2, -R * 0.85, w, R * 1.7); c.fillRect(-R * 0.6, -R * 0.35 - w / 2, R * 1.2, w);
    });
  }
  function afterimage(x1, y1, x2, y2, col) {
    for (let i = 0; i < 5; i++) {
      const k = i / 5, x = x1 + (x2 - x1) * k, y = y1 + (y2 - y1) * k;
      add(0.3, (c, q) => { c.globalCompositeOperation = 'lighter'; glow(c, x, y - 14, 16, col, 0.5 * (1 - q) * (0.4 + k)); }, i * 0.02);
    }
  }
  function follow(t, sec, draw) {   // วาดตามตำแหน่งมอนแบบสด หยุดเมื่อมอนตาย
    add(sec, (c, k) => { const m = mon(t.id); if (m && !m.alive) return; draw(c, k, m ? m.x : t.x, m ? m.y : t.y); });
  }
  function stunStars(t, sec) {
    follow(t, sec, (c, k, x, y) => {
      const tt = performance.now() / 1000;
      c.globalAlpha = k > 0.85 ? (1 - k) / 0.15 : 1; c.font = '12px sans-serif'; c.textAlign = 'center';
      for (let i = 0; i < 3; i++) { const a = tt * 4 + i * 2.094; c.fillText('⭐', x + Math.cos(a) * 16, y - 36 + Math.sin(a) * 5); }
    });
  }
  function iceBlock(t, sec) {
    follow(t, sec, (c, k, x, y) => {
      const a = k < 0.1 ? k / 0.1 : (k > 0.85 ? (1 - k) / 0.15 : 1);
      const g = c.createLinearGradient(x - 22, y - 40, x + 22, y + 10);
      g.addColorStop(0, '#e8fbff'); g.addColorStop(1, '#5fc8ff');
      c.globalAlpha = a * 0.55; c.fillStyle = g; c.strokeStyle = '#ffffff'; c.lineWidth = 1.5;
      c.beginPath(); c.moveTo(x - 20, y + 10); c.lineTo(x - 24, y - 22); c.lineTo(x - 8, y - 42); c.lineTo(x + 14, y - 38); c.lineTo(x + 24, y - 14); c.lineTo(x + 18, y + 10); c.closePath(); c.fill();
      c.globalAlpha = a; c.stroke();
    });
  }
  function dmgText(x, y, txt, o = {}) {
    const col = o.color || '#ffffff', big = o.crit ? 1.6 : 1, vx = (Math.random() - 0.5) * 30;
    add(o.life || 0.9, (c, k) => {
      const pop = k < 0.15 ? 0.6 + (k / 0.15) * 0.8 : 1.4 - Math.min(0.4, (k - 0.15) * 1.2);
      c.globalAlpha = k > 0.7 ? (1 - k) / 0.3 : 1; c.translate(x + vx * k, y - 30 - k * 40); c.scale(pop * big, pop * big);
      c.font = '900 18px "Kanit","Segoe UI",sans-serif'; c.textAlign = 'center'; c.lineJoin = 'round';
      c.lineWidth = 4; c.strokeStyle = 'rgba(0,0,0,.85)'; c.strokeText(txt, 0, 0);
      c.fillStyle = col; c.fillText(txt, 0, 0);
    }, o.delay);
  }
  function banner(x, y, name, col) {
    add(1.1, (c, k) => {
      const a = k < 0.1 ? k / 0.1 : (k > 0.75 ? (1 - k) / 0.25 : 1), t = '✦ ' + name + ' ✦';
      c.globalAlpha = a; c.translate(x, y - 70 - k * 12);
      c.font = '800 15px "Kanit","Segoe UI",sans-serif'; c.textAlign = 'center'; c.lineWidth = 4; c.strokeStyle = 'rgba(0,0,0,.8)';
      c.strokeText(t, 0, 0);
      const g = c.createLinearGradient(-60, 0, 60, 0); g.addColorStop(0, '#ffffff'); g.addColorStop(0.5, col); g.addColorStop(1, '#ffffff');
      c.fillStyle = g; c.fillText(t, 0, 0);
    });
  }
  function showHits(e, delay = 0.12, o = {}) {
    (e.targets || []).forEach((t, i) => {
      const list = t.hits && t.hits.length ? t.hits : [t.dmg];
      list.forEach((d, j) => {
        const dl = delay + j * (o.step || 0.09) + i * (o.stagger || 0.03);
        dmgText(t.x + (j % 2 ? 8 : -8), t.y - j * 6, String(d), { crit: t.crit, color: t.crit ? '#ffdd55' : '#ffffff', delay: dl });
        later(dl, () => burst(t.x, t.y, { n: o.n || 10, color: o.colors || [e.color, '#ffffff'], speed: 200, life: 0.4, size: 2.5, shape: 'spark' }));
      });
      if (t.died) later(delay + list.length * (o.step || 0.09) + 0.05, () => {
        ring(t.x, t.y, { r0: 5, r1: 60, color: e.color, life: 0.4, flat: 0.6 });
        burst(t.x, t.y, { n: 26, color: [e.color, '#ffffff'], speed: 260, life: 0.7, size: 3 });
      });
    });
  }
  function healFx(e, col, withPillar) {
    (e.allies || []).forEach((a, i) => {
      const d = i * 0.08;
      if (withPillar) pillar(a.x, a.y, { color: col, w: 26, h: 260, life: 0.9, delay: d });
      ring(a.x, a.y, { r0: 50, r1: 8, color: col, life: 0.45, width: 4, flat: 0.45, delay: d });
      later(d + 0.1, () => {
        for (let k = 0; k < 14; k++) particle({ x: a.x + (Math.random() - 0.5) * 44, y: a.y + (Math.random() - 0.2) * 20, vy: -50 - Math.random() * 80, life: 1, size: 4, color: pick([col, '#ffffff']), drag: 0.98, shape: 'cross' });
      });
    });
  }
  const T = e => (e.targets && e.targets[0]) || { x: e.cx, y: e.cy, hits: [] };

  // ---------------- สูตรเอฟเฟกต์รายสกิล ----------------
  const R = {
    _default(e) { const t = T(e); burst(t.x, t.y, { n: 20, color: [e.color, '#ffffff'] }); showHits(e, 0.1); },
    slash_gold(e) {
      const t = T(e); charge(e.x, e.y, { color: '#ffd166', life: 0.15 });
      slash(t.x, t.y, { color: '#ffd166', r: 44, angle: -0.5, delay: 0.08 });
      slash(t.x, t.y, { color: '#ffb300', r: 36, angle: 2.6, delay: 0.16 });
      later(0.12, () => burst(t.x, t.y, { n: 20, color: ['#ffd166', '#ffffff'], speed: 260, shape: 'spark' }));
      showHits(e, 0.12);
    },
    heal_ring(e) { healFx(e, '#6dff8e', false); },
    holy_heal(e) { healFx(e, '#fff3a0', true); },
    magnificat(e) {
      magicCircle(e.x, e.y, { r: 110, color: '#fff6c2', life: 1.6, spin: 2 }); flash('#fff6c2', 0.25, 0.4);
      ring(e.x, e.y, { r0: 20, r1: e.radius || 200, color: '#ffffff', life: 0.8, width: 6, flat: 0.5 });
      healFx(e, '#ffffff', true);
    },
    bash_impact(e) {
      const t = T(e); charge(e.x, e.y, { color: '#ff9f43', life: 0.2 });
      later(0.18, () => {
        glowHit(t.x, t.y, '#ff9f43', 70); ring(t.x, t.y, { r0: 6, r1: 80, color: '#ffcc80', life: 0.4, width: 9, flat: 0.5 });
        burst(t.x, t.y, { n: 22, color: ['#ffcc80', '#ff9f43', '#ffffff'], speed: 300, g: 500, shape: 'shard', life: 0.7, size: 4 });
      });
      showHits(e, 0.18, { n: 4 });
    },
    magnum_break(e) {
      charge(e.x, e.y, { color: '#ff5a1f', life: 0.25 });
      later(0.2, () => {
        flash('#ff6a00', 0.25);
        ring(e.x, e.y, { r0: 20, r1: e.radius, color: '#ff7b00', life: 0.55, width: 14, flat: 0.5 });
        ring(e.x, e.y, { r0: 10, r1: e.radius * 0.8, color: '#ffd166', life: 0.45, width: 6, flat: 0.5, delay: 0.05 });
        for (let i = 0; i < 18; i++) { const a = i / 18 * 6.283; burst(e.x + Math.cos(a) * e.radius * 0.5, e.y + Math.sin(a) * e.radius * 0.25, { n: 5, color: FIRE, speed: 120, g: -200, life: 0.7, size: 4 }); }
      });
      showHits(e, 0.28, { colors: FIRE });
    },
    brandish(e) {
      const t = T(e), an = Math.atan2(t.y - e.y, t.x - e.x);
      for (let i = 0; i < 2; i++) {
        projectile(e.x, e.y, t.x + Math.cos(an) * 20, t.y + Math.sin(an) * 20, { color: '#9fd8ff', dur: 0.12, size: 5, trail: 14, delay: i * 0.14, kind: 'arrow' });
        slash(t.x, t.y, { color: '#9fd8ff', r: 40, angle: an + (i ? 1.6 : -1.6), sweep: 1.6, delay: 0.12 + i * 0.14 });
      }
      showHits(e, 0.12, { step: 0.14 });
    },
    endure(e) { aura(e.x, e.y, { color: '#ffcf6b' }); shield(e.x, e.y, '#ffcf6b', 1.2); },
    bowling_bash(e) {
      magicCircle(e.x, e.y, { r: e.radius * 0.7, color: '#ffcf6b', life: 0.7, spin: 6 }); charge(e.x, e.y, { color: '#ffd166', life: 0.3 });
      later(0.25, () => {
        flash('#fff1c2', 0.35, 0.25);
        for (let i = 0; i < 3; i++) ring(e.x, e.y, { r0: 10, r1: e.radius * (1 + i * 0.15), color: i ? '#ff9f43' : '#ffffff', life: 0.5 + i * 0.12, width: 12 - i * 3, flat: 0.5, delay: i * 0.07 });
        burst(e.x, e.y, { n: 50, color: ['#ffd166', '#ffffff', '#a0763f'], speed: 420, g: 600, shape: 'shard', life: 0.9, size: 5 });
      });
      showHits(e, 0.3);
    },
    frost(e) {
      const t = T(e); charge(e.x, e.y, { color: '#7ad7ff', life: 0.2 });
      projectile(e.x, e.y - 14, t.x, t.y - 10, { color: '#9fe7ff', dur: 0.28, size: 7, trail: 16, delay: 0.12, sparks: ICE, onHit: () => {
        glowHit(t.x, t.y, '#7ad7ff', 70); ring(t.x, t.y, { r0: 5, r1: 60, color: '#bff3ff', life: 0.4, flat: 0.5 });
        burst(t.x, t.y, { n: 26, color: ICE, speed: 260, shape: 'shard', life: 0.7, size: 4 });
        if (!t.died && e.stun) iceBlock(t, e.stun);
      } });
      e._noStars = true; showHits(e, 0.4, { colors: ICE });
    },
    fire_burst(e) {
      magicCircle(e.cx, e.cy, { r: e.radius * 0.8, color: '#ff7b00', life: 0.9, spin: 4 });
      projectile(e.x, e.y - 14, e.cx, e.cy, { color: '#ff9f43', dur: 0.3, size: 9, trail: 14, arc: 40, sparks: FIRE, onHit: () => {
        explosion(e.cx, e.cy, { scale: 1.1 });
        (e.targets || []).slice(1).forEach((t, i) => later(0.06 * i, () => explosion(t.x, t.y, { scale: 0.5 })));
      } });
      showHits(e, 0.35, { colors: FIRE });
    },
    lightning(e) {
      const t = T(e), n = (t.hits && t.hits.length) || 3;
      charge(e.x, e.y, { color: '#9fd8ff', life: 0.25 }); flash('#cfe8ff', 0.25, 0.15);
      for (let i = 0; i < n; i++) later(0.15 + i * 0.13, () => {
        bolt(e.x, e.y - 20, t.x, t.y - 10, { color: '#9fd8ff', life: 0.22 });
        bolt(t.x, -20, t.x, t.y - 10, { color: '#d8f1ff', life: 0.18, jag: 40 });
        glowHit(t.x, t.y, '#9fd8ff', 60); burst(t.x, t.y, { n: 14, color: ELEC, speed: 320, shape: 'spark', life: 0.35 });
      });
      showHits(e, 0.15, { step: 0.13, colors: ELEC });
    },
    meteor(e) {
      magicCircle(e.cx, e.cy, { r: e.radius, color: '#ff6a00', life: 1.4, spin: 3 }); flash('#ff4500', 0.15, 0.6);
      const pts = (e.targets || []).map(t => [t.x, t.y]);
      while (pts.length < 5) pts.push([e.cx + (Math.random() - 0.5) * e.radius * 1.4, e.cy + (Math.random() - 0.5) * e.radius * 0.7]);
      pts.forEach(([x, y], i) => projectile(x + 260, y - 460, x, y, { color: '#ff7b00', dur: 0.45, size: 12, trail: 22, delay: 0.35 + i * 0.12, ease: ease.in, sparks: FIRE,
        onHit: () => { explosion(x, y, { scale: 1.2 }); if (i === 0) flash('#ffb36b', 0.35, 0.3); } }));
      showHits(e, 0.82, { colors: FIRE, stagger: 0.12 });
    },
    blizzard(e) {
      magicCircle(e.cx, e.cy, { r: e.radius, color: '#9fe7ff', life: 1.8, spin: -3 }); flash('#dff8ff', 0.3, 0.4);
      add(1.5, (c, k) => {
        for (let i = 0; i < 6; i++) {
          const a = Math.random() * 6.283, r = Math.random() * e.radius;
          particle({ x: e.cx + Math.cos(a) * r, y: e.cy + Math.sin(a) * r * 0.5 - 120, vx: -160 + Math.random() * 60, vy: 220 + Math.random() * 120, life: 0.6, size: 3, color: pick(ICE), drag: 1, shape: Math.random() < 0.4 ? 'shard' : 'dot' });
        }
        c.globalCompositeOperation = 'lighter'; c.translate(e.cx, e.cy); c.scale(1, 0.5); glow(c, 0, 0, e.radius, '#bff3ff', 0.25 * (1 - k));
      }, 0.1);
      for (let i = 0; i < 3; i++) ring(e.cx, e.cy, { r0: e.radius, r1: 20, color: '#bff3ff', life: 0.6, width: 5, flat: 0.5, delay: 0.2 + i * 0.4 });
      (e.targets || []).forEach(t => { if (!t.died && e.stun) later(0.4, () => iceBlock(t, e.stun)); });
      e._noStars = true; showHits(e, 0.35, { step: 0.35, colors: ICE });
    },
    arrow_double(e) {
      const t = T(e);
      for (let i = 0; i < 2; i++) projectile(e.x, e.y - 12 + i * 6, t.x, t.y - 10, { kind: 'arrow', color: '#c8ff7a', dur: 0.18, size: 3, trail: 12, delay: i * 0.1,
        onHit: () => burst(t.x, t.y, { n: 10, color: NATURE, speed: 220, shape: 'spark', life: 0.35 }) });
      showHits(e, 0.18, { step: 0.1, colors: NATURE });
    },
    arrow_rain(e) {
      magicCircle(e.cx, e.cy, { r: e.radius, color: '#a8ff60', life: 1.2, spin: 2 });
      for (let i = 0; i < 26; i++) {
        const a = Math.random() * 6.283, r = Math.sqrt(Math.random()) * e.radius, x = e.cx + Math.cos(a) * r, y = e.cy + Math.sin(a) * r * 0.5;
        projectile(x - 40, y - 300, x, y, { kind: 'arrow', color: '#c8ff7a', dur: 0.28, size: 2.5, trail: 8, delay: 0.15 + Math.random() * 0.6,
          onHit: () => burst(x, y, { n: 5, color: NATURE, speed: 140, shape: 'spark', life: 0.3 }) });
      }
      showHits(e, 0.45, { colors: NATURE });
    },
    falcon(e) {
      const ts = e.targets && e.targets.length ? e.targets : [T(e)];
      ts.forEach((t, i) => projectile(-40, t.y - 160, t.x, t.y - 10, { color: '#ffe08a', dur: 0.38, size: 8, trail: 20, arc: -60, delay: i * 0.1, sparks: ['#ffe08a', '#ffffff'],
        onHit: () => { burst(t.x, t.y, { n: 18, color: ['#ffe08a', '#ffffff', '#c49a5a'], speed: 240, shape: 'shard', life: 0.6 }); slash(t.x, t.y, { color: '#ffe08a', r: 30, angle: Math.random() * 6 }); } }));
      showHits(e, 0.42, { stagger: 0.1 });
    },
    aura_green(e) {
      aura(e.x, e.y, { color: '#7dff9a' });
      add(1.0, (c, k) => {
        const a = 1 - k, r = 34 - k * 10;
        c.globalCompositeOperation = 'lighter'; c.translate(e.x, e.y - 20); c.rotate(k * 3);
        c.strokeStyle = rgba('#7dff9a', a); c.lineWidth = 2; c.beginPath(); c.arc(0, 0, r, 0, 6.283); c.stroke();
        for (let i = 0; i < 4; i++) { c.rotate(1.5708); c.beginPath(); c.moveTo(r - 8, 0); c.lineTo(r + 8, 0); c.stroke(); }
      });
    },
    piercing(e) {
      const t = T(e), an = Math.atan2(t.y - e.y, t.x - e.x), ex = e.x + Math.cos(an) * 900, ey = e.y + Math.sin(an) * 900;
      charge(e.x, e.y, { color: '#e6ffb3', life: 0.35 });
      later(0.3, () => {
        flash('#f4ffd9', 0.25, 0.2);
        add(0.45, (c, k) => {
          c.globalCompositeOperation = 'lighter';
          for (const [w, col, al] of [[18, '#c8ff7a', 0.25], [7, '#e6ffb3', 0.7], [2.5, '#ffffff', 1]]) {
            c.strokeStyle = rgba(col, al * (1 - k)); c.lineWidth = w * (1 - k * 0.7);
            c.beginPath(); c.moveTo(e.x, e.y - 12); c.lineTo(ex, ey); c.stroke();
          }
        });
        const L = dist(t, e) * 1.4;
        for (let i = 0; i < 20; i++) { const d = Math.random() * L; particle({ x: e.x + Math.cos(an) * d, y: e.y - 12 + Math.sin(an) * d, vx: (Math.random() - 0.5) * 80, vy: (Math.random() - 0.5) * 80, life: 0.6, size: 2.5, color: pick(NATURE) }); }
        ring(t.x, t.y, { r0: 4, r1: 70, color: '#e6ffb3', life: 0.35, flat: 0.5 });
      });
      showHits(e, 0.32, { colors: NATURE });
    },
    sonic(e) {
      const t = T(e), n = (t.hits && t.hits.length) || 4;
      afterimage(e.x, e.y, t.x, t.y, '#ff4d6d');
      for (let i = 0; i < n; i++) slash(t.x + (Math.random() - 0.5) * 14, t.y + (Math.random() - 0.5) * 10, { color: i % 2 ? '#ff4d6d' : '#ff9fb2', r: 30 + i * 4, angle: i * 1.9, sweep: 2.2, life: 0.2, delay: 0.05 + i * 0.08 });
      showHits(e, 0.07, { step: 0.08, colors: ['#ff4d6d', '#ffffff'] });
    },
    poison(e) {
      const t = T(e); slash(t.x, t.y, { color: '#9dff57', r: 36, delay: 0.05 });
      later(0.1, () => burst(t.x, t.y, { n: 18, color: POISON, speed: 180, life: 0.6 }));
      if (!t.died) follow(t, e.dot || 4, (c, k, x, y) => { if (Math.random() < 0.35) particle({ x: x + (Math.random() - 0.5) * 30, y: y - Math.random() * 20, vy: -30 - Math.random() * 30, life: 0.9, size: 4, color: pick(POISON), drag: 0.99, shape: 'ring' }); });
      showHits(e, 0.08, { colors: POISON });
    },
    shadow_spike(e) {
      const t = T(e), n = 7;
      for (let i = 1; i <= n; i++) {
        const k = i / n, x = e.x + (t.x - e.x) * k, y = e.y + (t.y - e.y) * k;
        later(i * 0.045, () => { spike(x, y, i === n ? 1.8 : 0.9); burst(x, y, { n: 5, color: SHADOW, speed: 120, life: 0.4, shape: 'shard' }); });
      }
      later(n * 0.045, () => darkPuff(t.x, t.y, 60));
      showHits(e, 0.33, { colors: SHADOW });
    },
    shadow_aura(e) {
      darkPuff(e.x, e.y, 70); aura(e.x, e.y, { color: '#7b4dff' });
      add(1.2, () => { if (Math.random() < 0.6) particle({ x: e.x + (Math.random() - 0.5) * 50, y: e.y, vy: -40 - Math.random() * 40, life: 0.9, size: 8, color: '#1a0830', blend: 'source-over', drag: 0.97 }); });
    },
    shadow_burst(e) {
      flash('#000000', 0.45, 0.5); darkPuff(e.x, e.y, e.radius);
      later(0.15, () => {
        for (let i = 0; i < 12; i++) { const a = i / 12 * 6.283; for (let j = 1; j <= 3; j++) { const r = e.radius * j / 3; later(j * 0.05, () => spike(e.x + Math.cos(a) * r, e.y + Math.sin(a) * r * 0.5, 0.7 + j * 0.2)); } }
        ring(e.x, e.y, { r0: 10, r1: e.radius, color: '#b06cff', life: 0.5, width: 10, flat: 0.5 });
        burst(e.x, e.y, { n: 40, color: SHADOW, speed: 380, life: 0.8, shape: 'shard' });
      });
      showHits(e, 0.3, { colors: SHADOW });
    },
    bless(e) {
      (e.allies || []).forEach((a, i) => {
        pillar(a.x, a.y, { color: '#ffe680', w: 20, h: 300, life: 0.8, delay: i * 0.08 });
        later(i * 0.08, () => { for (let k = 0; k < 16; k++) particle({ x: a.x + (Math.random() - 0.5) * 60, y: a.y - 120 - Math.random() * 60, vx: (Math.random() - 0.5) * 20, vy: 60 + Math.random() * 60, life: 1.2, size: 3, color: pick(HOLY), drag: 0.99, shape: 'shard' }); });
      });
      aura(e.x, e.y, { color: '#ffe680' });
    },
    holy_light(e) {
      const t = T(e); charge(e.x, e.y, { color: '#fff6c2', life: 0.25 });
      later(0.2, () => { pillar(t.x, t.y, { color: '#fff6c2', w: 34, h: 500, life: 0.7 }); flash('#fffbe6', 0.25, 0.2); burst(t.x, t.y, { n: 24, color: HOLY, speed: 260, shape: 'cross', life: 0.7, size: 4 }); });
      showHits(e, 0.25, { colors: HOLY });
    },
    kyrie(e) { (e.allies || []).forEach((a, i) => { later(i * 0.06, () => shield(a.x, a.y, '#8fd3ff', 1.6)); ring(a.x, a.y, { r0: 10, r1: 60, color: '#8fd3ff', life: 0.5, flat: 0.45, delay: i * 0.06 }); }); },
    magnus(e) {
      const Rr = e.radius;
      magicCircle(e.cx, e.cy, { r: Rr, color: '#fff1a8', life: 2.0, spin: 1.5 });
      magicCircle(e.cx, e.cy, { r: Rr * 0.55, color: '#ffffff', life: 2.0, spin: -3 });
      crossMark(e.cx, e.cy, Rr, 2.0); flash('#fffbe6', 0.3, 0.5);
      for (let i = 0; i < 10; i++) { const a = Math.random() * 6.283, r = Math.sqrt(Math.random()) * Rr; pillar(e.cx + Math.cos(a) * r, e.cy + Math.sin(a) * r * 0.5, { color: '#fff6c2', w: 16 + Math.random() * 14, h: 520, life: 0.6, delay: 0.3 + i * 0.1 }); }
      (e.targets || []).forEach((t, i) => pillar(t.x, t.y, { color: '#ffffff', w: 26, h: 520, life: 0.6, delay: 0.35 + i * 0.05 }));
      showHits(e, 0.4, { step: 0.3, colors: HOLY });
    },
  };

  function playFx(e) {
    if (document.hidden || !e) return;
    banner(e.x, e.y, e.name || e.skill || '', e.color || '#ffd166');
    try { (R[e.fx] || R._default)(e); } catch (err) { console.warn('[LumiSkills] fx', err); }
    if (e.stun && !e._noStars) (e.targets || []).forEach(t => { if (!t.died) later(0.3, () => stunStars(t, e.stun)); });
    if (e.lifesteal) later(0.35, () => dmgText(e.x, e.y - 10, '+' + e.lifesteal, { color: '#ff6b8b' }));
    (e.allies || []).forEach(a => { if (a.amt > 0) dmgText(a.x, a.y, '+' + a.amt, { color: '#6dff8e', delay: 0.25 }); });
  }
  function celebrate(s) {
    const { x, y } = S.pos;
    pillar(x, y, { color: '#ffd166', w: 40, h: 600, life: 1.2 });
    magicCircle(x, y, { r: 70, color: s.color || '#ffd166', life: 1.4 });
    burst(x, y, { n: 50, color: [s.color || '#ffd166', '#ffffff', '#ffd166'], speed: 300, g: 200, shape: 'shard', life: 1 });
    banner(x, y, 'ปลดล็อก ' + s.name, '#ffd166');
  }

  // ---------------- overlay loop ----------------
  function findGame() {
    if (CFG.canvas) return typeof CFG.canvas === 'string' ? $(CFG.canvas) : CFG.canvas;
    let best = null, area = 0;
    document.querySelectorAll('canvas').forEach(cv => {
      if (cv === FX.cv) return;
      const r = cv.getBoundingClientRect(), a = r.width * r.height;
      if (a > area) { area = a; best = cv; }
    });
    return best;
  }
  function syncOverlay(now) {
    if (!FX.game || !FX.game.isConnected || now - FX.gameAt > 2000) { FX.game = findGame(); FX.gameAt = now; }
    const r = FX.game ? FX.game.getBoundingClientRect() : { left: 0, top: 0, width: innerWidth, height: innerHeight };
    const dpr = window.devicePixelRatio || 1, cv = FX.cv;
    const w = Math.max(1, Math.round(r.width * dpr)), hh = Math.max(1, Math.round(r.height * dpr));
    if (cv.width !== w || cv.height !== hh) { cv.width = w; cv.height = hh; }
    const st = cv.style; st.left = r.left + 'px'; st.top = r.top + 'px'; st.width = r.width + 'px'; st.height = r.height + 'px';
    FX.sx = w / CFG.worldW; FX.sy = hh / CFG.worldH;
  }
  function drawParticles(c, dt) {
    const P = FX.parts;
    for (let i = P.length - 1; i >= 0; i--) {
      const p = P[i]; p.t += dt;
      if (p.t >= p.life) { P[i] = P[P.length - 1]; P.pop(); continue; }
      const k = Math.pow(p.drag, dt * 60);
      p.vx *= k; p.vy = p.vy * k + p.g * dt; p.x += p.vx * dt; p.y += p.vy * dt; p.rot += p.spin * dt;
      const a = 1 - p.t / p.life;
      c.globalCompositeOperation = p.blend; c.globalAlpha = a; c.fillStyle = c.strokeStyle = p.color;
      switch (p.shape) {
        case 'spark': c.lineWidth = p.size * 0.7; c.beginPath(); c.moveTo(p.x, p.y); c.lineTo(p.x - p.vx * 0.05, p.y - p.vy * 0.05); c.stroke(); break;
        case 'shard': c.save(); c.translate(p.x, p.y); c.rotate(p.rot); c.beginPath(); c.moveTo(0, -p.size * 1.6); c.lineTo(p.size * 0.6, 0); c.lineTo(0, p.size * 1.6); c.lineTo(-p.size * 0.6, 0); c.closePath(); c.fill(); c.restore(); break;
        case 'cross': c.fillRect(p.x - p.size, p.y - p.size * 0.3, p.size * 2, p.size * 0.6); c.fillRect(p.x - p.size * 0.3, p.y - p.size, p.size * 0.6, p.size * 2); break;
        case 'ring': c.lineWidth = 1.2; c.beginPath(); c.arc(p.x, p.y, p.size * (1.4 - a * 0.4), 0, 6.283); c.stroke(); break;
        default: c.beginPath(); c.arc(p.x, p.y, p.size * (0.4 + 0.6 * a), 0, 6.283); c.fill();
      }
    }
    c.globalAlpha = 1; c.globalCompositeOperation = 'source-over';
  }
  function loop(now) {
    requestAnimationFrame(loop);
    const dt = Math.min(0.05, (now - (FX.last || now)) / 1000); FX.last = now;
    syncOverlay(now);
    const c = FX.ctx;
    c.setTransform(1, 0, 0, 1, 0, 0); c.globalAlpha = 1; c.globalCompositeOperation = 'source-over';
    c.clearRect(0, 0, FX.cv.width, FX.cv.height);
    c.setTransform(FX.sx, 0, 0, FX.sy, 0, 0);
    if (CFG.camera) { const cam = CFG.camera(); if (cam) c.translate(-cam.x, -cam.y); }
    const keep = [];
    for (const e of FX.list) {
      e.t += dt;
      if (e.t >= e.life) continue;
      keep.push(e);
      if (e.t < 0) continue;
      c.save();
      try { e.draw(c, e.t / e.life, dt); } catch (err) { keep.pop(); }
      c.restore();
    }
    FX.list = keep;
    drawParticles(c, dt);
    updateBar();
  }

  // =================== UI ===================
  const CSS = `
.ls-fx{position:fixed;pointer-events:none;z-index:40}
.ls-bar{position:fixed;left:50%;bottom:14px;transform:translateX(-50%);display:none;gap:6px;padding:8px 10px;background:linear-gradient(180deg,rgba(20,24,40,.9),rgba(8,10,20,.94));border:1px solid rgba(255,215,120,.35);border-radius:14px;box-shadow:0 8px 30px rgba(0,0,0,.5),inset 0 1px 0 rgba(255,255,255,.08);z-index:85;font-family:"Kanit","Segoe UI",sans-serif;user-select:none}
.ls-slot{position:relative;width:50px;height:50px;border-radius:10px;background:radial-gradient(circle at 50% 35%,#2c3350,#141828);border:1px solid rgba(255,255,255,.12);display:grid;place-items:center;font-size:24px;cursor:pointer;transition:transform .12s,border-color .12s,box-shadow .12s;overflow:hidden}
.ls-slot:hover{transform:translateY(-2px);border-color:var(--c,#ffd166)}
.ls-slot.ready{box-shadow:inset 0 0 12px -3px var(--c,#ffd166)}
.ls-slot.nomp{filter:grayscale(.85) brightness(.6)}
.ls-slot.cast{animation:ls-pop .25s}
.ls-slot.drop{outline:2px dashed #ffd166}
.ls-slot::after{content:"";position:absolute;inset:0;background:conic-gradient(rgba(0,0,0,.72) calc(var(--cd,0)*1turn),transparent 0);pointer-events:none}
.ls-slot .k{position:absolute;left:4px;top:2px;font-size:10px;color:#ffe9a8;text-shadow:0 1px 2px #000;z-index:2}
.ls-slot .m{position:absolute;right:3px;bottom:1px;font-size:9px;color:#8fd3ff;z-index:2}
.ls-slot .t{position:absolute;inset:0;display:grid;place-items:center;font-size:15px;font-weight:800;color:#fff;text-shadow:0 0 4px #000;z-index:3}
.ls-bookbtn{font-size:20px;background:linear-gradient(180deg,#3b2f12,#1c160a);border-color:rgba(255,215,120,.5)}
@keyframes ls-pop{50%{transform:scale(1.15)}}
.ls-book{position:fixed;inset:0;display:none;place-items:center;padding-bottom:80px;background:rgba(0,0,0,.55);backdrop-filter:blur(3px);z-index:80;font-family:"Kanit","Segoe UI",sans-serif}
.ls-book.open{display:grid}
.ls-win{width:min(940px,94vw);max-height:80vh;display:flex;flex-direction:column;background:linear-gradient(160deg,#1b2036,#0d1020);border:1px solid rgba(255,215,120,.35);border-radius:16px;color:#e9ecff;box-shadow:0 20px 60px rgba(0,0,0,.6)}
.ls-head{display:flex;align-items:center;gap:12px;padding:14px 18px;border-bottom:1px solid rgba(255,255,255,.08)}
.ls-head h3{margin:0;font-size:18px;color:#ffd98a}
.ls-me{font-size:12px;opacity:.8;margin-left:auto}
.ls-x{background:none;border:0;color:#fff;font-size:20px;cursor:pointer}
.ls-tabs{display:flex;gap:6px;padding:10px 18px;flex-wrap:wrap}
.ls-tab{padding:6px 12px;border-radius:999px;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);color:#cfd5ff;font-size:13px;cursor:pointer;font-family:inherit}
.ls-tab.mine{border-color:rgba(255,215,120,.5)}
.ls-tab.mine::before{content:"★ ";color:#ffd166}
.ls-tab.on{background:linear-gradient(90deg,#ffcf6b,#ff9f43);color:#231400;font-weight:700}
.ls-tab.on::before{color:#231400}
.ls-grid{padding:6px 18px 18px;overflow:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:12px}
.ls-card{position:relative;padding:12px;border-radius:12px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08)}
.ls-card.unlocked{border-color:var(--c);box-shadow:0 0 18px -8px var(--c);cursor:grab}
.ls-card.can{border-color:#7dff9a;animation:ls-glow 1.6s infinite}
.ls-card.locked{opacity:.75}
.ls-card .top{display:flex;gap:10px;align-items:center}
.ls-ico{width:42px;height:42px;border-radius:10px;display:grid;place-items:center;font-size:22px;background:radial-gradient(circle,var(--c) -40%,#141828 70%)}
.ls-name{font-weight:700}
.ls-meta{font-size:11px;opacity:.75}
.ls-desc{font-size:12.5px;margin:8px 0;opacity:.9;line-height:1.45}
.ls-stats{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
.ls-stats span{font-size:11px;padding:2px 7px;border-radius:6px;background:rgba(255,255,255,.07)}
.ls-conds{list-style:none;padding:0;margin:0 0 10px;font-size:12px;line-height:1.6}
.ls-conds li.ok{color:#8dffb0}.ls-conds li.no{color:#ff8f8f}
.ls-act{display:flex;gap:6px}
.ls-act button{flex:1;padding:7px;border:0;border-radius:8px;font-weight:700;cursor:pointer;font-family:inherit}
.ls-learn{background:linear-gradient(90deg,#7dff9a,#38d39f);color:#062615}
.ls-learn:disabled{background:#3a3f55;color:#8b90a8;cursor:not-allowed}
.ls-equip{background:#2b3355;color:#e9ecff}
.ls-badge{position:absolute;top:10px;right:10px;font-size:10px;padding:2px 8px;border-radius:999px}
@keyframes ls-glow{50%{box-shadow:0 0 22px -6px #7dff9a}}
.ls-toasts{position:fixed;top:70px;left:50%;transform:translateX(-50%);display:flex;flex-direction:column;align-items:center;gap:6px;z-index:90;pointer-events:none;font-family:"Kanit","Segoe UI",sans-serif}
.ls-toast{padding:8px 16px;border-radius:10px;background:rgba(10,12,24,.92);border:1px solid var(--c,#ffd166);color:#fff;font-size:13px;animation:ls-in .25s,ls-out .4s 2.4s forwards}
@keyframes ls-in{from{opacity:0;transform:translateY(-8px)}}
@keyframes ls-out{to{opacity:0;transform:translateY(-8px)}}
.ls-tip{position:fixed;z-index:95;pointer-events:none;width:260px;padding:8px 10px;border-radius:10px;background:rgba(8,10,20,.95);border:1px solid var(--c,#ffd166);color:#e9ecff;font-size:12px;display:none;font-family:"Kanit","Segoe UI",sans-serif}`;

  function toast(msg, color = '#ffd166') {
    if (!UI.toasts) return;
    const t = h('div', 'ls-toast', esc(msg)); t.style.setProperty('--c', color);
    UI.toasts.appendChild(t); later(2.9, () => t.remove());
    while (UI.toasts.children.length > 4) UI.toasts.firstChild.remove();
  }
  function statChips(s) {
    const a = [];
    if (s.type === 'single' || s.type === 'aoe') {
      a.push(`💥 ${Math.round(s.mult * 100)}%${s.hits > 1 ? ' × ' + s.hits : ''}`);
      a.push(s.type === 'single' ? `🎯 ระยะ ${s.range}` : `⭕ รัศมี ${s.radius} (สูงสุด ${s.max_t})`);
    }
    if (s.stun) a.push(`💫 สตัน ${s.stun}s`);
    if (s.dot) a.push(`🔥 DoT ${Math.round(s.dot.pct * 100)}%/วิ ${s.dot.sec}s`);
    if (s.lifesteal) a.push(`🧛 ดูดเลือด ${Math.round(s.lifesteal * 100)}%`);
    if (s.type === 'heal') a.push(`💚 ฟื้น ${Math.round(s.heal * 100)}% HP`);
    if (s.type === 'buff') a.push(`⬆️ ${s.stat.toUpperCase()} ×${s.buff_mult} ${s.dur}s`);
    if (s.party) a.push(`👥 รอบตัว ${s.party}`);
    return a.map(x => `<span>${x}</span>`).join('');
  }
  function showTip(s, el) {
    const t = UI.tip; t.style.setProperty('--c', s.color);
    t.innerHTML = `<b>${s.icon} ${esc(s.name)}</b><div style="opacity:.75;font-size:11px">${TYPE_TH[s.type]} • MP ${s.mp} • CD ${s.cd}s</div><div style="margin:4px 0">${esc(s.desc)}</div><div class="ls-stats">${statChips(s)}</div>`;
    t.style.display = 'block';
    const r = el.getBoundingClientRect();
    t.style.left = Math.max(8, Math.min(innerWidth - 270, r.left + r.width / 2 - 130)) + 'px';
    t.style.top = Math.max(8, r.top - t.offsetHeight - 10) + 'px';
  }
  const hideTip = () => { if (UI.tip) UI.tip.style.display = 'none'; };

  function buildUI() {
    const st = h('style'); st.textContent = CSS; document.head.appendChild(st);
    UI.bar = h('div', 'ls-bar');
    CFG.hotkeys.forEach((code, i) => {
      const sl = h('div', 'ls-slot'); sl.dataset.i = i; sl.draggable = true;
      sl.addEventListener('click', () => (S.bar[i] ? cast(S.bar[i]) : openBook()));
      sl.addEventListener('contextmenu', ev => { ev.preventDefault(); S.bar[i] = null; saveBar(); renderBar(); hideTip(); });
      sl.addEventListener('dragstart', ev => { if (!S.bar[i]) return ev.preventDefault(); ev.dataTransfer.setData('text/plain', JSON.stringify({ id: S.bar[i], from: i })); });
      sl.addEventListener('dragover', ev => { ev.preventDefault(); sl.classList.add('drop'); });
      sl.addEventListener('dragleave', () => sl.classList.remove('drop'));
      sl.addEventListener('drop', ev => {
        ev.preventDefault(); sl.classList.remove('drop');
        let d; try { d = JSON.parse(ev.dataTransfer.getData('text/plain')); } catch (e) { return; }
        const sk = d && skill(d.id); if (!sk) return;
        if (!sk.unlocked) return toast('ต้องปลดล็อกสกิลก่อน', '#ff8f8f');
        if (d.from != null) S.bar[d.from] = S.bar[i];
        else { const dup = S.bar.indexOf(d.id); if (dup >= 0) S.bar[dup] = null; }
        S.bar[i] = d.id; saveBar(); renderBar();
      });
      sl.addEventListener('mouseenter', () => { const sk = skill(S.bar[i]); if (sk) showTip(sk, sl); });
      sl.addEventListener('mouseleave', hideTip);
      UI.bar.appendChild(sl); UI.slots.push(sl);
    });
    const bb = h('div', 'ls-slot ls-bookbtn', '📖'); bb.title = `สมุดสกิล (${keyLabel(CFG.bookKey)})`; bb.onclick = toggleBook;
    UI.bar.appendChild(bb);
    document.body.appendChild(UI.bar);

    UI.book = h('div', 'ls-book', `<div class="ls-win"><div class="ls-head"><h3>📖 สมุดสกิล</h3><div class="ls-me"></div><button class="ls-x" title="ปิด">✕</button></div><div class="ls-tabs"></div><div class="ls-grid"></div></div>`);
    UI.book.addEventListener('click', ev => { if (ev.target === UI.book) closeBook(); });
    $('.ls-x', UI.book).onclick = closeBook;
    document.body.appendChild(UI.book);

    UI.toasts = h('div', 'ls-toasts'); document.body.appendChild(UI.toasts);
    UI.tip = h('div', 'ls-tip'); document.body.appendChild(UI.tip);

    FX.cv = h('canvas', 'ls-fx'); FX.ctx = FX.cv.getContext('2d'); document.body.appendChild(FX.cv);

    document.addEventListener('keydown', ev => {
      const tg = ev.target;
      if (tg && (tg.tagName === 'INPUT' || tg.tagName === 'TEXTAREA' || tg.isContentEditable)) return;
      if (ev.code === CFG.bookKey) { toggleBook(); return; }
      if (ev.code === 'Escape' && bookOpen()) { closeBook(); return; }
      const i = CFG.hotkeys.indexOf(ev.code);
      if (i >= 0 && S.bar[i]) { ev.preventDefault(); cast(S.bar[i]); }
    });
  }
  function renderBar() {
    UI.bar.style.display = S.me ? 'flex' : 'none';
    UI.slots.forEach((sl, i) => {
      const sk = skill(S.bar[i]);
      sl.style.setProperty('--c', sk ? sk.color : '#555555');
      sl.innerHTML = `<span class="k">${esc(keyLabel(CFG.hotkeys[i]))}</span>` +
        (sk ? `${sk.icon}<span class="m">${sk.mp}</span><span class="t"></span>` : '<span style="opacity:.25;font-size:16px">＋</span>');
    });
  }
  function updateBar() {
    const now = performance.now();
    UI.slots.forEach((sl, i) => {
      const sk = skill(S.bar[i]);
      if (!sk) { sl.style.setProperty('--cd', 0); sl.classList.remove('nomp', 'ready'); return; }
      const left = Math.max(0, (S.cd[sk.id] || 0) - now);
      sl.style.setProperty('--cd', left > 0 ? (left / (sk.cd * 1000)).toFixed(3) : 0);
      const t = sl.firstElementChild && sl.querySelector('.t');
      if (t) t.textContent = left > 0 ? (left >= 1000 ? Math.ceil(left / 1000) : (left / 1000).toFixed(1)) : '';
      sl.classList.toggle('nomp', S.mp < sk.mp);
      sl.classList.toggle('ready', left <= 0 && S.mp >= sk.mp);
    });
  }
  function loadBar() {
    S.barKey = 'lumi_skillbar_' + S.me.username;
    let arr = null; try { arr = JSON.parse(localStorage.getItem(S.barKey)); } catch (e) { /* ignore */ }
    S.bar = CFG.hotkeys.map((_, i) => (arr && arr[i] && S.byId[arr[i]] ? arr[i] : null));
    if (!arr) { S.tree.filter(s => s.unlocked).forEach(s => { const i = S.bar.indexOf(null); if (i >= 0) S.bar[i] = s.id; }); saveBar(); }
  }
  function saveBar() { if (S.barKey) localStorage.setItem(S.barKey, JSON.stringify(S.bar)); }
  function equip(id) {
    if (S.bar.includes(id)) return toast('อยู่ในแถบสกิลแล้ว');
    const i = S.bar.indexOf(null);
    if (i < 0) return toast('ช่องเต็ม — ลากการ์ดไปวางทับช่องที่ต้องการ', '#8fd3ff');
    S.bar[i] = id; saveBar(); renderBar(); toast(`ใส่ช่อง ${keyLabel(CFG.hotkeys[i])} แล้ว`, skill(id).color);
  }

  const bookOpen = () => UI.book.classList.contains('open');
  function openBook() { UI.book.classList.add('open'); renderBook(); refreshTree(); }
  function closeBook() { UI.book.classList.remove('open'); hideTip(); }
  function toggleBook() { bookOpen() ? closeBook() : openBook(); }

  function renderBook() {
    const me = S.me; if (!me) return;
    $('.ls-me', UI.book).innerHTML = `${esc(me.username)} • ${esc(me.job_label)} Lv.${me.level} • 💰 ${fmt(me.gold)} G • ⚔️ ${fmt(me.kills)} kills`;
    if (!S.tab || !S.groups.some(g => g.job === S.tab)) S.tab = me.job === 'Novice' ? 'All' : me.job;
    const tabs = $('.ls-tabs', UI.book); tabs.innerHTML = '';
    S.groups.forEach(g => {
      const list = S.tree.filter(s => s.job === g.job), un = list.filter(s => s.unlocked).length;
      const b = h('button', 'ls-tab' + (g.job === S.tab ? ' on' : '') + (g.mine ? ' mine' : ''), `${esc(g.label)} <small>(${un}/${list.length})</small>`);
      b.onclick = () => { S.tab = g.job; renderBook(); };
      tabs.appendChild(b);
    });
    const grid = $('.ls-grid', UI.book); grid.innerHTML = '';
    S.tree.filter(s => s.job === S.tab).forEach(s => grid.appendChild(card(s)));
  }
  function card(s) {
    const st = s.unlocked ? 'unlocked' : (s.can_unlock ? 'can' : 'locked');
    const badge = s.unlocked ? ['ปลดล็อกแล้ว', '#38d39f'] : s.can_unlock ? ['พร้อมปลดล็อก', '#ffd166'] : ['ล็อก', '#8b90a8'];
    const c = h('div', 'ls-card ' + st); c.style.setProperty('--c', s.color);
    c.innerHTML = `<span class="ls-badge" style="background:${badge[1]}33;color:${badge[1]}">${badge[0]}</span>
      <div class="top"><div class="ls-ico">${s.icon}</div><div><div class="ls-name">${esc(s.name)}</div>
      <div class="ls-meta">${TYPE_TH[s.type]}${s.ground ? ' • เล็งพื้นที่' : ''} • MP ${s.mp} • CD ${s.cd}s</div></div></div>
      <div class="ls-desc">${esc(s.desc)}</div><div class="ls-stats">${statChips(s)}</div>
      ${s.unlocked ? '' : `<ul class="ls-conds">${s.conditions.map(x => `<li class="${x.ok ? 'ok' : 'no'}">${x.ok ? '✔' : '✖'} ${esc(x.label)}</li>`).join('')}</ul>`}
      <div class="ls-act"></div>`;
    const act = $('.ls-act', c);
    if (s.unlocked) {
      const b1 = h('button', 'ls-equip', '➕ ใส่ช่องลัด'); b1.onclick = () => equip(s.id);
      const b2 = h('button', 'ls-equip', '▶ ใช้เลย'); b2.onclick = () => { closeBook(); cast(s.id); };
      act.append(b1, b2);
      c.draggable = true;
      c.addEventListener('dragstart', ev => ev.dataTransfer.setData('text/plain', JSON.stringify({ id: s.id })));
    } else {
      const b = h('button', 'ls-learn', s.gold ? `🔓 ปลดล็อก (${fmt(s.gold)} G)` : '🔓 ปลดล็อก (ฟรี)');
      b.disabled = !s.can_unlock; b.onclick = () => learn(s.id, b);
      act.appendChild(b);
    }
    return c;
  }

  // ---------------- network ----------------
  async function api(url, body) {
    const opt = body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), credentials: 'same-origin' }
                     : { credentials: 'same-origin' };
    const r = await fetch(url, opt);
    return r.json();
  }
  async function refreshTree() {
    try {
      const r = await api('/api/skills/tree');
      if (!r.success) return;
      S.tree = r.skills; S.groups = r.groups; S.me = r.me; S.mp = r.me.mp;
      S.byId = {}; S.tree.forEach(s => { S.byId[s.id] = s; });
      if (S.barKey !== 'lumi_skillbar_' + r.me.username) loadBar();
      S.bar = S.bar.map(id => (id && S.byId[id] && S.byId[id].unlocked ? id : null));
      (r.new || []).forEach(id => {
        const s = S.byId[id]; if (!s) return;
        toast(`🆕 ได้รับสกิลใหม่: ${s.icon} ${s.name}`, s.color); celebrate(s);
        if (!S.bar.includes(id)) { const i = S.bar.indexOf(null); if (i >= 0) S.bar[i] = id; }
      });
      saveBar(); renderBar();
      if (bookOpen()) renderBook();
    } catch (e) { /* ยังไม่ล็อกอิน */ }
  }
  async function learn(id, btn) {
    btn.disabled = true;
    try {
      const r = await api('/api/skills/learn', { skill_id: id });
      if (!r.success) { toast(r.message, '#ff8f8f'); btn.disabled = false; return; }
      toast(`✨ ปลดล็อก ${r.skill.icon} ${r.skill.name}!`, r.skill.color); celebrate(r.skill);
      await refreshTree();
      if (!S.bar.includes(id)) { const i = S.bar.indexOf(null); if (i >= 0) { S.bar[i] = id; saveBar(); renderBar(); } }
    } catch (e) { toast('เชื่อมต่อเซิร์ฟเวอร์ไม่ได้', '#ff8f8f'); btn.disabled = false; }
  }
  function pickTarget(s) {
    const rng = s.type === 'single' || s.ground ? s.range : s.radius;
    const cur = mon(S.target);
    if (cur && cur.alive && dist(cur, S.pos) <= rng) return cur.id;
    let best = null, bd = rng;
    for (const m of Object.values(S.monsters)) { if (!m.alive) continue; const d = dist(m, S.pos); if (d < bd) { bd = d; best = m; } }
    return best ? best.id : null;
  }
  function cast(id) {
    const s = skill(id); if (!s || !S.socket) return;
    if (!s.unlocked) return toast('ยังไม่ได้ปลดล็อกสกิลนี้', '#ff8f8f');
    if ((S.cd[id] || 0) > performance.now()) return;
    if (S.mp < s.mp) return toast('MP ไม่พอ', '#8fd3ff');
    const payload = { skill: id };
    if (s.type === 'single' || s.ground) { const t = pickTarget(s); if (t != null) payload.monster_id = t; }
    S.socket.emit('use_skill', payload);
    const i = S.bar.indexOf(id);
    if (i >= 0) { const sl = UI.slots[i]; sl.classList.remove('cast'); void sl.offsetWidth; sl.classList.add('cast'); }
  }
  function bindSocket(sock) {
    const orig = sock.emit;
    sock.emit = function (ev, data) {   // จับเป้าหมาย/ตำแหน่งจากโค้ดเกมเดิมโดยไม่ต้องแก้
      try {
        if (ev === 'attack_monster' && data && data.monster_id != null) S.target = String(data.monster_id);
        if (ev === 'move' && data && isFinite(data.x) && isFinite(data.y)) S.pos = { x: +data.x, y: +data.y };
      } catch (e) { /* ignore */ }
      return orig.apply(this, arguments);
    };
    sock.on('connect', refreshTree);
    sock.on('monsters_sync', d => { S.map = d.map; S.monsters = {}; (d.monsters || []).forEach(m => { S.monsters[String(m.id)] = m; }); });
    sock.on('monsters_update', d => { if (S.map && d.map !== S.map) return; (d.monsters || []).forEach(m => { S.monsters[String(m.id)] = m; }); });
    sock.on('move_player', p => { if (p && p.sid === sock.id) S.pos = { x: p.x, y: p.y }; });
    sock.on('players_in_map', all => { const me = all && all[sock.id]; if (me) S.pos = { x: me.x, y: me.y }; });
    sock.on('stats_update', d => { if (d && d.mp != null) S.mp = d.mp; });
    sock.on('respawned', d => { S.pos = { x: 400, y: 300 }; if (d && d.user) S.mp = d.user.maxMp; });
    sock.on('skill_fx', playFx);
    sock.on('skill_result', r => {
      if (!r) return;
      if (r.success) { const s = skill(r.skill); S.cd[r.skill] = performance.now() + (r.cd || (s ? s.cd : 0)) * 1000; if (r.mp != null) S.mp = r.mp; }
      else if (r.message) toast(r.message, '#ff8f8f');
    });
    sock.on('skill_unlocked', () => refreshTree());
    sock.on('skill_buff', d => toast(`${d.icon} ${d.from} ใช้ ${d.name} ให้คุณ (${String(d.stat).toUpperCase()} ×${d.mult} ${d.duration}s)`, '#ffe680'));
    sock.on('kill_reward', d => { if (d && d.leveled_up) later(0.3, refreshTree); });
  }
  function hookFetch() {   // เลื่อนอาชีพ/ล็อกอิน/รับเควส → โหลดต้นไม้สกิลใหม่
    const of = window.fetch; if (!of || of.__ls) return;
    const nf = function (input) {
      const p = of.apply(this, arguments);
      const u = typeof input === 'string' ? input : (input && input.url) || '';
      if (/\/api\/(job\/change|login|quests\/claim)/.test(u)) p.then(() => later(0.3, refreshTree)).catch(() => {});
      return p;
    };
    nf.__ls = true; window.fetch = nf;
  }

  // ---------------- public API ----------------
  window.LumiSkills = {
    init(opts = {}) {
      const sock = opts.socket || window.socket;
      if (!sock) throw new Error('LumiSkills.init: ต้องส่ง { socket }');
      Object.assign(CFG, opts); delete CFG.socket;
      if (S.socket) return;
      S.socket = sock;
      buildUI(); bindSocket(sock); hookFetch();
      requestAnimationFrame(loop);
      refreshTree();
    },
    refresh: refreshTree, cast, open: openBook, close: closeBook, play: playFx,
    demo(fx = 'meteor') {   // ทดสอบเอฟเฟกต์ใน console โดยไม่ต้องสู้จริง
      const { x, y } = S.pos, s = S.tree.find(k => k.fx === fx) || { name: fx, color: '#ffd166', radius: 160, hits: 1 };
      const targets = [0, 1, 2].map(i => ({ id: 'demo' + i, x: x + 120 + i * 30, y: y - 20 + i * 25, dmg: 999,
        hits: Array(s.hits || 1).fill(333), crit: i === 0, died: i === 2 }));
      playFx({ fx, name: s.name, color: s.color, x, y, cx: targets[1].x, cy: targets[1].y,
        radius: (s.type === 'heal' || s.type === 'buff') ? (s.party || 0) : (s.radius || 160),
        stun: s.stun || 0, dot: s.dot ? s.dot.sec : 0, targets, allies: [{ x, y, amt: 250 }] });
    },
  };
})();