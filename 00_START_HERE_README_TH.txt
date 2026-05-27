เริ่มจากไฟล์นี้ครับ

นี่คือแพ็กเดียวจบสำหรับส่งเข้า Codex:
BN9_X_SOCIAL_REAL_V6_READY_FOR_CODEX

ข้างในมีโปรเจกต์จริงแล้ว ไม่ต้องหา ZIP เก่าอีก
ไฟล์สำคัญที่ต้องเห็นคือ:

- app.py
- x_client.py
- oauth_user_token_helper.py
- RUN.bat
- GET_USER_TOKEN.bat
- 00_PASTE_TO_CODEX_FIRST.md

วิธีใช้กับ Codex

1) แตก ZIP นี้ก่อน
2) เปิดโฟลเดอร์ BN9_X_SOCIAL_REAL_V6_READY_FOR_CODEX ด้วย VS Code / Codex
3) เช็กว่ามีไฟล์ app.py อยู่ในโฟลเดอร์เดียวกัน
4) เปิดไฟล์ 00_PASTE_TO_CODEX_FIRST.md
5) คัดลอกเนื้อหาทั้งหมดไปวางใน Codex
6) ให้ Codex แก้โปรเจกต์ตามคำสั่ง
7) หลัง Codex ทำเสร็จ ให้รัน:

   python -m py_compile *.py
   python health_check.py --offline

คำเตือนสำคัญ

- อย่าวาง Token จริงลงใน Codex prompt
- Token จริงให้ใส่ในไฟล์ .env เท่านั้น
- ห้ามทดสอบปุ่ม Post / Reply / Like / Follow / DM จริง จนกว่าจะเช็ก offline ผ่านก่อน

ถ้าแค่อยากเปิดโปรแกรม V5 เดิมก่อน ยังไม่ให้ Codex แก้:
ดับเบิลคลิก RUN.bat

