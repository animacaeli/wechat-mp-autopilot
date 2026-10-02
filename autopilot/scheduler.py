"""定时写作调度：进程内 cron 触发，容器常驻场景无需宿主 cron。

保持零依赖（不引 croniter/apscheduler）：实现标准 5 字段 cron 的常用子集
（`*`、`*/n`、`a`、`a-b`、`a-b/n`、逗号列表；星期 0 和 7 均为周日），
公众号日更场景足够，简单意味着可预测。
"""

from __future__ import annotations

import datetime as dt
from typing import ClassVar


class Cron:
    """5 字段 cron：分 时 日 月 周（标准 vixie 语义：日与周都受限时取并集）。"""

    RANGES: ClassVar[dict[str, tuple[int, int]]] = {
        "minute": (0, 59),
        "hour": (0, 23),
        "dom": (1, 31),
        "month": (1, 12),
        "dow": (0, 7),
    }

    def __init__(self, expr: str):
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError(f"cron 需要 5 个字段（分 时 日 月 周），当前 {expr!r} 有 {len(parts)} 个")
        self.expr = expr
        self.fields = {name: self._parse_field(part, name) for name, part in zip(self.RANGES, parts, strict=True)}
        self.fields["dow"] = {0 if v == 7 else v for v in self.fields["dow"]}

    @classmethod
    def _parse_field(cls, part: str, name: str) -> set[int]:
        lo, hi = cls.RANGES[name]
        allowed: set[int] = set()
        for piece in part.split(","):
            piece = piece.strip()
            if not piece:
                raise ValueError(f"cron {name} 字段存在空片段：{part!r}")
            step = 1
            if "/" in piece:
                base, _, step_s = piece.partition("/")
                if not step_s.isdigit() or int(step_s) == 0:
                    raise ValueError(f"cron {name} 步长非法：{piece!r}")
                step = int(step_s)
            else:
                base = piece
            if base == "*":
                start, end = lo, hi
            elif base.isdigit():
                start = end = int(base)
                if not lo <= start <= hi:
                    raise ValueError(f"cron {name} 值越界：{base}（应在 {lo}-{hi}）")
            elif "-" in base:
                a, _, b = base.partition("-")
                if not (a.isdigit() and b.isdigit()):
                    raise ValueError(f"cron {name} 范围非法：{base!r}")
                start, end = int(a), int(b)
                if not (lo <= start <= hi and lo <= end <= hi):
                    raise ValueError(f"cron {name} 范围越界：{base}（应在 {lo}-{hi}）")
            else:
                raise ValueError(f"cron {name} 字段非法：{piece!r}")
            allowed.update(range(start, end + 1, step))
        if not allowed:
            raise ValueError(f"cron {name} 字段无有效值：{part!r}")
        return allowed

    def _day_matches(self, t: dt.datetime) -> bool:
        dom_ok = t.day in self.fields["dom"]
        dow_ok = ((t.weekday() + 1) % 7) in self.fields["dow"]  # 周一=1…周日=0
        dom_all = len(self.fields["dom"]) == 31
        dow_all = len(self.fields["dow"]) == 7
        # vixie cron 语义：日与周都受限时取并集（任一命中即触发）
        if not dom_all and not dow_all:
            return dom_ok or dow_ok
        return dom_ok and dow_ok

    def matches(self, t: dt.datetime) -> bool:
        return (
            t.minute in self.fields["minute"]
            and t.hour in self.fields["hour"]
            and t.month in self.fields["month"]
            and self._day_matches(t)
        )

    def next_after(self, now: dt.datetime) -> dt.datetime:
        """下一个触发时刻（逐分钟扫描，上限 400 天防死循环）。"""
        t = (now + dt.timedelta(minutes=1)).replace(second=0, microsecond=0)
        limit = 400 * 24 * 60
        for _ in range(limit):
            if self.matches(t):
                return t
            t += dt.timedelta(minutes=1)
        raise ValueError(f"cron 表达式 {self.expr!r} 在 400 天内没有触发点")

    def seconds_until_next(self, now: dt.datetime) -> float:
        return (self.next_after(now) - now).total_seconds()


def parse_daily(value: str) -> tuple[int, int]:
    """解析 "HH:MM"；不合法抛 ValueError（argparse 转成友好报错）。"""
    hh, _, mm = value.strip().partition(":")
    if not (hh.isdigit() and mm.isdigit()):
        raise ValueError(f"--daily 需要 HH:MM 格式，当前为 {value!r}")
    hour, minute = int(hh), int(mm)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"时间越界：{value!r}")
    return hour, minute


def daily_to_cron(hour: int, minute: int) -> str:
    return f"{minute} {hour} * * *"


def pick_direction(pool: list[str], day: dt.date) -> str | None:
    """按日期从方向池轮换取选题方向，保证相邻两天不重复（池够长时）。"""
    if not pool:
        return None
    return pool[day.toordinal() % len(pool)]
