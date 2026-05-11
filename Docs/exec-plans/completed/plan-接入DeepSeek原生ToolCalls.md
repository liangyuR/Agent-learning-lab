# 接入 DeepSeek 原生 Tool Calls 计划

## Summary

将当前 `--chat` 中“靠 prompt 要求模型输出 `{"action":"tool_call"}`”的软约束，升级为 DeepSeek Chat Completions 原生 `tools` / `tool_choice` / `tool_calls` 流程。工具调用由 API 返回的 `message.tool_calls` 驱动，本地执行工具后用原生 `role="tool"` 消息回传结果，再让模型生成自然语言最终回答。

参考官方文档：
- [DeepSeek Function Calling](https://api-docs.deepseek.com/guides/function_calling/)
- [DeepSeek Chat Completion API](https://api-docs.deepseek.com/api/create-chat-completion)
- [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)

## Key Changes

- 工具定义格式改为 API 原生结构：
  - 新增 `ToolRegistry.api_tools()`。
  - 把当前扁平 `ToolCallRequest` 转为 `{"type": "function", "function": {...}}`。
  - 保留现有 prompt 用 `definitions()`，避免破坏 `--mode agent`。
- DeepSeek 调用层支持工具参数：
  - `build_deepseek_chat_payload()` 增加可选参数 `tools`、`tool_choice`、`response_format`。
  - `call_chat_model()` 返回结构化 `ModelResponse`，同时保留 `.text` 兼容旧代码。
  - 新增响应字段：`content`、`tool_calls`、`finish_reason`。
- `--chat` 工具执行流程改为原生 Tool Calls：
  - 普通聊天使用 `tool_choice="auto"`。
  - 当响应包含 `tool_calls` 时，解析并执行本地工具。
  - 将 assistant 的 tool call 消息和本地 `role="tool"` 结果写入会话历史。
  - 再调用一次模型，生成给用户看的最终自然语言回答。
- 会话消息兼容原生 tool 消息：
  - 复用 `ChatMessage.metadata` 保存 `tool_call_id`、工具名、原始 arguments 和执行结果。
  - `chat_messages_to_api_messages()` 对新 tool 消息输出 DeepSeek 要求的 `role="tool"` 格式。
  - 旧会话中没有 `tool_call_id` 的 tool 消息降级为普通 user 上下文。

## Test Plan

- 单元测试：
  - 验证工具定义能转换成 DeepSeek `tools` 参数格式。
  - 验证 `build_deepseek_chat_payload()` 在传入工具时包含 `tools` 和 `tool_choice`。
  - 验证 `call_chat_model()` 能提取 `tool_calls`、`finish_reason`、`content`。
  - 验证 `complete_chat_turn()` 在收到 `tool_calls` 后执行工具、追加 tool 消息、二次调用模型并返回最终回答。
  - 验证无工具调用时仍保持普通多轮聊天行为。
- 回归测试：
  - `--mode analysis` 原有 JSON 摘要流程不变。
  - `--mode agent` 原有 prompt-tool 协议不变。
  - session 保存、加载、reset 行为不变。
- 手工验收：
  - 运行 `python src/main.py --chat --reset-session`。
  - 输入“现在是几点？”。
  - 期望本地调用 `get_current_time`，最终输出当前时间，而不是“我无法调用工具”。
  - 继续输入“刚才你查的是哪个时区？”。
  - 期望能基于历史回答工具使用的时区。

## Assumptions

- 第一版只在 `--chat` 接入 DeepSeek 原生 Tool Calls，`--mode agent` 暂不重构。
- 默认使用 `tool_choice="auto"`，先不增加复杂意图分类。
- 暂不启用 DeepSeek strict beta 模式；如后续需要更强参数约束，再切换 `DEEPSEEK_BASE_URL=https://api.deepseek.com/beta` 并给工具 schema 增加 `strict: true`。
- `response_format={"type":"json_object"}` 只用于需要结构化 JSON 内容的场景，不用于最终自然语言聊天回答。
