"""Send the previous day's door-monitor backup summary by email."""
from __future__ import annotations

import json
import os
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
    alert = os.environ.get("DOOR_MONITOR_ALERT", "daily")
    alerts = {
        "fallback": (
            "监控提醒：已切换本地录像",
            "极空间录制未能继续，Mac mini 已启用本地录像。极空间恢复后会重新优先写入 NAS，"
            "本地录像会经现有同步任务备份。",
        ),
        "restored": (
            "监控提醒：极空间录像已恢复",
            "Mac mini 已恢复优先写入极空间。故障期间的本地录像仍会由同步任务补传。",
        ),
        "local_low": (
            "监控紧急提醒：本地空间不足",
            "极空间录制不可用，Mac mini 本地剩余空间低于安全阈值。录像可能暂停，请检查设备。",
        ),
        "test": (
            "监控提醒：邮件通道测试",
            "监控故障邮件通道测试成功。",
        ),
    }
    if alert in alerts:
        subject, body = alerts[alert]
        mailer.send(subject, body, cfg)
        return 0
    if alert != "daily":
        raise ValueError(f"Unsupported door monitor alert: {alert}")
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
