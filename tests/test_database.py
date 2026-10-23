from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from campus_pilot.database import ChatRepository, TaskRepository


class TaskRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = TaskRepository(Path(self.temp_dir.name) / "tasks.db")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_add_list_and_complete_task(self) -> None:
        task = self.repository.add_task(
            title="软件工程作业",
            course="软件工程",
            due_at="2026-10-30 18:00",
            estimated_minutes=240,
            priority="high",
        )
        self.assertEqual(task["id"], 1)
        self.assertEqual(task["status"], "pending")
        self.assertEqual(self.repository.list_tasks(), [task])

        completed = self.repository.complete_task(task["id"])
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(self.repository.list_tasks(), [])
        self.assertEqual(len(self.repository.list_tasks("completed")), 1)

    def test_rejects_invalid_task(self) -> None:
        with self.assertRaisesRegex(ValueError, "标题"):
            self.repository.add_task("  ", "2026-10-30 18:00")
        with self.assertRaisesRegex(ValueError, "ISO 8601"):
            self.repository.add_task("作业", "下周五")
        with self.assertRaisesRegex(ValueError, "预计时长"):
            self.repository.add_task("作业", "2026-10-30", estimated_minutes=0)

    def test_priority_then_due_date_order(self) -> None:
        self.repository.add_task("低优先级", "2026-10-23", priority="low")
        self.repository.add_task("高优先级", "2026-11-01", priority="high")
        titles = [task["title"] for task in self.repository.list_tasks()]
        self.assertEqual(titles, ["高优先级", "低优先级"])

    def test_update_and_delete_task(self) -> None:
        task = self.repository.add_task("旧标题", "2026-10-30 18:00")
        updated = self.repository.update_task(
            task["id"],
            title="新标题",
            due_at="2026-11-01 20:00",
            priority="high",
        )
        self.assertEqual(updated["title"], "新标题")
        self.assertEqual(updated["due_at"], "2026-11-01T20:00")
        self.assertEqual(updated["priority"], "high")

        deleted = self.repository.delete_task(task["id"])
        self.assertEqual(deleted["title"], "新标题")
        with self.assertRaises(LookupError):
            self.repository.get_task(task["id"])


class ChatRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = ChatRepository(Path(self.temp_dir.name) / "chat.db")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_conversation_messages_survive_repository_recreation(self) -> None:
        conversation_id = self.repository.create_conversation()
        self.repository.add_message(conversation_id, "user", "列出我的任务")
        self.repository.add_message(conversation_id, "assistant", "你有一个任务。")

        reopened = ChatRepository(Path(self.temp_dir.name) / "chat.db")
        self.assertEqual(
            reopened.list_messages(conversation_id),
            [
                {"role": "user", "content": "列出我的任务"},
                {"role": "assistant", "content": "你有一个任务。"},
            ],
        )
        self.assertEqual(reopened.list_conversations()[0]["title"], "列出我的任务")


if __name__ == "__main__":
    unittest.main()

