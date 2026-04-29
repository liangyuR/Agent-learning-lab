import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from dotenv import load_dotenv
from loguru import logger
from tenacity import Retrying, stop_after_attempt, wait_chain, wait_fixed

from models import ToolCallRequest, ToolResult
from parser import ParserOutputError, parse_tool_call_response
from tool_registery import build_default_registry
from tool_runner import run_tool_invocation


class ParseOutputError(Exception):
    """模型输出无法解析为约定 JSON 时使用，由 main() 统一处理。"""

    def __init__(self, message: str, raw: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.raw = raw


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gemini CLI 文本助手")
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


def run_agent_flow(client: genai.Client, question: str) -> int:
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

_MODEL_MAX_ATTEMPTS = 4
_MODEL_RETRY_WAIT_SEC = (2.0, 4.0, 8.0)


def call_model(
    client: genai.Client,
    system_instruction: str,
    user_content: str,
    *,
    max_output_tokens: int = 600,
) -> Any:
    def do_generate() -> Any:
        return client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                max_output_tokens=max_output_tokens,
            ),
        )

    def before_sleep(retry_state: Any) -> None:
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        wait_sec = float(getattr(retry_state, "upcoming_sleep", 0.0) or 0.0)
        logger.warning(
            "调用模型失败（第 {} 次尝试），{:.0f}s 后重试: {}",
            retry_state.attempt_number,
            wait_sec,
            exc,
        )

    retryer = Retrying(
        stop=stop_after_attempt(_MODEL_MAX_ATTEMPTS),
        wait=wait_chain(
            *[wait_fixed(s) for s in _MODEL_RETRY_WAIT_SEC],
        ),
        reraise=True,
        before_sleep=before_sleep,
    )
    return retryer(do_generate)


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

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("错误：未找到 GEMINI_API_KEY 或 GOOGLE_API_KEY", file=sys.stderr)
        return 1

    try:
        client = genai.Client()

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

        if args.mode == "agent":
            return run_agent_flow(client, question)

        system_instruction = build_system_instruction()
        user_content = build_user_content(question)
        response = call_model(client, system_instruction, user_content)

        parsed_response = parse_output(response)
        print(json.dumps(parsed_response, ensure_ascii=False, indent=2))
        return 0

    except ParseOutputError as e:
        print(f"解析模型输出失败: {e.message}", file=sys.stderr)
        if e.raw is not None:
            logger.debug("完整原始输出: {}", e.raw)
            preview = e.raw if len(e.raw) <= 1200 else e.raw[:1200] + "…"
            print(f"原始输出（节选）:\n{preview}", file=sys.stderr)
        return 3

    except Exception as e:
        print(f"调用 Gemini 失败: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())