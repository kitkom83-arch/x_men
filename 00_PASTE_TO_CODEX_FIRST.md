# CODEX TASK: BN9 X Social Real V6 Easy Ready — Phase 1

> ใช้ไฟล์นี้เป็นคำสั่งหลักสำหรับวางใน Codex หลังจากเปิดโฟลเดอร์ `BN9_X_SOCIAL_REAL_V6_READY_FOR_CODEX` แล้ว โฟลเดอร์นี้มี `app.py` อยู่ด้านในแล้ว

## เป้าหมาย
อัปเกรดโปรเจกต์เดิม **BN9 X Social Real V5 Mega** ให้เป็น **BN9 X Social Real V6 Easy Ready** โดยทำเฉพาะ Phase 1 ก่อน:

- เปิดง่าย
- ตั้งค่า Token ง่าย
- Health Check อ่านง่าย
- กันใช้เครดิตเกินก่อนดึง X API
- บอกสิทธิ์/Scope ของ Token ก่อนกดปุ่มจริง
- Action จริงต้องเข้าคิวและยืนยันก่อนยิง
- Error ต้องแปลเป็นภาษาไทยแบบผู้ใช้ไม่รู้โค้ดก็เข้าใจ

## กติกาสำคัญ
1. ห้ามลบฟีเจอร์เดิมของ V5
2. ห้ามยิง X API แบบ write/action จริงระหว่างทดสอบ
3. ห้ามพิมพ์ token จริงลง log, dashboard, error message หรือไฟล์ report
4. รองรับ token ชื่อเดิม `BEARER_TOKEN` และชื่อใหม่ `APP_BEARER_TOKEN` พร้อมกัน เพื่อไม่ให้ผู้ใช้เดิมพัง
5. UI ภาษาไทยทั้งหมด
6. โค้ดต้องรันบน Windows ได้ผ่าน `.bat`
7. ต้องมีวิธีเช็กเร็วด้วย `python -m py_compile *.py`

## ไฟล์เดิมที่ต้องอ่านก่อนแก้
อ่านไฟล์เหล่านี้เพื่อเข้าใจระบบเดิม:

- `app.py`
- `x_client.py`
- `storage.py`
- `reporting.py`
- `analysis_engine.py`
- `oauth_user_token_helper.py`
- `.env.example`
- `README_TH.md`
- `RUN.bat`
- `FIX_INSTALL.bat`

## ไฟล์ใหม่ที่ต้องเพิ่ม
เพิ่มไฟล์เหล่านี้:

### 1. `START_HERE.bat`
หน้าที่:
- เปิดโปรแกรมแบบง่ายที่สุด
- ถ้ายังไม่มี dependency ให้บอกให้กด `FIX_INSTALL.bat`
- เรียก `python app.py`

ข้อความในไฟล์ต้องเป็นภาษาไทย อ่านง่าย

### 2. `health_check.py`
หน้าที่:
- เช็ก Python version
- เช็ก library จาก `requirements.txt`
- เช็ก `.env`
- เช็ก `APP_BEARER_TOKEN` หรือ fallback `BEARER_TOKEN`
- เช็ก `USER_ACCESS_TOKEN`
- เช็ก Telegram token/chat id
- เช็กว่าโฟลเดอร์ `outputs` สร้างได้
- มีโหมด offline ที่ไม่ยิง API จริง
- ถ้า `--online` ค่อยทดสอบ API เบื้องต้น เช่น usage/user lookup แบบ read เท่านั้น

CLI ที่ต้องรองรับ:

```bash
python health_check.py --offline
python health_check.py --online
```

ผลลัพธ์ต้องเป็นภาษาไทย เช่น:

```text
[ผ่าน] Python พร้อมใช้งาน
[เตือน] ยังไม่มี USER_ACCESS_TOKEN: ปุ่ม Post/Like/DM จะยังใช้ไม่ได้
[ต้องแก้] ยังไม่มี APP_BEARER_TOKEN: อ่านข้อมูล X ไม่ได้
```

### 3. `cost_guard.py`
หน้าที่:
- คำนวณต้นทุนคร่าว ๆ ก่อนดึงจริง
- รับจำนวนคำค้นและจำนวนโพสต์ต่อคำค้น
- สรุปจำนวน resource ที่จะใช้
- สร้างข้อความเตือนภาษาไทย

ต้องมี function อย่างน้อย:

```python
estimate_recent_search_cost(num_queries: int, max_posts_per_query: int) -> dict
format_cost_warning(estimate: dict) -> str
```

### 4. `scope_guard.py`
หน้าที่:
- เก็บ mapping ว่า action ไหนต้องใช้ scope อะไร
- บอกผู้ใช้ว่า token ยังขาด scope อะไร
- ใช้กับ UI เพื่อปิด/เตือนก่อนกดปุ่มจริง

ต้องมี mapping สำหรับ:

- read_posts = `tweet.read`, `users.read`
- create_post = `tweet.write`
- reply = `tweet.write`
- like = `like.write`
- follow = `follows.write`
- dm = `dm.read`, `dm.write`
- media_upload = `media.write`
- refresh = `offline.access`

### 5. `action_queue.py`
หน้าที่:
- สร้างคิว Action ก่อนยิงจริง
- เก็บ action เป็น JSONL ที่ `outputs/action_audit.jsonl`
- ทุก action ต้องมี `created_at`, `action_type`, `target_id`, `text_preview`, `status`
- status เริ่มต้นเป็น `queued`
- ห้ามเก็บ token ลงไฟล์

ต้องมี function อย่างน้อย:

```python
queue_action(action_type: str, payload: dict) -> dict
mark_action_status(action_id: str, status: str, result: dict | None = None) -> dict
load_actions(limit: int = 100) -> list[dict]
```

### 6. `policy_guard.py`
หน้าที่:
- กันพฤติกรรมเสี่ยง เช่น DM จำนวนมาก, follow จำนวนมาก, ข้อความซ้ำ ๆ, spam keyword
- คืนข้อความเตือนภาษาไทย
- ไม่ต้องบล็อกทั้งหมด แต่ต้องเตือนก่อน

### 7. `README_START_HERE_TH.md`
เขียนคู่มือเริ่มต้นใหม่แบบคนไม่รู้โค้ด:

1. กด `START_HERE.bat`
2. กด Health Check
3. ใส่ App Bearer Token
4. ทดสอบอ่านข้อมูล
5. เช็กจำนวนก่อนดึง
6. ดู Cost Estimate
7. ดึงจริง + วิเคราะห์ + รายงาน
8. ถ้าจะ Reply/Like/DM ค่อยทำ User Token

## ไฟล์ที่ต้องแก้

### `app.py`
แก้ตามนี้:

1. เปลี่ยนชื่อโปรแกรมเป็น:

```text
BN9 X Social Real V6 Easy Ready
```

2. เพิ่มแท็บแรกชื่อ:

```text
0 Start Here
```

ในแท็บนี้ต้องมี:

- ปุ่ม `Health Check`
- ปุ่ม `เปิดแท็บตั้งค่า Token`
- ปุ่ม `เปิด Social Listening`
- ปุ่ม `เปิด outputs`
- ปุ่ม `เปิด Dashboard ล่าสุด`
- กล่องสรุปสถานะว่า Token ไหนพร้อม/ไม่พร้อม

3. แท็บตั้งค่า Token ให้เปลี่ยน label ให้ชัด:

```text
App Bearer Token = อ่านข้อมูลสาธารณะ
User Access Token = ยิง Action จริง เช่น Post/Like/DM
```

4. `save_settings()` ต้องบันทึกทั้ง:

- `APP_BEARER_TOKEN`
- `BEARER_TOKEN` เป็น fallback compatibility
- `USER_ACCESS_TOKEN`
- `X_REFRESH_TOKEN` ถ้ามีช่องนี้

5. ก่อน Social Listening ดึงจริง ให้เรียก Cost Guard แล้วแสดง confirm dialog ภาษาไทย เช่น:

```text
รอบนี้จะดึงประมาณ 50 โพสต์
ใช้เครดิตตามจำนวน resource ที่ X API คิดจริง
ยืนยันดึงข้อมูลหรือไม่?
```

6. ก่อน Action จริงทุกปุ่ม ให้เพิ่มขั้น:

```text
Preview → Queue → Confirm → Execute
```

ถ้ายังแก้ action จริงทั้งหมดไม่ทัน ให้ทำอย่างน้อย:

- Post
- Reply
- Like
- Follow
- DM

### `x_client.py`
แก้ตามนี้:

1. รองรับ `APP_BEARER_TOKEN` และ fallback `BEARER_TOKEN`
2. เพิ่ม function แปลง rate-limit headers เป็น dict:

```python
parse_rate_limit_headers(headers: dict) -> dict
```

3. Error 400/401/402/403/404/429 ต้องยังเป็นภาษาไทย และบอกจุดแก้
4. ห้าม log token

### `.env.example`
ปรับให้มี key ชัดเจน:

```env
APP_BEARER_TOKEN=
BEARER_TOKEN=
USER_ACCESS_TOKEN=
X_REFRESH_TOKEN=
SELF_USER_ID=
MY_USERNAME=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
SEND_TELEGRAM=0
X_API_BASE_URL=https://api.x.com/2
```

### `README_TH.md`
ปรับให้เป็นคู่มือใหม่ของ V6 และชี้ไปที่ `README_START_HERE_TH.md`

## Acceptance Checks
หลังแก้เสร็จ ต้องรันคำสั่งนี้และต้องผ่าน:

```bash
python -m py_compile *.py
python health_check.py --offline
```

ถ้ารันบน Windows ให้เพิ่มการเช็ก:

```bat
START_HERE.bat
```

## สิ่งที่ต้องส่งกลับหลังทำเสร็จ
ให้สรุปเป็นภาษาไทย:

1. แก้ไฟล์อะไรบ้าง
2. เพิ่มไฟล์อะไรบ้าง
3. วิธีรันโปรแกรม
4. วิธีเช็ก error เร็ว
5. จุดที่ยังไม่ทำใน Phase 1
6. ผลลัพธ์จาก `python -m py_compile *.py`
7. ผลลัพธ์จาก `python health_check.py --offline`

## คำสั่งเริ่มงานสำหรับ Codex
ทำงานตามไฟล์นี้ทั้งหมด โดยเริ่มจากอ่านโค้ดเดิมก่อน แล้วแก้แบบ minimal-change ไม่รื้อระบบเดิม ถ้าเจอจุดเสี่ยง ให้แก้ด้วยวิธีที่ปลอดภัยที่สุดและไม่ยิง X API จริงระหว่างทดสอบ
