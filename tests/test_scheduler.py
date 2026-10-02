"""定时调度纯函数测试（不测常驻循环本身）。"""

import datetime as dt

import pytest

from autopilot.scheduler import parse_daily, pick_direction, seconds_until_next


def test_parse_daily_valid():
    assert parse_daily("08:00") == (8, 0)
    assert parse_daily("23:59") == (23, 59)
    assert parse_daily("0:5") == (0, 5)


@pytest.mark.parametrize("bad", ["8点", "24:00", "08:60", "08", ""])
def test_parse_daily_invalid(bad):
    with pytest.raises(ValueError):
        parse_daily(bad)


def test_seconds_until_next_future_today():
    now = dt.datetime(2026, 10, 2, 6, 0, 0)
    assert seconds_until_next(now, 8, 0) == 2 * 3600


def test_seconds_until_next_rolls_to_tomorrow():
    now = dt.datetime(2026, 10, 2, 9, 0, 0)
    assert seconds_until_next(now, 8, 0) == 23 * 3600


def test_seconds_until_next_at_exact_time():
    now = dt.datetime(2026, 10, 2, 8, 0, 0)
    assert seconds_until_next(now, 8, 0) == 24 * 3600  # 已到点则算明天


def test_pick_direction_rotates_by_day():
    pool = ["两性沟通", "婚姻经营", "亲子养育"]
    d1 = dt.date(2026, 10, 2)
    d2 = dt.date(2026, 10, 3)
    assert pick_direction(pool, d1) != pick_direction(pool, d2)
    assert pick_direction(pool, d1) == pick_direction(pool, d1 + dt.timedelta(days=len(pool)))


def test_pick_direction_empty_pool():
    assert pick_direction([], dt.date.today()) is None
