from __future__ import annotations

import requests


class TelegramError(Exception):
    pass


def send_message(bot_token: str, chat_id: str, text: str) -> dict:
    bot_token = (bot_token or "").strip()
    chat_id = (chat_id or "").strip()
    if not bot_token:
        raise TelegramError("ยังไม่ได้ใส่ Telegram Bot Token")
    if not chat_id:
        raise TelegramError("ยังไม่ได้ใส่ Telegram Chat ID")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": True}, timeout=30)
    except requests.RequestException as exc:
        raise TelegramError(f"ส่ง Telegram ไม่ได้: {exc}") from exc
    try:
        payload = resp.json()
    except Exception:
        payload = {"raw": resp.text}
    if resp.status_code >= 400 or not payload.get("ok", False):
        raise TelegramError(f"Telegram ERROR {resp.status_code}: {payload}")
    return payload


def get_updates(bot_token: str) -> dict:
    bot_token = (bot_token or "").strip()
    if not bot_token:
        raise TelegramError("ยังไม่ได้ใส่ Telegram Bot Token")
    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
    try:
        resp = requests.get(url, timeout=30)
    except requests.RequestException as exc:
        raise TelegramError(f"อ่าน Telegram update ไม่ได้: {exc}") from exc
    payload = resp.json()
    if resp.status_code >= 400 or not payload.get("ok", False):
        raise TelegramError(f"Telegram ERROR {resp.status_code}: {payload}")
    return payload


def latest_chat_id(bot_token: str) -> str:
    payload = get_updates(bot_token)
    results = payload.get("result", []) or []
    for item in reversed(results):
        msg = item.get("message") or item.get("edited_message") or item.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            return str(chat.get("id"))
    raise TelegramError("ยังไม่เจอ Chat ID ให้พิมพ์ test ไปหาบอทก่อน")
