"""Tavily 网页新闻搜索源。

用于覆盖固定 RSS 之外的 AI 大新闻、以及间接补社媒/转载内容。
项目内独立实现（不依赖本机的 openclaw 脚本），这样 GitHub Actions 也能用。
需要环境变量 TAVILY_API_KEY。
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

TAVILY_URL = "https://api.tavily.com/search"


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _search(key: str, query: str, max_results: int, days: int, source: str) -> list[dict]:
    try:
        resp = requests.post(
            TAVILY_URL,
            json={
                "api_key": key,
                "query": query,
                "topic": "news",
                "days": days,
                "max_results": max_results,
                "include_answer": False,
                "include_images": False,
                "include_raw_content": False,
            },
            timeout=40,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        print(f"  [Tavily:{query[:30]}] FAILED: {exc}")
        return []

    hits = data.get("results", []) or []
    print(f"  [Tavily:{query[:40]}] {len(hits)} 条")
    out: list[dict] = []
    for r in hits:
        url = r.get("url", "")
        if not url:
            continue
        dt = _parse_date(r.get("published_date"))
        out.append(
            {
                "id": url,
                "title": (r.get("title") or "").strip(),
                "url": url,
                "source": source,
                "published": dt.isoformat() if dt else "",
                "_published_dt": dt,
                # 新鲜度已由 days 参数控制，重复由 seen.json 拦截，
                # 因此不受全局 lookback_hours 时间窗约束。
                "_skip_window": True,
                "summary": (r.get("content") or "")[:1200],
            }
        )
    return out


def fetch(
    queries: list[str],
    max_results: int = 5,
    days: int = 3,
    people: list[str] | None = None,
    people_max_results: int = 3,
) -> list[dict]:
    key = os.environ.get("TAVILY_API_KEY", "")
    if not key:
        print("  [Tavily] 未设置 TAVILY_API_KEY，跳过")
        return []

    items: list[dict] = []
    for q in queries:
        items += _search(key, q, max_results, days, "网络搜索 (Tavily)")
    for name in people or []:
        hits = _search(key, f'"{name}" AI', people_max_results, days, f"人物·{name} (Tavily)")
        # Tavily 对人名是模糊匹配，会拽进同名无关结果；只保留正文确实提到完整姓名的。
        nl = name.lower()
        kept = [h for h in hits if nl in f"{h['title']} {h['summary']}".lower()]
        if len(kept) < len(hits):
            print(f"    [人物·{name}] 过滤掉 {len(hits) - len(kept)} 条同名噪音")
        items += kept
    return items
