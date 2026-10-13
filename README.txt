# Lumivara Online — UI Redesign

ไฟล์นี้เป็นการปรับหน้าตา UI ด้วย CSS โดยคง ID, class และฟังก์ชัน JavaScript ที่อยู่ใน HTML ต้นฉบับให้มากที่สุด

## ไฟล์
- `templates/index.html` — HTML template ที่คงการเรียกใช้ Flask และไฟล์ JavaScript เดิม
- `static/style.css` — ธีม Dark Fantasy + Neon RPG แบบ responsive

## วิธีนำไปใช้
1. สำรอง `static/style.css` เดิมก่อน
2. นำ `static/style.css` ใหม่นี้ไปแทนไฟล์เดิมในโปรเจกต์ Flask
3. ใช้ `templates/index.html` หากต้องการเทียบกับ template เดิม
4. คง `game.js`, `lumivara_fx.js`, Socket.IO และ backend เดิมไว้

หมายเหตุ: ไฟล์ JavaScript/backend ไม่ได้อยู่ในไฟล์ที่แนบมา จึงปรับเฉพาะ HTML template และ CSS ไม่ได้ทดสอบการทำงานของระบบเกมจริง


## โหมดเต็มหน้าจอ
- ปรับพื้นที่เกมให้เต็ม viewport ทั้งคอมและมือถือ รวมถึงรองรับความสูงแบบ dynamic viewport บนมือถือ
- Canvas ขยายเต็มพื้นที่หน้าจอโดยไม่เว้นขอบดำจากการ contain (อาจมีการยืดสัดส่วนตามอัตราส่วนหน้าจอ)
- สามารถใช้ปุ่ม ⛶ ในเกมเพื่อเรียกโหมด Fullscreen ได้ หากเบราว์เซอร์อนุญาต
