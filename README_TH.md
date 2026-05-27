# BN9 X Social Real V6 Easy Ready

โปรเจกต์นี้อัปเกรดจาก V5 Mega โดยยังคงฟีเจอร์เดิมไว้ และเพิ่มตัวช่วยเริ่มต้นสำหรับคนที่ไม่รู้โค้ด

อ่านคู่มือแบบเริ่มจากศูนย์ที่ `README_START_HERE_TH.md`

## เปิดโปรแกรมแบบง่าย

1. ดับเบิลคลิก `START_HERE.bat`
2. ถ้าระบบบอกว่ายังไม่พร้อม ให้ดับเบิลคลิก `FIX_INSTALL.bat`
3. กลับมากด `START_HERE.bat` อีกครั้ง
4. ไปแท็บ `0 Start Here`
5. กด `Health Check`

## Token ที่ใช้

| งาน | Token |
|---|---|
| อ่านข้อมูลสาธารณะ / Social Listening / Count / Trend | `APP_BEARER_TOKEN` |
| รองรับไฟล์เก่าจาก V5 | `BEARER_TOKEN` |
| Post / Reply / Like / Follow / DM | `USER_ACCESS_TOKEN` |
| ต่ออายุ User Token | `X_REFRESH_TOKEN` |
| Telegram แจ้งเตือน | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |

ระบบจะบันทึก `APP_BEARER_TOKEN` และ `BEARER_TOKEN` พร้อมกันเพื่อให้ผู้ใช้ V5 เดิมไม่พัง

## ลำดับใช้งานที่แนะนำ

1. เปิด `START_HERE.bat`
2. กด `Health Check`
3. ใส่ `App Bearer Token = อ่านข้อมูลสาธารณะ`
4. กด `บันทึกค่า`
5. ไปแท็บ `2 Social Listening`
6. กด `1 เช็กจำนวนก่อนดึง`
7. ดู Cost Guard ก่อนกดดึงจริง
8. กด `2 ดึงจริง + วิเคราะห์ + รายงาน`
9. เปิดผลที่ `outputs` หรือปุ่ม `เปิด Dashboard ล่าสุด`

## Action จริง

ปุ่ม Post, Reply, Like, Follow, DM เป็น Action จริงกับบัญชี X

V6 เพิ่มขั้นตอน:

```text
Preview -> Queue -> Confirm -> Execute
```

ทุก action จะถูกบันทึก audit ที่ `outputs/action_audit.jsonl` โดยไม่เก็บ token ลงไฟล์

## เช็กระบบแบบไม่ยิง API

รันคำสั่งนี้ในโฟลเดอร์โปรเจกต์:

```bash
python -m py_compile *.py
python health_check.py --offline
```

คำสั่ง `--offline` ไม่ยิง X API จริง

## Error ที่พบบ่อย

| ข้อความ | วิธีแก้ |
|---|---|
| 400 คำค้นหรือพารามิเตอร์ผิด | ตรวจ query, id, max_results |
| 401 Token ผิดหรือหมดอายุ | ใส่ token ใหม่ |
| 402 เครดิตหมด | เช็ก usage/billing ใน X Developer Portal |
| 403 Permission หรือ scope ไม่พอ | เช็ก plan, app permission, OAuth scope |
| 404 ไม่พบข้อมูล | ตรวจ tweet id, user id, endpoint |
| 429 rate limit | รอ reset หรือลดจำนวนคำค้น |

## ฟีเจอร์เดิมที่ยังอยู่

- Social Listening
- เช็กจำนวนก่อนดึงจริง
- ตัวกรองสแปม / คำต้องมี
- Lead Score
- Reply Draft
- Creator Finder
- Competitor Watch
- Customer Care Queue
- Trend Radar
- Telegram Alert
- Real Actions: Post, Reply, Like, Retweet, Follow, DM, List
- Media Upload
- Ads Analytics แบบ OAuth 1.0a
- CLI สำหรับตั้งเวลา
- Windows Task Scheduler
