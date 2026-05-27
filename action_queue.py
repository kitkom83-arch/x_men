from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


AUDIT_PATH = Path("outputs") / "action_audit.jsonl"
TOKEN_WORDS = ("token", "secret", "authorization", "bearer")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        clean = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(word in key_text for word in TOKEN_WORDS):
                clean[key] = "[ซ่อน]"
            else:
                clean[key] = _sanitize(item)
        return clean
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _text_preview(payload: dict) -> str:
    text = str(payload.get("text") or payload.get("dm_text") or payload.get("target") or "")
    return text.replace("\n", " ")[:120]


def _target_id(payload: dict) -> str:
    for key in ("target_id", "tweet_id", "reply_to_tweet_id", "target_user_id", "participant_id"):
        if payload.get(key):
            return str(payload.get(key))
    return ""


def _append(record: dict) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def queue_action(action_type: str, payload: dict) -> dict:
    record = {
        "action_id": uuid.uuid4().hex,
        "created_at": _now_iso(),
        "action_type": action_type,
        "target_id": _target_id(payload),
        "text_preview": _text_preview(payload),
        "status": "queued",
        "payload": _sanitize(payload),
    }
    _append(record)
    return record


def mark_action_status(action_id: str, status: str, result: dict | None = None) -> dict:
    record = {
        "action_id": action_id,
        "created_at": _now_iso(),
        "action_type": "status_update",
        "target_id": "",
        "text_preview": "",
        "status": status,
        "result": _sanitize(result or {}),
    }
    _append(record)
    return record


def load_actions(limit: int = 100) -> list[dict]:
    if not AUDIT_PATH.exists():
        return []
    rows: list[dict] = []
    with AUDIT_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-max(1, int(limit or 100)) :]
