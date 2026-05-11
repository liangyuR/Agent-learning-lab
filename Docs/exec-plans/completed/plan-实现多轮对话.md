# 多轮对话实现计划

## Summary

基于当前项目，下一步建议实现一个最小可用的 CLI 多轮对话能力：用户进入 `--chat` 模式后持续输入消息，程序保存历史消息，并把 `system + 历史 user/assistant 消息 + 当前 user 消息` 一起发给 DeepSeek。会话持久化到 `.sessions/<session_id>.json`，为后续上下文压缩、tool use、RAG 打基础。

## Key Changes

- 补全 `src/session/`：
  - `ChatMessage` 继续表示单条消息，包含 `role/content/created_at`。
  - `SessionState` 改成可序列化模型，字段固定为 `session_id/messages/summary/variables`。
  - 新增会话读写能力：创建、加载、保存、追加消息、清空会话。
- 调整模型调用接口：
  - 保留现有单轮 `call_model()`，避免破坏已有测试。
  - 新增 `call_chat_model(client, messages, max_output_tokens=...)`。
  - `build_deepseek_payload()` 支持直接传入完整 messages，而不是只支持 `system_instruction + user_content`。
- 新增 CLI 参数：
  - `--chat`：进入多轮对话 REPL。
  - `--session-id default`：指定会话文件，默认 `default`。
  - `--reset-session`：启动前清空该 session。
  - 退出命令：`/exit` 或 `/quit`。
- 多轮对话流程：
  - 启动时加载 `.sessions/<session_id>.json`，不存在则创建。
  - 如果没有 system 消息，插入一个通用中文助手 system prompt。
  - 每轮读取用户输入，追加 `user` 消息。
  - 调用 DeepSeek，打印 assistant 回复到 stdout。
  - 追加 `assistant` 消息并保存 session。
  - API 错误输出 stderr，本轮 user 消息不应丢失，可保存在 session 里方便排查。

## Implementation Guide

1. 先修会话模型
  把 `src/session/session.py` 从类型占位改成真正的 Pydantic 模型，并实现 session 文件读写。路径固定为项目根目录下 `.sessions/`，JSON 使用 UTF-8 和 `ensure_ascii=False`。
2. 再改 DeepSeek payload
  抽出一个 `build_deepseek_chat_payload(messages, max_output_tokens)`，让 `call_chat_model()` 使用它。现有 `call_model()` 可以内部组装两条消息后复用这个新函数。
3. 接入 CLI
  在 `parse_args()` 加 `--chat/--session-id/--reset-session`。`main()` 中优先判断 `args.chat`，进入 `run_chat_loop(client, session_id, reset_session)`。
4. 保持职责分离
  REPL 只负责读取输入和打印输出；session 模块只负责状态；DeepSeek 调用只负责 HTTP；prompt 构建单独保留函数，例如 `build_chat_system_instruction()`。
5. 暂不做 summary memory
  第一版只保留完整 messages。等功能跑通后，再加“超过 N 轮后压缩旧上下文到 summary”的能力。

## Test Plan

- 新增 `src/tests/test_session.py`：
  - 新 session 默认字段正确。
  - 追加 user/assistant 消息后可保存和重新加载。
  - `reset` 会清空旧消息。
  - session id 不允许包含路径穿越字符，例如 `../x`。
- 扩展 `test_main_retry.py`：
  - 验证 `call_chat_model()` 发送完整 messages。
  - 验证重试逻辑仍然生效。
- 扩展 `test_main_args.py`：
  - `--chat` 能被解析。
  - `--session-id abc` 默认值和指定值正确。
  - `--reset-session` 是布尔开关。
- 手工验收：
  - 第一句：“我叫小明。”
  - 第二句：“我叫什么？”
  - 期望模型能基于历史回答“小明”。
  - 退出后重新运行同一 `--session-id`，继续能记住历史。

## Assumptions

- 第一版目标是 CLI 多轮对话，不先做 Web UI。
- 会话需要落盘保存到 `.sessions/`，方便学习上下文管理。
- 当前 `analysis` 和 `agent` 单轮模式继续保留，不和 `--chat` 混在一起。
- 上下文压缩、token 预算、summary memory 放到下一阶段实现。
- 当前环境里 `python`/`py` 命令未识别，实际验证时优先使用项目虚拟环境或 `python3 -m unittest discover -s src/tests`。

