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
    topic = html.escape(it.get("ai_topic", "其它"))
    summary = html.escape(it.get("ai_summary", ""))
    cls = "card card--compact" if compact else "card"
    return f"""<article class="{cls}">
  <div class="meta">
    <span class="badge {_score_class(score)}">{score}</span>
    <span class="chip chip--src">{source}</span>
    <span class="chip chip--topic">{topic}</span>
  </div>
  <h3 class="title"><a href="{url}" target="_blank" rel="noopener">{title}</a></h3>
  <p class="summary">{summary}</p>
</article>"""


def _digest_body(items: list[dict], cfg: dict, intro: str, top_n: int) -> str:
    ranked = sorted(items, key=lambda x: x.get("ai_score", 0), reverse=True)
    parts: list[str] = []

    if intro:
        bullets = "".join(f"<li>{html.escape(line.lstrip('- ').strip())}</li>" for line in intro.splitlines() if line.strip())
        parts.append(f'<section class="overview"><h2>今日要点</h2><ul>{bullets}</ul></section>')

    parts.append('<section><h2>重点条目</h2>')
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
  --bg:#faf9f7; --surface:#ffffff; --ink:#1a1a1c; --muted:#6b6b73;
  --accent:#4f46e5; --accent-soft:#eef0ff; --line:#e7e5e1;
  --radius:14px; --shadow:0 1px 2px rgba(20,20,40,.04),0 8px 24px rgba(20,20,40,.06);
  --maxw:980px;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
  font-family:-apple-system,"PingFang SC","Microsoft YaHei",Segoe UI,sans-serif;
  line-height:1.65;-webkit-font-smoothing:antialiased}
.site-head{padding:34px 24px 26px;border-bottom:1px solid var(--line);background:var(--surface)}
.site-head .brand{font-size:1.9rem;font-weight:800;letter-spacing:-.02em}
.site-head .tag{color:var(--muted);font-size:.86rem;margin-top:4px}
main{max-width:var(--maxw);margin:0 auto;padding:28px 24px 60px}
.home{display:inline-block;color:var(--accent);text-decoration:none;font-size:.9rem;margin-bottom:8px}
.home:hover{text-decoration:underline}
.page-title{font-size:1.5rem;font-weight:800;letter-spacing:-.02em;margin:.2em 0 1em}
.layout{display:grid;grid-template-columns:1fr 220px;gap:34px;align-items:start}
@media(max-width:760px){.layout{grid-template-columns:1fr}}
h2{font-size:1.05rem;font-weight:800;color:var(--accent);margin:1.8em 0 .8em;
  text-transform:none;letter-spacing:.01em}
section:first-child h2{margin-top:0}
.overview{background:var(--accent-soft);border:1px solid #dfe2ff;border-radius:var(--radius);padding:6px 22px 14px}
.overview h2{color:var(--accent)}
.overview ul{margin:0;padding-left:18px}
.overview li{margin:6px 0;font-weight:600}
.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);
  padding:16px 18px;margin:12px 0;box-shadow:var(--shadow);transition:transform .15s ease,box-shadow .15s ease}
.card:hover{transform:translateY(-2px);box-shadow:0 4px 8px rgba(20,20,40,.06),0 16px 36px rgba(20,20,40,.10)}
.card--compact{padding:11px 16px;box-shadow:none}
.card--compact .summary{font-size:.9rem;color:var(--muted)}
.meta{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:7px}
.badge{font-weight:800;font-size:.78rem;padding:1px 9px;border-radius:999px;color:#fff;min-width:30px;text-align:center}
.s-high{background:var(--accent)}.s-mid{background:#0ea5a0}.s-ok{background:#c08a2d}.s-low{background:#a3a3ac}
.chip{font-size:.74rem;padding:1px 9px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.chip--topic{background:#f4f3f0}
.title{font-size:1.06rem;font-weight:700;margin:.1em 0 .35em;line-height:1.4}
.card--compact .title{font-size:.98rem}
.title a{color:var(--ink);text-decoration:none;background-image:linear-gradient(var(--accent),var(--accent));
  background-size:0 2px;background-repeat:no-repeat;background-position:0 100%;transition:background-size .2s}
.title a:hover{background-size:100% 2px;color:var(--accent)}
.summary{margin:0;color:#333}
.topic-h{font-size:.82rem;font-weight:700;color:var(--muted);margin:1.4em 0 .2em;
  text-transform:uppercase;letter-spacing:.06em}
.history{position:sticky;top:20px;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--radius);padding:6px 18px 14px}
.history h2{font-size:.82rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.history ol{list-style:none;margin:0;padding:0}
.history li{margin:4px 0}
.history a{color:var(--ink);text-decoration:none;font-size:.9rem;font-variant-numeric:tabular-nums}
.history a:hover{color:var(--accent)}
.site-foot{max-width:var(--maxw);margin:0 auto;padding:24px;color:var(--muted);
  font-size:.8rem;border-top:1px solid var(--line)}
"""
