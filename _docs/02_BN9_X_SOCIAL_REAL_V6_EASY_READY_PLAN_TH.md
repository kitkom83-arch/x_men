# แผนสร้าง BN9 X Social Real V6 Easy Ready

## เป้าหมาย
ใช้ `x_social_real_v5_1_token_helper` เป็นฐานเดิม แล้วปรับเป็นเวอร์ชันที่คนใช้งานเปิดแล้วทำตามได้ทันที โดยไม่ต้องเข้าใจโค้ดมาก

ชื่อที่แนะนำ: **BN9 X Social Real V6 Easy Ready**

## หลักการออกแบบ
1. ไม่เริ่มใหม่ ใช้ V5 เป็นฐาน
2. แยกงานอ่านข้อมูลออกจากงานยิง Action จริง
3. ตั้งค่า Token แบบ Wizard ทีละขั้น
4. มีปุ่ม Health Check เช็กทุกอย่างก่อนยิง API จริง
5. มี Cost Guard คุมจำนวนดึงและเตือนก่อนใช้เครดิต
6. มี Scope Guard บอกว่า Token ขาดสิทธิ์อะไร
7. Action จริงต้องมี Confirm 2 ชั้น
8. Ads API แยกเป็นระบบย่อย ไม่ปนกับ Organic API
9. Stream/Webhook ทำเป็น Phase 2 เพราะต้องใช้เซิร์ฟเวอร์และ HTTPS
10. ทุก error ต้องแปลเป็นภาษาคน พร้อมจุดแก้

## ความสามารถจาก X API ที่ควรเอามาใช้
| หมวด | ใส่ใน V6 หรือไม่ | เหตุผล |
|---|---:|---|
| Posts search / recent search | ใช้ทันที | เป็นแกน Social Listening |
| Create post / reply / delete | ใช้ทันที | มีใน V5 แล้ว ปรับ UI ให้ปลอดภัยขึ้น |
| Likes / Repost / Follow | ใช้ทันที | มีใน V5 แล้ว เพิ่ม Scope Guard |
| Direct Messages | ใช้ทันทีแบบ Manual | ป้องกัน DM ผิดและ Policy Risk |
| Trends by WOEID | ใช้ทันที | ทำ Trend Radar ได้ |
| Media upload | ใช้ทันทีสำหรับรูป | วิดีโอ/GIF chunk upload ใส่ Phase 2 |
| Lists | ใช้ทันที | ใช้เก็บ Creator / Lead / Competitor |
| Owned Reads | ใช้ทันที | ลดต้นทุนสำหรับข้อมูลของบัญชีตัวเอง |
| Usage / Rate limit headers | ใช้ทันที | คุมเครดิตและ 429 ได้ |
| Filtered Stream | Phase 2 | ต้องจัดการ connection ค้าง |
| Webhooks / Account Activity | Phase 2 | ต้องมี HTTPS public endpoint |
| Ads API | Phase 3 | Credential และระบบต่างจาก X API v2 |
| Enterprise / Firehose / Powerstream | ยังไม่ใส่ | ต้องมี entitlement เฉพาะ |

## โครงหน้าจอใหม่
### 0 Start Here
- ปุ่มติดตั้ง Library
- ปุ่มเปิด Setup Wizard
- ปุ่ม Health Check
- สถานะ Token: App Bearer / User Token / Telegram / Ads
- สรุปว่าใช้ฟีเจอร์อะไรได้แล้ว

### 1 ตั้งค่า Token
แยกชื่อให้ชัด:
- `APP_BEARER_TOKEN` = อ่านข้อมูลสาธารณะ
- `USER_ACCESS_TOKEN` = โพสต์ / Like / Follow / DM / Media
- `X_REFRESH_TOKEN` = ต่ออายุ User Token
- `ADS_*` = เฉพาะ Ads API

### 2 Social Listening
- เลือกสูตรคำค้น
- เช็กจำนวนก่อนดึง
- ประเมินเครดิตก่อนดึง
- ดึงจริง + วิเคราะห์ + รายงาน

### 3 Lead Inbox
- รวมโพสต์ที่น่าตอบ
- ปุ่มสร้าง Reply Draft
- ปุ่ม Copy Reply
- ปุ่ม Reply จริงแบบ Confirm

### 4 Trend / Creator / Competitor
- Trend Radar
- Creator Finder
- Competitor Watch
- Save to List

### 5 Action จริง
- Post / Reply / Like / Retweet / Follow / DM / List
- Require Confirm 2 ชั้น
- Action Queue ก่อนยิงจริง
- Log ทุก Action ลง `outputs/action_audit.jsonl`

### 6 Report
- dashboard.html
- report.xlsx
- lead_list.csv
- creator_list.csv
- action_audit.jsonl
- cost_summary.json

### 7 Ads API
- แยกไว้ท้ายสุด
- เปิดใช้เมื่อใส่ OAuth 1.0a ครบ
- ยังไม่ผูกกับ Social Listening ใน Phase 1

## ไฟล์ที่ต้องแก้ / เพิ่ม
| ไฟล์ | งานที่ทำ |
|---|---|
| `app.py` | เพิ่ม Start Here tab, Health Check, Cost Guard, Action Queue |
| `x_client.py` | เพิ่ม rate-limit parser, cost estimate, refresh token, bookmark/block/mute, better media helper |
| `oauth_user_token_helper.py` | เพิ่ม auto refresh token และแสดง token expiry |
| `analysis_engine.py` | เพิ่ม Lead Reason, Risk Label, Reply Tone |
| `reporting.py` | เพิ่ม cost_summary, action_audit, next_actions ใน dashboard |
| `.env.example` | เปลี่ยนชื่อ Token ให้ชัด และเพิ่ม default flags |
| `README_TH.md` | เขียนใหม่เป็นขั้นตอน 1-2-3 |
| `START_HERE.bat` | ไฟล์เดียวสำหรับผู้ใช้เริ่มงาน |
| `health_check.py` | เช็ก Python, Library, .env, Token, Scope, Rate limit |
| `cost_guard.py` | คำนวณต้นทุนคร่าว ๆ ก่อนดึงข้อมูล |
| `scope_guard.py` | ตรวจว่า scope พอกับปุ่มที่กดหรือไม่ |
| `action_queue.py` | เก็บ Action ก่อนยิงจริง |
| `policy_guard.py` | กันคำสั่งเสี่ยง เช่น DM จำนวนมาก / Spam / Scraping |

## Phase 1: ทำให้พร้อมใช้จริง
สิ่งที่ต้องเสร็จ:
1. START_HERE.bat
2. Setup Wizard
3. Health Check
4. Cost Guard
5. Scope Guard
6. Rename token labels ให้ไม่สับสน
7. Dashboard อ่านง่ายขึ้น
8. Action Confirm 2 ชั้น
9. Log action และ API error แบบอ่านง่าย
10. README ใหม่

ผลลัพธ์ Phase 1:
- เปิดไฟล์เดียวเริ่มได้
- รู้ทันทีว่า Token ใช้ได้หรือไม่ได้
- รู้ทันทีว่ากดปุ่มไหนได้
- ลดโอกาสยิง Action ผิด
- ลดโอกาสใช้เครดิตเกิน

## Phase 2: Real-time
สิ่งที่เพิ่ม:
1. Filtered Stream
2. Stream Rules Manager
3. Webhook endpoint guide
4. Deduplicate event ID
5. Alert เข้า Telegram แบบ near real-time

เงื่อนไข Phase 2:
- ต้องมีเครื่อง/เซิร์ฟเวอร์ที่รันต่อเนื่อง
- Webhook ต้องมี public HTTPS URL

## Phase 3: Ads API
สิ่งที่เพิ่ม:
1. Ads health check
2. ดึง campaign analytics
3. ดึง creative analytics
4. สรุป performance report
5. แยก credential ของ Ads API

## สูตรใช้งานสำหรับผู้ใช้จริง
1. กด `START_HERE.bat`
2. กด `Health Check`
3. ใส่ `APP_BEARER_TOKEN`
4. ทดสอบอ่านข้อมูล
5. เลือกสูตรคำค้น
6. กด `เช็กจำนวนก่อนดึง`
7. ดู Cost Estimate
8. กด `ดึงจริง + วิเคราะห์ + รายงาน`
9. เปิด `dashboard.html`
10. ถ้าจะ Reply / Like / DM ให้ทำ User Token ก่อน แล้วกดยืนยัน 2 ชั้น

## Error ที่ต้องแปลในระบบ
| Error | ข้อความที่ผู้ใช้ควรเห็น | จุดแก้ |
|---|---|---|
| 400 | คำค้นผิดรูปแบบ | แก้ query |
| 401 | Token ผิดหรือหมดอายุ | ใส่ token ใหม่ / refresh token |
| 402 | เครดิตหมด | เติมเครดิตใน X Developer Console |
| 403 | สิทธิ์ไม่พอ | เช็ก plan / scope / permission |
| 404 | ไม่เจอข้อมูล | เช็ก ID / username / endpoint |
| 429 | เรียกถี่เกิน | ลดจำนวนดึง / รอ reset |

## สรุป
ทำ V6 โดยยึด V5 เป็นฐาน แล้วเพิ่มชั้นใช้งานง่าย 5 ตัว:

1. Start Here
2. Health Check
3. Cost Guard
4. Scope Guard
5. Safe Action Queue

นี่คือทางที่ทำให้ระบบพร้อมใช้จริงที่สุด โดยไม่ต้องรื้อโค้ดเดิมทั้งหมด
