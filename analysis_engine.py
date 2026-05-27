from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Tuple

SPAM_WORDS_DEFAULT = [
    "เครดิตฟรี", "เว็บตรง", "แตกง่าย", "ฝากถอน", "สมัคร", "แอดไลน์", "โบนัส", "โปรโมชั่น", "แจกฟรี", "รับเครดิตฟรี",
    "ลิงก์สมัคร", "บาคาร่า", "คาสิโน", "เว็บพนัน", "แทงบอล", "slot", "casino", "bet", "หวยออนไลน์", "รับโปร",
]
INTENT_WORDS_DEFAULT = [
    "แนะนำ", "ร้านไหนดี", "ที่ไหนดี", "หา", "อยากได้", "อยากซื้อ", "ซื้อที่ไหน", "มีใคร", "ขอพิกัด", "ราคา", "โปร",
    "ส่งไหม", "สั่ง", "รีวิว", "ถาม", "ช่วย", "แถวไหน", "นางรอง", "บุรีรัมย์",
]
PAIN_WORDS = ["แพง", "ส่งช้า", "รอนาน", "ไม่อร่อย", "ไม่ดี", "ผิดหวัง", "โกง", "ถอนเงินไม่ได้", "เสียหมด", "ติดพนัน", "หายาก", "หาไม่เจอ"]
QUESTION_WORDS = ["ไหม", "มั้ย", "ที่ไหน", "ยังไง", "แนะนำ", "ใครรู้", "ขอ", "ร้านไหนดี", "ราคา", "?"]
PRAISE_WORDS = ["อร่อย", "ดีมาก", "ชอบ", "น่ารัก", "ประทับใจ", "เด็ด", "หอม", "คุ้ม", "อร่อยมาก", "สวย"]
SELL_WORDS = ["ขาย", "รับออเดอร์", "พร้อมส่ง", "โปร", "ลด", "ส่งฟรี", "สมัคร", "แอด", "จอง", "สั่งได้"]
REVIEW_WORDS = ["รีวิว", "ลองแล้ว", "กินแล้ว", "ไปมา", "แวะ", "ซื้อมา", "ประสบการณ์"]


def split_words(raw: str) -> List[str]:
    if not raw:
        return []
    return [w.strip().lower() for w in re.split(r"[,\n|]+", raw) if w.strip()]


def contains_any(text: str, words: Iterable[str]) -> bool:
    t = (text or "").lower()
    return any(w.lower() in t for w in words if w)


def normalize_int(value, default=0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return default


def classify_text(text: str) -> str:
    t = (text or "").lower()
    if contains_any(t, SPAM_WORDS_DEFAULT):
        return "สแปม/โปรโมท"
    if contains_any(t, PAIN_WORDS):
        return "บ่น/ปัญหา"
    if contains_any(t, QUESTION_WORDS):
        return "ถาม/สนใจซื้อ"
    if contains_any(t, REVIEW_WORDS):
        return "รีวิว/ประสบการณ์"
    if contains_any(t, PRAISE_WORDS):
        return "ชม"
    if contains_any(t, SELL_WORDS):
        return "ขายของ/โปรโมท"
    return "ทั่วไป"


def engagement(row: dict) -> int:
    return (
        normalize_int(row.get("like_count"))
        + normalize_int(row.get("reply_count")) * 3
        + normalize_int(row.get("retweet_count")) * 2
        + normalize_int(row.get("quote_count")) * 2
        + normalize_int(row.get("bookmark_count"))
    )


def lead_score(row: dict, brand_words: List[str] | None = None) -> int:
    text = row.get("text", "") or ""
    score = 0
    category = classify_text(text)
    if category in {"ถาม/สนใจซื้อ", "บ่น/ปัญหา"}:
        score += 35
    if category in {"รีวิว/ประสบการณ์", "ชม"}:
        score += 12
    if contains_any(text, INTENT_WORDS_DEFAULT):
        score += 25
    if contains_any(text, PAIN_WORDS):
        score += 20
    if brand_words and contains_any(text, brand_words):
        score += 15
    score += min(20, engagement(row) // 5)
    followers = normalize_int(row.get("followers_count"))
    if followers >= 10000:
        score += 12
    elif followers >= 3000:
        score += 8
    elif followers >= 500:
        score += 4
    if category in {"สแปม/โปรโมท", "ขายของ/โปรโมท"}:
        score -= 35
    return max(0, min(100, score))


def interest_level(score: int) -> str:
    if score >= 70:
        return "สูง"
    if score >= 40:
        return "กลาง"
    return "ต่ำ"


def action_suggestion(row: dict) -> str:
    cat = row.get("category") or classify_text(row.get("text", ""))
    score = normalize_int(row.get("lead_score"))
    if cat == "ถาม/สนใจซื้อ":
        return "ควรตอบเร็ว + แนบพิกัด/ราคา/ทางสั่ง"
    if cat == "บ่น/ปัญหา":
        return "ควรตรวจรายละเอียด + ตอบเชิงช่วยเหลือ"
    if score >= 70:
        return "ควรเปิดดูโพสต์และพิจารณาตอบ"
    if cat == "ชม":
        return "เก็บเป็น UGC/ไอเดียคอนเทนต์"
    if cat == "รีวิว/ประสบการณ์":
        return "เก็บ insight และดู engagement"
    if cat == "สแปม/โปรโมท":
        return "ไม่ต้องตอบ / ใช้เป็นข้อมูลสแปม"
    return "เก็บดูแนวโน้ม"


def reply_draft(row: dict, brand_name: str = "ร้านเรา") -> str:
    cat = row.get("category") or classify_text(row.get("text", ""))
    if cat == "ถาม/สนใจซื้อ":
        return f"สวัสดีครับ ขอบคุณที่ถามครับ {brand_name} มีรายละเอียด/พิกัด/ช่องทางสั่งให้ดูได้ครับ สนใจแบบไหนเป็นพิเศษครับ"
    if cat == "บ่น/ปัญหา":
        return "สวัสดีครับ ขอบคุณที่แจ้งครับ เดี๋ยวขอทราบรายละเอียดเพิ่มเติมเพื่อช่วยเช็กให้ครับ"
    if cat == "ชม":
        return "ขอบคุณมากครับ ดีใจที่ชอบครับ 🙏"
    if cat == "รีวิว/ประสบการณ์":
        return "ขอบคุณที่แชร์ประสบการณ์ครับ ขออนุญาตเก็บเป็นข้อมูลปรับปรุง/ต่อยอดนะครับ"
    return "สวัสดีครับ ขอบคุณที่แชร์ครับ"


def filter_rows(rows: List[dict], block_words_raw: str = "", require_words_raw: str = "", remove_blocked: bool = True) -> Tuple[List[dict], List[dict]]:
    block_words = split_words(block_words_raw)
    require_words = split_words(require_words_raw)
    kept, removed = [], []
    for row in rows:
        text = row.get("text", "") or ""
        reasons = []
        if block_words and contains_any(text, block_words):
            reasons.append("เจอคำห้าม")
        if require_words and not contains_any(text, require_words):
            reasons.append("ไม่มีคำที่ต้องมี")
        row2 = dict(row)
        row2["filter_reason"] = ", ".join(reasons)
        if reasons and remove_blocked:
            removed.append(row2)
        else:
            kept.append(row2)
    return kept, removed


def analyze_rows(rows: List[dict], brand_name: str = "ร้านเรา", brand_words_raw: str = "") -> List[dict]:
    brand_words = split_words(brand_words_raw or brand_name)
    out = []
    for row in rows:
        r = dict(row)
        r["category"] = classify_text(r.get("text", ""))
        r["engagement_score"] = engagement(r)
        r["lead_score"] = lead_score(r, brand_words)
        r["interest_level"] = interest_level(r["lead_score"])
        r["action_suggestion"] = action_suggestion(r)
        r["reply_draft"] = reply_draft(r, brand_name=brand_name)
        out.append(r)
    out.sort(key=lambda x: (normalize_int(x.get("lead_score")), normalize_int(x.get("engagement_score"))), reverse=True)
    return out


def summarize(rows: List[dict]) -> dict:
    cat = Counter(r.get("category", "ทั่วไป") for r in rows)
    query = Counter(r.get("query", "") for r in rows)
    top = sorted(rows, key=lambda x: normalize_int(x.get("lead_score")), reverse=True)[:10]
    return {
        "total_posts": len(rows),
        "categories": dict(cat),
        "queries": dict(query),
        "high_interest": sum(1 for r in rows if r.get("interest_level") == "สูง"),
        "medium_interest": sum(1 for r in rows if r.get("interest_level") == "กลาง"),
        "top_posts": top,
        "content_ideas": content_ideas(rows),
    }


def content_ideas(rows: List[dict]) -> List[str]:
    all_text = "\n".join(r.get("text", "") for r in rows).lower()
    ideas = []
    if contains_any(all_text, ["ของฝาก", "ฝาก", "กลับบ้าน"]):
        ideas.append("รวมของฝากที่เหมาะซื้อกลับบ้าน")
    if contains_any(all_text, ["หวานน้อย", "สุขภาพ", "น้ำตาล"]):
        ideas.append("เมนูหวานน้อยสำหรับคนรักสุขภาพ")
    if contains_any(all_text, ["พิกัด", "อยู่ไหน", "แถวไหน"]):
        ideas.append("โพสต์พิกัดร้าน + แผนที่ + วิธีเดินทาง")
    if contains_any(all_text, ["ราคา", "แพง", "คุ้ม", "โปร"]):
        ideas.append("โปรเซ็ตคุ้มค่า / ราคาเริ่มต้นชัดเจน")
    if contains_any(all_text, ["ส่ง", "เดลิเวอรี่", "พร้อมส่ง"]):
        ideas.append("คอนเทนต์พร้อมส่ง/บริการส่งในพื้นที่")
    if contains_any(all_text, ["เค้ก", "วันเกิด"]):
        ideas.append("เค้กวันเกิด/ขนมจัดเซ็ตสำหรับงานสำคัญ")
    if not ideas:
        ideas = ["สรุปประเด็นที่คนพูดถึงมากสุด", "โพสต์ถาม-ตอบจากคำถามลูกค้าจริง", "คอนเทนต์รีวิวจากโพสต์ที่ engagement สูง"]
    return ideas[:8]


def creator_scores(rows: List[dict]) -> List[dict]:
    by_author: Dict[str, dict] = {}
    for r in rows:
        aid = r.get("author_id") or r.get("username") or "unknown"
        item = by_author.setdefault(aid, {
            "author_id": aid,
            "username": r.get("username", ""),
            "name": r.get("name", ""),
            "followers_count": normalize_int(r.get("followers_count")),
            "post_count": 0,
            "total_engagement": 0,
            "max_lead_score": 0,
            "sample_url": r.get("url", ""),
            "sample_text": r.get("text", ""),
        })
        item["post_count"] += 1
        item["total_engagement"] += engagement(r)
        item["max_lead_score"] = max(item["max_lead_score"], normalize_int(r.get("lead_score")))
        if not item.get("sample_url"):
            item["sample_url"] = r.get("url", "")
    out = []
    for item in by_author.values():
        followers = normalize_int(item.get("followers_count"))
        avg_eng = item["total_engagement"] / max(1, item["post_count"])
        score = min(100, int(item["max_lead_score"] * 0.45 + min(35, avg_eng) + min(20, followers / 1000)))
        item["creator_score"] = score
        item["avg_engagement"] = round(avg_eng, 2)
        item["creator_level"] = interest_level(score)
        out.append(item)
    out.sort(key=lambda x: x["creator_score"], reverse=True)
    return out
