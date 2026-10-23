from __future__ import annotations

import unittest

from campus_pilot.planner import generate_plan


class PlannerTests(unittest.TestCase):
    def test_plan_respects_daily_capacity_and_deadline(self) -> None:
        tasks = [
            {
                "id": 1,
                "title": "软件工程作业",
                "course": "软件工程",
                "due_at": "2026-10-24T18:00",
                "estimated_minutes": 180,
                "priority": "high",
                "status": "pending",
            },
            {
                "id": 2,
                "title": "过期任务",
                "course": "",
                "due_at": "2026-10-21T18:00",
                "estimated_minutes": 30,
                "priority": "medium",
                "status": "pending",
            },
        ]
        plan = generate_plan(tasks, "2026-10-22", 120, 3)
        self.assertEqual(plan["total_planned_minutes"], 180)
        self.assertTrue(all(block["minutes"] <= 60 for block in plan["blocks"]))
        self.assertEqual(plan["unscheduled"][0]["title"], "过期任务")

    def test_rejects_invalid_constraints(self) -> None:
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            generate_plan([], "明天")
        with self.assertRaisesRegex(ValueError, "每日可用时间"):
            generate_plan([], "2026-10-22", 10)
