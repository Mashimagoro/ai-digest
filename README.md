# 今日重要信号

每天自动抓取高质量 RSS + 网页新闻补源，用 Gemini 筛选成跨领域中文简报，并同步生成网页和邮件。AI 是固定板块，其它板块按当天重要性浮动。

```
抓取 (RSS/Atom + Tavily 补源) → AI 富化 (中文摘要+五板块分类) → 生成 Markdown → 更新网页 → 发邮件
```

## 5 分钟上手

### 1. 准备密钥
- **Gemini API key（免费）**：https://aistudio.google.com/apikey
- **QQ 邮箱授权码**：QQ 邮箱 → 设置 → 账号 → 开启「IMAP/SMTP 服务」→ 生成授权码（不是登录密码）

### 2. 本地试跑
```bash
cd ai-digest
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # 填入你的 key 和邮箱
python main.py
```
跑完会发邮件，同时在 `state/digests/<日期>.md` 留一份本地副本。

> 不填 `GEMINI_API_KEY` 也能跑（跳过 AI，只列原始条目）；不填 `SMTP_*` 则只生成本地文件、不发信。便于先验证抓取是否正常。

### 3. 上 GitHub Actions（定时自动跑）
1. 把项目推到一个 GitHub 仓库（公共仓库 Actions 免费）。
2. 仓库 → Settings → Secrets and variables → Actions，添加 4 个 secret：
   `GEMINI_API_KEY`、`SMTP_USER`、`SMTP_PASS`、`MAIL_TO`。
3. 默认每天北京时间 08:00 自动发；也可在 Actions 页面点 **Run workflow** 手动触发一次测试。

## 改信源

全部在 `config.yaml`，不用动代码：

- **加固定 RSS 源**：在 `rss:` 下加 `name`、`url`、`section`，必要时加 `max_items`。
- **加搜索补源**：在 `tavily.queries:` 下加 `query`、`section`、`source`。
- **改板块排版**：调 `digest.sections`。
- **过滤/筛选方向**：调 `filters` 和 `ai.priorities`。
- **改频率**：编辑 `.github/workflows/digest.yml` 里的 `cron`。

## 当前板块

- AI：每天保留。
- 宏观/政策：有重要变化才上。
- 商业/科技：优先选产业变化。
- 国际/社会：只选有长期影响的。
- 消费/生活：偶尔补充，更接地气。
