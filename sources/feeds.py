"""统一的 RSS / Atom 抓取层（YouTube 频道也是 Atom feed）。

用 feedparser，能同时吃 RSS 2.0 和 Atom，并把各种日期格式归一化。
"""
from __future__ import annotations

from datetime import datetime, timezone
from time import mktime

import feedparser
import requests

USER_AGENT = "Mozilla/5.0 (compatible; ai-digest/1.0; +https://github.com)"


def youtube_feed_url(channel_id: str) -> str:
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def _published(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)


def fetch_feed(url: str, source: str) -> list[dict]:
    """抓一个 feed，返回归一化后的条目列表。

    每条至少包含: id, title, url, source, published, summary。
    单个源失败不抛出，返回空列表并打印，保证其它源继续。
    """
    # 自己用 requests 取字节再交给 feedparser：比 feedparser 内置抓取更稳，
    # 能避开部分服务器(如 Substack)导致的 IncompleteRead。
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except requests.RequestException as exc:
        print(f"  [{source}] FAILED: {exc}")
        return []

    if parsed.bozo and not parsed.entries:
        print(f"  [{source}] 无法解析: {getattr(parsed, 'bozo_exception', 'unknown')}")
        return []

    items: list[dict] = []
    for entry in parsed.entries:
        link = entry.get("link", "")
        if not link:
            continue
        published = _published(entry)
        summary = entry.get("summary", "") or ""
        items.append(
            {
                "id": entry.get("id", link),
                "title": _clean_title(entry.get("title", "") or ""),
                "url": link,
                "source": source,
                "published": published.isoformat() if published else "",
                "_published_dt": published,
                "summary": _strip_html(summary)[:1200],
            }
        )
    return items


def _strip_html(text: str) -> str:
    import html
    import re

    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _clean_title(text: str) -> str:
    """标题清洗：解码 HTML 实体并合并空白，但**不删尖括号**。

    标题里像 "On the <dl>" 的 <dl> 是文章名的一部分，按 HTML 标签删掉会把标题截断。
    """
    import html
    import re

    return re.sub(r"\s+", " ", html.unescape(text)).strip()
