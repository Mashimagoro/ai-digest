"""通过 SMTP 发送简报邮件（纯文本 + HTML）。默认 QQ 邮箱 SSL。"""
from __future__ import annotations

import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import markdown as md


def send(subject: str, markdown_body: str, cfg: dict) -> None:
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS", "")
    mail_to = os.environ.get("MAIL_TO", "") or user

    if not (user and password and mail_to):
        raise RuntimeError("缺少 SMTP_USER / SMTP_PASS / MAIL_TO 环境变量")

    host = cfg.get("mail", {}).get("smtp_host", "smtp.qq.com")
    port = int(cfg.get("mail", {}).get("smtp_port", 465))

    html_body = _html(md.markdown(markdown_body, extensions=["extra"]))

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = mail_to
    msg.attach(MIMEText(markdown_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
            server.login(user, password)
            server.sendmail(user, [mail_to], msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls(context=context)
            server.login(user, password)
            server.sendmail(user, [mail_to], msg.as_string())

    print(f"[mail] 已发送至 {mail_to}")


def _html(inner: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
         line-height: 1.7; color: #1a1a1a; max-width: 720px; margin: 0 auto; padding: 24px; }}
  h1 {{ font-size: 1.6rem; border-bottom: 2px solid #4f46e5; padding-bottom: 8px; }}
  h2 {{ font-size: 1.2rem; margin-top: 2rem; color: #4f46e5; }}
  h3 {{ font-size: 1.05rem; margin-bottom: 4px; }}
  a {{ color: #4f46e5; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  code {{ background: #eef; color: #4f46e5; padding: 1px 6px; border-radius: 4px; font-size: 0.85em; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 2rem 0; }}
  li {{ margin: 6px 0; }}
</style></head><body>{inner}</body></html>"""
