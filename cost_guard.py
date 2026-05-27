from __future__ import annotations


def estimate_recent_search_cost(num_queries: int, max_posts_per_query: int) -> dict:
    queries = max(0, int(num_queries or 0))
    per_query = max(0, int(max_posts_per_query or 0))
    estimated_posts = queries * per_query
    estimated_pages = sum(max(1, (per_query + 99) // 100) for _ in range(queries)) if queries else 0
    return {
        "num_queries": queries,
        "max_posts_per_query": per_query,
        "estimated_posts": estimated_posts,
        "estimated_api_calls": estimated_pages,
        "resource_note": "X API คิดเครดิตตาม endpoint และ resource จริงของบัญชี Developer",
    }


def format_cost_warning(estimate: dict) -> str:
    return (
        f"รอบนี้จะดึงประมาณ {estimate.get('estimated_posts', 0)} โพสต์\n"
        f"จำนวนคำค้น: {estimate.get('num_queries', 0)}\n"
        f"ดึงสูงสุดต่อคำค้น: {estimate.get('max_posts_per_query', 0)}\n"
        f"คาดว่าจะเรียก Recent Search ประมาณ {estimate.get('estimated_api_calls', 0)} ครั้ง\n"
        "ใช้เครดิตตามจำนวน resource ที่ X API คิดจริง\n\n"
        "ยืนยันดึงข้อมูลหรือไม่?"
    )
