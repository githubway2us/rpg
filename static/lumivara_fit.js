/* Lumivara Fit — ปรับขนาดเกมตามเบราว์เซอร์ + เต็มจอ (โหลดหลัง game.js เสมอ) */
(function () {
  'use strict';

  const canvas  = document.getElementById('gameCanvas');
  /* ===== เขตห้ามเดินในเมือง (Collision) ===== */
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

  // กันตกขอบแมพ
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
  const wrapper = document.getElementById('game-wrapper');
  if (!canvas || !wrapper) return;

  const LOGICAL_W = canvas.width  || 800;
  const LOGICAL_H = canvas.height || 600;

  window.LUMI_VIEW = { scale: 1, fullscreen: false, vw: 0, vh: 0 };

  function updateViewInfo() {
    const r = canvas.getBoundingClientRect();
    window.LUMI_VIEW.vw = r.width;
    window.LUMI_VIEW.vh = r.height;
    window.LUMI_VIEW.scale = Math.min(r.width / LOGICAL_W, r.height / LOGICAL_H);
    window.LUMI_VIEW.fullscreen = !!(document.fullscreenElement || document.webkitFullscreenElement);
    window.dispatchEvent(new CustomEvent('lumi:resize', { detail: window.LUMI_VIEW }));
  }

  /* ================= fitToScreen : เรียกตอนล็อกอินสำเร็จ ================= */
  let autoFsTried = false;
  let tapFallbackArmed = false;

  window.fitToScreen = function () {
    // 1) บังคับคำนวณขนาดใหม่ทันที (wrapper เพิ่งโดน display:block)
    updateViewInfo();
    requestAnimationFrame(updateViewInfo);

    // 2) ขอเต็มจอ — ต้องทำในช่วง user gesture หลังกดปุ่ม (Chrome/Firefox ~5 วินาที)
    if (!autoFsTried) {
      autoFsTried = true;
      tryFullscreen();
      // ถ้า 400ms แล้วยังไม่เต็มจอ (gesture หมดเวลา / ไม่รองรับ) → รอแตะจอครั้งแรกแทน
      setTimeout(() => {
        const fsEl = document.fullscreenElement || document.webkitFullscreenElement;
        if (!fsEl) armTapFallback();
      }, 400);
    }
  };

  function tryFullscreen() {
    const fsEl = document.fullscreenElement || document.webkitFullscreenElement;
    if (fsEl) return;
    let p = null;
    try {
      if (wrapper.requestFullscreen)            p = wrapper.requestFullscreen({ navigationUI: 'hide' });
      else if (wrapper.webkitRequestFullscreen) p = wrapper.webkitRequestFullscreen();
    } catch (e) { /* ไม่รองรับ */ }
    if (p && p.catch) p.catch(() => armTapFallback());

    // ล็อกแนวนอนมือถือ (เบราว์เซอร์ที่ไม่รองรับจะข้ามไปเอง)
    if (screen.orientation && screen.orientation.lock) {
      screen.orientation.lock('landscape').catch(() => {});
    }
  }

  function armTapFallback() {
    if (tapFallbackArmed) return;
    tapFallbackArmed = true;
    canvas.addEventListener('pointerdown', function once() {
      canvas.removeEventListener('pointerdown', once);
      tryFullscreen();
    });
  }

  /* ================= toggleFullscreen : ปุ่ม ⛶ / กด F ================= */
  window.toggleFullscreen = window.toggleFullscreen || function () {
    const fsEl = document.fullscreenElement || document.webkitFullscreenElement;
    if (!fsEl) tryFullscreen();
    else {
      const exit = document.exitFullscreen || document.webkitExitFullscreen;
      if (exit) exit.call(document);
    }
  };

  /* ================= ติดตามการย่อ/ขยายหน้าต่าง (รวม Ctrl + / Ctrl -) ================= */
  let rsTimer;
  const onResize = () => { clearTimeout(rsTimer); rsTimer = setTimeout(updateViewInfo, 50); };

  window.addEventListener('resize', onResize, { passive: true });
  window.addEventListener('orientationchange', onResize, { passive: true });
  if (window.visualViewport) visualViewport.addEventListener('resize', onResize, { passive: true });
  document.addEventListener('fullscreenchange', onResize);
  document.addEventListener('webkitfullscreenchange', onResize);
  if (window.ResizeObserver) new ResizeObserver(onResize).observe(wrapper);
  updateViewInfo();

  /* ================= แปลงพิกัดจอ → พิกัดเกม 800x600 ================= */
  window.toGameCoords = function (clientX, clientY) {
    const r = canvas.getBoundingClientRect();
    return {
      x: (clientX - r.left) * (canvas.width  / r.width),
      y: (clientY - r.top)  * (canvas.height / r.height)
    };
  };

  // แก้ offsetX/offsetY ให้เป็นพิกัดเกมอัตโนมัติ (ถ้าระบบคลิกเพี้ยนหลังยืด canvas ลบบล็อกนี้ได้)
  ['pointerdown','pointermove','pointerup','mousedown','mousemove','mouseup','click']
  .forEach(type => {
    window.addEventListener(type, e => {
      if (e.target !== canvas) return;
      const p = window.toGameCoords(e.clientX, e.clientY);
      try {
        Object.defineProperty(e, 'offsetX', { value: p.x, configurable: true });
        Object.defineProperty(e, 'offsetY', { value: p.y, configurable: true });
      } catch (_) {}
    }, { capture: true, passive: true });
  });

  /* ================= กด F = สลับเต็มจอ (Esc = ออก เป็นค่าเริ่มต้นเบราว์เซอร์) ================= */
  window.addEventListener('keydown', e => {
    if ((e.key === 'f' || e.key === 'F') &&
        !/INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || '')) {
      e.preventDefault();
      window.toggleFullscreen();
    }
  });

  /* ================= กันเบราว์เซอร์มือถือรบกวน ================= */
  document.addEventListener('gesturestart', e => e.preventDefault()); // กัน pinch-zoom iOS
  wrapper.addEventListener('dblclick', e => e.preventDefault());      // กัน double-tap ซูม
})();