"""将确定性学习计划渲染并安全写入 Markdown 文件。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


def render_plan_markdown(plan: dict[str, Any]) -> str:
    generated_at = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M")
    lines = [
        "# CampusPilot 学习计划",
        "",
        f"> 计划周期：{plan['start_date']} 至 {plan['end_date']}",
        f"> 每日可用时间：{plan['daily_available_minutes']} 分钟",
        f"> 生成时间：{generated_at}（北京时间）",
        "",
        "## 学习安排",
        "",
    ]
    if plan["blocks"]:
        current_date = None
        for block in plan["blocks"]:
            if block["date"] != current_date:
                current_date = block["date"]
                lines.extend([f"### {current_date}", ""])
            course = f"（{block['course']}）" if block.get("course") else ""
            lines.append(
                f"- [ ] #{block['task_id']} {block['title']}{course} — {block['minutes']} 分钟"
            )
        lines.append("")
    else:
        lines.extend(["当前计划周期内没有可安排的未完成任务。", ""])

    lines.extend(["## 未排入任务", ""])
    if plan["unscheduled"]:
        for item in plan["unscheduled"]:
            lines.append(
                f"- #{item['task_id']} {item['title']}：剩余 {item['remaining_minutes']} 分钟（{item['reason']}）"
            )
    else:
        lines.append("所有任务均已排入计划。")
    lines.extend(["", f"总计划时长：**{plan['total_planned_minutes']} 分钟**", ""])
    return "\n".join(lines)


def export_plan_markdown(
    plan: dict[str, Any], export_dir: str | Path, filename: str
) -> dict[str, Any]:
    """只允许在 export_dir 下写入安全文件名的 Markdown。"""
    safe_name = Path(filename.strip()).name
    if not safe_name:
        safe_name = f"study-plan-{plan['start_date']}.md"
    safe_name = re.sub(r"[^0-9A-Za-z_.\-\u4e00-\u9fff]", "-", safe_name)
    if not safe_name.lower().endswith(".md"):
        safe_name += ".md"
    target_dir = Path(export_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = (target_dir / safe_name).resolve()
    if target.parent != target_dir:
        raise ValueError("导出文件必须位于 exports 目录")
    content = render_plan_markdown(plan)
    target.write_text(content, encoding="utf-8")
    return {
        "filename": safe_name,
        "path": str(target),
        "content": content,
        "bytes": len(content.encode("utf-8")),
    }
