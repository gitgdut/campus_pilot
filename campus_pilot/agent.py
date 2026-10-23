"""把 OpenAI 兼容模型的工具调用桥接到真实 MCP Client。"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from mcp import Client
from openai import AsyncOpenAI

from .database import ChatRepository

ToolEventHandler = Callable[[str, dict[str, Any]], None]


class CampusAgent:
    """维护多轮上下文，并让模型自主选择 MCP 工具。"""

    def __init__(
        self,
        mcp_client: Client,
        llm_client: AsyncOpenAI,
        model: str,
        on_tool_call: ToolEventHandler | None = None,
        max_tool_rounds: int = 6,
        initial_messages: list[dict[str, Any]] | None = None,
        chat_repository: ChatRepository | None = None,
        conversation_id: str | None = None,
    ) -> None:
        self.mcp_client = mcp_client
        self.llm_client = llm_client
        self.model = model
        self.on_tool_call = on_tool_call
        self.max_tool_rounds = max_tool_rounds
        self.messages: list[dict[str, Any]] = list(initial_messages or [])
        self.chat_repository = chat_repository
        self.conversation_id = conversation_id
        if (chat_repository is None) != (conversation_id is None):
            raise ValueError("chat_repository 和 conversation_id 必须同时提供")

    def clear_history(self) -> None:
        self.messages.clear()
        if self.chat_repository and self.conversation_id:
            self.chat_repository.clear_messages(self.conversation_id)

    def _system_prompt(self) -> str:
        now = datetime.now(ZoneInfo("Asia/Shanghai"))
        return f"""你是 CampusPilot，一个严谨友好的校园学习任务助理。
当前北京时间是 {now:%Y-%m-%d %H:%M}。
你必须遵守：
1. 涉及创建、查询、修改、完成、删除任务、天气、生成或导出计划时，必须调用相应工具，不能假装已经操作。
2. 创建任务缺少标题或明确截止时间时，先向用户追问，不得猜测。
3. 用户用“它、刚才那个”等指代时，结合对话和工具返回结果判断；仍不明确就追问。
4. 调用工具后，用简短中文说明真实执行结果，日期时间要清楚。
5. 工具报错时如实解释，不得捏造成功结果。
6. 删除任务必须先用 confirmed=false 预览并向用户明确确认；只有用户确认后才能用 confirmed=true。
7. 生成学习计划时使用今天或用户指定日期作为 start_date，并清楚提示未排入的时长。
8. 天气相关问题必须调用 get_weather，不得依赖模型记忆猜测实时天气。
9. 用户要求下载或保存计划时调用 export_study_plan，并告诉用户可在网页侧边栏下载。"""

    async def _openai_tools(self) -> list[dict[str, Any]]:
        listed = await self.mcp_client.list_tools()
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description or "",
                    "parameters": tool.input_schema,
                },
            }
            for tool in listed.tools
        ]

    @staticmethod
    def _result_text(result: Any) -> str:
        if result.structured_content is not None:
            return json.dumps(result.structured_content, ensure_ascii=False)
        parts = [
            item.text
            for item in result.content
            if getattr(item, "type", None) == "text"
        ]
        return "\n".join(parts) or "工具没有返回文本内容"

    async def chat(self, user_message: str) -> str:
        user_message = user_message.strip()
        if not user_message:
            raise ValueError("消息不能为空")

        tools = await self._openai_tools()
        self.messages.append({"role": "user", "content": user_message})
        if self.chat_repository and self.conversation_id:
            self.chat_repository.add_message(
                self.conversation_id, "user", user_message
            )

        for _ in range(self.max_tool_rounds + 1):
            response = await self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._system_prompt()},
                    *self.messages,
                ],
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
            )
            message = response.choices[0].message
            tool_calls = message.tool_calls or []
            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": message.content,
            }
            if tool_calls:
                assistant_message["tool_calls"] = [
                    call.model_dump(exclude_none=True) for call in tool_calls
                ]
            self.messages.append(assistant_message)

            if not tool_calls:
                final_text = message.content or "模型没有返回文本内容。"
                if self.chat_repository and self.conversation_id:
                    self.chat_repository.add_message(
                        self.conversation_id, "assistant", final_text
                    )
                return final_text

            for call in tool_calls:
                try:
                    arguments = json.loads(call.function.arguments or "{}")
                    if not isinstance(arguments, dict):
                        raise ValueError("工具参数必须是 JSON 对象")
                except (json.JSONDecodeError, ValueError) as exc:
                    tool_text = json.dumps(
                        {"ok": False, "error": f"模型生成了无效工具参数：{exc}"},
                        ensure_ascii=False,
                    )
                else:
                    if self.on_tool_call:
                        self.on_tool_call(call.function.name, arguments)
                    try:
                        result = await self.mcp_client.call_tool(
                            call.function.name, arguments
                        )
                        tool_text = self._result_text(result)
                    except Exception as exc:  # MCP 将工具异常作为协议错误返回
                        tool_text = json.dumps(
                            {"ok": False, "error": str(exc)}, ensure_ascii=False
                        )
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": tool_text,
                    }
                )

        raise RuntimeError("工具调用轮数过多，已停止以避免无限循环")

