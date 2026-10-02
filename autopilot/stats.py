"""⑩ 数据回流：personal 模式人工补录阅读数据（enterprise 的 datacube 自动拉取属 M3）。

发布后第 3 / 7 天，把后台数据录入 09_stats.json，SQLite 汇总留给 M3。
"""

from __future__ import annotations

import datetime as dt

from .pipeline.common import load_json, save_json

FIELDS = [("reads", "阅读数"), ("likes", "点赞"), ("wows", "在看"), ("shares", "转发")]


def record_stats(run_dir, values: dict | None = None, day: int = 3) -> dict:
    """交互式（或传入 values 直接）补录第 day 天数据。"""
    values = values or {}
    payload: dict[str, int | str] = {}
    for key, label in FIELDS:
        if key in values:
            payload[key] = int(values[key])
        else:
            raw = input(f"  {label}（回车跳过）: ").strip()
            payload[key] = int(raw) if raw.isdigit() else None

    existing_path = run_dir / "09_stats.json"
    data = load_json(existing_path) if existing_path.is_file() else {}
    snapshots = data.get("snapshots", [])
    snapshots.append(
        {
            "day": day,
            "recorded_at": dt.datetime.now().isoformat(timespec="seconds"),
            **payload,
        }
    )
    data["snapshots"] = snapshots
    save_json(existing_path, data)
    return data
