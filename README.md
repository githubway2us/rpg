# Lumivara Online - Backend

## รัน
```bash
pip install -r requirements.txt
python app.py
```
เปิด http://localhost:5000 (ต้องมี templates/index.html ของ frontend เอง)

## ระบบที่มีให้ครบในเวอร์ชันนี้
- สมัคร/ล็อกอิน: เข้ารหัสรหัสผ่านด้วย werkzeug (ไม่เก็บ plaintext แล้ว)
- อาชีพเริ่มต้น 4 อาชีพ พร้อมค่าพลังและอัตราการโตต่อเลเวลต่างกัน (game_data.py)
- อินเวนทอรี + ระบบสวมใส่อุปกรณ์ (weapon/armor/accessory) และคำนวณโบนัสสเตตัสจริง
- ร้านค้า ซื้อไอเทมด้วยทอง เช็คเลเวลและเงินฝั่งเซิร์ฟเวอร์
- ระบบต่อสู้กับมอนสเตอร์ต่อแมพ คำนวณดาเมจฝั่งเซิร์ฟเวอร์ (กันโกง client)
- เลเวลอัพอัตโนมัติเมื่อ exp ถึงเกณฑ์ พร้อมสูตร exp โตแบบ non-linear
- ระบบเควส (รับ/ติดตามความคืบหน้า/รับรางวัล)
- แชท 3 ช่องทาง: global, map (เฉพาะห้อง/แมพ), whisper (ส่วนตัว) + log ลง DB
- ห้อง (Socket.IO room) แยกตามแมพ ลดการ broadcast ตำแหน่งข้ามแมพที่ไม่จำเป็น
- ระบบแอดมิน: broadcast ข้อความระบบ, แบนผู้ใช้ (เตะออกจากเกมทันที)
- บันทึกตำแหน่งผู้เล่นอัตโนมัติตอน disconnect

## ยังไม่ได้ทำ (ต้องต่อยอดถ้าต้องการ "เทพ" กว่านี้)
- Frontend (templates/index.html, canvas/Phaser render ตัวละครและแมพ)
- Rate limiting / anti-spam แชท
- ระบบกิลด์ (guild) และ PvP arena
- JWT/refresh token แทน session คุกกี้ธรรมดา (ถ้าจะรองรับหลาย client หรือ mobile)
- Redis สำหรับ connected_players ถ้าจะ scale เกิน 1 process
