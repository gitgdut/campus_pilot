# CampusPilot 第三阶段

CampusPilot 是一个使用自然语言管理学习任务的校园智能体。目前已经完成：

- SQLite 持久化任务；
- 八个真实 MCP 工具：任务增查改完删、计划生成、天气查询和 Markdown 导出；
- MCP Client 与支持 Tool Calling 的 OpenAI 兼容模型之间的调用循环；
- 可连续对话的终端入口与 Streamlit 网页；
- SQLite 持久化聊天记录，支持历史会话和多轮记忆；
- 网页展示 MCP 工具名称与参数，便于演示 Agent 的执行过程；
- 删除任务需要用户二次确认；
- 通过 Open-Meteo 查询真实天气，无需额外 API Key；
- 将学习计划安全导出到 `exports/`，网页侧边栏可直接下载；
- 数据库与 MCP 端到端自动化测试。

## 运行环境

- Python 3.11 或更高版本
- 一个支持 OpenAI Chat Completions 和 Tool Calling 的模型 API

## 安装

```bash
cd /home/purplr/agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

编辑 `.env`：

```dotenv
LLM_API_KEY=你的密钥
LLM_MODEL=你的模型名称
LLM_BASE_URL=兼容服务的API地址
```

使用官方 OpenAI 时可以将 `LLM_BASE_URL` 留空。密钥文件 `.env` 已被 `.gitignore` 排除。

## 自动测试

测试不需要模型密钥，也不会调用外网：

```bash
cd /home/purplr/agent
.venv/bin/python -m unittest discover -s tests -v
```

## 对话测试

```bash
cd /home/purplr/agent
.venv/bin/python -m campus_pilot.cli
```

建议依次输入：

```text
下周五下午六点前要交软件工程作业，预计需要4小时，优先级高，请帮我记录。
列出我所有未完成的任务。
把软件工程作业标记为完成。
再列出未完成任务。
```

终端中的 `[MCP]` 行是模型实际决定调用工具的记录。任务数据默认保存在 `data/tasks.db`。

## 启动网页

```bash
cd /home/purplr/agent
.venv/bin/streamlit run campus_pilot/web.py
```

浏览器访问终端显示的地址，默认通常是 `http://localhost:8501`。网页左侧包含历史对话、任务统计和任务一览；聊天区会显示每次 MCP 工具调用及其参数。

第二阶段建议按顺序测试：

```text
列出我所有未完成的任务。
把软件工程作业的优先级改成高。
从今天起按每天2小时生成未来7天的学习计划。
删除软件工程作业。
确认删除。
```

最后两句用于验证删除操作的二次确认机制。

第三阶段建议继续测试：

```text
查询明天上海的天气，适合去图书馆吗？
结合天气和我的未完成任务，给出明天的学习建议。
从今天起按每天2小时生成7天学习计划，并导出为“本周学习计划.md”。
```

导出完成后刷新页面，即可从左侧“导出文件”区域下载 Markdown。天气数据来自 [Open-Meteo](https://open-meteo.com/)。

## 独立检查 MCP Server

可以通过 stdio 独立启动：

```bash
.venv/bin/python -m campus_pilot.mcp_server
```

也可以使用 MCP Inspector 检查工具定义：

```bash
.venv/bin/mcp dev campus_pilot/mcp_server.py:mcp --with-editable .
```

## 核心流程

```text
用户输入 → 大模型判断意图 → MCP Client → MCP Server 工具
       ← 大模型组织回答 ← 工具结果 ← SQLite 数据库
```

模型不能直接操作 SQLite；所有任务操作都通过 MCP 工具完成。
