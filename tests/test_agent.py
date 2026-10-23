from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mcp import Client

from campus_pilot.agent import CampusAgent
from campus_pilot.mcp_server import create_server


class FakeToolCall:
    def __init__(self, name: str, arguments: dict) -> None:
        self.id = "call-1"
        self.type = "function"
        self.function = SimpleNamespace(
            name=name, arguments=json.dumps(arguments, ensure_ascii=False)
        )

    def model_dump(self, exclude_none: bool = True) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.function.name,
                "arguments": self.function.arguments,
            },
        }


class FakeCompletions:
    def __init__(self) -> None:
        self.requests: list[dict] = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        if len(self.requests) == 1:
            message = SimpleNamespace(
                content=None,
                tool_calls=[
                    FakeToolCall(
                        "add_task",
                        {
                            "title": "软件工程作业",
                            "course": "软件工程",
                            "due_at": "2026-10-30 18:00",
                            "estimated_minutes": 240,
                            "priority": "high",
                        },
                    )
                ],
            )
        else:
            message = SimpleNamespace(
                content="已创建软件工程作业，截止到 2026-10-30 18:00。",
                tool_calls=None,
            )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class AgentFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_tool_call_is_executed_through_mcp(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            server = create_server(Path(temp_dir) / "tasks.db")
            async with Client(server, raise_exceptions=True) as mcp_client:
                completions = FakeCompletions()
                fake_llm = SimpleNamespace(
                    chat=SimpleNamespace(completions=completions)
                )
                events: list[tuple[str, dict]] = []
                agent = CampusAgent(
                    mcp_client=mcp_client,
                    llm_client=fake_llm,
                    model="fake-tool-model",
                    on_tool_call=lambda name, args: events.append((name, args)),
                )

                reply = await agent.chat("帮我记录软件工程作业")

                self.assertIn("已创建", reply)
                self.assertEqual(events[0][0], "add_task")
                self.assertEqual(len(completions.requests), 2)
                second_messages = completions.requests[1]["messages"]
                self.assertEqual(second_messages[-1]["role"], "tool")
                self.assertIn("软件工程作业", second_messages[-1]["content"])

                result = await mcp_client.call_tool(
                    "list_tasks", {"status": "pending"}
                )
                self.assertEqual(result.structured_content["count"], 1)
                self.assertEqual(
                    result.structured_content["tasks"][0]["title"],
                    "软件工程作业",
                )


if __name__ == "__main__":
    unittest.main()
