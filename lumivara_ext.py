# -*- coding: utf-8 -*-
"""
lumivara_ext.py — EXTENSION PACK v1.0 สำหรับ Lumivara Online (GOD TIER v5.0)
วางไว้โฟลเดอร์เดียวกับ app.py → รัน python app.py ตามปกติ (app.py import ให้เอง)

เพิ่มให้:
  ⚒️  ช่างตีเหล็กโบราณ (NPC เมือง): ตีเสริมอาวุธ/เกราะ +1..+10 (คลิก NPC เพื่อเปิด UI)
  🗡️  อุปกรณ์ 9 ชิ้น + หินเสริมแรง/หินประกาย + ดรอปจากบอส/โกเลม
  🛒  ร้านอาวุธใน UI ช่างตีเหล็ก (ฉีดหน้าเว็บอัตโนมัติ — ไม่ต้องแก้ index.html)
  ⭐  สกิล "ผิวเหล็ก" (Def buff ทุกอาชีพ)
  🔨  Admin API: /api/admin/broadcast • /api/admin/ban (toggle แบน + เตะออกทันที)
  🩹  /api/ext/resync — ซิงก์ ATK/DEF (ฐานอาชีพ + โบนัสอุปกรณ์) หลังเปลี่ยนอาชีพ
"""
import time
import random
import sqlite3
import logging

from flask import request, jsonify, Response, session

log = logging.getLogger("lumivara.ext")

_G = {"g": None}

EXT_VERSION = "1.0"
EXT_STONE = 600       # หินเสริมแรง
EXT_PROTECT = 601     # หินประกายศักดิ์สิทธิ์
ENH_MAX = 10
ENH_BONUS = 2         # ATK/DEF ต่อระดับตีเสริม
ENH_FEE_BASE = 120
ENH_FEE_GROW = 1.8

EXT_EQUIP = {
    700: {"name": "ดาบนักผจญภัย",      "slot": "weapon", "atk": 6,  "price": 400,  "sell_price": 160,  "level_req": 1},
    701: {"name": "ดาบอัศวิน",          "slot": "weapon", "atk": 14, "price": 2200, "sell_price": 880,  "level_req": 15},
    702: {"name": "ธนูพญาเหยี่ยว",      "slot": "weapon", "atk": 13, "price": 2000, "sell_price": 800,  "level_req": 15},
    703: {"name": "ไม้เทวดา",           "slot": "weapon", "atk": 15, "price": 2400, "sell_price": 960,  "level_req": 15},
    704: {"name": "มีดเงา",             "slot": "weapon", "atk": 14, "price": 2100, "sell_price": 840,  "level_req": 15},
    705: {"name": "คทาแสงศักดิ์สิทธิ์", "slot": "weapon", "atk": 11, "price": 1800, "sell_price": 720,  "level_req": 15},
    710: {"name": "เกราะหนัง",          "slot": "armor",  "def": 5,  "price": 350,  "sell_price": 140,  "level_req": 1},
    711: {"name": "เกราะเหล็กอัศวิน",   "slot": "armor",  "def": 14, "price": 2600, "sell_price": 1040, "level_req": 20},
    712: {"name": "เกราะเวทมิติ",       "slot": "armor",  "def": 11, "price": 2000, "sell_price": 800,  "level_req": 18},
}

EXT_SHOP_EXTRA = {
    EXT_STONE:   {"name": "หินเสริมแรง",          "price": 450,  "level_req": 1},
    EXT_PROTECT: {"name": "หินประกายศักดิ์สิทธิ์", "price": 1500, "level_req": 1},
}


def enhance_fee(enh):
    return int(ENH_FEE_BASE * (ENH_FEE_GROW ** enh))


def enhance_chance(enh):
    return max(0.35, 0.95 - enh * 0.065)

def _equip_bonus(conn, uid):
    """รวมโบนัสจากอุปกรณ์ที่สวม: อาวุธ → ATK, เกราะ → DEF"""
    GD = _G["g"]["GD"]
    atk = df = 0
    rows = conn.execute("SELECT item_id, enhance FROM inventory WHERE user_id=? AND equipped=1",
                        (uid,)).fetchall()
    for r in rows:
        meta = GD.ITEMS.get(r["item_id"])
        if not meta or meta.get("type") != "equipment":
            continue
        bonus = (r["enhance"] or 0) * ENH_BONUS
        if meta.get("slot") == "weapon":
            atk += meta.get("atk", 0) + bonus
        else:
            df += meta.get("def", 0) + bonus
    return atk, df


def recalc_stats(conn, uid):
    """คำนวณ ATK/DEF ใหม่ทั้งหมด แล้วบันทึกลง DB — เรียกใน transaction เดียวกับที่แก้ข้อมูล"""
    g = _G["g"]
    GD = g["GD"]
    row = g["get_user_by_id"](conn, uid)
    if row is None:
        return None
    job = GD.JOBS.get(row["job"], GD.JOBS["Novice"])
    lv = row["level"]
    ea, ed = _equip_bonus(conn, uid)
    atk = job["atk"] + job["g"]["atk"] * (lv - 1) + ea
    df = job["def"] + job["g"]["def"] * (lv - 1) + ed
    conn.execute("UPDATE users SET atk=?, def=? WHERE id=?", (atk, df, uid))
    return g["get_user_by_id"](conn, uid)


def push_stats(uid, row):
    """เรียกหลัง commit: อัปเดตตัวละครในหน่วยความจำ (ใช้คำนวณดาเมจ) + แจ้งหน้าเว็บ"""
    g = _G["g"]
    g["sync_memory_stats"](g["user_to_dict"](row), vitals=False)
    sid = g["find_sid_by_uid"](uid)
    if sid:
        g["socketio"].emit("ext_stats", {"atk": row["atk"], "def": row["def"]}, room=sid)

# ============ จุดเข้าหลัก: app.py เรียกตอนโหลดโมดูล ============
def extend_world(g):
    _G["g"] = g

    # ---- (1) ไอเทมใหม่ (GD.ITEMS เกิดแล้ว แก้ได้ทันที) ----
    IT = g["GD"].ITEMS
    IT[EXT_STONE] = {"name": "หินเสริมแรง", "type": "material", "price": 450, "sell_price": 220}
    IT[EXT_PROTECT] = {"name": "หินประกายศักดิ์สิทธิ์", "type": "material", "price": 1500, "sell_price": 750}
    for iid, meta in EXT_EQUIP.items():
        d = {"name": meta["name"], "type": "equipment", "slot": meta["slot"],
             "price": meta["price"], "sell_price": meta["sell_price"],
             "level_req": meta["level_req"]}
        if "atk" in meta:
            d["atk"] = meta["atk"]
        if "def" in meta:
            d["def"] = meta["def"]
        IT[iid] = d

    # ---- (2) ตารางดรอป (วัสดุบอสยังมาช่องแรก 100% เหมือนเดิม) ----
    DT = g["DROP_TABLES"]
    DT[19] = [(119, 1.0), (700, 0.28), (710, 0.28), (EXT_PROTECT, 0.12), (500, 0.6), (3, 0.5), (1, 0.4)]
    DT[68] = [(168, 1.0), (701, 0.25), (711, 0.25), (EXT_PROTECT, 0.30), (EXT_STONE, 0.30), (500, 0.6), (3, 0.5), (1, 0.4)]
    for mid in (9, 24, 25, 36, 48):        # โกเลมหิน/ช่างเหมือง/ด้วงอัญมณี/ลาวา/ทราย
        DT[mid] = [(EXT_STONE, 0.06)] + DT.get(mid, [])
    for mid in (28, 42, 55):               # ผู้พิทักษ์ / อัศวินหิน / อัศวินเวหา
        DT[mid] = [(EXT_STONE, 0.05), (EXT_PROTECT, 0.025)] + DT.get(mid, [])



def _late_init():
    g = _G["g"]
    need = ["app", "socketio", "NPCS", "get_db", "authorize", "get_user_by_id",
            "find_sid_by_uid", "find_player_by_uid", "sync_memory_stats",
            "live_user", "user_to_dict", "DB_PATH"]
    for _ in range(300):
        if all(k in g for k in need):
            break
        time.sleep(0.1)
    missing = [k for k in need if k not in g]
    if missing:
        log.error("[ext] ยกเลิกโหลด — app.py ขาดสัญลักษณ์: %s", missing)
        return

    # รอ init_db ของ app.py สร้างตารางก่อน แล้วค่อยเติมคอลัมน์ enhance
    for _ in range(150):
        try:
            conn = sqlite3.connect(g["DB_PATH"], timeout=10)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            conn.close()
            if "users" in tables and "inventory" in tables:
                break
        except Exception:
            pass
        time.sleep(0.2)

    _ext_db_init(g)
    _patch_npcs(g)
    _patch_skills(g)
    _register_http(g)
    _register_socket(g)
    log.info("[ext] EXT v%s โหลดสำเร็จ — ช่างตีเหล็ก + ร้านอาวุธ + Admin API พร้อมใช้งาน", EXT_VERSION)


def _ext_db_init(g):
    conn = sqlite3.connect(g["DB_PATH"], timeout=10)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(inventory)")}
        if cols and "enhance" not in cols:
            conn.execute("ALTER TABLE inventory ADD COLUMN enhance INTEGER DEFAULT 0")
        conn.commit()
    finally:
        conn.close()


def _patch_npcs(g):
    lst = g["NPCS"].setdefault("town", [])
    if not any(n.get("id") == "npc_smith" for n in lst):
        lst.append({"id": "npc_smith", "name": "ช่างตีเหล็กโบราณ", "sprite": "⚒️",
                    "x": 300.0, "y": 210.0, "type": "smith"})
    log.info("[ext] เพิ่ม NPC ช่างตีเหล็กโบราณ ที่เมืองหลวง")


def _patch_skills(g):
    """ใส่สกิล 'ผิวเหล็ก' แทรกหลัง heal — ขึ้น Quick Slot ให้ทุกอาชีพ"""
    sk = g["GD"].SKILLS
    if "ext_iron_skin" in sk:
        return
    new_sk = {"name": "ผิวเหล็ก", "job": "All", "type": "buff", "mp": 12, "cd": 20,
              "mult": 1.45, "stat": "def", "duration": 20}
    ordered = {}
    for k, v in sk.items():
        ordered[k] = v
        if k == "heal":
            ordered["ext_iron_skin"] = new_sk
    if "ext_iron_skin" not in ordered:
        ordered["ext_iron_skin"] = new_sk
    sk.clear()
    sk.update(ordered)


# ================= HTTP =================
def _register_http(g):
    app, socketio = g["app"], g["socketio"]
    get_db, authorize, get_user_by_id = g["get_db"], g["authorize"], g["get_user_by_id"]
    live_user, find_player_by_uid = g["live_user"], g["find_player_by_uid"]
    GD = g["GD"]

    # ---------- เสิร์ฟ JS ฝั่งหน้าบ้าน ----------
    @app.route("/ext/lumivara_ext.js")
    def ext_js():
        return Response(_EXT_JS, mimetype="application/javascript")

    # ---------- ฉีด <script> เข้า index.html อัตโนมัติ ----------
    @app.after_request
    def ext_inject_js(resp):
        try:
            if request.path == "/" and (resp.headers.get("Content-Type", "") or "").startswith("text/html"):
                body = resp.get_data(as_text=True)
                tag = '<script src="/ext/lumivara_ext.js?v=' + EXT_VERSION + '"></script>'
                if "</body>" in body and "lumivara_ext.js" not in body:
                    resp.set_data(body.replace("</body>", tag + "</body>"))
        except Exception:
            pass
        return resp

    @app.route("/api/ext/status")
    def ext_status():
        return jsonify({"success": True, "ext": EXT_VERSION,
                        "features": ["smith", "equipment", "admin_api", "auto_ui_inject", "resync"]})

    # ---------- กระเป๋าแบบละเอียด (มีเลเวลตีเสริม) ----------
    @app.route("/api/ext/inventory")
    def ext_inventory():
        uid, err = authorize()
        if err:
            return err
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM inventory WHERE user_id=? ORDER BY equipped DESC, item_id",
                                (uid,)).fetchall()
            user = get_user_by_id(conn, uid)
        items = []
        for r in rows:
            meta = GD.ITEMS.get(r["item_id"], {})
            enh = r["enhance"] if "enhance" in r.keys() else 0
            items.append({"id": r["id"], "itemId": r["item_id"], "name": meta.get("name", "?"),
                          "type": meta.get("type"), "slot": meta.get("slot"),
                          "atk": meta.get("atk", 0), "def": meta.get("def", 0),
                          "quantity": r["quantity"], "equipped": bool(r["equipped"]),
                          "enhance": enh, "price": meta.get("price", 0),
                          "sell_price": meta.get("sell_price", 0), "level_req": meta.get("level_req", 1)})
        stones = sum(i["quantity"] for i in items if i["itemId"] == EXT_STONE)
        protects = sum(i["quantity"] for i in items if i["itemId"] == EXT_PROTECT)
        return jsonify({"success": True, "items": items, "gold": user["gold"],
                        "stones": stones, "protects": protects})

    # ---------- ร้านของช่างตีเหล็ก (ต้องยืนใกล้ NPC) ----------
    @app.route("/api/ext/smith/buy", methods=["POST"])
    def ext_smith_buy():
        uid, err = authorize()
        if err:
            return err
        data = request.json or {}
        try:
            iid = int(data.get("item_id", 0))
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "ข้อมูลไม่ถูกต้อง"}), 400
        meta = EXT_EQUIP.get(iid) or EXT_SHOP_EXTRA.get(iid)
        if not meta:
            return jsonify({"success": False, "message": "ไม่พบสินค้า"}), 404
        found = find_player_by_uid(uid)
        if not found:
            return jsonify({"success": False, "message": "ยังไม่ได้เข้าเกม"}), 400
        p = found[1]
        if p["map"] != "town":
            return jsonify({"success": False, "message": "ต้องไปหาช่างตีเหล็กที่เมือง"}), 400
        npc = next((n for n in g["NPCS"].get("town", []) if n.get("id") == "npc_smith"), None)
        if npc and ((p["x"] - npc["x"]) ** 2 + (p["y"] - npc["y"]) ** 2) > 110 ** 2:
            return jsonify({"success": False, "message": 'ต้องอยู่ใกล้ "ช่างตีเหล็กโบราณ" (คลิก NPC เพื่อเดินไปหา)'}), 400
        with get_db() as conn:
            user = get_user_by_id(conn, uid)
            if user["level"] < meta.get("level_req", 1):
                return jsonify({"success": False, "message": f"ต้องเลเวล {meta.get('level_req', 1)} ขึ้นไป"}), 400
            if user["gold"] < meta["price"]:
                return jsonify({"success": False, "message": "Gold ไม่พอ"}), 400
            conn.execute("UPDATE users SET gold=gold-? WHERE id=?", (meta["price"], uid))
            if iid in EXT_SHOP_EXTRA:   # หิน → รวมกอง
                ex = conn.execute("SELECT id FROM inventory WHERE user_id=? AND item_id=? AND equipped=0 LIMIT 1",
                                  (uid, iid)).fetchone()
                if ex:
                    conn.execute("UPDATE inventory SET quantity=quantity+1 WHERE id=?", (ex["id"],))
                else:
                    conn.execute("INSERT INTO inventory (user_id,item_id,quantity,equipped,enhance) VALUES (?,?,1,0,0)",
                                 (uid, iid))
            else:                        # อุปกรณ์ → แถวใหม่เสมอ
                conn.execute("INSERT INTO inventory (user_id,item_id,quantity,equipped,enhance) VALUES (?,?,1,0,0)",
                             (uid, iid))
            user = get_user_by_id(conn, uid)
        return jsonify({"success": True, "message": "ซื้อ " + meta["name"] + " สำเร็จ!", "user": live_user(user)})

    # ---------- ซิงก์ ATK/DEF = ฐานอาชีพ + โบนัสอุปกรณ์ที่สวม ----------
    @app.route("/api/ext/resync", methods=["POST"])
    def ext_resync():
        uid, err = authorize()
        if err:
            return err
        with get_db() as conn:
            row = get_user_by_id(conn, uid)
            if row is None:
                return jsonify({"success": False, "message": "ไม่พบผู้เล่น"}), 401
            job = GD.JOBS.get(row["job"], GD.JOBS["Novice"])
            gr, lv = job["g"], row["level"]
            atk = job["atk"] + gr["atk"] * (lv - 1)
            df = job["def"] + gr["def"] * (lv - 1)
            equipped = []
            for r in conn.execute("SELECT item_id, enhance FROM inventory WHERE user_id=? AND equipped=1",
                                  (uid,)).fetchall():
                meta = GD.ITEMS.get(r["item_id"])
                if meta and meta.get("type") == "equipment":
                    enh = (r["enhance"] or 0) if "enhance" in r.keys() else 0
                    atk += meta.get("atk", 0) + enh * ENH_BONUS
                    df += meta.get("def", 0) + enh * ENH_BONUS
                    equipped.append(meta["name"] + "+" + str(enh))
            conn.execute("UPDATE users SET atk=?, def=? WHERE id=?", (atk, df, uid))
            row = get_user_by_id(conn, uid)
        g["sync_memory_stats"](g["user_to_dict"](row), vitals=True)
        return jsonify({"success": True, "atk": row["atk"], "def": row["def"], "equipped": equipped})

    # ---------- ADMIN ----------
    def _admin_row():
        uid, err = authorize()
        if err:
            return None, err
        with get_db() as conn:
            row = get_user_by_id(conn, uid)
        if row is None or not row["is_admin"]:
            return None, (jsonify({"success": False, "message": "ต้องเป็นแอดมินเท่านั้น"}), 403)
        return row, None

    @app.route("/api/admin/broadcast", methods=["POST"])
    def ext_admin_broadcast():
        row, err = _admin_row()
        if err:
            return err
        msg = ((request.json or {}).get("message") or "").strip()[:300]
        if not msg:
            return jsonify({"success": False, "message": "พิมพ์ข้อความก่อน"}), 400
        with get_db() as conn:
            conn.execute("INSERT INTO chat_log (username, channel, message) VALUES (?,?,?)",
                         (row["username"], "sys", "[Admin] " + msg))
        socketio.emit("system_message", {"message": "📢 [Admin] " + msg})
        return jsonify({"success": True, "message": "ประกาศแล้ว"})

    @app.route("/api/admin/ban", methods=["POST"])
    def ext_admin_ban():
        admin, err = _admin_row()
        if err:
            return err
        username = ((request.json or {}).get("username") or "").strip()
        if not username:
            return jsonify({"success": False, "message": "ระบุชื่อผู้เล่น"}), 400
        if username == admin["username"]:
            return jsonify({"success": False, "message": "แบนตัวเองไม่ได้ 😅"}), 400
        with get_db() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
            if row is None:
                return jsonify({"success": False, "message": "ไม่พบผู้เล่นนี้"}), 404
            if row["is_admin"]:
                return jsonify({"success": False, "message": "แบนแอดมินไม่ได้"}), 400
            if row["is_banned"]:
                conn.execute("UPDATE users SET is_banned=0 WHERE id=?", (row["id"],))
                action = "ปลดแบน"
            else:
                conn.execute("UPDATE users SET is_banned=1 WHERE id=?", (row["id"],))
                action = "แบน"
        if action == "แบน":
            sid = g["find_sid_by_uid"](row["id"])
            if sid:
                socketio.emit("force_disconnect", {}, room=sid)
        socketio.emit("system_message", {"message": f"🔨 {action}ผู้เล่น {username} แล้ว"})
        return jsonify({"success": True, "message": f"{action} {username} สำเร็จ"})


# ================= SOCKET =================
def _register_socket(g):
    socketio, get_db, GD = g["socketio"], g["get_db"], g["GD"]
    get_user_by_id, find_sid_by_uid = g["get_user_by_id"], g["find_sid_by_uid"]
    rate_ok = g.get("rate_ok")

    def _notice(uid, msg):
        sid = find_sid_by_uid(uid)
        if sid:
            socketio.emit("ext_notice", {"message": msg}, room=sid)

    def _gold_update(uid):
        with get_db() as conn:
            row = get_user_by_id(conn, uid)
        sid = find_sid_by_uid(uid)
        if sid and row:
            socketio.emit("gold_update", {"gold": row["gold"]}, room=sid)

    def _stats_update(uid):
        with get_db() as conn:
            row = get_user_by_id(conn, uid)
        sid = find_sid_by_uid(uid)
        if sid and row:
            socketio.emit("ext_stats", {"atk": row["atk"], "def": row["def"]}, room=sid)

    def _consume(conn, uid, rows, qty):
        for r in rows:
            if qty <= 0:
                break
            take = min(qty, r["quantity"])
            if take >= r["quantity"]:
                conn.execute("DELETE FROM inventory WHERE id=?", (r["id"],))
            else:
                conn.execute("UPDATE inventory SET quantity=quantity-? WHERE id=?", (take, r["id"]))
            qty -= take

    # ---------- สวม/ถอดอุปกรณ์ ----------
    @socketio.on("ext_equip")
    def ext_equip(data):
        uid = session.get("user_id")
        if not uid:
            return
        try:
            inv_id = int((data or {}).get("inventory_id", 0))
        except (TypeError, ValueError):
            return
        with get_db() as conn:
            row = conn.execute("SELECT * FROM inventory WHERE id=? AND user_id=?", (inv_id, uid)).fetchone()
            if not row:
                return _notice(uid, "ไม่พบไอเทม")
            meta = GD.ITEMS.get(row["item_id"])
            if not meta or meta.get("type") != "equipment":
                return _notice(uid, "สวมได้เฉพาะอาวุธ/เกราะ")
            enh = (row["enhance"] or 0) if "enhance" in row.keys() else 0
            stat = "atk" if meta.get("slot") == "weapon" else "def"
            bonus = int(meta.get(stat, 0)) + enh * ENH_BONUS
            if row["equipped"]:
                conn.execute(f"UPDATE users SET {stat}=MAX(1, {stat}-?) WHERE id=?", (bonus, uid))
                conn.execute("UPDATE inventory SET equipped=0 WHERE id=?", (inv_id,))
                _notice(uid, f"ถอด {meta['name']}+{enh} แล้ว")
            else:
                urow = get_user_by_id(conn, uid)
                if urow["level"] < meta.get("level_req", 1):
                    return _notice(uid, f"ต้องเลเวล {meta.get('level_req', 1)} ขึ้นไป")
                for o in conn.execute("SELECT id, item_id, enhance FROM inventory WHERE user_id=? AND equipped=1 AND id!=?",
                                      (uid, inv_id)).fetchall():
                    om = GD.ITEMS.get(o["item_id"])
                    if om and om.get("type") == "equipment" and om.get("slot") == meta.get("slot"):
                        ostat = "atk" if om.get("slot") == "weapon" else "def"
                        obonus = int(om.get(ostat, 0)) + ((o["enhance"] or 0) if "enhance" in o.keys() else 0) * ENH_BONUS
                        conn.execute(f"UPDATE users SET {ostat}=MAX(1, {ostat}-?) WHERE id=?", (obonus, uid))
                        conn.execute("UPDATE inventory SET equipped=0 WHERE id=?", (o["id"],))
                        _notice(uid, f"ถอด {om['name']} ออก (สวมได้ช่องละ 1 ชิ้น)")
                conn.execute(f"UPDATE users SET {stat}={stat}+? WHERE id=?", (bonus, uid))
                conn.execute("UPDATE inventory SET equipped=1 WHERE id=?", (inv_id,))
                _notice(uid, f"สวม {meta['name']}+{enh} → {stat.upper()}+{bonus}")
        _stats_update(uid)

    # ---------- ตีเสริม ----------
    @socketio.on("ext_equip")
    def ext_equip(data):
        uid = session.get("user_id")
        if not uid:
            return
        try:
            inv_id = int((data or {}).get("inventory_id", 0))
        except (TypeError, ValueError):
            return
        msg, urow = None, None
        with get_db() as conn:
            row = conn.execute("SELECT * FROM inventory WHERE id=? AND user_id=?", (inv_id, uid)).fetchone()
            meta = GD.ITEMS.get(row["item_id"]) if row else None
            if not row:
                msg = "ไม่พบไอเทม"
            elif not meta or meta.get("type") != "equipment":
                msg = "สวมได้เฉพาะอาวุธ/เกราะ"
            elif row["equipped"]:
                conn.execute("UPDATE inventory SET equipped=0 WHERE id=?", (inv_id,))
                msg = f"ถอด {meta['name']}+{row['enhance'] or 0} แล้ว"
            elif get_user_by_id(conn, uid)["level"] < meta.get("level_req", 1):
                msg = f"ต้องเลเวล {meta.get('level_req', 1)} ขึ้นไป"
            else:
                # ถอดชิ้นเดิมในช่องเดียวกัน (สวมได้ช่องละ 1 ชิ้น)
                for o in conn.execute("SELECT id, item_id FROM inventory WHERE user_id=? AND equipped=1",
                                      (uid,)).fetchall():
                    if GD.ITEMS.get(o["item_id"], {}).get("slot") == meta.get("slot"):
                        conn.execute("UPDATE inventory SET equipped=0 WHERE id=?", (o["id"],))
                conn.execute("UPDATE inventory SET equipped=1 WHERE id=?", (inv_id,))
                msg = f"สวม {meta['name']}+{row['enhance'] or 0} แล้ว"
            urow = recalc_stats(conn, uid)
        # ออกจาก with = commit แล้ว
        if urow:
            push_stats(uid, urow)
        if msg:
            _notice(uid, msg)

    def _enhance_tx(conn, uid, inv_id):
        """ทำในทรานแซกชันเดียว คืน (error, result) — ห้าม emit ข้างใน"""
        row = conn.execute("SELECT * FROM inventory WHERE id=? AND user_id=?", (inv_id, uid)).fetchone()
        if not row:
            return "ไม่พบไอเทม", None
        meta = GD.ITEMS.get(row["item_id"])
        if not meta or meta.get("type") != "equipment":
            return "ตีเสริมได้เฉพาะอาวุธ/เกราะ", None
        enh = row["enhance"] or 0
        if enh >= ENH_MAX:
            return f"{meta['name']} ตีเสริมสูงสุดแล้ว (+{ENH_MAX})", None
        fee = enhance_fee(enh)
        user = get_user_by_id(conn, uid)
        if user["gold"] < fee:
            return f"ค่าตีเสริม {fee} G — Gold ไม่พอ", None
        stones = conn.execute("SELECT id, quantity FROM inventory WHERE user_id=? AND item_id=? AND equipped=0",
                              (uid, EXT_STONE)).fetchall()
        if sum(r["quantity"] for r in stones) < 1:
            return "ต้องใช้ 🔹หินเสริมแรง 1 เม็ด (ล่าโกเลม/บอส หรือซื้อจากช่างตีเหล็ก)", None
        need_protect = enh >= 7
        protects = conn.execute("SELECT id, quantity FROM inventory WHERE user_id=? AND item_id=? AND equipped=0",
                                (uid, EXT_PROTECT)).fetchall()
        if need_protect and sum(r["quantity"] for r in protects) < 1:
            return "ตั้งแต่ +7 ขึ้นไปต้องมี 💠หินประกายศักดิ์สิทธิ์ 1 เม็ด", None

        conn.execute("UPDATE users SET gold=gold-? WHERE id=?", (fee, uid))
        _consume(conn, uid, stones, 1)
        if need_protect:
            _consume(conn, uid, protects, 1)

        name = meta["name"]
        if random.random() < enhance_chance(enh):
            newenh = enh + 1
            res = {"result": "success", "enhance": newenh, "name": name}
        elif need_protect:
            newenh = enh
            res = {"result": "fail", "enhance": enh, "name": name, "protect": True,
                   "message": f"ตีเสริมพลาด! แต่ 💠หินประกายช่วยไว้ — {name}+{enh} ไม่เสียหาย"}
        else:
            newenh = max(0, enh - 1)
            res = {"result": "fail", "enhance": newenh, "name": name,
                   "message": f"ตีเสริมพลาด! {name} ตกเป็น +{newenh}"}
        conn.execute("UPDATE inventory SET enhance=? WHERE id=?", (newenh, inv_id))
        res["username"] = user["username"]
        return None, res

    @socketio.on("smith_enhance")
    def smith_enhance(data):
        uid = session.get("user_id")
        if not uid:
            return
        if rate_ok and not rate_ok(request.sid, "smith", 1.0):
            return
        try:
            inv_id = int((data or {}).get("inventory_id", 0))
        except (TypeError, ValueError):
            return

        with get_db() as conn:
            conn.execute("BEGIN IMMEDIATE")      # ล็อกการเขียน กันกดรัวแล้วค่าทับกัน
            err, res = _enhance_tx(conn, uid, inv_id)
            urow = None if err else recalc_stats(conn, uid)
        # ออกจาก with = commit แล้ว → ค่อยแจ้งหน้าเว็บ (refresh จะเห็นค่าใหม่แน่นอน)

        if err:
            return _notice(uid, err)
        push_stats(uid, urow)
        uname = res.pop("username")
        sid = find_sid_by_uid(uid)
        if sid:
            socketio.emit("smith_result", res, room=sid)
        if res["result"] == "success" and res["enhance"] >= 9:
            socketio.emit("system_message", {"message": f"⚒️ {uname} ตี {res['name']} ถึง +{res['enhance']} สำเร็จ!!"})
        _gold_update(uid)

# ================= JS ฝั่งหน้าบ้าน (ฉีดอัตโนมัติ) =================
_EXT_JS = r"""/* lumivara_ext.js — UI ช่างตีเหล็ก/ร้านอาวุธ (ฉีดโดย lumivara_ext.py) */
(function(){
  var EQ=[
    {id:700,icon:'🗡️',name:'ดาบนักผจญภัย',slot:'weapon',stat:6,price:400,lv:1},
    {id:701,icon:'⚔️',name:'ดาบอัศวิน',slot:'weapon',stat:14,price:2200,lv:15},
    {id:702,icon:'🏹',name:'ธนูพญาเหยี่ยว',slot:'weapon',stat:13,price:2000,lv:15},
    {id:703,icon:'🔮',name:'ไม้เทวดา',slot:'weapon',stat:15,price:2400,lv:15},
    {id:704,icon:'🔪',name:'มีดเงา',slot:'weapon',stat:14,price:2100,lv:15},
    {id:705,icon:'✨',name:'คทาแสงศักดิ์สิทธิ์',slot:'weapon',stat:11,price:1800,lv:15},
    {id:710,icon:'🧥',name:'เกราะหนัง',slot:'armor',stat:5,price:350,lv:1},
    {id:711,icon:'🛡️',name:'เกราะเหล็กอัศวิน',slot:'armor',stat:14,price:2600,lv:20},
    {id:712,icon:'🌀',name:'เกราะเวทมิติ',slot:'armor',stat:11,price:2000,lv:18}
  ];
  var SHOP=([{id:600,icon:'🔹',name:'หินเสริมแรง',price:450,lv:1,desc:'วัตถุดิบตีเสริม 1 ครั้ง'},
             {id:601,icon:'💠',name:'หินประกายศักดิ์สิทธิ์',price:1500,lv:1,desc:'ใช้บังคับตั้งแต่ +7 ขึ้นไป (กันตกเกรด)'}]).concat(EQ);
  var fee=function(e){return Math.round(120*Math.pow(1.8,e));};
  var chance=function(e){return Math.max(35,Math.round((0.95-e*0.065)*100));};
  var css=['#exm-panel{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:9999;width:min(430px,94vw);',
    'max-height:82vh;display:none;flex-direction:column;background:linear-gradient(165deg,#141a2a,#1d2647);',
    'border:2px solid #3d4a7a;border-radius:14px;color:#e8ecff;font-family:inherit;box-shadow:0 14px 44px rgba(0,0,0,.65);overflow:hidden}',
    '#exm-head{display:flex;align-items:center;gap:8px;padding:10px 14px;border-bottom:1px solid #2c355e;font-weight:700;font-size:15px}',
    '.exm-x{margin-left:auto;background:#a33;border:0;color:#fff;border-radius:8px;padding:5px 10px;cursor:pointer}',
    '.exm-tab{flex:1;padding:9px 4px;border:0;background:#232c4e;color:#aab3d8;cursor:pointer;font-weight:700;font-size:13px}',
    '.exm-tab.active{background:#3d4a7a;color:#fff}',
    '#exm-body{overflow-y:auto;padding:10px}',
    '.exm-row{display:flex;align-items:center;gap:10px;padding:9px 6px;border-bottom:1px solid #262e55}',
    '.exm-ic{font-size:24px;width:30px;text-align:center}',
    '.exm-meta{font-size:11px;color:#8f9ac0;margin-top:2px}',
    '.exm-btn{padding:7px 10px;border:0;border-radius:8px;background:#5b6ee1;color:#fff;cursor:pointer;font-weight:700;font-size:12px;white-space:nowrap}',
    '.exm-btn.gold{background:#c99a2e}.exm-btn.gray{background:#4a5578}',
    '.exm-tag{font-size:10px;padding:2px 6px;border-radius:6px;background:#2e7d4f;color:#fff;vertical-align:middle}',
    '.exm-col{display:flex;flex-direction:column;gap:5px}'].join('');
  var st=document.createElement('style');st.textContent=css;document.head.appendChild(st);

  var inv=null,tab='enhance',panel=null;
  function byId(id){return document.getElementById(id);}
  function esc(s){var d=document.createElement('div');d.textContent=s==null?'':String(s);return d.innerHTML;}

  function buildPanel(){
    panel=document.createElement('div');panel.id='exm-panel';
    panel.innerHTML='<div id="exm-head">⚒️ ช่างตีเหล็กโบราณ <span id="exm-gold" style="margin-left:8px;color:#ffd166;font-size:13px"></span><button class="exm-x" id="exm-close">✕</button></div>'+
      '<div style="display:flex"><button class="exm-tab active" id="exm-tab-e">🔧 ตีเสริม</button>'+
      '<button class="exm-tab" id="exm-tab-s">🛒 ร้านอาวุธ</button></div><div id="exm-body"></div>';
    document.body.appendChild(panel);
    byId('exm-close').onclick=closePanel;
    byId('exm-tab-e').onclick=function(){tab='enhance';setTab();render();};
    byId('exm-tab-s').onclick=function(){tab='shop';setTab();render();};
  }
  function setTab(){byId('exm-tab-e').classList.toggle('active',tab==='enhance');byId('exm-tab-s').classList.toggle('active',tab==='shop');}
  function openPanel(){if(!panel)buildPanel();panel.style.display='flex';refresh();}
  function closePanel(){if(panel)panel.style.display='none';}
  window.__extOpenSmith=openPanel;

  function refresh(){
    fetch('/api/ext/inventory',{credentials:'same-origin'}).then(function(r){return r.json();}).then(function(d){
      if(!d||!d.success)return;inv=d.items;
      var g=byId('exm-gold');if(g)g.textContent='💰 '+d.gold+' G • 🔹 '+d.stones+' • 💠 '+d.protects;
      render();}).catch(function(){});
  }
  function actEquip(id){if(socket)socket.emit('ext_equip',{inventory_id:id});setTimeout(refresh,400);}
  function actEnh(id){if(socket)socket.emit('smith_enhance',{inventory_id:id});setTimeout(refresh,500);}
  function actBuy(id,name){
    apiPost('/api/ext/smith/buy',{item_id:id}).then(function(d){
      if(d.success){showNotice('🛒 ซื้อ '+name+' สำเร็จ!');if(window.SND&&SND.buy)SND.buy();}
      else showNotice('❌ '+(d.message||'ไม่สำเร็จ'));refresh();
    }).catch(function(e){showNotice('❌ '+e.message);});}
  window.__extEquip=actEquip;window.__extEnh=actEnh;window.__extBuy=actBuy;

  function render(){
    if(!panel)return;var b=byId('exm-body');
    if(tab==='shop'){
      var h='<div class="exm-meta" style="padding:4px 8px">ซื้อได้เมื่อยืนใกล้ช่างตีเหล็กในเมือง • อุปกรณ์ติดมาแบบ +0</div>';
      SHOP.forEach(function(it){
        var line=it.desc?esc(it.desc):((it.slot==='weapon'?'⚔️ ATK +':'🛡️ DEF +')+it.stat);
        h+='<div class="exm-row"><div class="exm-ic">'+it.icon+'</div><div style="flex:1"><div>'+esc(it.name)+'</div>'+
           '<div class="exm-meta">'+line+' • 💰 '+it.price+' G'+(it.lv>1?' • Lv.'+it.lv+'+':'')+'</div></div>'+
           '<button class="exm-btn" onclick="__extBuy('+it.id+',\''+esc(it.name)+'\')">ซื้อ</button></div>';});
      b.innerHTML=h;return;}
    var eq=(inv||[]).filter(function(i){return i.type==='equipment';});
    if(!eq.length){b.innerHTML='<div class="exm-meta" style="padding:10px">ยังไม่มีอาวุธ/เกราะ — ซื้อที่แท็บ "ร้านอาวุธ" หรือล่าบอสเอาดรอป</div>';return;}
    var h2='<div class="exm-meta" style="padding:4px 8px">ตีเสริม: 🔹1 + ค่าตีเสริม • +7 ขึ้นไปต้องมี 💠 • สำเร็จ +2 ATK/DEF • พลาดตกเกรด 1 (มี 💠 ไม่ตก)</div>';
    eq.forEach(function(it){
      var isW=it.slot==='weapon',now=(isW?it.atk:it.def)+it.enhance*2;
      var statLine=(isW?'⚔️ ATK ':'🛡️ DEF ')+now+(it.enhance<10?' → <b style="color:#7bed9f">'+(now+2)+'</b> (โอกาส '+chance(it.enhance)+'%)':' <b style="color:#ffd166">MAX</b>');
      var feeTxt=fee(it.enhance)+' G + 🔹1'+(it.enhance>=7?' + 💠1':'');
      h2+='<div class="exm-row"><div class="exm-ic">'+(isW?'🗡️':'🛡️')+'</div><div style="flex:1">'+
          '<div>'+esc(it.name)+' <b style="color:#ffd166">+'+it.enhance+'</b> '+(it.equipped?'<span class="exm-tag">สวมอยู่</span>':'')+'</div>'+
          '<div class="exm-meta">'+statLine+'</div><div class="exm-meta">ค่าตีเสริม: 💰 '+feeTxt+'</div></div>'+
          '<div class="exm-col"><button class="exm-btn gold" onclick="__extEnh('+it.id+')">ตีเสริม</button>'+
          '<button class="exm-btn gray" onclick="__extEquip('+it.id+')">'+(it.equipped?'ถอด':'สวมใส่')+'</button></div></div>';});
    b.innerHTML=h2;}

  function wait(cond,cb){var t0=Date.now();var t=setInterval(function(){
    var ok=false;try{ok=cond();}catch(e){}
    if(ok){clearInterval(t);cb();}else if(Date.now()-t0>20000)clearInterval(t);},200);}

  // คลิก NPC ช่างตีเหล็ก → เปิดแผง
  wait(function(){return typeof openNPC==='function';},function(){
    var orig=openNPC;
    window.openNPC=function(n){if(n&&n.type==='smith'){openPanel();return;}return orig(n);};});

  // ซิงก์ ATK/DEF อัตโนมัติหลังเปลี่ยนอาชีพ
  wait(function(){return typeof doJobChange==='function';},function(){
    var orig=doJobChange;
    window.doJobChange=function(t){
      var r=orig(t);
      Promise.resolve(r).then(function(){
        return fetch('/api/ext/resync',{method:'POST',credentials:'same-origin',
          headers:{'Content-Type':'application/json'},body:'{}'}).then(function(x){return x.json();});
      }).then(function(d){
        if(d&&d.success){try{myData.atk=d.atk;myData.def=d.def;updateUIValues();
          showNotice('⚒️ ซิงก์สถานะ: ATK '+d.atk+' / DEF '+d.def);}catch(e){}}
      }).catch(function(){});return r;};});

  // ต่อ listener ทุกครั้งที่ socket ถูกสร้างใหม่ (re-login)
  setInterval(function(){
    try{
      if(typeof socket!=='undefined'&&socket&&!socket._extHooked){
        socket._extHooked=true;
        socket.on('smith_result',function(d){
          if(d.result==='success'){showNotice('⚒️ ตีเสริมสำเร็จ! '+(d.name||'')+' +'+d.enhance);if(window.SND&&SND.crit)SND.crit();}
          else{showNotice('💥 '+(d.message||('ตีเสริมล้มเหลว → +'+d.enhance)));if(window.SND&&SND.kill)SND.kill();}
          refresh();});
        socket.on('ext_notice',function(d){showNotice('⚒️ '+d.message);refresh();});
        socket.on('ext_equip_result',function(d){showNotice('⚒️ '+d.message);});
        socket.on('ext_stats',function(d){try{myData.atk=d.atk;myData.def=d.def;updateUIValues();}catch(e){}});
      }}catch(e){}
  },1000);
  document.addEventListener('keydown',function(e){if(e.key==='Escape')closePanel();});
})();"""
# ==== COMPAT: รองรับ app.py ที่เรียก EXT.install(globals()) ====
# ==== COMPAT BLOCK (v2-ready) ====
# ==== COMPAT BLOCK v3 (chain ext2 + ext3) ====
_core_extend = extend_world
_done = {"v": False}

def extend_world(g):
    if not _done["v"]:
        _done["v"] = True
        _core_extend(g)

def install(g):
    extend_world(g)
    _late_init()          # ← เพิ่ม: ทุกอย่างพร้อมแล้ว ไม่ต้องรอในเธรด
    import logging
    _lg = logging.getLogger("lumivara.ext")
    for modname in ("lumivara_ext2", "lumivara_ext3"):
        try:
            __import__(modname).install(g)
        except Exception:
            _lg.exception("[%s] โหลดไม่สำเร็จ", modname)