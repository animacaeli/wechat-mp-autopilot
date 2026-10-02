"""定时写作调度：进程内每日触发，容器常驻场景无需宿主 cron。

保持零依赖（不引 apscheduler/croniter）：只支持"每日 HH:MM"这一种节奏——
公众号本就以日更为主流，简单意味着可预测。
"""

from __future__ import annotations

import datetime as dt


def parse_daily(value: str) -> tuple[int, int]:
    """解析 "HH:MM"；不合法抛 ValueError（argparse 转成友好报错）。"""
    hh, _, mm = value.strip().partition(":")
    if not (hh.isdigit() and mm.isdigit()):
        raise ValueError(f"--daily 需要 HH:MM 格式，当前为 {value!r}")
    hour, minute = int(hh), int(mm)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"时间越界：{value!r}")
    return hour, minute


def seconds_until_next(now: dt.datetime, hour: int, minute: int) -> float:
    """距下一次触发点的秒数；今天已过则顺延到明天。"""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return (target - now).total_seconds()


def pick_direction(pool: list[str], day: dt.date) -> str | None:
    """按日期从方向池轮换取选题方向，保证相邻两天不重复（池够长时）。"""
    if not pool:
        return None
    return pool[day.toordinal() % len(pool)]
