"""把简报渲染成静态 HTML，供 GitHub Pages 展示（输出到 docs/）。

- docs/digests/<日期>.html  每日一页（历史靠提交累积）
- docs/index.html           首页：最新一期内容 + 历史列表
"""
from __future__ import annotations

import html
from pathlib import Path

ROOT = Path(__file__).parent.parent
DOCS = ROOT / "docs"
DIGEST_DIR = DOCS / "digests"

TOPIC_ORDER = [
    "模型发布",
    "研究论文",
    "行业动态",
    "工具开源",
    "安全监管",
    "观点访谈",
    "其它",
]


def _score_class(score: int) -> str:
    if score >= 85:
        return "s-high"
    if score >= 70:
        return "s-mid"
    if score >= 50:
        return "s-ok"
    return "s-low"


def _card(it: dict, compact: bool = False) -> str:
    score = int(it.get("ai_score", 0))
    title = html.escape(it.get("title", ""))
    url = html.escape(it.get("url", ""), quote=True)
    source = html.escape(it.get("source", ""))
    domain = html.escape(it.get("source_domain", ""))
    tier = html.escape(it.get("source_tier_label", ""))
    credibility = html.escape(it.get("ai_credibility") or it.get("source_credibility", ""))
    topic = html.escape(it.get("ai_topic", "其它"))
    summary = html.escape(it.get("ai_summary", ""))
    reason = html.escape(it.get("ai_reason", ""))
    qa_notes = [html.escape(str(note)) for note in it.get("qa_notes", []) or []]
    quality = _quality_label(tier, credibility)
    show_domain = domain and (it.get("source_tier") == "low" or "Tavily" in it.get("source", "") or "网络搜索" in it.get("source", ""))
    chips = [
        f'<span class="chip chip--src">{source}</span>',
        f'<span class="chip chip--topic">{topic}</span>',
    ]
    if quality:
        chips.append(f'<span class="chip chip--quality">{quality}</span>')
    if show_domain:
        chips.append(f'<span class="chip chip--domain">{domain}</span>')
    chip_html = "\n      ".join(chips)
    reason_html = ""
    if reason and not compact and reason != "未启用 AI 富化":
        reason_html = f'\n  <p class="reason"><strong>为什么重要：</strong>{reason}</p>'
    qa_html = ""
    if qa_notes:
        qa_html = f'\n  <p class="qa"><strong>质检：</strong>{"；".join(qa_notes)}</p>'
    cls = "card card--compact" if compact else "card"
    return f"""<article class="{cls}">
  <div class="card-head">
    <div class="meta">
      {chip_html}
    </div>
    <span class="badge {_score_class(score)}">{score}</span>
  </div>
  <h3 class="title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
  <p class="summary">{summary}</p>{reason_html}{qa_html}
</article>"""


def _digest_body(items: list[dict], cfg: dict, intro: str, top_n: int) -> str:
    ranked = sorted(items, key=lambda x: x.get("ai_score", 0), reverse=True)
    parts: list[str] = []
    fallback = _is_fallback_run(ranked)

    if intro:
        bullets = "".join(f"<li>{html.escape(line.lstrip('- ').strip())}</li>" for line in intro.splitlines() if line.strip())
        parts.append(f'<section class="overview"><h2>今日要点</h2><ul>{bullets}</ul></section>')
    elif fallback:
        parts.append(
            '<section class="overview overview--muted"><h2>本地预览</h2>'
            '<p>当前页面由无 AI 密钥的本地试跑生成，仅用于检查版式；正式运行会恢复评分、摘要和今日要点。</p></section>'
        )

    lead_title = "最新抓取" if fallback else "重点条目"
    parts.append(f'<section><h2>{lead_title}</h2>')
    parts += [_card(it) for it in ranked[:top_n]]
    parts.append("</section>")

    rest = ranked[top_n:]
    if rest:
        by_topic: dict[str, list[dict]] = {}
        for it in rest:
            by_topic.setdefault(it.get("ai_topic", "其它"), []).append(it)
        parts.append('<section class="more"><h2>更多更新</h2>')
        for topic in TOPIC_ORDER:
            group = by_topic.get(topic)
            if not group:
                continue
            parts.append(f'<h3 class="topic-h">{html.escape(topic)}</h3>')
            parts += [_card(it, compact=True) for it in group]
        parts.append("</section>")
    return "\n".join(parts)


def _quality_label(tier: str, credibility: str) -> str:
    if tier == "官方/一手":
        return "官方/一手"
    if credibility == "待核":
        return "待核来源"
    if tier == "低置信/转载":
        return "低置信来源"
    if tier == "高可信":
        return "高可信来源"
    if tier == "普通来源":
        return "普通来源"
    return credibility


def _is_fallback_run(items: list[dict]) -> bool:
    return bool(items) and all(it.get("ai_reason") == "未启用 AI 富化" for it in items)


def _page(title: str, body: str, home_href: str | None, history: list[str] | None, digest_href) -> str:
    nav = "" if home_href is None else f'<a class="home" href="{home_href}">← 返回首页</a>'
    hist_html = ""
    if history:
        links = "".join(
            f'<li><a href="{digest_href(d)}">{d}</a></li>' for d in history[:60]
        )
        hist_html = f'<aside class="history"><h2>历史简报</h2><ol>{links}</ol></aside>'
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<header class="site-head">
  <div class="brand">AI 速览</div>
  <div class="tag">每日自动汇总 · YouTube · 新闻 · Newsletter · 人物动态</div>
</header>
<main>
  {nav}
  <h1 class="page-title">{html.escape(title)}</h1>
  <div class="layout">
    <div class="content">{body}</div>
    {hist_html}
  </div>
</main>
<footer class="site-foot">由 AI Digest 自动生成 · 信源配置见仓库 config.yaml</footer>
</body>
</html>"""


def build(items: list[dict], cfg: dict, intro: str, date_str: str) -> None:
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    top_n = cfg.get("digest", {}).get("top_n", 8)
    body = _digest_body(items, cfg, intro, top_n)

    # 当日页（在 docs/digests/ 下，历史链接同目录、首页在上一级）
    dates_now = sorted({p.stem for p in DIGEST_DIR.glob("*.html")} | {date_str}, reverse=True)
    page = _page(
        f"AI 速览 · {date_str}",
        body,
        home_href="../index.html",
        history=dates_now,
        digest_href=lambda d: f"{d}.html",
    )
    (DIGEST_DIR / f"{date_str}.html").write_text(page, encoding="utf-8")

    # 首页：展示最新一期 + 历史（链接在 digests/ 子目录）
    index = _page(
        f"AI 速览 · {date_str}",
        body,
        home_href=None,
        history=dates_now,
        digest_href=lambda d: f"digests/{d}.html",
    )
    (DOCS / "index.html").write_text(index, encoding="utf-8")
    print(f"[site] 已生成 docs/index.html 与 docs/digests/{date_str}.html")


_CSS = """
:root{
  --bg:#f6f8f5; --surface:rgba(255,255,255,.88); --ink:#14171a; --muted:#626a73;
  --accent:#2563eb; --signal:#00a99d; --warm:#b87913; --accent-soft:#eaf2ff; --line:#dfe7e2;
  --radius:10px; --shadow:0 1px 2px rgba(16,24,32,.04),0 14px 38px rgba(16,24,32,.08);
  --maxw:1040px;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:-apple-system,"PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;
  line-height:1.65;-webkit-font-smoothing:antialiased;
  background-image:
    linear-gradient(rgba(37,99,235,.07) 1px,transparent 1px),
    linear-gradient(90deg,rgba(0,169,157,.06) 1px,transparent 1px);
  background-size:34px 34px}
.site-head{position:relative;overflow:hidden;padding:34px 24px 26px;border-bottom:1px solid var(--line);
  background:linear-gradient(180deg,rgba(255,255,255,.96),rgba(248,251,249,.88))}
.site-head::before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.55;
  background:
    repeating-linear-gradient(90deg,transparent 0 24px,rgba(37,99,235,.08) 24px 25px),
    repeating-linear-gradient(0deg,transparent 0 24px,rgba(0,169,157,.06) 24px 25px);
  mask-image:linear-gradient(90deg,#000,transparent 68%)}
.site-head .brand{position:relative;font-size:1.9rem;font-weight:850;letter-spacing:0}
.site-head .brand::before{content:"";display:inline-block;width:9px;height:9px;margin-right:10px;border-radius:50%;
  background:var(--signal);box-shadow:0 0 0 5px rgba(0,169,157,.12),0 0 22px rgba(0,169,157,.45);vertical-align:middle}
.site-head .tag{position:relative;color:var(--muted);font-size:.86rem;margin-top:4px}
main{max-width:var(--maxw);margin:0 auto;padding:28px 24px 60px}
.home{display:inline-block;color:var(--accent);text-decoration:none;font-size:.9rem;margin-bottom:8px}
.home:hover{text-decoration:underline}
.page-title{font-size:1.5rem;font-weight:850;letter-spacing:0;margin:.2em 0 1em}
.layout{display:grid;grid-template-columns:1fr 220px;gap:34px;align-items:start}
@media(max-width:760px){.layout{grid-template-columns:1fr}}
h2{font-size:1.05rem;font-weight:850;color:var(--accent);margin:1.8em 0 .8em;
  text-transform:none;letter-spacing:.01em}
section:first-child h2{margin-top:0}
.overview{background:rgba(234,242,255,.86);border:1px solid #cfe0ff;border-radius:var(--radius);padding:6px 22px 14px;
  box-shadow:inset 3px 0 0 var(--accent)}
.overview--muted{background:#f4f3f0;border-color:var(--line)}
.overview h2{color:var(--accent)}
.overview ul{margin:0;padding-left:18px}
.overview li{margin:6px 0;font-weight:600}
.overview p{margin:0;color:var(--muted)}
.card{position:relative;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:16px 18px;margin:12px 0;box-shadow:var(--shadow);backdrop-filter:blur(12px);
  transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease}
.card::before{content:"";position:absolute;left:-1px;top:14px;bottom:14px;width:3px;border-radius:3px;background:var(--signal);opacity:.68}
.card:hover{transform:translateY(-2px);border-color:#b9d7d2;box-shadow:0 4px 10px rgba(16,24,32,.08),0 18px 44px rgba(16,24,32,.12)}
.card--compact{padding:11px 16px;box-shadow:none}
.card--compact::before{top:12px;bottom:12px;background:#a5b4fc;opacity:.55}
.card--compact .summary{font-size:.9rem;color:var(--muted)}
.card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:7px}
.meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:7px}
.card-head .meta{margin-bottom:0}
.badge{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-weight:850;font-size:.78rem;
  padding:1px 9px;border-radius:999px;color:#fff;min-width:30px;text-align:center}
.s-high{background:var(--accent)}.s-mid{background:var(--signal)}.s-ok{background:var(--warm)}.s-low{background:#8f969d}
.chip{font-size:.74rem;padding:1px 9px;border-radius:999px;border:1px solid var(--line);color:var(--muted);background:rgba(255,255,255,.66)}
.chip--topic{background:#f2f5f2;color:#4b5563}
.chip--quality{background:#e9f8f5;color:#087a72;border-color:#bde6df}
.chip--domain{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.title{font-size:1.06rem;font-weight:760;margin:.1em 0 .35em;line-height:1.4}
.card--compact .title{font-size:.96rem;margin-bottom:.2em}
.title a{color:var(--ink);text-decoration:none;background-image:linear-gradient(var(--accent),var(--accent));
  background-size:0 2px;background-repeat:no-repeat;background-position:0 100%;transition:background-size .2s}
.title a:hover{background-size:100% 2px;color:var(--accent)}
.summary{margin:0;color:#333}
.reason,.qa{margin:.45em 0 0;color:var(--muted);font-size:.88rem}
.reason strong,.qa strong{color:#444}
.qa{border-left:3px solid #f1dfb2;padding-left:10px;background:rgba(255,248,232,.52)}
.topic-h{font-size:.82rem;font-weight:700;color:var(--muted);margin:1.4em 0 .2em;
  text-transform:uppercase;letter-spacing:.08em}
.history{position:sticky;top:20px;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius);padding:6px 18px 14px;backdrop-filter:blur(12px)}
.history h2{font-size:.82rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.history ol{list-style:none;margin:0;padding:0}
.history li{margin:4px 0}
.history a{color:var(--ink);text-decoration:none;font-size:.9rem;font-variant-numeric:tabular-nums;
  font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.history a:hover{color:var(--accent)}
.site-foot{max-width:var(--maxw);margin:0 auto;padding:24px;color:var(--muted);
  font-size:.8rem;border-top:1px solid var(--line)}
@media(max-width:520px){
  main{padding:22px 16px 52px}
  .site-head{padding:28px 16px 22px}
  .card{padding:14px}
  .card-head{display:block}
  .badge{display:inline-block;margin-top:7px}
}
"""
