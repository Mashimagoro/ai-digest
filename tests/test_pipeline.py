"""单元测试：信源质检、可信度合并、关键词过滤、标题近重复去重、今日要点。

这些都是纯函数逻辑，最容易在改 config.yaml 或调参时被悄悄改坏，值得有测试兜底。
运行：pytest -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai.quality import _merged_credibility, apply_quality_gate, classify_source
from ai.digest import _first_sentence, build_markdown, dedupe_similar, overview, sectionize
from deliver.site import _digest_body
from main import _title_ok, passes_filters, source_filter


# ---- classify_source：信源分级 ----

def test_classify_official_domain():
    assert classify_source({"url": "https://openai.com/blog/x"}, {})["source_tier"] == "official"


def test_classify_official_subdomain():
    assert classify_source({"url": "https://www.openai.com/index/x"}, {})["source_tier"] == "official"


def test_classify_high_confidence():
    assert classify_source({"url": "https://www.theverge.com/a"}, {})["source_tier"] == "high"


def test_classify_research_counts_as_high():
    assert classify_source({"url": "https://arxiv.org/abs/2401.00001"}, {})["source_tier"] == "high"


def test_classify_low_confidence():
    assert classify_source({"url": "https://www.yahoo.com/news/a"}, {})["source_tier"] == "low"


def test_classify_unknown_is_normal():
    assert classify_source({"url": "https://example.com/a"}, {})["source_tier"] == "normal"


# ---- apply_quality_gate：分数封顶 ----

def test_low_source_caps_high_score():
    out = apply_quality_gate({"url": "https://yahoo.com/x", "ai_score": 95}, {})
    assert out["ai_score"] == 79
    assert any("封顶" in n for n in out["qa_notes"])


def test_official_high_score_not_capped():
    out = apply_quality_gate({"url": "https://openai.com/x", "ai_score": 95}, {})
    assert out["ai_score"] == 95
    assert not out.get("qa_notes")


def test_normal_source_90_capped_and_flagged():
    out = apply_quality_gate({"url": "https://example.com/x", "ai_score": 90}, {})
    assert out["ai_score"] == 89
    assert any("90+" in n for n in out["qa_notes"])


def test_gate_disabled_passthrough():
    out = apply_quality_gate(
        {"url": "https://yahoo.com/x", "ai_score": 95},
        {"quality_gates": {"enabled": False}},
    )
    assert out["ai_score"] == 95


# ---- _merged_credibility：取更保守的一档 ----

def test_merged_credibility_takes_conservative():
    assert _merged_credibility("待核", "高") == "待核"
    assert _merged_credibility("高", "中") == "中"
    assert _merged_credibility("中", "待核") == "待核"


def test_merged_credibility_unknown_model_uses_source():
    assert _merged_credibility("", "高") == "高"


# ---- 关键词过滤 ----

def test_title_block_hit():
    assert _title_ok("New crypto trading bot", ["crypto"], []) is False


def test_title_allows_when_no_block_hit():
    assert _title_ok("OpenAI releases model", ["crypto"], []) is True


def test_title_require_not_met():
    assert _title_ok("Local weather report", [], ["ai", "llm"]) is False


def test_title_require_met():
    assert _title_ok("New AI model", [], ["ai"]) is True


def test_passes_filters_reads_config_keys():
    filters = {"blocked_keywords": ["crypto"], "required_keywords": []}
    assert passes_filters("crypto pump incoming", filters) is False
    assert passes_filters("AI lab ships model", filters) is True


def test_source_filter_require():
    items = [{"title": "AI breakthrough"}, {"title": "Sports recap"}]
    out = source_filter(items, {"require_keywords": ["ai"]})
    assert [i["title"] for i in out] == ["AI breakthrough"]


def test_source_filter_noop_without_rules():
    items = [{"title": "anything"}]
    assert source_filter(items, {}) == items


# ---- dedupe_similar：标题近重复兜底 ----

def test_dedupe_similar_merges_near_identical_keep_high_score():
    items = [
        {"title": "OpenAI releases GPT-5.5 with major reasoning gains", "ai_score": 80},
        {"title": "OpenAI releases GPT-5.5 with major reasoning improvements", "ai_score": 60},
    ]
    out = dedupe_similar(items)
    assert len(out) == 1
    assert out[0]["ai_score"] == 80


def test_dedupe_similar_keeps_distinct_stories():
    items = [
        {"title": "AI & Tech Brief: Tech CEOs blocked executive order", "ai_score": 50},
        {"title": "AI & Tech Brief: White House AI order now postponed", "ai_score": 50},
    ]
    assert len(dedupe_similar(items)) == 2


def test_dedupe_similar_cjk():
    items = [
        {"title": "谷歌发布全新大模型 Gemini", "ai_score": 70},
        {"title": "谷歌发布全新大模型 Gemini Pro", "ai_score": 60},
    ]
    out = dedupe_similar(items)
    assert len(out) == 1
    assert out[0]["ai_score"] == 70


# ---- overview / _first_sentence：今日要点（不再调用模型） ----

def test_first_sentence():
    assert _first_sentence("这是要点一。后面还有。") == "这是要点一。"
    assert _first_sentence("No punctuation here") == "No punctuation here"


def test_overview_from_scores():
    items = [
        {"ai_score": 90, "ai_summary": "要点一说明。补充。"},
        {"ai_score": 80, "ai_summary": "要点二。"},
    ]
    assert overview(items, {}) == "- 要点一说明。\n- 要点二。"


def test_overview_disabled():
    items = [{"ai_score": 90, "ai_summary": "x。"}]
    assert overview(items, {"digest": {"write_overview": False}}) == ""


# ---- 新版每日重要信号：五板块排版 ----

def _section_cfg():
    return {
        "digest": {
            "subject_prefix": "今日重要信号",
            "sections": [
                {"label": "AI", "note": "每天保留", "max_items": 1},
                {"label": "宏观/政策", "note": "有重要变化才上", "max_items": 1},
                {"label": "商业/科技", "note": "优先选产业变化", "max_items": 1},
                {"label": "国际/社会", "note": "只选有长期影响的", "max_items": 1},
                {"label": "消费/生活", "note": "偶尔补充，更接地气", "max_items": 1},
            ],
        }
    }


def test_sectionize_orders_by_editorial_sections_and_caps_each_section():
    items = [
        {"title": "商业二", "ai_topic": "商业/科技", "ai_score": 70},
        {"title": "AI 一", "ai_topic": "AI", "ai_score": 80},
        {"title": "AI 二", "ai_topic": "AI", "ai_score": 75},
        {"title": "宏观一", "ai_topic": "宏观/政策", "ai_score": 90},
        {"title": "商业一", "ai_topic": "商业/科技", "ai_score": 92},
        {"title": "国际一", "ai_topic": "国际/社会", "ai_score": 77},
    ]

    sections = sectionize(items, _section_cfg())

    assert [(s["label"], [it["title"] for it in s["items"]]) for s in sections] == [
        ("AI", ["AI 一"]),
        ("宏观/政策", ["宏观一"]),
        ("商业/科技", ["商业一"]),
        ("国际/社会", ["国际一"]),
    ]


def test_sectionize_does_not_emit_empty_optional_sections():
    sections = sectionize(
        [{"title": "AI 一", "ai_topic": "AI", "ai_score": 80}],
        _section_cfg(),
    )

    assert [s["label"] for s in sections] == ["AI"]


def test_build_markdown_uses_signal_brief_sections_instead_of_old_ranked_list():
    body = build_markdown(
        [
            {
                "title": "AI 一",
                "url": "https://example.com/ai",
                "source": "Example",
                "ai_topic": "AI",
                "ai_score": 80,
                "ai_summary": "AI 事件说明。",
                "ai_reason": "影响工具使用方式",
            },
            {
                "title": "宏观一",
                "url": "https://example.com/macro",
                "source": "Example",
                "ai_topic": "宏观/政策",
                "ai_score": 90,
                "ai_summary": "宏观事件说明。",
                "ai_reason": "影响市场预期",
            },
        ],
        _section_cfg(),
        intro="- 今日判断。",
    )

    assert body.startswith("# 今日重要信号 · ")
    assert "## AI｜每天保留" in body
    assert "## 宏观/政策｜有重要变化才上" in body
    assert "## 重点条目" not in body


def test_site_digest_body_renders_signal_sections():
    body = _digest_body(
        [
            {
                "title": "AI 一",
                "url": "https://example.com/ai",
                "source": "Example",
                "ai_topic": "AI",
                "ai_score": 80,
                "ai_summary": "AI 事件说明。",
            }
        ],
        _section_cfg(),
        "",
        top_n=5,
    )

    assert "<h2>AI｜每天保留</h2>" in body
    assert "重点条目" not in body
