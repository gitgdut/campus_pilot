"""CampusPilot Streamlit 网页。"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

# Streamlit 直接执行本文件时，只会把 campus_pilot/ 放入 sys.path。
# 显式加入项目根目录，使 `streamlit run campus_pilot/web.py` 在任意目录都能导入包。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from dotenv import load_dotenv
from mcp import Client
from openai import AsyncOpenAI

from campus_pilot.agent import CampusAgent
from campus_pilot.database import ChatRepository, TaskRepository
from campus_pilot.mcp_server import create_server


def _settings() -> tuple[str, str, str | None]:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL")
    base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None
    if not api_key or not model:
        raise RuntimeError("请先在 .env 中配置 LLM_API_KEY 和 LLM_MODEL")
    return api_key, model, base_url


async def _ask_agent(
    prompt: str,
    db_path: str,
    conversation_id: str,
    history: list[dict[str, str]],
    on_tool_call,
) -> str:
    api_key, model, base_url = _settings()
    llm = AsyncOpenAI(api_key=api_key, base_url=base_url)
    chat_repository = ChatRepository(db_path)
    server = create_server(db_path)
    async with Client(server) as mcp_client:
        agent = CampusAgent(
            mcp_client=mcp_client,
            llm_client=llm,
            model=model,
            on_tool_call=on_tool_call,
            initial_messages=history,
            chat_repository=chat_repository,
            conversation_id=conversation_id,
        )
        return await agent.chat(prompt)


def _task_label(task: dict[str, Any]) -> str:
    icon = "✅" if task["status"] == "completed" else "⏳"
    return f"{icon} #{task['id']} {task['title']}"


def render_app() -> None:
    st.set_page_config(page_title="CampusPilot", page_icon="🎓", layout="wide")
    load_dotenv(PROJECT_ROOT / ".env")
    db_path = os.getenv("CAMPUS_PILOT_DB", str(PROJECT_ROOT / "data" / "tasks.db"))
    task_repository = TaskRepository(db_path)
    chat_repository = ChatRepository(db_path)
    export_dir = PROJECT_ROOT / "exports"

    st.title("🎓 CampusPilot")
    st.caption("会对话、会调用 MCP 工具的校园学习任务智能体")
    if st.session_state.pop("export_ready", False):
        st.toast("学习计划已导出，可从左侧下载。", icon="✅")

    conversations = chat_repository.list_conversations()
    if "conversation_id" not in st.session_state:
        st.session_state.conversation_id = (
            conversations[0]["id"]
            if conversations
            else chat_repository.create_conversation()
        )

    with st.sidebar:
        st.header("对话")
        if st.button("＋ 新建对话", use_container_width=True):
            st.session_state.conversation_id = chat_repository.create_conversation()
            st.rerun()

        conversations = chat_repository.list_conversations()
        labels = {
            item["id"]: f"{item['title']} · {item['updated_at'][5:16]}"
            for item in conversations
        }
        ids = list(labels)
        current = st.session_state.conversation_id
        selected = st.selectbox(
            "历史记录",
            ids,
            index=ids.index(current) if current in ids else 0,
            format_func=lambda item_id: labels[item_id],
        )
        if selected != current:
            st.session_state.conversation_id = selected
            st.rerun()

        if st.button("清空当前对话", use_container_width=True):
            chat_repository.clear_messages(st.session_state.conversation_id)
            st.rerun()

        st.divider()
        pending = task_repository.list_tasks("pending")
        completed = task_repository.list_tasks("completed")
        st.metric("待完成任务", len(pending))
        st.metric("已完成任务", len(completed))
        with st.expander("任务一览", expanded=True):
            tasks = pending + completed[:5]
            if not tasks:
                st.caption("暂时没有任务")
            for task in tasks:
                st.markdown(f"**{_task_label(task)}**")
                st.caption(
                    f"截止 {task['due_at']} · {task['estimated_minutes']} 分钟 · {task['priority']}"
                )

        st.divider()
        st.subheader("导出文件")
        exported_files = sorted(
            export_dir.glob("*.md"), key=lambda path: path.stat().st_mtime, reverse=True
        )[:5]
        if not exported_files:
            st.caption("让 CampusPilot 导出计划后，可在这里下载。")
        for exported_file in exported_files:
            st.download_button(
                label=f"⬇ {exported_file.name}",
                data=exported_file.read_bytes(),
                file_name=exported_file.name,
                mime="text/markdown",
                key=f"download-{exported_file.name}-{exported_file.stat().st_mtime_ns}",
                use_container_width=True,
            )

    conversation_id = st.session_state.conversation_id
    history = chat_repository.list_messages(conversation_id)
    for message in history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("例如：帮我记录周五的软件工程作业"):
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.status("CampusPilot 正在处理…", expanded=True) as status:
                events: list[tuple[str, dict[str, Any]]] = []

                def show_tool(name: str, arguments: dict[str, Any]) -> None:
                    events.append((name, arguments))
                    st.write(f"🔧 调用 MCP 工具 `{name}`")
                    st.json(arguments)

                try:
                    reply = asyncio.run(
                        _ask_agent(
                            prompt=prompt,
                            db_path=db_path,
                            conversation_id=conversation_id,
                            history=history,
                            on_tool_call=show_tool,
                        )
                    )
                except Exception as exc:
                    status.update(label="处理失败", state="error")
                    st.error(f"请求失败：{exc}")
                else:
                    status.update(
                        label=f"处理完成，共调用 {len(events)} 个工具",
                        state="complete",
                        expanded=False,
                    )
                    st.markdown(reply)
                    if any(name == "export_study_plan" for name, _ in events):
                        # 侧边栏在本轮工具调用前已经渲染；自动重跑后会读取新文件。
                        # 回复已持久化到 SQLite，因此重跑不会丢失对话内容。
                        st.session_state.export_ready = True
                        st.rerun()


def main() -> None:
    render_app()


if __name__ == "__main__":
    main()
