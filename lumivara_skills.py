# -*- coding: utf-8 -*-
"""
lumivara_skills.py — Skill System Upgrade v1.0 (สำหรับ Lumivara Online v5.1.1)
- สกิลตามสายอาชีพ: อาชีพขั้น 2 ใช้สกิลของอาชีพขั้นก่อนหน้าได้ (Knight ใช้ Bash ได้)
- ปลดล็อกตามเงื่อนไข: สายอาชีพ / เลเวล / สกิลก่อนหน้า / ยอดสังหาร / เควส / ค่าเรียน
- สกิลค่าเรียน 0 G ปลดล็อกอัตโนมัติเมื่อผ่านเงื่อนไข
- ประเภท single / aoe (รอบตัว หรือเล็งพื้นที่) / heal / buff
  + multi-hit, stun, DoT, lifesteal, ฮีล/บัฟผู้เล่นรอบตัว
- ส่ง event "skill_fx" ให้ client วาดเอฟเฟกต์ทุกคนในแมพ
- แก้บั๊กเควสที่ต้องฆ่า 1 ตัว (เควสบอส) ซึ่งเดิมไม่เปลี่ยนเป็น done
ติดตั้ง (app.py ส่วน START หลัง EXT, ก่อน spawn_all_monsters):
    import lumivara_skills
    lumivara_skills.install(globals())
"""
import math
import time
import threading
import logging

from flask import request, jsonify

log = logging.getLogger("lumivara.skills")
_G = {}
_INSTALLED = False

JOB_TH = {"All": "พื้นฐาน", "Novice": "โนวิซ", "Swordsman": "นักดาบ", "Knight": "อัศวิน",
          "Mage": "นักเวท", "Wizard": "พ่อมด", "Archer": "นักธนู", "Hunter": "นักล่า",
          "Thief": "โจร", "Assassin": "นักฆ่า", "Acolyte": "นักบวช", "Priest": "นักบวชชั้นสูง"}
LINEAGE, JOB_TIER, GROUP_ORDER = {}, {}, []


def S(name, job, stype, mp, cd, *, lv, gold=0, req=(), kills=0, quest=None,
      mult=1.0, hits=1, rng=180, radius=160, max_t=6, ground=False, stun=0.0, dot=None,
      heal=0.0, party=0, stat="atk", buff=1.0, dur=20, lifesteal=0.0, shake_delay=0.0,
      fx="slash_gold", color="#ffd166", icon="⚔️", desc=""):
    return {"name": name, "job": job, "type": stype, "mp": mp, "cd": cd, "lv": lv, "gold": gold,
            "req": tuple(req), "kills": kills, "quest": quest, "mult": mult, "hits": hits,
            "rng": rng, "radius": radius, "max_t": max_t, "ground": ground, "stun": stun,
            "dot": {"pct": dot[0], "sec": dot[1]} if dot else None,
            "heal": heal, "party": party, "stat": stat, "buff_mult": buff, "dur": dur,
            "lifesteal": lifesteal, "shake_delay": shake_delay,
            "fx": fx, "color": color, "icon": icon, "desc": desc}


SKILL_TREE = {
    # ---------- พื้นฐาน (ทุกอาชีพ) ----------
    "power_strike": S("ฟันพลัง", "All", "single", 8, 3, lv=1, mult=1.8, rng=150,
                      fx="slash_gold", color="#ffd166", icon="⚔️", desc="ฟันอย่างแรงด้วยพลังทั้งหมด"),
    "heal": S("ฟื้นฟู", "All", "heal", 14, 10, lv=3, gold=100, heal=0.35,
              fx="heal_ring", color="#6dff8e", icon="💚", desc="ฟื้นฟู HP ตัวเอง 35%"),
    # ---------- Swordsman → Knight ----------
    "bash": S("ทุบสกัล", "Swordsman", "single", 10, 4, lv=10, mult=2.2, rng=160, stun=1.0,
              fx="bash_impact", color="#ff9f43", icon="🔨", desc="ทุบอย่างแรงจนศัตรูมึนงง 1 วินาที"),
    "magnum": S("แม็กนัมเบรก", "Swordsman", "aoe", 20, 8, lv=14, gold=600, req=["bash"],
                mult=1.5, radius=170, max_t=7, dot=(0.15, 3), shake_delay=0.2,
                fx="magnum_break", color="#ff5a1f", icon="🔥", desc="ระเบิดเปลวไฟรอบตัว เผาไหม้ต่อเนื่อง 3 วินาที"),
    "brandish": S("แบรนดิช", "Knight", "single", 24, 6, lv=30, mult=1.5, hits=2, rng=180,
                  fx="brandish", color="#9fd8ff", icon="🔱", desc="แทงหอกสองครั้งติดด้วยความเร็วสูง"),
    "endure": S("ต้านทาน", "Knight", "buff", 18, 20, lv=32, gold=2000, stat="def", buff=1.35, dur=20,
                fx="endure", color="#ffcf6b", icon="🛡️", desc="เพิ่ม DEF 35% เป็นเวลา 20 วินาที"),
    "bowling_bash": S("โบว์ลิ่งแบช", "Knight", "aoe", 34, 12, lv=38, gold=6000, req=["brandish"], kills=300,
                      mult=2.6, radius=180, max_t=8, stun=1.5, shake_delay=0.25,
                      fx="bowling_bash", color="#ffb347", icon="💥", desc="กระแทกพื้นสร้างคลื่นกระแทก ศัตรูรอบตัวมึนงง"),
    # ---------- Mage → Wizard ----------
    "frost_bolt": S("ศรน้ำแข็ง", "Mage", "single", 12, 4, lv=10, mult=2.0, rng=220, stun=1.5,
                    fx="frost", color="#7ad7ff", icon="❄️", desc="ยิงศรน้ำแข็งแช่แข็งเป้าหมาย 1.5 วินาที"),
    "fire_blast": S("ระเบิดเพลิง", "Mage", "aoe", 22, 7, lv=14, gold=600, req=["frost_bolt"],
                    mult=1.7, radius=150, max_t=6, rng=240, ground=True, dot=(0.12, 3), shake_delay=0.3,
                    fx="fire_burst", color="#ff7b00", icon="🔥", desc="ขว้างลูกไฟระเบิดเป็นวง เผาไหม้ต่อเนื่อง"),
    "jupitel": S("จูปิเตอร์ธันเดอร์", "Wizard", "single", 25, 5, lv=30, mult=1.0, hits=3, rng=240, stun=0.6,
                 fx="lightning", color="#9fd8ff", icon="⚡", desc="สายฟ้าฟาดต่อเนื่อง 3 ครั้ง"),
    "meteor": S("อุกกาบาต", "Wizard", "aoe", 40, 12, lv=35, gold=3000, req=["jupitel"],
                mult=2.2, radius=190, max_t=8, rng=260, ground=True, stun=1.0, dot=(0.15, 3), shake_delay=0.8,
                fx="meteor", color="#ff6a00", icon="☄️", desc="เรียกอุกกาบาตถล่มพื้นที่ เผาไหม้และมึนงง"),
    "storm_gust": S("พายุหิมะ", "Wizard", "aoe", 48, 15, lv=42, gold=9000, req=["meteor"], quest=5,
                    mult=1.1, hits=2, radius=210, max_t=10, rng=260, ground=True, stun=2.0, shake_delay=0.35,
                    fx="blizzard", color="#b8f0ff", icon="🌨️", desc="พายุหิมะโหมกระหน่ำ แช่แข็งทั้งพื้นที่ 2 วินาที"),
    # ---------- Archer → Hunter ----------
    "double_strafe": S("ศรคู่", "Archer", "single", 12, 4, lv=10, mult=1.2, hits=2, rng=280,
                       fx="arrow_double", color="#c8ff7a", icon="🏹", desc="ยิงลูกศรสองดอกติดกัน"),
    "arrow_rain": S("ฝนศร", "Archer", "aoe", 20, 7, lv=14, gold=600, req=["double_strafe"],
                    mult=1.5, radius=150, max_t=6, rng=280, ground=True,
                    fx="arrow_rain", color="#a8ff60", icon="🌧️", desc="โปรยลูกศรนับสิบลงพื้นที่เป้าหมาย"),
    "blitz_beat": S("บลิทซ์บีท", "Hunter", "aoe", 26, 8, lv=30, mult=1.8, radius=130, max_t=5, rng=300, ground=True,
                    fx="falcon", color="#ffe08a", icon="🦅", desc="ส่งเหยี่ยวคู่ใจโฉบจู่โจมกลุ่มศัตรู"),
    "focus_aim": S("เล็งแม่น", "Hunter", "buff", 15, 18, lv=32, gold=2000, stat="atk", buff=1.35, dur=20,
                   fx="aura_green", color="#7dff9a", icon="🎯", desc="เพิ่ม ATK 35% เป็นเวลา 20 วินาที"),
    "sharp_shoot": S("ชาร์ปชูต", "Hunter", "single", 30, 9, lv=40, gold=7000, req=["focus_aim"], kills=300,
                     mult=4.0, rng=340,
                     fx="piercing", color="#e6ffb3", icon="💫", desc="ยิงศรทะลวงพลังสูงสุดจากระยะไกล"),
    # ---------- Thief → Assassin ----------
    "sonic_blow": S("โซนิคโบลว์", "Thief", "single", 16, 5, lv=10, mult=0.75, hits=4, rng=140,
                    fx="sonic", color="#ff4d6d", icon="🗡️", desc="ฟันรัว 4 ครั้งในพริบตา"),
    "envenom": S("พิษร้าย", "Thief", "single", 14, 6, lv=14, gold=600, req=["sonic_blow"],
                 mult=1.3, rng=150, dot=(0.25, 6),
                 fx="poison", color="#9dff57", icon="☠️", desc="ฟันอาบพิษ ดาเมจต่อเนื่อง 6 วินาที"),
    "grimtooth": S("กริมทูธ", "Assassin", "single", 22, 6, lv=30, mult=3.0, rng=200,
                   fx="shadow_spike", color="#9b5cff", icon="🌑", desc="หนามเงาพุ่งจากพื้นไปแทงเป้าหมาย"),
    "cloak": S("ล่องหน", "Assassin", "buff", 18, 20, lv=32, gold=2000, stat="atk", buff=1.3, dur=20,
               fx="shadow_aura", color="#7b4dff", icon="👤", desc="กลืนเข้ากับเงา เพิ่ม ATK 30% เป็นเวลา 20 วินาที"),
    "meteor_assault": S("มีทิเออร์แอสซอลต์", "Assassin", "aoe", 36, 11, lv=40, gold=7000, req=["grimtooth"],
                        kills=300, mult=2.6, radius=160, max_t=8, stun=0.8, lifesteal=0.10, shake_delay=0.2,
                        fx="shadow_burst", color="#b06cff", icon="🌪️", desc="ระเบิดเงามืดรอบตัว ดูดเลือด 10% ของดาเมจ"),
    # ---------- Acolyte → Priest ----------
    "heal_plus": S("ฮีลใหญ่", "Acolyte", "heal", 20, 9, lv=10, heal=0.55, party=140,
                   fx="holy_heal", color="#fff3a0", icon="✨", desc="ฟื้นฟู HP 55% ให้ตัวเองและผู้เล่นรอบตัว"),
    "bless": S("อวยพร", "Acolyte", "buff", 15, 18, lv=12, gold=600, stat="atk", buff=1.3, dur=20, party=160,
               fx="bless", color="#ffe680", icon="🙏", desc="เพิ่ม ATK 30% ให้ตัวเองและผู้เล่นรอบตัว"),
    "holy_light": S("แสงศักดิ์สิทธิ์", "Acolyte", "single", 18, 5, lv=16, gold=1200, req=["bless"],
                    mult=2.2, rng=240,
                    fx="holy_light", color="#fff6c2", icon="☀️", desc="เสาแสงศักดิ์สิทธิ์ผ่าลงใส่เป้าหมาย"),
    "magnificat": S("มักนิฟิแคท", "Priest", "heal", 30, 12, lv=30, heal=0.7, party=200,
                    fx="magnificat", color="#ffffff", icon="🕊️", desc="วงเวทฟื้นฟู HP 70% ทั้งกลุ่ม"),
    "kyrie": S("คีรีเอเลซอน", "Priest", "buff", 24, 20, lv=33, gold=2500, stat="def", buff=1.5, dur=20, party=160,
               fx="kyrie", color="#8fd3ff", icon="🔰", desc="โล่ศักดิ์สิทธิ์เพิ่ม DEF 50% ทั้งกลุ่ม"),
    "magnus": S("แม็กนัสเอ็กซอร์ซิสมัส", "Priest", "aoe", 50, 16, lv=42, gold=9000, req=["holy_light"], quest=5,
                mult=1.0, hits=3, radius=200, max_t=10, rng=260, ground=True, shake_delay=0.45,
                fx="magnus", color="#fff1a8", icon="✝️", desc="วงเวทกางเขนชำระล้างศัตรู 3 ระลอก"),
}


# ================= helpers =================
def _build_lineage(jobs):
    parent = {}
    for j, d in jobs.items():
        for child in d.get("advance", {}):
            parent[child] = j
    out = {}
    for j in jobs:
        chain, cur = [], j
        while cur:
            chain.insert(0, cur)
            cur = parent.get(cur)
        out[j] = chain
    return out


def _group_order(jobs):
    order = ["All"]
    for j, d in jobs.items():
        if d["tier"] == 1:
            order.append(j)
            order.extend(d.get("advance", {}).keys())
    return order


def _job_allows(job, skill_job):
    return skill_job == "All" or skill_job in LINEAGE.get(job, [job])


def _compat(s):
    """รูปแบบเดียวกับ GD.SKILLS เดิม (ให้ /api/skills และโค้ดเก่ายังอ่านได้)"""
    d = {"name": s["name"], "job": s["job"], "type": s["type"], "mp": s["mp"], "cd": s["cd"]}
    if s["type"] == "heal":
        d["heal_pct"] = s["heal"]
    elif s["type"] == "buff":
        d.update(mult=s["buff_mult"], stat=s["stat"], duration=s["dur"])
    else:
        d.update(mult=s["mult"], range=s["rng"], radius=s["radius"], max_targets=s["max_t"])
    if s["stun"]:
        d["stun"] = s["stun"]
    return d


def _c(label, ok):
    return {"label": label, "ok": bool(ok)}


def _owned(conn, uid):
    return {r["skill_id"] for r in conn.execute("SELECT skill_id FROM user_skills WHERE user_id=?", (uid,))}


def _conditions(conn, row, sk_id, owned):
    s = SKILL_TREE[sk_id]
    line = LINEAGE.get(row["job"], [row["job"]])
    out = []
    if s["job"] != "All":
        out.append(_c(f"สายอาชีพ{JOB_TH.get(s['job'], s['job'])}", s["job"] in line))
    out.append(_c(f"เลเวล {s['lv']}+ (ตอนนี้ {row['level']})", row["level"] >= s["lv"]))
    for r in s["req"]:
        out.append(_c(f"ปลดล็อก “{SKILL_TREE[r]['name']}” ก่อน", r in owned))
    if s["kills"]:
        k = row["kills"] or 0
        out.append(_c(f"สังหารมอนสเตอร์ {s['kills']:,} ตัว ({k:,})", k >= s["kills"]))
    if s["quest"]:
        q = _G["GD"].QUESTS.get(s["quest"], {})
        st = conn.execute("SELECT status FROM user_quests WHERE user_id=? AND quest_id=?",
                          (row["id"], s["quest"])).fetchone()
        out.append(_c(f"สำเร็จเควส “{q.get('name', s['quest'])}”",
                      st is not None and st["status"] in ("done", "claimed")))
    if s["gold"]:
        out.append(_c(f"ค่าเรียน {s['gold']:,} G (มี {row['gold']:,})", row["gold"] >= s["gold"]))
    return out


def _auto_grant(conn, row, owned):
    """สกิลฟรีที่ผ่านเงื่อนไขครบ → ปลดล็อกให้อัตโนมัติ"""
    new = []
    for sk_id, s in SKILL_TREE.items():
        if sk_id in owned or s["gold"] > 0:
            continue
        if all(c["ok"] for c in _conditions(conn, row, sk_id, owned)):
            conn.execute("INSERT OR IGNORE INTO user_skills (user_id, skill_id) VALUES (?,?)", (row["id"], sk_id))
            owned.add(sk_id)
            new.append(sk_id)
    return new


def _cache_owned(uid, owned):
    with _G["STATE_LOCK"]:
        for q in _G["connected_players"].values():
            if q["id"] == uid:
                q["skills_owned"] = set(owned)


def _load_owned(uid):
    G = _G
    with G["get_db"]() as conn:
        row = G["get_user_by_id"](conn, uid)
        if row is None:
            return set()
        owned = _owned(conn, uid)
        _auto_grant(conn, row, owned)
    _cache_owned(uid, owned)
    return owned


def _public(sk_id, s, conds, owned):
    unlocked = sk_id in owned
    return {"id": sk_id, "name": s["name"], "icon": s["icon"], "desc": s["desc"], "job": s["job"],
            "tier": JOB_TIER.get(s["job"], 0), "type": s["type"], "ground": s["ground"],
            "mp": s["mp"], "cd": s["cd"], "lv": s["lv"], "gold": s["gold"],
            "fx": s["fx"], "color": s["color"], "mult": s["mult"], "hits": s["hits"],
            "range": s["rng"], "radius": s["radius"], "max_t": s["max_t"], "stun": s["stun"],
            "dot": s["dot"], "heal": s["heal"], "party": s["party"], "stat": s["stat"],
            "buff_mult": s["buff_mult"], "dur": s["dur"], "lifesteal": s["lifesteal"],
            "unlocked": unlocked, "conditions": [] if unlocked else conds,
            "can_unlock": (not unlocked) and all(c["ok"] for c in conds)}


# ================= [FIX] เควสที่ต้องฆ่า 1 ตัว =================
def _update_quest_progress(conn, user_id, monster_id):
    for qid, q in _G["GD"].QUESTS.items():
        if q["target_monster"] != monster_id:
            continue
        row = conn.execute("SELECT * FROM user_quests WHERE user_id=? AND quest_id=?", (user_id, qid)).fetchone()
        if row is None:
            status = "done" if q["target_count"] <= 1 else "active"
            conn.execute("INSERT INTO user_quests (user_id, quest_id, progress, status) VALUES (?,?,1,?)",
                         (user_id, qid, status))
        elif row["status"] == "active":
            prog = row["progress"] + 1
            conn.execute("UPDATE user_quests SET progress=?, status=? WHERE id=?",
                         (prog, "done" if prog >= q["target_count"] else "active", row["id"]))


def _init_db():
    with _G["get_db"]() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS user_skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                skill_id TEXT NOT NULL,
                unlocked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, skill_id))""")
        # ซ่อมเควสที่ค้าง active ทั้งที่ทำครบแล้ว (จากบั๊กเดิม)
        for qid, q in _G["GD"].QUESTS.items():
            conn.execute("UPDATE user_quests SET status='done' WHERE quest_id=? AND status='active' AND progress>=?",
                         (qid, q["target_count"]))


# ================= REST =================
def _route_tree():
    G = _G
    uid, err = G["authorize"]()
    if err:
        return err
    with G["get_db"]() as conn:
        row = G["get_user_by_id"](conn, uid)
        if row is None:
            return jsonify({"success": False, "message": "ไม่พบผู้เล่น"}), 404
        owned = _owned(conn, uid)
        new = _auto_grant(conn, row, owned)
        skills = [_public(k, s, _conditions(conn, row, k, owned), owned) for k, s in SKILL_TREE.items()]
    _cache_owned(uid, owned)
    line = LINEAGE.get(row["job"], [row["job"]])
    found = G["find_player_by_uid"](uid)
    mp = found[1]["mp"] if found else row["mp"]
    groups = [{"job": j, "label": JOB_TH.get(j, j), "tier": JOB_TIER.get(j, 0),
               "mine": j == "All" or j in line} for j in GROUP_ORDER]
    return jsonify({"success": True, "new": new, "groups": groups, "skills": skills,
                    "me": {"username": row["username"], "job": row["job"],
                           "job_label": JOB_TH.get(row["job"], row["job"]), "level": row["level"],
                           "gold": row["gold"], "kills": row["kills"] or 0,
                           "mp": mp, "max_mp": row["max_mp"], "lineage": line}})


def _route_learn():
    G = _G
    uid, err = G["authorize"]()
    if err:
        return err
    sk_id = str((request.json or {}).get("skill_id") or "")
    s = SKILL_TREE.get(sk_id)
    if s is None:
        return jsonify({"success": False, "message": "ไม่พบสกิล"}), 404
    with G["get_db"]() as conn:
        row = G["get_user_by_id"](conn, uid)
        owned = _owned(conn, uid)
        if sk_id in owned:
            return jsonify({"success": False, "message": "ปลดล็อกสกิลนี้แล้ว"}), 400
        fails = [c["label"] for c in _conditions(conn, row, sk_id, owned) if not c["ok"]]
        if fails:
            return jsonify({"success": False, "message": "เงื่อนไขไม่ครบ: " + " • ".join(fails)}), 400
        ins = conn.execute("INSERT OR IGNORE INTO user_skills (user_id, skill_id) VALUES (?,?)", (uid, sk_id))
        if ins.rowcount == 0:
            return jsonify({"success": False, "message": "ปลดล็อกสกิลนี้แล้ว"}), 400
        if s["gold"]:
            cur = conn.execute("UPDATE users SET gold=gold-? WHERE id=? AND gold>=?", (s["gold"], uid, s["gold"]))
            if cur.rowcount == 0:
                conn.execute("DELETE FROM user_skills WHERE user_id=? AND skill_id=?", (uid, sk_id))
                return jsonify({"success": False, "message": "ทองไม่พอ"}), 400
        owned.add(sk_id)
        row = G["get_user_by_id"](conn, uid)
    _cache_owned(uid, owned)
    sio, sid = G["socketio"], G["find_sid_by_uid"](uid)
    if sid:
        sio.emit("gold_update", {"gold": row["gold"]}, room=sid)
        sio.emit("skill_unlocked", {"skill_id": sk_id, "name": s["name"]}, room=sid)
    if JOB_TIER.get(s["job"], 0) >= 2:
        sio.emit("system_message", {"message": f"🌟 {row['username']} ปลดล็อกสกิลขั้นสูง {s['icon']} {s['name']}!"})
    return jsonify({"success": True, "user": G["live_user"](row),
                    "skill": {"id": sk_id, "name": s["name"], "color": s["color"], "icon": s["icon"]}})


# ================= Socket: use_skill (แทนที่ของเดิม) =================
def _party(p, sid, radius):
    out = [(sid, p)]
    if radius > 0:
        for s2, q in _G["connected_players"].items():
            if (s2 != sid and q["id"] != p["id"] and q["map"] == p["map"] and q["hp"] > 0
                    and math.hypot(q["x"] - p["x"], q["y"] - p["y"]) <= radius):
                out.append((s2, q))
    return out


def _ally(s2, q, amt=0):
    return {"sid": s2, "x": round(q["x"], 1), "y": round(q["y"], 1), "amt": amt, "hp": q["hp"], "mp": q["mp"]}


def _do_heal(p, sid, s, res):
    for s2, q in _party(p, sid, s["party"]):
        before = q["hp"]
        q["hp"] = min(q["max_hp"], q["hp"] + int(q["max_hp"] * s["heal"]))
        res["allies"].append(_ally(s2, q, q["hp"] - before))
    res["heal"] = res["allies"][0]["amt"]


def _do_buff(p, sid, s, res, now):
    for s2, q in _party(p, sid, s["party"]):
        q.setdefault("buffs", {})[s["stat"]] = {"mult": s["buff_mult"], "until": now + s["dur"]}
        res["allies"].append(_ally(s2, q))
    res["buff"] = {"stat": s["stat"], "mult": s["buff_mult"], "duration": s["dur"]}


def _do_attack(p, s, res, now, req_mid):
    G = _G
    insts = G["MONSTER_INSTANCES"].get(p["map"], {})
    px, py = p["x"], p["y"]

    def ok(m):
        return m is not None and m["alive"] and now >= m.get("spawn_until", 0)

    def anchor(rng):
        m = G["find_monster"](p["map"], req_mid) if req_mid is not None else None
        if ok(m) and math.hypot(m["x"] - px, m["y"] - py) <= rng:
            return m
        best, bd = None, rng                        # ไม่ได้เล็ง/เล็งไม่ได้ → เลือกตัวใกล้สุด
        for m in insts.values():
            if ok(m):
                d = math.hypot(m["x"] - px, m["y"] - py)
                if d <= bd:
                    best, bd = m, d
        return best

    if s["type"] == "single" or s["ground"]:
        a = anchor(s["rng"])
        if a is None:
            return "ไม่มีเป้าหมายในระยะ"
        cx, cy = a["x"], a["y"]
    else:
        a, cx, cy = None, px, py
    if s["type"] == "single":
        targets = [a]
    else:
        targets = sorted((m for m in insts.values()
                          if ok(m) and math.hypot(m["x"] - cx, m["y"] - cy) <= s["radius"]),
                         key=lambda m: math.hypot(m["x"] - cx, m["y"] - cy))[:s["max_t"]]
        if not targets:
            return "ไม่มีเป้าหมายในระยะ"
    res["center"] = (cx, cy)
    atk = G["eff_stat"](p, "atk", now)
    for inst in targets:
        dmgs, crit_any, snap = [], False, None
        for _ in range(s["hits"]):
            if not inst["alive"]:
                break
            dmg, crit = G["roll_damage"](atk, inst["def"], mult=s["mult"])
            snap = G["hit_monster"](inst, p, dmg, now, 1.5) or snap
            dmgs.append(dmg)
            crit_any = crit_any or crit
        res["lifesteal"] += int(sum(dmgs) * s["lifesteal"])
        if inst["alive"]:
            if s["stun"] and not inst["boss"]:
                inst["stun_until"] = max(inst["stun_until"], now + s["stun"])
            if s["dot"]:
                inst["dot"] = {"uid": p["id"], "name": p["username"], "dps": max(1, int(atk * s["dot"]["pct"])),
                               "next": now + 1.0, "until": now + s["dot"]["sec"]}
        if snap:
            res["kills"].append(snap)
        res["hits"].append({"monster_id": inst["id"], "x": round(inst["x"], 1), "y": round(inst["y"], 1),
                            "dmg": sum(dmgs), "hits": dmgs, "crit": crit_any,
                            "monster_hp_left": inst["hp"], "monster_died": snap is not None})
        res["states"].append(G["serialize_monster"](inst))
    if res["lifesteal"]:
        p["hp"] = min(p["max_hp"], p["hp"] + res["lifesteal"])
    return None


def _on_use_skill(data):
    G = _G
    sio = G["socketio"]
    sid = request.sid
    p = G["connected_players"].get(sid)
    if not p:
        return
    data = data or {}
    skill_id = str(data.get("skill") or "")

    def fail(msg):
        sio.emit("skill_result", {"success": False, "skill": skill_id, "message": msg}, room=sid)

    if not G["rate_ok"](sid, "skill", 0.25):
        return
    s = SKILL_TREE.get(skill_id)
    if s is None:
        return fail("ไม่พบสกิล")
    if p["hp"] <= 0:
        return fail("สลบอยู่ใช้สกิลไม่ได้")
    if not _job_allows(p["job"], s["job"]):
        return fail(f"สกิลนี้สำหรับสาย{JOB_TH.get(s['job'], s['job'])}")
    owned = p.get("skills_owned")
    if owned is None or skill_id not in owned:
        owned = _load_owned(p["id"])
        if skill_id not in owned:
            return fail("ยังไม่ได้ปลดล็อกสกิลนี้ (เปิดสมุดสกิลเพื่อดูเงื่อนไข)")
    offensive = s["type"] in ("single", "aoe")
    if offensive and p["map"] == "town":
        return fail("ในเมืองใช้สกิลโจมตีไม่ได้")

    now = time.time()
    res = {"heal": 0, "buff": None, "allies": [], "hits": [], "kills": [], "states": [],
           "center": None, "lifesteal": 0}
    err = None
    with G["STATE_LOCK"]:
        cds = p.setdefault("skill_cd", {})
        if now < cds.get(skill_id, 0):
            err = f"คูลดาวน์อีก {cds[skill_id] - now:.1f} วิ"
        elif p["mp"] < s["mp"]:
            err = "MP ไม่พอ"
        elif s["type"] == "heal":
            _do_heal(p, sid, s, res)
        elif s["type"] == "buff":
            _do_buff(p, sid, s, res, now)
        else:
            err = _do_attack(p, s, res, now, data.get("monster_id"))
        if err is None:
            p["mp"] -= s["mp"]
            cds[skill_id] = now + s["cd"]
            if offensive:
                p["last_combat"] = now
        px, py, map_name = p["x"], p["y"], p["map"]
    if err:
        return fail(err)

    tier = JOB_TIER.get(s["job"], 0)
    cx, cy = res["center"] or (px, py)
    if res["states"]:
        sio.emit("monsters_update", {"map": map_name, "monsters": res["states"]}, room=map_name)
    sio.emit("skill_fx", {
        "skill": skill_id, "fx": s["fx"], "name": s["name"], "color": s["color"], "type": s["type"],
        "tier": tier, "caster_sid": sid, "caster": p["username"],
        "x": round(px, 1), "y": round(py, 1), "cx": round(cx, 1), "cy": round(cy, 1),
        "radius": s["party"] if s["type"] in ("heal", "buff") else s["radius"],
        "stun": s["stun"], "dot": (s["dot"] or {}).get("sec", 0), "lifesteal": res["lifesteal"],
        "targets": [{"id": h["monster_id"], "x": h["x"], "y": h["y"], "dmg": h["dmg"], "hits": h["hits"],
                     "crit": h["crit"], "died": h["monster_died"]} for h in res["hits"]],
        "allies": [{"sid": a["sid"], "x": a["x"], "y": a["y"], "amt": a["amt"]} for a in res["allies"]],
    }, room=map_name)
    for a in res["allies"]:
        if a["sid"] == sid:
            continue
        sio.emit("stats_update", {"hp": a["hp"], "mp": a["mp"]}, room=a["sid"])
        if res["buff"]:
            sio.emit("skill_buff", {"from": p["username"], "name": s["name"], "icon": s["icon"], **res["buff"]},
                     room=a["sid"])
    sio.emit("stats_update", {"hp": p["hp"], "mp": p["mp"]}, room=sid)

    # สั่นจอ (สกิลที่มีจังหวะตกกระทบ เช่น อุกกาบาต → หน่วงให้ตรงภาพ)
    if not offensive:
        G["fx_shake"](sid, G["SHAKE_HEAL"], 0.35)
    else:
        power = (G["SHAKE_SKILL_AOE"] if s["type"] == "aoe" else G["SHAKE_SKILL"]) + 2 * tier
        if res["kills"]:
            power = max(power, G["SHAKE_KILL"])
        args = (map_name if (s["type"] == "aoe" or res["kills"]) else sid, power, 0.3 + 0.1 * tier)
        if s["shake_delay"]:
            threading.Timer(s["shake_delay"], G["fx_shake"], args=args).start()
        else:
            G["fx_shake"](*args)

    merged = {"exp_gain": 0, "gold_gain": 0, "leveled_up": False}
    user_payload = None
    for snap in res["kills"]:
        g = G["distribute_kill"](snap, p["id"], p["username"])
        if g:
            merged["exp_gain"] += g["exp_gain"]
            merged["gold_gain"] += g["gold_gain"]
            merged["leveled_up"] = merged["leveled_up"] or g["leveled_up"]
            user_payload = g["user"]

    out = {"success": True, "skill": skill_id, "type": s["type"], "mp": p["mp"], "hp": p["hp"], "cd": s["cd"]}
    if s["type"] == "heal":
        out["heal"] = res["heal"]
    elif s["type"] == "buff":
        out.update(res["buff"])
    else:
        out["hits"] = res["hits"]
        if res["kills"]:
            out.update(merged)
            if user_payload:
                out["user"] = user_payload
    sio.emit("skill_result", out, room=sid)


# ================= install =================
def install(G):
    global _G, _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True
    _G = G
    GD = G["GD"]
    LINEAGE.clear()
    LINEAGE.update(_build_lineage(GD.JOBS))
    JOB_TIER.clear()
    JOB_TIER.update({j: d["tier"] for j, d in GD.JOBS.items()})
    JOB_TIER["All"] = 0
    GROUP_ORDER[:] = _group_order(GD.JOBS)
    for k, s in SKILL_TREE.items():
        assert s["job"] == "All" or s["job"] in GD.JOBS, f"skill {k}: ไม่รู้จักอาชีพ {s['job']}"
        assert all(r in SKILL_TREE for r in s["req"]), f"skill {k}: req ไม่ถูกต้อง"
        GD.SKILLS[k] = _compat(s)
    _init_db()
    G["update_quest_progress"] = _update_quest_progress     # award_kill จะเรียกตัวใหม่
    app, sio = G["app"], G["socketio"]
    app.add_url_rule("/api/skills/tree", "lumi_skills_tree", _route_tree)
    app.add_url_rule("/api/skills/learn", "lumi_skills_learn", _route_learn, methods=["POST"])
    sio.on_event("use_skill", _on_use_skill)                 # แทนที่ handler เดิม
    log.info("Skill system v1.0 installed: %d skills / %d jobs", len(SKILL_TREE), len(LINEAGE))