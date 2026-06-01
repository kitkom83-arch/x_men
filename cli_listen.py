from __future__ import annotations

import argparse
from pathlib import Path

from analysis_engine import analyze_rows, creator_scores, deduplicate_rows, filter_rows, should_include_review_queue, summarize
from reporting import attach_report_to_session, build_dashboard_hub, create_research_session, now_run_dir, save_csv, save_dashboard, save_excel, save_json
from storage import read_env
from telegram_notify import TelegramError, send_message
from x_client import XClient


def main():
    p = argparse.ArgumentParser(description="BN9 X Social Real V5 CLI - run real X API listening")
    p.add_argument("--queries", default="queries.txt", help="file with one query per line")
    p.add_argument("--max-posts", type=int, default=10)
    p.add_argument("--telegram", action="store_true")
    p.add_argument("--session-name", default="")
    p.add_argument("--session-note", default="")
    args = p.parse_args()
    env = read_env()
    queries_file = Path(args.queries)
    if not queries_file.exists():
        raise SystemExit(f"ไม่พบไฟล์คำค้น: {queries_file}")
    queries = [x.strip() for x in queries_file.read_text(encoding="utf-8").splitlines() if x.strip() and not x.strip().startswith("# ")]
    client = XClient(env.get("BEARER_TOKEN", ""), env.get("USER_ACCESS_TOKEN", ""), env.get("X_API_BASE_URL", "https://api.x.com/2"))
    raw = []
    for q in queries:
        print(f"FETCH: {q}")
        raw.extend(client.recent_search(q, max_posts=args.max_posts))
    kept, removed = filter_rows(raw, env.get("BLOCK_WORDS", ""), env.get("REQUIRE_WORDS", ""), env.get("REMOVE_BLOCKED", "1") != "0")
    rows = deduplicate_rows(analyze_rows(kept, env.get("BRAND_NAME", "ร้านเรา"), env.get("BRAND_WORDS", "")))
    creators = creator_scores(rows)
    summary = summarize(rows)
    run_dir = now_run_dir("cli_listen")
    save_csv(run_dir / "raw_posts_before_filter.csv", raw)
    save_csv(run_dir / "filtered_out.csv", removed)
    save_csv(run_dir / "posts.csv", rows)
    lead_rows = [r for r in rows if should_include_review_queue(r)]
    save_csv(run_dir / "lead_list.csv", lead_rows)
    save_csv(run_dir / "creators.csv", creators)
    save_json(run_dir / "summary.json", summary)
    save_excel(run_dir / "report.xlsx", {"posts": rows, "lead_list": lead_rows, "creators": creators, "filtered_out": removed}, summary)
    save_dashboard(run_dir / "dashboard.html", "BN9 CLI Social Listening Report", summary, rows, creators=creators)
    if args.session_name or args.session_note:
        session_dir = create_research_session(session_name=args.session_name, session_note=args.session_note)
        attach_report_to_session(session_dir, "social", run_dir, inputs={"social_queries": queries})
    build_dashboard_hub()
    print(f"DONE: {run_dir}")
    if args.telegram or env.get("SEND_TELEGRAM", "0") == "1":
        msg = f"BN9 CLI Report\nโพสต์ทั้งหมด: {summary.get('total_posts', 0)}\nความสนใจสูง: {summary.get('high_interest', 0)}\nผลลัพธ์: {run_dir}"
        try:
            send_message(env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", ""), msg)
            print("Telegram sent")
        except TelegramError as exc:
            print(f"Telegram skipped: {exc}")


if __name__ == "__main__":
    main()
