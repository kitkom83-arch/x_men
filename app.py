from __future__ import annotations

import json
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from action_queue import load_actions, mark_action_status, queue_action
from analysis_engine import SPAM_WORDS_DEFAULT, INTENT_WORDS_DEFAULT, analyze_rows, creator_scores, filter_rows, should_include_review_queue, split_words, summarize
from cost_guard import estimate_recent_search_cost, format_cost_warning
from policy_guard import check_action_policy, format_policy_warnings
from recipes import RECIPES, recipe_names
from reporting import now_run_dir, open_browser, open_path, save_csv, save_dashboard, save_excel, save_json, OUTPUT_DIR
from scope_guard import format_scope_warning
from storage import read_env, write_env, ENV_PATH
from telegram_notify import TelegramError, latest_chat_id, send_message
from x_client import AdsClient, DEFAULT_ADS_API_BASE_URL, DEFAULT_API_BASE_URL, XAPIError, XClient, XConnectionError


APP_TITLE = "BN9 X Social Real V6 Easy Ready"
_STATUS_VAR: tk.StringVar | None = None
USER_PUBLIC_METRIC_FIELDS = (
    "followers_count",
    "following_count",
    "tweet_count",
    "listed_count",
    "like_count",
    "media_count",
)


def mask_secret(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return "ยังไม่ได้ตั้งค่า"
    if len(text) <= 10:
        return text[:2] + "..." + text[-2:]
    return text[:6] + "..." + text[-4:]


def add_guide_box(parent, title, purpose, steps, examples, expected, warnings=None):
    box = ttk.LabelFrame(parent, text=title)
    box.columnconfigure(0, weight=1)
    lines = []
    if purpose:
        lines.append("หน้านี้ใช้ทำอะไร")
        lines.extend(f"- {item}" for item in purpose)
    if steps:
        lines.append("")
        lines.append("วิธีใช้ทีละขั้น")
        lines.extend(f"{i}. {item}" for i, item in enumerate(steps, start=1))
    if examples:
        lines.append("")
        lines.append("ตัวอย่างที่ใส่ได้")
        lines.extend(f"- {item}" for item in examples)
    if expected:
        lines.append("")
        lines.append("ผลลัพธ์ที่ควรได้")
        lines.extend(f"- {item}" for item in expected)
    if warnings:
        lines.append("")
        lines.append("คำเตือน")
        lines.extend(f"- {item}" for item in warnings)
    label_options = {"text": "\n".join(lines), "justify": "left", "wraplength": 1180}
    if "ระวัง" in title or "Action" in title:
        label_options["foreground"] = "red"
    ttk.Label(box, **label_options).grid(row=0, column=0, sticky="ew", padx=12, pady=10)
    return box


def add_example_button(parent, label, text_widget_or_entry, value, clear_first=True):
    def apply_value():
        target = text_widget_or_entry
        if isinstance(target, tk.Variable):
            target.set(value)
            return
        if clear_first:
            try:
                target.delete("1.0", "end")
            except tk.TclError:
                target.delete(0, "end")
        try:
            target.insert("1.0", value)
        except tk.TclError:
            target.insert(0, value)
    return ttk.Button(parent, text=label, command=apply_value)


def set_status(message):
    if _STATUS_VAR is not None:
        _STATUS_VAR.set(str(message)[:180])


def append_output(text_widget, message):
    if not text_widget:
        return
    text_widget.insert("end", str(message) + "\n")
    text_widget.see("end")


def explain_error(error_text) -> str:
    text = str(error_text or "")
    lower = text.lower()
    if "403" in text:
        return "คำอธิบาย: 403 หมายถึงสิทธิ์, plan, app permission หรือ OAuth scope ยังไม่พอสำหรับ endpoint นี้"
    if "429" in text or "rate limit" in lower:
        return "คำอธิบาย: 429 หมายถึงเรียก API ถี่เกิน rate limit ให้รอ reset หรือลดจำนวนคำค้น/จำนวนโพสต์"
    if "401" in text:
        return "คำอธิบาย: 401 หมายถึง token ผิด, หมดอายุ หรือใช้ token ผิดประเภท"
    if "400" in text:
        return "คำอธิบาย: 400 มักเกิดจาก query หรือพารามิเตอร์ผิดรูปแบบ"
    if "402" in text:
        return "คำอธิบาย: 402 หมายถึงเครดิตหรือ billing ของ X API ไม่พร้อม"
    if "not implemented" in lower or "404" in text:
        return "คำอธิบาย: ไม่พบ endpoint หรือ endpoint นี้ยังไม่พร้อมใช้งานในระบบ/plan ปัจจุบัน"
    if "token" in lower:
        return "คำอธิบาย: ตรวจ token ในแท็บตั้งค่า แต่ห้ามแคปหรือส่ง token เต็มให้ผู้อื่น"
    if "excel" in lower or "cannot convert" in lower:
        return "คำอธิบาย: ข้อมูลบางช่องเขียนลง Excel ไม่ได้โดยตรง ระบบควรแปลง dict/list เป็นข้อความก่อน"
    return "คำอธิบาย: ตรวจข้อความด้านบน, ค่า input, สิทธิ์ X API และลองรัน Health Check"


def flatten_public_metrics(row: dict) -> dict:
    flat = dict(row)
    metrics = flat.pop("public_metrics", {}) or {}
    if not isinstance(metrics, dict):
        metrics = {}
    for key in USER_PUBLIC_METRIC_FIELDS:
        flat[key] = metrics.get(key, flat.get(key, 0))
    return flat


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1360x900")
        self.root.minsize(1080, 760)
        self.env = read_env()
        self.last_run_dir: Path | None = None
        self.last_rows: list[dict] = []
        self.last_creators: list[dict] = []
        self.last_trends: list[dict] = []
        self.running = False

        self._vars()
        self._ui()
        self._apply_secret_visibility()
        self.refresh_start_status()
        self.log("พร้อมใช้งาน: เริ่มที่แท็บ 0 Start Here เพื่อเช็กสถานะก่อน")
        self.log("Action จริงจะเข้า Queue และต้องยืนยันก่อนยิง X API")

    def _vars(self):
        e = self.env
        self.bearer_var = tk.StringVar(value=e.get("APP_BEARER_TOKEN") or e.get("BEARER_TOKEN", ""))
        self.user_token_var = tk.StringVar(value=e.get("USER_ACCESS_TOKEN", ""))
        self.refresh_token_var = tk.StringVar(value=e.get("X_REFRESH_TOKEN", ""))
        self.self_user_id_var = tk.StringVar(value=e.get("SELF_USER_ID", ""))
        self.my_username_var = tk.StringVar(value=e.get("MY_USERNAME", ""))
        self.brand_name_var = tk.StringVar(value=e.get("BRAND_NAME", "ร้านเรา"))
        self.brand_words_var = tk.StringVar(value=e.get("BRAND_WORDS", ""))
        self.api_base_var = tk.StringVar(value=e.get("X_API_BASE_URL", DEFAULT_API_BASE_URL))
        self.tg_token_var = tk.StringVar(value=e.get("TELEGRAM_BOT_TOKEN", ""))
        self.tg_chat_var = tk.StringVar(value=e.get("TELEGRAM_CHAT_ID", ""))
        self.send_tg_var = tk.BooleanVar(value=e.get("SEND_TELEGRAM", "0") in ("1", "true", "TRUE", "yes"))
        self.woeid_var = tk.StringVar(value=e.get("WOEID", "23424960"))
        self.max_posts_var = tk.StringVar(value=e.get("MAX_POSTS", "10"))
        self.max_trends_var = tk.StringVar(value=e.get("MAX_TRENDS", "20"))
        self.show_secrets_var = tk.BooleanVar(value=False)
        self.exclude_rt_var = tk.BooleanVar(value=True)
        self.lang_th_var = tk.BooleanVar(value=True)
        self.block_words_var = tk.StringVar(value=e.get("BLOCK_WORDS", ", ".join(SPAM_WORDS_DEFAULT)))
        self.require_words_var = tk.StringVar(value=e.get("REQUIRE_WORDS", ""))
        self.remove_blocked_var = tk.BooleanVar(value=e.get("REMOVE_BLOCKED", "1") not in ("0", "false", "FALSE"))
        self.recipe_var = tk.StringVar(value=recipe_names()[0])
        self.status_var = tk.StringVar(value="พร้อม")
        self.ads_ck_var = tk.StringVar(value=e.get("ADS_CONSUMER_KEY", ""))
        self.ads_cs_var = tk.StringVar(value=e.get("ADS_CONSUMER_SECRET", ""))
        self.ads_at_var = tk.StringVar(value=e.get("ADS_ACCESS_TOKEN", ""))
        self.ads_as_var = tk.StringVar(value=e.get("ADS_ACCESS_TOKEN_SECRET", ""))
        self.ads_account_var = tk.StringVar(value=e.get("ADS_ACCOUNT_ID", ""))
        self.ads_base_var = tk.StringVar(value=e.get("ADS_API_BASE_URL", DEFAULT_ADS_API_BASE_URL))
        self.start_status_var = tk.StringVar(value="")

    def _ui(self):
        global _STATUS_VAR
        _STATUS_VAR = self.status_var
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        ttk.Label(root, text=APP_TITLE, font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w", padx=16, pady=(10, 4))
        self.nb = ttk.Notebook(root)
        self.nb.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)

        self.tab_start = ttk.Frame(self.nb)
        self.tab_settings = ttk.Frame(self.nb)
        self.tab_listen = ttk.Frame(self.nb)
        self.tab_trends = ttk.Frame(self.nb)
        self.tab_competitor = ttk.Frame(self.nb)
        self.tab_creator = ttk.Frame(self.nb)
        self.tab_care = ttk.Frame(self.nb)
        self.tab_actions = ttk.Frame(self.nb)
        self.tab_ads = ttk.Frame(self.nb)
        self.tab_logs = ttk.Frame(self.nb)

        self.nb.add(self.tab_start, text="0 Start Here")
        self.nb.add(self.tab_settings, text="1 ตั้งค่า")
        self.nb.add(self.tab_listen, text="2 Social Listening")
        self.nb.add(self.tab_trends, text="3 Trend Radar")
        self.nb.add(self.tab_competitor, text="4 คู่แข่ง")
        self.nb.add(self.tab_creator, text="5 Creator Finder")
        self.nb.add(self.tab_care, text="6 Customer Care")
        self.nb.add(self.tab_actions, text="7 Action จริง")
        self.nb.add(self.tab_ads, text="8 Ads Report")
        self.nb.add(self.tab_logs, text="Log/ผลลัพธ์")

        self._start_tab()
        self._settings_tab()
        self._listen_tab()
        self._trend_tab()
        self._competitor_tab()
        self._creator_tab()
        self._care_tab()
        self._actions_tab()
        self._ads_tab()
        self._logs_tab()

        footer = ttk.Frame(root)
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="เปิด outputs", command=lambda: open_path(OUTPUT_DIR)).grid(row=0, column=1, padx=4)
        ttk.Button(footer, text="เปิด Dashboard ล่าสุด", command=self.open_last_dashboard).grid(row=0, column=2, padx=4)

    def _start_tab(self):
        f = self.tab_start
        f.columnconfigure(0, weight=1)
        f.rowconfigure(1, weight=1)
        guide = add_guide_box(
            f,
            "เริ่มตรงนี้",
            ["ใช้ตรวจว่าระบบพร้อมหรือยัง", "ใช้เปิด Health Check", "ใช้เปิด outputs และ dashboard ล่าสุด"],
            ["กด Health Check", "ถ้าขึ้น [ผ่าน] ครบ ให้ไปเมนู 2 Social Listening", "ห้ามส่งภาพที่โชว์ token เต็ม ๆ"],
            ["ปุ่ม Health Check", "ปุ่มเปิด outputs", "ปุ่มเปิด Dashboard ล่าสุด"],
            ["Python พร้อม", "Library พร้อม", ".env มี", "token มี", "outputs เขียนไฟล์ได้"],
            ["ห้ามโชว์ token เต็ม", "ห้ามกด Action จริงจนกว่าจะทดสอบ Preview/Queue"],
        )
        guide.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        box = ttk.LabelFrame(f, text="สถานะ Token และระบบ")
        box.grid(row=1, column=0, sticky="nsew", padx=12, pady=8)
        box.columnconfigure(0, weight=1)
        ttk.Label(box, textvariable=self.start_status_var, justify="left").grid(row=0, column=0, sticky="nw", padx=12, pady=12)

        actions = ttk.Frame(f)
        actions.grid(row=2, column=0, sticky="ew", padx=12, pady=8)
        ttk.Button(actions, text="Health Check", command=lambda: self.threaded(self.run_health_check)).grid(row=0, column=0, padx=4, pady=4)
        ttk.Button(actions, text="เปิดแท็บตั้งค่า Token", command=lambda: self.nb.select(self.tab_settings)).grid(row=0, column=1, padx=4, pady=4)
        ttk.Button(actions, text="เปิด Social Listening", command=lambda: self.nb.select(self.tab_listen)).grid(row=0, column=2, padx=4, pady=4)
        ttk.Button(actions, text="เปิด outputs", command=lambda: open_path(OUTPUT_DIR)).grid(row=0, column=3, padx=4, pady=4)
        ttk.Button(actions, text="เปิด Dashboard ล่าสุด", command=self.open_last_dashboard).grid(row=0, column=4, padx=4, pady=4)
        ttk.Button(actions, text="อัปเดตสถานะ", command=self.refresh_start_status).grid(row=0, column=5, padx=4, pady=4)

    def _settings_tab(self):
        f = self.tab_settings
        f.columnconfigure(1, weight=1)
        guide = add_guide_box(
            f,
            "ตั้งค่า",
            ["ใช้ตรวจค่า .env และ token", "ใช้บันทึกค่า config"],
            ["ตรวจช่อง Token หลัก", "แก้เฉพาะค่าที่ต้องการ", "กด บันทึกค่าตั้งต้น เฉพาะตอนตั้งค่า config"],
            ["APP_BEARER_TOKEN = abc123...wxyz", "USER_ACCESS_TOKEN = ซ่อนในช่องกรอกและแสดงเฉพาะแบบย่อ"],
            ["ค่า config ถูกบันทึกลง .env", "Health Check อ่านค่าใหม่ได้"],
            ["หน้านี้ไม่ใช่หน้าค้นโพสต์", "ปุ่มบันทึกค่า ต้องใช้เฉพาะตอนแก้ config", "ระบบไม่แสดง token เต็มใน UI"],
        )
        guide.grid(row=0, column=0, columnspan=4, sticky="ew", padx=12, pady=(12, 4))
        ttk.Label(f, text="Token หลัก", font=("Segoe UI", 13, "bold")).grid(row=1, column=0, columnspan=4, sticky="w", padx=12, pady=(12, 4))
        row = 2
        self._entry(f, row, "App Bearer Token = อ่านข้อมูลสาธารณะ", self.bearer_var, secret=True); row += 1
        self._entry(f, row, "User Access Token = ยิง Action จริง เช่น Post/Like/DM", self.user_token_var, secret=True); row += 1
        self._entry(f, row, "X Refresh Token (ถ้ามี)", self.refresh_token_var, secret=True); row += 1
        self._entry(f, row, "Self User ID", self.self_user_id_var); row += 1
        self._entry(f, row, "Username ของเรา", self.my_username_var); row += 1
        self._entry(f, row, "Brand name", self.brand_name_var); row += 1
        self._entry(f, row, "Brand words เพิ่มเติม", self.brand_words_var); row += 1
        self._entry(f, row, "X API Base URL", self.api_base_var); row += 1
        ttk.Label(f, text="Token ถูกซ่อนเสมอ และแสดงเฉพาะ 6 ตัวหน้า + 4 ตัวท้าย").grid(row=row, column=1, sticky="w", padx=8, pady=4)
        ttk.Button(f, text="บันทึกค่าตั้งต้น", command=self.save_settings).grid(row=row, column=2, padx=8, pady=4)
        ttk.Button(f, text="ทดสอบ Bearer ด้วย Usage API", command=lambda: self.threaded(self.test_bearer)).grid(row=row, column=3, padx=8, pady=4)
        row += 1
        ttk.Button(f, text="ทดสอบ User Token + ดึง User ID อัตโนมัติ", command=lambda: self.threaded(self.test_user_token)).grid(row=row, column=1, padx=8, pady=6, sticky="w")
        ttk.Button(f, text="ดู .env แบบซ่อน Token", command=self.show_masked_env).grid(row=row, column=2, padx=8, pady=6, sticky="w")
        row += 1
        ttk.Separator(f).grid(row=row, column=0, columnspan=4, sticky="ew", padx=12, pady=10); row += 1
        ttk.Label(f, text="Telegram", font=("Segoe UI", 13, "bold")).grid(row=row, column=0, columnspan=4, sticky="w", padx=12, pady=(8, 4)); row += 1
        self._entry(f, row, "Telegram Bot Token", self.tg_token_var, secret=True); row += 1
        self._entry(f, row, "Telegram Chat ID", self.tg_chat_var); row += 1
        ttk.Checkbutton(f, text="ส่งสรุปเข้า Telegram หลังรันรายงาน", variable=self.send_tg_var).grid(row=row, column=1, sticky="w", padx=8, pady=4)
        ttk.Button(f, text="หา Chat ID จากข้อความล่าสุด", command=lambda: self.threaded(self.find_tg_id)).grid(row=row, column=2, padx=8, pady=4)
        ttk.Button(f, text="ทดสอบส่ง Telegram", command=lambda: self.threaded(self.test_tg)).grid(row=row, column=3, padx=8, pady=4)
        row += 1
        ttk.Label(f, text="หมายเหตุ: ถ้าเคยแคป Token หลุด ให้ Regenerate Token ใหม่ทันที", foreground="red").grid(row=row, column=1, columnspan=3, sticky="w", padx=8, pady=8)

    def _listen_tab(self):
        f = self.tab_listen
        f.columnconfigure(0, weight=1)
        f.rowconfigure(3, weight=1)
        f.rowconfigure(5, weight=1)
        guide = add_guide_box(
            f,
            "Social Listening / ดึงโพสต์จริง",
            ["ใช้ค้นโพสต์จาก X ตาม keyword, hashtag, website, หรือคำที่ลูกค้าพูดถึง", "ใช้สร้าง dashboard.html, posts.csv, lead_list.csv, report.xlsx"],
            ["ใส่คำค้นในช่องใหญ่", "ตั้งจำนวนโพสต์ต่อคำค้น เช่น 5, 10, 20", "กด “1 เช็คจำนวนก่อน”", "ถ้าจำนวนโอเค กด “2 ดึงจริง + วิเคราะห์ + รายงาน”", "กด “เปิด Dashboard ล่าสุด”"],
            ["#maha289 -is:retweet", "url:\"maha289.com\" -is:retweet", "(maha289 OR #maha289 OR url:\"maha289.com\") (สนใจ OR สมัคร OR โปร OR ทัก OR ฝาก) -is:retweet"],
            ["จำนวนโพสต์ที่ดึงได้", "โฟลเดอร์ output", "ไฟล์ dashboard.html, posts.csv, lead_list.csv, report.xlsx"],
            ["Cost Guard จะแสดงก่อนดึงจริง", "อย่าเพิ่มจำนวนโพสต์สูงเกินจำเป็นถ้ายังทดสอบ"],
        )
        guide.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        top = ttk.Frame(f); top.grid(row=1, column=0, sticky="ew", padx=10, pady=6); top.columnconfigure(1, weight=1)
        ttk.Label(top, text="สูตรคำค้น").grid(row=0, column=0, sticky="w", padx=4)
        ttk.Combobox(top, textvariable=self.recipe_var, values=recipe_names(), state="readonly", width=42).grid(row=0, column=1, sticky="w", padx=4)
        ttk.Button(top, text="ใช้สูตรตัวอย่าง", command=self.apply_recipe).grid(row=0, column=2, padx=4)
        ttk.Button(top, text="เพิ่มสูตรต่อท้าย", command=lambda: self.apply_recipe(append=True)).grid(row=0, column=3, padx=4)
        ttk.Button(top, text="บันทึกค่าตั้งต้น", command=self.save_settings).grid(row=0, column=4, padx=4)
        ttk.Button(top, text="ล้างคำค้น", command=lambda: self.queries_text.delete("1.0", "end")).grid(row=0, column=5, padx=4)

        opts = ttk.LabelFrame(f, text="คุมต้นทุนและตัวกรอง")
        opts.grid(row=2, column=0, sticky="ew", padx=10, pady=4)
        opts.columnconfigure(5, weight=1)
        ttk.Label(opts, text="ดึงสูงสุด/คำค้น").grid(row=0, column=0, padx=8, pady=6)
        ttk.Entry(opts, textvariable=self.max_posts_var, width=8).grid(row=0, column=1, padx=4, pady=6)
        ttk.Checkbutton(opts, text="ตัดรีโพสต์", variable=self.exclude_rt_var).grid(row=0, column=2, padx=8)
        ttk.Checkbutton(opts, text="บังคับ lang:th", variable=self.lang_th_var).grid(row=0, column=3, padx=8)
        ttk.Checkbutton(opts, text="ตัดโพสต์ที่เจอคำห้าม", variable=self.remove_blocked_var).grid(row=0, column=4, padx=8)
        ttk.Label(opts, text="คำห้าม").grid(row=1, column=0, padx=8, pady=4, sticky="w")
        ttk.Entry(opts, textvariable=self.block_words_var).grid(row=1, column=1, columnspan=4, sticky="ew", padx=4, pady=4)
        ttk.Button(opts, text="ชุดกรองสแปม", command=lambda: self.block_words_var.set(", ".join(SPAM_WORDS_DEFAULT))).grid(row=1, column=5, padx=4)
        ttk.Label(opts, text="คำที่ต้องมี").grid(row=2, column=0, padx=8, pady=4, sticky="w")
        ttk.Entry(opts, textvariable=self.require_words_var).grid(row=2, column=1, columnspan=4, sticky="ew", padx=4, pady=4)
        ttk.Button(opts, text="ชุด Lead", command=lambda: self.require_words_var.set(", ".join(INTENT_WORDS_DEFAULT))).grid(row=2, column=5, padx=4)

        textframe = ttk.LabelFrame(f, text="คำค้น ใส่หลายบรรทัด")
        textframe.grid(row=3, column=0, sticky="nsew", padx=10, pady=6)
        textframe.columnconfigure(0, weight=1); textframe.rowconfigure(0, weight=1)
        self.queries_text = tk.Text(textframe, height=10, wrap="word")
        self.queries_text.grid(row=0, column=0, sticky="nsew")
        self.queries_text.insert("1.0", "\n".join(RECIPES[self.recipe_var.get()]))
        ttk.Scrollbar(textframe, command=self.queries_text.yview).grid(row=0, column=1, sticky="ns")
        examples = ttk.Frame(textframe)
        examples.grid(row=1, column=0, sticky="w", pady=(6, 2))
        add_example_button(examples, "ใส่ตัวอย่าง #maha289 + เว็บ", self.queries_text, "(#maha289 OR url:\"maha289.com\" OR \"www.maha289.com\" OR \"maha289.com\") -is:retweet").grid(row=0, column=0, padx=3, pady=2)
        add_example_button(examples, "ใส่ตัวอย่างเฉพาะ #maha289", self.queries_text, "#maha289 -is:retweet").grid(row=0, column=1, padx=3, pady=2)
        add_example_button(examples, "ใส่ตัวอย่างเฉพาะเว็บ", self.queries_text, "url:\"maha289.com\" -is:retweet").grid(row=0, column=2, padx=3, pady=2)
        add_example_button(examples, "ใส่ตัวอย่าง Lead สนใจสมัคร", self.queries_text, "(maha289 OR #maha289 OR url:\"maha289.com\") (สนใจ OR สมัคร OR โปร OR ทัก OR ฝาก) -is:retweet").grid(row=0, column=3, padx=3, pady=2)
        ttk.Button(examples, text="ล้างคำค้น", command=lambda: self.queries_text.delete("1.0", "end")).grid(row=0, column=4, padx=3, pady=2)
        ttk.Label(
            textframe,
            text='OR = เอาคำใดคำหนึ่งก็ได้ | "..." = ค้นคำตรงตัว | #maha289 = ค้นแฮชแท็ก | url:"maha289.com" = ค้นโพสต์ที่มีลิงก์เว็บ | -is:retweet = ตัดรีโพสต์ออก | lang:th = เฉพาะภาษาไทย แต่อาจไม่เหมาะกับโพสต์ที่มีแต่ลิงก์',
            wraplength=1180,
            foreground="#555",
        ).grid(row=2, column=0, sticky="ew", pady=(2, 6))

        actions = ttk.Frame(f); actions.grid(row=4, column=0, sticky="ew", padx=10, pady=8)
        ttk.Button(actions, text="1 เช็คจำนวนก่อน", command=lambda: self.threaded(self.count_queries)).grid(row=0, column=0, padx=4)
        ttk.Button(actions, text="2 ดึงจริง + วิเคราะห์ + รายงาน", command=self.start_collect_queries).grid(row=0, column=1, padx=4)
        ttk.Button(actions, text="วิเคราะห์ CSV เดิม", command=self.analyze_csv_dialog).grid(row=0, column=2, padx=4)
        ttk.Button(actions, text="ส่งสรุปล่าสุดเข้า Telegram", command=lambda: self.threaded(self.send_latest_summary)).grid(row=0, column=3, padx=4)
        ttk.Button(actions, text="เปิด Dashboard ล่าสุด", command=self.open_last_dashboard).grid(row=0, column=4, padx=4)

        outframe = ttk.LabelFrame(f, text="ผลลัพธ์รอบล่าสุด")
        outframe.grid(row=5, column=0, sticky="nsew", padx=10, pady=(0, 8))
        outframe.columnconfigure(0, weight=1); outframe.rowconfigure(0, weight=1)
        self.listen_box = tk.Text(outframe, height=7, wrap="word")
        self.listen_box.grid(row=0, column=0, sticky="nsew")
        ttk.Scrollbar(outframe, command=self.listen_box.yview).grid(row=0, column=1, sticky="ns")

    def _trend_tab(self):
        f = self.tab_trends
        f.columnconfigure(0, weight=1); f.rowconfigure(2, weight=1)
        guide = add_guide_box(
            f,
            "Trend Radar",
            ["ใช้ดูเทรนด์ตาม WOEID"],
            ["ใส่ WOEID", "ใส่จำนวนเทรนด์", "กดดึงเทรนด์จริง", "ดูผลในช่องขาว", "เปิด outputs/trends_..."],
            ["Thailand WOEID: 23424960", "Worldwide WOEID: 1"],
            ["รายชื่อเทรนด์", "ไฟล์ trends.csv, trends.xlsx, dashboard.html"],
            ["403 = สิทธิ์หรือ plan ของ X ไม่พอ", "429 = rate limit", "ไม่มีข้อมูล = trend location อาจไม่รองรับ"],
        )
        guide.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        frm = ttk.LabelFrame(f, text="Trend Radar")
        frm.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
        ttk.Label(frm, text="WOEID").grid(row=0, column=0, padx=8, pady=8)
        ttk.Entry(frm, textvariable=self.woeid_var, width=15).grid(row=0, column=1, padx=4)
        ttk.Label(frm, text="Worldwide=1, Thailand=23424960").grid(row=0, column=2, padx=8)
        ttk.Label(frm, text="จำนวนเทรนด์").grid(row=0, column=3, padx=8)
        ttk.Entry(frm, textvariable=self.max_trends_var, width=8).grid(row=0, column=4, padx=4)
        ttk.Button(frm, text="ดึงเทรนด์จริง", command=lambda: self.threaded(self.fetch_trends)).grid(row=0, column=5, padx=8)
        ttk.Button(frm, text="ส่งสรุป Telegram", command=lambda: self.threaded(self.send_latest_summary)).grid(row=0, column=6, padx=8)
        add_example_button(frm, "ตัวอย่าง Thailand", self.woeid_var, "23424960").grid(row=1, column=1, padx=4, pady=(0, 8), sticky="w")
        add_example_button(frm, "ตัวอย่าง Worldwide", self.woeid_var, "1").grid(row=1, column=2, padx=4, pady=(0, 8), sticky="w")
        self.trend_box = tk.Text(f, height=22, wrap="word")
        self.trend_box.grid(row=2, column=0, sticky="nsew", padx=10, pady=8)

    def _competitor_tab(self):
        f = self.tab_competitor
        f.columnconfigure(0, weight=1); f.rowconfigure(2, weight=1)
        guide = add_guide_box(
            f,
            "คู่แข่ง / Competitor Watch",
            ["ใช้ตรวจบัญชีคู่แข่งหรือบัญชีตัวอย่าง", "ใส่ username ไม่ต้องใส่ @"],
            ["ใส่ username", "ใส่จำนวนโพสต์ล่าสุด เช่น 10", "กดดึงคู่แข่ง + สรุปรายงาน", "ดูข้อมูลบัญชีและโพสต์ล่าสุด"],
            ["xdevelopers"],
            ["ข้อมูลบัญชี", "โพสต์ล่าสุด", "competitor_profiles.csv, competitor_posts.csv, competitor_report.xlsx"],
            ["ถ้า Excel ฟ้อง Cannot convert dict แปลว่าข้อมูล metrics ยังไม่ถูก flatten ก่อนเขียนไฟล์"],
        )
        guide.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        frm = ttk.LabelFrame(f, text="Competitor Watch")
        frm.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
        frm.columnconfigure(1, weight=1)
        ttk.Label(frm, text="username คู่แข่ง ทีละบรรทัด (ไม่ต้องใส่ @)").grid(row=0, column=0, sticky="nw", padx=8, pady=8)
        self.competitor_text = tk.Text(frm, height=5, wrap="word")
        self.competitor_text.grid(row=0, column=1, sticky="ew", padx=4, pady=8)
        self.competitor_text.insert("1.0", "")
        add_example_button(frm, "ใส่ตัวอย่าง xdevelopers", self.competitor_text, "xdevelopers").grid(row=0, column=2, padx=8, pady=8, sticky="n")
        ttk.Label(frm, text="ดึงโพสต์ล่าสุด/บัญชี").grid(row=1, column=0, padx=8, pady=8)
        self.comp_max_var = tk.StringVar(value="10")
        ttk.Entry(frm, textvariable=self.comp_max_var, width=8).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Button(frm, text="ดึงคู่แข่ง + สรุปรายงาน", command=lambda: self.threaded(self.fetch_competitors)).grid(row=1, column=2, padx=8)
        self.comp_box = tk.Text(f, height=22, wrap="word")
        self.comp_box.grid(row=2, column=0, sticky="nsew", padx=10, pady=8)

    def _creator_tab(self):
        f = self.tab_creator
        f.columnconfigure(0, weight=1); f.rowconfigure(2, weight=1)
        guide = add_guide_box(
            f,
            "Creator Finder",
            ["ใช้หา creator/reviewer จาก keyword", "เหมาะกับการหา account ที่พูดเรื่องสินค้า ร้าน คาเฟ่ พื้นที่ หรือ hashtag"],
            ["ใส่ keyword", "กดค้น Creator จริง", "ดู score, username, followers, posts, sample", "แท็บนี้ไม่มีช่องจำนวนแยก ใช้ limit ตั้งต้นภายในระบบ"],
            ['"ร้านขนมนางรอง" -is:retweet lang:th', '"คาเฟ่นางรอง" -is:retweet lang:th', "#maha289 -is:retweet"],
            ["score", "username", "followers", "posts", "sample"],
            ["ใช้จำนวนโพสต์ตามค่า default/internal limit ไม่ใช่ช่องจำนวนแยกในแท็บนี้"],
        )
        guide.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        frm = ttk.LabelFrame(f, text="Creator Finder")
        frm.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
        frm.columnconfigure(1, weight=1)
        ttk.Label(frm, text="คำค้นหา Creator/Reviewer").grid(row=0, column=0, sticky="nw", padx=8, pady=8)
        self.creator_query_text = tk.Text(frm, height=5, wrap="word")
        self.creator_query_text.grid(row=0, column=1, sticky="ew", padx=4, pady=8)
        self.creator_query_text.insert("1.0", '"รีวิว" "ของกิน" -is:retweet lang:th\n"คาเฟ่" OR "ร้านขนม" -is:retweet lang:th')
        ttk.Button(frm, text="ค้น Creator จริง", command=lambda: self.threaded(self.find_creators)).grid(row=0, column=2, padx=8)
        ex = ttk.Frame(frm); ex.grid(row=1, column=1, sticky="w", padx=4, pady=(0, 8))
        add_example_button(ex, "ร้านขนมนางรอง", self.creator_query_text, '"ร้านขนมนางรอง" -is:retweet lang:th').grid(row=0, column=0, padx=3)
        add_example_button(ex, "คาเฟ่นางรอง", self.creator_query_text, '"คาเฟ่นางรอง" -is:retweet lang:th').grid(row=0, column=1, padx=3)
        add_example_button(ex, "#maha289", self.creator_query_text, "#maha289 -is:retweet").grid(row=0, column=2, padx=3)
        self.creator_box = tk.Text(f, height=22, wrap="word")
        self.creator_box.grid(row=2, column=0, sticky="nsew", padx=10, pady=8)

    def _care_tab(self):
        f = self.tab_care
        f.columnconfigure(0, weight=1); f.rowconfigure(3, weight=1)
        guide = add_guide_box(
            f,
            "Customer Care",
            ["ใช้วิเคราะห์ข้อความลูกค้า", "ใช้ร่างคำตอบ", "ยังไม่ส่งจริง"],
            ["ใส่ข้อความลูกค้า", "กดวิเคราะห์ / ร่างคำตอบ", "อ่าน draft", "ห้ามกดส่งจริง"],
            ["สนใจโปรตอนนี้ต้องทำยังไง"],
            ["draft คำตอบภาษาไทย", "ไฟล์ mentions/care queue เมื่อดึง mentions จริง"],
            ["หน้านี้ควรร่างคำตอบเท่านั้น", "Reply จริงต้องไปผ่าน Action Queue ก่อน"],
        )
        guide.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        frm = ttk.LabelFrame(f, text="Customer Care Queue")
        frm.grid(row=1, column=0, sticky="ew", padx=10, pady=6)
        ttk.Label(frm, text="User ID ของบัญชีเรา").grid(row=0, column=0, padx=8, pady=8)
        ttk.Entry(frm, textvariable=self.self_user_id_var, width=24).grid(row=0, column=1, padx=4)
        ttk.Label(frm, text="หรือ Username").grid(row=0, column=2, padx=8)
        ttk.Entry(frm, textvariable=self.my_username_var, width=24).grid(row=0, column=3, padx=4)
        ttk.Entry(frm, textvariable=self.max_posts_var, width=8).grid(row=0, column=4, padx=4)
        ttk.Button(frm, text="ดึง Mentions จริง + สร้างคิวตอบ", command=lambda: self.threaded(self.fetch_mentions)).grid(row=0, column=5, padx=8)
        draft = ttk.LabelFrame(f, text="วิเคราะห์ข้อความลูกค้า / ร่างคำตอบเท่านั้น")
        draft.grid(row=2, column=0, sticky="ew", padx=10, pady=6)
        draft.columnconfigure(1, weight=1)
        ttk.Label(draft, text="ข้อความลูกค้า").grid(row=0, column=0, sticky="nw", padx=8, pady=8)
        self.customer_msg_text = tk.Text(draft, height=3, wrap="word")
        self.customer_msg_text.grid(row=0, column=1, sticky="ew", padx=4, pady=8)
        self.customer_msg_text.insert("1.0", "สนใจโปรตอนนี้ต้องทำยังไง")
        add_example_button(draft, "ใส่ตัวอย่าง", self.customer_msg_text, "สนใจโปรตอนนี้ต้องทำยังไง").grid(row=0, column=2, padx=8, pady=8)
        ttk.Button(draft, text="วิเคราะห์ / ร่างคำตอบ", command=self.draft_customer_reply).grid(row=1, column=1, sticky="w", padx=4, pady=(0, 8))
        self.care_box = tk.Text(f, height=22, wrap="word")
        self.care_box.grid(row=3, column=0, sticky="nsew", padx=10, pady=8)

    def _actions_tab(self):
        f = self.tab_actions
        f.columnconfigure(0, weight=1)
        guide = add_guide_box(
            f,
            "โหมด Action จริง ระวังมาก",
            ["ใช้โพสต์จริง / reply จริง / DM / follow / like ในบัญชีจริง"],
            ["Preview", "Add to Queue", "ติ๊ก checklist", "พิมพ์ POST", "Execute"],
            ["ทดสอบระบบ BN9 X Social Real V6 Easy Ready ✅"],
            ["Action เข้าคิวก่อนเสมอ", "ระบบแสดง action type, target และคำเตือน USER_ACCESS_TOKEN ก่อนยิงจริง"],
            ["This will use USER_ACCESS_TOKEN", "ห้าม DM / Follow / Like / Reply โดยไม่ preview", "ตรวจ target ทุกครั้งก่อน execute"],
        )
        guide.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))

        post = ttk.LabelFrame(f, text="โพสต์ / Reply จริง")
        post.grid(row=1, column=0, sticky="ew", padx=10, pady=6); post.columnconfigure(1, weight=1)
        ttk.Label(post, text="ข้อความ").grid(row=0, column=0, sticky="nw", padx=8, pady=6)
        self.post_text = tk.Text(post, height=4, wrap="word")
        self.post_text.grid(row=0, column=1, sticky="ew", padx=4, pady=6)
        add_example_button(post, "ใส่ข้อความทดสอบปลอดภัย", self.post_text, "ทดสอบระบบ BN9 X Social Real V6 Easy Ready ✅").grid(row=0, column=3, padx=4, pady=6)
        self.reply_to_var = tk.StringVar(value="")
        self.media_path_var = tk.StringVar(value="")
        ttk.Label(post, text="Reply to Tweet ID").grid(row=1, column=0, padx=8, pady=4, sticky="w")
        ttk.Entry(post, textvariable=self.reply_to_var).grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Label(post, text="รูปภาพ").grid(row=2, column=0, padx=8, pady=4, sticky="w")
        ttk.Entry(post, textvariable=self.media_path_var).grid(row=2, column=1, sticky="ew", padx=4)
        ttk.Button(post, text="เลือกไฟล์รูป", command=self.choose_media).grid(row=2, column=2, padx=4)
        ttk.Button(post, text="โพสต์จริง", command=lambda: self.confirm_and_thread("POST", self.publish_post)).grid(row=0, column=2, padx=8, pady=6)
        ttk.Button(post, text="ลบโพสต์จริง", command=lambda: self.confirm_and_thread("DELETE", self.delete_post)).grid(row=1, column=2, padx=8, pady=6)
        ttk.Label(post, text="ใช้ช่อง Tweet ID ด้านล่างสำหรับลบโพสต์").grid(row=3, column=1, sticky="w", padx=4, pady=(0,6))

        act = ttk.LabelFrame(f, text="Like / Retweet / Follow / DM / List จริง")
        act.grid(row=2, column=0, sticky="ew", padx=10, pady=6); act.columnconfigure(1, weight=1); act.columnconfigure(3, weight=1)
        self.action_tweet_id_var = tk.StringVar(value="")
        self.target_user_var = tk.StringVar(value="")
        self.dm_text_var = tk.StringVar(value="")
        self.list_name_var = tk.StringVar(value="")
        self.list_id_var = tk.StringVar(value="")
        ttk.Label(act, text="Tweet ID").grid(row=0, column=0, padx=8, pady=4)
        ttk.Entry(act, textvariable=self.action_tweet_id_var).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(act, text="Like จริง", command=lambda: self.confirm_and_thread("LIKE", self.like_post)).grid(row=0, column=2, padx=4)
        ttk.Button(act, text="Unlike จริง", command=lambda: self.confirm_and_thread("UNLIKE", self.unlike_post)).grid(row=0, column=3, sticky="w", padx=4)
        ttk.Button(act, text="Retweet จริง", command=lambda: self.confirm_and_thread("RETWEET", self.retweet_post)).grid(row=0, column=4, padx=4)
        ttk.Button(act, text="Unretweet จริง", command=lambda: self.confirm_and_thread("UNRETWEET", self.unretweet_post)).grid(row=0, column=5, padx=4)
        ttk.Label(act, text="Target User ID หรือ @username").grid(row=1, column=0, padx=8, pady=4)
        ttk.Entry(act, textvariable=self.target_user_var).grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Button(act, text="Follow จริง", command=lambda: self.confirm_and_thread("FOLLOW", self.follow_user)).grid(row=1, column=2, padx=4)
        ttk.Button(act, text="Unfollow จริง", command=lambda: self.confirm_and_thread("UNFOLLOW", self.unfollow_user)).grid(row=1, column=3, sticky="w", padx=4)
        ttk.Label(act, text="DM Text").grid(row=2, column=0, padx=8, pady=4)
        ttk.Entry(act, textvariable=self.dm_text_var).grid(row=2, column=1, sticky="ew", padx=4)
        ttk.Button(act, text="ส่ง DM จริง", command=lambda: self.confirm_and_thread("DM", self.send_dm)).grid(row=2, column=2, padx=4)
        ttk.Label(act, text="List Name").grid(row=3, column=0, padx=8, pady=4)
        ttk.Entry(act, textvariable=self.list_name_var).grid(row=3, column=1, sticky="ew", padx=4)
        ttk.Button(act, text="สร้าง List จริง", command=lambda: self.confirm_and_thread("LIST", self.create_list)).grid(row=3, column=2, padx=4)
        ttk.Label(act, text="List ID").grid(row=4, column=0, padx=8, pady=4)
        ttk.Entry(act, textvariable=self.list_id_var).grid(row=4, column=1, sticky="ew", padx=4)
        ttk.Button(act, text="เพิ่มสมาชิกเข้า List", command=lambda: self.confirm_and_thread("ADD_MEMBER", self.add_list_member)).grid(row=4, column=2, padx=4)
        ttk.Button(act, text="ลบสมาชิกออก List", command=lambda: self.confirm_and_thread("REMOVE_MEMBER", self.remove_list_member)).grid(row=4, column=3, sticky="w", padx=4)

    def _ads_tab(self):
        f = self.tab_ads
        f.columnconfigure(1, weight=1)
        guide = add_guide_box(
            f,
            "Ads Report",
            ["ใช้ดูหน้า Ads Report", "ยังไม่ควรรันจริงถ้ายังไม่มี Ads API access"],
            ["ตั้งค่า Ads API ให้ครบ", "ตรวจ Advertiser Account", "กดดึง Ads Analytics จริงเมื่อพร้อมเท่านั้น"],
            ["Ads API แยกจาก X API ปกติ", "ต้องใช้ OAuth 1.0a", "ต้องมี Advertiser Account", "ต้องขอ Ads API Access แยก"],
            ["ads_analytics.json เมื่อ config ครบและ API ตอบกลับ"],
            ["ถ้ายังไม่มี config ระบบจะไม่รันจริงและจะแสดงข้อความว่ายังไม่พร้อม"],
        )
        guide.grid(row=0, column=0, columnspan=4, sticky="ew", padx=12, pady=(10, 4))
        row = 1
        self._entry(f, row, "Ads Consumer Key", self.ads_ck_var, secret=True); row += 1
        self._entry(f, row, "Ads Consumer Secret", self.ads_cs_var, secret=True); row += 1
        self._entry(f, row, "Ads Access Token", self.ads_at_var, secret=True); row += 1
        self._entry(f, row, "Ads Access Token Secret", self.ads_as_var, secret=True); row += 1
        self._entry(f, row, "Ads Account ID", self.ads_account_var); row += 1
        self._entry(f, row, "Ads API Base URL", self.ads_base_var); row += 1
        self.ads_params_text = tk.Text(f, height=8, wrap="word")
        self.ads_params_text.grid(row=row, column=1, columnspan=3, sticky="ew", padx=8, pady=8)
        self.ads_params_text.insert("1.0", "entity=CAMPAIGN\nmetric_groups=ENGAGEMENT,BILLING\ngranularity=DAY\nstart_time=2026-05-01T00:00:00Z\nend_time=2026-05-08T00:00:00Z")
        ttk.Label(f, text="Params").grid(row=row, column=0, sticky="nw", padx=12, pady=8); row += 1
        ttk.Button(f, text="บันทึก Ads ค่า", command=self.save_settings).grid(row=row, column=1, sticky="w", padx=8, pady=6)
        ttk.Button(f, text="ดึง Ads Analytics จริงเมื่อ config ครบ", command=lambda: self.threaded(self.fetch_ads)).grid(row=row, column=2, sticky="w", padx=8, pady=6)

    def _logs_tab(self):
        f = self.tab_logs
        f.columnconfigure(0, weight=1); f.rowconfigure(1, weight=1)
        guide = add_guide_box(
            f,
            "Log/ผลลัพธ์",
            ["ใช้เปิด output ล่าสุด", "ใช้ดู dashboard.html, posts.csv, lead_list.csv, report.xlsx"],
            ["ดู log ล่าสุด", "กดเปิด outputs หรือ dashboard", "เปิด CSV ล่าสุดเมื่อต้องการดูข้อมูลดิบ"],
            ["dashboard.html = หน้าอ่านผล", "posts.csv = โพสต์ที่ดึงได้", "lead_list.csv = โพสต์ที่ควรดู", "report.xlsx = รายงาน Excel"],
            ["เปิดไฟล์/โฟลเดอร์ล่าสุดได้จากปุ่มด้านล่าง"],
            ["ถ้าไม่มีไฟล์ ระบบจะแจ้งว่ายังไม่มีผลลัพธ์"],
        )
        guide.grid(row=0, column=0, sticky="ew", padx=8, pady=(10, 4))
        self.log_text = tk.Text(f, wrap="word", height=25)
        self.log_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        ttk.Scrollbar(f, command=self.log_text.yview).grid(row=1, column=1, sticky="ns", pady=8)
        btn = ttk.Frame(f); btn.grid(row=2, column=0, sticky="ew", padx=8, pady=6)
        ttk.Button(btn, text="ล้าง Log", command=lambda: self.log_text.delete("1.0", "end")).grid(row=0, column=0, padx=4)
        ttk.Button(btn, text="เปิด outputs", command=lambda: open_path(OUTPUT_DIR)).grid(row=0, column=1, padx=4)
        ttk.Button(btn, text="เปิด Dashboard ล่าสุด", command=self.open_last_dashboard).grid(row=0, column=2, padx=4)
        ttk.Button(btn, text="เปิด CSV ล่าสุด", command=self.open_latest_csv).grid(row=0, column=3, padx=4)
        ttk.Button(btn, text="เปิดโฟลเดอร์รอบล่าสุด", command=self.open_latest_run_dir).grid(row=0, column=4, padx=4)

    def _entry(self, parent, row, label, var, secret=False):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=5)
        ent = ttk.Entry(parent, textvariable=var, show="*" if secret else "")
        ent.grid(row=row, column=1, columnspan=2 if secret else 3, sticky="ew", padx=8, pady=5)
        if secret:
            if not hasattr(self, "secret_entries"):
                self.secret_entries = []
            self.secret_entries.append(ent)
            preview = ttk.Label(parent, text=mask_secret(var.get()), foreground="#555")
            preview.grid(row=row, column=3, sticky="w", padx=8, pady=5)
            var.trace_add("write", lambda *_args, v=var, p=preview: p.configure(text=mask_secret(v.get())))
        return ent

    def _apply_secret_visibility(self):
        for ent in getattr(self, "secret_entries", []):
            ent.configure(show="*")

    def client(self) -> XClient:
        return XClient(self.bearer_var.get(), self.user_token_var.get(), self.api_base_var.get())

    def save_settings(self):
        bearer = self.bearer_var.get().strip()
        write_env({
            "APP_BEARER_TOKEN": bearer,
            "BEARER_TOKEN": bearer,
            "USER_ACCESS_TOKEN": self.user_token_var.get().strip(),
            "X_REFRESH_TOKEN": self.refresh_token_var.get().strip(),
            "SELF_USER_ID": self.self_user_id_var.get().strip(),
            "MY_USERNAME": self.my_username_var.get().strip(),
            "BRAND_NAME": self.brand_name_var.get().strip(),
            "BRAND_WORDS": self.brand_words_var.get().strip(),
            "X_API_BASE_URL": self.api_base_var.get().strip(),
            "TELEGRAM_BOT_TOKEN": self.tg_token_var.get().strip(),
            "TELEGRAM_CHAT_ID": self.tg_chat_var.get().strip(),
            "SEND_TELEGRAM": "1" if self.send_tg_var.get() else "0",
            "WOEID": self.woeid_var.get().strip(),
            "MAX_POSTS": self.max_posts_var.get().strip(),
            "BLOCK_WORDS": self.block_words_var.get().strip(),
            "REQUIRE_WORDS": self.require_words_var.get().strip(),
            "REMOVE_BLOCKED": "1" if self.remove_blocked_var.get() else "0",
            "ADS_CONSUMER_KEY": self.ads_ck_var.get().strip(),
            "ADS_CONSUMER_SECRET": self.ads_cs_var.get().strip(),
            "ADS_ACCESS_TOKEN": self.ads_at_var.get().strip(),
            "ADS_ACCESS_TOKEN_SECRET": self.ads_as_var.get().strip(),
            "ADS_ACCOUNT_ID": self.ads_account_var.get().strip(),
            "ADS_API_BASE_URL": self.ads_base_var.get().strip(),
        })
        self.env = read_env()
        self.refresh_start_status()
        self.log("บันทึกค่าแล้ว")
        messagebox.showinfo("บันทึกแล้ว", "บันทึกค่าใน .env แล้ว")

    def open_env(self):
        if not ENV_PATH.exists():
            self.save_settings()
        open_path(ENV_PATH)

    def show_masked_env(self):
        env = read_env()
        secret_words = ("TOKEN", "SECRET", "KEY")
        lines = []
        for key in sorted(env):
            value = env.get(key, "")
            if any(word in key.upper() for word in secret_words):
                value = mask_secret(value)
            lines.append(f"{key}={value}")
        top = tk.Toplevel(self.root)
        top.title(".env แบบซ่อน Token")
        top.geometry("760x520")
        txt = tk.Text(top, wrap="word")
        txt.pack(fill="both", expand=True, padx=12, pady=12)
        txt.insert("1.0", "\n".join(lines) or "ยังไม่มีค่าใน .env")
        txt.configure(state="disabled")

    def log(self, msg: str):
        msg = str(msg)
        try:
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
        except Exception:
            print(msg)
        set_status(msg)

    def refresh_start_status(self):
        env = read_env()
        bearer = self.bearer_var.get().strip() or env.get("APP_BEARER_TOKEN", "").strip() or env.get("BEARER_TOKEN", "").strip()
        user_token = self.user_token_var.get().strip() or env.get("USER_ACCESS_TOKEN", "").strip()
        refresh_token = self.refresh_token_var.get().strip() or env.get("X_REFRESH_TOKEN", "").strip()
        tg_ready = bool((self.tg_token_var.get().strip() or env.get("TELEGRAM_BOT_TOKEN", "").strip()) and (self.tg_chat_var.get().strip() or env.get("TELEGRAM_CHAT_ID", "").strip()))
        lines = [
            "[ผ่าน] โปรแกรม V6 Easy Ready เปิดได้",
            "[ผ่าน] APP_BEARER_TOKEN พร้อมอ่านข้อมูลสาธารณะ" if bearer else "[ต้องแก้] ยังไม่มี APP_BEARER_TOKEN: อ่านข้อมูล X ไม่ได้",
            "[ผ่าน] USER_ACCESS_TOKEN พร้อมใช้ Action จริง" if user_token else "[เตือน] ยังไม่มี USER_ACCESS_TOKEN: ปุ่ม Post/Like/DM จะยังใช้ไม่ได้",
            "[ผ่าน] X_REFRESH_TOKEN มีแล้ว" if refresh_token else "[เตือน] ยังไม่มี X_REFRESH_TOKEN: ถ้า token หมดอายุอาจต้องขอใหม่",
            "[ผ่าน] Telegram พร้อมส่งแจ้งเตือน" if tg_ready else "[เตือน] Telegram ยังไม่ครบ: ไม่กระทบการอ่าน X",
            f"outputs: {OUTPUT_DIR.resolve()}",
        ]
        self.start_status_var.set("\n".join(lines))

    def run_health_check(self):
        cmd = [sys.executable, "health_check.py", "--offline"]
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=120)
        output = (proc.stdout or "").strip()
        if proc.stderr:
            output = (output + "\n" + proc.stderr.strip()).strip()
        self.log("ผล Health Check:")
        self.log(output or "ไม่มี output")
        self.refresh_start_status()
        if proc.returncode == 0:
            messagebox.showinfo("Health Check", output or "ผ่าน")
        else:
            messagebox.showwarning("Health Check พบจุดต้องแก้", output or "ตรวจไม่ผ่าน")

    def threaded(self, func):
        if self.running:
            messagebox.showwarning("กำลังทำงาน", "รอรอบก่อนจบก่อนครับ")
            return
        def runner():
            self.running = True
            try:
                func()
            except (XAPIError, XConnectionError, TelegramError) as exc:
                detail = f"{exc}\n{explain_error(exc)}"
                self.log(detail)
                messagebox.showerror("ข้อผิดพลาด", detail)
            except Exception as exc:
                detail = f"ข้อผิดพลาด: {exc}\n{explain_error(exc)}"
                self.log(detail)
                messagebox.showerror("ข้อผิดพลาด", detail)
            finally:
                self.running = False
        threading.Thread(target=runner, daemon=True).start()

    def confirm_and_thread(self, word: str, func):
        action_payload = self._build_action_payload(word)
        action_name = self._scope_action_name(word, action_payload)
        scope_msg = format_scope_warning(action_name, read_env().get("OAUTH_SCOPES", ""))
        policy_warnings = check_action_policy(word.lower(), action_payload, load_actions(200))
        policy_msg = format_policy_warnings(policy_warnings)
        top = tk.Toplevel(self.root)
        top.title("Preview → Queue → Confirm → Execute")
        top.geometry("620x520")
        preview = [
            "Preview ก่อนยิง Action จริง",
            f"Action: {word}",
            f"Target: {action_payload.get('target_id') or action_payload.get('tweet_id') or action_payload.get('reply_to_tweet_id') or action_payload.get('target') or '-'}",
            f"ข้อความ: {action_payload.get('text') or action_payload.get('dm_text') or '-'}",
            "คำเตือน: This will use USER_ACCESS_TOKEN",
            "",
            scope_msg,
            policy_msg,
            "",
            "Required flow: Preview → Add to Queue → Type POST → Execute",
        ]
        ttk.Label(top, text="\n".join(preview), justify="left", foreground="red").pack(fill="x", padx=16, pady=12)
        queued_var = tk.StringVar(value="ยังไม่เข้าคิว")
        ttk.Label(top, textvariable=queued_var).pack(fill="x", padx=16, pady=4)
        checks = {
            "read": tk.BooleanVar(value=False),
            "target": tk.BooleanVar(value=False),
            "safe": tk.BooleanVar(value=False),
            "post": tk.BooleanVar(value=False),
        }
        checklist = ttk.LabelFrame(top, text="Checklist ก่อน Execute")
        checklist.pack(fill="x", padx=16, pady=6)
        ttk.Checkbutton(checklist, text="อ่านข้อความแล้ว", variable=checks["read"]).grid(row=0, column=0, sticky="w", padx=8, pady=2)
        ttk.Checkbutton(checklist, text="target ถูกต้อง", variable=checks["target"]).grid(row=1, column=0, sticky="w", padx=8, pady=2)
        ttk.Checkbutton(checklist, text="ไม่ใช่ DM/Follow/Like มั่ว", variable=checks["safe"]).grid(row=2, column=0, sticky="w", padx=8, pady=2)
        ttk.Checkbutton(checklist, text="พิมพ์ POST เพื่อยืนยัน", variable=checks["post"]).grid(row=3, column=0, sticky="w", padx=8, pady=2)
        var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=var, state="disabled")
        entry.pack(fill="x", padx=16, pady=6)
        state = {"record": None}

        def queue_only():
            if state["record"]:
                return
            required_target = action_payload.get("target_id") or action_payload.get("tweet_id") or action_payload.get("reply_to_tweet_id")
            if word.upper() in {"DELETE", "LIKE", "UNLIKE", "RETWEET", "UNRETWEET", "FOLLOW", "UNFOLLOW", "DM", "ADD_MEMBER", "REMOVE_MEMBER"} and not required_target:
                messagebox.showerror("ยังไม่มี target", "กรุณาใส่ Tweet ID หรือ Target User ให้ชัดเจนก่อนเข้าคิว")
                return
            record = queue_action(word.lower(), action_payload)
            state["record"] = record
            queued_var.set(f"เข้าคิวแล้ว: {record['action_id']} | พิมพ์ POST เพื่อยิงจริง")
            entry.configure(state="normal")
            entry.focus_set()

        def ok():
            if not state["record"]:
                messagebox.showerror("ยังไม่เข้าคิว", "ต้องกดเข้าคิวก่อนยิงจริง")
                return
            if not all(v.get() for v in checks.values()):
                messagebox.showerror("Checklist ยังไม่ครบ", "ต้องติ๊ก checklist ให้ครบก่อน Execute")
                return
            if var.get().strip() != "POST":
                messagebox.showerror("ไม่ตรง", "ต้องพิมพ์ POST")
                return
            top.destroy()
            action_id = state["record"]["action_id"]
            def wrapped():
                mark_action_status(action_id, "executing")
                try:
                    result = func()
                    mark_action_status(action_id, "done", {"message": "สำเร็จ"})
                    return result
                except Exception as exc:
                    mark_action_status(action_id, "failed", {"error": str(exc)})
                    raise
            self.threaded(wrapped)

        buttons = ttk.Frame(top)
        buttons.pack(fill="x", padx=16, pady=10)
        ttk.Button(buttons, text="1 เข้าคิว Action", command=queue_only).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text="2 ยืนยันยิงจริง", command=ok).grid(row=0, column=1, padx=4)
        ttk.Button(buttons, text="ยกเลิก", command=top.destroy).grid(row=0, column=2, padx=4)

    def _build_action_payload(self, word: str) -> dict:
        text = self.post_text.get("1.0", "end").strip() if hasattr(self, "post_text") else ""
        return {
            "action_type": word.lower(),
            "text": text,
            "dm_text": self.dm_text_var.get().strip() if hasattr(self, "dm_text_var") else "",
            "tweet_id": self.action_tweet_id_var.get().strip() if hasattr(self, "action_tweet_id_var") else "",
            "reply_to_tweet_id": self.reply_to_var.get().strip() if hasattr(self, "reply_to_var") else "",
            "target": self.target_user_var.get().strip() if hasattr(self, "target_user_var") else "",
            "target_id": self.target_user_var.get().strip() if hasattr(self, "target_user_var") else "",
            "media_path_set": bool(self.media_path_var.get().strip()) if hasattr(self, "media_path_var") else False,
            "list_name": self.list_name_var.get().strip() if hasattr(self, "list_name_var") else "",
            "list_id": self.list_id_var.get().strip() if hasattr(self, "list_id_var") else "",
        }

    def _scope_action_name(self, word: str, payload: dict) -> str:
        action = word.lower()
        if action == "post":
            return "reply" if payload.get("reply_to_tweet_id") else "create_post"
        if action in ("like", "unlike"):
            return "like"
        if action in ("follow", "unfollow"):
            return "follow"
        if action == "dm":
            return "dm"
        if payload.get("media_path_set"):
            return "media_upload"
        return action

    def get_queries(self) -> list[str]:
        raw = self.queries_text.get("1.0", "end").strip().splitlines()
        out = []
        for q in raw:
            q = q.strip()
            if not q or q.startswith("# "):
                continue
            if self.exclude_rt_var.get() and "-is:retweet" not in q:
                q += " -is:retweet"
            if self.lang_th_var.get() and "lang:" not in q:
                q += " lang:th"
            out.append(q)
        return out

    def apply_recipe(self, append=False):
        qs = RECIPES.get(self.recipe_var.get(), [])
        if append:
            old = self.queries_text.get("1.0", "end").strip()
            text = (old + "\n" + "\n".join(qs)).strip()
        else:
            text = "\n".join(qs)
        self.queries_text.delete("1.0", "end")
        self.queries_text.insert("1.0", text)

    def test_bearer(self):
        payload = self.client().usage_tweets()
        self.log("Bearer ใช้ได้ / Usage API ตอบกลับ")
        self.log(json.dumps(payload, ensure_ascii=False)[:1000])

    def test_user_token(self):
        payload = self.client().me()
        data = payload.get("data", {})
        if data.get("id"):
            self.self_user_id_var.set(data.get("id"))
        if data.get("username"):
            self.my_username_var.set(data.get("username"))
        self.save_settings()
        self.log(f"User Token ใช้ได้: @{data.get('username')} id={data.get('id')}")

    def find_tg_id(self):
        chat = latest_chat_id(self.tg_token_var.get())
        self.tg_chat_var.set(chat)
        self.save_settings()
        self.log(f"เจอ Telegram Chat ID: {chat}")

    def test_tg(self):
        send_message(self.tg_token_var.get(), self.tg_chat_var.get(), "ทดสอบ BN9 X Social Real V6 สำเร็จ")
        self.log("ส่ง Telegram สำเร็จ")

    def count_queries(self):
        qs = self.get_queries()
        if not qs:
            raise XAPIError(0, "ยังไม่มีคำค้น")
        set_status("Started: เช็คจำนวนก่อนดึง")
        self.log("Started: เช็คจำนวนก่อนดึง")
        self.log("Cost Guard result: เช็คจำนวนอย่างเดียว ยังไม่ดึงรายงานเต็ม")
        append_output(getattr(self, "listen_box", None), "Started: เช็คจำนวนก่อนดึง")
        rows = []
        client = self.client()
        for q in qs:
            self.log(f"เช็คจำนวน: {q}")
            if hasattr(client, "count_recent_posts"):
                payload = client.count_recent_posts(q, granularity="day")
                total = payload.get("meta", {}).get("total_tweet_count", 0)
                rows.append({"query": q, "total_7_days": total, "raw": json.dumps(payload, ensure_ascii=False)})
                msg = f"API result count: พบประมาณ {total} โพสต์ใน 7 วัน"
                self.log(msg)
                append_output(getattr(self, "listen_box", None), f"{q}\n{msg}")
            else:
                msg = "ระบบยังไม่มี count endpoint แยก กำลังใช้ preview แบบปลอดภัยแทน"
                self.log(msg)
                append_output(getattr(self, "listen_box", None), msg)
                preview = client.recent_search(q, max_posts=1)
                rows.append({"query": q, "total_7_days": "preview_only", "preview_count": len(preview)})
        run_dir = now_run_dir("counts")
        save_csv(run_dir / "counts.csv", rows)
        save_excel(run_dir / "counts.xlsx", {"counts": rows}, {"type": "recent_counts", "queries": len(qs)})
        self.last_run_dir = run_dir
        self.log(f"Output folder: {run_dir}")
        self.log("Done: เช็คจำนวนเสร็จ")
        append_output(getattr(self, "listen_box", None), f"Output folder: {run_dir}\nไฟล์ที่สร้าง: counts.csv, counts.xlsx\nDone")

    def start_collect_queries(self):
        try:
            max_posts = max(1, int(self.max_posts_var.get() or 10))
        except ValueError:
            messagebox.showerror("ข้อผิดพลาด", "ดึงสูงสุด/คำค้น ต้องเป็นตัวเลข")
            return
        qs = self.get_queries()
        if not qs:
            messagebox.showerror("ข้อผิดพลาด", "ยังไม่มีคำค้น")
            return
        estimate = estimate_recent_search_cost(len(qs), max_posts)
        self.log("Cost Guard result:")
        self.log(format_cost_warning(estimate))
        if messagebox.askyesno("Cost Guard", format_cost_warning(estimate)):
            self.threaded(self.collect_queries)
        else:
            self.log("ยกเลิกการดึงข้อมูลตาม Cost Guard")

    def collect_queries(self):
        set_status("Started: ดึง Social Listening จริง")
        self.log("Started: ดึง Social Listening จริง")
        append_output(getattr(self, "listen_box", None), "Started: ดึงจริง + วิเคราะห์ + รายงาน")
        max_posts = max(1, int(self.max_posts_var.get() or 10))
        qs = self.get_queries()
        if not qs:
            raise XAPIError(0, "ยังไม่มีคำค้น")
        client = self.client()
        raw = []
        for q in qs:
            self.log(f"ดึงจริง: {q} | max={max_posts}")
            part = client.recent_search(q, max_posts=max_posts)
            raw.extend(part)
            self.log(f"API result count: ได้ {len(part)} โพสต์ | {client.rate_limit_text()}")
            append_output(getattr(self, "listen_box", None), f"{q}\nAPI result count: ได้ {len(part)} โพสต์")
        kept, removed = filter_rows(raw, self.block_words_var.get(), self.require_words_var.get(), self.remove_blocked_var.get())
        rows = analyze_rows(kept, self.brand_name_var.get() or "ร้านเรา", self.brand_words_var.get())
        creators = creator_scores(rows)
        summary = summarize(rows)
        run_dir = now_run_dir("listen")
        save_csv(run_dir / "raw_posts_before_filter.csv", raw)
        save_csv(run_dir / "filtered_out.csv", removed)
        save_csv(run_dir / "posts.csv", rows)
        lead_rows = [r for r in rows if should_include_review_queue(r)]
        save_csv(run_dir / "lead_list.csv", lead_rows)
        save_csv(run_dir / "creators.csv", creators)
        save_json(run_dir / "summary.json", summary)
        save_excel(run_dir / "report.xlsx", {"posts": rows, "lead_list": lead_rows, "creators": creators, "filtered_out": removed}, summary)
        save_dashboard(run_dir / "dashboard.html", "BN9 Social Listening Report", summary, rows, creators=creators)
        self.last_run_dir, self.last_rows, self.last_creators = run_dir, rows, creators
        files = "raw_posts_before_filter.csv, filtered_out.csv, posts.csv, lead_list.csv, creators.csv, summary.json, report.xlsx, dashboard.html"
        summary_msg = f"จำนวนโพสต์ที่ดึงได้: {len(raw)}\nจำนวนหลังกรอง: {len(rows)}\nโฟลเดอร์ output: {run_dir}\nไฟล์ที่สร้าง: {files}\nปุ่มเปิด dashboard: ใช้ปุ่ม เปิด Dashboard ล่าสุด"
        self.log(f"Output folder: {run_dir}")
        self.log("Done: Social Listening เสร็จ")
        append_output(getattr(self, "listen_box", None), summary_msg)
        if self.send_tg_var.get():
            self._send_summary(summary, run_dir)

    def analyze_csv_dialog(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        self.threaded(lambda: self.analyze_csv(path))

    def analyze_csv(self, path: str):
        import csv
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        rows = analyze_rows(rows, self.brand_name_var.get() or "ร้านเรา", self.brand_words_var.get())
        creators = creator_scores(rows)
        summary = summarize(rows)
        run_dir = now_run_dir("csv_analysis")
        save_csv(run_dir / "posts.csv", rows)
        lead_rows = [r for r in rows if should_include_review_queue(r)]
        save_csv(run_dir / "lead_list.csv", lead_rows)
        save_csv(run_dir / "creators.csv", creators)
        save_json(run_dir / "summary.json", summary)
        save_excel(run_dir / "report.xlsx", {"posts": rows, "lead_list": lead_rows, "creators": creators}, summary)
        save_dashboard(run_dir / "dashboard.html", "BN9 CSV Analysis Report", summary, rows, creators=creators)
        self.last_run_dir, self.last_rows, self.last_creators = run_dir, rows, creators
        self.log(f"วิเคราะห์ CSV เสร็จ: {run_dir}")

    def fetch_trends(self):
        set_status("Started: ดึง Trend Radar")
        self.log("Started: ดึง Trend Radar")
        self.log("Cost Guard result: Trend Radar ดึงเฉพาะจำนวนเทรนด์ที่ตั้งไว้")
        payload = self.client().trends_by_woeid(int(self.woeid_var.get()), int(self.max_trends_var.get()))
        trends = payload.get("data", []) or []
        self.last_trends = trends
        run_dir = now_run_dir("trends")
        summary = {"total_posts": 0, "high_interest": 0, "medium_interest": 0, "categories": {}, "content_ideas": [
            "วิธีตรวจสอบช่องทางหลักก่อนใช้โค้ด",
            "FAQ วิธีใช้โค้ดกิจกรรม",
            "อ่านเงื่อนไขกิจกรรมก่อนรับสิทธิ์",
            "ระวังเว็บปลอม / ลิงก์ปลอม",
            "Checklist ความปลอดภัยก่อนกรอกข้อมูล",
            "เล่นอย่างรับผิดชอบ",
        ]}
        save_csv(run_dir / "trends.csv", trends)
        save_excel(run_dir / "trends.xlsx", {"trends": trends}, {"woeid": self.woeid_var.get(), "count": len(trends)})
        save_dashboard(run_dir / "dashboard.html", "BN9 Trend Radar", summary, [], trends=trends)
        self.last_run_dir = run_dir
        self.trend_box.delete("1.0", "end")
        for t in trends:
            self.trend_box.insert("end", f"{t.get('trend_name')} | {t.get('tweet_count','')}\n")
        self.log(f"API result count: ได้ {len(trends)} เทรนด์")
        self.log(f"Output folder: {run_dir}")
        self.log("Done: Trend Radar เสร็จ")

    def fetch_competitors(self):
        set_status("Started: ดึง Competitor Watch")
        self.log("Started: ดึง Competitor Watch")
        self.log(f"Cost Guard result: จะดึงไม่เกิน {self.comp_max_var.get() or 10} โพสต์ต่อบัญชี")
        users = [x.strip() for x in self.competitor_text.get("1.0", "end").splitlines() if x.strip()]
        if not users:
            raise XAPIError(0, "ยังไม่ได้ใส่ @คู่แข่ง")
        max_posts = max(5, int(self.comp_max_var.get() or 10))
        client = self.client()
        profiles = [flatten_public_metrics(p) for p in client.lookup_usernames(users)]
        posts = []
        for p in profiles:
            uid = p.get("id")
            username = p.get("username")
            self.log(f"ดึงโพสต์คู่แข่ง @{username}")
            for tw in client.get_user_tweets(uid, max_posts=max_posts):
                row = {
                    **tw,
                    "query": f"from:{username}",
                    "username": username,
                    "name": p.get("name", ""),
                    "followers_count": p.get("followers_count", 0),
                    "url": f"https://x.com/{username}/status/{tw.get('id','')}",
                }
                posts.append(row)
        rows = analyze_rows(posts, self.brand_name_var.get(), self.brand_words_var.get())
        summary = summarize(rows)
        run_dir = now_run_dir("competitor")
        save_csv(run_dir / "competitor_profiles.csv", profiles)
        save_csv(run_dir / "competitor_posts.csv", rows)
        save_json(run_dir / "summary.json", summary)
        save_excel(run_dir / "competitor_report.xlsx", {"profiles": profiles, "posts": rows}, summary)
        save_dashboard(run_dir / "dashboard.html", "BN9 Competitor Watch", summary, rows)
        self.last_run_dir, self.last_rows = run_dir, rows
        self.comp_box.delete("1.0", "end")
        self.comp_box.insert("end", f"API result count: ดึงคู่แข่ง {len(profiles)} บัญชี / {len(rows)} โพสต์\nOutput folder: {run_dir}\nไฟล์ที่สร้าง: competitor_profiles.csv, competitor_posts.csv, competitor_report.xlsx, dashboard.html\nDone\n")
        self.log(f"API result count: ดึงคู่แข่ง {len(profiles)} บัญชี / {len(rows)} โพสต์")
        self.log(f"Output folder: {run_dir}")
        self.log("Done: Competitor Watch เสร็จ")

    def find_creators(self):
        set_status("Started: ค้น Creator Finder")
        self.log("Started: ค้น Creator Finder")
        self.log("Cost Guard result: ใช้ limit ตั้งต้นภายในระบบสำหรับ Creator Finder")
        old_text = self.queries_text.get("1.0", "end")
        self.queries_text.delete("1.0", "end")
        self.queries_text.insert("1.0", self.creator_query_text.get("1.0", "end"))
        try:
            self.collect_queries()
            self.creator_box.delete("1.0", "end")
            self.creator_box.insert("end", "score | username | followers | posts | sample\n")
            for c in self.last_creators[:30]:
                self.creator_box.insert("end", f"{c.get('creator_score')} | @{c.get('username')} | followers={c.get('followers_count')} | posts={c.get('post_count')} | {c.get('sample_text','')[:120]}\n")
            self.log(f"API result count: พบ creator candidates {len(self.last_creators)} ราย")
            self.log("Done: Creator Finder เสร็จ")
        finally:
            self.queries_text.delete("1.0", "end")
            self.queries_text.insert("1.0", old_text)

    def fetch_mentions(self):
        set_status("Started: ดึง Customer Care Mentions")
        self.log("Started: ดึง Customer Care Mentions")
        self.log(f"Cost Guard result: จะดึงไม่เกิน {self.max_posts_var.get() or 10} mentions")
        uid = self.self_user_id_var.get().strip()
        if not uid and self.my_username_var.get().strip():
            prof = self.client().lookup_usernames([self.my_username_var.get().strip()])
            if prof:
                uid = prof[0].get("id", "")
                self.self_user_id_var.set(uid)
        if not uid:
            raise XAPIError(0, "ยังไม่มี User ID หรือ Username")
        rows = self.client().get_mentions(uid, max_posts=int(self.max_posts_var.get() or 10))
        rows = analyze_rows(rows, self.brand_name_var.get(), self.brand_words_var.get())
        summary = summarize(rows)
        run_dir = now_run_dir("mentions")
        save_csv(run_dir / "mentions.csv", rows)
        care_rows = [r for r in rows if should_include_review_queue(r)]
        save_csv(run_dir / "care_queue.csv", care_rows)
        save_excel(run_dir / "care_report.xlsx", {"mentions": rows, "care_queue": care_rows}, summary)
        save_dashboard(run_dir / "dashboard.html", "BN9 Customer Care Queue", summary, rows)
        self.last_run_dir, self.last_rows = run_dir, rows
        self.care_box.delete("1.0", "end")
        for r in rows[:30]:
            self.care_box.insert("end", f"{r.get('lead_score')} | @{r.get('username')} | {r.get('category')} | {r.get('text')}\n")
        self.log(f"API result count: ได้ {len(rows)} mentions")
        self.log(f"Output folder: {run_dir}")
        self.log("Done: Customer Care เสร็จ")

    def draft_customer_reply(self):
        text = self.customer_msg_text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("ยังไม่มีข้อความ", "กรุณาใส่ข้อความลูกค้าก่อน")
            return
        lowered = text.lower()
        intent = "สอบถามทั่วไป"
        if any(word in lowered for word in ["สนใจ", "สมัคร", "โปร", "ราคา"]):
            intent = "ลูกค้าสนใจ/ถามโปร"
        elif any(word in lowered for word in ["ปัญหา", "ไม่ได้", "เสีย", "ช้า"]):
            intent = "ลูกค้าแจ้งปัญหา"
        draft = (
            f"วิเคราะห์: {intent}\n"
            "Draft (ยังไม่ส่งจริง):\n"
            "สวัสดีครับ ขอบคุณที่ทักมานะครับ เดี๋ยวทีมงานตรวจรายละเอียดให้ทันที "
            "รบกวนแจ้งข้อมูลเพิ่มเติมหรือช่องทางติดต่อกลับได้เลยครับ"
        )
        self.care_box.delete("1.0", "end")
        self.care_box.insert("end", draft + "\n\nคำเตือน: ข้อความนี้เป็น draft เท่านั้น หากจะ Reply จริงให้ไปแท็บ Action จริงและผ่าน Queue ก่อน")
        self.log("Customer Care สร้าง draft แล้ว ยังไม่ได้ส่งจริง")

    def _resolve_user_id(self, value: str) -> str:
        v = value.strip().lstrip("@")
        if v.isdigit():
            return v
        prof = self.client().lookup_usernames([v])
        if not prof:
            raise XAPIError(0, f"หา user ไม่เจอ: {value}")
        return prof[0].get("id", "")

    def choose_media(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp;*.bmp"), ("All", "*.*")])
        if path:
            self.media_path_var.set(path)

    def publish_post(self):
        text = self.post_text.get("1.0", "end").strip()
        if not text and not self.media_path_var.get().strip():
            raise XAPIError(0, "ยังไม่มีข้อความหรือรูป")
        media_ids = []
        if self.media_path_var.get().strip():
            payload = self.client().upload_media(self.media_path_var.get().strip())
            mid = payload.get("data", {}).get("id")
            if mid:
                media_ids.append(mid)
        payload = self.client().publish_post(text, self.reply_to_var.get().strip(), media_ids=media_ids)
        self.log(f"โพสต์สำเร็จ: {payload}")
        return payload

    def delete_post(self):
        tid = self.action_tweet_id_var.get().strip()
        payload = self.client().delete_post(tid)
        self.log(f"ลบโพสต์สำเร็จ: {payload}")
        return payload

    def like_post(self):
        payload = self.client().like_post(self.self_user_id_var.get().strip(), self.action_tweet_id_var.get().strip())
        self.log(f"Like สำเร็จ: {payload}")
        return payload

    def unlike_post(self):
        payload = self.client().unlike_post(self.self_user_id_var.get().strip(), self.action_tweet_id_var.get().strip())
        self.log(f"Unlike สำเร็จ: {payload}")
        return payload

    def retweet_post(self):
        payload = self.client().retweet_post(self.self_user_id_var.get().strip(), self.action_tweet_id_var.get().strip())
        self.log(f"Retweet สำเร็จ: {payload}")
        return payload

    def unretweet_post(self):
        payload = self.client().unretweet_post(self.self_user_id_var.get().strip(), self.action_tweet_id_var.get().strip())
        self.log(f"Unretweet สำเร็จ: {payload}")
        return payload

    def follow_user(self):
        target = self._resolve_user_id(self.target_user_var.get())
        payload = self.client().follow_user(self.self_user_id_var.get().strip(), target)
        self.log(f"Follow สำเร็จ: {payload}")
        return payload

    def unfollow_user(self):
        target = self._resolve_user_id(self.target_user_var.get())
        payload = self.client().unfollow_user(self.self_user_id_var.get().strip(), target)
        self.log(f"Unfollow สำเร็จ: {payload}")
        return payload

    def send_dm(self):
        target = self._resolve_user_id(self.target_user_var.get())
        payload = self.client().send_dm(target, self.dm_text_var.get().strip())
        self.log(f"DM สำเร็จ: {payload}")
        return payload

    def create_list(self):
        payload = self.client().create_list(self.list_name_var.get().strip(), "สร้างด้วย BN9 V6", private=True)
        lid = payload.get("data", {}).get("id")
        if lid:
            self.list_id_var.set(lid)
        self.log(f"สร้าง List สำเร็จ: {payload}")
        return payload

    def add_list_member(self):
        target = self._resolve_user_id(self.target_user_var.get())
        payload = self.client().add_list_member(self.list_id_var.get().strip(), target)
        self.log(f"เพิ่มสมาชิก List สำเร็จ: {payload}")
        return payload

    def remove_list_member(self):
        target = self._resolve_user_id(self.target_user_var.get())
        payload = self.client().remove_list_member(self.list_id_var.get().strip(), target)
        self.log(f"ลบสมาชิก List สำเร็จ: {payload}")
        return payload

    def fetch_ads(self):
        set_status("Started: Ads Report")
        self.log("Started: Ads Report")
        self.log("Cost Guard result: Ads API ต้องมี config ครบก่อน ระบบจะไม่รันถ้าขาดค่า")
        required = [
            self.ads_ck_var.get().strip(),
            self.ads_cs_var.get().strip(),
            self.ads_at_var.get().strip(),
            self.ads_as_var.get().strip(),
            self.ads_account_var.get().strip(),
        ]
        if not all(required):
            msg = "ยังไม่พร้อมรัน Ads API จริง กรุณาตั้งค่า Ads API ก่อน"
            self.log(msg)
            messagebox.showwarning("Ads API ยังไม่พร้อม", msg)
            return
        params = {}
        for line in self.ads_params_text.get("1.0", "end").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                params[k.strip()] = v.strip()
        client = AdsClient(self.ads_ck_var.get(), self.ads_cs_var.get(), self.ads_at_var.get(), self.ads_as_var.get(), self.ads_base_var.get())
        payload = client.analytics_sync(self.ads_account_var.get().strip(), params)
        run_dir = now_run_dir("ads")
        save_json(run_dir / "ads_analytics.json", payload)
        self.last_run_dir = run_dir
        self.log("API result count: Ads API ตอบกลับ 1 payload")
        self.log(f"Output folder: {run_dir}")
        self.log("Done: Ads Analytics เสร็จ")

    def _send_summary(self, summary: dict, run_dir: Path):
        msg = [
            "BN9 X Social Report",
            f"โพสต์ทั้งหมด: {summary.get('total_posts', 0)}",
            f"ความสนใจสูง: {summary.get('high_interest', 0)}",
            f"ผลลัพธ์: {run_dir}",
            "หมวด:",
        ]
        for k, v in (summary.get("categories") or {}).items():
            msg.append(f"- {k}: {v}")
        ideas = summary.get("content_ideas") or []
        if ideas:
            msg.append("ไอเดียคอนเทนต์:")
            for i in ideas[:5]:
                msg.append(f"- {i}")
        send_message(self.tg_token_var.get(), self.tg_chat_var.get(), "\n".join(msg))
        self.log("ส่งสรุปเข้า Telegram แล้ว")

    def send_latest_summary(self):
        if not self.last_rows and not self.last_trends:
            raise XAPIError(0, "ยังไม่มีผลลัพธ์ล่าสุด")
        summary = summarize(self.last_rows) if self.last_rows else {"total_posts": 0, "categories": {}, "high_interest": 0, "content_ideas": ["Trend Radar เสร็จแล้ว"]}
        self._send_summary(summary, self.last_run_dir or OUTPUT_DIR)

    def _latest_output_dir(self) -> Path | None:
        if self.last_run_dir and self.last_run_dir.exists():
            return self.last_run_dir
        if OUTPUT_DIR.exists():
            dirs = sorted([p for p in OUTPUT_DIR.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
            if dirs:
                self.last_run_dir = dirs[0]
                return dirs[0]
        return None

    def open_latest_run_dir(self):
        run_dir = self._latest_output_dir()
        if not run_dir:
            messagebox.showinfo("ยังไม่มี", "ยังไม่มีโฟลเดอร์ผลลัพธ์")
            return
        open_path(run_dir)

    def open_latest_csv(self):
        run_dir = self._latest_output_dir()
        if not run_dir:
            messagebox.showinfo("ยังไม่มี", "ยังไม่มีไฟล์ CSV")
            return
        preferred = ["posts.csv", "lead_list.csv", "trends.csv", "competitor_posts.csv", "counts.csv", "creators.csv"]
        for name in preferred:
            path = run_dir / name
            if path.exists():
                open_path(path)
                return
        csvs = sorted(run_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if csvs:
            open_path(csvs[0])
            return
        messagebox.showinfo("ยังไม่มี", "รอบล่าสุดยังไม่มีไฟล์ CSV")

    def open_last_dashboard(self):
        run_dir = self._latest_output_dir()
        if not run_dir:
            messagebox.showinfo("ยังไม่มี", "ยังไม่มีรายงาน")
            return
        dash = run_dir / "dashboard.html"
        if dash.exists():
            open_browser(dash)
        else:
            open_path(run_dir)


def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
