"""从模型输出文本中抽取 JSON 并解析为 ToolCallResponse。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from models import ToolCallResponse


class ParserOutputError(Exception):
    """无法从文本中解析出合法的 ToolCallResponse 结构化输出。"""


def _slice_balanced_object(s: str, start: int) -> str:
    """从 s[start]（应为 '{'）起截取与之匹配的 JSON 对象子串。"""
    depth = 0
    i = start
    in_string = False
    escape = False
    quote = ""

    while i < len(s):
        c = s[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == quote:
                in_string = False
        else:
            if c in ('"', "'"):
                in_string = True
                quote = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
        i += 1

    raise ParserOutputError("未找到成对的 JSON 大括号")


def _strip_markdown_fence(text: str) -> str:
    """若存在 ``` / ```json 围栏则返回围栏内正文，否则返回原文。"""
    stripped = text.strip()
    if "```" not in stripped:
        return stripped

    start = stripped.find("```")
    if start < 0:
        return stripped
    after_open = stripped[start + 3 :].lstrip()
    lower = after_open.lower()
    if lower.startswith("json"):
        after_open = after_open[4:].lstrip()
    elif after_open.startswith("\n"):
        after_open = after_open.lstrip("\n")

    close = after_open.find("```")
    if close < 0:
        raise ParserOutputError("Markdown 代码围栏未闭合")

    return after_open[:close].strip()


def extract_json_text(text: str) -> str:
    """从模型原文中取出一段可交给 json.loads 的 JSON 对象字符串。"""
    if not text or not text.strip():
        raise ParserOutputError("输入为空")

    inner = _strip_markdown_fence(text)
    brace_at = inner.find("{")
    if brace_at < 0:
        raise ParserOutputError("未找到 JSON 对象起始 '{'")

    return _slice_balanced_object(inner, brace_at)


def parse_tool_call_response(text: str) -> ToolCallResponse:
    """抽取 JSON 并校验为 ToolCallResponse。"""
    try:
        raw: Any = json.loads(extract_json_text(text))
    except json.JSONDecodeError as e:
        raise ParserOutputError("JSON 解析失败") from e

    try:
        return ToolCallResponse.model_validate(raw)
    except ValidationError as e:
        raise ParserOutputError("与 ToolCallResponse 结构不一致") from e
