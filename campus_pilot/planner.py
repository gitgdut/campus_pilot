"""可测试、可解释的学习计划生成算法。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any


def generate_plan(
    tasks: list[dict[str, Any]],
    start_date: str,
    daily_available_minutes: int = 120,
    days: int = 7,
) -> dict[str, Any]:
    """在截止日期前按天分配任务时长，不让模型虚构排程结果。"""
    try:
        first_day = date.fromisoformat(start_date)
    except ValueError as exc:
        raise ValueError("start_date 必须是 YYYY-MM-DD 格式") from exc
    if not 30 <= daily_available_minutes <= 12 * 60:
        raise ValueError("每日可用时间必须在 30 到 720 分钟之间")
    if not 1 <= days <= 31:
        raise ValueError("计划天数必须在 1 到 31 天之间")

    plan_days = [first_day + timedelta(days=offset) for offset in range(days)]
    capacity = {day: daily_available_minutes for day in plan_days}
    blocks: list[dict[str, Any]] = []
    unscheduled: list[dict[str, Any]] = []
    priority_rank = {"high": 0, "medium": 1, "low": 2}

    sorted_tasks = sorted(
        (task for task in tasks if task.get("status") == "pending"),
        key=lambda task: (
            datetime.fromisoformat(task["due_at"]),
            priority_rank.get(task.get("priority", "medium"), 1),
        ),
    )

    for task in sorted_tasks:
        remaining = int(task["estimated_minutes"])
        due_day = datetime.fromisoformat(task["due_at"]).date()
        for day in plan_days:
            if day > due_day or remaining == 0:
                break
            while capacity[day] > 0 and remaining > 0:
                minutes = min(remaining, capacity[day], 60)
                blocks.append(
                    {
                        "date": day.isoformat(),
                        "task_id": task["id"],
                        "title": task["title"],
                        "course": task["course"],
                        "minutes": minutes,
                        "due_at": task["due_at"],
                    }
                )
                capacity[day] -= minutes
                remaining -= minutes
        if remaining:
            unscheduled.append(
                {
                    "task_id": task["id"],
                    "title": task["title"],
                    "remaining_minutes": remaining,
                    "reason": "截止日期前或计划周期内可用时间不足",
                }
            )

    return {
        "start_date": first_day.isoformat(),
        "end_date": plan_days[-1].isoformat(),
        "daily_available_minutes": daily_available_minutes,
        "blocks": blocks,
        "unscheduled": unscheduled,
        "total_planned_minutes": sum(block["minutes"] for block in blocks),
    }
