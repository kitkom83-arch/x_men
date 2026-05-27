from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

ENV_PATH = Path('.env')
AUTH_URL = 'https://x.com/i/oauth2/authorize'
TOKEN_URL = 'https://api.x.com/2/oauth2/token'
ME_URL = 'https://api.x.com/2/users/me'
DEFAULT_REDIRECT_URI = 'http://127.0.0.1:8765/callback'
DEFAULT_SCOPES = 'tweet.read users.read tweet.write like.write follows.read follows.write list.read list.write dm.read dm.write media.write offline.access'


def read_env(path: Path = ENV_PATH) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        data[k.strip()] = v.strip()
    return data


def write_env(values: Dict[str, str], path: Path = ENV_PATH) -> None:
    current = read_env(path)
    current.update({k: str(v) for k, v in values.items()})
    # Keep a stable order for important keys; append any extra keys after.
    order = [
        'BEARER_TOKEN', 'USER_ACCESS_TOKEN', 'X_REFRESH_TOKEN', 'TOKEN_EXPIRES_AT',
        'SELF_USER_ID', 'MY_USERNAME', 'X_CLIENT_ID', 'X_CLIENT_SECRET', 'OAUTH_REDIRECT_URI', 'OAUTH_SCOPES',
        'BRAND_NAME', 'BRAND_WORDS', 'X_API_BASE_URL',
        'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'SEND_TELEGRAM',
    ]
    keys = [k for k in order if k in current] + [k for k in current.keys() if k not in order]
    lines = [f'{k}={current[k]}' for k in keys]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def make_pkce() -> Tuple[str, str]:
    verifier = b64url(secrets.token_bytes(64))
    digest = hashlib.sha256(verifier.encode('ascii')).digest()
    challenge = b64url(digest)
    return verifier, challenge


class CallbackHandler(BaseHTTPRequestHandler):
    server_version = 'BN9OAuthCallback/1.0'

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        self.server.oauth_result = {k: v[0] for k, v in qs.items()}  # type: ignore[attr-defined]
        if 'code' in qs:
            title = 'สำเร็จ'
            body = 'ได้รับ authorization code แล้ว กลับไปดูหน้าต่างโปรแกรมได้เลยครับ'
        else:
            title = 'มีปัญหา'
            body = 'ยังไม่ได้รับ code จาก X. กลับไปดูหน้าต่างโปรแกรมครับ'
        page = f'''<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title></head>
<body style="font-family:Arial,sans-serif;padding:30px"><h2>{html.escape(title)}</h2><p>{html.escape(body)}</p></body></html>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(page.encode('utf-8'))

    def log_message(self, format, *args):
        return


def start_callback_server(redirect_uri: str) -> Tuple[HTTPServer, str, int]:
    parsed = urllib.parse.urlparse(redirect_uri)
    host = parsed.hostname or '127.0.0.1'
    port = parsed.port or 8765
    server = HTTPServer((host, port), CallbackHandler)
    server.oauth_result = None  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, host, port


def exchange_code(client_id: str, client_secret: str, redirect_uri: str, code: str, verifier: str) -> dict:
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'code_verifier': verifier,
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    auth = None
    if client_secret:
        raw = f'{client_id}:{client_secret}'.encode('utf-8')
        headers['Authorization'] = 'Basic ' + base64.b64encode(raw).decode('ascii')
    else:
        data['client_id'] = client_id
    resp = requests.post(TOKEN_URL, data=data, headers=headers, timeout=45)
    try:
        payload = resp.json()
    except Exception:
        payload = {'raw': resp.text}
    if resp.status_code >= 400:
        raise RuntimeError(f'TOKEN ERROR {resp.status_code}: {json.dumps(payload, ensure_ascii=False, indent=2)}')
    return payload


def get_me(access_token: str) -> dict:
    params = {'user.fields': 'id,name,username,created_at,description,public_metrics,verified,location'}
    resp = requests.get(ME_URL, params=params, headers={'Authorization': f'Bearer {access_token}'}, timeout=45)
    try:
        payload = resp.json()
    except Exception:
        payload = {'raw': resp.text}
    if resp.status_code >= 400:
        raise RuntimeError(f'USERS/ME ERROR {resp.status_code}: {json.dumps(payload, ensure_ascii=False, indent=2)}')
    return payload


def main():
    print('=' * 70)
    print('BN9 X OAuth 2.0 User Access Token Helper')
    print('=' * 70)
    print('ใช้ตัวนี้เพื่อเอา User Access Token สำหรับโพสต์/ไลก์/ฟอล/DM/List จริง')
    print('ห้ามส่ง Token ที่ได้ให้ใครดูนะครับ')
    print()

    if not ENV_PATH.exists() and Path('.env.example').exists():
        ENV_PATH.write_text(Path('.env.example').read_text(encoding='utf-8'), encoding='utf-8')

    env = read_env()
    redirect_uri = env.get('OAUTH_REDIRECT_URI') or DEFAULT_REDIRECT_URI
    scopes = env.get('OAUTH_SCOPES') or DEFAULT_SCOPES

    client_id = env.get('X_CLIENT_ID') or input('วาง OAuth 2.0 Client ID: ').strip()
    client_secret = env.get('X_CLIENT_SECRET') or input('วาง Client Secret ถ้ามี ถ้าไม่มีให้กด Enter: ').strip()

    if not client_id:
        print('ERROR: ต้องมี Client ID')
        input('กด Enter เพื่อปิด...')
        return

    print()
    print('Redirect URI ที่ต้องตั้งใน X Developer ให้ตรงเป๊ะ:')
    print(redirect_uri)
    print()
    print('Scopes ที่จะขอสิทธิ์:')
    print(scopes)
    print()
    input('ถ้าตั้งค่าใน X Developer ครบแล้ว กด Enter เพื่อเปิดหน้า Authorize...')

    verifier, challenge = make_pkce()
    state = secrets.token_urlsafe(24)
    server, _, _ = start_callback_server(redirect_uri)

    params = {
        'response_type': 'code',
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'scope': scopes,
        'state': state,
        'code_challenge': challenge,
        'code_challenge_method': 'S256',
    }
    url = AUTH_URL + '?' + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    print('กำลังเปิด Browser...')
    print(url)
    webbrowser.open(url)

    print('รอคุณ Login/Authorize ใน Browser...')
    timeout_at = time.time() + 180
    result: Optional[dict] = None
    try:
        while time.time() < timeout_at:
            result = getattr(server, 'oauth_result', None)
            if result:
                break
            time.sleep(0.3)
    finally:
        server.shutdown()

    if not result:
        print('ERROR: หมดเวลา ยังไม่ได้รับ code จาก Browser')
        input('กด Enter เพื่อปิด...')
        return
    if result.get('state') != state:
        print('ERROR: state ไม่ตรง หยุดเพื่อความปลอดภัย')
        input('กด Enter เพื่อปิด...')
        return
    if result.get('error'):
        print('ERROR จาก X:', result)
        input('กด Enter เพื่อปิด...')
        return

    code = result.get('code', '')
    if not code:
        print('ERROR: ไม่พบ code')
        print(result)
        input('กด Enter เพื่อปิด...')
        return

    print('ได้ code แล้ว กำลังแลกเป็น access token...')
    try:
        token_payload = exchange_code(client_id, client_secret, redirect_uri, code, verifier)
        access_token = token_payload.get('access_token', '')
        refresh_token = token_payload.get('refresh_token', '')
        expires_in = int(token_payload.get('expires_in') or 0)
        expires_at = int(time.time()) + expires_in if expires_in else ''
        if not access_token:
            raise RuntimeError('ไม่พบ access_token ใน response')
        me_payload = get_me(access_token)
        me = me_payload.get('data', {}) or {}
        values = {
            'USER_ACCESS_TOKEN': access_token,
            'X_REFRESH_TOKEN': refresh_token,
            'TOKEN_EXPIRES_AT': expires_at,
            'SELF_USER_ID': me.get('id', ''),
            'MY_USERNAME': me.get('username', ''),
            'X_CLIENT_ID': client_id,
            'X_CLIENT_SECRET': client_secret,
            'OAUTH_REDIRECT_URI': redirect_uri,
            'OAUTH_SCOPES': scopes,
        }
        write_env(values)
        print()
        print('สำเร็จ ✅ บันทึกลง .env แล้ว')
        print(f"SELF_USER_ID = {me.get('id', '')}")
        print(f"MY_USERNAME = {me.get('username', '')}")
        print('เปิดโปรแกรม V5 ใหม่ แล้วช่อง User Access Token / Self User ID / Username จะถูกเติมจาก .env')
    except Exception as exc:
        print('\nERROR ตอนแลก Token:')
        print(exc)
        print('\nจุดที่ต้องเช็กเร็ว:')
        print('1) Callback URL ใน X Developer ต้องตรงกับ http://127.0.0.1:8765/callback')
        print('2) Client ID ต้องถูก')
        print('3) ถ้าเลือก Web App/Automated App ให้ใส่ Client Secret ด้วย')
        print('4) ต้องกด Authorize แล้วกลับมาภายในเวลาสั้น ๆ')
    input('\nกด Enter เพื่อปิด...')


if __name__ == '__main__':
    main()
