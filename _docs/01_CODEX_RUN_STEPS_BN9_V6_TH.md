# วิธีใช้ Codex กับโปรเจกต์ BN9 X Social Real V6

## วิธีที่ง่ายสุด: Codex App / VS Code Extension

1. แตกไฟล์ `x_social_real_v5_1_token_helper (1).zip`
2. เปิดโฟลเดอร์ `x_social_real_v5_1_token` ใน Codex
3. เลือกโหมด Local
4. วางข้อความในไฟล์ `CODEX_TASK_BN9_V6_EASY_READY_PHASE1_TH.md`
5. ให้ Codex แก้โค้ด
6. ให้ Codex รันเช็ก:

```bash
python -m py_compile *.py
python health_check.py --offline
```

## วิธีใช้ Codex CLI

ติดตั้ง:

```bash
npm i -g @openai/codex
```

เข้าโฟลเดอร์โปรเจกต์:

```bash
cd path/to/x_social_real_v5_1_token
codex
```

แล้ววาง task จากไฟล์ `CODEX_TASK_BN9_V6_EASY_READY_PHASE1_TH.md`

## ข้อห้าม

- ห้ามวาง X Token จริงใน prompt
- ให้ใส่ Token ใน `.env` เท่านั้น
- ห้ามให้ Codex ยิงปุ่ม Post/Reply/Like/DM จริงระหว่างทดสอบ
- ให้ทดสอบแบบ offline ก่อนเสมอ
