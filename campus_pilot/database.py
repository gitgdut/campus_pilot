"""SQLite 任务仓库。

数据库逻辑与 MCP/模型逻辑分离，便于独立测试，也避免让模型直接执行 SQL。
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Literal

TaskStatus = Literal["pending", "completed"]
Priority = Literal["low", "medium", "high"]


class TaskRepository:
    """为任务工具提供小而明确的持久化接口。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    course TEXT NOT NULL DEFAULT '',
                    due_at TEXT NOT NULL,
                    estimated_minutes INTEGER NOT NULL DEFAULT 60,
                    priority TEXT NOT NULL DEFAULT 'medium'
                        CHECK (priority IN ('low', 'medium', 'high')),
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'completed')),
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )

    @staticmethod
    def _validate_due_at(due_at: str) -> str:
        try:
            parsed = datetime.fromisoformat(due_at)
        except ValueError as exc:
            raise ValueError(
                "due_at 必须是 ISO 8601 格式，例如 2026-10-30 18:00"
            ) from exc
        return parsed.isoformat(timespec="minutes")

    def add_task(
        self,
        title: str,
        due_at: str,
        course: str = "",
        estimated_minutes: int = 60,
        priority: Priority = "medium",
    ) -> dict[str, Any]:
        title = title.strip()
        course = course.strip()
        if not title:
            raise ValueError("任务标题不能为空")
        if estimated_minutes <= 0 or estimated_minutes > 24 * 60:
            raise ValueError("预计时长必须在 1 到 1440 分钟之间")
        if priority not in {"low", "medium", "high"}:
            raise ValueError("priority 只能是 low、medium 或 high")

        normalized_due_at = self._validate_due_at(due_at)
        created_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO tasks
                    (title, course, due_at, estimated_minutes, priority, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    course,
                    normalized_due_at,
                    estimated_minutes,
                    priority,
                    created_at,
                ),
            )
            task_id = cursor.lastrowid
        return self.get_task(int(task_id))

    def get_task(self, task_id: int) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
        if row is None:
            raise LookupError(f"未找到 ID 为 {task_id} 的任务")
        return dict(row)

    def list_tasks(self, status: TaskStatus | Literal["all"] = "pending") -> list[dict[str, Any]]:
        if status not in {"pending", "completed", "all"}:
            raise ValueError("status 只能是 pending、completed 或 all")
        where = "" if status == "all" else "WHERE status = ?"
        parameters: tuple[str, ...] = () if status == "all" else (status,)
        query = f"""
            SELECT * FROM tasks
            {where}
            ORDER BY
                CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                due_at ASC,
                id ASC
        """
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def complete_task(self, task_id: int) -> dict[str, Any]:
        completed_at = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE tasks
                SET status = 'completed', completed_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (completed_at, task_id),
            )
            if cursor.rowcount == 0:
                row = connection.execute(
                    "SELECT status FROM tasks WHERE id = ?", (task_id,)
                ).fetchone()
                if row is None:
                    raise LookupError(f"未找到 ID 为 {task_id} 的任务")
                raise ValueError(f"任务 {task_id} 已经完成，无需重复操作")
        return self.get_task(task_id)

    def update_task(
        self,
        task_id: int,
        title: str | None = None,
        due_at: str | None = None,
        course: str | None = None,
        estimated_minutes: int | None = None,
        priority: Priority | None = None,
    ) -> dict[str, Any]:
        """只更新明确传入的字段，并返回更新后的任务。"""
        self.get_task(task_id)
        updates: dict[str, Any] = {}
        if title is not None:
            title = title.strip()
            if not title:
                raise ValueError("任务标题不能为空")
            updates["title"] = title
        if due_at is not None:
            updates["due_at"] = self._validate_due_at(due_at)
        if course is not None:
            updates["course"] = course.strip()
        if estimated_minutes is not None:
            if estimated_minutes <= 0 or estimated_minutes > 24 * 60:
                raise ValueError("预计时长必须在 1 到 1440 分钟之间")
            updates["estimated_minutes"] = estimated_minutes
        if priority is not None:
            if priority not in {"low", "medium", "high"}:
                raise ValueError("priority 只能是 low、medium 或 high")
            updates["priority"] = priority
        if not updates:
            raise ValueError("至少需要提供一个要修改的字段")

        assignments = ", ".join(f"{field} = ?" for field in updates)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE tasks SET {assignments} WHERE id = ?",
                (*updates.values(), task_id),
            )
        return self.get_task(task_id)

    def delete_task(self, task_id: int) -> dict[str, Any]:
        """删除任务并返回删除前的数据，供界面展示与审计。"""
        task = self.get_task(task_id)
        with self._connect() as connection:
            connection.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        return task


class ChatRepository:
    """持久化会话和用户可见消息，为跨页面刷新记忆提供支持。"""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                        ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, id);
                """
            )

    def create_conversation(self, title: str = "新对话") -> str:
        conversation_id = uuid.uuid4().hex
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations (id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, title, now, now),
            )
        return conversation_id

    def list_conversations(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, title, created_at, updated_at
                FROM conversations
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_message(self, conversation_id: str, role: str, content: str) -> None:
        if role not in {"user", "assistant"}:
            raise ValueError("只持久化 user 和 assistant 消息")
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)
            ).fetchone()
            if exists is None:
                raise LookupError("会话不存在")
            connection.execute(
                """
                INSERT INTO messages (conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, role, content, now),
            )
            if role == "user":
                connection.execute(
                    """
                    UPDATE conversations
                    SET title = CASE WHEN title = '新对话' THEN ? ELSE title END,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (content.strip()[:24] or "新对话", now, conversation_id),
                )
            else:
                connection.execute(
                    "UPDATE conversations SET updated_at = ? WHERE id = ?",
                    (now, conversation_id),
                )

    def list_messages(self, conversation_id: str, limit: int = 40) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content FROM (
                    SELECT id, role, content
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) ORDER BY id ASC
                """,
                (conversation_id, limit),
            ).fetchall()
        return [{"role": row["role"], "content": row["content"]} for row in rows]

    def clear_messages(self, conversation_id: str) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM messages WHERE conversation_id = ?", (conversation_id,)
            )
            connection.execute(
                """
                UPDATE conversations SET title = '新对话', updated_at = ?
                WHERE id = ?
                """,
                (now, conversation_id),
            )

