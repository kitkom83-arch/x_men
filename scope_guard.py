from __future__ import annotations

from collections.abc import Iterable


ACTION_SCOPES: dict[str, set[str]] = {
    "read_posts": {"tweet.read", "users.read"},
    "create_post": {"tweet.write"},
    "reply": {"tweet.write"},
    "like": {"like.write"},
    "follow": {"follows.write"},
    "dm": {"dm.read", "dm.write"},
    "media_upload": {"media.write"},
    "refresh": {"offline.access"},
}


ACTION_LABELS: dict[str, str] = {
    "read_posts": "อ่านโพสต์",
    "create_post": "โพสต์",
    "reply": "ตอบกลับ",
    "like": "Like",
    "follow": "Follow",
    "dm": "DM",
    "media_upload": "อัปโหลดรูป",
    "refresh": "Refresh Token",
}


def normalize_scopes(scopes: str | Iterable[str]) -> set[str]:
    if isinstance(scopes, str):
        raw = scopes.replace(",", " ").split()
    else:
        raw = list(scopes)
    return {str(scope).strip() for scope in raw if str(scope).strip()}


def required_scopes(action_name: str) -> set[str]:
    return set(ACTION_SCOPES.get(action_name, set()))


def missing_scopes(action_name: str, available_scopes: str | Iterable[str]) -> list[str]:
    available = normalize_scopes(available_scopes)
    return sorted(required_scopes(action_name) - available)


def format_scope_warning(action_name: str, available_scopes: str | Iterable[str]) -> str:
    missing = missing_scopes(action_name, available_scopes)
    label = ACTION_LABELS.get(action_name, action_name)
    if not missing:
        return f"Scope สำหรับ {label} ดูพร้อมใช้งาน"
    return f"Token อาจยังขาด scope สำหรับ {label}: {', '.join(missing)}"
