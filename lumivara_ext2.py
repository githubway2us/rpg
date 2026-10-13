# -*- coding: utf-8 -*-
"""
lumivara_ext2.py — SYSTEMS PACK v2.0 (Pet / Guild / PvP Rank / Balance)
ต้องมี lumivara_ext.py v1.0 อยู่ก่อน — โหลดอัตโนมัติผ่าน hook ท้ายไฟล์ v1
"""
import time, math, random, threading, logging, sqlite3
from datetime import datetime, timezone
from flask import request, jsonify, session, Response

log = logging.getLogger("lumivara.ext2")
_G = {"g": None}
V2 = "2.0"

# ================= ค่าคงที่ระบบใหม่ =================
PET_FOOD = 610
EGGS = {620: ("wolf", "ไข่ลูกหมาป่า", 3000),
        621: ("bird", "ไข่นกฟ้า", 5000),
        622: ("dragon", "ไข่ลูกมังกร", 30000)}
PET_TYPES = {
    "wolf":   {"icon": "🐺", "name": "ลูกหมาป่า", "atk": 9,  "crit": 0.08},
    "bird":   {"icon": "🐦", "name": "นกฟ้า",     "atk": 7,  "crit": 0.22},
    "dragon": {"icon": "🐲", "name": "ลูกมังกร",  "atk": 12, "crit": 0.12},
}
PET_MAX_LV = 60
GUILD_CREATE_GOLD, GUILD_CREATE_LV, GUILD_CAP = 5000, 10, 20
GUILD_POTION = 630
PVP_START, PVP_DAILY_GOLD = 1000, 500

BALANCE_LOG = []

# ================= Balance =================
BALANCE = {
    "const": {"CRIT_CHANCE": 0.12, "MONSTER_DODGE": 0.03, "PLAYER_DODGE": 0.05,
              "DEATH_EXP_LOSS": 0.08, "DEATH_GOLD_LOSS": 0.03,
              "GROUND_ITEM_TTL": 120.0, "IDLE_REGEN_DELAY": 6.0, "IDLE_REGEN_PCT": 0.06},
    "mon_hp_mult": 0.90, "mon_boss_hp_mult": 0.92,
    "low_exp_mult": 1.30, "low_exp_max_lv": 15,
    "skills": {"power_strike": {"mult": 2.0}, "magnum": {"mult": 1.75},
               "fire_blast": {"mp": 18}, "meteor": {"cd": 9},
               "heal_plus": {"heal_pct": 0.62}, "magnificat": {"heal_pct": 0.75},
               "sonic_blow": {"mult": 2.8}, "grimtooth": {"mult": 3.2}, "brandish": {"mult": 3.1}},
    "items": {1: {"heal_pct": 0.40}, 2: {"mana_pct": 0.40},
              3: {"heal_pct": 0.85}, 4: {"mana_pct": 0.85}},
}

def _apply_balance(g):
    for k, v in BALANCE["const"].items():
        if k in g:
            g[k] = v
            BALANCE_LOG.append(f"{k} -> {v}")
    hp_m, bh_m = BALANCE["mon_hp_mult"], BALANCE["mon_boss_hp_mult"]
    for key, insts in g["GD"].MONSTERS.items():
        for m in insts:
            m["hp"] = int(m["hp"] * (bh_m if m.get("boss") else hp_m))
            if m["level"] <= BALANCE["low_exp_max_lv"]:
                m["exp"] = int(m["exp"] * BALANCE["low_exp_mult"])
    # แพตช์อินสแตนซ์ที่ spawn ไปแล้ว (ถ้ามี)
    try:
        for mapkey, live in g["MONSTER_INSTANCES"].items():
            defs = {d["id"]: d for d in g["GD"].MONSTERS.get(mapkey, [])}
            for inst in live.values():
                d = defs.get(inst.get("base_id"))
                if not d:
                    continue
                ratio = inst["hp"] / inst["max_hp"] if inst["max_hp"] else 1.0
                inst["max_hp"], inst["exp"], inst["gold"] = d["hp"], d["exp"], d["gold"]
                if inst["alive"]:
                    inst["hp"] = max(1, int(d["hp"] * ratio))
    except Exception:
        pass
    for sid, patch in BALANCE["skills"].items():
        if sid in g["GD"].SKILLS:
            g["GD"].SKILLS[sid].update(patch)
            BALANCE_LOG.append(f"skill:{sid} {patch}")
    for iid, patch in BALANCE["items"].items():
        if iid in g["GD"].ITEMS:
            g["GD"].ITEMS[iid].update(patch)
    BALANCE_LOG.append("Novice hp growth 14 -> 16")
    g["GD"].JOBS["Novice"]["g"]["hp"] = 16

# ================= Helpers =================
def _sid(uid):
    return _G["g"]["find_sid_by_uid"](uid)

def _notice(uid, msg):
    s = _sid(uid)
    if s:
        _G["g"]["socketio"].emit("ext2_notice", {"message": msg}, room=s)

def _pvp_title(pts):
    for lo, t in [
        (1400, "ผู้พิชิต 👑"),
        (1250, "ไดมอนด์ 💎"),
        (1150, "แพลทินัม 🥈"),
        (1050, "โกลด์ 🥇"),
        (950,  "ซิลเวอร์"),
    ]:
        if pts >= lo:
            return t
    return "บรอนซ์"

def _pet_need(lv):
    return int(60 * lv ** 1.45)

def _pet_stats(ptype, lv):
    t = PET_TYPES[ptype]
    return {"atk": t["atk"] + lv * 2.6, "crit": t["crit"], "icon": t["icon"]}

# ================= DB =================
def _db_init(g):
    conn = sqlite3.connect(g["DB_PATH"], timeout=15)
    try:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS pets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT, type TEXT, level INTEGER DEFAULT 1, exp INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS guilds (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
                leader_id INTEGER NOT NULL, level INTEGER DEFAULT 1, exp INTEGER DEFAULT 0,
                fund INTEGER DEFAULT 0, notice TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        c.execute("""CREATE TABLE IF NOT EXISTS guild_members (
                guild_id INTEGER NOT NULL REFERENCES guilds(id) ON DELETE CASCADE,
                user_id INTEGER UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role TEXT DEFAULT 'member', joined_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        cols = {r[1] for r in c.execute("PRAGMA table_info(users)")}
        alters = [
            ("pvp_points", "INTEGER DEFAULT 1000"),
            ("pvp_wins", "INTEGER DEFAULT 0"),
            ("pvp_losses", "INTEGER DEFAULT 0"),
            ("pvp_streak", "INTEGER DEFAULT 0"),
            ("pvp_last_win", "TEXT DEFAULT ''"),
        ]
        for col, typ in alters:
            if col not in cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
        c.execute("CREATE INDEX IF NOT EXISTS idx_gm_guild ON guild_members(guild_id)")
        conn.commit()
    finally:
        conn.close()

# ================= PETS (server) =================
PETS_MEM = {}   # uid -> {"x","y","map","active","row":{...},"cd_until":0}

def _ensure_pet(g, uid):
    if uid in PETS_MEM:
        return PETS_MEM[uid]
    with g["get_db"]() as conn:
        row = conn.execute("SELECT * FROM pets WHERE user_id=?", (uid,)).fetchone()
    if not row:
        return None
    row = dict(row)
    PETS_MEM[uid] = {"x": 400.0, "y": 300.0, "map": None, "cd_until": 0.0, "row": row}
    return PETS_MEM[uid]

def _pet_push_state(g, uid, msg=None):
    mem = PETS_MEM.get(uid)
    if not mem:
        return
    st = _pet_stats(mem["row"]["type"], mem["row"]["level"])
    payload = {"pet": {"name": mem["row"]["name"], "type": mem["row"]["type"],
                       "icon": st["icon"], "level": mem["row"]["level"],
                       "exp": mem["row"]["exp"], "need": _pet_need(mem["row"]["level"]),
                       "active": bool(mem["row"]["active"]), "atk": round(st["atk"]),
                       "crit": round(st["crit"] * 100)}}
    if msg:
        payload["message"] = msg
    s = _sid(uid)
    if s:
        g["socketio"].emit("pet_state", payload, room=s)

def _pet_target(g, p, insts):
    best, bd = None, 1e9
    for m in insts.values():
        if not m["alive"]:
            continue
        d = math.hypot(m["x"] - p["x"], m["y"] - p["y"])
        if d > 320:
            continue
        score = d - (160 if m.get("target") == p["id"] else 0)
        if score < bd:
            bd, best = score, m
    return best

def _pet_tick(g):
    now = time.time()
    with g["STATE_LOCK"]:
        players = {q["id"]: (s, q) for s, q in g["connected_players"].items()}
    by_map = {}
    for uid, (sid, p) in players.items():
        mem = PETS_MEM.get(uid) or _ensure_pet(g, uid)
        if not mem or not mem["row"]["active"]:
            continue
        if mem["map"] != p["map"] or mem["x"] is None:
            mem["map"], mem["x"], mem["y"] = p["map"], p["x"], p["y"]
        st = _pet_stats(mem["row"]["type"], mem["row"]["level"])
        target = None
        if p["hp"] > 0 and p["map"] != "town":
            with g["STATE_LOCK"]:
                insts = dict(g["MONSTER_INSTANCES"].get(p["map"], {}))
            target = _pet_target(g, p, insts)
        tx, ty = (target["x"], target["y"]) if target else (p["x"], p["y"])
        d = math.hypot(tx - mem["x"], ty - mem["y"])
        if target and d <= 46:
            if now >= mem["cd_until"]:
                mem["cd_until"] = now + 1.6
                dmg, crit = g["roll_damage"](st["atk"], target["def"], 1.0, st["crit"])
                with g["STATE_LOCK"]:
                    snap = g["hit_monster"](target, {"id": uid}, dmg, now, threat_mult=0.5)
                    ser = g["serialize_monster"](target)
                g["socketio"].emit("monsters_update", {"map": p["map"], "monsters": [ser]}, room=p["map"])
                g["socketio"].emit("pet_fx", {"x": target["x"], "y": target["y"], "dmg": dmg,
                                              "crit": crit, "icon": st["icon"]}, room=p["map"])
                if snap:
                    g["distribute_kill"](snap, uid, p["username"])
        else:
            if d > 560:
                mem["x"], mem["y"] = tx + 20, ty + 14
            else:
                step = 95.0
                if d > 1:
                    mem["x"] += (tx - mem["x"]) / d * step
                    mem["y"] += (ty - mem["y"]) / d * step
            mem["x"] = g["clamp"](mem["x"], 20, 780)
            mem["y"] = g["clamp"](mem["y"], 20, 580)
        by_map.setdefault(p["map"], []).append(
            {"uid": uid, "x": round(mem["x"], 1), "y": round(mem["y"], 1),
             "icon": st["icon"], "name": mem["row"]["name"], "lv": mem["row"]["level"]})
    for map_name, pets in by_map.items():
        g["socketio"].emit("pets_update", {"pets": pets}, room=map_name)

def pet_loop():
    g = _G["g"]
    log.info("[ext2] Pet AI loop started")
    while True:
        time.sleep(0.6)
        try:
            _pet_tick(g)
        except Exception:
            log.exception("pet tick error")

# ================= Hooks: kill → pet exp / guild exp =================
def _wrap_award_kill(g):
    orig = g.get("award_kill")
    if not orig:
        return

    def wrapped(conn, uid, exp, gold, monster):
        res = orig(conn, uid, exp, gold, monster)
        if not res:
            return res
        try:  # 🐾 pet exp
            row = conn.execute("SELECT * FROM pets WHERE user_id=? AND active=1", (uid,)).fetchone()
            if row:
                lv, pexp = row["level"], row["exp"] + int(exp * 0.35)
                lvup = 0
                while lv < PET_MAX_LV and pexp >= _pet_need(lv):
                    pexp -= _pet_need(lv)
                    lv += 1
                    lvup += 1
                conn.execute("UPDATE pets SET level=?, exp=? WHERE id=?", (lv, pexp, row["id"]))
                if uid in PETS_MEM:
                    PETS_MEM[uid]["row"].update(level=lv, exp=pexp)
                s = _sid(uid)
                if s and (lvup or True):
                    g["socketio"].emit("pet_exp", {"gain": int(exp * 0.35), "level": lv,
                                                   "lvup": lvup, "need": _pet_need(lv)}, room=s)
                if lvup and lv >= 30:
                    g["socketio"].emit("system_message",
                                       {"message": f"🐾 เพทของ {res['user']['username']} ถึง Lv.{lv}!"})
        except Exception:
            log.exception("pet exp hook")
        try:  # 🛡️ guild exp
            gm = conn.execute("SELECT guild_id FROM guild_members WHERE user_id=?", (uid,)).fetchone()
            if gm:
                gd = conn.execute("SELECT * FROM guilds WHERE id=?", (gm["guild_id"],)).fetchone()
                if gd:
                    gexp = gd["exp"] + int(exp * 0.10)
                    lvl, need = gd["level"], gd["level"] * 3000
                    while gexp >= need and lvl < 20:
                        gexp -= need
                        lvl += 1
                        need = lvl * 3000
                        g["socketio"].emit("system_message",
                                           {"message": f"🛡️ กิลด์ {gd['name']} เลเวลอัพเป็น {lvl}!"})
                    conn.execute("UPDATE guilds SET exp=?, level=? WHERE id=?", (gexp, lvl, gd["id"]))
        except Exception:
            log.exception("guild exp hook")
        return res

    g["award_kill"] = wrapped

# ================= PvP =================
def _wrap_pvp_death(g):
    orig = g.get("handle_player_death")
    if not orig:
        log.warning("[ext2] ไม่พบ handle_player_death — PvP Rank ปิด")
        return

    def wrapped(sid, p, killer_name, pvp=False):
        orig(sid, p, killer_name, pvp)
        if not pvp:
            return
        try:
            _record_pvp(g, p, killer_name)
        except Exception:
            log.exception("pvp record")

    g["handle_player_death"] = wrapped

def _record_pvp(g, victim_p, killer_name):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with g["get_db"]() as conn:
        win = conn.execute("SELECT * FROM users WHERE username=?", (killer_name,)).fetchone()
        if not win or win["id"] == victim_p["id"]:
            return
        lose = g["get_user_by_id"](conn, victim_p["id"])
        if not lose:
            return
        ra, rb = win["pvp_points"], lose["pvp_points"]
        exp_a = 1 / (1 + 10 ** ((rb - ra) / 400.0))
        delta = max(6, int(30 * (1 - exp_a)) + 6)
        streak = win["pvp_streak"] + 1
        bonus = 5 * streak if streak >= 2 else 0
        wpts = ra + delta + bonus
        lpts = max(0, rb - (delta + 4))
        daily = ""
        if (win["pvp_last_win"] or "") != today:
            conn.execute("UPDATE users SET gold=gold+?, pvp_last_win=? WHERE id=?",
                         (PVP_DAILY_GOLD, today, win["id"]))
            daily = f" (🎁 ชนะแรกของวัน +{PVP_DAILY_GOLD} G)"
        conn.execute("""UPDATE users SET pvp_points=?, pvp_wins=pvp_wins+1, pvp_streak=?
                        WHERE id=?""", (wpts, streak, win["id"]))
        conn.execute("""UPDATE users SET pvp_points=?, pvp_losses=pvp_losses+1, pvp_streak=0
                        WHERE id=?""", (lpts, lose["id"]))
        win_username = win["username"]
        lose_username = lose["username"]
    title_old, title_new = _pvp_title(ra), _pvp_title(wpts)
    for uid, pts, extra in [(win["id"], wpts, f"+{delta + bonus}"),
                            (lose["id"], lpts, f"-{delta + 4}")]:
        s = _sid(uid)
        if s:
            g["socketio"].emit("pvp_rank", {"points": pts, "delta": extra,
                                            "title": _pvp_title(pts)}, room=s)
    io = g["socketio"]
    if title_new != title_old:
        io.emit("system_message", {
            "message": f"🏆 {win_username} ขึ้นยศ {title_new} (เรตติ้ง {wpts}) — ปราบ {lose_username}"
        })
    elif streak >= 3:
        io.emit("system_message", {
            "message": f"⚔️ {win_username} ชนะต่อเนื่อง {streak} ศึก! "
                       f"(ปราบ {lose_username}){daily}"
        })

# ================= HTTP =================
def _register_http(g):
    app, socketio = g["app"], g["socketio"]
    GD = g["GD"]

    @app.route("/ext/lumivara_ext2.js")
    def ext2_js():
        return Response(_EXT2_JS, mimetype="application/javascript")

    @app.after_request
    def ext2_inject(resp):
        try:
            if request.path == "/" and (resp.headers.get("Content-Type", "") or "").startswith("text/html"):
                body = resp.get_data(as_text=True)
                tag = '<script src="/ext/lumivara_ext2.js?v=' + V2 + '"></script>'
                if "</body>" in body and "lumivara_ext2.js" not in body:
                    resp.set_data(body.replace("</body>", tag + "</body>"))
        except Exception:
            pass
        return resp

    @app.route("/api/ext2/status")
    def ext2_status():
        return jsonify({"success": True, "ext2": V2,
                        "features": ["pet", "guild", "pvp_rank", "balance", "ui_inject"]})

    def _uid():
        return session.get("user_id")

    # ---------- PET ----------
    @app.route("/api/ext/pet/mine")
    def pet_mine():
        uid = _uid()
        if not uid:
            return jsonify({"success": False}), 401
        with g["get_db"]() as conn:
            row = conn.execute("SELECT * FROM pets WHERE user_id=?", (uid,)).fetchone()
            food = conn.execute("SELECT COALESCE(SUM(quantity),0) n FROM inventory WHERE user_id=? AND item_id=?",
                                (uid, PET_FOOD)).fetchone()["n"]
            eggs = conn.execute("SELECT item_id, quantity FROM inventory WHERE user_id=? AND item_id IN (620,621,622)",
                                (uid,)).fetchall()
            gold = g["get_user_by_id"](conn, uid)["gold"]
        pet = None
        if row:
            st = _pet_stats(row["type"], row["level"])
            pet = {"name": row["name"], "type": row["type"], "icon": st["icon"],
                   "level": row["level"], "exp": row["exp"], "need": _pet_need(row["level"]),
                   "active": bool(row["active"]), "atk": round(st["atk"]), "crit": round(st["crit"] * 100)}
        return jsonify({"success": True, "pet": pet, "food": food,
                        "eggs": [{"itemId": e["item_id"], "qty": e["quantity"]} for e in eggs], "gold": gold})

    @app.route("/api/ext/pet/buy", methods=["POST"])
    def pet_buy():
        uid = _uid()
        if not uid:
            return jsonify({"success": False}), 401
        iid = (request.json or {}).get("item_id")
        meta = GD.ITEMS.get(iid)
        if not meta or iid not in (PET_FOOD, *EGGS.keys()):
            return jsonify({"success": False, "message": "ไม่พบสินค้า"}), 404
        found = g["find_player_by_uid"](uid)
        if not found or found[1]["map"] != "town":
            return jsonify({"success": False, "message": "ต้องไปหา 🐾 เทรนเนอร์มิรูที่เมือง"}), 400
        npc = next((n for n in g["NPCS"].get("town", []) if n.get("id") == "npc_pet"), None)
        if npc and math.hypot(found[1]["x"] - npc["x"], found[1]["y"] - npc["y"]) > 110:
            return jsonify({"success": False, "message": "เดินเข้าใกล้เทรนเนอร์มิรูก่อน (คลิก NPC)"}), 400
        with g["get_db"]() as conn:
            u = g["get_user_by_id"](conn, uid)
            if u["gold"] < meta["price"]:
                return jsonify({"success": False, "message": "Gold ไม่พอ"}), 400
            conn.execute("UPDATE users SET gold=gold-? WHERE id=?", (meta["price"], uid))
            ex = conn.execute("SELECT id FROM inventory WHERE user_id=? AND item_id=? AND equipped=0",
                              (uid, iid)).fetchone()
            if ex:
                conn.execute("UPDATE inventory SET quantity=quantity+1 WHERE id=?", (ex["id"],))
            else:
                conn.execute("INSERT INTO inventory (user_id,item_id,quantity,equipped,enhance) VALUES (?,?,1,0,0)",
                             (uid, iid))
            u = g["get_user_by_id"](conn, uid)
        return jsonify({"success": True, "message": "ซื้อ " + meta["name"], "user": g["live_user"](u)})

    # ---------- GUILD ----------
    def _guild_of(conn, uid):
        gm = conn.execute("SELECT * FROM guild_members WHERE user_id=?", (uid,)).fetchone()
        if not gm:
            return None, None
        gd = conn.execute("SELECT * FROM guilds WHERE id=?", (gm["guild_id"],)).fetchone()
        return dict(gm), dict(gd) if gd else None

    @app.route("/api/guild/mine")
    def guild_mine():
        uid = _uid()
        if not uid:
            return jsonify({"success": False}), 401
        with g["get_db"]() as conn:
            gm, gd = _guild_of(conn, uid)
            if not gd:
                return jsonify({"success": True, "guild": None})
            members = conn.execute("""SELECT u.username, u.level, u.job, gm.role FROM guild_members gm
                                      JOIN users u ON u.id=gm.user_id WHERE gm.guild_id=? ORDER BY gm.role DESC""",
                                   (gd["id"],)).fetchall()
        return jsonify({"success": True, "guild": {**gd, "members": [dict(m) for m in members],
                                                   "my_role": gm["role"]}})

    @app.route("/api/guild/list")
    def guild_list():
        with g["get_db"]() as conn:
            rows = conn.execute("""SELECT g.id, g.name, g.level, COUNT(gm.user_id) members
                                   FROM guilds g LEFT JOIN guild_members gm ON gm.guild_id=g.id
                                   GROUP BY g.id ORDER BY g.level DESC LIMIT 20""").fetchall()
        return jsonify({"success": True, "guilds": [dict(r) for r in rows]})

    @app.route("/api/guild/create", methods=["POST"])
    def guild_create():
        uid = _uid()
        if not uid:
            return jsonify({"success": False}), 401
        name = ((request.json or {}).get("name") or "").strip()[:16]
        if len(name) < 2:
            return jsonify({"success": False, "message": "ชื่อกิลด์ต้องยาว 2-16 ตัว"}), 400
        with g["get_db"]() as conn:
            if conn.execute("SELECT 1 FROM guild_members WHERE user_id=?", (uid,)).fetchone():
                return jsonify({"success": False, "message": "คุณมีกิลด์อยู่แล้ว"}), 400
            u = g["get_user_by_id"](conn, uid)
            if u["level"] < GUILD_CREATE_LV:
                return jsonify({"success": False, "message": f"ต้อง Lv.{GUILD_CREATE_LV}+"}), 400
            if u["gold"] < GUILD_CREATE_GOLD:
                return jsonify({"success": False, "message": f"ต้องใช้ {GUILD_CREATE_GOLD} G"}), 400
            try:
                conn.execute("INSERT INTO guilds (name, leader_id) VALUES (?,?)", (name, uid))
                gid = conn.execute("SELECT last_insert_rowid() id").fetchone()["id"]
                conn.execute("INSERT INTO guild_members (guild_id,user_id,role) VALUES (?,?, 'leader')", (gid, uid))
                conn.execute("UPDATE users SET gold=gold-? WHERE id=?", (GUILD_CREATE_GOLD, uid))
            except sqlite3.IntegrityError:
                return jsonify({"success": False, "message": "ชื่อกิลด์นี้ถูกใช้แล้ว"}), 409
            u = g["get_user_by_id"](conn, uid)
            username = u["username"]
        socketio.emit("system_message", {"message": f"🛡️ กิลด์ '{name}' ก่อตั้งโดย {username}!"})
        return jsonify({"success": True, "message": f"ก่อตั้งกิลด์ {name}!", "user": g["live_user"](u)})

    @app.route("/api/guild/join", methods=["POST"])
    def guild_join():
        uid = _uid()
        if not uid:
            return jsonify({"success": False}), 401
        gid = (request.json or {}).get("guild_id")
        with g["get_db"]() as conn:
            if conn.execute("SELECT 1 FROM guild_members WHERE user_id=?", (uid,)).fetchone():
                return jsonify({"success": False, "message": "คุณมีกิลด์อยู่แล้ว"}), 400
            gd = conn.execute("SELECT * FROM guilds WHERE id=?", (gid,)).fetchone()
            if not gd:
                return jsonify({"success": False, "message": "ไม่พบกิลด์"}), 404
            n = conn.execute("SELECT COUNT(*) c FROM guild_members WHERE guild_id=?", (gid,)).fetchone()["c"]
            if n >= GUILD_CAP:
                return jsonify({"success": False, "message": "กิลด์เต็ม"}), 400
            conn.execute("INSERT INTO guild_members (guild_id,user_id) VALUES (?,?)", (gid, uid))
            username = g["get_user_by_id"](conn, uid)["username"]
            guild_name = gd["name"]
        socketio.emit("system_message", {
            "message": f"🛡️ {username} เข้าร่วมกิลด์ {guild_name}"
        })
        return jsonify({"success": True, "message": f"เข้ากิลด์ {guild_name} แล้ว!"})

    @app.route("/api/guild/leave", methods=["POST"])
    def guild_leave():
        uid = _uid()
        if not uid:
            return jsonify({"success": False}), 401
        with g["get_db"]() as conn:
            gm, gd = _guild_of(conn, uid)
            if not gd:
                return jsonify({"success": False, "message": "ไม่มีกิลด์"}), 400
            conn.execute("DELETE FROM guild_members WHERE user_id=?", (uid,))
            msg = f"ออกจากกิลด์ {gd['name']} แล้ว"
            if gm["role"] == "leader":
                conn.execute("DELETE FROM guilds WHERE id=?", (gd["id"],))
                msg = f"ยุบกิลด์ {gd['name']} แล้ว (หัวหน้าออก)"
                socketio.emit("system_message", {"message": f"🛡️ กิลด์ {gd['name']} ถูกยุบ"})
        return jsonify({"success": True, "message": msg})

    @app.route("/api/guild/kick", methods=["POST"])
    def guild_kick():
        uid = _uid()
        if not uid:
            return jsonify({"success": False}), 401
        target = ((request.json or {}).get("username") or "").strip()
        with g["get_db"]() as conn:
            gm, gd = _guild_of(conn, uid)
            if not gd or gm["role"] != "leader":
                return jsonify({"success": False, "message": "ต้องเป็นหัวหน้ากิลด์"}), 403
            tu = conn.execute("SELECT id FROM users WHERE username=?", (target,)).fetchone()
            if not tu:
                return jsonify({"success": False, "message": "ไม่พบผู้เล่น"}), 404
            tgm = conn.execute("SELECT * FROM guild_members WHERE user_id=?", (tu["id"],)).fetchone()
            if not tgm or tgm["guild_id"] != gd["id"]:
                return jsonify({"success": False, "message": "เขาไม่ได้อยู่กิลด์นี้"}), 400
            conn.execute("DELETE FROM guild_members WHERE user_id=?", (tu["id"],))
        return jsonify({"success": True, "message": f"เตะ {target} ออกจากกิลด์"})

    @app.route("/api/guild/donate", methods=["POST"])
    def guild_donate():
        uid = _uid()
        if not uid:
            return jsonify({"success": False}), 401
        amt = int((request.json or {}).get("amount") or 0)
        amt = max(100, min(100000, amt))
        with g["get_db"]() as conn:
            gm, gd = _guild_of(conn, uid)
            if not gd:
                return jsonify({"success": False, "message": "ไม่มีกิลด์"}), 400
            u = g["get_user_by_id"](conn, uid)
            if u["gold"] < amt:
                return jsonify({"success": False, "message": "Gold ไม่พอ"}), 400
            conn.execute("UPDATE users SET gold=gold-? WHERE id=?", (amt, uid))
            conn.execute("UPDATE guilds SET fund=fund+?, exp=exp+? WHERE id=?", (amt, amt // 10, gd["id"]))
            gd = conn.execute("SELECT * FROM guilds WHERE id=?", (gd["id"],)).fetchone()
            need = gd["level"] * 3000
            lvl, gexp = gd["level"], gd["exp"]
            while gexp >= need and lvl < 20:
                gexp -= need
                lvl += 1
                need = lvl * 3000
            conn.execute("UPDATE guilds SET level=?, exp=? WHERE id=?", (lvl, gexp, gd["id"]))
            u = g["get_user_by_id"](conn, uid)
        return jsonify({"success": True, "message": f"บริจาค {amt} G — กิลด์ Lv.{lvl} "
                                                    f"({gexp}/{need})", "user": g["live_user"](u)})

    @app.route("/api/guild/buy", methods=["POST"])
    def guild_buy():
        uid = _uid()
        if not uid:
            return jsonify({"success": False}), 401
        with g["get_db"]() as conn:
            gm, gd = _guild_of(conn, uid)
            if not gd:
                return jsonify({"success": False, "message": "ต้องมีกิลด์"}), 400
            if gd["level"] < 2:
                return jsonify({"success": False, "message": "กิลด์ต้อง Lv.2 ขึ้นไป"}), 400
            u = g["get_user_by_id"](conn, uid)
            if u["gold"] < 45:
                return jsonify({"success": False, "message": "Gold ไม่พอ"}), 400
            conn.execute("UPDATE users SET gold=gold-45 WHERE id=?", (uid,))
            ex = conn.execute("SELECT id FROM inventory WHERE user_id=? AND item_id=? AND equipped=0",
                              (uid, GUILD_POTION)).fetchone()
            if ex:
                conn.execute("UPDATE inventory SET quantity=quantity+1 WHERE id=?", (ex["id"],))
            else:
                conn.execute("INSERT INTO inventory (user_id,item_id,quantity,equipped,enhance) VALUES (?,?,1,0,0)",
                             (uid, GUILD_POTION))
            u = g["get_user_by_id"](conn, uid)
        return jsonify({"success": True, "message": "ซื้อ น้ำยากิลด์ สำเร็จ (ใช้จากกระเป๋าได้เลย)",
                        "user": g["live_user"](u)})

    TAG_CACHE = {}

    @app.route("/api/ext/presence")
    def ext_presence():
        uid = _uid()
        if not uid:
            return jsonify({"success": False}), 401
        found = g["find_player_by_uid"](uid)
        if not found:
            return jsonify({"success": True, "players": []})
        mymap = found[1]["map"]
        now = time.time()
        out = []
        with g["STATE_LOCK"]:
            for s, q in g["connected_players"].items():
                if q["map"] != mymap:
                    continue
                cu = TAG_CACHE.get(q["id"])
                if not cu or cu[1] < now:
                    with g["get_db"]() as conn:
                        row = conn.execute("""SELECT g.name FROM guild_members gm JOIN guilds g
                                              ON g.id=gm.guild_id WHERE gm.user_id=?""",
                                           (q["id"],)).fetchone()
                    cu = (row["name"] if row else None, now + 60)
                    TAG_CACHE[q["id"]] = cu
                out.append({"sid": s, "username": q["username"], "guild": cu[0], "level": q["level"]})
        return jsonify({"success": True, "players": out})

    # ---------- PVP ----------
    @app.route("/api/pvp/me")
    def pvp_me():
        uid = _uid()
        if not uid:
            return jsonify({"success": False}), 401
        with g["get_db"]() as conn:
            u = g["get_user_by_id"](conn, uid)
        return jsonify({"success": True, "points": u["pvp_points"], "wins": u["pvp_wins"],
                        "losses": u["pvp_losses"], "streak": u["pvp_streak"],
                        "title": _pvp_title(u["pvp_points"])})

    @app.route("/api/pvp/rank")
    def pvp_rank():
        with g["get_db"]() as conn:
            rows = conn.execute("""SELECT username, level, job, pvp_points, pvp_wins, pvp_losses
                                   FROM users WHERE is_banned=0 ORDER BY pvp_points DESC LIMIT 10""").fetchall()
        return jsonify({"success": True, "rank": [dict(r) for r in rows]})

    @app.route("/api/admin/pvp_reset", methods=["POST"])
    def pvp_reset():
        uid = _uid()
        with g["get_db"]() as conn:
            admin = g["get_user_by_id"](conn, uid) if uid else None
            if not admin or not admin["is_admin"]:
                return jsonify({"success": False, "message": "ต้องเป็นแอดมิน"}), 403
            conn.execute("UPDATE users SET pvp_points=?, pvp_streak=0", (PVP_START,))
        socketio.emit("system_message", {"message": "🏆 เปิดซีซัน PvP ใหม่ — Rating ทุกคนกลับเป็น 1000"})
        return jsonify({"success": True, "message": "รีเซ็ตซีซันแล้ว"})

# ================= SOCKET (pet actions + guild chat) =================
def _register_socket(g):
    socketio, get_db, GD = g["socketio"], g["get_db"], g["GD"]
    rate_ok = g.get("rate_ok")

    @socketio.on("pet_hatch")
    def pet_hatch(data):
        uid = session.get("user_id")
        if not uid:
            return
        iid = (data or {}).get("inventory_id")
        with get_db() as conn:
            row = conn.execute("SELECT * FROM inventory WHERE id=? AND user_id=?", (iid, uid)).fetchone()
            if not row:
                return _notice(uid, "ไม่พบไข่")
            if row["item_id"] not in EGGS:
                return _notice(uid, "นี่ไม่ใช่ไข่เพท")
            if conn.execute("SELECT 1 FROM pets WHERE user_id=?", (uid,)).fetchone():
                return _notice(uid, "มีเพทอยู่แล้ว — ปล่อยตัวเดิมก่อน (ปุ่มปล่อย)")
            ptype = EGGS[row["item_id"]][0]
            if row["quantity"] > 1:
                conn.execute("UPDATE inventory SET quantity=quantity-1 WHERE id=?", (row["id"],))
            else:
                conn.execute("DELETE FROM inventory WHERE id=?", (row["id"],))
            conn.execute("INSERT INTO pets (user_id,name,type) VALUES (?,?,?)",
                         (uid, PET_TYPES[ptype]["name"], ptype))
        PETS_MEM.pop(uid, None)
        _ensure_pet(g, uid)
        _pet_push_state(g, uid, f"ฟักไข่สำเร็จ! {PET_TYPES[ptype]['name']} เกิดแล้ว 🎉")

    @socketio.on("pet_feed")
    def pet_feed(data=None):
        uid = session.get("user_id")
        if not uid:
            return
        mem = PETS_MEM.get(uid) or _ensure_pet(g, uid)
        if not mem:
            return _notice(uid, "ยังไม่มีเพท")
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM inventory WHERE user_id=? AND item_id=? AND equipped=0",
                                (uid, PET_FOOD)).fetchall()
            if sum(r["quantity"] for r in rows) < 1:
                return _notice(uid, "ไม่มี 🍖 ขนมปังสัตว์เลี้ยง (ซื้อที่เทรนเนอร์มิรู)")
            need = 1
            for r in rows:
                if need <= 0:
                    break
                take = min(need, r["quantity"])
                if take >= r["quantity"]:
                    conn.execute("DELETE FROM inventory WHERE id=?", (r["id"],))
                else:
                    conn.execute("UPDATE inventory SET quantity=quantity-? WHERE id=?", (take, r["id"]))
                need -= take
            lv, exp = mem["row"]["level"], mem["row"]["exp"] + 120
            lvup = 0
            while lv < PET_MAX_LV and exp >= _pet_need(lv):
                exp -= _pet_need(lv)
                lv += 1
                lvup += 1
            conn.execute("UPDATE pets SET level=?, exp=? WHERE id=?", (lv, exp, mem["row"]["id"]))
        mem["row"].update(level=lv, exp=exp)
        _pet_push_state(g, uid, f"🍖 อร่อย! +120 EXP" + (f" • LEVEL UP → {lv}!" if lvup else ""))
        if uid in PETS_MEM:
            find_sid = _sid(uid)
            if find_sid:
                socketio.emit("ext2_notice", {"message": "🐾 ให้อาหารสำเร็จ"}, room=find_sid)

    @socketio.on("pet_rename")
    def pet_rename(data):
        uid = session.get("user_id")
        if not uid:
            return
        name = ((data or {}).get("name") or "").strip()[:14]
        if len(name) < 2:
            return _notice(uid, "ชื่อต้องยาว 2-14 ตัว")
        with get_db() as conn:
            conn.execute("UPDATE pets SET name=? WHERE user_id=?", (name, uid))
        if uid in PETS_MEM:
            PETS_MEM[uid]["row"]["name"] = name
        _pet_push_state(g, uid, f"เปลี่ยนชื่อเพทเป็น {name}")

    @socketio.on("pet_toggle")
    def pet_toggle(data=None):
        uid = session.get("user_id")
        if not uid:
            return
        mem = PETS_MEM.get(uid) or _ensure_pet(g, uid)
        if not mem:
            return
        new = 0 if mem["row"]["active"] else 1
        with get_db() as conn:
            conn.execute("UPDATE pets SET active=? WHERE user_id=?", (new, uid))
        mem["row"]["active"] = new
        _pet_push_state(g, uid, "เพทออกมาช่วยล่าแล้ว 🐾" if new else "เพทเข้าโพยังพักผ่อน 😴")

    @socketio.on("pet_release")
    def pet_release(data=None):
        uid = session.get("user_id")
        if not uid:
            return
        with get_db() as conn:
            conn.execute("DELETE FROM pets WHERE user_id=?", (uid,))
        PETS_MEM.pop(uid, None)
        _notice(uid, "ลาก่อนนะ... เพทกลับสู่ธรรมชาติ 🌿")

    @socketio.on("guild_chat")
    def guild_chat(data):
        uid = session.get("user_id")
        if not uid:
            return
        if rate_ok and not rate_ok(request.sid, "gchat", 0.8):
            return
        msg = ((data or {}).get("message") or "").strip()[:200]
        if not msg:
            return
        with get_db() as conn:
            gm = conn.execute("""SELECT gm.guild_id, g.name, u.username FROM guild_members gm
                                 JOIN guilds g ON g.id=gm.guild_id JOIN users u ON u.id=gm.user_id
                                 WHERE gm.user_id=?""", (uid,)).fetchone()
            if not gm:
                return _notice(uid, "คุณไม่มีกิลด์")
            members = conn.execute("SELECT user_id FROM guild_members WHERE guild_id=?",
                                   (gm["guild_id"],)).fetchall()
        payload = {"username": gm["username"], "message": msg, "guild": gm["name"]}
        for m in members:
            s = _sid(m["user_id"])
            if s:
                socketio.emit("guild_chat", payload, room=s)

# ================= ไอเทม/NPC/DROP ของ v2 =================
def _extend_content(g):
    IT = g["GD"].ITEMS
    IT[PET_FOOD] = {"name": "ขนมปังสัตว์เลี้ยง", "type": "material", "price": 60, "sell_price": 25}
    for iid, (ptype, name, price) in EGGS.items():
        IT[iid] = {"name": name, "type": "pet_egg", "price": price, "sell_price": price // 2}
    IT[GUILD_POTION] = {"name": "น้ำยากิลด์", "type": "potion", "price": 45, "sell_price": 18,
                        "heal_pct": 0.60, "mana_pct": 0.60}
    DT = g["DROP_TABLES"]
    for mid in (52,):                                # ลูกมังกรดรอปไข่มังกร
        DT[mid] = DT.get(mid, []) + [(622, 0.08)]
    for mid in (1, 2, 3, 4):                         # มอนแมพแรกดรอปอาหารเพท
        DT[mid] = DT.get(mid, []) + [(PET_FOOD, 0.05)]
    lst = g["NPCS"].setdefault("town", [])
    if not any(n.get("id") == "npc_pet" for n in lst):
        lst.append({"id": "npc_pet", "name": "เทรนเนอร์มิรู (เพท)", "sprite": "🐾",
                    "x": 520.0, "y": 140.0, "type": "pet"})

# ================= Client JS (minimal stub) =================
_EXT2_JS = r"""
/* LumiVara Ext2 Client v2.0 — minimal stub (replace with full UI later) */
console.log("[ext2] SYSTEMS PACK v2.0 loaded (Pet / Guild / PvP Rank / Balance)");
// TODO: implement full pet panel, guild UI, pvp rank display, etc.
"""

# ================= MAIN =================
def install(g):
    _G["g"] = g
    _apply_balance(g)
    _extend_content(g)
    _wrap_pvp_death(g)
    _wrap_award_kill(g)
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
    _register_http(g)
    _register_socket(g)
    threading.Thread(target=pet_loop, daemon=True).start()
    log.info("[ext2] SYSTEMS PACK v%s โหลดสำเร็จ — Pet/Guild/PvP/Balance | %d balance patches",
             V2, len(BALANCE_LOG))