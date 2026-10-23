from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from mcp import Client

from campus_pilot.mcp_server import create_server


class MCPToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_are_discoverable_and_form_a_complete_flow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            server = create_server(Path(temp_dir) / "tasks.db")
            # AnyIO 的取消域要求 MCP Client 在同一个异步任务中进入和退出。
            async with Client(server, raise_exceptions=True) as client:
                listed = await client.list_tools()
                self.assertEqual(
                    {tool.name for tool in listed.tools},
                    {
                        "add_task",
                        "list_tasks",
                        "complete_task",
                        "update_task",
                        "delete_task",
                        "generate_study_plan",
                        "get_weather",
                        "export_study_plan",
                    },
                )

                added = await client.call_tool(
                    "add_task",
                    {
                        "title": "MCP 作业",
                        "course": "软件工程",
                        "due_at": "2026-10-30 18:00",
                        "estimated_minutes": 120,
                        "priority": "high",
                    },
                )
                task_id = added.structured_content["task"]["id"]
                self.assertTrue(added.structured_content["ok"])

                pending = await client.call_tool(
                    "list_tasks", {"status": "pending"}
                )
                self.assertEqual(pending.structured_content["count"], 1)
                self.assertEqual(
                    pending.structured_content["tasks"][0]["id"], task_id
                )

                completed = await client.call_tool(
                    "complete_task", {"task_id": task_id}
                )
                self.assertEqual(
                    completed.structured_content["task"]["status"], "completed"
                )

                pending_after = await client.call_tool(
                    "list_tasks", {"status": "pending"}
                )
                self.assertEqual(pending_after.structured_content["count"], 0)

    async def test_update_plan_and_confirmed_delete(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            server = create_server(Path(temp_dir) / "tasks.db")
            async with Client(server, raise_exceptions=True) as client:
                added = await client.call_tool(
                    "add_task",
                    {
                        "title": "课程设计",
                        "due_at": "2026-10-25 18:00",
                        "estimated_minutes": 180,
                    },
                )
                task_id = added.structured_content["task"]["id"]

                updated = await client.call_tool(
                    "update_task",
                    {"task_id": task_id, "priority": "high"},
                )
                self.assertEqual(
                    updated.structured_content["task"]["priority"], "high"
                )

                plan = await client.call_tool(
                    "generate_study_plan",
                    {
                        "start_date": "2026-10-22",
                        "daily_available_minutes": 120,
                        "days": 4,
                    },
                )
                self.assertEqual(plan.structured_content["total_planned_minutes"], 180)
                self.assertEqual(len(plan.structured_content["blocks"]), 3)

                preview = await client.call_tool(
                    "delete_task", {"task_id": task_id, "confirmed": False}
                )
                self.assertTrue(preview.structured_content["requires_confirmation"])
                still_there = await client.call_tool(
                    "list_tasks", {"status": "pending"}
                )
                self.assertEqual(still_there.structured_content["count"], 1)

                deleted = await client.call_tool(
                    "delete_task", {"task_id": task_id, "confirmed": True}
                )
                self.assertTrue(deleted.structured_content["ok"])
                after = await client.call_tool(
                    "list_tasks", {"status": "pending"}
                )
                self.assertEqual(after.structured_content["count"], 0)

    async def test_weather_and_markdown_export_tools(self) -> None:
        class FakeWeather:
            def get_forecast(self, city: str, start_date: str, days: int = 3):
                return {
                    "location": city,
                    "timezone": "Asia/Shanghai",
                    "forecasts": [
                        {
                            "date": start_date,
                            "weather": "小雨",
                            "precipitation_probability_percent": 80,
                        }
                    ],
                    "source": "Open-Meteo",
                }

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            server = create_server(
                root / "tasks.db",
                export_dir=root / "exports",
                weather_service=FakeWeather(),
            )
            async with Client(server, raise_exceptions=True) as client:
                weather = await client.call_tool(
                    "get_weather",
                    {"city": "上海", "start_date": "2026-10-23", "days": 1},
                )
                self.assertEqual(weather.structured_content["location"], "上海")
                self.assertEqual(
                    weather.structured_content["forecasts"][0]["weather"], "小雨"
                )

                await client.call_tool(
                    "add_task",
                    {
                        "title": "导出测试任务",
                        "due_at": "2026-10-25 18:00",
                        "estimated_minutes": 60,
                    },
                )
                exported = await client.call_tool(
                    "export_study_plan",
                    {
                        "start_date": "2026-10-22",
                        "filename": "我的计划.md",
                    },
                )
                output = root / "exports" / "我的计划.md"
                self.assertTrue(output.exists())
                self.assertEqual(exported.structured_content["filename"], "我的计划.md")
                self.assertIn("导出测试任务", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

