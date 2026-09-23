# -*- coding: utf-8 -*-
"""
Lumivara Online — Flask + Flask-SocketIO ( GOD TIER v2.0 )

อัปเกรดใหญ่:
- Server-authoritative monsters: HP แชร์ระหว่างผู้เล่น + respawn + สแกนวอร์
- Skills system, crit/dodge, ดาเมจสุ่ม
- Security: session auth ทุก endpoint, anti-cheat (cooldown/ระยะ/ความเร็ว)
- Regen tick, autosave, multi-login kick, rate limiting
- Leaderboard, daily reward, sell items, PvP ใน dungeon
"""

import os
import math
import time
import random
import sqlite3
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash

import game_data as GD

# ---------------------------------------------------------------------------
# ตั้งค่า
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
ADMIN_USERNAME = os.environ.get("LUMIVARA_ADMIN", "")  # คนนี้จะเป็นแอดมินอัตโนมัติ

TICK_SECONDS     = 2.0     # รอบ regen / wander / respawn
AUTOSAVE_SECONDS = 30
ATTACK_COOLDOWN  = 0.7
CHAT_COOLDOWN    = 1.0
PVP_COOLDOWN     = 1.2
ATTACK_RANGE     = 120
MAX_MOVE_SPEED   = 450.0   # px/วินาที (ป้องกัน speed hack)
PVP_MAP          = "dungeon"

CRIT_CHANCE   = 0.10
CRIT_MULT     = 1.9
DMG_VARIANCE  = 0.15
MONSTER_DODGE = 0.05
MONSTER_MISS  = 0.08

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("LUMIVARA_SECRET", "lumivara_secret_2026")
socketio = SocketIO(app, cors_allowed_origins="*")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lumivara")

STATE_LOCK = threading.Lock()
connected_players = {}   # sid -> runtime state
MONSTER_INSTANCES = {}   # map -> {monster_id: instance}
_rate_limit = {}         # (sid, action) -> เวลาล่าสุด


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------
@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL, level INTEGER DEFAULT 1, job TEXT DEFAULT 'Novice',
                hp INTEGER DEFAULT 100, max_hp INTEGER DEFAULT 100,
                mp INTEGER DEFAULT 50, max_mp INTEGER DEFAULT 50,
                atk INTEGER DEFAULT 10, def INTEGER DEFAULT 8,
                gold INTEGER DEFAULT 100, exp INTEGER DEFAULT 0, max_exp INTEGER DEFAULT 100,
                x REAL DEFAULT 400, y REAL DEFAULT 300, map TEXT DEFAULT 'town',
                is_admin INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP, last_login TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                item_id INTEGER NOT NULL, quantity INTEGER DEFAULT 1, equipped INTEGER DEFAULT 0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS user_quests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                quest_id INTEGER NOT NULL, progress INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active')""")
        c.execute("""CREATE TABLE IF NOT EXISTS chat_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, channel TEXT,
                message TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")

        # ---- migrations (database.db เดิมใช้ต่อได้ทันที) ----
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        if "kills" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN kills INTEGER DEFAULT 0")
        if "last_daily" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN last_daily TEXT")

        c.execute("CREATE INDEX IF NOT EXISTS idx_inv_user ON inventory(user_id)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_quest ON user_quests(user_id, quest_id)")
    log.info("Database ready at %s", DB_PATH)


def user_to_dict(row):
    return {
        "id": row["id"], "username": row["username"], "level": row["level"],
        "job": row["job"], "hp": row["hp"], "maxHp": row["max_hp"],
        "mp": row["mp"], "maxMp": row["max_mp"], "atk": row["atk"], "def": row["def"],
        "gold": row["gold"], "exp": row["exp"], "maxExp": row["max_exp"],
        "x": row["x"], "y": row["y"], "map": row["map"], "isAdmin": bool(row["is_admin"]),
    }


def get_user_by_id(conn, user_id):
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def authorize(user_id_from_body=None):
    """REST auth: ต้องมี session และตรงกับ user_id ที่ส่งมา (กันยืม ID คนอื่น)"""
    uid = session.get("user_id")
    if uid is None:
        return None, (jsonify({"success": False, "message": "กรุณาเข้าสู่ระบบก่อน"}), 401)
    if user_id_from_body is not None and str(user_id_from_body) != str(uid):
        return None, (jsonify({"success": False, "message": "ไม่มีสิทธิ์เข้าถึงข้อมูลผู้เล่นนี้"}), 403)
    return uid, None


# ---------------------------------------------------------------------------
# ระบบมอนสเตอร์ (server-authoritative)
# ---------------------------------------------------------------------------
def spawn_grid(idx):
    return 120 + (idx * 150) % 620, 140 + (idx // 4) * 130


def make_instance(md, idx):
    x, y = spawn_grid(idx)
    return {
        "id": md["id"], "name": md["name"], "level": md["level"],
        "boss": bool(md.get("boss")), "hp": md["hp"], "max_hp": md["hp"],
        "atk": md["atk"], "def": md["def"], "exp": md["exp"], "gold": md["gold"],
        "respawn_sec": md.get("respawn", 20),
        "x": float(x), "y": float(y), "home_x": float(x), "home_y": float(y),
        "alive": True, "respawn_at": 0.0,
    }


def serialize_monster(m):
    return {"id": m["id"], "name": m["name"], "level": m["level"], "boss": m["boss"],
            "hp": m["hp"], "max_hp": m["max_hp"], "alive": m["alive"],
            "x": round(m["x"], 1), "y": round(m["y"], 1)}


def spawn_all_monsters():
    with STATE_LOCK:
        for map_name, defs in GD.MONSTERS.items():
            MONSTER_INSTANCES[map_name] = {i: make_instance(md, i)
                                           for i, md in enumerate(defs)}
    log.info("Spawned monsters: %s",
             {m: len(v) for m, v in MONSTER_INSTANCES.items()})


def respawn_monster(m):
    m["hp"] = m["max_hp"]
    m["alive"] = True
    m["x"] = clamp(m["home_x"] + random.uniform(-80, 80), 40, 760)
    m["y"] = clamp(m["home_y"] + random.uniform(-80, 80), 60, 540)


def step_wander(m):
    if random.random() < 0.6:
        return False
    m["x"] += random.uniform(-9, 9)
    m["y"] += random.uniform(-9, 9)
    if abs(m["x"] - m["home_x"]) > 70:
        m["x"] += (m["home_x"] - m["x"]) * 0.25
    if abs(m["y"] - m["home_y"]) > 70:
        m["y"] += (m["home_y"] - m["y"]) * 0.25
    m["x"] = clamp(m["x"], 20, 780)
    m["y"] = clamp(m["y"], 20, 580)
    return True


# ---------------------------------------------------------------------------
# Combat helpers
# ---------------------------------------------------------------------------
def rate_ok(sid, action, seconds):
    now = time.time()
    key = (sid, action)
    if now - _rate_limit.get(key, 0) < seconds:
        return False
    _rate_limit[key] = now
    return True


def roll_damage(atk, defense, mult=1.0):
    base = atk * mult - defense / 2.0
    base = max(1.0, base) * random.uniform(1 - DMG_VARIANCE, 1 + DMG_VARIANCE)
    crit = random.random() < CRIT_CHANCE
    if crit:
        base *= CRIT_MULT
    return max(1, int(round(base))), crit


def apply_level_up(conn, user_row):
    user = dict(user_row)
    leveled = False
    while user["exp"] >= user["max_exp"] and user["level"] < 999:
        user["exp"] -= user["max_exp"]
        user["level"] += 1
        user["max_exp"] = GD.exp_to_next_level(user["level"])
        g = GD.stat_growth_per_level(user["job"])
        user["max_hp"] += g["hp"]; user["max_mp"] += g["mp"]
        user["atk"] += g["atk"];   user["def"] += g["def"]
        user["hp"] = user["max_hp"]; user["mp"] = user["max_mp"]
        leveled = True
    conn.execute("""UPDATE users SET level=?, exp=?, max_exp=?, max_hp=?, max_mp=?,
                    atk=?, def=?, hp=?, mp=? WHERE id=?""",
                 (user["level"], user["exp"], user["max_exp"], user["max_hp"], user["max_mp"],
                  user["atk"], user["def"], user["hp"], user["mp"], user["id"]))
    return user, leveled


def update_quest_progress(conn, user_id, monster_id):
    for qid, q in GD.QUESTS.items():
        if q["target_monster"] != monster_id:
            continue
        row = conn.execute("SELECT * FROM user_quests WHERE user_id=? AND quest_id=?",
                           (user_id, qid)).fetchone()
        if row is None:
            conn.execute("INSERT INTO user_quests (user_id, quest_id, progress, status) "
                         "VALUES (?,?,1,'active')", (user_id, qid))
        elif row["status"] == "active":
            new_prog = row["progress"] + 1
            status = "done" if new_prog >= q["target_count"] else "active"
            conn.execute("UPDATE user_quests SET progress=?, status=? WHERE id=?",
                         (new_prog, status, row["id"]))


def grant_kill_rewards(conn, user_id, inst):
    """รางวัลจากมอนสเตอร์ที่ตาย (ผู้เรียกต้อง sync memory เอง)"""
    conn.execute("UPDATE users SET exp=exp+?, gold=gold+?, kills=kills+1 WHERE id=?",
                 (inst["exp"], inst["gold"], user_id))
    update_quest_progress(conn, user_id, inst["id"])
    user = get_user_by_id(conn, user_id)
    user, leveled = apply_level_up(conn, user)
    return {"exp_gain": inst["exp"], "gold_gain": inst["gold"], "leveled_up": leveled,
            "user": user_to_dict(get_user_by_id(conn, user_id))}


def sync_memory_stats(user_dict):
    """อัปเดต stat ในหน่วยความจำ (ไม่แตะ x/y/map กัน teleport ย้อนหลัง)"""
    with STATE_LOCK:
        for p in connected_players.values():
            if p["id"] == user_dict["id"]:
                p.update({
                    "level": user_dict["level"],
                    "hp": user_dict["hp"],
                    "mp": user_dict["mp"],
                    "max_hp": user_dict["maxHp"],
                    "max_mp": user_dict["maxMp"],
                    "atk": user_dict["atk"],
                    "def": user_dict["def"],   # ✅ dict literal ใช้ "def" เป็น key ได้
                })
                break

def find_sid_by_uid(uid):
    with STATE_LOCK:
        return next((s for s, q in connected_players.items() if q["id"] == uid), None)


def public_player_info(sid, p):
    return {"sid": sid, "id": p["id"], "username": p["username"], "x": p["x"], "y": p["y"],
            "map": p["map"], "level": p["level"], "hp": p["hp"]}


def broadcast_online():
    with STATE_LOCK:
        seen = {q["id"]: q for q in connected_players.values()}
        payload = {"count": len(seen), "players": [
            {"username": q["username"], "level": q["level"], "job": q["job"], "map": q["map"]}
            for q in seen.values()]}
    socketio.emit("online_players", payload, broadcast=True)


def cleanup_player(sid, announce=True):
    with STATE_LOCK:
        p = connected_players.pop(sid, None)
        for k in [k for k in _rate_limit if k[0] == sid]:
            _rate_limit.pop(k, None)
    if not p:
        return None
    with get_db() as conn:
        conn.execute("UPDATE users SET x=?, y=?, map=?, hp=?, mp=? WHERE id=?",
                     (p["x"], p["y"], p["map"], p["hp"], p["mp"], p["id"]))
    if announce:
        socketio.emit("remove_player", {"sid": sid}, room=p["map"])
        socketio.emit("system_message", {"message": f"💤 {p['username']} ออกจากเกม"},
                      broadcast=True)
    broadcast_online()
    return p


# ---------------------------------------------------------------------------
# REST: Auth
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/register", methods=["POST"])
def register():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    job = data.get("job", "Novice")
    if len(username) < 3 or len(username) > 20:
        return jsonify({"success": False, "message": "ชื่อผู้ใช้ต้องยาว 3-20 ตัวอักษร"}), 400
    if len(password) < 6:
        return jsonify({"success": False, "message": "รหัสผ่านต้องยาวอย่างน้อย 6 ตัวอักษร"}), 400
    if job not in GD.JOBS:
        job = "Novice"
    stats = GD.JOBS[job]
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO users (username, password_hash, job, hp, max_hp, mp, max_mp, atk, def)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (username, generate_password_hash(password), job,
                 stats["hp"], stats["hp"], stats["mp"], stats["mp"], stats["atk"], stats["def"]))
        log.info("New player registered: %s (%s)", username, job)
        return jsonify({"success": True, "message": "สร้างตัวละครสำเร็จ!"})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "ชื่อผู้ใช้นี้ถูกใช้งานแล้ว"}), 409


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if row is None or not check_password_hash(row["password_hash"], password):
            return jsonify({"success": False, "message": "ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง"}), 401
        if row["is_banned"]:
            return jsonify({"success": False, "message": "บัญชีนี้ถูกระงับการใช้งาน"}), 403
        if ADMIN_USERNAME and row["username"] == ADMIN_USERNAME and not row["is_admin"]:
            conn.execute("UPDATE users SET is_admin=1 WHERE id=?", (row["id"],))
            row = get_user_by_id(conn, row["id"])
        conn.execute("UPDATE users SET last_login=? WHERE id=?", (now_iso(), row["id"]))
        row = get_user_by_id(conn, row["id"])
    session["user_id"] = row["id"]
    return jsonify({"success": True, "user": user_to_dict(row)})


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/me")
def me():
    uid, err = authorize()
    if err:
        return err
    with get_db() as conn:
        row = get_user_by_id(conn, uid)
        if row is None or row["is_banned"]:
            session.clear()
            return jsonify({"success": False}), 401
    return jsonify({"success": True, "user": user_to_dict(row)})


# ---------------------------------------------------------------------------
# REST: ข้อมูลเกม
# ---------------------------------------------------------------------------
@app.route("/api/inventory/<int:user_id>")
def get_inventory(user_id):
    uid, err = authorize(user_id)
    if err:
        return err
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM inventory WHERE user_id=?", (uid,)).fetchall()
    items = []
    for r in rows:
        meta = GD.ITEMS.get(r["item_id"], {})
        items.append({"id": r["id"], "itemId": r["item_id"], "name": meta.get("name", "?"),
                      "type": meta.get("type"), "quantity": r["quantity"],
                      "equipped": bool(r["equipped"])})
    return jsonify({"success": True, "inventory": items})


@app.route("/api/monsters/<map_name>")
def get_monsters(map_name):
    if map_name not in GD.MAPS:
        return jsonify({"success": True, "monsters": []})
    with STATE_LOCK:
        insts = [serialize_monster(m) for m in MONSTER_INSTANCES.get(map_name, {}).values()]
    return jsonify({"success": True, "monsters": insts})


@app.route("/api/shop")
def get_shop():
    items = [{"id": iid, **meta} for iid, meta in sorted(GD.ITEMS.items())]
    return jsonify({"success": True, "items": items})


@app.route("/api/skills")
def get_skills():
    job = request.args.get("job")
    skills = {k: v for k, v in GD.SKILLS.items() if not job or v["job"] == job}
    return jsonify({"success": True, "skills": skills})


@app.route("/api/quests/<int:user_id>")
def get_quests(user_id):
    uid, err = authorize(user_id)
    if err:
        return err
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM user_quests WHERE user_id=?", (uid,)).fetchall()
    active = {r["quest_id"]: r for r in rows}
    result = []
    for qid, q in GD.QUESTS.items():
        prog = active.get(qid)
        result.append({"id": qid, **q, "progress": prog["progress"] if prog else 0,
                       "status": prog["status"] if prog else "not_started"})
    return jsonify({"success": True, "quests": result})


@app.route("/api/leaderboard")
def leaderboard():
    with get_db() as conn:
        rows = conn.execute("""SELECT username, job, level, kills, gold FROM users
                               WHERE is_banned=0 ORDER BY level DESC, exp DESC LIMIT 10""").fetchall()
    return jsonify({"success": True, "leaderboard": [dict(r) for r in rows]})


@app.route("/api/online")
def online():
    with STATE_LOCK:
        seen = {q["id"]: q for q in connected_players.values()}
        players = [{"username": q["username"], "level": q["level"], "job": q["job"], "map": q["map"]}
                   for q in seen.values()]
    return jsonify({"success": True, "count": len(players), "players": players})


@app.route("/api/chat/recent")
def chat_recent():
    with get_db() as conn:
        rows = conn.execute("""SELECT username, channel, message, created_at FROM chat_log
                               ORDER BY id DESC LIMIT 30""").fetchall()
    msgs = [{"username": r["username"],
             "channel": r["channel"] if r["channel"] in ("global", "map", "whisper", "sys") else "global",
             "message": r["message"], "time": (r["created_at"] or "")[11:16]}
            for r in reversed(rows)]
    return jsonify({"success": True, "messages": msgs})


# ---------------------------------------------------------------------------
# REST: ธุรกรรม (buy / sell / claim / respawn / daily)
# ---------------------------------------------------------------------------
@app.route("/api/shop/buy", methods=["POST"])
def buy_item():
    data = request.json or {}
    uid, err = authorize(data.get("user_id"))
    if err:
        return err
    item = GD.ITEMS.get(data.get("item_id"))
    if not item:
        return jsonify({"success": False, "message": "ไม่พบไอเทมนี้"}), 404
    with get_db() as conn:
        user = get_user_by_id(conn, uid)
        if user["gold"] < item["price"]:
            return jsonify({"success": False, "message": "เงินไม่พอ"}), 400
        if user["level"] < item.get("level_req", 1):
            return jsonify({"success": False, "message": "เลเวลไม่ถึงเกณฑ์"}), 400
        conn.execute("UPDATE users SET gold=gold-? WHERE id=?", (item["price"], uid))
        existing = conn.execute(
            "SELECT * FROM inventory WHERE user_id=? AND item_id=? AND equipped=0",
            (uid, data["item_id"])).fetchone()
        if existing and item["type"] in ("potion", "material"):
            conn.execute("UPDATE inventory SET quantity=quantity+1 WHERE id=?", (existing["id"],))
        else:
            conn.execute("INSERT INTO inventory (user_id, item_id, quantity) VALUES (?,?,1)",
                         (uid, data["item_id"]))
        user = get_user_by_id(conn, uid)
    return jsonify({"success": True, "user": user_to_dict(user)})


@app.route("/api/shop/sell", methods=["POST"])
def sell_item():
    data = request.json or {}
    uid, err = authorize(data.get("user_id"))
    if err:
        return err
    inv_id = data.get("inventory_id")
    with get_db() as conn:
        inv = conn.execute("SELECT * FROM inventory WHERE id=? AND user_id=?",
                           (inv_id, uid)).fetchone()
        if inv is None:
            return jsonify({"success": False, "message": "ไม่พบไอเทม"}), 404
        if inv["equipped"]:
            return jsonify({"success": False, "message": "ต้องถอดออกก่อนจึงจะขายได้"}), 400
        item = GD.ITEMS.get(inv["item_id"], {})
        price = max(1, item.get("price", 0) // 2)
        if inv["quantity"] > 1:
            conn.execute("UPDATE inventory SET quantity=quantity-1 WHERE id=?", (inv_id,))
        else:
            conn.execute("DELETE FROM inventory WHERE id=?", (inv_id,))
        conn.execute("UPDATE users SET gold=gold+? WHERE id=?", (price, uid))
        user = get_user_by_id(conn, uid)
    sync_memory_stats(user_to_dict(user))
    return jsonify({"success": True, "message": f"ขาย {item.get('name','ไอเทม')} ได้ {price} Gold",
                    "user": user_to_dict(user)})


@app.route("/api/quests/claim", methods=["POST"])
def claim_quest():
    data = request.json or {}
    uid, err = authorize(data.get("user_id"))
    if err:
        return err
    quest = GD.QUESTS.get(data.get("quest_id"))
    if not quest:
        return jsonify({"success": False, "message": "ไม่พบเควสนี้"}), 404
    with get_db() as conn:
        row = conn.execute("SELECT * FROM user_quests WHERE user_id=? AND quest_id=?",
                           (uid, data["quest_id"])).fetchone()
        if row is None or row["status"] != "done":
            return jsonify({"success": False, "message": "เควสยังไม่สำเร็จ"}), 400
        conn.execute("UPDATE user_quests SET status='claimed' WHERE id=?", (row["id"],))
        conn.execute("UPDATE users SET gold=gold+?, exp=exp+? WHERE id=?",
                     (quest["reward_gold"], quest["reward_exp"], uid))
        user = get_user_by_id(conn, uid)
        user, leveled = apply_level_up(conn, user)
        user_row = get_user_by_id(conn, uid)
    user_d = user_to_dict(user_row)
    sync_memory_stats(user_d)
    return jsonify({"success": True, "user": user_d, "leveled_up": leveled})


@app.route("/api/respawn", methods=["POST"])
def respawn():
    data = request.json or {}
    uid, err = authorize(data.get("user_id"))
    if err:
        return err
    with get_db() as conn:
        conn.execute("UPDATE users SET hp=max_hp, mp=max_mp, map='town', x=400, y=300 WHERE id=?",
                     (uid,))
        user = get_user_by_id(conn, uid)
    user_d = user_to_dict(user)
    sid = find_sid_by_uid(uid)
    if sid:
        with STATE_LOCK:  # อัปเดต hp/mp/พิกัด — map ปล่อยให้ event 'move' จัดการสลับห้อง
            p = connected_players.get(sid)
            if p:
                p.update(hp=user_d["maxHp"], mp=user_d["maxMp"], x=400.0, y=300.0)
    return jsonify({"success": True, "user": user_d})


@app.route("/api/daily", methods=["POST"])
def daily_reward():
    data = request.json or {}
    uid, err = authorize(data.get("user_id"))
    if err:
        return err
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with get_db() as conn:
        user = get_user_by_id(conn, uid)
        if user["last_daily"] == today:
            return jsonify({"success": False, "message": "วันนี้รับรางวัลรายวันไปแล้ว"}), 400
        reward = 100 + user["level"] * 50
        conn.execute("UPDATE users SET gold=gold+?, last_daily=? WHERE id=?", (reward, today, uid))
        user = get_user_by_id(conn, uid)
    sync_memory_stats(user_to_dict(user))
    return jsonify({"success": True, "reward": reward, "user": user_to_dict(user)})


# ---------------------------------------------------------------------------
# Socket.IO: presence
# ---------------------------------------------------------------------------
@socketio.on("join_game")
def handle_join(data):
    sid = request.sid
    uid = data.get("id")
    sess_uid = session.get("user_id")
    if uid is None or sess_uid is None or str(uid) != str(sess_uid):
        emit("force_disconnect", {"reason": "session ไม่ถูกต้อง กรุณาล็อกอินใหม่"})
        return
    with get_db() as conn:
        user = get_user_by_id(conn, uid)
        if user is None or user["is_banned"]:
            emit("force_disconnect", {"reason": "banned"})
            return
        conn.execute("UPDATE users SET last_login=? WHERE id=?", (now_iso(), uid))

    # ----- ป้องกันล็อกอินซ้ำ: เตะ session เดิม -----
    dup = find_sid_by_uid(uid)
    if dup:
        socketio.emit("force_disconnect", {"reason": "มีการล็อกอินจากที่อื่น"}, room=dup)
        cleanup_player(dup, announce=False)

    map_name = user["map"] if user["map"] in GD.MAPS else "town"
    with STATE_LOCK:
        connected_players[sid] = {
            "id": user["id"], "username": user["username"], "job": user["job"],
            "level": user["level"], "hp": user["hp"], "mp": user["mp"],
            "max_hp": user["max_hp"], "max_mp": user["max_mp"],
            "atk": user["atk"], "def": user["def"],
            "x": clamp(float(user["x"]), 20, 780), "y": clamp(float(user["y"]), 20, 580),
            "map": map_name, "is_admin": bool(user["is_admin"]),
            "skill_cd": {}, "last_move_t": time.time(),
        }
        room_players = {s: public_player_info(s, q) for s, q in connected_players.items()
                        if q["map"] == map_name}
        sync = [serialize_monster(m) for m in MONSTER_INSTANCES.get(map_name, {}).values()]
    join_room(map_name)
    emit("players_in_map", room_players, room=map_name)
    emit("monsters_sync", {"map": map_name, "monsters": sync}, room=sid)
    emit("stats_update", {"hp": user["hp"], "mp": user["mp"]}, room=sid)
    broadcast_online()
    socketio.emit("system_message", {"message": f"⚡ {user['username']} เข้าสู่โลก Lumivara"},
                  broadcast=True)
    log.info("Player %s joined map %s", user["username"], map_name)


@socketio.on("move")
def handle_move(data):
    sid = request.sid
    p = connected_players.get(sid)
    if not p or p["hp"] <= 0:
        return
    try:
        x, y = float(data.get("x", p["x"])), float(data.get("y", p["y"]))
    except (TypeError, ValueError):
        return
    if math.isnan(x) or math.isnan(y):
        return
    x, y = clamp(x, 20, 780), clamp(y, 20, 580)
    new_map = data.get("map", p["map"])
    if new_map not in GD.MAPS:
        new_map = p["map"]

    # ----- จำกัดความเร็ว (กัน speed hack) -----
    now = time.time()
    dt = max(0.05, now - p.get("last_move_t", now))
    dist = math.hypot(x - p["x"], y - p["y"])
    max_step = MAX_MOVE_SPEED * dt
    if dist > max_step and dist > 0:
        scale = max_step / dist
        x, y = p["x"] + (x - p["x"]) * scale, p["y"] + (y - p["y"]) * scale

    old_map = p["map"]
    changed_map = new_map != old_map
    with STATE_LOCK:
        p.update(x=x, y=y, last_move_t=now)
        if changed_map:
            p["map"] = new_map
        payload = public_player_info(sid, p)
        if changed_map:
            sync = [serialize_monster(m) for m in MONSTER_INSTANCES.get(new_map, {}).values()]
            room_players = {s: public_player_info(s, q) for s, q in connected_players.items()
                            if q["map"] == new_map}

    if changed_map:
        leave_room(old_map)
        join_room(new_map)
        emit("player_left_map", {"sid": sid}, room=old_map)
        emit("players_in_map", room_players, room=new_map)
        emit("monsters_sync", {"map": new_map, "monsters": sync}, room=sid)
    emit("move_player", payload, room=p["map"], include_self=False)


@socketio.on("disconnect")
def handle_disconnect():
    p = cleanup_player(request.sid, announce=True)
    if p:
        log.info("Player %s disconnected", p.get("username"))


# ---------------------------------------------------------------------------
# Socket.IO: combat
# ---------------------------------------------------------------------------
@socketio.on("attack_monster")
def handle_attack(data):
    sid = request.sid
    p = connected_players.get(sid)
    if not p:
        return
    if not rate_ok(sid, "attack", ATTACK_COOLDOWN):
        return  # เงียบไว้ กัน spam notice ฝั่ง client
    if p["hp"] <= 0:
        emit("attack_result", {"success": False, "message": "คุณสลบอยู่ ฟื้นก่อนจึงจะสู้ได้"})
        return
    mid = data.get("monster_id")
    with STATE_LOCK:
        inst = MONSTER_INSTANCES.get(p["map"], {}).get(mid)
        snap = dict(inst) if inst and inst["alive"] else None
    if not snap:
        emit("attack_result", {"success": False, "message": "ไม่พบมอนสเตอร์ (หรือรอเกิดใหม่)"})
        return
    if math.hypot(p["x"] - snap["x"], p["y"] - snap["y"]) > ATTACK_RANGE:
        emit("attack_result", {"success": False, "message": "มอนสเตอร์อยู่ไกลเกินระยะโจมตี"})
        return

    dodged = random.random() < MONSTER_DODGE
    dmg, crit, hp_left, died, state = 0, False, snap["hp"], False, None
    if not dodged:
        dmg, crit = roll_damage(p["atk"], snap["def"])
        with STATE_LOCK:
            inst["hp"] = max(0, inst["hp"] - dmg)
            hp_left, died = inst["hp"], inst["hp"] <= 0
            if died:
                inst["alive"] = False
                inst["respawn_at"] = time.time() + inst["respawn_sec"]
            state = serialize_monster(inst)
        socketio.emit("monster_state", state, room=p["map"])

    result = {"success": True, "monster_id": mid, "dmg": dmg, "crit": crit, "dodged": dodged,
              "monster_hp_left": hp_left, "monster_died": died}
    if died:
        with get_db() as conn:
            result.update(grant_kill_rewards(conn, p["id"], snap))
        sync_memory_stats(result["user"])
    elif not dodged:
        m_dmg, _ = roll_damage(snap["atk"], p["def"])
        if random.random() < MONSTER_MISS:
            m_dmg = 0
        if m_dmg:
            with get_db() as conn:
                row = get_user_by_id(conn, p["id"])
                new_hp = max(0, row["hp"] - m_dmg)
                conn.execute("UPDATE users SET hp=? WHERE id=?", (new_hp, p["id"]))
            with STATE_LOCK:
                p["hp"] = new_hp
        else:
            new_hp = p["hp"]
        result.update({"monster_dmg": m_dmg, "player_hp_left": new_hp})
    emit("attack_result", result)


@socketio.on("use_skill")
def handle_use_skill(data):
    sid = request.sid
    p = connected_players.get(sid)
    if not p:
        return
    if not rate_ok(sid, "skill", 0.35):
        return
    if p["hp"] <= 0:
        emit("skill_result", {"success": False, "message": "สลบอยู่ใช้สกิลไม่ได้"})
        return
    skill_id = data.get("skill")
    sk = GD.SKILLS.get(skill_id)
    if not sk or sk["job"] not in ("All", p["job"]):
        emit("skill_result", {"success": False, "message": "ไม่พบสกิล/อาชีพไม่ตรง"})
        return
    now = time.time()
    with STATE_LOCK:
        cds = p.setdefault("skill_cd", {})
        if now < cds.get(skill_id, 0):
            emit("skill_result", {"success": False,
                                  "message": f"สกิลคูลดาวน์อีก {int(cds[skill_id] - now) + 1} วินาที"})
            return
        if p["mp"] < sk["mp"]:
            emit("skill_result", {"success": False, "message": "MP ไม่พอ"})
            return

    # ----- สกิลฟื้นฟู -----
    if sk["type"] == "heal":
        heal = int(p["max_hp"] * sk.get("heal_pct", 0.3))
        with get_db() as conn:
            row = get_user_by_id(conn, p["id"])
            new_hp = min(row["max_hp"], row["hp"] + heal)
            new_mp = max(0, row["mp"] - sk["mp"])
            conn.execute("UPDATE users SET hp=?, mp=? WHERE id=?", (new_hp, new_mp, p["id"]))
        with STATE_LOCK:
            p["hp"], p["mp"] = new_hp, new_mp
            p["skill_cd"][skill_id] = now + sk.get("cd", 4)
        emit("skill_result", {"success": True, "skill": skill_id, "type": "heal",
                              "heal": heal, "hp": new_hp, "mp": new_mp})
        return

    # ----- สกิลโจมตี -----
    radius = sk.get("radius", ATTACK_RANGE)
    with STATE_LOCK:
        px, py = p["x"], p["y"]
        if sk["type"] == "aoe":
            targets = [dict(m) for m in MONSTER_INSTANCES.get(p["map"], {}).values()
                       if m["alive"] and math.hypot(px - m["x"], py - m["y"]) <= radius]
        else:
            m = MONSTER_INSTANCES.get(p["map"], {}).get(data.get("monster_id"))
            targets = [dict(m)] if m and m["alive"] else []
    if not targets:
        emit("skill_result", {"success": False, "message": "ไม่มีเป้าหมายในระยะ"})
        return

    planned = []
    for t in targets:
        for _ in range(sk.get("hits", 1)):
            dmg, crit = roll_damage(p["atk"], t["def"], mult=sk.get("mult", 1.5))
            planned.append((t["id"], dmg, crit))

    with get_db() as conn:
        row = get_user_by_id(conn, p["id"])
        new_mp = max(0, row["mp"] - sk["mp"])
        conn.execute("UPDATE users SET mp=? WHERE id=?", (new_mp, p["id"]))

    hits, died_list, states = [], [], []
    with STATE_LOCK:
        for mid, dmg, crit in planned:
            inst = MONSTER_INSTANCES.get(p["map"], {}).get(mid)
            if not inst or not inst["alive"]:
                continue
            inst["hp"] = max(0, inst["hp"] - dmg)
            died = inst["hp"] <= 0
            if died:
                inst["alive"] = False
                inst["respawn_at"] = time.time() + inst["respawn_sec"]
                died_list.append(dict(inst))
            hits.append({"monster_id": mid, "dmg": dmg, "crit": crit,
                         "monster_hp_left": inst["hp"], "monster_died": died})
            states.append(serialize_monster(inst))
        p["mp"] = new_mp
        p["skill_cd"][skill_id] = now + sk.get("cd", 4)

    for st in states:
        socketio.emit("monster_state", st, room=p["map"])

    if died_list:
        merged = {"exp_gain": 0, "gold_gain": 0, "leveled_up": False}
        user_payload = None
        with get_db() as conn:
            for inst in died_list:
                g = grant_kill_rewards(conn, p["id"], inst)
                merged["exp_gain"] += g["exp_gain"]
                merged["gold_gain"] += g["gold_gain"]
                merged["leveled_up"] = merged["leveled_up"] or g["leveled_up"]
                user_payload = g["user"]
        sync_memory_stats(user_payload)
        emit("skill_result", {"success": True, "skill": skill_id, "hits": hits,
                              "mp": new_mp, **merged, "user": user_payload})
    else:
        emit("skill_result", {"success": True, "skill": skill_id, "hits": hits, "mp": new_mp})


# ---------------------------------------------------------------------------
# Socket.IO: PvP (เปิดเฉพาะ dungeon)
# ---------------------------------------------------------------------------
@socketio.on("attack_player")
def handle_pvp(data):
    sid = request.sid
    p = connected_players.get(sid)
    if not p or p["hp"] <= 0:
        return
    if p["map"] != PVP_MAP:
        emit("pvp_result", {"success": False, "message": "PvP เปิดเฉพาะในดันเจี้ยน"})
        return
    if not rate_ok(sid, "pvp", PVP_COOLDOWN):
        return
    t_sid = data.get("target_sid")
    with STATE_LOCK:
        t = connected_players.get(t_sid)
        t_snap = ({"id": t["id"], "username": t["username"], "x": t["x"], "y": t["y"],
                   "def": t["def"], "level": t["level"]}
                  if t and t["id"] != p["id"] and t["map"] == p["map"] and t["hp"] > 0 else None)
    if not t_snap:
        emit("pvp_result", {"success": False, "message": "ไม่พบเป้าหมาย"})
        return
    if math.hypot(p["x"] - t_snap["x"], p["y"] - t_snap["y"]) > ATTACK_RANGE:
        emit("pvp_result", {"success": False, "message": "เป้าหมายไกลเกินไป"})
        return

    dmg, crit = roll_damage(p["atk"], t_snap["def"])
    loot_gold, winner_user = 0, None
    with get_db() as conn:
        t_row = get_user_by_id(conn, t_snap["id"])
        new_hp = max(0, t_row["hp"] - dmg)
        conn.execute("UPDATE users SET hp=? WHERE id=?", (new_hp, t_snap["id"]))
        if new_hp <= 0:
            loot_gold = t_row["gold"] // 10
            conn.execute("UPDATE users SET gold=gold-? WHERE id=?", (loot_gold, t_snap["id"]))
            conn.execute("UPDATE users SET gold=gold+?, exp=exp+? WHERE id=?",
                         (loot_gold, t_snap["level"] * 15, p["id"]))
            user, _ = apply_level_up(conn, get_user_by_id(conn, p["id"]))
            winner_user = user_to_dict(get_user_by_id(conn, p["id"]))
    with STATE_LOCK:
        if t_sid in connected_players:
            connected_players[t_sid]["hp"] = new_hp
    if winner_user:
        sync_memory_stats(winner_user)

    emit("pvp_result", {"success": True, "target": t_snap["username"], "dmg": dmg, "crit": crit,
                        "target_hp": new_hp, "kill": new_hp <= 0, "loot_gold": loot_gold,
                        "user": winner_user}, room=sid)
    emit("pvp_hit", {"attacker": p["username"], "dmg": dmg, "hp": new_hp, "died": new_hp <= 0},
         room=t_sid)
    if new_hp <= 0:
        socketio.emit("system_message",
                      {"message": f"⚔️ {p['username']} ปราบ {t_snap['username']} ในสนาม PvP แย่งชิง {loot_gold} Gold!"},
                      room=p["map"])


# ---------------------------------------------------------------------------
# Socket.IO: ไอเทม (ใช้ sid ระบุตัวตน ไม่เชื่อ user_id จาก client)
# ---------------------------------------------------------------------------
@socketio.on("use_item")
def handle_use_item(data):
    p = connected_players.get(request.sid)
    if not p:
        return
    if p["hp"] <= 0:
        emit("item_result", {"success": False, "message": "สลบอยู่ ใช้ไอเทมไม่ได้"})
        return
    inv_id = data.get("inventory_id")
    with get_db() as conn:
        inv = conn.execute("SELECT * FROM inventory WHERE id=? AND user_id=?",
                           (inv_id, p["id"])).fetchone()
        if inv is None:
            emit("item_result", {"success": False, "message": "ไม่พบไอเทม"})
            return
        item = GD.ITEMS.get(inv["item_id"], {})
        if item.get("type") != "potion":
            emit("item_result", {"success": False, "message": "ไอเทมนี้ต้องสวมใส่ ไม่ใช่ใช้ตรง ๆ"})
            return
        user = get_user_by_id(conn, p["id"])
        new_hp = min(user["max_hp"], user["hp"] + item.get("heal", 0))
        new_mp = min(user["max_mp"], user["mp"] + item.get("heal_mp", 0))
        conn.execute("UPDATE users SET hp=?, mp=? WHERE id=?", (new_hp, new_mp, p["id"]))
        if inv["quantity"] > 1:
            conn.execute("UPDATE inventory SET quantity=quantity-1 WHERE id=?", (inv_id,))
        else:
            conn.execute("DELETE FROM inventory WHERE id=?", (inv_id,))
        user = get_user_by_id(conn, p["id"])
        user_d = user_to_dict(user)
    with STATE_LOCK:
        p["hp"], p["mp"] = user_d["hp"], user_d["mp"]
    emit("item_result", {"success": True, "user": user_d})


@socketio.on("equip_item")
def handle_equip(data):
    p = connected_players.get(request.sid)
    if not p:
        return
    inv_id = data.get("inventory_id")
    with get_db() as conn:
        inv = conn.execute("SELECT * FROM inventory WHERE id=? AND user_id=?",
                           (inv_id, p["id"])).fetchone()
        if inv is None:
            emit("item_result", {"success": False, "message": "ไม่พบไอเทม"})
            return
        item = GD.ITEMS.get(inv["item_id"], {})
        if item.get("type") not in ("weapon", "armor", "accessory"):
            emit("item_result", {"success": False, "message": "สวมใส่ไอเทมนี้ไม่ได้"})
            return
        user = get_user_by_id(conn, p["id"])
        if user["level"] < item.get("level_req", 1):
            emit("item_result", {"success": False, "message": "เลเวลไม่ถึง"})
            return
        # ถอดชิ้นเดิมประเภทเดียวกัน
        for row in conn.execute("SELECT inventory.id AS inv_id, item_id FROM inventory "
                                "WHERE user_id=? AND equipped=1", (p["id"],)).fetchall():
            other = GD.ITEMS.get(row["item_id"])
            if other and other["type"] == item["type"]:
                conn.execute("UPDATE inventory SET equipped=0 WHERE id=?", (row["inv_id"],))
                conn.execute("""UPDATE users SET atk=atk-?, def=def-?, max_hp=max_hp-?, max_mp=max_mp-?
                                WHERE id=?""",
                             (other.get("atk_bonus", 0), other.get("def_bonus", 0),
                              other.get("hp_bonus", 0), other.get("mp_bonus", 0), p["id"]))
        conn.execute("UPDATE inventory SET equipped=1 WHERE id=?", (inv_id,))
        conn.execute("""UPDATE users SET atk=atk+?, def=def+?, max_hp=max_hp+?, max_mp=max_mp+?,
                        hp=MIN(hp, max_hp+?), mp=MIN(mp, max_mp+?) WHERE id=?""",
                     (item.get("atk_bonus", 0), item.get("def_bonus", 0),
                      item.get("hp_bonus", 0), item.get("mp_bonus", 0),
                      item.get("hp_bonus", 0), item.get("mp_bonus", 0), p["id"]))
        user = get_user_by_id(conn, p["id"])
        user_d = user_to_dict(user)
    sync_memory_stats(user_d)
    emit("item_result", {"success": True, "user": user_d})


# ---------------------------------------------------------------------------
# Socket.IO: แชท
# ---------------------------------------------------------------------------
@socketio.on("send_chat")
def handle_chat(data):
    p = connected_players.get(request.sid)
    if not p:
        return
    if not rate_ok(request.sid, "chat", CHAT_COOLDOWN):
        emit("chat_message", {"channel": "sys", "username": "ระบบ", "message": "พิมพ์เร็วเกินไป รอสักครู่"})
        return
    message = str(data.get("message") or "").strip()[:300]
    if not message:
        return
    channel = data.get("channel", "global")
    if channel not in ("global", "map", "whisper"):
        channel = "global"
    username = p["username"]  # กันปลอมชื่อ

    with get_db() as conn:
        conn.execute("INSERT INTO chat_log (username, channel, message) VALUES (?,?,?)",
                     (username, channel, message))
    payload = {"username": username, "message": message, "channel": channel,
               "time": datetime.now(timezone.utc).strftime("%H:%M")}

    if channel == "whisper":
        target = (data.get("target_username") or "").strip().lower()
        dest = data.get("target_sid")
        if dest not in connected_players and target:
            with STATE_LOCK:
                dest = next((s for s, q in connected_players.items()
                             if q["username"].lower() == target), None)
        if dest:
            emit("chat_message", payload, room=dest)
            emit("chat_message", payload, room=request.sid)
        else:
            emit("chat_message", {"channel": "sys", "username": "ระบบ",
                                  "message": "ไม่พบผู้เล่นนี้ออนไลน์อยู่"}, room=request.sid)
    elif channel == "map":
        emit("chat_message", payload, room=p["map"])
    else:
        emit("chat_message", payload, broadcast=True)


# ---------------------------------------------------------------------------
# Socket.IO: แอดมิน (ตรวจสิทธิ์จาก sid ฝั่งเซิร์ฟเวอร์)
# ---------------------------------------------------------------------------
@socketio.on("admin_broadcast")
def handle_admin_broadcast(data):
    p = connected_players.get(request.sid)
    if not p or not p.get("is_admin"):
        return
    msg = str(data.get("message") or "").strip()[:300]
    if msg:
        emit("system_message", {"message": msg}, broadcast=True)


@socketio.on("admin_ban")
def handle_admin_ban(data):
    p = connected_players.get(request.sid)
    if not p or not p.get("is_admin"):
        return
    target = str(data.get("username") or "").strip()
    with get_db() as conn:
        row = conn.execute("SELECT id FROM users WHERE username=?", (target,)).fetchone()
        if row is None:
            emit("chat_message", {"channel": "sys", "username": "ระบบ",
                                  "message": f"ไม่พบผู้ใช้ '{target}'"}, room=request.sid)
            return
        conn.execute("UPDATE users SET is_banned=1 WHERE username=?", (target,))
    with STATE_LOCK:
        kick = [s for s, q in connected_players.items() if q["username"] == target]
    for s in kick:
        socketio.emit("force_disconnect", {"reason": "banned"}, room=s)
        cleanup_player(s, announce=False)
    emit("system_message", {"message": f"🔨 {target} ถูกแบนโดยแอดมิน"}, broadcast=True)


# ---------------------------------------------------------------------------
# Background loop: regen / wander / respawn / autosave
# ---------------------------------------------------------------------------
def game_tick_loop():
    last_save = time.time()
    log.info("Game tick loop started (interval=%ss)", TICK_SECONDS)
    while True:
        socketio.sleep(TICK_SECONDS)
        now = time.time()
        updates, moves, respawns = [], {}, []

        with STATE_LOCK:
            # ----- regen (ในเมืองฟื้นเร็ว 3 เท่า) -----
            for sid, p in connected_players.items():
                if p["hp"] <= 0:
                    continue
                fast = p["map"] == "town"
                new_hp = min(p["max_hp"], p["hp"] + max(1, int(p["max_hp"] * (0.03 if fast else 0.01))))
                new_mp = min(p["max_mp"], p["mp"] + max(1, int(p["max_mp"] * (0.035 if fast else 0.012))))
                if new_hp != p["hp"] or new_mp != p["mp"]:
                    p["hp"], p["mp"] = new_hp, new_mp
                    updates.append((sid, new_hp, new_mp, p["id"]))
            # ----- มอนสเตอร์เดิน + เกิดใหม่ -----
            for map_name, insts in MONSTER_INSTANCES.items():
                for m in insts.values():
                    if m["alive"]:
                        if step_wander(m):
                            moves.setdefault(map_name, []).append(
                                {"id": m["id"], "x": round(m["x"], 1), "y": round(m["y"], 1)})
                    elif now >= m["respawn_at"]:
                        respawn_monster(m)
                        respawns.append((map_name, serialize_monster(m)))
            # prune rate limit เก่า
            for k in [k for k, t in _rate_limit.items() if now - t > 60]:
                _rate_limit.pop(k, None)

        for sid, hp, mp, _ in updates:
            socketio.emit("stats_update", {"hp": hp, "mp": mp}, room=sid)
        for map_name, mv in moves.items():
            socketio.emit("monsters_move", {"moves": mv}, room=map_name)
        for map_name, st in respawns:
            socketio.emit("monster_state", st, room=map_name)

        # ----- autosave -----
        if now - last_save >= AUTOSAVE_SECONDS:
            last_save = now
            with STATE_LOCK:
                snapshot = [(p["x"], p["y"], p["map"], p["hp"], p["mp"], p["id"])
                            for p in connected_players.values()]
            if snapshot:
                with get_db() as conn:
                    conn.executemany(
                        "UPDATE users SET x=?, y=?, map=?, hp=?, mp=? WHERE id=?", snapshot)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    spawn_all_monsters()
    socketio.start_background_task(game_tick_loop)
    # use_reloader=False กัน background task รันซ้ำ 2 ตัว
    socketio.run(app, host="0.0.0.0", port=5000, debug=True, use_reloader=False)