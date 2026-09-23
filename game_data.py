# -*- coding: utf-8 -*-
"""Lumivara Online — Game Data (อาชีพ / สกิล / ไอเทม / มอนสเตอร์ / เควส)"""

MAPS = {
    "town": "เมืองหลัก",
    "forest": "ป่าลึก",
    "cave": "ถ้ำสะเก็ดดาว",
    "dungeon": "ดันเจี้ยนมืด (PvP)",
}

JOBS = {
    "Novice":  {"hp": 120, "mp": 60,  "atk": 12, "def": 8,  "desc": "มือใหม่ผจญภัย ค่าค่อนข้างสมดุล"},
    "Warrior": {"hp": 170, "mp": 45,  "atk": 15, "def": 13, "desc": "นักรบหน้าด้าน พลังชีวิตสูง"},
    "Mage":    {"hp": 95,  "mp": 110, "atk": 18, "def": 5,  "desc": "นักเวทดาเมจรุนแรง แต่บางเบา"},
    "Archer":  {"hp": 115, "mp": 75,  "atk": 17, "def": 7,  "desc": "นักธนูโจมตีต่อเนื่อ ว่องไว"},
}

GROWTH = {  # ค่าพลังที่ได้ต่อเลเวล
    "Novice":  {"hp": 12, "mp": 6,  "atk": 2, "def": 1},
    "Warrior": {"hp": 20, "mp": 4,  "atk": 3, "def": 2},
    "Mage":    {"hp": 9,  "mp": 12, "atk": 4, "def": 1},
    "Archer":  {"hp": 13, "mp": 8,  "atk": 3, "def": 1},
}

# type: damage (单体) / aoe (วงกว้าง) / multi (หลายฮิต) / heal (ฟื้นฟู)
SKILLS = {
    "bash":         {"job": "Novice",  "name": "Bash",         "type": "damage", "mp": 6,  "mult": 1.7, "cd": 3,  "desc": "ตีแรงด้วยอาวุธ"},
    "power_strike": {"job": "Warrior", "name": "Power Strike", "type": "damage", "mp": 12, "mult": 2.3, "cd": 5,  "desc": "ฟันพลังสูง 1 เป้า"},
    "whirlwind":    {"job": "Warrior", "name": "Whirlwind",    "type": "aoe",    "mp": 20, "mult": 1.3, "radius": 110, "cd": 8, "desc": "หมุนดาบโจมตีรอบตัว"},
    "fireball":     {"job": "Mage",    "name": "Fireball",     "type": "damage", "mp": 16, "mult": 2.8, "cd": 5,  "desc": "ลูกไฟดาเมจสูง"},
    "frost_nova":   {"job": "Mage",    "name": "Frost Nova",   "type": "aoe",    "mp": 24, "mult": 1.5, "radius": 120, "cd": 9, "desc": "น้ำแข็งระเบิดรอบตัว"},
    "heal_light":   {"job": "Mage",    "name": "Heal Light",   "type": "heal",   "mp": 22, "heal_pct": 0.45, "cd": 10, "desc": "ฟื้นฟู 45% HP"},
    "double_shot":  {"job": "Archer",  "name": "Double Shot",  "type": "multi",  "mp": 14, "mult": 1.35, "hits": 2, "cd": 4, "desc": "ยิง 2 ลูกติดกัน"},
    "arrow_rain":   {"job": "Archer",  "name": "Arrow Rain",   "type": "aoe",    "mp": 22, "mult": 1.25, "radius": 130, "cd": 8, "desc": "ฝนลูกธนูย่ำพื้นที่"},
}

ITEMS = {
    # --- ยา ---
    1:  {"name": "ยา HP เล็ก",    "type": "potion", "price": 30,  "level_req": 1,  "heal": 60},
    2:  {"name": "ยา HP กลาง",    "type": "potion", "price": 90,  "level_req": 3,  "heal": 180},
    3:  {"name": "ยา HP ใหญ่",    "type": "potion", "price": 220, "level_req": 10, "heal": 400},
    4:  {"name": "ยา MP เล็ก",    "type": "potion", "price": 40,  "level_req": 1,  "heal_mp": 50},
    5:  {"name": "ยา MP กลาง",    "type": "potion", "price": 110, "level_req": 5,  "heal_mp": 120},
    6:  {"name": "ยาเอลิกซิร์",   "type": "potion", "price": 500, "level_req": 8,  "heal": 99999, "heal_mp": 99999},
    # --- อาวุธ ---
    7:  {"name": "ดาบสนิม",       "type": "weapon", "price": 120,  "level_req": 1,  "atk_bonus": 3},
    8:  {"name": "ดาบเหล็ก",      "type": "weapon", "price": 480,  "level_req": 5,  "atk_bonus": 8},
    9:  {"name": "ใบมีดเพลิง",    "type": "weapon", "price": 1600, "level_req": 12, "atk_bonus": 16},
    10: {"name": "ไม้เท้าโอ๊ค",   "type": "weapon", "price": 350,  "level_req": 3,  "atk_bonus": 6,  "mp_bonus": 20},
    11: {"name": "ไม้เท้าลี้ลับ",  "type": "weapon", "price": 1500, "level_req": 10, "atk_bonus": 14, "mp_bonus": 40},
    # --- เกราะ ---
    12: {"name": "หนังสัตว์",      "type": "armor", "price": 100,  "level_req": 1,  "def_bonus": 3,  "hp_bonus": 20},
    13: {"name": "เกราะเหล็ก",     "type": "armor", "price": 420,  "level_req": 5,  "def_bonus": 8,  "hp_bonus": 50},
    14: {"name": "เกราะมังกร",     "type": "armor", "price": 1800, "level_req": 12, "def_bonus": 16, "hp_bonus": 120},
    # --- เครื่องประดับ ---
    15: {"name": "แหวนพลัง",      "type": "accessory", "price": 300, "level_req": 4,  "atk_bonus": 5},
    16: {"name": "เข็มกำลัง",      "type": "accessory", "price": 300, "level_req": 4,  "def_bonus": 5, "hp_bonus": 60},
    17: {"name": "แหวนนักปราชญ์",  "type": "accessory", "price": 400, "level_req": 6,  "mp_bonus": 50, "atk_bonus": 3},
}

MONSTERS = {
    "town": [],
    "forest": [
        {"id": 1, "name": "สไลม์",       "level": 2,  "hp": 35,  "atk": 7,  "def": 2,  "exp": 14,  "gold": 9,   "respawn": 12},
        {"id": 2, "name": "หมาป่า",      "level": 5,  "hp": 60,  "atk": 12, "def": 4,  "exp": 30,  "gold": 18,  "respawn": 18},
        {"id": 3, "name": "แมงมุมพิษ",    "level": 8,  "hp": 80,  "atk": 15, "def": 6,  "exp": 45,  "gold": 25,  "respawn": 22},
        {"id": 1, "name": "สไลม์",       "level": 2,  "hp": 35,  "atk": 7,  "def": 2,  "exp": 14,  "gold": 9,   "respawn": 12},
        {"id": 2, "name": "หมาป่า",      "level": 5,  "hp": 60,  "atk": 12, "def": 4,  "exp": 30,  "gold": 18,  "respawn": 18},
    ],
    "cave": [
        {"id": 4, "name": "ค้างคาว",      "level": 10, "hp": 55,  "atk": 14, "def": 3,  "exp": 35,  "gold": 20,  "respawn": 15},
        {"id": 5, "name": "โกเลม",       "level": 14, "hp": 150, "atk": 20, "def": 14, "exp": 80,  "gold": 45,  "respawn": 30},
        {"id": 6, "name": "วิญญาณถ้ำ",    "level": 16, "hp": 110, "atk": 24, "def": 6,  "exp": 70,  "gold": 40,  "respawn": 25},
        {"id": 4, "name": "ค้างคาว",      "level": 10, "hp": 55,  "atk": 14, "def": 3,  "exp": 35,  "gold": 20,  "respawn": 15},
    ],
    "dungeon": [
        {"id": 7, "name": "โครงกระดูก",   "level": 18, "hp": 130, "atk": 26, "def": 10, "exp": 100, "gold": 60,  "respawn": 25},
        {"id": 8, "name": "แม่มดมืด",     "level": 22, "hp": 160, "atk": 34, "def": 8,  "exp": 140, "gold": 85,  "respawn": 30},
        {"id": 9, "name": "อัศวินมรณะ",   "level": 26, "hp": 240, "atk": 38, "def": 18, "exp": 220, "gold": 130, "respawn": 45, "boss": True},
        {"id": 7, "name": "โครงกระดูก",   "level": 18, "hp": 130, "atk": 26, "def": 10, "exp": 100, "gold": 60,  "respawn": 25},
        {"id": 8, "name": "แม่มดมืด",     "level": 22, "hp": 160, "atk": 34, "def": 8,  "exp": 140, "gold": 85,  "respawn": 30},
        {"id": 10, "name": "จอมปีศาจเลวร้าย", "level": 35, "hp": 600, "atk": 50, "def": 22, "exp": 900, "gold": 600, "respawn": 90, "boss": True},
    ],
}

QUESTS = {
    1: {"name": "ทำความสะอาดป่า",  "desc": "กำจัดสไลม์ในป่าลึกให้หมด",     "target_monster": 1,  "target_count": 10, "reward_exp": 150,  "reward_gold": 120},
    2: {"name": "ล่าหมาป่า",      "desc": "หมาป่าร้ายกาจออกล่าเหยื่อ",       "target_monster": 2,  "target_count": 6,  "reward_exp": 320,  "reward_gold": 220},
    3: {"name": "พิษแมงมุม",      "desc": "กำจัดแมงมุมพิษก่อนระบาด",        "target_monster": 3,  "target_count": 8,  "reward_exp": 500,  "reward_gold": 350},
    4: {"name": "สำรวจถ้ำ",       "desc": "จัดการค้างคาวในถ้ำให้พ้น",        "target_monster": 4,  "target_count": 12, "reward_exp": 600,  "reward_gold": 400},
    5: {"name": "ทลายโกเลม",      "desc": "โกเลมหินกำลังตื่นตัว ทำลายมัน!",   "target_monster": 5,  "target_count": 6,  "reward_exp": 900,  "reward_gold": 600},
    6: {"name": "กวาดล้างดันเจี้ยน", "desc": "ปราบโครงกระดูกในดันเจี้ยนมืด",  "target_monster": 7,  "target_count": 12, "reward_exp": 1300, "reward_gold": 900},
    7: {"name": "ปราบแม่มดมืด",    "desc": "เลิกพิธีมืดของแม่มดให้สิ้นซาก",    "target_monster": 8,  "target_count": 8,  "reward_exp": 1800, "reward_gold": 1200},
    8: {"name": "ผู้พิชิตจอมปีศาจ", "desc": "งานสุดท้าย: ปราบจอมปีศาจเลวร้าย", "target_monster": 10, "target_count": 1,  "reward_exp": 5000, "reward_gold": 4000},
}


def exp_to_next_level(level):
    return int(60 * (level ** 1.5)) + 40


def stat_growth_per_level(job):
    return GROWTH.get(job, GROWTH["Novice"])