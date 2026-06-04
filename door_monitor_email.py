"""Send the previous day's door-monitor backup summary by email."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from deliver import email as mailer
from main import load_config


ROOT = Path(__file__).parent
STATS_PATH = ROOT / "state" / "door_monitor_stats.json"
TZ = ZoneInfo("Asia/Shanghai")


def target_date() -> str:
    return (datetime.now(TZ).date() - timedelta(days=1)).isoformat()


def load_stats(day: str) -> tuple[dict | None, str | None]:
    if not STATS_PATH.exists():
        return None, None
    data = json.loads(STATS_PATH.read_text(encoding="utf-8"))
    days = data.get("days", {})
    if day not in days:
        latest = sorted(days)[-1] if days else None
        return None, latest
    return days[day], day


def build_markdown(day: str, stats: dict | None, latest_day: str | None = None) -> str:
    if stats is None:
        latest = f"最近一次统计是 {latest_day}。" if latest_day else "目前仓库里没有任何监控统计。"
        return "\n".join(
            [
                f"# 门口监控备份 · {day}",
                "",
                "没有收到前一天的门口监控统计。",
                "",
                f"{latest}",
                "",
                "请检查家里这台电脑的监控录像、极空间同步，以及 00:50 的统计推送任务。",
                "",
                "---",
                "",
                "这封邮件只汇报监控备份状态，不更新 AI 资讯网页。",
            ]
        )

    stored = int(stats.get("stored") or 0)
    synced = int(stats.get("synced") or 0)
    local_present = int(stats.get("local_present") or 0)
    deleted_local = int(stats.get("deleted_local") or 0)
    diff = max(stored - synced, 0)
    status = "同步正常" if diff == 0 else f"还有 {diff} 段未确认同步"

    return "\n".join(
        [
            f"# 门口监控备份 · {day}",
            "",
            f"- 前一天保存：**{stored}** 段",
            f"- 同步成功：**{synced}** 段",
            f"- 本地仍保留：**{local_present}** 段",
            f"- 已清理本地：**{deleted_local}** 段",
            "",
            f"状态：**{status}**",
            "",
            "---",
            "",
            "这封邮件只汇报监控备份状态，不更新 AI 资讯网页。",
        ]
    )


def main() -> int:
    load_dotenv()
    cfg = load_config()
    day = target_date()
    stats, latest_day = load_stats(day)
    subject = f"门口监控备份 · {day}"
    mailer.send(subject, build_markdown(day, stats, latest_day), cfg)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"发送门口监控备份邮件失败: {exc}", file=sys.stderr)
        raise
