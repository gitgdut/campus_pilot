"""CampusPilot MCP Server 及三个第一阶段工具。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from mcp.server import MCPServer

from campus_pilot.database import TaskRepository
from campus_pilot.exporter import export_plan_markdown
from campus_pilot.planner import generate_plan
from campus_pilot.weather import WeatherService

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "tasks.db"
DEFAULT_EXPORT_DIR = PROJECT_ROOT / "exports"


def create_server(
    db_path: str | Path | None = None,
    export_dir: str | Path | None = None,
    weather_service: WeatherService | None = None,
) -> MCPServer:
    """创建可独立运行、也可在测试中以内存客户端连接的 MCP Server。"""

    actual_path = Path(db_path or os.getenv("CAMPUS_PILOT_DB", DEFAULT_DB_PATH))
    actual_export_dir = Path(export_dir or DEFAULT_EXPORT_DIR)
    repository = TaskRepository(actual_path)
    weather = weather_service or WeatherService()
    server = MCPServer(
        name="campus-pilot",
        title="CampusPilot 学习任务工具",
        description="管理校园学习任务、生成计划、查询天气并导出文件。",
        instructions=(
            "新增任务前确认标题和截止时间；查询任务后使用返回的真实 ID；"
            "不要声称执行了尚未调用的操作。"
        ),
    )

    @server.tool()
    def add_task(
        title: str,
        due_at: str,
        course: str = "",
        estimated_minutes: int = 60,
        priority: Literal["low", "medium", "high"] = "medium",
    ) -> dict[str, Any]:
        """创建学习任务。due_at 使用 ISO 8601 格式；缺少标题或截止时间时不要调用。"""
        task = repository.add_task(
            title=title,
            due_at=due_at,
            course=course,
            estimated_minutes=estimated_minutes,
            priority=priority,
        )
        return {"ok": True, "message": "任务已创建", "task": task}

    @server.tool()
    def list_tasks(
        status: Literal["pending", "completed", "all"] = "pending",
    ) -> dict[str, Any]:
        """查询任务列表。默认只查未完成任务，也可以查询 completed 或 all。"""
        tasks = repository.list_tasks(status=status)
        return {
            "ok": True,
            "status": status,
            "count": len(tasks),
            "tasks": tasks,
        }

    @server.tool()
    def complete_task(task_id: int) -> dict[str, Any]:
        """用任务 ID 将一个未完成任务标记为已完成。ID 不确定时先调用 list_tasks。"""
        task = repository.complete_task(task_id)
        return {"ok": True, "message": "任务已完成", "task": task}

    @server.tool()
    def update_task(
        task_id: int,
        title: str | None = None,
        due_at: str | None = None,
        course: str | None = None,
        estimated_minutes: int | None = None,
        priority: Literal["low", "medium", "high"] | None = None,
    ) -> dict[str, Any]:
        """修改指定 ID 的任务。只传要改变的字段；ID 不确定时先调用 list_tasks。"""
        task = repository.update_task(
            task_id=task_id,
            title=title,
            due_at=due_at,
            course=course,
            estimated_minutes=estimated_minutes,
            priority=priority,
        )
        return {"ok": True, "message": "任务已更新", "task": task}

    @server.tool()
    def delete_task(task_id: int, confirmed: bool = False) -> dict[str, Any]:
        """删除任务。必须先用 confirmed=false 预览，用户明确确认后才能用 true 删除。"""
        task = repository.get_task(task_id)
        if not confirmed:
            return {
                "ok": False,
                "requires_confirmation": True,
                "message": "尚未删除，请向用户确认",
                "task": task,
            }
        deleted = repository.delete_task(task_id)
        return {"ok": True, "message": "任务已删除", "task": deleted}

    @server.tool()
    def generate_study_plan(
        start_date: str,
        daily_available_minutes: int = 120,
        days: int = 7,
    ) -> dict[str, Any]:
        """根据未完成任务、截止日期和每日可用分钟数，生成确定性的按日学习计划。"""
        tasks = repository.list_tasks(status="pending")
        plan = generate_plan(
            tasks=tasks,
            start_date=start_date,
            daily_available_minutes=daily_available_minutes,
            days=days,
        )
        return {"ok": True, "message": "学习计划已生成", **plan}

    @server.tool()
    def get_weather(city: str, start_date: str, days: int = 3) -> dict[str, Any]:
        """查询指定城市从某天开始的逐日天气，用于出行或学习地点决策。最多查询 7 天。"""
        forecast = weather.get_forecast(city=city, start_date=start_date, days=days)
        return {"ok": True, "message": "天气查询成功", **forecast}

    @server.tool()
    def export_study_plan(
        start_date: str,
        daily_available_minutes: int = 120,
        days: int = 7,
        filename: str = "study-plan.md",
    ) -> dict[str, Any]:
        """生成学习计划并导出 Markdown 文件，返回可供用户下载的文件名和路径。"""
        tasks = repository.list_tasks(status="pending")
        plan = generate_plan(
            tasks=tasks,
            start_date=start_date,
            daily_available_minutes=daily_available_minutes,
            days=days,
        )
        exported = export_plan_markdown(plan, actual_export_dir, filename)
        return {
            "ok": True,
            "message": "学习计划已导出",
            "filename": exported["filename"],
            "path": exported["path"],
            "bytes": exported["bytes"],
            "plan": plan,
        }

    return server


mcp = create_server()


def main() -> None:
    """以 stdio 方式启动，供 MCP Inspector 或其他 MCP Host 连接。"""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

