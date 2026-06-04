"""编排：抓取所有信源 → 去重/时间窗过滤 → AI 富化 → 生成简报 → 发邮件。

每天由 GitHub Actions 调用一次。已发过的条目记在 state/seen.json，由工作流提交回仓库。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from ai import digest as digest_mod
from ai.quality import apply_quality_gate
from deliver import email as mailer
from deliver import site as site_builder
from sources import tavily
from sources.feeds import fetch_feed, youtube_feed_url

ROOT = Path(__file__).parent
SEEN_PATH = ROOT / "state" / "seen.json"
SEEN_CAP = 5000  # seen.json 里最多保留多少条 id，防止无限膨胀


def load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def load_seen() -> dict[str, None]:
    # 用 dict（保留插入顺序）而非 set：裁剪时才能按时间序保留“最近见到的”id。
    if SEEN_PATH.exists():
        try:
            return dict.fromkeys(json.loads(SEEN_PATH.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_seen(seen: dict[str, None]) -> None:
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    # dict 有序，[-CAP:] 保留最近插入的 CAP 条，丢弃最老的（而非随机丢弃）。
    trimmed = list(seen)[-SEEN_CAP:]
    SEEN_PATH.write_text(json.dumps(trimmed, ensure_ascii=False, indent=0))


def collect(cfg: dict) -> list[dict]:
    items: list[dict] = []
    for ch in cfg.get("youtube", []):
        src = f"YouTube · {ch['name']}"
        fetched = source_filter(fetch_feed(youtube_feed_url(ch["channel_id"]), src), ch)
        print(f"[{src}] {len(fetched)} 条")
        items += fetched
    for feed in cfg.get("rss", []):
        fetched = source_filter(fetch_feed(feed["url"], feed["name"]), feed)
        print(f"[{feed['name']}] {len(fetched)} 条")
        items += fetched
    tv = cfg.get("tavily", {})
    if tv.get("enabled") and tv.get("queries"):
        print("[Tavily 搜索]")
        items += tavily.fetch(
            tv["queries"],
            max_results=tv.get("max_results", 5),
            days=tv.get("days", 3),
            people=tv.get("people", []),
            people_max_results=tv.get("people_max_results", 3),
        )
    return items


def _title_ok(title: str, block: list[str], require: list[str]) -> bool:
    low = title.lower()
    if any(w.lower() in low for w in block):
        return False
    if require and not any(w.lower() in low for w in require):
        return False
    return True


def passes_filters(title: str, filters: dict) -> bool:
    return _title_ok(
        title,
        filters.get("blocked_keywords", []),
        filters.get("required_keywords", []),
    )


def source_filter(items: list[dict], src_cfg: dict) -> list[dict]:
    """源级关键词过滤：让“全量型”信源在本地就收口，不必把相关性全压给 AI。"""
    block = src_cfg.get("block_keywords") or []
    require = src_cfg.get("require_keywords") or []
    if not block and not require:
        return items
    kept = [it for it in items if _title_ok(it.get("title", ""), block, require)]
    if len(kept) != len(items):
        print(f"    源级过滤: {len(items)} → {len(kept)} 条")
    return kept


def main() -> None:
    cfg = load_config()
    seen = load_seen()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=cfg.get("lookback_hours", 30))
    filters = cfg.get("filters", {})

    raw = collect(cfg)

    fresh: list[dict] = []
    for it in raw:
        if it["id"] in seen:
            continue
        dt = it.get("_published_dt")
        if dt and dt < cutoff and not it.get("_skip_window"):
            continue
        if not passes_filters(it.get("title", ""), filters):
            continue
        fresh.append(it)

    # 同一批内按 url 再去一次重
    by_url, deduped = set(), []
    for it in fresh:
        if it["url"] in by_url:
            continue
        by_url.add(it["url"])
        deduped.append(it)

    print(f"新条目: {len(deduped)} 条（过滤前 {len(raw)}）")

    if not deduped:
        print("没有新内容，跳过发信。")
        # 仍然记录本次抓到的所有 id，避免历史条目某天突然进窗
        for it in raw:
            seen[it["id"]] = None
        save_seen(seen)
        return

    if os.environ.get("GEMINI_API_KEY"):
        enriched = digest_mod.analyse(deduped, cfg)
        enriched = digest_mod.dedupe_stories(enriched, cfg)
        enriched = digest_mod.dedupe_similar(enriched)
        intro = digest_mod.overview(enriched, cfg)
    else:
        print("[AI] 未设置 GEMINI_API_KEY，跳过富化，直接列原始条目")
        enriched = [
            apply_quality_gate(
                {
                    **it,
                    "ai_score": 50,
                    "ai_summary": it.get("summary", "")[:200],
                    "ai_reason": "未启用 AI 富化",
                    "ai_topic": "其它",
                },
                cfg,
            )
            for it in deduped
        ]
        intro = ""

    markdown_body = digest_mod.build_markdown(enriched, cfg, intro=intro)

    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    subject = f"{cfg.get('digest', {}).get('subject_prefix', 'AI 速览')} · {today} · {len(enriched)} 条"

    # 本地也存一份，方便调试/留档
    out_dir = ROOT / "state" / "digests"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{today}.md").write_text(markdown_body, encoding="utf-8")

    # 生成静态网页（GitHub Pages 展示）
    site_builder.build(enriched, cfg, intro, today)

    if os.environ.get("SMTP_USER"):
        try:
            mailer.send(subject, markdown_body, cfg)
        except Exception as exc:
            print(f"[mail] 发送失败，继续保存站点和 seen 状态: {exc}", file=sys.stderr)
    else:
        print("[mail] 未设置 SMTP_USER，仅生成本地简报，不发信。")

    for it in raw:
        seen[it["id"]] = None
    save_seen(seen)
    print("完成。")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # 让 Actions 日志能看到栈
        print(f"运行失败: {exc}", file=sys.stderr)
        raise
