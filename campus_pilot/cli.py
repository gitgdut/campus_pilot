"""CampusPilot 终端交互入口。"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from mcp import Client
from openai import AsyncOpenAI

from .agent import CampusAgent
from .database import ChatRepository
from .mcp_server import create_server

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _required_setting(*names: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    raise RuntimeError(
        f"缺少配置：请在 .env 中设置 {' 或 '.join(names)}。可复制 .env.example 开始。"
    )


async def run_chat() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = _required_setting("LLM_API_KEY", "OPENAI_API_KEY")
    model = _required_setting("LLM_MODEL", "OPENAI_MODEL")
    base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or None

    llm_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    server = create_server()
    db_path = os.getenv("CAMPUS_PILOT_DB", str(PROJECT_ROOT / "data" / "tasks.db"))
    chat_repository = ChatRepository(db_path)
    # CLI 每次启动创建一个独立会话，避免混入此前终端运行的上下文。
    now_title = "终端对话"
    conversation_id = chat_repository.create_conversation(now_title)
    async with Client(server) as mcp_client:
        agent = CampusAgent(
            mcp_client=mcp_client,
            llm_client=llm_client,
            model=model,
            on_tool_call=lambda name, args: print(f"  [MCP] {name} {args}"),
            chat_repository=chat_repository,
            conversation_id=conversation_id,
        )
        print("CampusPilot 已启动。输入 /clear 清空上下文，输入 /quit 退出。")
        while True:
            try:
                user_input = await asyncio.to_thread(input, "\n你：")
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                return
            command = user_input.strip().lower()
            if command in {"/quit", "/exit"}:
                print("再见！")
                return
            if command == "/clear":
                agent.clear_history()
                print("已清空本轮对话上下文。")
                continue
            if not command:
                continue
            try:
                reply = await agent.chat(user_input)
            except Exception as exc:
                print(f"系统错误：{exc}")
            else:
                print(f"CampusPilot：{reply}")


def main() -> None:
    try:
        asyncio.run(run_chat())
    except RuntimeError as exc:
        raise SystemExit(f"配置错误：{exc}") from None


if __name__ == "__main__":
    main()

