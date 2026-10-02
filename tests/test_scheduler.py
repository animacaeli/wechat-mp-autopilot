"""定时调度测试：cron 解析/触发点计算 + 方向轮换（不测常驻循环本身）。"""

import datetime as dt

import pytest

from autopilot.scheduler import Cron, daily_to_cron, parse_daily, pick_direction


def test_parse_daily_valid():
    assert parse_daily("08:00") == (8, 0)
    assert parse_daily("23:59") == (23, 59)
    assert parse_daily("0:5") == (0, 5)


@pytest.mark.parametrize("bad", ["8点", "24:00", "08:60", "08", ""])
def test_parse_daily_invalid(bad):
    with pytest.raises(ValueError):
        parse_daily(bad)


def test_daily_to_cron():
    assert daily_to_cron(8, 5) == "5 8 * * *"


# ── Cron 解析 ────────────────────────────────────────────


def test_cron_daily_expression():
    cron = Cron("0 8 * * *")
    assert cron.fields["minute"] == {0}
    assert cron.fields["hour"] == {8}
    assert cron.fields["dom"] == set(range(1, 32))
    assert cron.fields["dow"] == set(range(7))


def test_cron_step_and_range_and_list():
    cron = Cron("*/15 9-11 1,15 * *")
    assert cron.fields["minute"] == {0, 15, 30, 45}
    assert cron.fields["hour"] == {9, 10, 11}
    assert cron.fields["dom"] == {1, 15}


def test_cron_dow_7_is_sunday():
    assert Cron("0 8 * * 7").fields["dow"] == {0}
    assert Cron("0 8 * * 0").fields["dow"] == {0}


@pytest.mark.parametrize(
    "bad", ["0 8 * *", "60 8 * * *", "0 25 * * *", "0 8 0 * *", "*/0 8 * * *", "0 8 * * abc", "0 8 32 * *"]
)
def test_cron_invalid(bad):
    with pytest.raises(ValueError):
        Cron(bad)


# ── 触发点计算 ───────────────────────────────────────────


def test_cron_next_after_same_day():
    cron = Cron("0 8 * * *")
    now = dt.datetime(2026, 10, 2, 6, 0)
    assert cron.next_after(now) == dt.datetime(2026, 10, 2, 8, 0)


def test_cron_next_after_rolls_to_tomorrow():
    cron = Cron("0 8 * * *")
    now = dt.datetime(2026, 10, 2, 9, 0)
    assert cron.next_after(now) == dt.datetime(2026, 10, 3, 8, 0)


def test_cron_next_after_exact_time_counts_next_day():
    cron = Cron("0 8 * * *")
    now = dt.datetime(2026, 10, 2, 8, 0)
    assert cron.next_after(now) == dt.datetime(2026, 10, 3, 8, 0)


def test_cron_weekday_restriction():
    # 2026-10-02 是周五；0=周日
    cron = Cron("0 8 * * 0")
    now = dt.datetime(2026, 10, 2, 6, 0)
    assert cron.next_after(now) == dt.datetime(2026, 10, 4, 8, 0)  # 周日


def test_cron_every_other_day():
    # dom 的 */2 是 1,3,5,…（vixie 语义）：10-02 之后下一个奇数日是 10-03
    cron = Cron("0 8 */2 * *")
    now = dt.datetime(2026, 10, 2, 9, 0)
    assert cron.next_after(now).day == 3


def test_cron_seconds_until_next():
    cron = Cron("0 8 * * *")
    assert cron.seconds_until_next(dt.datetime(2026, 10, 2, 7, 0)) == 3600


# ── 方向轮换 ─────────────────────────────────────────────


def test_pick_direction_rotates_by_day():
    pool = ["两性沟通", "婚姻经营", "亲子养育"]
    d1 = dt.date(2026, 10, 2)
    d2 = dt.date(2026, 10, 3)
    assert pick_direction(pool, d1) != pick_direction(pool, d2)
    assert pick_direction(pool, d1) == pick_direction(pool, d1 + dt.timedelta(days=len(pool)))


def test_pick_direction_empty_pool():
    assert pick_direction([], dt.date.today()) is None
