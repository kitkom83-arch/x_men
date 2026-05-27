from __future__ import annotations


SPAM_KEYWORDS = {
    "เครดิตฟรี",
    "เว็บตรง",
    "แตกง่าย",
    "ฝากถอน",
    "สมัคร",
    "โบนัส",
    "คาสิโน",
    "บาคาร่า",
    "พนัน",
}


def check_action_policy(action_type: str, payload: dict, recent_actions: list[dict] | None = None) -> list[str]:
    warnings: list[str] = []
    action = action_type.lower()
    text = str(payload.get("text") or payload.get("dm_text") or "").strip()
    recent = recent_actions or []

    if action == "dm" and len([a for a in recent if str(a.get("action_type", "")).lower() == "dm"]) >= 20:
        warnings.append("พบคิว DM จำนวนมาก ควรหยุดตรวจข้อความก่อนเพื่อเลี่ยงพฤติกรรมคล้ายสแปม")
    if action == "follow" and len([a for a in recent if str(a.get("action_type", "")).lower() == "follow"]) >= 50:
        warnings.append("พบคิว Follow จำนวนมาก ควรแบ่งรอบและตรวจบัญชีเป้าหมายก่อน")
    if text:
        same_text = [
            a for a in recent
            if str(a.get("text_preview", "")).strip() and str(a.get("text_preview", "")).strip() == text[:120]
        ]
        if len(same_text) >= 3:
            warnings.append("พบข้อความซ้ำหลายครั้ง ควรปรับข้อความให้เหมาะกับแต่ละคนก่อนส่ง")
        found = [word for word in SPAM_KEYWORDS if word in text]
        if found:
            warnings.append(f"ข้อความมีคำเสี่ยงสแปม: {', '.join(sorted(found))}")
    return warnings


def format_policy_warnings(warnings: list[str]) -> str:
    if not warnings:
        return "ไม่พบสัญญาณเสี่ยงจาก policy guard"
    return "คำเตือนก่อนยิง Action จริง:\n" + "\n".join(f"- {warning}" for warning in warnings)
