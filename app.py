# -*- coding: utf-8 -*-
"""
Lumivara Online — GOD TIER v5.1 (RO-like + Trading Market)
- 23 แมพ (เมือง + 22 ด่านล่า) | ระบบอาชีพ 3 ต้น (Novice→Tier1→Tier2) เปลี่ยนอาชีพในเมือง
- Item Drop + Ground Item + เก็บอัตโนมัติ | ขายได้ทุกที่ | ไอเทมซ้ำรวมกอง
- ตลาดเทรด LUX: กราฟเคลื่อนไหวด้วย Market Maker | Limit order | TP/SL | Liquidation
- บอทฟาร์ม v2 (สวิตช์ใน Settings)
- [v5.1] ATK/DEF คำนวณจากแหล่งเดียว (recalc_stats) → ตีบวก/สวมใส่/เปลี่ยนอาชีพไม่ทำค่าหาย
- [v5.1.1] แก้ typo import + มอนเกิดใหม่มีช่วง "ตกลงมา" (spawn_until) ไม่สู้/ไม่โดนตีจนกว่าจะลงพื้น
รัน: python app.py -> http://localhost:6600
"""
import os, math, time, random, sqlite3, logging, threading
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash

# ================= GAME DATA =================
class GD:
    pass

# ---- อาชีพ 3 ต้น (RO-like) ----
GD.JOBS = {
    "Novice":   {"tier":0,"hp":100,"mp":50,"atk":10,"def":6,"g":{"hp":14,"mp":7,"atk":2,"def":1},
                 "advance":{"Swordsman":(10,800),"Mage":(10,800),"Archer":(10,800),"Thief":(10,800),"Acolyte":(10,800)}},
    "Swordsman":{"tier":1,"hp":140,"mp":40,"atk":14,"def":10,"g":{"hp":22,"mp":5,"atk":3,"def":2},"advance":{"Knight":(30,6000)}},
    "Mage":     {"tier":1,"hp":85,"mp":90,"atk":16,"def":4,"g":{"hp":11,"mp":11,"atk":4,"def":1},"advance":{"Wizard":(30,6000)}},
    "Archer":   {"tier":1,"hp":100,"mp":60,"atk":15,"def":5,"g":{"hp":13,"mp":8,"atk":4,"def":1},"advance":{"Hunter":(30,6000)}},
    "Thief":    {"tier":1,"hp":105,"mp":50,"atk":17,"def":5,"g":{"hp":12,"mp":6,"atk":4,"def":1},"advance":{"Assassin":(30,6000)}},
    "Acolyte":  {"tier":1,"hp":110,"mp":80,"atk":12,"def":7,"g":{"hp":15,"mp":10,"atk":2,"def":2},"advance":{"Priest":(30,6000)}},
    "Knight":   {"tier":2,"hp":200,"mp":50,"atk":20,"def":16,"g":{"hp":32,"mp":6,"atk":4,"def":3},"advance":{}},
    "Wizard":   {"tier":2,"hp":110,"mp":140,"atk":26,"def":5,"g":{"hp":13,"mp":16,"atk":6,"def":1},"advance":{}},
    "Hunter":   {"tier":2,"hp":140,"mp":90,"atk":24,"def":7,"g":{"hp":17,"mp":11,"atk":6,"def":2},"advance":{}},
    "Assassin": {"tier":2,"hp":150,"mp":70,"atk":27,"def":7,"g":{"hp":16,"mp":8,"atk":6,"def":2},"advance":{}},
    "Priest":   {"tier":2,"hp":170,"mp":120,"atk":17,"def":11,"g":{"hp":20,"mp":14,"atk":3,"def":3},"advance":{}},
}

GD.MAPS, GD.MONSTERS, MAP_META, MON_NAME = [], {}, [], {}

def mk(name, lv, agg=False, boss=False, resp=12):
    if boss:
        agg = True                      # บอสต้อง aggressive เสมอ
    return {"name": name, "level": lv,
            "hp": int(60 * (1.09 ** (lv - 1))) + (250 * lv if boss else 0),
            "atk": int(8 + lv * 1.8 + (1.06 ** lv)),
            "def": 2 + int(lv * 0.7),
            "exp": int(15 * (1.11 ** (lv - 1))) * (4 if boss else 1),
            "gold": int(8 * (1.06 ** (lv - 1))) * (6 if boss else 1),
            "respawn": (60 if boss else resp), "aggressive": agg, "boss": boss}

# FIELD_SPECS: (map_key, label, [(ชื่อมอน, เลเวล, aggressive?, boss?)])
FIELD_SPECS = [
    # --- ด่านเดิม 22 ด่านแรก ---
    ("forest","ป่าแห่งการเริ่มต้น",[("สไลม์เขียว",1),("สไลม์ทอง",2),("หมาป่า",3,True)]),
    ("meadow","ทุ่งหญ้ากว้าง",[("ผึ้งป่า",4),("หมูป่า",5,True),("สิงโตน้อย",6)]),
    ("cave","ถ้ำลึก",[("ค้างคาว",7,True),("โคบอลด์",8),("โกเลมหิน",9)]),
    ("beach","ชายหาดปริศนา",[("ปูยักษ์",10),("เพนกวินนักรบ",11),("หมึกโจรสลัด",12,True)]),
    ("desert","ทะเลทรายร้อน",[("แมงป่องทราย",13,True),("งูเห่า",14),("หนอนทราย",15)]),
    ("dungeon","ดันเจี้ยนเก่า (PvP)",[("โครงกระดูก",16,True),("ผีร้าย",17,True),("เวอราธ",18),("ราชาอสูรเงา",19,False,True)]),
    ("swamp","หนองบึงพิษ",[("กบยักษ์",20),("ปลิงดูดเลือด",21,True),("ชายโคลน",22)]),
    ("mine","เหมืองแร่โบราณ",[("หนอนหิน",23),("โกเลมช่างเหมือง",24),("ด้วงอัญมณี",25)]),
    ("temple","วิหารสาบสูญ",[("รูปปั้นมีชีวิต",26),("วิญญาณนักบวช",27,True),("ผู้พิทักษ์",28)]),
    ("snowfield","ทุ่งหิมะนิรันดร์",[("มนุษย์หิมะ",29),("หมาป่าน้ำแข็ง",30,True),("เยติ",31)]),
    ("jungle","ป่าดิบชื้น",[("ลิงป่า",32),("เสือโคร่ง",33,True),("เสจวดำ",34)]),
    ("volcano","ภูเขาไฟ",[("ภูตไฟ",35),("โกเลมลาวา",36,True),("สุนัขแมกม่า",37)]),
    ("ghost_town","เมืองร้างผีสิง",[("ซอมบี้",38,True),("ไวท์",39),("หน้ากากเกรียน",40)]),
    ("ruins","ซากปรักหักพัง",[("การ์กอยล์",41),("อัศวินหิน",42,True),("อาร์คลิช",43)]),
    ("labyrinth","เขาวงกต",[("มิโนทอร์",44,True),("สฟิงซ์",45),("แมงมุมวางกับดัก",46)]),
    ("oasis","โอเอซิสลับ",[("โจรทะเลทราย",47,True),("โกเลมทราย",48),("ภาพลวงตา",49)]),
    ("dragon_valley","หุบเขามังกร",[("เดรก",50,True),("ไวเวิร์น",51),("ลูกมังกร",52)]),
    ("sky_tower","หอคอยสวรรค์",[("ฮาร์ปี้",53,True),("ภูตพายุ",54),("อัศวินเวหา",55)]),
    ("glacier","ธารน้ำแข็ง",[("ยักษ์น้ำแข็ง",56,True),("ยามของราชินีน้ำแข็ง",57),("เวราธหิมะ",58)]),
    ("abyss","เหวลึกมืดมน",[("นักเดินผ่ามืด",59,True),("ฝันร้าย",60),("ผู้รับใช้ห้วง",61)]),
    ("hell","นรกเพลิงชั่วนิรันดร์",[("ปีศาจ",62,True),("สุนัขนรก",63),("ปีศาจอัคคี",64)]),
    ("moonlight","ป่าแสงจันทร์",[("กระต่ายจันทร์",65),("หมาป่าแสงจันทร์",66,True),("ภูตดาว",67),("ราชาแสงจันทร์",68,False,True)]),

    # --- เพิ่มใหม่อีก 50 ด่าน (ด่านที่ 23 ถึง 72) ---
    ("star_ridge","สันเขาดารา",[("กริฟฟินฝึกหัด",69),("สิงโตนภา",70,True),("นักรบดารา",71)]),
    ("crystal_cave","ถ้ำคริสตัลระยิบ",[("คริสตัลลิ่ง",72),("โกเลมคริสตัล",73,True),("ราชินีคริสตัล",74,False,True)]),
    ("blood_marsh","บึงโลหิต",[("อีกาผี",75),("ผีดิบดูดเลือด",76,True),("อสูรบึง",77)]),
    ("sunken_ruin","ซากปรักหักพังใต้น้ำ",[("ฉลามคลั่ง",78,True),("เงือกดุร้าย",79),("ราชาเงือก",80,False,True)]),
    ("shadow_realm","ดินแดนเงาทมิฬ",[("เงามืด",81,True),("นักฆ่าไร้เงา",82,True),("ปีศาจเงา",83)]),
    ("thunder_peak","ยอดเขาอัสนี",[("อินทรีสายฟ้า",84,True),("ภูตสายฟ้า",85),("เจ้านกสายฟ้า",86,False,True)]),
    ("necropolis","นครคนตาย",[("โครงกระดูกเกราะเหล็ก",87,True),("มัมมี่โบราณ",88),("ราชาโครงกระดูก",89,False,True)]),
    ("magma_core","แกนกลางลาวา",[("แมกม่าสไลม์",90),("อสูรหลอมเหลว",91,True),("มังกรไฟลาวา",92,False,True)]),
    ("forgotten_isle","เกาะแห่งความทรงจำ",[("ภูตเร่ร่อน",93),("พายุดวงวิญญาณ",94,True),("ผู้เฝ้าประตูมิติ",95,False,True)]),
    ("storm_canyon","หุบเขาพายุ",[("แฮปปี้สตอร์ม",96,True),("โกเลมลมกรด",97),("เจ้าแห่งพายุ",98,False,True)]),
    ("toxic_cave","ถ้ำพิษมรกต",[("แมงมุมพิษเขียว",99,True),("ค้างคาวพิษ",100),("ราชาแมงมุม",101,False,True)]),
    ("golden_desert","ทะเลทรายทองคำ",[("ยามสุริยะ",102),("อสูรทรายทอง",103,True),("ฟาโรห์โบราณ",104,False,True)]),
    ("frost_spire","ยอดหอคอยน้ำแข็ง",[("นักเวทย์น้ำแข็ง",105,True),("อัศวินน้ำแข็ง",106),("ราชินีน้ำแข็ง",107,False,True)]),
    ("chaos_dimension","มิติโกลาหล",[("อสูรกายไร้ร่าง",108,True),("ปีศาจความวุ่นวาย",109),("ผู้ทำลายล้าง",110,False,True)]),
    ("sky_kingdom","อาณาจักรลอยฟ้า",[("ทหารสวรรค์",111),("เซนทอร์เวหา",112,True),("เทพผู้พิทักษ์",113,False,True)]),
    ("infernal_gate","ประตูสู่นรกภูมิ",[("ยามนรก",114,True),("หมาสามหัว",115,True),("แม่ทัพนรก",116,False,True)]),
    ("world_edge","ขอบสิ้นสุดโลก",[("ผู้กล้าตกสวรรค์",117,True),("มังกรบรรพกาล",118,False,True)]),
    ("dragon_nest","รังมังกรโบราณ",[("ลูกมังกรไฟ",119),("มังกรทมิฬ",120,True),("ราชามังกรทองคำ",121,False,True)]),
    ("dimension_rift","รอยแยกมิติเวลา",[("ภูตเวลา",122),("นักรบต่างมิติ",123,True),("ผู้ควบคุมกาลเวลา",124,False,True)]),
    ("nirvana_temple","วิหารนิพพาน",[("รูปปั้นทองคำ",125),("นักบวชโบราณ",126,True),("เทพแห่งวิหาร",127,False,True)]),
    ("dark_forest","ป่ารัตติกาลลึก",[("หมาป่าตาเดียว",128,True),("แม่มดแห่งความมืด",129),("ราชาป่ามืด",130,False,True)]),
    ("iron_fortress","ป้อมปราการเหล็กกล้า",[("ทหารยามจักรกล",131,True),("ป้อมปืนกลอัตโนมัติ",132),("แม่ทัพจักรกล",133,False,True)]),
    ("poison_swamp","บึงพิษพันปี",[("งูลายเมฆ",134),("จระเข้หนองน้ำ",135,True),("ราชินีงูพิษ",136,False,True)]),
    ("star_temple","วิหารแห่งดวงดาว",[("นักบวชแห่งดาว",137),("นักรบแสงดาว",138,True),("เทพแห่งดวงดาว",139,False,True)]),
    ("moon_castle","ปราสาทจันทรา",[("อัศวินจันทร์เสี้ยว",140,True),("เงาจันทรา",141),("ราชาจันทรา",142,False,True)]),
    ("sun_temple","วิหารสุริยัน",[("นักรบสุริยะ",143,True),("สิงโตเพลิง",144),("เทพสุริยัน",145,False,True)]),
    ("abyss_core","แกนกลางเหวลึก",[("อสูรเหว",146,True),("ปีศาจตาเดียว",147),("เจ้าแห่งเหว",148,False,True)]),
    ("heaven_stair","บันไดสู่สรวงสวรรค์",[("ทูตสวรรค์ฝึกหัด",149),("เทวดาปีกคู่",150,True),("อัครเทวดา",151,False,True)]),
    ("void_space","ห้วงอวกาศว่างเปล่า",[("ภูตความว่างเปล่า",152,True),("ปีศาจไร้ลักษณ์",153),("ผู้กลืนกินดวงดาว",154,False,True)]),
    ("eternal_fire","เปลวเพลิงนิรันดร์",[("ภูตอัคคีอมตะ",155,True),("ฟีนิกซ์ไฟ",156),("ราชาฟีนิกซ์",157,False,True)]),
    ("frozen_throne","บัลลังก์น้ำแข็งนิรันดร์",[("ยักษ์น้ำแข็งโบราณ",158,True),("อัศวินน้ำแข็งดำ",159),("จักรพรรดิน้ำแข็ง",160,False,True)]),
    ("storm_realm","อาณาจักรพายุสายฟ้า",[("ปีศาจพายุ",161,True),("มังกรสายฟ้า",162),("เทพเจ้าสายฟ้า",163,False,True)]),
    ("phantom_city","เมืองมายา",[("ภูตเงามายา",164,True),("นักฆ่ามายา",165),("ราชามายา",166,False,True)]),
    ("blood_arena","สนามประลองโลหิต",[("นักสู้คลั่ง",167,True),("นักรบเดนตาย",168),("เจ้าสนามประลอง",169,False,True)]),
    ("spirit_world","โลกวิญญาณ",[("ดวงวิญญาณเร่ร่อน",170),("ยมทูตฝึกหัด",171,True),("ราชาแห่งยมโลก",172,False,True)]),
    ("dragon_realm","ดินแดนราชามังกร",[("มังกรพิทักษ์",173,True),("มังกรโบราณ",174),("บรรพบุรุษมังกร",175,False,True)]),
    ("galaxy_edge","ขอบกาแล็กซี่",[("สิ่งมีชีวิตต่างดาว",176,True),("ผู้พิทักษ์จักรวาล",177),("ราชันแห่งจักรวาล",178,False,True)]),
    ("time_labyrinth","เขาวงกตเวลา",[("นักเดินทางข้ามเวลา",179,True),("อสูรนาฬิกา",180),("เจ้าแห่งกาลเวลา",181,False,True)]),
    ("mythic_land","ดินแดนในตำนาน",[("สัตว์ประหลาดในตำนาน",182,True),("เทพนิยายโบราณ",183),("มหาเทพผู้สร้าง",184,False,True)]),
    ("ultimate_hell","ขุมนรกสูงสุด",[("อสูรนรกเกรดเอส",185,True),("ปราชญ์ทมิฬ",186),("จอมมารแห่งนรก",187,False,True)]),
    ("god_domain","เขตแดนทวยเทพ",[("เทวดาสงคราม",188,True),("เทพผู้ทำลาย",189),("มหาเทพแห่งสงคราม",190,False,True)]),
    ("genesis_realm","ดินแดนปฐมกำเนิด",[("ภูตกำเนิดโลก",191,True),("มังกรปฐมกาล",192),("ผู้ให้กำเนิดจักรวาล",193,False,True)]),
    ("omega_dimension","มิติโอเมก้า",[("เงาโอเมก้า",194,True),("ปีศาจขั้นสุดท้าย",195),("โอเมก้าอสูร",196,False,True)]),
    ("infinity_tower","หอคอยไร้สิ้นสุด",[("ผู้พิทักษ์ชั้นสูง",197,True),("นักรบอมตะ",198),("เจ้าแห่งหอคอยนิรันดร์",199,False,True)]),
    ("lumivara_zenith","จุดสูงสุดลูมิฟาร่า",[("มังกรแสงศักดิ์สิทธิ์",200,True),("เทพสูงสุดลูมิฟาร่า",201,False,True)]),
]

mid = 0
for key, label, mons in FIELD_SPECS:
    GD.MAPS.append(key)
    MAP_META.append({"key": key, "label": label, "level": mons[0][1] if mons else 0})
    insts = []
    for name, lv, *rest in mons:
        mid += 1
        agg = bool(rest[0]) if rest else False            # arg แรก = aggressive
        boss = bool(rest[1]) if len(rest) > 1 else False   # arg ที่สอง = boss
        m = mk(name, lv, agg=agg, boss=boss)
        m["id"] = mid
        MON_NAME[mid] = name
        insts.append(m)
    GD.MONSTERS[key] = insts

GD.MAPS.insert(0, "town")
MAP_META.insert(0, {"key": "town", "label": "เมืองหลวง Gemivara", "level": 0})
MAP_LABELS = {m["key"]: m["label"] for m in MAP_META}

GD.ITEMS = {
    1: {"name": "โพชั่น HP เล็ก", "type": "potion", "price": 20, "sell_price": 8, "heal_pct": 0.35},
    2: {"name": "โพชั่น MP เล็ก", "type": "potion", "price": 20, "sell_price": 8, "mana_pct": 0.35},
    3: {"name": "โพชั่น HP ใหญ่", "type": "potion", "price": 60, "sell_price": 25, "heal_pct": 0.8, "level_req": 5},
    4: {"name": "โพชั่น MP ใหญ่", "type": "potion", "price": 60, "sell_price": 25, "mana_pct": 0.8, "level_req": 5},
    500: {"name": "อัญมณีราชา", "type": "material", "price": 400, "sell_price": 250},
}

# สร้างไอเทมวัสดุดรอปจากมอนสเตอร์ทุกตัวอัตโนมัติ (ต่อจากของที่คุณเพิ่ม)
for _key, insts in GD.MONSTERS.items():
    for mm in insts:
        p = 5 + mm["level"] * 6
        GD.ITEMS[100 + mm["id"]] = {"name": f"วัสดุ {mm['name']}", "type": "material",
                                    "price": p, "sell_price": int(p * 0.55)}

DROP_TABLES = {}
for _key, insts in GD.MONSTERS.items():
    for mm in insts:
        if mm.get("boss"):
            DROP_TABLES[mm["id"]] = [(100 + mm["id"], 1.0), (500, 0.6), (3, 0.5), (1, 0.4)]
        else:
            DROP_TABLES[mm["id"]] = [(100 + mm["id"], 0.55), (1, 0.07), (2, 0.07)]

# [FIX] โหลดส่วนเสริมแบบไม่บังคับ — ไม่มีไฟล์ก็ยังเปิดเกมได้
try:
    import lumivara_ext as EXT
except ImportError:
    EXT = None
    logging.getLogger("lumivara").warning("ไม่พบ lumivara_ext.py — รันโดยไม่มีส่วนเสริม")
if EXT:
    EXT.extend_world(globals())

# [FIX] โบนัส ATK/DEF ต่อระดับตีบวก (ใช้ค่าเดียวกับส่วนเสริม)
ENH_BONUS = getattr(EXT, "ENH_BONUS", 2) if EXT else 2


# ---- สกิล 20 ตัว (tuple 7 ค่าเสมอ: name, job, type, mp, cd, paramA, paramB) ----
SKILL_DB = {
    "power_strike":  ("ฟันพลัง","All","single",8,3,1.8,150),
    "heal":          ("ฟื้นฟู","All","heal",14,10,0.35,None),
    "bash":          ("ทุบสกัล","Swordsman","single",10,4,2.2,160),
    "magnum":        ("แม็กนัมเบรก","Swordsman","aoe",20,8,1.5,7),
    "frost_bolt":    ("ศรน้ำแข็ง","Mage","single",12,4,2.0,200),
    "fire_blast":    ("ระเบิดเพลิง","Mage","aoe",22,7,1.7,6),
    "meteor":        ("อุกกาบาต","Wizard","aoe",35,10,2.2,8),
    "jupitel":       ("จูปิเตอร์ธันเดอร์","Wizard","single",25,5,2.8,200),
    "double_strafe": ("ศรคู่","Archer","single",12,4,2.4,200),
    "arrow_rain":    ("ฝนศร","Archer","aoe",20,7,1.5,6),
    "blitz_beat":    ("บลิทซ์บีท","Hunter","aoe",26,8,1.8,7),
    "focus_aim":     ("เล็งแม่น","Hunter","buff",15,18,1.35,"atk"),
    "sonic_blow":    ("โซนิคโบว์","Thief","single",16,5,2.6,170),
    "grimtooth":     ("กริมทูธ","Assassin","single",22,6,3.0,180),
    "cloak":         ("ล่องหน","Assassin","buff",18,20,1.3,"atk"),
    "bless":         ("อวยพร","Acolyte","buff",15,18,1.3,"atk"),
    "heal_plus":     ("ฮีลใหญ่","Acolyte","heal",20,9,0.55,None),
    "magnificat":    ("มักนิฟิแคท","Priest","heal",30,12,0.7,None),
    "brandish":      ("แบรนดิช","Knight","single",24,6,2.9,180),
    "endure":        ("ต้านทน","Knight","buff",18,20,1.35,"def"),
}
GD.SKILLS = {}
for sid_, (nm, jb, tp, mp_, cd, a, b) in SKILL_DB.items():
    sk = {"name": nm, "job": jb, "type": tp, "mp": mp_, "cd": cd}
    if tp == "heal":
        sk["heal_pct"] = a
    elif tp == "buff":
        sk["mult"] = a
        sk["stat"] = b if b in ("atk", "def") else "atk"
        sk["duration"] = 20
    else:
        sk["mult"] = a
        if tp == "single":
            sk["range"] = b if isinstance(b, (int, float)) else 170
        else:
            sk["radius"] = 160
            sk["max_targets"] = b if isinstance(b, int) else 7
    GD.SKILLS[sid_] = sk

# ---- เควส (target_monster = base_id จริง) ----
GD.QUESTS = {
    # --- เควสเริ่มต้น (ด่าน 1-6) ---
    1: {"name": "กำจัดสไลม์", "desc": "กำจัดสไลม์เขียว 5 ตัว", "target_monster": 1, "target_count": 5, "reward_exp": 80, "reward_gold": 50},
    2: {"name": "ล่าหมาป่า", "desc": "กำจัดหมาป่า 3 ตัว", "target_monster": 3, "target_count": 3, "reward_exp": 120, "reward_gold": 80},
    3: {"name": "ภัยจากผึ้งป่า", "desc": "กำจัดผึ้งป่า 5 ตัว", "target_monster": 4, "target_count": 5, "reward_exp": 180, "reward_gold": 120},

    # --- เควสกลางเกม (ด่าน 7-22) ---
    4: {"name": "ล้างบางถ้ำลึก", "desc": "กำจัดโกเลมหิน 5 ตัว", "target_monster": 9, "target_count": 5, "reward_exp": 350, "reward_gold": 250},
    5: {"name": "ปราบราชาอสูร", "desc": "ปราบราชาอสูรเงาในดันเจี้ยนเก่า", "target_monster": 19, "target_count": 1, "reward_exp": 800, "reward_gold": 600},
    6: {"name": "ผู้กล้าแสงจันทร์", "desc": "ปราบราชาแสงจันทร์ที่ป่าแสงจันทร์", "target_monster": 68, "target_count": 1, "reward_exp": 3000, "reward_gold": 2000},

    # --- เควสเนื้อเรื่องใหม่ (ดันเจี้ยนและบอส 50 ด่านเพิ่ม) ---
    7: {"name": "ความลับถ้ำคริสตัล", "desc": "ปราบราชินีคริสตัลในถ้ำคริสตัล", "target_monster": 74, "target_count": 1, "reward_exp": 5000, "reward_gold": 3500},
    8: {"name": "เจ้าแห่งท้องทะเล", "desc": "ปราบราชาเงือกในซากปรักหักพังใต้น้ำ", "target_monster": 80, "target_count": 1, "reward_exp": 8500, "reward_gold": 6000},
    9: {"name": "อัสนีคำราม", "desc": "ปราบเจ้านกสายฟ้าบนยอดเขาอัสนี", "target_monster": 86, "target_count": 1, "reward_exp": 13000, "reward_gold": 9000},
    10: {"name": "มังกรแห่งลาวา", "desc": "ปราบมังกรไฟลาวาในแกนกลางลาวา", "target_monster": 92, "target_count": 1, "reward_exp": 20000, "reward_gold": 15000},
    11: {"name": "ผู้พิทักษ์มิติ", "desc": "ปราบผู้เฝ้าประตูมิติที่เกาะแห่งความทรงจำ", "target_monster": 95, "target_count": 1, "reward_exp": 30000, "reward_gold": 22000},
    12: {"name": "ตำนานลูมิฟาร่า", "desc": "ปราบเทพสูงสุดลูมิฟาร่าที่จุดสูงสุดลูมิฟาร่า", "target_monster": 201, "target_count": 1, "reward_exp": 100000, "reward_gold": 80000},
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
ADMIN_USERNAME = os.environ.get("LUMIVARA_ADMIN", "")

AI_TICK, REGEN_EVERY, WANDER_EVERY, AUTOSAVE_SECONDS = 0.5, 2.0, 2.0, 30
ATTACK_COOLDOWN, CHAT_COOLDOWN, PVP_COOLDOWN, ITEM_COOLDOWN = 0.7, 1.0, 1.2, 0.8
ATTACK_RANGE, SKILL_RANGE, MAX_MOVE_SPEED, PVP_MAP = 120, 220, 450.0, "dungeon"
CRIT_CHANCE, CRIT_MULT, DMG_VARIANCE = 0.10, 1.9, 0.15
MONSTER_DODGE, PLAYER_DODGE = 0.05, 0.04
AGGRO_RANGE, LEASH_RANGE, MONSTER_ATTACK_RANGE = 150, 380, 55
PROVOKE_RANGE = 70.0
MONSTER_ATTACK_CD, BOSS_ATTACK_CD = 1.8, 1.4
MONSTER_SPEED, BOSS_SPEED = 95.0, 75.0
IDLE_REGEN_DELAY, IDLE_REGEN_PCT = 8.0, 0.05
BOSS_ENRAGE_HP, BOSS_ENRAGE_MULT = 0.30, 1.5
BOSS_SLAM_CD, BOSS_SLAM_RADIUS, BOSS_SLAM_MULT = 10.0, 150, 1.3
RESPAWN_DELAY, SPAWN_PROTECT = 3.0, 3.0
MONSTER_SPAWN_FALL = 2.1   # [v5.1.1] วินาทีที่มอนเกิดใหม่ "ตกลงมา" — ไม่สู้/ไม่โดนตี (ให้ตรงกับ skydrop.js)
DEATH_EXP_LOSS, DEATH_GOLD_LOSS = 0.10, 0.05
LAST_HIT_BONUS, MIN_SHARE = 0.10, 0.05
GROUND_ITEM_TTL, PICKUP_RANGE, GROUND_CAP_PER_MAP = 90.0, 60.0, 80
SHAKE_HIT, SHAKE_HIT_CRIT, SHAKE_KILL = 5, 11, 13
SHAKE_SKILL, SHAKE_SKILL_AOE, SHAKE_HEAL = 8, 12, 3
SHAKE_MONSTER_HIT, SHAKE_BOSS_SLAM = 6, 16

MAP_SPAWNS = {k: (400.0, 300.0) if k == "town" else (90.0, 300.0) for k in GD.MAPS}
NPCS = {
    "town": [
        {"id": "npc_potion", "name": "ยายพอใจ (ร้านยา)", "sprite": "🧪", "x": 615.0, "y": 140.0, "type": "shop"},
        {"id": "npc_buyer", "name": "บอทรับซื้อ BE-1", "sprite": "🤖", "x": 705.0, "y": 235.0, "type": "sell"},
        {"id": "npc_job", "name": "ปรมาจารย์อาชีพ", "sprite": "🏅", "x": 200.0, "y": 130.0, "type": "job"},
    ],
}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("LUMIVARA_SECRET", "lumivara_secret_2026")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading", ping_interval=20, ping_timeout=15)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("lumivara")

@app.after_request
def _no_cache(resp):
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    return resp

STATE_LOCK = threading.RLock()
connected_players = {}
MONSTER_INSTANCES = {}
GROUND_ITEMS = {}
_rate_limit = {}

# ================= MARKET (BTC-like) =================
MARKET_LOCK = threading.Lock()
MARKET = {"price": 1000.0, "hist": [1000.0] * 60}
MARKET_ORDERS = {}      # uid -> [order]
POSITIONS = {}          # uid -> {"side","qty","entry","margin","tp","sl"}
MARGIN_RATE, TRADE_FEE = 0.10, 0.002

def _get_gold(uid):
    with get_db() as conn:
        row = get_user_by_id(conn, uid)
        return int(row["gold"]) if row else 0

def _set_gold(uid, gold):
    with get_db() as conn:
        conn.execute("UPDATE users SET gold=? WHERE id=?", (max(0, int(gold)), uid))

def _emit_state(uid, extra=None):
    sid = find_sid_by_uid(uid)
    if not sid:
        return
    payload = {"position": POSITIONS.get(uid), "orders": MARKET_ORDERS.get(uid, []),
               "gold": _get_gold(uid)}
    if extra:
        payload.update(extra)
    socketio.emit("market_state", payload, room=sid)
    socketio.emit("gold_update", {"gold": payload["gold"]}, room=sid)

def _open_position(uid, side, qty, price):
    qty = max(1, int(qty))
    pos = POSITIONS.get(uid)
    if pos and pos["side"] != side:
        _close_position(uid, MARKET["price"], reason="swap")
        pos = None
    notional = qty * price
    margin = notional * MARGIN_RATE
    fee = notional * TRADE_FEE
    cost = margin + fee
    gold = _get_gold(uid)
    if gold < cost:
        return False, f"เงินไม่พอ (ต้องใช้ {cost:.0f} G = Margin 10% + ค่าธรรมเนียม)"
    _set_gold(uid, gold - cost)
    if pos:
        total_qty = pos["qty"] + qty
        pos["entry"] = (pos["entry"] * pos["qty"] + price * qty) / total_qty
        pos["qty"] = total_qty
        pos["margin"] += margin
    else:
        POSITIONS[uid] = {"side": side, "qty": qty, "entry": round(price, 2),
                          "margin": margin, "tp": None, "sl": None}
    _emit_state(uid, {"msg": f"✅ เปิดสถานะ {('LONG' if side=='long' else 'SHORT')} {qty} @ {price:.2f}"})
    return True, "ok"

def _close_position(uid, price, reason="manual"):
    pos = POSITIONS.pop(uid, None)
    if not pos:
        return 0
    pnl = (price - pos["entry"]) * pos["qty"] if pos["side"] == "long" else (pos["entry"] - price) * pos["qty"]
    payout = max(0.0, pos["margin"] + pnl)
    _set_gold(uid, _get_gold(uid) + payout)
    sid = find_sid_by_uid(uid)
    if sid:
        socketio.emit("market_closed", {"pnl": round(pnl, 2), "payout": round(payout, 0),
                                        "price": round(price, 2), "reason": reason,
                                        "side": pos["side"]}, room=sid)
    _emit_state(uid)
    return pnl

def market_loop():
    log.info("Market loop started (Market Makers active)")
    while True:
        try:
            time.sleep(2.0)
            with MARKET_LOCK:
                p = MARKET["price"]
                flow = random.uniform(-1, 1) * random.choice([1, 1, 1, 2])   # MM bots buy/sell pressure
                p += (1000 - p) * 0.004 + flow * random.uniform(3, 14) + random.gauss(0, 2.5)
                p = max(50.0, p)
                MARKET["price"] = p
                MARKET["hist"].append(round(p, 2))
                if len(MARKET["hist"]) > 240:
                    MARKET["hist"].pop(0)
                # Limit orders
                for uid in list(MARKET_ORDERS.keys()):
                    remain = []
                    for o in MARKET_ORDERS.get(uid, []):
                        hit = (o["side"] == "long" and p <= o["limit"]) or (o["side"] == "short" and p >= o["limit"])
                        if hit:
                            ok, msg = _open_position(uid, o["side"], o["qty"], o["limit"])
                            sid = find_sid_by_uid(uid)
                            if sid and not ok:
                                socketio.emit("market_notice", {"msg": "❌ " + msg}, room=sid)
                        else:
                            remain.append(o)
                    MARKET_ORDERS[uid] = remain
                # TP / SL / Liquidation
                for uid, pos in list(POSITIONS.items()):
                    liq = pos["entry"] * (0.9 if pos["side"] == "long" else 1.1)
                    if (pos["side"] == "long" and p <= liq) or (pos["side"] == "short" and p >= liq):
                        _close_position(uid, p, reason="liquidation")
                        continue
                    if pos.get("tp") and ((pos["side"] == "long" and p >= pos["tp"]) or (pos["side"] == "short" and p <= pos["tp"])):
                        _close_position(uid, p, reason="tp")
                        continue
                    if pos.get("sl") and ((pos["side"] == "long" and p <= pos["sl"]) or (pos["side"] == "short" and p >= pos["sl"])):
                        _close_position(uid, p, reason="sl")
            socketio.emit("market_tick", {"price": round(p, 2)})
        except Exception:
            log.exception("market loop error")

def now_iso(): return datetime.now(timezone.utc).isoformat()
def clamp(v, lo, hi): return max(lo, min(hi, v))

def fx_shake(room, intensity, duration=0.25, extra=None):
    payload = {"intensity": round(float(intensity), 1), "duration": float(duration)}
    if extra: payload.update(extra)
    if room is None: socketio.emit("screen_shake", payload)
    else: socketio.emit("screen_shake", payload, room=room)

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode=WAL")
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
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        if "kills" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN kills INTEGER DEFAULT 0")
        if "last_daily" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN last_daily TEXT")
        # [FIX] คอลัมน์ตีบวก — สร้างที่นี่เลย ไม่ต้องรอส่วนเสริม
        inv_cols = {r["name"] for r in conn.execute("PRAGMA table_info(inventory)")}
        if "enhance" not in inv_cols:
            conn.execute("ALTER TABLE inventory ADD COLUMN enhance INTEGER DEFAULT 0")
        c.execute("CREATE INDEX IF NOT EXISTS idx_inv_user ON inventory(user_id)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_quest ON user_quests(user_id, quest_id)")
    log.info("Database ready (%s)", DB_PATH)

def user_to_dict(row):
    return {"id": row["id"], "username": row["username"], "level": row["level"],
            "job": row["job"], "hp": row["hp"], "maxHp": row["max_hp"],
            "mp": row["mp"], "maxMp": row["max_mp"], "atk": row["atk"], "def": row["def"],
            "gold": row["gold"], "exp": row["exp"], "maxExp": row["max_exp"],
            "x": row["x"], "y": row["y"], "map": row["map"], "isAdmin": bool(row["is_admin"])}

def get_user_by_id(conn, uid):
    return conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()

# ================= [FIX] ค่าสถานะ: แหล่งความจริงเดียว =================
def equip_bonus(conn, uid):
    """รวมโบนัสจากอุปกรณ์ที่สวมอยู่: อาวุธ → ATK, เกราะ → DEF (รวมค่าตีบวก)"""
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
    """ATK/DEF = ฐานอาชีพ + การเติบโตตามเลเวล + อุปกรณ์ที่สวม → บันทึกลง DB แล้วคืนแถวล่าสุด
    ใช้สูตรเดียวกับ register / apply_level_up / job_change จึงไม่มีค่าเพี้ยนสะสม"""
    row = get_user_by_id(conn, uid)
    if row is None:
        return None
    job = GD.JOBS.get(row["job"], GD.JOBS["Novice"])
    lv = row["level"]
    ea, ed = equip_bonus(conn, uid)
    atk = job["atk"] + job["g"]["atk"] * (lv - 1) + ea
    df = job["def"] + job["g"]["def"] * (lv - 1) + ed
    if atk != row["atk"] or df != row["def"]:
        conn.execute("UPDATE users SET atk=?, def=? WHERE id=?", (atk, df, uid))
        row = get_user_by_id(conn, uid)
    return row

def authorize(user_id_from_body=None):
    uid = session.get("user_id")
    if uid is None:
        return None, (jsonify({"success": False, "message": "กรุณาเข้าสู่ระบบก่อน"}), 401)
    if user_id_from_body is not None and str(user_id_from_body) != str(uid):
        return None, (jsonify({"success": False, "message": "ไม่มีสิทธิ์เข้าถึงข้อมูลผู้เล่นนี้"}), 403)
    return uid, None

def find_sid_by_uid(uid):
    with STATE_LOCK:
        for s, q in connected_players.items():
            if q["id"] == uid:
                return s
    return None

def find_player_by_uid(uid):
    with STATE_LOCK:
        for s, q in connected_players.items():
            if q["id"] == uid:
                return s, q
    return None

def live_user(row):
    d = user_to_dict(row)
    found = find_player_by_uid(row["id"])
    if found:
        d["hp"], d["mp"] = found[1]["hp"], found[1]["mp"]
    return d

def flush_vitals_by_uid(conn, uid):
    found = find_player_by_uid(uid)
    if found:
        p = found[1]
        conn.execute("UPDATE users SET hp=?, mp=? WHERE id=?", (p["hp"], p["mp"], uid))

def sync_memory_stats(user_dict, vitals=False):
    with STATE_LOCK:
        for p in connected_players.values():
            if p["id"] == user_dict["id"]:
                p.update({"level": user_dict["level"], "max_hp": user_dict["maxHp"],
                          "max_mp": user_dict["maxMp"], "atk": user_dict["atk"], "def": user_dict["def"],
                          "job": user_dict["job"]})
                if vitals and p["hp"] > 0:
                    p["hp"], p["mp"] = user_dict["hp"], user_dict["mp"]
                p["hp"] = min(p["hp"], p["max_hp"])
                p["mp"] = min(p["mp"], p["max_mp"])
                break

def eff_stat(p, key, now=None):
    now = now or time.time()
    val = p[key]
    b = p.get("buffs", {}).get(key)
    if b and b["until"] > now:
        val = val * b["mult"]
    return val

def public_player_info(sid, p):
    return {"sid": sid, "id": p["id"], "username": p["username"], "x": p["x"], "y": p["y"],
            "map": p["map"], "level": p["level"], "hp": p["hp"], "max_hp": p["max_hp"], "job": p["job"]}

def broadcast_online():
    with STATE_LOCK:
        seen = {q["id"]: q for q in connected_players.values()}
        payload = {"count": len(seen), "players": [
            {"username": q["username"], "level": q["level"], "job": q["job"], "map": q["map"]}
            for q in seen.values()]}
    socketio.emit("online_players", payload)

def cleanup_player(sid, announce=True):
    with STATE_LOCK:
        p = connected_players.pop(sid, None)
        for k in [k for k in _rate_limit if k[0] == sid]:
            _rate_limit.pop(k, None)
    if not p:
        return None
    try:
        with get_db() as conn:
            conn.execute("UPDATE users SET x=?, y=?, map=?, hp=?, mp=? WHERE id=?",
                         (p["x"], p["y"], p["map"], p["hp"], p["mp"], p["id"]))
    except Exception:
        log.exception("cleanup save failed")
    if announce:
        socketio.emit("remove_player", {"sid": sid}, room=p["map"])
        socketio.emit("system_message", {"message": f"💤 {p['username']} ออกจากเกม"})
    broadcast_online()
    return p

def switch_rooms(sid, old_map, new_map):
    if old_map == new_map:
        return
    socketio.server.leave_room(sid, old_map, namespace="/")
    socketio.server.enter_room(sid, new_map, namespace="/")
    socketio.emit("player_left_map", {"sid": sid}, room=old_map)
    with STATE_LOCK:
        room_players = {s: public_player_info(s, q) for s, q in connected_players.items() if q["map"] == new_map}
        sync = [serialize_monster(m) for m in MONSTER_INSTANCES.get(new_map, {}).values()]
        gitems = [serialize_ground_item(g) for g in GROUND_ITEMS.get(new_map, {}).values()]
    socketio.emit("players_in_map", room_players, room=new_map)
    socketio.emit("monsters_sync", {"map": new_map, "monsters": sync}, room=sid)
    socketio.emit("npcs_sync", {"map": new_map, "npcs": NPCS.get(new_map, [])}, room=sid)
    socketio.emit("ground_items_sync", {"map": new_map, "items": gitems}, room=sid)

def random_point(avoid=None, min_dist=150.0):
    for _ in range(25):
        x, y = random.uniform(60.0, 740.0), random.uniform(80.0, 520.0)
        if avoid and math.hypot(x - avoid[0], y - avoid[1]) < min_dist:
            continue
        return x, y
    return random.uniform(60.0, 740.0), random.uniform(80.0, 520.0)

def make_instance(md):
    boss = bool(md.get("boss"))
    return {"id": md["id"], "base_id": md["id"], "name": md["name"], "level": md["level"],
            "boss": boss, "hp": md["hp"], "max_hp": md["hp"],
            "atk": md["atk"], "def": md["def"], "exp": md["exp"], "gold": md["gold"],
            "respawn_sec": md.get("respawn", 20), "aggressive": bool(md.get("aggressive", boss)),
            "x": 400.0, "y": 300.0, "home_x": 400.0, "home_y": 300.0,
            "alive": True, "respawn_at": 0.0, "threat": {}, "contrib": {}, "target": None,
            "atk_cd_until": 0.0, "stun_until": 0.0, "dot": None,
            "last_hit_t": 0.0, "wander_at": 0.0, "enraged": False, "slam_at": 0.0,
            "spawn_until": 0.0}                       # [v5.1.1] ช่วงตกลงมาหลังเกิดใหม่

def serialize_monster(m):
    return {"id": m["id"], "base_id": m.get("base_id", m["id"]), "name": m["name"], "level": m["level"],
            "boss": m["boss"], "hp": m["hp"], "max_hp": m["max_hp"], "alive": m["alive"],
            "x": round(m["x"], 1), "y": round(m["y"], 1), "enraged": m["enraged"],
            "aggro": m["target"] is not None, "stunned": time.time() < m["stun_until"]}

def serialize_ground_item(g):
    return {"id": g["id"], "item_id": g["item_id"], "name": g["name"],
            "x": round(g["x"], 1), "y": round(g["y"], 1), "ttl": max(0, int(g["expire"] - time.time()))}

def roll_drops(inst):
    table = DROP_TABLES.get(inst.get("base_id"), [])
    return [iid for iid, chance in table if random.random() < chance][:3]

def spawn_ground_items(map_name, x, y, item_ids):
    created = []
    with STATE_LOCK:
        bucket = GROUND_ITEMS.setdefault(map_name, {})
        while len(bucket) >= GROUND_CAP_PER_MAP:
            bucket.pop(next(iter(bucket)))
        for iid in item_ids:
            meta = GD.ITEMS.get(iid)
            if not meta:
                continue
            gid = f"g{int(time.time()*1000)%100000000}_{random.randint(100,999)}"
            g = {"id": gid, "item_id": iid, "name": meta["name"],
                 "x": clamp(x + random.uniform(-30, 30), 20, 780),
                 "y": clamp(y + random.uniform(-26, 26), 20, 580),
                 "expire": time.time() + GROUND_ITEM_TTL}
            bucket[gid] = g
            created.append(g)
    for g in created:
        socketio.emit("item_dropped", serialize_ground_item(g), room=map_name)

def spawn_all_monsters():
    with STATE_LOCK:
        for map_name, defs in GD.MONSTERS.items():
            insts, seen = {}, set()
            avoid = MAP_SPAWNS.get(map_name, (400.0, 300.0))
            for i, md in enumerate(defs):
                mkey = f"{md['id']}_{i}" if md["id"] in seen else str(md["id"])
                seen.add(md["id"])
                inst = make_instance(md)
                inst["id"] = mkey
                hx, hy = random_point(avoid=avoid)
                inst["x"] = inst["home_x"] = hx
                inst["y"] = inst["home_y"] = hy
                insts[mkey] = inst
            MONSTER_INSTANCES[map_name] = insts
    log.info("Monsters spawned: %s maps", len(MONSTER_INSTANCES))

def find_monster(map_name, mid):
    insts = MONSTER_INSTANCES.get(map_name, {})
    return insts.get(mid) or insts.get(str(mid))

def respawn_monster(m, map_name):
    avoid = MAP_SPAWNS.get(map_name, (400.0, 300.0))
    hx, hy = random_point(avoid=avoid)
    m["home_x"], m["home_y"], m["x"], m["y"] = hx, hy, hx, hy
    m["hp"] = m["max_hp"]
    m["alive"] = True
    m.update(threat={}, contrib={}, target=None, atk_cd_until=0.0, stun_until=0.0,
             dot=None, enraged=False, slam_at=0.0, last_hit_t=0.0)
    m["spawn_until"] = time.time() + MONSTER_SPAWN_FALL   # [v5.1.1] ตกลงมา: ยังไม่สู้/ยังไม่โดนตี

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

def rate_ok(sid, action, seconds):
    now = time.time()
    key = (sid, action)
    if now - _rate_limit.get(key, 0) < seconds:
        return False
    _rate_limit[key] = now
    return True

def roll_damage(atk, defense, mult=1.0, crit_chance=CRIT_CHANCE):
    base = atk * mult - defense / 2.0
    base = max(1.0, base) * random.uniform(1 - DMG_VARIANCE, 1 + DMG_VARIANCE)
    crit = random.random() < crit_chance
    if crit:
        base *= CRIT_MULT
    return max(1, int(round(base))), crit

def exp_modifier(player_lv, monster_lv):
    diff = monster_lv - player_lv
    if diff >= 5: return 1.2
    if diff >= -4: return 1.0
    if diff >= -9: return 0.5
    return 0.1

def apply_level_up(conn, user_row):
    user = dict(user_row)
    leveled = False
    while user["exp"] >= user["max_exp"] and user["level"] < 999:
        user["exp"] -= user["max_exp"]
        user["level"] += 1
        user["max_exp"] = int(80 + user["level"] * user["level"] * 18)
        g = GD.JOBS.get(user["job"], GD.JOBS["Novice"])["g"]
        user["max_hp"] += g["hp"]; user["max_mp"] += g["mp"]
        user["atk"] += g["atk"]; user["def"] += g["def"]
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
        row = conn.execute("SELECT * FROM user_quests WHERE user_id=? AND quest_id=?", (user_id, qid)).fetchone()
        if row is None:
            conn.execute("INSERT INTO user_quests (user_id, quest_id, progress, status) VALUES (?,?,1,'active')", (user_id, qid))
        elif row["status"] == "active":
            new_prog = row["progress"] + 1
            status = "done" if new_prog >= q["target_count"] else "active"
            conn.execute("UPDATE user_quests SET progress=?, status=? WHERE id=?", (new_prog, status, row["id"]))

def hit_monster(inst, p, dmg, now, threat_mult=1.0):
    """ตีมอน: บันทึก contrib/threat + มอนสู้กลับ/สลับเป้าตาม threat"""
    if not inst["alive"]:
        return None
    real = min(dmg, inst["hp"])
    inst["hp"] -= real
    inst["last_hit_t"] = now
    uid = p["id"]
    inst["contrib"][uid] = inst["contrib"].get(uid, 0) + real
    inst["threat"][uid] = inst["threat"].get(uid, 0) + dmg * threat_mult
    cur = inst.get("target")
    if cur is None:
        inst["target"] = uid
    elif uid != cur:
        if inst["threat"].get(uid, 0) > inst["threat"].get(cur, 0) * 1.4:
            inst["target"] = uid
    if inst["hp"] <= 0:
        inst["alive"] = False
        inst["respawn_at"] = now + inst["respawn_sec"]
        inst["target"] = None
        inst["dot"] = None
        snap = dict(inst)
        inst["contrib"] = {}
        inst["threat"] = {}
        return snap
    return None

def award_kill(conn, uid, exp, gold, monster):
    found = find_player_by_uid(uid)
    if found and found[1]["hp"] <= 0:
        return None
    flush_vitals_by_uid(conn, uid)
    row = get_user_by_id(conn, uid)
    if row is None:
        return None
    exp = max(1, int(exp * exp_modifier(row["level"], monster["level"])))
    conn.execute("UPDATE users SET exp=exp+?, gold=gold+?, kills=kills+1 WHERE id=?", (exp, gold, uid))
    update_quest_progress(conn, uid, monster.get("base_id", monster["id"]))
    row = get_user_by_id(conn, uid)
    user, leveled = apply_level_up(conn, row)
    sync_memory_stats(user_to_dict(user), vitals=leveled)
    return {"exp_gain": exp, "gold_gain": gold, "leveled_up": leveled, "user": live_user(user)}

def distribute_kill(snap, killer_uid, killer_name):
    contrib = snap.get("contrib") or {killer_uid: 1}
    total = sum(contrib.values()) or 1
    killer_result = None
    with get_db() as conn:
        for uid, dmg in contrib.items():
            share = dmg / total
            if share < MIN_SHARE and uid != killer_uid:
                continue
            exp, gold = int(snap["exp"] * share), int(snap["gold"] * share)
            if uid == killer_uid:
                exp += int(snap["exp"] * LAST_HIT_BONUS)
                gold += int(snap["gold"] * LAST_HIT_BONUS)
            res = award_kill(conn, uid, exp, gold, snap)
            if res is None:
                continue
            if uid == killer_uid:
                killer_result = res
            found = find_player_by_uid(uid)
            if found:
                if res["leveled_up"]:
                    fx_shake(found[0], 9, 0.45, extra={"type": "levelup"})
                socketio.emit("kill_reward", {"monster": snap["name"], "share": round(share, 2), **res}, room=found[0])
    map_name = _map_of_monster(snap)
    drops = roll_drops(snap)
    if map_name and drops:
        spawn_ground_items(map_name, snap["x"], snap["y"], drops)
    socketio.emit("monster_killed", {"monster_id": snap["id"], "name": snap["name"], "killer": killer_name}, room=map_name)
    if snap["boss"]:
        fx_shake(None, 10, 0.5, extra={"type": "boss"})
        socketio.emit("system_message", {"message": f"👑 {killer_name} ปราบบอส {snap['name']} สำเร็จ!"})
    return killer_result or {}

def _map_of_monster(snap):
    with STATE_LOCK:
        for map_name, insts in MONSTER_INSTANCES.items():
            if snap["id"] in insts and insts[snap["id"]]["name"] == snap["name"]:
                return map_name
    return None

def take_damage(p, dmg, now):
    with STATE_LOCK:
        if p["hp"] <= 0 or now < p.get("invuln_until", 0):
            return None
        p["hp"] = max(0, p["hp"] - dmg)
        p["last_combat"] = now
        return p["hp"]

def handle_player_death(sid, p, killer_name, pvp=False):
    now = time.time()
    with STATE_LOCK:
        if p.get("dead_handled"):
            return
        p["dead_handled"] = True
        p["hp"] = 0
        p["dead_at"] = now
        p["buffs"] = {}
        for m in MONSTER_INSTANCES.get(p["map"], {}).values():
            m["threat"].pop(p["id"], None)
            if m["target"] == p["id"]:
                m["target"] = None
    exp_lost = gold_lost = 0
    try:
        with get_db() as conn:
            row = get_user_by_id(conn, p["id"])
            if row is not None and not pvp:
                exp_lost = int(row["exp"] * DEATH_EXP_LOSS)
                gold_lost = int(row["gold"] * DEATH_GOLD_LOSS)
            conn.execute("UPDATE users SET hp=0, mp=?, exp=MAX(0, exp-?), gold=MAX(0, gold-?) WHERE id=?",
                         (p["mp"], exp_lost, gold_lost, p["id"]))
    except Exception:
        log.exception("death save failed")
    socketio.emit("player_died", {"killer": killer_name, "pvp": pvp, "exp_lost": exp_lost,
                                  "gold_lost": gold_lost, "respawn_delay": RESPAWN_DELAY}, room=sid)
    fx_shake(sid, 12, 0.5, extra={"type": "death"})
    socketio.emit("combat_fx", {"type": "player_died", "sid": sid}, room=p["map"])
    socketio.emit("system_message", {"message": f"💀 {p['username']} ถูก {killer_name} ปราบ"}, room=p["map"])

def do_respawn(uid):
    now = time.time()
    found = find_player_by_uid(uid)
    sid, p = found if found else (None, None)
    with get_db() as conn:
        row = get_user_by_id(conn, uid)
        if row is None:
            return None, "ไม่พบผู้เล่น"
        dead = (p["hp"] <= 0) if p else (row["hp"] <= 0)
        if not dead:
            return None, "ยังไม่ได้สลบ"
        if p and now - p.get("dead_at", 0) < RESPAWN_DELAY:
            wait = int(RESPAWN_DELAY - (now - p["dead_at"])) + 1
            return None, f"รออีก {wait} วินาที"
        conn.execute("UPDATE users SET hp=max_hp, mp=max_mp, map='town', x=400, y=300 WHERE id=?", (uid,))
        row = get_user_by_id(conn, uid)
    user_d = user_to_dict(row)
    if p:
        with STATE_LOCK:
            old_map = p["map"]
            p.update(hp=user_d["maxHp"], mp=user_d["maxMp"], x=400.0, y=300.0, map="town",
                     invuln_until=now + SPAWN_PROTECT, dead_handled=False, dead_at=0.0,
                     last_combat=0.0, buffs={}, last_move_t=now)
        switch_rooms(sid, old_map, "town")
        socketio.emit("move_player", public_player_info(sid, p), room="town")
        socketio.emit("stats_update", {"hp": user_d["maxHp"], "mp": user_d["maxMp"]}, room=sid)
        socketio.emit("respawned", {"user": user_d, "map": "town", "protect": SPAWN_PROTECT}, room=sid)
    return user_d, None

# ---------------- REST: Auth ----------------
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
        return jsonify({"success": False, "message": "ชื่อต้องยาว 3-20 ตัวอักษร"}), 400
    if len(password) < 6:
        return jsonify({"success": False, "message": "รหัสผ่านต้องยาว 6+ ตัวอักษร"}), 400
    # [FIX] สมัครได้เฉพาะ Novice / อาชีพขั้น 1 (กันสมัครเป็น Knight/Wizard ตั้งแต่เริ่ม)
    if job not in GD.JOBS or GD.JOBS[job]["tier"] > 1:
        job = "Novice"
    stats = GD.JOBS[job]
    try:
        with get_db() as conn:
            conn.execute("""INSERT INTO users (username, password_hash, job, hp, max_hp, mp, max_mp, atk, def)
                            VALUES (?,?,?,?,?,?,?,?,?)""",
                         (username, generate_password_hash(password), job,
                          stats["hp"], stats["hp"], stats["mp"], stats["mp"], stats["atk"], stats["def"]))
        return jsonify({"success": True, "message": "สร้างตัวละครสำเร็จ!"})
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "ชื่อนี้ถูกใช้งานแล้ว"}), 409

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
            return jsonify({"success": False, "message": "บัญชีนี้ถูกระงับ"}), 403
        if ADMIN_USERNAME and row["username"] == ADMIN_USERNAME and not row["is_admin"]:
            conn.execute("UPDATE users SET is_admin=1 WHERE id=?", (row["id"],))
        conn.execute("UPDATE users SET last_login=? WHERE id=?", (now_iso(), row["id"]))
        row = recalc_stats(conn, row["id"])          # [FIX] แก้ค่าสถานะที่เพี้ยนตั้งแต่ตอนล็อกอิน
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
    return jsonify({"success": True, "user": live_user(row)})

# ---------------- REST: ข้อมูลเกม ----------------
@app.route("/api/inventory/<int:user_id>")
def get_inventory(user_id):
    uid, err = authorize(user_id)
    if err:
        return err
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM inventory WHERE user_id=? ORDER BY equipped DESC, item_id",
                            (uid,)).fetchall()
    items = []
    for r in rows:
        meta = GD.ITEMS.get(r["item_id"], {})
        # [FIX] ส่งค่าตีบวก/ช่อง/สเตตัสไปให้กระเป๋าหลักด้วย
        items.append({"id": r["id"], "itemId": r["item_id"], "name": meta.get("name", "?"),
                      "type": meta.get("type"), "slot": meta.get("slot"),
                      "atk": meta.get("atk", 0), "def": meta.get("def", 0),
                      "enhance": r["enhance"] or 0,
                      "quantity": r["quantity"], "equipped": bool(r["equipped"]),
                      "price": meta.get("price", 0), "sell_price": meta.get("sell_price", 0),
                      "level_req": meta.get("level_req", 1)})
    return jsonify({"success": True, "inventory": items})

@app.route("/api/monsters/<map_name>")
def get_monsters(map_name):
    if map_name not in GD.MAPS:
        return jsonify({"success": True, "monsters": []})
    with STATE_LOCK:
        return jsonify({"success": True, "monsters": [serialize_monster(m) for m in MONSTER_INSTANCES.get(map_name, {}).values()]})

@app.route("/api/maps")
def get_maps():
    return jsonify({"success": True, "maps": MAP_META})

@app.route("/api/shop")
def get_shop():
    items = [{"id": iid, **meta} for iid, meta in sorted(GD.ITEMS.items()) if meta.get("type") == "potion"]
    return jsonify({"success": True, "items": items})

@app.route("/api/jobs")
def get_jobs():
    return jsonify({"success": True, "jobs": GD.JOBS})

@app.route("/api/skills")
def get_skills():
    job = request.args.get("job")
    return jsonify({"success": True, "skills": {k: v for k, v in GD.SKILLS.items() if not job or v["job"] in ("All", job)}})

@app.route("/api/quests/<int:user_id>")
def get_quests(user_id):
    uid, err = authorize(user_id)
    if err:
        return err
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM user_quests WHERE user_id=?", (uid,)).fetchall()
    active = {r["quest_id"]: r for r in rows}
    result = [{"id": qid, **q, "progress": prog["progress"] if prog else 0,
               "status": prog["status"] if prog else "not_started"}
              for qid, q in GD.QUESTS.items() for prog in [active.get(qid)]]
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
        return jsonify({"success": True, "count": len(seen),
                        "players": [{"username": q["username"], "level": q["level"], "job": q["job"], "map": q["map"]} for q in seen.values()]})

# ---------------- REST: ธุรกรรม ----------------
@app.route("/api/shop/buy", methods=["POST"])
def buy_item():
    data = request.json or {}
    uid, err = authorize(data.get("user_id"))
    if err:
        return err
    try:
        item_id = int(data.get("item_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "ข้อมูลไม่ถูกต้อง"}), 400
    item = GD.ITEMS.get(item_id)
    # [FIX] ร้านยาขายเฉพาะโพชั่น (อาวุธ/หินต้องซื้อที่ช่างตีเหล็ก)
    if not item or item.get("type") != "potion":
        return jsonify({"success": False, "message": "ไม่พบไอเทมในร้านนี้"}), 404
    with get_db() as conn:
        user = get_user_by_id(conn, uid)
        if user["gold"] < item["price"]:
            return jsonify({"success": False, "message": "เงินไม่พอ"}), 400
        if user["level"] < item.get("level_req", 1):
            return jsonify({"success": False, "message": "เลเวลไม่ถึง"}), 400
        conn.execute("UPDATE users SET gold=gold-? WHERE id=?", (item["price"], uid))
        existing = conn.execute("SELECT * FROM inventory WHERE user_id=? AND item_id=? AND equipped=0",
                                (uid, item_id)).fetchone()
        if existing:
            conn.execute("UPDATE inventory SET quantity=quantity+1 WHERE id=?", (existing["id"],))
        else:
            conn.execute("INSERT INTO inventory (user_id, item_id, quantity) VALUES (?,?,1)", (uid, item_id))
        user = get_user_by_id(conn, uid)
    return jsonify({"success": True, "user": live_user(user)})

@app.route("/api/shop/sell", methods=["POST"])
def sell_item():
    """ขายไอเทมให้บอทรับซื้อ — ใช้ได้จากทุกที่ (กระเป๋า/ร้าน/บอท)"""
    data = request.json or {}
    uid, err = authorize(data.get("user_id"))
    if err:
        return err
    try:
        inv_id = int(data.get("inventory_id"))
        qty = max(1, int(data.get("quantity", 1)))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "ข้อมูลไม่ถูกต้อง"}), 400
    with get_db() as conn:
        row = conn.execute("SELECT * FROM inventory WHERE id=? AND user_id=?", (inv_id, uid)).fetchone()
        if not row:
            return jsonify({"success": False, "message": "ไม่พบไอเทม"}), 404
        # [FIX] ห้ามขายของที่สวมอยู่ (เดิมขายได้ แต่ ATK/DEF ค้าง → บั๊กปั๊มสเตตัส)
        if row["equipped"]:
            return jsonify({"success": False, "message": "ถอดอุปกรณ์ก่อนขาย"}), 400
        qty = min(qty, row["quantity"])
        meta = GD.ITEMS.get(row["item_id"], {})
        unit = int(meta.get("sell_price", max(1, int(meta.get("price", 10) * 0.4))))
        total = unit * qty
        remain = row["quantity"] - qty
        if remain <= 0:
            conn.execute("DELETE FROM inventory WHERE id=?", (row["id"],))
        else:
            conn.execute("UPDATE inventory SET quantity=? WHERE id=?", (remain, row["id"]))
        conn.execute("UPDATE users SET gold=gold+? WHERE id=?", (total, uid))
        user = get_user_by_id(conn, uid)
    return jsonify({"success": True, "earned": total, "unit": unit,
                    "item_name": meta.get("name", "?"), "user": live_user(user)})

@app.route("/api/job/change", methods=["POST"])
def job_change():
    data = request.json or {}
    uid, err = authorize(data.get("user_id"))
    if err:
        return err
    target = data.get("job")
    with get_db() as conn:
        row = get_user_by_id(conn, uid)
        if row is None:
            return jsonify({"success": False, "message": "ไม่พบผู้เล่น"}), 404
        cur = GD.JOBS.get(row["job"])
        adv = cur.get("advance", {}) if cur else {}
        if target not in adv:
            return jsonify({"success": False, "message": "อาชีพนี้ไม่สามารถเลื่อนเป็น " + str(target)}), 400
        req_lv, req_gold = adv[target]
        if row["level"] < req_lv:
            return jsonify({"success": False, "message": f"ต้องเลเวล {req_lv} ขึ้นไป (ตอนนี้ Lv.{row['level']})"}), 400
        if row["gold"] < req_gold:
            return jsonify({"success": False, "message": f"ต้องใช้ {req_gold} G (มี {row['gold']} G)"}), 400
        base = GD.JOBS[target]
        g = base["g"]
        lv = row["level"]
        max_hp = base["hp"] + g["hp"] * (lv - 1)
        max_mp = base["mp"] + g["mp"] * (lv - 1)
        conn.execute("""UPDATE users SET job=?, gold=gold-?, max_hp=?, max_mp=?,
                        hp=?, mp=? WHERE id=?""",
                     (target, req_gold, max_hp, max_mp, max_hp, max_mp, uid))
        # [FIX] ATK/DEF คำนวณใหม่ "รวมอุปกรณ์ + ตีบวก" (เดิมคิดแค่ฐานอาชีพ → โบนัสหายหมด)
        user_row = recalc_stats(conn, uid)
    user_d = user_to_dict(user_row)
    sync_memory_stats(user_d, vitals=True)
    socketio.emit("system_message", {"message": f"🏅 {user_d['username']} เลื่อนอาชีพเป็น {target}!"})
    return jsonify({"success": True, "user": user_d, "message": f"เลื่อนอาชีพเป็น {target} สำเร็จ!"})

@app.route("/api/quests/claim", methods=["POST"])
def claim_quest():
    data = request.json or {}
    uid, err = authorize(data.get("user_id"))
    if err:
        return err
    quest = GD.QUESTS.get(data.get("quest_id"))
    if not quest:
        return jsonify({"success": False, "message": "ไม่พบเควส"}), 404
    with get_db() as conn:
        row = conn.execute("SELECT * FROM user_quests WHERE user_id=? AND quest_id=?", (uid, data.get("quest_id"))).fetchone()
        if row is None or row["status"] != "done":
            return jsonify({"success": False, "message": "เควสยังไม่สำเร็จ"}), 400
        conn.execute("UPDATE user_quests SET status='claimed' WHERE id=?", (row["id"],))
        conn.execute("UPDATE users SET gold=gold+?, exp=exp+? WHERE id=?", (quest["reward_gold"], quest["reward_exp"], uid))
        flush_vitals_by_uid(conn, uid)
        user, leveled = apply_level_up(conn, get_user_by_id(conn, uid))
        user_row = get_user_by_id(conn, uid)
    sync_memory_stats(user_to_dict(user_row), vitals=leveled)
    return jsonify({"success": True, "user": live_user(user_row), "leveled_up": leveled})

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
            return jsonify({"success": False, "message": "วันนี้รับไปแล้ว"}), 400
        reward = 100 + user["level"] * 50
        conn.execute("UPDATE users SET gold=gold+?, last_daily=? WHERE id=?", (reward, today, uid))
        user = get_user_by_id(conn, uid)
    return jsonify({"success": True, "reward": reward, "user": live_user(user)})

# ---------------- REST: Market ----------------
@app.route("/api/market/state")
def market_state_api():
    uid, err = authorize()
    if err:
        return err
    with MARKET_LOCK:
        return jsonify({"success": True, "price": round(MARKET["price"], 2),
                        "hist": MARKET["hist"][-120:],
                        "position": POSITIONS.get(uid),
                        "orders": MARKET_ORDERS.get(uid, []),
                        "margin_rate": MARGIN_RATE, "fee": TRADE_FEE})

@app.route("/api/market/order", methods=["POST"])
def market_order_api():
    uid, err = authorize()
    if err:
        return err
    data = request.json or {}
    side = data.get("side")
    otype = data.get("otype", "market")
    try:
        qty = max(1, int(data.get("qty", 1)))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "จำนวนไม่ถูกต้อง"}), 400
    if side not in ("long", "short"):
        return jsonify({"success": False, "message": "side ต้องเป็น long/short"}), 400
    with MARKET_LOCK:
        # [FIX] เช็กสถานะฝั่งตรงข้ามภายใน lock (กัน race กับ market_loop)
        if POSITIONS.get(uid) and POSITIONS[uid]["side"] != side:
            return jsonify({"success": False, "message": "มีสถานะฝั่งตรงข้ามอยู่ — ปิดสถานะก่อน"}), 400
        price = MARKET["price"]
        if otype == "market":
            ok, msg = _open_position(uid, side, qty, price)
            if not ok:
                return jsonify({"success": False, "message": msg}), 400
        else:
            try:
                limit = float(data.get("limit_price"))
            except (TypeError, ValueError):
                return jsonify({"success": False, "message": "ระบุราคา limit"}), 400
            lst = MARKET_ORDERS.setdefault(uid, [])
            lst.append({"id": f"o{int(time.time()*1000)%100000000}", "side": side, "qty": qty, "limit": limit})
            _emit_state(uid, {"msg": f"📋 ตั้งออเดอร์ {side.upper()} {qty} @ {limit}"})
    return jsonify({"success": True})

@app.route("/api/market/close", methods=["POST"])
def market_close_api():
    uid, err = authorize()
    if err:
        return err
    with MARKET_LOCK:
        if uid not in POSITIONS:
            return jsonify({"success": False, "message": "ไม่มีสถานะเปิดอยู่"}), 400
        _close_position(uid, MARKET["price"], reason="manual")
    return jsonify({"success": True})

@app.route("/api/market/cancel", methods=["POST"])
def market_cancel_api():
    uid, err = authorize()
    if err:
        return err
    oid = str((request.json or {}).get("order_id") or "")
    with MARKET_LOCK:
        lst = MARKET_ORDERS.get(uid, [])
        MARKET_ORDERS[uid] = [o for o in lst if o["id"] != oid]
        _emit_state(uid, {"msg": "🚫 ยกเลิกออเดอร์แล้ว"})
    return jsonify({"success": True})

@app.route("/api/market/tpsl", methods=["POST"])
def market_tpsl_api():
    uid, err = authorize()
    if err:
        return err
    data = request.json or {}
    with MARKET_LOCK:
        pos = POSITIONS.get(uid)
        if not pos:
            return jsonify({"success": False, "message": "ไม่มีสถานะ"}), 400
        for k in ("tp", "sl"):
            v = data.get(k)
            try:
                pos[k] = float(v) if v not in (None, "", 0) else None
            except (TypeError, ValueError):
                return jsonify({"success": False, "message": f"ค่า {k.upper()} ไม่ถูกต้อง"}), 400
        _emit_state(uid, {"msg": "🎯 ตั้ง TP/SL แล้ว"})
    return jsonify({"success": True})

# ---------------- REST: Admin ----------------
def _require_admin():
    uid = session.get("user_id")
    if uid is None:
        return None, (jsonify({"success": False, "message": "กรุณาเข้าสู่ระบบ"}), 401)
    with get_db() as conn:
        row = get_user_by_id(conn, uid)
        if not row or not row["is_admin"]:
            return None, (jsonify({"success": False, "message": "ไม่มีสิทธิ์แอดมิน"}), 403)
    return row, None

@app.route("/api/admin/broadcast", methods=["POST"])
def admin_broadcast():
    admin, err = _require_admin()
    if err:
        return err
    msg = ((request.json or {}).get("message") or "").strip()[:300]
    if not msg:
        return jsonify({"success": False, "message": "ข้อความว่าง"}), 400
    with get_db() as conn:   # [FIX] เก็บประวัติประกาศ
        conn.execute("INSERT INTO chat_log (username, channel, message) VALUES (?,?,?)",
                     (admin["username"], "sys", "[Admin] " + msg))
    socketio.emit("system_message", {"message": f"📢 [Admin] {msg}"})
    return jsonify({"success": True, "message": "ประกาศแล้ว"})

@app.route("/api/admin/ban", methods=["POST"])
def admin_ban():
    """[FIX] สลับ แบน ↔ ปลดแบน + เตะออกทันทีเมื่อแบน"""
    admin, err = _require_admin()
    if err:
        return err
    username = ((request.json or {}).get("username") or "").strip()
    if not username:
        return jsonify({"success": False, "message": "ระบุชื่อผู้เล่น"}), 400
    if username == admin["username"]:
        return jsonify({"success": False, "message": "แบนตัวเองไม่ได้"}), 400
    with get_db() as conn:
        row = conn.execute("SELECT id, is_admin, is_banned FROM users WHERE username=?", (username,)).fetchone()
        if row is None:
            return jsonify({"success": False, "message": "ไม่พบผู้เล่นนี้"}), 404
        if row["is_admin"]:
            return jsonify({"success": False, "message": "แบนแอดมินไม่ได้"}), 400
        banned = not row["is_banned"]
        conn.execute("UPDATE users SET is_banned=? WHERE id=?", (1 if banned else 0, row["id"]))
    action = "แบน" if banned else "ปลดแบน"
    if banned:
        dup = find_sid_by_uid(row["id"])
        if dup:
            socketio.emit("force_disconnect", {"reason": "บัญชีถูกระงับ"}, room=dup)
            cleanup_player(dup, announce=False)
    socketio.emit("system_message", {"message": f"🔨 {action}ผู้เล่น {username} แล้ว"})
    return jsonify({"success": True, "banned": banned, "message": f"{action} {username} สำเร็จ"})

# ---------------- Socket.IO ----------------
@socketio.on("join_game")
def handle_join(data):
    sid = request.sid
    uid = (data or {}).get("id")
    sess_uid = session.get("user_id")
    try:
        uid = int(uid)
    except (TypeError, ValueError):
        pass
    if uid is None or sess_uid is None or str(uid) != str(sess_uid):
        emit("force_disconnect", {"reason": "session ไม่ถูกต้อง"})
        return
    with get_db() as conn:
        user = get_user_by_id(conn, uid)
        if user is None or user["is_banned"]:
            emit("force_disconnect", {"reason": "banned"})
            return
        conn.execute("UPDATE users SET last_login=? WHERE id=?", (now_iso(), uid))
        user = recalc_stats(conn, uid)              # [FIX] ATK/DEF ถูกต้องเสมอตอนเข้าเกม
    dup = None
    with STATE_LOCK:
        for s, q in connected_players.items():
            if q["id"] == uid and s != sid:
                dup = s
                break
    if dup:
        socketio.emit("force_disconnect", {"reason": "มีการล็อกอินจากที่อื่น"}, room=dup)
        cleanup_player(dup, announce=False)
    map_name = user["map"] if user["map"] in GD.MAPS else "town"
    is_dead = user["hp"] <= 0
    now = time.time()
    with STATE_LOCK:
        connected_players[sid] = {
            "id": user["id"], "username": user["username"], "job": user["job"],
            "level": user["level"], "hp": user["hp"], "mp": user["mp"],
            "max_hp": user["max_hp"], "max_mp": user["max_mp"],
            "atk": user["atk"], "def": user["def"],
            "x": clamp(float(user["x"]), 20, 780), "y": clamp(float(user["y"]), 20, 580),
            "map": map_name, "is_admin": bool(user["is_admin"]),
            "skill_cd": {}, "last_move_t": now, "buffs": {}, "last_combat": 0.0,
            "invuln_until": now + SPAWN_PROTECT, "dead_handled": is_dead, "dead_at": 0.0,
        }
        room_players = {s: public_player_info(s, q) for s, q in connected_players.items() if q["map"] == map_name}
        sync = [serialize_monster(m) for m in MONSTER_INSTANCES.get(map_name, {}).values()]
        gitems = [serialize_ground_item(g) for g in GROUND_ITEMS.get(map_name, {}).values()]
    join_room(map_name)
    emit("players_in_map", room_players, room=map_name)
    emit("monsters_sync", {"map": map_name, "monsters": sync}, room=sid)
    emit("npcs_sync", {"map": map_name, "npcs": NPCS.get(map_name, [])}, room=sid)
    emit("ground_items_sync", {"map": map_name, "items": gitems}, room=sid)
    emit("stats_update", {"hp": user["hp"], "mp": user["mp"]}, room=sid)
    emit("ext_stats", {"atk": user["atk"], "def": user["def"]}, room=sid)   # [FIX] ให้ HUD เห็นค่าล่าสุด
    if is_dead:
        emit("player_died", {"killer": "-", "pvp": False, "exp_lost": 0, "gold_lost": 0, "respawn_delay": 0}, room=sid)
    broadcast_online()
    socketio.emit("system_message", {"message": f"⚡ {user['username']} เข้าสู่โลก Gemivara"})
    log.info("Player %s joined %s", user["username"], map_name)

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
    old_map = p["map"]
    changed = new_map != old_map
    now = time.time()
    if changed:
        x, y = MAP_SPAWNS.get(new_map, (400.0, 300.0))
    else:
        dt = max(0.05, min(1.0, now - p.get("last_move_t", now)))
        dist = math.hypot(x - p["x"], y - p["y"])
        max_step = MAX_MOVE_SPEED * dt
        if dist > max_step and dist > 0:
            scale = max_step / dist
            x, y = p["x"] + (x - p["x"]) * scale, p["y"] + (y - p["y"]) * scale
    with STATE_LOCK:
        p.update(x=x, y=y, last_move_t=now)
        if changed:
            p["map"] = new_map
        payload = public_player_info(sid, p)
    if changed:
        switch_rooms(sid, old_map, new_map)
        socketio.emit("move_player", payload, room=new_map)
    else:
        emit("move_player", payload, room=p["map"], include_self=False)

@socketio.on("disconnect")
def handle_disconnect():
    p = cleanup_player(request.sid, announce=True)
    if p:
        log.info("Player %s disconnected", p.get("username"))

@socketio.on("attack_monster")
def handle_attack(data):
    sid = request.sid
    p = connected_players.get(sid)
    if not p:
        return
    if not rate_ok(sid, "attack", ATTACK_COOLDOWN):
        return
    if p["hp"] <= 0:
        emit("attack_result", {"success": False, "message": "คุณสลบอยู่"})
        return
    if p["map"] == "town":
        emit("attack_result", {"success": False, "message": "ในเมืองต่อสู้ไม่ได้"})
        return
    mid = data.get("monster_id")
    now = time.time()
    err, dmg, crit, dodged, killed, state, hp_left = None, 0, False, False, None, None, 0
    shake = 0
    with STATE_LOCK:
        inst = find_monster(p["map"], mid)
        if not inst or not inst["alive"]:
            err = "ไม่พบมอนสเตอร์ (หรือรอเกิดใหม่)"
        elif now < inst.get("spawn_until", 0):                      # [v5.1.1] ยังตกลงมาไม่ถึงพื้น
            err = "มอนสเตอร์กำลังตกลงมา"
        elif math.hypot(p["x"] - inst["x"], p["y"] - inst["y"]) > ATTACK_RANGE:
            err = "มอนสเตอร์อยู่ไกลเกินระยะโจมตี"
        else:
            p["last_combat"] = now
            if random.random() < MONSTER_DODGE:
                dodged, shake = True, 2
                inst["threat"][p["id"]] = inst["threat"].get(p["id"], 0) + 1
                inst["last_hit_t"] = now
                if inst["target"] is None:
                    inst["target"] = p["id"]          # หลบแต่ยังโกรธ
            else:
                dmg, crit = roll_damage(eff_stat(p, "atk", now), inst["def"])
                killed = hit_monster(inst, p, dmg, now)
                shake = SHAKE_KILL if killed else (SHAKE_HIT_CRIT if crit else SHAKE_HIT)
            hp_left = inst["hp"]
            state = serialize_monster(inst)
    if err:
        emit("attack_result", {"success": False, "message": err})
        return
    fx_shake(p["map"] if (crit or killed is not None) else sid, shake,
             0.3 if (crit or killed is not None) else 0.22)
    socketio.emit("monsters_update", {"map": p["map"], "monsters": [state]}, room=p["map"])
    socketio.emit("combat_fx", {"type": "hit", "monster_id": str(mid), "dmg": dmg, "crit": crit,
                                "dodged": dodged, "by": p["username"]}, room=p["map"])
    result = {"success": True, "monster_id": mid, "dmg": dmg, "crit": crit, "dodged": dodged,
              "monster_hp_left": hp_left, "monster_died": killed is not None, "player_hp_left": p["hp"]}
    if killed:
        result.update(distribute_kill(killed, p["id"], p["username"]))
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
        emit("skill_result", {"success": False, "skill": skill_id, "message": "ไม่พบสกิล/อาชีพไม่ตรง"})
        return
    now = time.time()
    stype = sk.get("type", "single")
    cd_len = sk.get("cd", 4)
    err = None
    heal_amt = 0
    buff_info = None
    hits, killed_list, states = [], [], []
    shake = 0
    with STATE_LOCK:
        cds = p.setdefault("skill_cd", {})
        if now < cds.get(skill_id, 0):
            err = f"คูลดาวน์อีก {int(cds[skill_id] - now) + 1} วิ"
        elif p["mp"] < sk["mp"]:
            err = "MP ไม่พอ"
        elif stype == "heal":
            heal_amt = int(p["max_hp"] * sk.get("heal_pct", 0.3))
            p["hp"] = min(p["max_hp"], p["hp"] + heal_amt)
            p["mp"] -= sk["mp"]
            cds[skill_id] = now + cd_len
        elif stype == "buff":
            stat = sk.get("stat", "atk")
            stat = stat if stat in ("atk", "def") else "atk"
            buff_info = {"stat": stat, "mult": sk.get("mult", 1.25), "duration": sk.get("duration", 15)}
            p["buffs"][stat] = {"mult": buff_info["mult"], "until": now + buff_info["duration"]}
            p["mp"] -= sk["mp"]
            cds[skill_id] = now + cd_len
        else:
            px, py = p["x"], p["y"]
            insts = MONSTER_INSTANCES.get(p["map"], {})
            if stype == "aoe":
                radius = sk.get("radius", ATTACK_RANGE)
                targets = sorted((m for m in insts.values()
                                  if m["alive"] and now >= m.get("spawn_until", 0)       # [v5.1.1]
                                  and math.hypot(px - m["x"], py - m["y"]) <= radius),
                                 key=lambda m: math.hypot(px - m["x"], py - m["y"]))[:sk.get("max_targets", 8)]
            else:
                m = find_monster(p["map"], data.get("monster_id"))
                rng = sk.get("range", SKILL_RANGE)
                targets = [m] if (m and m["alive"] and now >= m.get("spawn_until", 0)    # [v5.1.1]
                                  and math.hypot(px - m["x"], py - m["y"]) <= rng) else []
            if not targets:
                err = "ไม่มีเป้าหมายในระยะ"
            else:
                p["mp"] -= sk["mp"]
                cds[skill_id] = now + cd_len
                p["last_combat"] = now
                atk = eff_stat(p, "atk", now)
                shake = SHAKE_SKILL_AOE if stype == "aoe" else SHAKE_SKILL
                for inst in targets:
                    if not inst["alive"]:
                        continue
                    dmg, crit = roll_damage(atk, inst["def"], mult=sk.get("mult", 1.5))
                    snap = hit_monster(inst, p, dmg, now, 1.5)
                    hits.append({"monster_id": inst["id"], "dmg": dmg, "crit": crit,
                                 "monster_hp_left": inst["hp"], "monster_died": snap is not None})
                    if snap:
                        killed_list.append(snap)
                    if inst["alive"] and sk.get("stun") and not inst["boss"]:
                        inst["stun_until"] = max(inst["stun_until"], now + sk["stun"])
                    states.append(serialize_monster(inst))
        mp_now, hp_now = p["mp"], p["hp"]
    if err:
        emit("skill_result", {"success": False, "skill": skill_id, "message": err})
        return
    base = {"success": True, "skill": skill_id, "mp": mp_now, "hp": hp_now, "cd": cd_len}
    if stype in ("heal", "buff"):
        fx_shake(sid, SHAKE_HEAL, 0.35)
        emit("skill_result", {**base, "type": stype, **({"heal": heal_amt} if stype == "heal" else buff_info)})
        return
    if states:
        socketio.emit("monsters_update", {"map": p["map"], "monsters": states}, room=p["map"])
        socketio.emit("combat_fx", {"type": "skill_cast", "skill": skill_id, "stype": stype,
                                    "by": p["username"], "x": round(p["x"], 1), "y": round(p["y"], 1),
                                    "targets": [h["monster_id"] for h in hits]}, room=p["map"])
    if killed_list:
        shake = max(shake, SHAKE_KILL)
    fx_shake(p["map"] if (stype == "aoe" or killed_list) else sid, shake, 0.3)
    merged = {"exp_gain": 0, "gold_gain": 0, "leveled_up": False}
    user_payload = None
    for snap in killed_list:
        g = distribute_kill(snap, p["id"], p["username"])
        if g:
            merged["exp_gain"] += g["exp_gain"]
            merged["gold_gain"] += g["gold_gain"]
            merged["leveled_up"] = merged["leveled_up"] or g["leveled_up"]
            user_payload = g["user"]
    out = {**base, "type": stype, "hits": hits}
    if killed_list:
        out.update(merged)
        if user_payload:
            out["user"] = user_payload
    emit("skill_result", out)

@socketio.on("attack_player")
def handle_pvp(data):
    sid = request.sid
    p = connected_players.get(sid)
    if not p or p["hp"] <= 0:
        return
    if p["map"] != PVP_MAP:
        emit("pvp_result", {"success": False, "message": "PvP เปิดเฉพาะดันเจี้ยนเก่า"})
        return
    if not rate_ok(sid, "pvp", PVP_COOLDOWN):
        return
    t_sid = data.get("target_sid")
    now = time.time()
    err, dmg, crit, dodged, new_hp, t_info = None, 0, False, False, 0, None
    with STATE_LOCK:
        t = connected_players.get(t_sid)
        if not (t and t["id"] != p["id"] and t["map"] == p["map"] and t["hp"] > 0):
            err = "ไม่พบเป้าหมาย"
        elif math.hypot(p["x"] - t["x"], p["y"] - t["y"]) > ATTACK_RANGE:
            err = "เป้าหมายไกลเกินไป"
        elif now < t.get("invuln_until", 0):
            err = "เป้าหมายคุ้มครองอยู่"
        else:
            t_info = {"sid": t_sid, "username": t["username"], "level": t["level"], "x": t["x"], "y": t["y"]}
            p["last_combat"] = now
            if random.random() < PLAYER_DODGE:
                dodged = True
            else:
                dmg, crit = roll_damage(eff_stat(p, "atk", now), eff_stat(t, "def", now))
                new_hp = take_damage(t, dmg, now) or 0
    if err:
        if err == "เป้าหมายคุ้มครองอยู่":
            emit("combat_fx", {"type": "immune"})
        emit("pvp_result", {"success": False, "message": err})
        return
    if dodged:
        emit("combat_fx", {"type": "miss"})
        return
    socketio.emit("pvp_hit", {"hp": new_hp, "dmg": dmg, "attacker": p["username"]}, room=t_sid)
    if new_hp <= 0:
        dead_t = connected_players.get(t_sid)
        if dead_t:
            handle_player_death(t_sid, dead_t, p["username"], pvp=True)

@socketio.on("use_item")
def handle_use_item(data):
    sid = request.sid
    p = connected_players.get(sid)
    if not p:
        return
    if not rate_ok(sid, "use_item", ITEM_COOLDOWN):
        return
    try:
        inv_id = int(data.get("inventory_id"))
    except (TypeError, ValueError):
        emit("item_result", {"success": False, "message": "ไอเทมไม่ถูกต้อง"})
        return
    err, item_name, heal, mana = None, None, 0, 0
    with STATE_LOCK:
        if p["hp"] <= 0:
            err = "สลบอยู่ ใช้ยาไม่ได้"
        else:
            try:
                with get_db() as conn:
                    row = conn.execute("SELECT * FROM inventory WHERE id=? AND user_id=?", (inv_id, p["id"])).fetchone()
                    if not row or row["quantity"] <= 0:
                        err = "ไม่พบไอเทมในคลัง"
                    else:
                        item = GD.ITEMS.get(row["item_id"])
                        if not item or item.get("type") != "potion":
                            err = "ใช้ไอเทมนี้ไม่ได้"
                        else:
                            item_name = item["name"]
                            if item.get("heal_pct"):
                                heal = int(p["max_hp"] * item["heal_pct"])
                                p["hp"] = min(p["max_hp"], p["hp"] + heal)
                            if item.get("mana_pct"):
                                mana = int(p["max_mp"] * item["mana_pct"])
                                p["mp"] = min(p["max_mp"], p["mp"] + mana)
                            if heal <= 0 and mana <= 0:
                                err = "ไอเทมนี้ไม่มีผลใด ๆ"
                            else:
                                remain = row["quantity"] - 1
                                if remain <= 0:
                                    conn.execute("DELETE FROM inventory WHERE id=?", (inv_id,))
                                else:
                                    conn.execute("UPDATE inventory SET quantity=? WHERE id=?", (remain, inv_id))
            except Exception:
                log.exception("use_item failed")
                err = "เกิดข้อผิดพลาด"
    if err:
        emit("item_result", {"success": False, "message": err})
        return
    emit("item_result", {"success": True, "name": item_name, "heal": heal, "mana": mana, "hp": p["hp"], "mp": p["mp"]})
    emit("stats_update", {"hp": p["hp"], "mp": p["mp"]})
    fx_shake(sid, SHAKE_HEAL, 0.3)

@socketio.on("pickup_item")
def handle_pickup(data):
    sid = request.sid
    p = connected_players.get(sid)
    if not p or p["hp"] <= 0:
        return
    if not rate_ok(sid, "pickup", 0.15):
        return
    gid = str(data.get("item_id") or "")
    err, item_id, item_name = None, None, None
    with STATE_LOCK:
        bucket = GROUND_ITEMS.get(p["map"], {})
        g = bucket.get(gid)
        if not g:
            err = "ไอเทมหายไปแล้ว"
        elif math.hypot(p["x"] - g["x"], p["y"] - g["y"]) > PICKUP_RANGE:
            err = "เดินเข้าไปใกล้ก่อนถึงจะเก็บได้"
        else:
            item_id, item_name = g["item_id"], g["name"]
            bucket.pop(gid, None)
    if err:
        emit("item_result", {"success": False, "message": err})
        return
    try:
        with get_db() as conn:
            stackable = GD.ITEMS.get(item_id, {}).get("type") in ("potion", "material")
            row = conn.execute("SELECT * FROM inventory WHERE user_id=? AND item_id=? AND equipped=0",
                               (p["id"], item_id)).fetchone() if stackable else None
            if row:
                conn.execute("UPDATE inventory SET quantity=quantity+1 WHERE id=?", (row["id"],))
            else:   # อุปกรณ์ → แถวใหม่เสมอ (แต่ละชิ้นมีค่าตีบวกของตัวเอง)
                conn.execute("INSERT INTO inventory (user_id, item_id, quantity, enhance) VALUES (?,?,1,0)",
                             (p["id"], item_id))
    except Exception:
        log.exception("pickup save failed")
        emit("item_result", {"success": False, "message": "บันทึกไอเทมไม่สำเร็จ"})
        return
    emit("item_result", {"success": True, "message": f"🎒 เก็บ {item_name} ได้แล้ว!", "picked": True})
    socketio.emit("item_picked", {"item_id": gid, "by": p["username"]}, room=p["map"])

@socketio.on("respawn")
def handle_respawn():
    uid = session.get("user_id")
    if uid is None:
        return
    user_d, err = do_respawn(uid)
    if err:
        emit("respawn_error", {"message": err})

@socketio.on("chat")
def handle_chat(data):
    sid = request.sid
    p = connected_players.get(sid)
    if not p:
        return
    msg = ((data.get("message") or "").strip())[:200]
    if not msg or not rate_ok(sid, "chat", CHAT_COOLDOWN):
        return
    channel = data.get("channel", "global")
    if channel not in ("global", "map", "whisper"):
        channel = "global"
    target = ((data.get("target") or "") or "").strip()
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO chat_log (username, channel, message) VALUES (?,?,?)", (p["username"], channel, msg))
    except Exception:
        pass
    chat_time = datetime.now().strftime("%H:%M")
    if channel == "whisper":
        t_sid = t_name = None
        with STATE_LOCK:
            if target in connected_players:
                t_sid = target
                t_name = connected_players[target]["username"]
            else:
                for s, q in connected_players.items():
                    if q["username"].lower() == target.lower():
                        t_sid, t_name = s, q["username"]
                        break
        if not t_sid or t_sid == sid:
            emit("system_message", {"message": "❌ ไม่พบผู้เล่นสำหรับทักส่วนตัว (ใส่ชื่อผู้เล่น)"})
            return
        payload = {"username": p["username"], "channel": "whisper", "message": msg, "time": chat_time, "to": t_name}
        socketio.emit("chat_message", payload, room=t_sid)
        emit("chat_message", payload)
        return
    payload = {"username": p["username"], "channel": channel, "message": msg, "time": chat_time, "to": None}
    if channel == "map":
        socketio.emit("chat_message", payload, room=p["map"])
    else:
        socketio.emit("chat_message", payload)
    # [FIX] ลบ route guild_notice ที่ซ้อนอยู่ในฟังก์ชันนี้ออก → ย้ายไปไว้ใน lumivara_ext2.py

# ================= Background loops =================
def ai_loop():
    log.info("Monster AI loop started")
    while True:
        try:
            time.sleep(AI_TICK)
            now = time.time()
            updates, kills, deaths = {}, [], []
            expired = []
            with STATE_LOCK:
                for map_name, bucket in GROUND_ITEMS.items():
                    for gid, g in list(bucket.items()):
                        if now >= g["expire"]:
                            expired.append((map_name, gid))
                            bucket.pop(gid, None)
            for map_name, gid in expired:
                socketio.emit("item_picked", {"item_id": gid, "by": None}, room=map_name)
            with STATE_LOCK:
                for map_name, insts in MONSTER_INSTANCES.items():
                    plist = [(s, p) for s, p in connected_players.items() if p["map"] == map_name and p["hp"] > 0]
                    ups = []
                    for m in insts.values():
                        if not m["alive"]:
                            if now >= m["respawn_at"]:
                                respawn_monster(m, map_name)
                                ups.append(serialize_monster(m))
                            continue
                        changed = False
                        if m["dot"]:
                            if now >= m["dot"]["until"]:
                                m["dot"] = None
                            elif now >= m["dot"]["next"]:
                                m["dot"]["next"] = now + 1.0
                                socketio.emit("combat_fx", {"type": "dot", "monster_id": m["id"], "dmg": m["dot"]["dps"]}, room=map_name)
                                pseudo = {"id": m["dot"]["uid"], "username": m["dot"]["name"]}
                                snap = hit_monster(m, pseudo, m["dot"]["dps"], now)
                                changed = True
                                if snap:
                                    kills.append((snap, m["dot"]["name"]))
                        if not m["alive"]:
                            ups.append(serialize_monster(m)); continue
                        if now < m["stun_until"]:
                            continue
                        if now < m.get("spawn_until", 0):      # [v5.1.1] กำลังตกลงมา: ยังไม่เดิน/ไม่สู้
                            continue
                        tgt_sid = tgt_p = None
                        if m["target"]:
                            for s, p in plist:
                                if p["id"] == m["target"]:
                                    tgt_sid, tgt_p = s, p
                                    break
                            if tgt_p is None or math.hypot(tgt_p["x"] - m["home_x"], tgt_p["y"] - m["home_y"]) > LEASH_RANGE:
                                m["target"] = None
                                tgt_sid = tgt_p = None
                        if tgt_p is None and plist:
                            rng = AGGRO_RANGE if m["aggressive"] else PROVOKE_RANGE
                            best, bd = None, rng
                            for s, p in plist:
                                if now < p.get("invuln_until", 0):
                                    continue
                                d = math.hypot(p["x"] - m["x"], p["y"] - m["y"])
                                if d < bd:
                                    best, bd = (s, p), d
                            if best:
                                tgt_sid, tgt_p = best
                                m["target"] = tgt_p["id"]
                        if tgt_p:
                            d = math.hypot(tgt_p["x"] - m["x"], tgt_p["y"] - m["y"])
                            if d > MONSTER_ATTACK_RANGE:
                                sp = BOSS_SPEED if m["boss"] else MONSTER_SPEED
                                step = min(sp * AI_TICK, d - MONSTER_ATTACK_RANGE + 5)
                                m["x"] += (tgt_p["x"] - m["x"]) / d * step
                                m["y"] += (tgt_p["y"] - m["y"]) / d * step
                                changed = True
                            elif now >= m["atk_cd_until"] and now >= tgt_p.get("invuln_until", 0):
                                m["atk_cd_until"] = now + (BOSS_ATTACK_CD if m["boss"] else MONSTER_ATTACK_CD)
                                atk = m["atk"] * (BOSS_ENRAGE_MULT if m["enraged"] else 1.0)
                                dmg, crit = roll_damage(atk, eff_stat(tgt_p, "def", now), crit_chance=0.0)
                                if random.random() < PLAYER_DODGE:
                                    socketio.emit("combat_fx", {"type": "miss"}, room=tgt_sid)
                                else:
                                    hp = take_damage(tgt_p, dmg, now)
                                    fx_shake(tgt_sid, SHAKE_MONSTER_HIT, 0.25, extra={"hurt": True})
                                    socketio.emit("monster_attack", {"target_sid": tgt_sid, "hp_left": hp, "dmg": dmg,
                                                                     "crit": crit, "monster_id": m["id"], "monster_name": m["name"]}, room=tgt_sid)
                                    if hp == 0:
                                        deaths.append((tgt_sid, tgt_p, m["name"]))
                                changed = True
                            if m["boss"]:
                                if not m["enraged"] and m["hp"] <= m["max_hp"] * BOSS_ENRAGE_HP:
                                    m["enraged"] = True
                                    fx_shake(map_name, 8, 0.4, extra={"type": "enrage"})
                                    socketio.emit("system_message", {"message": f"😡 {m['name']} โกรธจัด!"}, room=map_name)
                                if m["enraged"] and now >= m["slam_at"]:
                                    m["slam_at"] = now + BOSS_SLAM_CD
                                    socketio.emit("boss_slam", {"x": round(m["x"], 1), "y": round(m["y"], 1), "radius": BOSS_SLAM_RADIUS}, room=map_name)
                                    for s2, p2 in plist:
                                        if math.hypot(p2["x"] - m["x"], p2["y"] - m["y"]) <= BOSS_SLAM_RADIUS:
                                            dmg2, _ = roll_damage(m["atk"] * BOSS_SLAM_MULT, eff_stat(p2, "def", now), crit_chance=0.0)
                                            hp2 = take_damage(p2, dmg2, now)
                                            socketio.emit("monster_attack", {"target_sid": s2, "hp_left": hp2, "dmg": dmg2,
                                                                             "crit": False, "monster_id": m["id"], "monster_name": m["name"]}, room=s2)
                                            socketio.emit("combat_fx", {"type": "slam_hit", "sid": s2, "dmg": dmg2}, room=map_name)
                                            if hp2 == 0:
                                                deaths.append((s2, p2, m["name"]))
                        elif now >= m["wander_at"]:
                            m["wander_at"] = now + WANDER_EVERY
                            if step_wander(m):
                                changed = True
                        if changed and m["alive"]:
                            ups.append(serialize_monster(m))
                    if ups:
                        updates[map_name] = ups
            for map_name, ups in updates.items():
                socketio.emit("monsters_update", {"map": map_name, "monsters": ups}, room=map_name)
            for sid, p, kname in deaths:
                handle_player_death(sid, p, kname)
            for snap, kname in kills:
                uid = max(snap.get("contrib", {}), key=snap["contrib"].get) if snap.get("contrib") else None
                distribute_kill(snap, uid, kname)
        except Exception:
            log.exception("AI loop error")

def regen_loop():
    while True:
        time.sleep(REGEN_EVERY)
        now = time.time()
        updates = []
        with STATE_LOCK:
            for sid, p in connected_players.items():
                if p["hp"] <= 0:
                    continue
                if now - p.get("last_combat", 0.0) < IDLE_REGEN_DELAY:
                    continue
                nh = min(p["max_hp"], p["hp"] + int(p["max_hp"] * IDLE_REGEN_PCT))
                nm = min(p["max_mp"], p["mp"] + int(p["max_mp"] * IDLE_REGEN_PCT))
                if nh != p["hp"] or nm != p["mp"]:
                    p["hp"], p["mp"] = nh, nm
                    updates.append((sid, nh, nm))
        for sid, hp, mp in updates:
            socketio.emit("stats_update", {"hp": hp, "mp": mp}, room=sid)

def autosave_loop():
    while True:
        time.sleep(AUTOSAVE_SECONDS)
        try:
            with STATE_LOCK:
                snapshot = [(p["x"], p["y"], p["map"], p["hp"], p["mp"], p["id"]) for p in connected_players.values()]
            if snapshot:
                with get_db() as conn:
                    conn.executemany("UPDATE users SET x=?,y=?,map=?,hp=?,mp=? WHERE id=?", snapshot)
        except Exception:
            log.exception("autosave failed")

# ================= START =================
init_db()
if EXT:   # [FIX] รองรับทั้งส่วนเสริมรุ่นที่มี/ไม่มี install()
    (EXT.install if hasattr(EXT, "install") else EXT.extend_world)(globals())
import lumivara_skills                      # ← เพิ่ม
lumivara_skills.install(globals())          # ← เพิ่ม
spawn_all_monsters()
threading.Thread(target=ai_loop, daemon=True).start()
threading.Thread(target=regen_loop, daemon=True).start()
threading.Thread(target=autosave_loop, daemon=True).start()
threading.Thread(target=market_loop, daemon=True).start()
log.info("Lumivara Online v5.1.1 → http://localhost:6600 (%d maps, %d skills)", len(GD.MAPS), len(GD.SKILLS))

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=6600, debug=False,
                 use_reloader=False, allow_unsafe_werkzeug=True)
    # ถ้า flask-socketio รุ่นเก่า error ที่ allow_unsafe_werkzeug ให้ลบพารามิเตอร์นั้นออก