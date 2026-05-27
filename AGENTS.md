# AGENTS.md — BN9 X Social Real V6 Easy Ready

## งานหลัก
อัปเกรดโปรเจกต์เดิม BN9 X Social Real V5 Mega ให้เป็น V6 Easy Ready โดยทำตามไฟล์ `00_PASTE_TO_CODEX_FIRST.md` เท่านั้น

## กติกา
- ห้ามลบฟีเจอร์เดิมของ V5
- ห้ามยิง X API แบบ write/action จริงระหว่างทดสอบ
- ห้ามพิมพ์ token จริงลง log, dashboard, error message หรือ report
- รองรับทั้ง `APP_BEARER_TOKEN` และ fallback `BEARER_TOKEN`
- UI และ error message ต้องเป็นภาษาไทย
- โค้ดต้องรันบน Windows ได้ผ่าน `.bat`

## เช็กงานหลังแก้
รันคำสั่งนี้ในโฟลเดอร์นี้:

```bash
python -m py_compile *.py
python health_check.py --offline
```
