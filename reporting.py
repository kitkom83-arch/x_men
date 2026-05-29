from __future__ import annotations

import csv
import json
import os
import sys
import webbrowser
from datetime import datetime
from html import escape
from pathlib import Path
from typing import List, Optional

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

OUTPUT_DIR = Path("outputs")
MANUAL_REVIEW_ACTIONS = {"manual_reply_if_brand_mention", "pain_point_report", "creator_review"}


def now_run_dir(prefix: str = "run") -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    d = OUTPUT_DIR / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_csv(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    keys = []
    for r in rows:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _int_value(value, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return default


def _dashboard_review_rows(rows: List[dict]) -> List[dict]:
    review_rows = []
    for row in rows:
        action = str(row.get("recommendedAction") or "")
        if action == "no_action_spam":
            continue
        if action in MANUAL_REVIEW_ACTIONS or _int_value(row.get("lead_score")) >= 40:
            review_rows.append(row)
    return review_rows


def _sheet_from_rows(wb: Workbook, title: str, rows: List[dict]) -> None:
    ws = wb.create_sheet(title=title[:31])
    if not rows:
        ws.append(["ไม่มีข้อมูล"])
        return
    keys = []
    for r in rows:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    ws.append(keys)
    fill = PatternFill("solid", fgColor="1F4E78")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for r in rows:
        values = []
        for k in keys:
            value = r.get(k, "")
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            values.append(value)
        ws.append(values)
    ws.freeze_panes = "A2"
    for idx, key in enumerate(keys, start=1):
        width = min(60, max(12, len(key) + 2))
        if key in {"text", "reply_draft", "action_suggestion", "recommendedAction", "sample_text", "user_description"}:
            width = 45
        if key == "url":
            width = 42
        ws.column_dimensions[get_column_letter(idx)].width = width
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")


def save_excel(path: Path, sheets: dict[str, List[dict]], summary: Optional[dict] = None) -> None:
    wb = Workbook()
    default = wb.active
    default.title = "Summary"
    default.append(["หัวข้อ", "ค่า"])
    default["A1"].font = Font(bold=True, color="FFFFFF")
    default["B1"].font = Font(bold=True, color="FFFFFF")
    default["A1"].fill = PatternFill("solid", fgColor="1F4E78")
    default["B1"].fill = PatternFill("solid", fgColor="1F4E78")
    if summary:
        for k, v in summary.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            default.append([k, v])
    default.column_dimensions["A"].width = 28
    default.column_dimensions["B"].width = 80
    for title, rows in sheets.items():
        _sheet_from_rows(wb, title, rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def save_dashboard(path: Path, title: str, summary: dict, rows: List[dict], creators: Optional[List[dict]] = None, trends: Optional[List[dict]] = None) -> None:
    cats = summary.get("categories", {}) or {}
    ideas = summary.get("content_ideas", []) or []
    top = _dashboard_review_rows(rows)[:20]
    creators = creators or []
    trends = trends or []
    html = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{escape(title)}</title>",
        "<style>body{font-family:Segoe UI,Tahoma,sans-serif;margin:24px;background:#f6f7fb;color:#111} .card{background:white;border-radius:14px;padding:18px;margin:12px 0;box-shadow:0 1px 8px #ddd} table{border-collapse:collapse;width:100%;background:white} th,td{border:1px solid #ddd;padding:8px;vertical-align:top} th{background:#1f4e78;color:white} .kpi{display:inline-block;background:#fff;padding:18px;margin:8px;border-radius:14px;box-shadow:0 1px 8px #ddd;min-width:150px}.score{font-weight:bold}</style>",
        "</head><body>",
        f"<h1>{escape(title)}</h1>",
        f"<p>สร้างเมื่อ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>",
        "<div>",
        f"<div class='kpi'><b>โพสต์ทั้งหมด</b><br><span style='font-size:28px'>{summary.get('total_posts', len(rows))}</span></div>",
        f"<div class='kpi'><b>ความสนใจสูง</b><br><span style='font-size:28px'>{summary.get('high_interest', 0)}</span></div>",
        f"<div class='kpi'><b>ความสนใจกลาง</b><br><span style='font-size:28px'>{summary.get('medium_interest', 0)}</span></div>",
        "</div>",
        "<div class='card'><h2>หมวดโพสต์</h2><ul>",
    ]
    for k, v in cats.items():
        html.append(f"<li><b>{escape(str(k))}</b>: {escape(str(v))}</li>")
    html.append("</ul></div>")
    html.append("<div class='card'><h2>ไอเดียคอนเทนต์</h2><ol>")
    for idea in ideas:
        html.append(f"<li>{escape(str(idea))}</li>")
    html.append("</ol></div>")
    if trends:
        html.append("<div class='card'><h2>Trend Radar</h2><table><tr><th>Trend</th><th>Tweet count</th></tr>")
        for r in trends[:30]:
            html.append(f"<tr><td>{escape(str(r.get('trend_name','')))}</td><td>{escape(str(r.get('tweet_count','')))}</td></tr>")
        html.append("</table></div>")
    if creators:
        html.append("<div class='card'><h2>Creator Finder</h2><table><tr><th>Score</th><th>User</th><th>Followers</th><th>Posts</th><th>Sample</th></tr>")
        for c in creators[:20]:
            html.append(f"<tr><td class='score'>{escape(str(c.get('creator_score','')))}</td><td>@{escape(str(c.get('username','')))}</td><td>{escape(str(c.get('followers_count','')))}</td><td>{escape(str(c.get('post_count','')))}</td><td>{escape(str(c.get('sample_text','')))}</td></tr>")
        html.append("</table></div>")
    html.append("<div class='card'><h2>Lead Queue / โพสต์ที่ควรดู</h2><table><tr><th>Score</th><th>หมวด</th><th>User</th><th>ข้อความ</th><th>Recommended Action</th><th>ควรทำอะไร</th><th>ลิงก์</th></tr>")
    for r in top:
        html.append(
            "<tr>"
            f"<td class='score'>{escape(str(r.get('lead_score','')))}</td>"
            f"<td>{escape(str(r.get('category','')))}</td>"
            f"<td>@{escape(str(r.get('username','')))}</td>"
            f"<td>{escape(str(r.get('text','')))}</td>"
            f"<td>{escape(str(r.get('recommendedAction','')))}</td>"
            f"<td>{escape(str(r.get('action_suggestion','')))}</td>"
            f"<td><a href='{escape(str(r.get('url','')))}' target='_blank'>เปิด</a></td>"
            "</tr>"
        )
    html.append("</table></div></body></html>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(html), encoding="utf-8")


def open_path(path: Path) -> None:
    path = path.resolve()
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        os.system(f"open {path!s}")
    else:
        os.system(f"xdg-open {path!s}")


def open_browser(path: Path) -> None:
    webbrowser.open(path.resolve().as_uri())
