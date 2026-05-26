"""Source quality rules and score gates for AI Digest."""
from __future__ import annotations

from urllib.parse import urlparse


DEFAULT_SOURCE_QUALITY = {
    "official_domains": [
        "anthropic.com",
        "blog.google",
        "deepmind.google",
        "github.blog",
        "googleblog.com",
        "huggingface.co",
        "microsoft.com",
        "mistral.ai",
        "openai.com",
    ],
    "high_confidence_domains": [
        "apnews.com",
        "arstechnica.com",
        "axios.com",
        "bloomberg.com",
        "businessinsider.com",
        "cnbc.com",
        "ft.com",
        "nature.com",
        "nytimes.com",
        "politico.com",
        "reuters.com",
        "science.org",
        "semafor.com",
        "simonwillison.net",
        "techcrunch.com",
        "technologyreview.com",
        "techmeme.com",
        "theinformation.com",
        "theregister.com",
        "theverge.com",
        "venturebeat.com",
        "washingtonpost.com",
        "wired.com",
        "wsj.com",
    ],
    "research_domains": [
        "arxiv.org",
        "openreview.net",
        "papers.ssrn.com",
    ],
    "low_confidence_domains": [
        "economictimes.indiatimes.com",
        "geeky-gadgets.com",
        "huffpost.com",
        "letsdatascience.com",
        "mlq.ai",
        "nypost.com",
        "thesunchronicle.com",
        "yahoo.com",
    ],
    "score_caps": {
        "official": 100,
        "high": 96,
        "normal": 89,
        "low": 79,
    },
}

TIER_LABELS = {
    "official": "官方/一手",
    "high": "高可信",
    "normal": "普通来源",
    "low": "低置信/转载",
}

CREDIBILITY_LABELS = {
    "official": "高",
    "high": "高",
    "normal": "中",
    "low": "待核",
}


def domain_from_url(url: str) -> str:
    host = urlparse(url or "").netloc.lower().split("@")[-1].split(":")[0]
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host


def _rules(cfg: dict) -> dict:
    user_rules = cfg.get("source_quality", {}) or {}
    merged = {
        key: list(value) if isinstance(value, list) else dict(value)
        for key, value in DEFAULT_SOURCE_QUALITY.items()
    }
    for key, value in user_rules.items():
        if isinstance(value, list):
            merged[key] = value
        elif isinstance(value, dict):
            base = merged.get(key, {})
            if isinstance(base, dict):
                base.update(value)
                merged[key] = base
            else:
                merged[key] = value
        else:
            merged[key] = value
    return merged


def _matches(domain: str, candidates: list[str]) -> bool:
    return any(domain == c or domain.endswith(f".{c}") for c in candidates)


def classify_source(item: dict, cfg: dict) -> dict:
    rules = _rules(cfg)
    domain = item.get("source_domain") or domain_from_url(item.get("url", ""))
    if _matches(domain, rules.get("official_domains", [])):
        tier = "official"
    elif _matches(domain, rules.get("high_confidence_domains", [])) or _matches(
        domain, rules.get("research_domains", [])
    ):
        tier = "high"
    elif _matches(domain, rules.get("low_confidence_domains", [])):
        tier = "low"
    else:
        tier = "normal"
    return {
        "source_domain": domain,
        "source_tier": tier,
        "source_tier_label": TIER_LABELS[tier],
        "source_credibility": CREDIBILITY_LABELS[tier],
    }


def apply_quality_gate(item: dict, cfg: dict) -> dict:
    """Attach source quality metadata and cap scores that lack source support."""
    enriched = {**item, **classify_source(item, cfg)}
    enriched["ai_credibility"] = _merged_credibility(
        str(enriched.get("ai_credibility", "") or ""),
        enriched["source_credibility"],
    )
    gates = cfg.get("quality_gates", {}) or {}
    if gates.get("enabled", True) is False:
        return enriched

    caps = _rules(cfg).get("score_caps", {})
    tier = enriched["source_tier"]
    cap = int(caps.get(tier, 100))
    score = int(enriched.get("ai_score", 0) or 0)
    notes = list(enriched.get("qa_notes", []) or [])

    if score > cap:
        enriched["ai_score"] = cap
        notes.append(f"来源等级为“{enriched['source_tier_label']}”，高分封顶为 {cap}")

    if score >= 90 and tier not in {"official", "high"}:
        notes.append("90+ 条目需要官方、主流媒体、研究原文或多源交叉验证")

    if notes:
        enriched["qa_notes"] = notes
    return enriched


def _merged_credibility(model_label: str, source_label: str) -> str:
    order = {"待核": 0, "中": 1, "高": 2}
    if model_label not in order:
        return source_label
    model_rank = order[model_label]
    source_rank = order.get(source_label, model_rank)
    rank = min(model_rank, source_rank)
    return next(label for label, value in order.items() if value == rank)
