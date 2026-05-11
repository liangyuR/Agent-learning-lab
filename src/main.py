import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import httpx
from loguru import logger

from models import NativeToolCall, ToolCallRequest, ToolResult
from parser import ParserOutputError, parse_tool_call_response
from session.message import ChatMessage
from session.session import (
    SessionState,
    append_message,
    assert_safe_session_id,
    clear_session,
    load_or_create_session,
    save_session,
)
from tool_registery import build_default_registry
from tool_runner import run_tool_invocation

DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_DEEPSEEK_REASONING_EFFORT = "high"


@dataclass(frozen=True, init=False)
class ModelResponse:
    """Chat Completions 响应的最小结构；text 兼容旧调用方。"""

    content: str = ""
    tool_calls: list[NativeToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    reasoning_content: str | None = None

    def __init__(
        self,
        content: str = "",
        tool_calls: list[NativeToolCall] | None = None,
        finish_reason: str | None = None,
        reasoning_content: str | None = None,
        *,
        text: str | None = None,
    ) -> None:
        object.__setattr__(self, "content", content if text is None else text)
        object.__setattr__(self, "tool_calls", tool_calls or [])
        object.__setattr__(self, "finish_reason", finish_reason)
        object.__setattr__(self, "reasoning_content", reasoning_content)

    @property
    def text(self) -> str:
        return self.content


class ParseOutputError(Exception):
    """模型输出无法解析为约定 JSON 时使用，由 main() 统一处理。"""

    def __init__(self, message: str, raw: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.raw = raw


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DeepSeek CLI 文本助手")
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument(
        "--input",
        "-i",
        type=str,
        default=None,
        help="从命令行传入的问题（与 --file 互斥；都不传则进入交互输入）",
    )
    source.add_argument(
        "--file",
        "-f",
        type=str,
        default=None,
        metavar="PATH",
        help="从 UTF-8 文本文件读取待分析全文（与 --input 互斥）",
    )
    parser.add_argument(
        "--mode",
        choices=("analysis", "agent"),
        default="analysis",
        help="analysis：摘要 JSON；agent：注册工具 + ToolCallResponse 两轮对话",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="进入多轮对话 REPL（与 --input/--file 互斥）",
    )
    parser.add_argument(
        "--session-id",
        default="default",
        metavar="ID",
        help="会话文件名标识，对应 .sessions/<ID>.json，默认 default",
    )
    parser.add_argument(
        "--reset-session",
        action="store_true",
        help="启动前清空该会话（消息、摘要与 variables）",
    )
    return parser.parse_args(argv)


def read_input() -> str:
    return input("请输入问题: ")


def read_text_file(path: str) -> str:
    """以 UTF-8 读取文件全文。"""
    return Path(path).read_text(encoding="utf-8")


def build_system_instruction() -> str:
    return """你是一个文本分析助手。
请根据用户输入输出严格 JSON。
不要输出 Markdown，不要输出额外解释。

JSON 必须包含以下字段：
- summary: 字符串
- key_points: 字符串数组
- risks: 字符串数组
- next_actions: 字符串数组
"""

def build_user_content(question: str) -> str:
    return f"""请分析下面这段内容，并按要求返回结果：

{question}
"""


def build_chat_system_instruction(
    definitions: list[ToolCallRequest] | None = None,
) -> str:
    """多轮对话使用的中文 system prompt；工具能力由 API 原生 tools 承载。"""
    base = """你是一个友好的中文助手。
请根据对话历史简洁、准确地回答用户。
不要编造事实；不清楚时请说明。"""
    if not definitions:
        return base

    return f"""{base}

你可以使用 API 提供的本地工具。用户可能会用工具类名描述能力，例如 GetCurrentTimeTool；实际工具名以 API tools 定义为准。
当用户问题需要当前时间、文件内容、HTTP 请求、数据库查询等外部或实时信息时，应优先调用合适工具，不要声称自己无法调用工具。
工具结果会以 tool 消息提供；收到工具结果后，请直接给用户自然、简洁的中文最终回答。"""


def default_sessions_dir() -> Path:
    """项目根目录下的 .sessions（与 main.py 位于 src/ 的上一级对应）。"""
    return Path(__file__).resolve().parents[1] / ".sessions"


_TOOL_RESULT_MAX_MODEL_CHARS = 6000
_HISTORICAL_TOOL_RESULT_MAX_MODEL_CHARS = 1200


def truncate_text_for_model(text: str, max_chars: int) -> str:
    """限制塞回模型的工具文本长度，避免大网页把 Chat Completion 请求打爆。"""
    if len(text) <= max_chars:
        return text
    omitted = len(text) - max_chars
    return f"{text[:max_chars]}\n\n[内容已截断，省略 {omitted} 个字符]"


def build_tool_result_content(tool_result: ToolResult) -> str:
    """把工具结果整理成可放入对话历史的文本。"""
    payload = tool_result.model_dump(mode="json", exclude_none=True)
    content = json.dumps(payload, ensure_ascii=False)
    return truncate_text_for_model(content, _TOOL_RESULT_MAX_MODEL_CHARS)


def native_tool_call_to_api_dict(tool_call: NativeToolCall) -> dict[str, Any]:
    """转为可写入 assistant 消息的原生 tool_call 结构。"""
    return {
        "id": tool_call.id,
        "type": "function",
        "function": {
            "name": tool_call.name,
            "arguments": json.dumps(tool_call.arguments, ensure_ascii=False),
        },
    }


def chat_messages_to_api_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    """将 ChatMessage 列表转为 Chat Completions 的 role/content 列表。"""
    api_messages: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            tool_call_id = message.metadata.get("tool_call_id")
            if isinstance(tool_call_id, str) and tool_call_id:
                api_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": truncate_text_for_model(
                            message.content,
                            _TOOL_RESULT_MAX_MODEL_CHARS,
                        ),
                    }
                )
                continue

            content = message.content
            if message.tool_name:
                content = f"[历史工具结果: {message.tool_name}]\n{content}"
            content = truncate_text_for_model(
                content,
                _HISTORICAL_TOOL_RESULT_MAX_MODEL_CHARS,
            )
            api_messages.append({"role": "user", "content": content})
            continue

        if message.role == "assistant" and isinstance(
            message.metadata.get("tool_calls"),
            list,
        ):
            tool_calls = message.metadata["tool_calls"]
            api_message: dict[str, Any] = {
                "role": "assistant",
                "content": message.content,
                "tool_calls": tool_calls,
            }
            reasoning_content = message.metadata.get("reasoning_content")
            if isinstance(reasoning_content, str):
                api_message["reasoning_content"] = reasoning_content
            api_messages.append(api_message)
            continue

        api_message = {"role": message.role, "content": message.content}
        if message.role == "assistant":
            reasoning_content = message.metadata.get("reasoning_content")
            if isinstance(reasoning_content, str):
                api_message["reasoning_content"] = reasoning_content
        api_messages.append(api_message)
    return api_messages


def ensure_chat_system_message(
    state: SessionState,
    definitions: list[ToolCallRequest] | None = None,
) -> None:
    """若无 system 消息则插入；旧版内置 prompt 会升级为原生 tools prompt。"""
    desired = build_chat_system_instruction(definitions)
    system_messages = [m for m in state.messages if m.role == "system"]
    if not system_messages:
        state.messages.insert(
            0,
            ChatMessage(
                role="system",
                content=desired,
                metadata={"managed_by": "agent_learning_lab"},
            ),
        )
        return

    first_system = system_messages[0]
    if (
        first_system.metadata.get("managed_by") == "agent_learning_lab"
        or "tool_call" in first_system.content
    ):
        first_system.content = desired
        first_system.metadata["managed_by"] = "agent_learning_lab"


_CHAT_MAX_OUTPUT_TOKENS = 2048
_CHAT_MAX_TOOL_CALLS_DEFAULT = 10


def _chat_max_tool_calls() -> int:
    """每轮允许的工具调用轮数上限（模型返回 tool_calls 并本地执行算一轮）。默认 10，可用 CHAT_MAX_TOOL_CALLS 覆盖。"""
    raw = os.getenv("CHAT_MAX_TOOL_CALLS", str(_CHAT_MAX_TOOL_CALLS_DEFAULT)).strip()
    try:
        n = int(raw)
    except ValueError:
        return _CHAT_MAX_TOOL_CALLS_DEFAULT
    return max(1, n)


def complete_chat_turn(
    client: httpx.Client,
    state: SessionState,
    registry: Any,
) -> str:
    """完成一个用户回合：必要时执行原生 tool_calls，再返回最终文本。"""
    max_tool_rounds = _chat_max_tool_calls()
    for _ in range(max_tool_rounds):
        response = call_chat_model(
            client,
            chat_messages_to_api_messages(state.messages),
            max_output_tokens=_CHAT_MAX_OUTPUT_TOKENS,
            tools=registry.api_tools(),
            tool_choice="auto",
        )

        if not response.tool_calls:
            answer = response.content.strip()
            metadata: dict[str, Any] = {}
            if response.reasoning_content is not None:
                metadata["reasoning_content"] = response.reasoning_content
            append_message(
                state,
                ChatMessage(
                    role="assistant",
                    content=answer,
                    metadata=metadata,
                ),
            )
            return answer

        api_tool_calls = [
            native_tool_call_to_api_dict(tool_call)
            for tool_call in response.tool_calls
        ]
        assistant_metadata: dict[str, Any] = {"tool_calls": api_tool_calls}
        if response.reasoning_content is not None:
            assistant_metadata["reasoning_content"] = response.reasoning_content
        append_message(
            state,
            ChatMessage(
                role="assistant",
                content=response.content,
                metadata=assistant_metadata,
            ),
        )
        for tool_call in response.tool_calls:
            tool_result = run_tool_invocation(registry, tool_call.to_invocation())
            append_message(
                state,
                ChatMessage(
                    role="tool",
                    content=build_tool_result_content(tool_result),
                    tool_name=tool_result.tool_name,
                    metadata={
                        "tool_call_id": tool_call.id,
                        "tool_name": tool_call.name,
                        "arguments": tool_call.arguments,
                        "result": tool_result.model_dump(
                            mode="json",
                            exclude_none=True,
                        ),
                    },
                ),
            )

    fallback = (
        f"工具调用次数过多（每轮最多 {max_tool_rounds} 次），"
        "已停止本轮处理。请换一种方式提问。"
    )
    append_message(state, ChatMessage(role="assistant", content=fallback))
    return fallback


def run_chat_loop(
    client: httpx.Client,
    session_id: str,
    reset_session: bool,
) -> int:
    """
    多轮对话 REPL：加载或创建会话，循环读用户输入，调用模型并落盘。

    退出：用户输入 /exit 或 /quit；EOF 视为退出。
    """
    sessions_dir = default_sessions_dir()
    registry = build_default_registry()
    state = load_or_create_session(session_id, sessions_dir)
    if reset_session:
        clear_session(state, clear_variables=True)
        save_session(state, sessions_dir)
    ensure_chat_system_message(state, registry.definitions())
    save_session(state, sessions_dir)

    print("多轮对话（输入 /exit 或 /quit 退出）", file=sys.stderr)
    while True:
        try:
            line = input("你: ")
        except EOFError:
            print("", file=sys.stderr)
            break
        user_text = line.strip()
        if not user_text:
            continue
        if user_text in ("/exit", "/quit"):
            break

        user_msg = ChatMessage(role="user", content=user_text)
        append_message(state, user_msg)
        try:
            save_session(state, sessions_dir)
        except OSError as e:
            print(f"错误：无法保存会话: {e}", file=sys.stderr)
            return 1

        try:
            assistant_text = complete_chat_turn(
                client,
                state,
                registry,
            )
        except Exception as e:
            print(f"调用 DeepSeek 失败: {e}", file=sys.stderr)
            continue

        print(assistant_text)
        try:
            save_session(state, sessions_dir)
        except OSError as e:
            print(f"错误：无法保存会话: {e}", file=sys.stderr)
            return 1

    return 0


def build_agent_system_instruction(definitions: list[ToolCallRequest]) -> str:
    """列出已注册工具定义，并要求模型只输出 ToolCallResponse JSON。"""
    defs_json = json.dumps(
        [d.model_dump() for d in definitions],
        ensure_ascii=False,
        indent=2,
    )
    return f"""你是助手。用户会提出问题。

可用工具（JSON 数组，每项为 function 定义）如下：
{defs_json}

你必须只输出一个 JSON 对象（不要 Markdown、不要解释），字段如下：
- action: 字符串，取值为 "final_answer" 或 "tool_call"
- 当 action 为 "final_answer" 时：必须设置 answer（给用户的完整中文答复），不要设置 tool_call
- 当 action 为 "tool_call" 时：必须设置 tool_call 为对象 {{"name": "<工具名>", "arguments": {{...}}}}，不要设置 answer

需要工具时先输出 tool_call；你会在下一轮收到工具结果后再输出 final_answer。
"""


def build_agent_user_turn(question: str) -> str:
    return f"用户问题：\n{question}\n\n请只输出一个 JSON（可先 tool_call）。"


def build_agent_followup_after_tool(
    original_question: str,
    tool_result: ToolResult,
) -> str:
    """把工具结果交给模型，要求其输出 final_answer JSON。"""
    payload = tool_result.model_dump(mode="json", exclude_none=True)
    return (
        f"用户原始问题：\n{original_question}\n\n"
        f"工具 {tool_result.tool_name} 返回：\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "请根据工具输出给出对用户的最终答复。"
        "只输出 JSON：action 为 final_answer，answer 为完整中文回答。"
    )


def run_agent_flow(client: httpx.Client, question: str) -> int:
    """一轮模型可能 tool_call，本地执行后再调一次模型要 final_answer。"""
    registry = build_default_registry()
    system_instruction = build_agent_system_instruction(registry.definitions())
    first = call_model(
        client,
        system_instruction,
        build_agent_user_turn(question),
        max_output_tokens=1024,
    )
    text1 = (getattr(first, "text", None) or "").strip()
    try:
        step1 = parse_tool_call_response(text1)
    except ParserOutputError as e:
        print(f"解析模型输出失败: {e}", file=sys.stderr)
        logger.debug("agent 首轮原始输出: {}", text1)
        return 3

    if step1.action == "final_answer":
        print(step1.answer or "")
        return 0

    assert step1.tool_call is not None
    tool_result = run_tool_invocation(registry, step1.tool_call)
    second = call_model(
        client,
        system_instruction,
        build_agent_followup_after_tool(question, tool_result),
        max_output_tokens=1024,
    )
    text2 = (getattr(second, "text", None) or "").strip()
    try:
        step2 = parse_tool_call_response(text2)
    except ParserOutputError:
        print(
            "解析第二轮输出失败，改为输出工具原始结果（JSON）。",
            file=sys.stderr,
        )
        print(json.dumps(tool_result.model_dump(), ensure_ascii=False, indent=2))
        return 0

    if step2.action == "final_answer" and step2.answer:
        print(step2.answer)
        return 0

    print(
        "模型未返回 final_answer，输出工具结果（JSON）。",
        file=sys.stderr,
    )
    print(json.dumps(tool_result.model_dump(), ensure_ascii=False, indent=2))
    return 0

def build_deepseek_client(api_key: str) -> httpx.Client:
    """创建 DeepSeek OpenAI-compatible Chat Completions 客户端。"""
    base_url = os.getenv("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
    return httpx.Client(
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=60.0,
    )


def build_deepseek_chat_payload(
    messages: list[dict[str, Any]],
    max_output_tokens: int,
    *,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    构建 DeepSeek 对话请求体；messages 为 Chat Completions 的 role/content 列表。

    默认启用官方 thinking 模式。
    """
    model = os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
    reasoning_effort = os.getenv(
        "DEEPSEEK_REASONING_EFFORT",
        DEFAULT_DEEPSEEK_REASONING_EFFORT,
    )
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "max_tokens": max_output_tokens,
        "reasoning_effort": reasoning_effort,
        "thinking": {"type": "enabled"},
    }
    if tools is not None:
        payload["tools"] = tools
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    if response_format is not None:
        payload["response_format"] = response_format
    return payload


def build_deepseek_payload(
    system_instruction: str,
    user_content: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    """构建 system + user 两消息请求体，内部复用 build_deepseek_chat_payload。"""
    return build_deepseek_chat_payload(
        [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content},
        ],
        max_output_tokens,
    )


def extract_deepseek_text(data: dict[str, Any]) -> str:
    """从 DeepSeek Chat Completions 响应中取最终回答 content。"""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("DeepSeek 响应缺少 choices")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("DeepSeek 响应 choices[0] 格式异常")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("DeepSeek 响应缺少 message")

    content = message.get("content")
    if content is None:
        return ""
    if not isinstance(content, str):
        raise ValueError("DeepSeek 响应 content 不是字符串")
    return content


def parse_native_tool_call(raw: Any) -> NativeToolCall:
    """解析 DeepSeek/OpenAI 原生 tool_calls 条目。"""
    if not isinstance(raw, dict):
        raise ValueError("DeepSeek tool_call 格式异常")

    call_id = raw.get("id")
    if not isinstance(call_id, str) or not call_id:
        raise ValueError("DeepSeek tool_call 缺少 id")

    function = raw.get("function")
    if not isinstance(function, dict):
        raise ValueError("DeepSeek tool_call 缺少 function")

    name = function.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError("DeepSeek tool_call 缺少 function.name")

    raw_arguments = function.get("arguments")
    if raw_arguments in (None, ""):
        arguments: dict[str, Any] = {}
    elif isinstance(raw_arguments, str):
        parsed = json.loads(raw_arguments)
        if not isinstance(parsed, dict):
            raise ValueError("DeepSeek tool_call arguments 不是 JSON 对象")
        arguments = parsed
    elif isinstance(raw_arguments, dict):
        arguments = raw_arguments
    else:
        raise ValueError("DeepSeek tool_call arguments 格式异常")

    return NativeToolCall(id=call_id, name=name, arguments=arguments)


def extract_deepseek_model_response(data: dict[str, Any]) -> ModelResponse:
    """从 DeepSeek Chat Completions 响应中提取 content、tool_calls 和 finish_reason。"""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("DeepSeek 响应缺少 choices")

    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("DeepSeek 响应 choices[0] 格式异常")

    finish_reason = first_choice.get("finish_reason")
    if finish_reason is not None and not isinstance(finish_reason, str):
        raise ValueError("DeepSeek 响应 finish_reason 格式异常")

    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("DeepSeek 响应缺少 message")

    content = message.get("content")
    if content is None:
        content = ""
    if not isinstance(content, str):
        raise ValueError("DeepSeek 响应 content 不是字符串")

    reasoning_content = message.get("reasoning_content")
    if reasoning_content is not None and not isinstance(reasoning_content, str):
        raise ValueError("DeepSeek 响应 reasoning_content 不是字符串")

    raw_tool_calls = message.get("tool_calls") or []
    if not isinstance(raw_tool_calls, list):
        raise ValueError("DeepSeek 响应 tool_calls 格式异常")
    tool_calls = [parse_native_tool_call(raw) for raw in raw_tool_calls]

    return ModelResponse(
        content=content,
        tool_calls=tool_calls,
        finish_reason=finish_reason,
        reasoning_content=reasoning_content,
    )


def call_chat_model(
    client: httpx.Client,
    messages: list[dict[str, Any]],
    *,
    max_output_tokens: int = 600,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    response_format: dict[str, Any] | None = None,
) -> ModelResponse:
    """按完整 messages 调用 Chat Completions；失败立即抛出，不重试。"""

    response = client.post(
        "/chat/completions",
        json=build_deepseek_chat_payload(
            messages,
            max_output_tokens,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
        ),
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        body = response.text
        preview = body if len(body) <= 1200 else body[:1200] + "..."
        raise RuntimeError(
            f"DeepSeek HTTP {response.status_code}: {preview}"
        ) from e
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("DeepSeek 响应不是 JSON 对象")
    return extract_deepseek_model_response(data)


def call_model(
    client: httpx.Client,
    system_instruction: str,
    user_content: str,
    *,
    max_output_tokens: int = 600,
) -> ModelResponse:
    """单轮 system + user，内部转为 messages 后调用 call_chat_model。"""
    return call_chat_model(
        client,
        [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user_content},
        ],
        max_output_tokens=max_output_tokens,
    )


def _extract_json_text(text: str) -> str:
    """从模型原文中提取 JSON 子串（兼容 ```json 围栏）。"""
    raw = text.strip()
    if not raw:
        return raw
    fence = re.match(
        r"^```(?:json)?\s*\n?([\s\S]*?)\n?```\s*$",
        raw,
        re.IGNORECASE,
    )
    if fence:
        raw = fence.group(1).strip()
    if not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start : end + 1]
    return raw


def parse_output(response: Any) -> dict[str, Any]:
    """解析模型输出为业务 dict。失败时抛出 ParseOutputError，由 main() 写 stderr 并设退出码。"""
    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise ParseOutputError("模型未返回任何文本")
    logger.debug(f"Raw response: {text}")
    snippet = _extract_json_text(text)
    try:
        data = json.loads(snippet)
    except json.JSONDecodeError:
        raise ParseOutputError("模型输出不是合法 JSON", raw=text) from None
    if not validate_data(data):
        raise ParseOutputError("模型 JSON 不符合约定的字段或类型", raw=text)
    return data


def validate_data(data: dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False

    # Check keys existence
    required_keys = ["summary", "key_points", "risks", "next_actions"]
    for key in required_keys:
        if key not in data:
            return False

    # Check summary type
    if not isinstance(data["summary"], str):
        return False

    # Validate list fields and their content types
    for key in ["key_points", "risks", "next_actions"]:
        value = data[key]
        if not isinstance(value, list):
            return False
        if not all(isinstance(item, str) for item in value):
            return False

    return True

def main() -> int:
    load_dotenv()
    args = parse_args()

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("错误：未找到 DEEPSEEK_API_KEY", file=sys.stderr)
        return 1

    if args.chat:
        if args.file is not None or args.input is not None:
            print("错误：--chat 不能与 --file/--input 同时使用", file=sys.stderr)
            return 1
        try:
            assert_safe_session_id(args.session_id)
        except ValueError as e:
            print(f"错误：无效的 session_id: {e}", file=sys.stderr)
            return 1
        client = build_deepseek_client(api_key)
        try:
            return run_chat_loop(
                client,
                args.session_id,
                args.reset_session,
            )
        finally:
            client.close()

    try:
        if args.file is not None:
            try:
                question = read_text_file(args.file).strip()
            except OSError as e:
                print(f"错误：无法读取文件 {args.file}: {e}", file=sys.stderr)
                return 1
            except UnicodeDecodeError:
                print(f"错误：文件不是合法 UTF-8: {args.file}", file=sys.stderr)
                return 1
            if not question:
                print("错误：文件内容不能为空", file=sys.stderr)
                return 1
        elif args.input is not None:
            question = args.input.strip()
            if not question:
                print("错误：--input 不能为空", file=sys.stderr)
                return 1
        else:
            question = read_input().strip()
            if question == "":
                print("错误：问题不能为空", file=sys.stderr)
                return 1

        client = build_deepseek_client(api_key)
        try:
            if args.mode == "agent":
                return run_agent_flow(client, question)

            system_instruction = build_system_instruction()
            user_content = build_user_content(question)
            response = call_model(client, system_instruction, user_content)

            parsed_response = parse_output(response)
            print(json.dumps(parsed_response, ensure_ascii=False, indent=2))
            return 0
        finally:
            client.close()

    except ParseOutputError as e:
        print(f"解析模型输出失败: {e.message}", file=sys.stderr)
        if e.raw is not None:
            logger.debug("完整原始输出: {}", e.raw)
            preview = e.raw if len(e.raw) <= 1200 else e.raw[:1200] + "…"
            print(f"原始输出（节选）:\n{preview}", file=sys.stderr)
        return 3

    except Exception as e:
        print(f"调用 DeepSeek 失败: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
