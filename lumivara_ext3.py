# -*- coding: utf-8 -*-
"""
lumivara_ext3.py — BANK PACK v3.0 (🏦 ธนาคาร Lumivara)
- เงินฝาก/ถอน (ทำรายการได้ที่เมือง) + ดอกเบี้ย 1.5%/ชม. (สะสมออฟไลน์สูงสุด 24 ชม.)
- 🛡️ เงินฝากไม่ถูกหักตอนตาย (อยู่ตารางแยกจาก users.gold)
- UI ฉีดอัตโนมัติ + ปุ่ม HUD 🏦 + รองรับป้าย 'bank' ใน TownScene
ปรับอัตราดอกเบี้ยได้: set LUMIVARA_BANK_RATE=0.02 ก่อนรัน
"""
import time, os, sqlite3, logging, threading
from flask import request, jsonify, session, Response

log = logging.getLogger("lumivara.ext3")
_G = {"g": None}
V3 = "3.0"

BANK_RATE = float(os.environ.get("LUMIVARA_BANK_RATE", "0.015"))  # ต่อชั่วโมง
BANK_CAP_BASE = 200_000        # ฐานยอดฝากสูงสุดที่คิดดอกเบี้ย
BANK_MAX_HOURS = 24.0          # สะสมดอกเบี้ยออฟไลน์สูงสุด (ชม.)
BANK_LOG_KEEP = 50
_rl = {}

def _rl_ok(uid, key, sec=0.6):
    now = time.time(); k = (uid, key)
    if now - _rl.get(k, 0) < sec:
        return False
    _rl[k] = now
    return True

def _to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0

# ================= DB =================
def _db_init(g):
    conn = sqlite3.connect(g["DB_PATH"], timeout=15)
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS bank_accounts (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            balance INTEGER DEFAULT 0, total_interest INTEGER DEFAULT 0,
            last_interest_at REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS bank_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            action TEXT, amount INTEGER, balance_after INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_banklog ON bank_log(user_id)")
        conn.commit()
    finally:
        conn.close()

# ================= CORE =================
def _ensure(conn, uid):
    row = conn.execute("SELECT * FROM bank_accounts WHERE user_id=?", (uid,)).fetchone()
    if not row:
        conn.execute("""INSERT INTO bank_accounts (user_id, balance, total_interest, last_interest_at)
                        VALUES (?,?,?,?)""", (uid, 0, 0, time.time()))
        row = conn.execute("SELECT * FROM bank_accounts WHERE user_id=?", (uid,)).fetchone()
    return row

def _log(conn, uid, action, amount, bal_after):
    conn.execute("INSERT INTO bank_log (user_id, action, amount, balance_after) VALUES (?,?,?,?)",
                 (uid, action, amount, bal_after))
    conn.execute("""DELETE FROM bank_log WHERE user_id=? AND id NOT IN
                    (SELECT id FROM bank_log WHERE user_id=? ORDER BY id DESC LIMIT ?)""",
                 (uid, uid, BANK_LOG_KEEP))

def _accrue(conn, uid):
    """คิดดอกเบี้ยย้อนหลังทุกครบชั่วโมง (lazy) — คืนจำนวนที่ได้รับรอบนี้"""
    row = conn.execute("SELECT * FROM bank_accounts WHERE user_id=?", (uid,)).fetchone()
    if not row:
        return 0
    if row["balance"] <= 0:
        if not row["last_interest_at"]:
            conn.execute("UPDATE bank_accounts SET last_interest_at=? WHERE user_id=?",
                         (time.time(), uid))
        return 0
    now = time.time()
    last = row["last_interest_at"] or now
    full = int(min((now - last) / 3600.0, BANK_MAX_HOURS))
    if full < 1:
        return 0
    base = min(row["balance"], BANK_CAP_BASE)
    interest = int(base * BANK_RATE * full)
    newbal = row["balance"] + interest
    conn.execute("""UPDATE bank_accounts SET balance=?, total_interest=total_interest+?,
                    last_interest_at=? WHERE user_id=?""",
                 (newbal, interest, last + full * 3600.0, uid))
    if interest > 0:
        _log(conn, uid, "interest", interest, newbal)
    return interest

def _emit_gold(uid, gold):
    g = _G["g"]
    sid = g["find_sid_by_uid"](uid)
    if sid:
        g["socketio"].emit("gold_update", {"gold": gold}, room=sid)

def _in_town(g, uid):
    found = g["find_player_by_uid"](uid)
    return bool(found and found[1]["map"] == "town")

# ================= 🛡️ Death protection notice =================
def _wrap_death(g):
    orig = g.get("handle_player_death")
    if not orig:
        log.warning("[ext3] ไม่พบ handle_player_death — ข้าม (ป้องกันอยู่แล้วเพราะธนาคารเป็นตารางแยก)")
        return

    def wrapped(sid, p, killer_name, pvp=False):
        orig(sid, p, killer_name, pvp)
        try:
            with g["get_db"]() as conn:
                r = conn.execute("SELECT balance FROM bank_accounts WHERE user_id=?",
                                 (p["id"],)).fetchone()
            if r and r["balance"] > 0:
                g["socketio"].emit("system_message",
                                   {"message": f"🏦 เงินฝาก {r['balance']:,} G ในธนาคารปลอดภัย"},
                                   room=sid)
        except Exception:
            log.exception("bank death notice")

    g["handle_player_death"] = wrapped

# ================= HTTP =================
def _register_http(g):
    app, socketio = g["app"], g["socketio"]
    get_db, get_user_by_id, live_user = g["get_db"], g["get_user_by_id"], g["live_user"]

    @app.route("/ext/lumivara_ext3.js")
    def ext3_js():
        return Response(_EXT3_JS, mimetype="application/javascript")

    @app.after_request
    def ext3_inject(resp):
        try:
            if request.path == "/" and (resp.headers.get("Content-Type", "") or "").startswith("text/html"):
                body = resp.get_data(as_text=True)
                tag = '<script src="/ext/lumivara_ext3.js?v=' + V3 + '"></script>'
                if "</body>" in body and "lumivara_ext3.js" not in body:
                    resp.set_data(body.replace("</body>", tag + "</body>"))
        except Exception:
            pass
        return resp

    @app.route("/api/ext3/status")
    def ext3_status():
        return jsonify({"success": True, "ext3": V3, "rate_pct": round(BANK_RATE * 100, 2),
                        "features": ["bank", "interest", "death_protect", "ui_inject", "townscene_hook"]})

    # ---------- ข้อมูลบัญชี (เปิดแผง = รับดอกเบี้ยที่ครบกำหนดด้วย) ----------
    @app.route("/api/bank/mine")
    def bank_mine():
        uid = session.get("user_id")
        if not uid:
            return jsonify({"success": False}), 401
        with get_db() as conn:
            _ensure(conn, uid)
            gained = _accrue(conn, uid)
            row = conn.execute("SELECT * FROM bank_accounts WHERE user_id=?", (uid,)).fetchone()
            logs = conn.execute("""SELECT action, amount, balance_after, created_at FROM bank_log
                                   WHERE user_id=? ORDER BY id DESC LIMIT 10""", (uid,)).fetchall()
            user = get_user_by_id(conn, uid)
        return jsonify({"success": True, "balance": row["balance"], "gold": user["gold"],
                        "total_interest": row["total_interest"], "interest_gained": gained,
                        "last_interest_at": row["last_interest_at"] or time.time(),
                        "rate": BANK_RATE, "rate_pct": round(BANK_RATE * 100, 2),
                        "cap": BANK_CAP_BASE, "max_hours": BANK_MAX_HOURS,
                        "in_town": _in_town(g, uid),
                        "log": [dict(l) for l in logs]})

    # ---------- ฝาก ----------
    @app.route("/api/bank/deposit", methods=["POST"])
    def bank_deposit():
        uid = session.get("user_id")
        if not uid:
            return jsonify({"success": False, "message": "กรุณาเข้าสู่ระบบ"}), 401
        if not _rl_ok(uid, "dep"):
            return jsonify({"success": False, "message": "ทำรายการช้าๆ หน่อย"}), 429
        if not _in_town(g, uid):
            return jsonify({"success": False, "message": "🏦 ฝากเงินได้ที่เมืองหลวงเท่านั้น"}), 400
        with get_db() as conn:
            user = get_user_by_id(conn, uid)
            _ensure(conn, uid)
            gained = _accrue(conn, uid)
            data = request.json or {}
            amt = user["gold"] if data.get("all") else _to_int(data.get("amount"))
            amt = min(amt, user["gold"])
            if amt < 1:
                return jsonify({"success": False, "message": "ไม่มีเงินในตัวให้ฝาก"}), 400
            row = conn.execute("SELECT balance FROM bank_accounts WHERE user_id=?", (uid,)).fetchone()
            conn.execute("UPDATE users SET gold=gold-? WHERE id=?", (amt, uid))
            conn.execute("UPDATE bank_accounts SET balance=balance+? WHERE user_id=?", (amt, uid))
            newbal = row["balance"] + amt
            _log(conn, uid, "deposit", amt, newbal)
            user = get_user_by_id(conn, uid)
        _emit_gold(uid, user["gold"])
        msg = f"🏦 ฝาก {amt:,} G สำเร็จ — ยอดฝากรวม {newbal:,} G"
        if gained > 0:
            msg += f" (💹 รับดอกเบี้ยค้างจ่าย +{gained:,} G)"
        return jsonify({"success": True, "message": msg, "balance": newbal, "user": live_user(user)})

    # ---------- ถอน ----------
    @app.route("/api/bank/withdraw", methods=["POST"])
    def bank_withdraw():
        uid = session.get("user_id")
        if not uid:
            return jsonify({"success": False, "message": "กรุณาเข้าสู่ระบบ"}), 401
        if not _rl_ok(uid, "wd"):
            return jsonify({"success": False, "message": "ทำรายการช้าๆ หน่อย"}), 429
        if not _in_town(g, uid):
            return jsonify({"success": False, "message": "🏦 ถอนเงินได้ที่เมืองหลวงเท่านั้น"}), 400
        with get_db() as conn:
            _ensure(conn, uid)
            gained = _accrue(conn, uid)
            row = conn.execute("SELECT balance FROM bank_accounts WHERE user_id=?", (uid,)).fetchone()
            data = request.json or {}
            amt = row["balance"] if data.get("all") else _to_int(data.get("amount"))
            amt = min(amt, row["balance"])
            if amt < 1:
                return jsonify({"success": False, "message": "ยอดฝากไม่พอ"}), 400
            conn.execute("UPDATE bank_accounts SET balance=balance-? WHERE user_id=?", (amt, uid))
            conn.execute("UPDATE users SET gold=gold+? WHERE id=?", (amt, uid))
            newbal = row["balance"] - amt
            _log(conn, uid, "withdraw", amt, newbal)
            user = get_user_by_id(conn, uid)
        _emit_gold(uid, user["gold"])
        msg = f"🏦 ถอน {amt:,} G — เหลือฝาก {newbal:,} G"
        if gained > 0:
            msg += f" (💹 รับดอกเบี้ยค้างจ่าย +{gained:,} G)"
        return jsonify({"success": True, "message": msg, "balance": newbal, "user": live_user(user)})

# ================= MAIN =================
def install(g):
    _G["g"] = g
    threading.Thread(target=_late_init, daemon=True).start()

def _late_init():
    g = _G["g"]
    for _ in range(300):
        try:
            conn = sqlite3.connect(g["DB_PATH"], timeout=10)
            t = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            conn.close()
            if "users" in t and "inventory" in t:
                break
        except Exception:
            pass
        time.sleep(0.2)
    _db_init(g)
    _wrap_death(g)
    _register_http(g)
    log.info("[ext3] BANK PACK v%s โหลดสำเร็จ — ดอกเบี้ย %.1f%%/ชม. • เพดานฐาน %s G • สะสมสูงสุด %g ชม.",
             V3, BANK_RATE * 100, f"{BANK_CAP_BASE:,}", BANK_MAX_HOURS)

# ================= JS (ฉีดอัตโนมัติ) =================
_EXT3_JS = r"""/* lumivara_ext3.js — 🏦 Bank UI */
(function(){
  var css = [
    /* ===== Overlay เต็มจอ บังคับตรงกลาง ===== */
    '#bk-panel{',
      'position:fixed !important;',
      'inset:0 !important;',
      'left:0 !important; top:0 !important; right:0 !important; bottom:0 !important;',
      'width:100vw !important; height:100vh !important; height:100dvh !important;',
      'z-index:99999 !important;',
      'display:none;',
      'align-items:center !important;',
      'justify-content:center !important;',
      'background:rgba(0,0,0,0.6) !important;',
      'backdrop-filter:blur(8px) !important;',
      '-webkit-backdrop-filter:blur(8px) !important;',
      'padding:16px !important;',
      'margin:0 !important;',
      'transform:none !important;',
      'box-sizing:border-box !important;',
    '}',

    /* กล่องเนื้อหา */
    '.bk-box{',
      'width:min(400px,94vw) !important;',
      'max-height:82vh !important;',
      'display:flex !important;',
      'flex-direction:column !important;',
      'background:linear-gradient(165deg,#10141f,#1c2440) !important;',
      'border:2px solid #c9a227 !important;',
      'border-radius:14px !important;',
      'color:#eef2ff !important;',
      'font-family:inherit !important;',
      'box-shadow:0 20px 60px rgba(0,0,0,0.7) !important;',
      'overflow:hidden !important;',
      'position:relative !important;',
      'margin:0 !important;',
      'transform:none !important;',
    '}',

    '.bk-head{display:flex;align-items:center;gap:8px;padding:12px 16px;border-bottom:1px solid #3a4468;font-weight:700;font-size:15px}',
    '#bk-gold{margin-left:auto;color:#ffd166;font-size:13px}',
    '.bk-x{background:#a33;border:0;color:#fff;border-radius:8px;padding:5px 10px;cursor:pointer;font-size:14px}',
    '#bk-body{overflow-y:auto;padding:14px;font-size:13px}',
    '#bk-bal{font-size:26px;font-weight:800;color:#ffd166;text-align:center;margin:4px 0}',
    '.bk-sub{text-align:center;color:#9fb0d8;font-size:12px;margin-top:2px}',
    '.bk-warn{background:#5a2323;border:1px solid #a33;border-radius:8px;padding:8px 12px;color:#ffb3b3;font-size:12px;margin:10px 0;text-align:center}',
    '.bk-row{display:flex;gap:6px;margin-top:10px}',
    '#bk-amt{flex:1;background:#0c1018;border:1px solid #3a4468;color:#fff;border-radius:8px;padding:9px;font-size:14px;min-width:0}',
    '.bk-btn{padding:9px 14px;border:0;border-radius:8px;background:#2f7d5c;color:#fff;cursor:pointer;font-weight:700;font-size:13px;white-space:nowrap}',
    '.bk-btn.blue{background:#3a6ea8}',
    '.bk-btn.gold{background:#c9a227;color:#201a05}',
    '.bk-btn:disabled,#bk-amt:disabled{opacity:.45;cursor:not-allowed}',
    '.bk-note{color:#8ea0c8;font-size:11px;margin-top:12px;line-height:1.6}',
    '.bk-h{border-top:1px solid #3a4468;margin-top:12px;padding-top:8px;font-weight:700;color:#c9d4f2}',
    '.bk-log{display:flex;gap:8px;padding:5px 2px;border-bottom:1px dashed #2a3352;font-size:12px}',
    '.bk-log .t{color:#7f8db3;margin-left:auto;font-size:10px}'
  ].join('');

  var st = document.createElement('style');
  st.id = 'bk-style';
  st.textContent = css;
  document.head.appendChild(st);

  var panel = null, last = null, lastFetch = 0;
  function byId(i){ return document.getElementById(i); }
  function fmt(n){ return (n||0).toLocaleString('en-US'); }

  function build(){
    // ลบของเก่าถ้ามี
    var old = document.getElementById('bk-panel');
    if(old) old.remove();

    panel = document.createElement('div');
    panel.id = 'bk-panel';
    panel.innerHTML =
      '<div class="bk-box">' +
        '<div class="bk-head">🏦 ธนาคาร Gemivara <span id="bk-gold"></span>' +
          '<button class="bk-x" onclick="__bkClose()">✕</button>' +
        '</div>' +
        '<div id="bk-body"></div>' +
      '</div>';
    document.body.appendChild(panel);
  }

  function open(){
    if(!panel) build();
    // บังคับสไตล์ตรงกลาง
    panel.style.cssText = 'position:fixed;inset:0;left:0;top:0;right:0;bottom:0;width:100vw;height:100vh;z-index:99999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,0.6);padding:16px;margin:0;transform:none;';
    refresh();
  }

  function close(){
    if(panel) panel.style.display = 'none';
  }

  window.__bkClose = close;
  window.__extOpenBank = open;
  document.addEventListener('keydown', function(e){ if(e.key === 'Escape') close(); });


  function post(url,p){return fetch(url,{method:'POST',credentials:'same-origin',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(p||{})})
    .then(function(r){return r.json();});}
  function get(url){return fetch(url,{credentials:'same-origin'}).then(function(r){return r.json();});}

  window.__bkDeposit=function(all){
    var amt=all?0:(parseInt(byId('bk-amt').value,10)||0);
    post('/api/bank/deposit',all?{all:true}:{amount:amt}).then(function(d){
      if(window.SND){d.success?(SND.buy&&SND.buy()):(SND.miss&&SND.miss());}
      if(window.showNotice)showNotice(d.message||'');refresh();});};
  window.__bkWithdraw=function(all){
    var amt=all?0:(parseInt(byId('bk-amt').value,10)||0);
    post('/api/bank/withdraw',all?{all:true}:{amount:amt}).then(function(d){
      if(window.SND){d.success?(SND.sell&&SND.sell()):(SND.miss&&SND.miss());}
      if(window.showNotice)showNotice(d.message||'');refresh();});};

  /* ดอกเบี้ยรอรับ ประมาณสดทุกวินาที (สูตรเดียวกับ server) */
  function estPending(){
    if(!last||!(last.balance>0))return 0;
    var h=(Date.now()/1000-(last.last_interest_at||Date.now()/1000))/3600;
    h=Math.max(0,Math.min(h,last.max_hours||24));
    return Math.floor(Math.min(last.balance,last.cap)*last.rate*h);}

  function render(d){
    last=d;lastFetch=Date.now();
    byId('bk-gold').textContent='💰 '+fmt(d.gold)+' G';
    var dis=d.in_town?'':' disabled';
    var h='<div id="bk-bal">💰 '+fmt(d.balance)+' G</div>'+
      '<div class="bk-sub">ดอกเบี้ย '+d.rate_pct+'% ต่อชั่วโมง • รอรับ <b id="bk-pend" style="color:#7bed9f">'+fmt(estPending())+' G</b></div>'+
      (d.in_town?'':'<div class="bk-warn">🚫 ต้องอยู่ในเมืองหลวงเท่านั้นจึงจะฝาก/ถอนได้</div>')+
      '<div class="bk-row"><input type="number" id="bk-amt" min="1" placeholder="จำนวน G"'+(d.in_town?'':' disabled')+'>'+
      '<button class="bk-btn"'+dis+' onclick="__bkDeposit(false)">ฝาก</button>'+
      '<button class="bk-btn blue"'+dis+' onclick="__bkWithdraw(false)">ถอน</button></div>'+
      '<div class="bk-row"><button class="bk-btn gold" style="flex:1"'+dis+' onclick="__bkDeposit(true)">⬆️ ฝากทั้งหมด</button>'+
      '<button class="bk-btn gold" style="flex:1"'+dis+' onclick="__bkWithdraw(true)">⬇️ ถอนทั้งหมด</button></div>'+
      '<div class="bk-note">🛡️ <b>เงินฝากไม่ถูกหักตอนตาย</b> (ตายเสียเฉพาะเงินในตัว)<br>'+
      '💹 ดอกเบี้ยเข้าอัตโนมัติทุกครบชั่วโมง — ออฟไลน์สะสมได้สูงสุด 24 ชม.<br>'+
      '📊 ฐานคิดดอกเบี้ยสูงสุด '+fmt(d.cap)+' G • ดอกเบี้ยสะสมตลอดไป <b style="color:#ffd166">'+fmt(d.total_interest)+' G</b></div>'+
      '<div class="bk-h">📜 ประวัติล่าสุด</div>';
    (d.log||[]).forEach(function(l){
      var ic=l.action==='deposit'?'⬆️':(l.action==='withdraw'?'⬇️':'💹');
      var nm=l.action==='deposit'?'ฝาก':(l.action==='withdraw'?'ถอน':'ดอกเบี้ย');
      h+='<div class="bk-log"><span>'+ic+' '+nm+' <b style="color:'+(l.action==='withdraw'?'#ff9f8a':'#7bed9f')+'">'+fmt(l.amount)+'</b> G</span>'+
         '<span class="t">→ '+fmt(l.balance_after)+' G</span></div>';});
    if(!(d.log||[]).length)h+='<div class="bk-log" style="color:#7f8db3">ยังไม่มีรายการ</div>';
    byId('bk-body').innerHTML=h;}

  function refresh(){
    get('/api/bank/mine').then(function(d){if(d&&d.success)render(d);}).catch(function(){});}

  setInterval(function(){
    if(panel&&panel.style.display!=='none'){
      var p=byId('bk-pend');if(p&&last)p.textContent=fmt(estPending())+' G';
      if(Date.now()-lastFetch>10000)refresh();}},1000);

  /* ปุ่ม HUD 🏦 */
  (function(){var w=document.getElementById('hud-menu');if(!w)return;
    if([].some.call(w.children,function(b){return b.title==='ธนาคาร';}))return;
    var b=document.createElement('button');b.className='menu-btn';b.title='ธนาคาร';
    b.textContent='🏦';b.onclick=open;w.appendChild(b);})();

  /* รองรับป้าย 🏦 ใน TownScene: openShop('bank') หรือ TownHooks.shop('bank') */
  function hookShop(){
    if(typeof window.openShop==='function'&&!window.openShop._bk){
      var o=window.openShop;
      window.openShop=function(k){if(k==='bank'){open();return;}return o.apply(this,arguments);};
      window.openShop._bk=true;}
    if(window.TownHooks&&typeof window.TownHooks.shop==='function'&&!window.TownHooks.shop._bk){
      var t=window.TownHooks.shop;
      window.TownHooks.shop=function(k){if(k==='bank'){open();return;}return t.apply(this,arguments);};
      window.TownHooks.shop._bk=true;}}
  setInterval(hookShop,800);
})();"""