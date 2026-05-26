"""AI 富化 + 简报组装：批量打分/中文摘要，再生成 Markdown。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ai.client import generate
from ai.quality import apply_quality_gate, classify_source


def _chunks(items: list[dict], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def analyse(items: list[dict], cfg: dict) -> list[dict]:
    """逐批让 AI 打分+写中文摘要+主题标签。AI 不可用时降级为原样返回。"""
    ai_cfg = cfg.get("ai", {})
    if not ai_cfg.get("enabled", True):
        return items

    model = ai_cfg.get("model", "gemini-2.0-flash")
    rate = ai_cfg.get("rate_limit_seconds", 7.0)
    batch = ai_cfg.get("batch_size", 5)
    min_score = ai_cfg.get("min_score", 0)
    priorities = ai_cfg.get("priorities", [])

    batches = list(_chunks(items, batch))
    print(f"  [AI] {len(items)} 条 → {len(batches)} 次调用")

    out: list[dict] = []
    for idx, group in enumerate(batches, 1):
        print(f"  [AI] 第 {idx}/{len(batches)} 批…")
        result = generate(_prompt(group, priorities, cfg), model=model, rate_limit=rate)
        analyses = result.get("analyses", [])
        # 空返回或条数不足时重试一次（应对偶发 429/截断）
        if len(analyses) < len(group):
            print(f"  [AI] 第 {idx} 批返回不全（{len(analyses)}/{len(group)}），重试…")
            retry = generate(_prompt(group, priorities, cfg), model=model, rate_limit=rate).get("analyses", [])
            if len(retry) > len(analyses):
                analyses = retry
        for j, item in enumerate(group):
            a = analyses[j] if j < len(analyses) else {}
            if not a:
                # 拿不到 AI 结果就不收进简报，避免英文残摘要 / 绕过 min_score
                print(f"  [AI] 跳过未富化条目: {item.get('title', '')[:40]}")
                continue
            score = max(0, min(100, int(a.get("score", 0))))
            enriched = apply_quality_gate(
                {
                    **item,
                    "ai_score": score,
                    "ai_summary": a.get("summary", ""),
                    "ai_reason": a.get("reason", ""),
                    "ai_credibility": a.get("credibility", ""),
                    "ai_topic": a.get("topic", "其它"),
                },
                cfg,
            )
            if min_score and enriched.get("ai_score", 0) < min_score:
                continue
            out.append(enriched)
    return out


def _prompt(group: list[dict], priorities: list[str], cfg: dict) -> str:
    items_text = "\n\n".join(
        _prompt_item(i, it, cfg)
        for i, it in enumerate(group)
    )
    prio = "\n".join(f"- {p}" for p in priorities) or "- AI 领域的重要进展"
    return f"""你是一名 AI 领域资深编辑。请分析下面 {len(group)} 条内容，为每条返回 JSON。

# 条目
{items_text}

# 用户关心的方向（据此打重要性分）
{prio}

# 信源和质检规则
- 官方博客、研究原文、主流媒体、知名技术博客可给更高可信度。
- 聚合站、转载站、营销站、来源不清的网站即使标题很大，也不要轻易给 90 分以上。
- 90+ 分必须是必看的大新闻/突破，且需要有一手/主流/研究原文支撑。
- 如果来源偏弱但事件可能重要，降低 score，并在 credibility 写“待核”。

# 要求
- summary：用简体中文写 1-2 句话，说清楚这条讲了什么、为什么值得看。不要复述标题。
- score：0-100 的重要性分。90+=必看的大新闻/突破，70-89=值得看，50-69=一般，<50=边角料。
- reason：用 12-28 个中文字解释评分理由，例如“影响搜索入口和信息分发”。
- credibility：从 高 / 中 / 待核 中选一个，表示信源可信度与核验状态。
- topic：从中选一个简短主题标签：模型发布 / 研究论文 / 行业动态 / 工具开源 / 安全监管 / 观点访谈 / 其它。

严格按条目顺序返回：
{{"analyses": [{{"score": <int>, "summary": "<中文>", "reason": "<中文>", "credibility": "高|中|待核", "topic": "<标签>"}}, ...]}}"""


def _prompt_item(i: int, it: dict, cfg: dict) -> str:
    source_quality = classify_source(it, cfg)
    return (
        f"条目 {i + 1}:\n标题: {it.get('title', '')}\n来源: {it.get('source', '')}\n"
        f"域名: {source_quality.get('source_domain', '')}\n"
        f"信源等级: {source_quality.get('source_tier_label', '')}\n"
        f"摘要: {it.get('summary', '')[:600]}"
    )


def dedupe_stories(items: list[dict], cfg: dict) -> list[dict]:
    """让 AI 找出报道同一件事的重复条目，每组只保留分数最高的一条。

    只按「同一具体事件」合并，不按「同一主题」。AI 不可用或条目过少时原样返回。
    """
    if not cfg.get("ai", {}).get("enabled", True) or len(items) < 2:
        return items

    listing = "\n".join(
        f"{i + 1}. [{it.get('source', '')}] {it.get('title', '')}"
        for i, it in enumerate(items)
    )
    result = generate(
        f"""下面是今天的 AI 资讯条目。找出报道**同一件事/同一具体事件**的重复条目并分组。
注意：是「同一事件的不同报道」才算重复，仅仅「同一主题」不算。

{listing}

返回 JSON: {{"groups": [[同一事件的条目编号(1基), ...], ...]}}。
不确定就不要分组；独立事件无需列出。""",
        model=cfg.get("ai", {}).get("model", "gemini-2.0-flash"),
        rate_limit=cfg.get("ai", {}).get("rate_limit_seconds", 7.0),
    )

    drop: set[int] = set()
    for group in result.get("groups", []) or []:
        idxs = [i - 1 for i in group if isinstance(i, int) and 1 <= i <= len(items)]
        if len(idxs) < 2:
            continue
        keep = max(idxs, key=lambda k: items[k].get("ai_score", 0))
        drop.update(k for k in idxs if k != keep)

    if drop:
        print(f"  [去重] 合并同一事件，丢弃 {len(drop)} 条重复")
    return [it for i, it in enumerate(items) if i not in drop]


def overview(items: list[dict], cfg: dict) -> str:
    """让 AI 写一段当日总览（3 条以内要点）。失败返回空串。"""
    if not cfg.get("digest", {}).get("write_overview", True):
        return ""
    top = sorted(items, key=lambda x: x.get("ai_score", 0), reverse=True)[:12]
    listing = "\n".join(f"- [{i.get('ai_score')}] {i.get('title')} ({i.get('source')})" for i in top)
    result = generate(
        f"""下面是今天收集到的 AI 资讯标题（已按重要性排序）。
用简体中文写一段不超过 3 条的「今日要点」，每条一句话，点出今天最值得关注的事。

{listing}

返回 JSON: {{"points": ["要点1", "要点2", "要点3"]}}""",
        model=cfg.get("ai", {}).get("model", "gemini-2.0-flash"),
        rate_limit=cfg.get("ai", {}).get("rate_limit_seconds", 7.0),
    )
    points = result.get("points", [])
    return "\n".join(f"- {p}" for p in points)


TOPIC_ORDER = [
    "模型发布",
    "研究论文",
    "行业动态",
    "工具开源",
    "安全监管",
    "观点访谈",
    "其它",
]


def build_markdown(items: list[dict], cfg: dict, intro: str = "") -> str:
    """组装最终 Markdown 简报。"""
    today = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    top_n = cfg.get("digest", {}).get("top_n", 8)
    ranked = sorted(items, key=lambda x: x.get("ai_score", 0), reverse=True)

    lines = [f"# AI 速览 · {today}", "", f"今天共收集 **{len(items)}** 条更新。", ""]

    if intro:
        lines += ["## 今日要点", "", intro, ""]

    lines += ["## 重点条目", ""]
    for it in ranked[:top_n]:
        lines.append(_render_item(it))
    lines.append("")

    # 其余按主题分组
    rest = ranked[top_n:]
    if rest:
        lines += ["## 更多更新", ""]
        by_topic: dict[str, list[dict]] = {}
        for it in rest:
            by_topic.setdefault(it.get("ai_topic", "其它"), []).append(it)
        for topic in TOPIC_ORDER:
            group = by_topic.get(topic)
            if not group:
                continue
            lines.append(f"### {topic}")
            lines.append("")
            for it in group:
                lines.append(_render_item(it, compact=True))
            lines.append("")

    lines += ["---", "", "*由 AI Digest 自动生成。修改信源请编辑 config.yaml。*"]
    return "\n".join(lines)


def _render_item(it: dict, compact: bool = False) -> str:
    score = it.get("ai_score", "")
    title = it.get("title", "")
    url = it.get("url", "")
    source = it.get("source", "")
    summary = it.get("ai_summary", "")
    reason = it.get("ai_reason", "")
    credibility = it.get("ai_credibility") or it.get("source_credibility", "")
    qa_notes = it.get("qa_notes", [])
    extra = ""
    if reason:
        extra += f"  \n  为什么重要：{reason}"
    if credibility:
        extra += f"  \n  可信度：{credibility}"
    if qa_notes:
        extra += f"  \n  质检：{'；'.join(qa_notes)}"
    if compact:
        return f"- **[{title}]({url})** · {source} `{score}`  \n  {summary}{extra}"
    return f"### [{title}]({url})\n\n`重要性 {score}` · {source}\n\n{summary}{extra}\n"
