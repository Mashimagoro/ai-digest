# AI Digest

每天自动抓取 YouTube 频道 + AI 新闻/Newsletter，用 Gemini（免费）写中文摘要并按重要性排序，发一封简报到你的邮箱。跑在 GitHub Actions 上，**全程免费**。

```
抓取 (RSS/Atom) → AI 富化 (中文摘要+打分+分类) → 生成 Markdown → 发邮件
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
1. 把 `ai-digest/` 推到一个 GitHub 仓库（公共仓库 Actions 免费）。
2. 仓库 → Settings → Secrets and variables → Actions，添加 4 个 secret：
   `GEMINI_API_KEY`、`SMTP_USER`、`SMTP_PASS`、`MAIL_TO`。
3. 默认每天北京时间 08:00 自动发；也可在 Actions 页面点 **Run workflow** 手动触发一次测试。

## 改信源

全部在 `config.yaml`，不用动代码：

- **加新闻/Newsletter**：在 `rss:` 下加 `name` + `url`（feed 地址）。
- **加 YouTube 频道**：在 `youtube:` 下加 `name` + `channel_id`。
  拿频道 ID：打开频道主页 → 查看网页源代码 → 搜 `channelId`，形如 `UCxxxxxxxxxxxxxxxxxxxxxx`。
- **过滤/打分方向**：调 `filters` 和 `ai.priorities`。
- **改频率**：编辑 `.github/workflows/digest.yml` 里的 `cron`。

## 当前内置信源

YouTube：Andrej Karpathy、Two Minute Papers、Yannic Kilcher、AI Explained、ML Street Talk、Lex Fridman
新闻/博客：Import AI、Ahead of AI、Simon Willison、The Verge AI、Ars Technica AI、MIT Tech Review AI
