"""AI 富化 + 简报组装：批量打分/中文摘要，再生成 Markdown。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from ai.client import generate


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
        result = generate(_prompt(group, priorities), model=model, rate_limit=rate)
        analyses = result.get("analyses", [])
        for j, item in enumerate(group):
            a = analyses[j] if j < len(analyses) else {}
            if a:
                score = max(0, min(100, int(a.get("score", 0))))
                if min_score and score < min_score:
                    continue
                out.append(
                    {
                        **item,
                        "ai_score": score,
                        "ai_summary": a.get("summary", ""),
                        "ai_topic": a.get("topic", "其它"),
                    }
                )
            else:
                # AI 没给结果也别丢，给个中性分
                out.append({**item, "ai_score": 50, "ai_summary": item.get("summary", "")[:200], "ai_topic": "其它"})
    return out


def _prompt(group: list[dict], priorities: list[str]) -> str:
    items_text = "\n\n".join(
        f"条目 {i + 1}:\n标题: {it.get('title', '')}\n来源: {it.get('source', '')}\n"
        f"摘要: {it.get('summary', '')[:600]}"
        for i, it in enumerate(group)
    )
    prio = "\n".join(f"- {p}" for p in priorities) or "- AI 领域的重要进展"
    return f"""你是一名 AI 领域资深编辑。请分析下面 {len(group)} 条内容，为每条返回 JSON。

# 条目
{items_text}

# 用户关心的方向（据此打重要性分）
{prio}

# 要求
- summary：用简体中文写 1-2 句话，说清楚这条讲了什么、为什么值得看。不要复述标题。
- score：0-100 的重要性分。90+=必看的大新闻/突破，70-89=值得看，50-69=一般，<50=边角料。
- topic：从中选一个简短主题标签：模型发布 / 研究论文 / 行业动态 / 工具开源 / 安全监管 / 观点访谈 / 其它。

严格按条目顺序返回：
{{"analyses": [{{"score": <int>, "summary": "<中文>", "topic": "<标签>"}}, ...]}}"""


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
    if compact:
        return f"- **[{title}]({url})** · {source} `{score}`  \n  {summary}"
    return f"### [{title}]({url})\n\n`重要性 {score}` · {source}\n\n{summary}\n"
