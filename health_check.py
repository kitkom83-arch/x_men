from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from storage import read_env


REQUIREMENT_IMPORTS = {
    "requests-oauthlib": "requests_oauthlib",
}


def line(status: str, message: str) -> str:
    return f"[{status}] {message}"


def package_name(requirement: str) -> str:
    name = requirement.strip().split(";", 1)[0].split("[", 1)[0]
    for marker in (">=", "==", "<=", "~=", ">", "<"):
        if marker in name:
            name = name.split(marker, 1)[0]
    name = name.strip()
    return REQUIREMENT_IMPORTS.get(name, name.replace("-", "_"))


def check_requirements() -> list[str]:
    path = Path("requirements.txt")
    if not path.exists():
        return [line("เตือน", "ไม่พบ requirements.txt")]
    results: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#"):
            continue
        mod = package_name(raw)
        try:
            importlib.import_module(mod)
            results.append(line("ผ่าน", f"Library พร้อมใช้งาน: {mod}"))
        except Exception:
            results.append(line("ต้องแก้", f"ยังไม่มี library: {mod} ให้กด FIX_INSTALL.bat"))
    return results


def run_offline_checks() -> tuple[list[str], dict]:
    results: list[str] = []
    version = sys.version_info
    if version >= (3, 10):
        results.append(line("ผ่าน", f"Python พร้อมใช้งาน: {version.major}.{version.minor}.{version.micro}"))
    else:
        results.append(line("ต้องแก้", "ควรใช้ Python 3.10 ขึ้นไป"))

    results.extend(check_requirements())

    env_path = Path(".env")
    env = read_env(env_path)
    if env_path.exists():
        results.append(line("ผ่าน", "พบไฟล์ .env"))
    else:
        results.append(line("เตือน", "ยังไม่มี .env ให้คัดลอกจาก .env.example หรือกด START_HERE.bat"))

    app_bearer = env.get("APP_BEARER_TOKEN", "").strip()
    old_bearer = env.get("BEARER_TOKEN", "").strip()
    if app_bearer:
        results.append(line("ผ่าน", "พบ APP_BEARER_TOKEN สำหรับอ่านข้อมูลสาธารณะ"))
    elif old_bearer:
        results.append(line("เตือน", "พบ BEARER_TOKEN เดิม ระบบจะใช้เป็น fallback ได้ แต่แนะนำให้ย้ายไป APP_BEARER_TOKEN"))
    else:
        results.append(line("ต้องแก้", "ยังไม่มี APP_BEARER_TOKEN: อ่านข้อมูล X ไม่ได้"))

    if env.get("USER_ACCESS_TOKEN", "").strip():
        results.append(line("ผ่าน", "พบ USER_ACCESS_TOKEN สำหรับ Action จริง"))
    else:
        results.append(line("เตือน", "ยังไม่มี USER_ACCESS_TOKEN: ปุ่ม Post/Like/DM จะยังใช้ไม่ได้"))

    if env.get("X_REFRESH_TOKEN", "").strip():
        results.append(line("ผ่าน", "พบ X_REFRESH_TOKEN"))
    else:
        results.append(line("เตือน", "ยังไม่มี X_REFRESH_TOKEN: ถ้า token หมดอายุอาจต้องขอใหม่เอง"))

    if env.get("TELEGRAM_BOT_TOKEN", "").strip() and env.get("TELEGRAM_CHAT_ID", "").strip():
        results.append(line("ผ่าน", "Telegram พร้อมใช้งาน"))
    else:
        results.append(line("เตือน", "Telegram ยังไม่ครบ: ไม่กระทบการอ่าน X แต่ส่งแจ้งเตือนไม่ได้"))

    outputs = Path("outputs")
    try:
        outputs.mkdir(parents=True, exist_ok=True)
        test_file = outputs / ".health_check_write_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink(missing_ok=True)
        results.append(line("ผ่าน", "โฟลเดอร์ outputs สร้างและเขียนไฟล์ได้"))
    except Exception as exc:
        results.append(line("ต้องแก้", f"เขียน outputs ไม่ได้: {exc}"))

    return results, env


def run_online_checks(env: dict) -> list[str]:
    from x_client import XAPIError, XClient, XConnectionError

    results: list[str] = []
    bearer = env.get("APP_BEARER_TOKEN", "").strip() or env.get("BEARER_TOKEN", "").strip()
    if not bearer:
        return [line("ต้องแก้", "ไม่มี APP_BEARER_TOKEN หรือ BEARER_TOKEN จึงทดสอบ online ไม่ได้")]
    client = XClient(bearer, env.get("USER_ACCESS_TOKEN", ""), env.get("X_API_BASE_URL", ""))
    try:
        client.usage_tweets()
        results.append(line("ผ่าน", "Online read-only: Usage API ตอบกลับ"))
    except (XAPIError, XConnectionError) as exc:
        results.append(line("ต้องแก้", f"Online read-only ไม่ผ่าน: {exc}"))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="BN9 X Social Real V6 Health Check")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="เช็กเฉพาะเครื่อง ไม่ยิง API")
    mode.add_argument("--online", action="store_true", help="ทดสอบ read-only API")
    args = parser.parse_args()

    results, env = run_offline_checks()
    if args.online:
        results.append(line("เตือน", "โหมด online จะยิง API แบบอ่านอย่างเดียว ไม่มี write/action"))
        results.extend(run_online_checks(env))
    else:
        results.append(line("ผ่าน", "โหมด offline: ไม่ยิง X API จริง"))

    for item in results:
        print(item)
    critical_markers = ("ควรใช้ Python", "ยังไม่มี library", "เขียน outputs ไม่ได้", "Online read-only ไม่ผ่าน")
    return 1 if any(any(marker in item for marker in critical_markers) for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
