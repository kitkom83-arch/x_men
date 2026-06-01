from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Tuple

SPAM_WORDS_DEFAULT = [
    "เครดิตฟรี", "เว็บตรง", "แตกง่าย", "ฝากถอน", "สมัคร", "แอดไลน์", "โบนัส", "โปรโมชั่น", "แจกฟรี", "รับเครดิตฟรี",
    "ลิงก์สมัคร", "บาคาร่า", "คาสิโน", "เว็บพนัน", "แทงบอล", "slot", "casino", "bet", "หวยออนไลน์", "รับโปร",
]
REAL_INTENT_PHRASES = [
    "เว็บไหนดี",
    "มีเว็บไหน",
    "แนะนำเว็บ",
    "ใครมีเว็บ",
    "หาเว็บ",
    "ขอเว็บ",
    "แนะนำหน่อย",
    "ได้จริงไหม",
    "จ่ายจริงไหม",
    "ถอนจริงไหม",
]
INTENT_WORDS_DEFAULT = REAL_INTENT_PHRASES
BRAND_WORDS_DEFAULT = [
    "MAHA289",
    "maha289.com",
    "BN9Arena",
    "@BN9Arena",
    "ZWZAY57AJYYXC2QP",
    "code.bn9.one",
]
PAIN_POINT_WORDS = [
    "โดนโกง",
    "เว็บโกง",
    "โกงแล้ว",
    "โกงจริง",
    "ถอนเงินไม่ได้",
    "ไม่จ่าย",
    "ติดต่อไม่ได้",
    "โดนหลอก",
    "ถอนช้า",
    "แอดมินไม่ตอบ",
    "เงินหาย",
    "ล็อกบัญชี",
]
PROMO_NEGATION_PHRASES = [
    "ไม่มีโกง",
    "ไม่โกง",
    "มั่นคง",
    "ปลอดภัย",
    "จ่ายจริง",
    "ถอนจริง",
    "เว็บตรง",
    "สมัคร",
    "เครดิตฟรี",
    "โปร",
    "โบนัส",
]
PAIN_POINT_COMPLAINT_PHRASES = PAIN_POINT_WORDS
QUESTION_WORDS = ["ไหม", "มั้ย", "ที่ไหน", "ยังไง", "แนะนำ", "ใครรู้", "ขอ", "?"]
PRAISE_WORDS = ["ดีมาก", "ชอบ", "ประทับใจ", "คุ้ม"]
SELL_WORDS = ["ขาย", "โปร", "ลด", "ส่งฟรี", "สมัคร", "แอด", "รับโปร"]
REVIEW_WORDS = ["รีวิว", "ลองแล้ว", "ประสบการณ์"]
SAFE_CONTENT_IDEAS = [
    "วิธีตรวจสอบช่องทางหลักก่อนใช้โค้ด",
    "FAQ วิธีใช้โค้ดกิจกรรม",
    "อ่านเงื่อนไขกิจกรรมก่อนรับสิทธิ์",
    "ระวังเว็บปลอม / ลิงก์ปลอม",
    "Checklist ความปลอดภัยก่อนกรอกข้อมูล",
    "เล่นอย่างรับผิดชอบ",
]
ALLOWED_RECOMMENDED_ACTIONS = {
    "review_only",
    "insight_only",
    "manual_reply_if_brand_mention",
    "no_action_spam",
    "creator_review",
    "pain_point_report",
}
URL_RE = re.compile(r"(?:https?://|www\.)\S+|(?:\b[a-z0-9][a-z0-9.-]*\.(?:com|net|org|io|co|one|th|me|info|biz)\b)(?:/\S*)?", re.IGNORECASE)
HASHTAG_RE = re.compile(r"(?<!\w)#\S+")
NON_DEDUPE_TEXT_RE = re.compile(r"[^\w\s#@\u0E00-\u0E7F]", re.UNICODE)


def split_words(raw: str) -> List[str]:
    if not raw:
        return []
    return [w.strip().lower() for w in re.split(r"[,\n|]+", raw) if w.strip()]


def contains_any(text: str, words: Iterable[str]) -> bool:
    t = (text or "").lower()
    return any(w.lower() in t for w in words if w)


def normalize_post_text_for_dedupe(text: str) -> str:
    cleaned = URL_RE.sub(" ", (text or "").lower())
    cleaned = NON_DEDUPE_TEXT_RE.sub(" ", cleaned)
    tokens = re.split(r"\s+", cleaned.strip())
    seen_hashtags = set()
    normalized_tokens = []
    for token in tokens:
        if not token:
            continue
        if token.startswith("#"):
            if token in seen_hashtags:
                continue
            seen_hashtags.add(token)
        normalized_tokens.append(token)
    return " ".join(normalized_tokens)


def url_count(text: str) -> int:
    return len(URL_RE.findall(text or ""))


def hashtag_tokens(text: str) -> List[str]:
    return HASHTAG_RE.findall(text or "")


def text_tokens(text: str) -> List[str]:
    return [token for token in re.split(r"\s+", (text or "").strip()) if token]


def hashtag_ratio(text: str) -> float:
    tokens = text_tokens(text)
    if not tokens:
        return 0.0
    return len(hashtag_tokens(text)) / len(tokens)


def is_hashtag_only(text: str) -> bool:
    tokens = text_tokens(text)
    if not tokens:
        return False
    hashtags = hashtag_tokens(text)
    if not hashtags:
        return False
    non_hashtag = [token for token in tokens if not token.startswith("#")]
    mostly_empty = not re.sub(r"[\s#\w\u0E00-\u0E7F]+", "", text or "").strip()
    return len(hashtags) / len(tokens) > 0.60 or (not non_hashtag and mostly_empty)


def has_real_intent(text: str) -> bool:
    return contains_any(text, REAL_INTENT_PHRASES)


def is_promo_like(text: str) -> bool:
    return url_count(text) > 0 and (
        contains_any(text, SPAM_WORDS_DEFAULT)
        or contains_any(text, SELL_WORDS)
        or contains_any(text, PROMO_NEGATION_PHRASES)
    )


def has_pain_point_intent(text: str) -> bool:
    t = (text or "").lower()
    if is_promo_like(t) and contains_any(t, PROMO_NEGATION_PHRASES):
        return False
    return contains_any(t, PAIN_POINT_COMPLAINT_PHRASES)


def is_brand_mention(text: str, brand_words: List[str] | None = None) -> bool:
    words = list(BRAND_WORDS_DEFAULT)
    if brand_words:
        words.extend(brand_words)
    return contains_any(text, words)


def normalize_int(value, default=0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return default


def classify_text(text: str) -> str:
    t = (text or "").lower()
    if is_hashtag_only(t):
        return "spam_promo"
    if url_count(t) > 1:
        return "spam_promo"
    if is_promo_like(t):
        return "spam_promo"
    if has_pain_point_intent(t):
        return "pain_point"
    if is_brand_mention(t):
        return "customer_care_manual"
    if contains_any(t, SPAM_WORDS_DEFAULT):
        return "spam_promo"
    if has_real_intent(t):
        return "lead_candidate"
    if contains_any(t, QUESTION_WORDS):
        return "review_only"
    if contains_any(t, REVIEW_WORDS):
        return "insight"
    if contains_any(t, PRAISE_WORDS):
        return "insight"
    if contains_any(t, SELL_WORDS):
        return "spam_promo"
    return "general"


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
    urls = url_count(text)
    hashtag_only = is_hashtag_only(text)
    if category == "lead_candidate" and not hashtag_only and urls <= 1:
        score += 35
    if category in {"insight", "customer_care_manual", "pain_point"}:
        score += 12
    if has_real_intent(text) and not hashtag_only:
        score += 35
    if has_pain_point_intent(text):
        score += 10
    if is_brand_mention(text, brand_words):
        score += 15
    score += min(20, engagement(row) // 5)
    followers = normalize_int(row.get("followers_count"))
    if followers >= 10000:
        score += 12
    elif followers >= 3000:
        score += 8
    elif followers >= 500:
        score += 4
    if urls:
        score -= 15
    if urls > 1:
        score -= 45
    if hashtag_only:
        score -= 80
    elif hashtag_ratio(text) > 0.60:
        score -= 60
    if category == "spam_promo":
        score -= 45
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
    recommended = row.get("recommendedAction") or recommended_action(row)
    if recommended == "manual_reply_if_brand_mention":
        return "ตรวจเองเท่านั้น: brand mention ควรตอบแบบ manual หากเหมาะสม"
    if recommended == "pain_point_report":
        return "ทำรายงาน pain point เพื่อตรวจสอบ ไม่ยิง action อัตโนมัติ"
    if recommended == "no_action_spam":
        return "ไม่ต้องตอบ ใช้เป็นข้อมูลสแปม/โปรโมท"
    if recommended == "creator_review":
        return "ตรวจเป็น creator candidate ด้วยคนก่อน"
    if recommended == "insight_only":
        return "เก็บเป็น insight/content idea เท่านั้น"
    if cat == "lead_candidate" or score >= 70:
        return "เปิดดูเป็น lead candidate ด้วยคนก่อน ไม่มี action อัตโนมัติ"
    return "review only"


def recommended_action(row: dict) -> str:
    text = row.get("text", "") or ""
    category = row.get("category") or classify_text(text)
    score = normalize_int(row.get("lead_score"))
    followers = normalize_int(row.get("followers_count"))
    if category == "pain_point":
        return "pain_point_report"
    if category == "customer_care_manual":
        return "manual_reply_if_brand_mention"
    if category == "spam_promo" or is_hashtag_only(text) or url_count(text) > 1:
        return "no_action_spam"
    if followers >= 3000 and score >= 35:
        return "creator_review"
    if category == "insight":
        return "insight_only"
    return "review_only"


def should_include_review_queue(row: dict) -> bool:
    action = row.get("recommendedAction") or recommended_action(row)
    if action == "no_action_spam":
        return False
    if action in {"manual_reply_if_brand_mention", "pain_point_report", "creator_review"}:
        return True
    return normalize_int(row.get("lead_score")) >= 40


def reply_draft(row: dict, brand_name: str = "ร้านเรา") -> str:
    cat = row.get("category") or classify_text(row.get("text", ""))
    if cat == "customer_care_manual":
        return f"ตรวจเองก่อนตอบ: หากเป็นช่องทางหลักของ {brand_name} ให้ตอบแบบสุภาพและไม่แนบลิงก์เสี่ยง"
    if cat == "pain_point":
        return "ตรวจเองก่อนตอบ: ขอรายละเอียดอย่างระมัดระวังและส่งต่อเป็นรายงาน pain point"
    if cat == "lead_candidate":
        return "ตรวจเองก่อนตอบ: ให้ข้อมูลทั่วไปและย้ำให้ตรวจสอบช่องทางหลัก/เงื่อนไขก่อนใช้โค้ด"
    if cat == "spam_promo":
        return "ไม่ควรตอบ"
    return "เก็บเป็น insight / review only"


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
        r["recommendedAction"] = recommended_action(r)
        r["action_suggestion"] = action_suggestion(r)
        r["reply_draft"] = reply_draft(r, brand_name=brand_name)
        out.append(r)
    out.sort(key=lambda x: (normalize_int(x.get("lead_score")), normalize_int(x.get("engagement_score"))), reverse=True)
    return out


def dedupe_key(row: dict) -> str:
    username = (row.get("username") or row.get("author_id") or "unknown")
    normalized = normalize_post_text_for_dedupe(row.get("text", ""))
    return f"{str(username).strip().lower()}|{normalized}"


def _dedupe_sort_key(row: dict) -> tuple:
    return (
        normalize_int(row.get("lead_score", row.get("score"))),
        normalize_int(row.get("engagement_score")),
        str(row.get("created_at") or ""),
    )


def deduplicate_rows(rows: List[dict]) -> List[dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for row in rows:
        key = dedupe_key(row)
        if key.endswith("|"):
            key = f"{key}{row.get('id') or row.get('post_id') or row.get('tweet_id') or len(grouped)}"
        grouped[key].append(row)

    out = []
    for group in grouped.values():
        group_sorted = sorted(group, key=_dedupe_sort_key, reverse=True)
        kept = dict(group_sorted[0])
        post_ids = [str(r.get("id") or r.get("post_id") or r.get("tweet_id") or "") for r in group_sorted]
        post_ids = [pid for pid in post_ids if pid]
        kept["duplicate_count"] = len(group_sorted)
        kept["duplicate_post_ids"] = ", ".join(post_ids[:20])
        kept["duplicate_examples"] = " | ".join((r.get("text", "") or "")[:160] for r in group_sorted[1:4])
        if len(group_sorted) > 1 and is_promo_like(kept.get("text", "")):
            kept["category"] = "spam_promo"
            kept["lead_score"] = 0
            kept["interest_level"] = interest_level(0)
            kept["recommendedAction"] = "no_action_spam"
            kept["action_suggestion"] = action_suggestion(kept)
            kept["reply_draft"] = reply_draft(kept)
        out.append(kept)
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
    return SAFE_CONTENT_IDEAS[:8]


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
