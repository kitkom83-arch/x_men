from __future__ import annotations

import base64
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

DEFAULT_API_BASE_URL = "https://api.x.com/2"
DEFAULT_ADS_API_BASE_URL = "https://ads-api.x.com/12"


class XAPIError(Exception):
    def __init__(self, status_code: int, message: str, payload: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


class XConnectionError(Exception):
    pass


@dataclass
class APIResult:
    payload: dict
    headers: dict


def parse_rate_limit_headers(headers: dict) -> dict:
    h = headers or {}
    return {
        "limit": h.get("x-rate-limit-limit"),
        "remaining": h.get("x-rate-limit-remaining"),
        "reset": h.get("x-rate-limit-reset"),
    }


class XClient:
    def __init__(self, bearer_token: str = "", user_access_token: str = "", api_base_url: str = DEFAULT_API_BASE_URL):
        self.bearer_token = (bearer_token or os.environ.get("APP_BEARER_TOKEN") or os.environ.get("BEARER_TOKEN") or "").strip()
        self.user_access_token = (user_access_token or os.environ.get("USER_ACCESS_TOKEN") or "").strip()
        self.api_base_url = (api_base_url or DEFAULT_API_BASE_URL).rstrip("/")
        self.last_headers: Dict[str, str] = {}

    def _auth_token(self, token_type: str) -> str:
        if token_type == "user":
            token = self.user_access_token
            label = "USER_ACCESS_TOKEN"
        else:
            token = self.bearer_token
            label = "APP_BEARER_TOKEN หรือ BEARER_TOKEN"
        if not token:
            raise XAPIError(0, f"ยังไม่ได้ใส่ {label}")
        return token

    def _headers(self, token_type: str = "bearer", json_body: bool = False) -> dict:
        headers = {"Authorization": f"Bearer {self._auth_token(token_type)}"}
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _request(self, method: str, endpoint: str, *, params: Optional[dict] = None, json: Optional[dict] = None,
                 token_type: str = "bearer", base_url: Optional[str] = None, timeout: int = 60) -> APIResult:
        base = (base_url or self.api_base_url).rstrip("/")
        url = endpoint if endpoint.startswith("http") else f"{base}/{endpoint.lstrip('/')}"
        try:
            resp = requests.request(
                method,
                url,
                params=params,
                json=json,
                headers=self._headers(token_type, json_body=json is not None),
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise XConnectionError(f"เชื่อมต่อ X API ไม่ได้: {self._redact(str(exc))}") from exc
        self.last_headers = dict(resp.headers)
        try:
            payload = resp.json() if resp.text else {}
        except ValueError:
            payload = {"raw": resp.text}
        if resp.status_code >= 400:
            detail = self._format_error(resp.status_code, payload)
            raise XAPIError(resp.status_code, detail, payload)
        return APIResult(payload=payload, headers=dict(resp.headers))

    @staticmethod
    def _format_error(status: int, payload: dict) -> str:
        if status == 400:
            prefix = "ข้อผิดพลาด 400: คำค้นหรือพารามิเตอร์ผิดรูปแบบ | จุดแก้: ตรวจ query, id, max_results และพารามิเตอร์ที่ส่ง"
        elif status == 401:
            prefix = "ข้อผิดพลาด 401: Token ผิด / หมดอายุ / สิทธิ์ไม่พอ | จุดแก้: ใส่ APP_BEARER_TOKEN หรือ USER_ACCESS_TOKEN ใหม่"
        elif status == 402:
            prefix = "ข้อผิดพลาด 402: เครดิต X API หมดหรือยังไม่ได้ซื้อ Credits | จุดแก้: เช็ก usage และ billing ใน X Developer Portal"
        elif status == 403:
            prefix = "ข้อผิดพลาด 403: App/Plan/Permission ไม่มีสิทธิ์ใช้งาน endpoint นี้ | จุดแก้: เช็ก plan, app permission และ OAuth scope"
        elif status == 404:
            prefix = "ข้อผิดพลาด 404: ไม่พบข้อมูลหรือ endpoint | จุดแก้: ตรวจ id, username หรือ endpoint ว่าถูกต้อง"
        elif status == 429:
            prefix = "ข้อผิดพลาด 429: เรียก API ถี่เกิน rate limit | จุดแก้: รอ reset หรือลดจำนวนคำค้น"
        else:
            prefix = f"ข้อผิดพลาด {status}"
        parts = []
        if isinstance(payload, dict):
            if payload.get("title"):
                parts.append(XClient._redact(str(payload.get("title"))))
            if payload.get("detail"):
                parts.append(XClient._redact(str(payload.get("detail"))))
            for err in payload.get("errors", []) or []:
                if isinstance(err, dict):
                    text = err.get("detail") or err.get("title") or str(err)
                    parts.append(XClient._redact(str(text)))
            if payload.get("type"):
                parts.append(XClient._redact(str(payload.get("type"))))
        return prefix + (" | " + " | ".join(parts) if parts else "")

    @staticmethod
    def _redact(text: str) -> str:
        out = str(text)
        for marker in ("Bearer ", "bearer "):
            if marker in out:
                before, _, after = out.partition(marker)
                tail = after.split(" ", 1)
                out = before + marker + "[ซ่อน]" + ((" " + tail[1]) if len(tail) > 1 else "")
        return out

    def rate_limit_text(self) -> str:
        parsed = parse_rate_limit_headers(self.last_headers or {})
        limit = parsed.get("limit")
        remain = parsed.get("remaining")
        reset = parsed.get("reset")
        if not any([limit, remain, reset]):
            return "ไม่มีข้อมูล rate limit ใน header รอบล่าสุด"
        return f"rate limit: remaining={remain}, limit={limit}, reset={reset}"

    def count_recent_posts(self, query: str, granularity: str = "day") -> dict:
        params = {"query": query, "granularity": granularity}
        return self._request("GET", "/tweets/counts/recent", params=params, token_type="bearer").payload

    def recent_search(self, query: str, max_posts: int = 10, since_id: str = "") -> List[dict]:
        max_posts = max(1, int(max_posts))
        rows: List[dict] = []
        next_token = None
        while len(rows) < max_posts:
            per_page = min(100, max(10, max_posts - len(rows)))
            params = {
                "query": query,
                "max_results": per_page,
                "tweet.fields": "created_at,author_id,public_metrics,conversation_id,lang,entities,possibly_sensitive,source,referenced_tweets",
                "expansions": "author_id",
                "user.fields": "id,name,username,created_at,description,public_metrics,verified,location,protected,profile_image_url",
            }
            if next_token:
                params["next_token"] = next_token
            if since_id:
                params["since_id"] = since_id
            payload = self._request("GET", "/tweets/search/recent", params=params, token_type="bearer").payload
            users = {u.get("id"): u for u in payload.get("includes", {}).get("users", []) or []}
            for tw in payload.get("data", []) or []:
                author = users.get(tw.get("author_id"), {})
                metrics = tw.get("public_metrics", {}) or {}
                user_metrics = author.get("public_metrics", {}) or {}
                username = author.get("username", "")
                row = {
                    "query": query,
                    "id": tw.get("id", ""),
                    "created_at": tw.get("created_at", ""),
                    "author_id": tw.get("author_id", ""),
                    "username": username,
                    "name": author.get("name", ""),
                    "user_description": author.get("description", ""),
                    "user_location": author.get("location", ""),
                    "user_verified": author.get("verified", ""),
                    "user_protected": author.get("protected", ""),
                    "followers_count": user_metrics.get("followers_count", 0),
                    "following_count": user_metrics.get("following_count", 0),
                    "user_tweet_count": user_metrics.get("tweet_count", 0),
                    "text": tw.get("text", ""),
                    "lang": tw.get("lang", ""),
                    "conversation_id": tw.get("conversation_id", ""),
                    "like_count": metrics.get("like_count", 0),
                    "reply_count": metrics.get("reply_count", 0),
                    "retweet_count": metrics.get("retweet_count", 0),
                    "quote_count": metrics.get("quote_count", 0),
                    "bookmark_count": metrics.get("bookmark_count", 0),
                    "impression_count": metrics.get("impression_count", 0),
                    "source": tw.get("source", ""),
                    "possibly_sensitive": tw.get("possibly_sensitive", ""),
                    "url": f"https://x.com/{username}/status/{tw.get('id','')}" if username and tw.get("id") else "",
                }
                rows.append(row)
                if len(rows) >= max_posts:
                    break
            next_token = payload.get("meta", {}).get("next_token")
            if not next_token:
                break
        return rows[:max_posts]

    def usage_tweets(self) -> dict:
        return self._request("GET", "/usage/tweets", token_type="bearer").payload

    def trends_by_woeid(self, woeid: int = 23424960, max_trends: int = 20) -> dict:
        params = {"max_trends": max(1, min(50, int(max_trends))), "trend.fields": "trend_name,tweet_count"}
        return self._request("GET", f"/trends/by/woeid/{int(woeid)}", params=params, token_type="bearer").payload

    def lookup_usernames(self, usernames: List[str]) -> List[dict]:
        clean = [u.strip().lstrip("@").strip() for u in usernames if u.strip()]
        if not clean:
            return []
        rows: List[dict] = []
        for i in range(0, len(clean), 100):
            batch = clean[i:i + 100]
            params = {
                "usernames": ",".join(batch),
                "user.fields": "id,name,username,created_at,description,public_metrics,verified,location,protected,url",
            }
            payload = self._request("GET", "/users/by", params=params, token_type="bearer").payload
            rows.extend(payload.get("data", []) or [])
        return rows

    def lookup_user_ids(self, ids: List[str]) -> List[dict]:
        clean = [str(u).strip() for u in ids if str(u).strip()]
        if not clean:
            return []
        rows: List[dict] = []
        for i in range(0, len(clean), 100):
            batch = clean[i:i + 100]
            params = {
                "ids": ",".join(batch),
                "user.fields": "id,name,username,created_at,description,public_metrics,verified,location,protected,url",
            }
            payload = self._request("GET", "/users", params=params, token_type="bearer").payload
            rows.extend(payload.get("data", []) or [])
        return rows

    def get_user_tweets(self, user_id: str, max_posts: int = 10) -> List[dict]:
        params = {
            "max_results": max(5, min(100, int(max_posts))),
            "tweet.fields": "created_at,author_id,public_metrics,conversation_id,lang,entities,possibly_sensitive,source",
            "exclude": "retweets,replies",
        }
        payload = self._request("GET", f"/users/{user_id}/tweets", params=params, token_type="bearer").payload
        out = []
        for tw in payload.get("data", []) or []:
            m = tw.get("public_metrics", {}) or {}
            out.append({
                "id": tw.get("id", ""), "author_id": tw.get("author_id", user_id), "created_at": tw.get("created_at", ""),
                "text": tw.get("text", ""), "lang": tw.get("lang", ""), "conversation_id": tw.get("conversation_id", ""),
                "like_count": m.get("like_count", 0), "reply_count": m.get("reply_count", 0),
                "retweet_count": m.get("retweet_count", 0), "quote_count": m.get("quote_count", 0),
                "bookmark_count": m.get("bookmark_count", 0), "impression_count": m.get("impression_count", 0),
            })
        return out

    def get_mentions(self, user_id: str, max_posts: int = 10) -> List[dict]:
        params = {
            "max_results": max(5, min(100, int(max_posts))),
            "tweet.fields": "created_at,author_id,public_metrics,conversation_id,lang,entities,possibly_sensitive,source",
            "expansions": "author_id",
            "user.fields": "id,name,username,created_at,description,public_metrics,verified,location,protected",
        }
        payload = self._request("GET", f"/users/{user_id}/mentions", params=params, token_type="bearer").payload
        users = {u.get("id"): u for u in payload.get("includes", {}).get("users", []) or []}
        out = []
        for tw in payload.get("data", []) or []:
            author = users.get(tw.get("author_id"), {})
            m = tw.get("public_metrics", {}) or {}
            username = author.get("username", "")
            out.append({
                "query": f"mentions:{user_id}",
                "id": tw.get("id", ""), "author_id": tw.get("author_id", ""), "username": username,
                "name": author.get("name", ""), "created_at": tw.get("created_at", ""), "text": tw.get("text", ""), "lang": tw.get("lang", ""),
                "conversation_id": tw.get("conversation_id", ""), "like_count": m.get("like_count", 0),
                "reply_count": m.get("reply_count", 0), "retweet_count": m.get("retweet_count", 0), "quote_count": m.get("quote_count", 0),
                "followers_count": (author.get("public_metrics", {}) or {}).get("followers_count", 0),
                "url": f"https://x.com/{username}/status/{tw.get('id','')}" if username and tw.get("id") else "",
            })
        return out

    def me(self) -> dict:
        params = {"user.fields": "id,name,username,created_at,description,public_metrics,verified,location"}
        return self._request("GET", "/users/me", params=params, token_type="user").payload

    def publish_post(self, text: str, reply_to_tweet_id: str = "", media_ids: Optional[List[str]] = None) -> dict:
        body: Dict[str, Any] = {"text": text}
        if reply_to_tweet_id:
            body["reply"] = {"in_reply_to_tweet_id": reply_to_tweet_id}
        if media_ids:
            body["media"] = {"media_ids": media_ids}
        return self._request("POST", "/tweets", json=body, token_type="user").payload

    def delete_post(self, tweet_id: str) -> dict:
        return self._request("DELETE", f"/tweets/{tweet_id}", token_type="user").payload

    def like_post(self, user_id: str, tweet_id: str) -> dict:
        return self._request("POST", f"/users/{user_id}/likes", json={"tweet_id": tweet_id}, token_type="user").payload

    def unlike_post(self, user_id: str, tweet_id: str) -> dict:
        return self._request("DELETE", f"/users/{user_id}/likes/{tweet_id}", token_type="user").payload

    def retweet_post(self, user_id: str, tweet_id: str) -> dict:
        return self._request("POST", f"/users/{user_id}/retweets", json={"tweet_id": tweet_id}, token_type="user").payload

    def unretweet_post(self, user_id: str, tweet_id: str) -> dict:
        return self._request("DELETE", f"/users/{user_id}/retweets/{tweet_id}", token_type="user").payload

    def follow_user(self, user_id: str, target_user_id: str) -> dict:
        return self._request("POST", f"/users/{user_id}/following", json={"target_user_id": target_user_id}, token_type="user").payload

    def unfollow_user(self, user_id: str, target_user_id: str) -> dict:
        return self._request("DELETE", f"/users/{user_id}/following/{target_user_id}", token_type="user").payload

    def send_dm(self, participant_id: str, text: str) -> dict:
        return self._request("POST", f"/dm_conversations/with/{participant_id}/messages", json={"text": text}, token_type="user").payload

    def create_list(self, name: str, description: str = "", private: bool = True) -> dict:
        return self._request("POST", "/lists", json={"name": name, "description": description, "private": private}, token_type="user").payload

    def add_list_member(self, list_id: str, user_id: str) -> dict:
        return self._request("POST", f"/lists/{list_id}/members", json={"user_id": user_id}, token_type="user").payload

    def remove_list_member(self, list_id: str, user_id: str) -> dict:
        return self._request("DELETE", f"/lists/{list_id}/members/{user_id}", token_type="user").payload

    def upload_media(self, file_path: str, media_category: str = "tweet_image") -> dict:
        path = Path(file_path)
        if not path.exists():
            raise XAPIError(0, f"ไม่พบไฟล์: {file_path}")
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        body = {"media": data, "media_category": media_category, "media_type": mime}
        return self._request("POST", "/media/upload", json=body, token_type="user", timeout=120).payload


class AdsClient:
    def __init__(self, consumer_key: str, consumer_secret: str, access_token: str, access_token_secret: str,
                 base_url: str = DEFAULT_ADS_API_BASE_URL):
        self.consumer_key = (consumer_key or "").strip()
        self.consumer_secret = (consumer_secret or "").strip()
        self.access_token = (access_token or "").strip()
        self.access_token_secret = (access_token_secret or "").strip()
        self.base_url = (base_url or DEFAULT_ADS_API_BASE_URL).rstrip("/")

    def _auth(self):
        if not all([self.consumer_key, self.consumer_secret, self.access_token, self.access_token_secret]):
            raise XAPIError(0, "ต้องใส่ Ads OAuth 1.0a ครบ 4 ช่อง")
        try:
            from requests_oauthlib import OAuth1
        except Exception as exc:
            raise XAPIError(0, "ยังไม่ได้ติดตั้ง requests-oauthlib ให้รัน FIX_INSTALL.bat") from exc
        return OAuth1(self.consumer_key, self.consumer_secret, self.access_token, self.access_token_secret)

    def analytics_sync(self, account_id: str, params: dict) -> dict:
        url = f"{self.base_url}/stats/accounts/{account_id}"
        try:
            resp = requests.get(url, params=params, auth=self._auth(), timeout=90)
        except requests.RequestException as exc:
            raise XConnectionError(f"เชื่อมต่อ Ads API ไม่ได้: {exc}") from exc
        try:
            payload = resp.json() if resp.text else {}
        except ValueError:
            payload = {"raw": resp.text}
        if resp.status_code >= 400:
            raise XAPIError(resp.status_code, XClient._format_error(resp.status_code, payload), payload)
        return payload
