"""测试 models 中的工具定义模型。"""

import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pydantic import ValidationError  # noqa: E402

from models import (  # noqa: E402
    ToolCallInvocation,
    ToolCallRequest,
    ToolCallResponse,
    ToolFunctionParameters,
    ToolResult,
)


class TestToolCallRequest(unittest.TestCase):
    def test_get_weather_example_matches_openai_shape(self) -> None:
        """与 models.py 顶部注释中的 OpenAI function 示例一致。"""
        raw = {
            "type": "function",
            "name": "get_weather",
            "description": "Retrieves current weather for the given location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City and country e.g. Bogotá, Colombia",
                    },
                    "units": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                        "description": (
                            "Units the temperature will be returned in."
                        ),
                    },
                },
                "required": ["location", "units"],
                "additionalProperties": False,
            },
            "strict": True,
        }
        req = ToolCallRequest.model_validate(raw)
        self.assertEqual(req.type, "function")
        self.assertEqual(req.name, "get_weather")
        self.assertTrue(req.strict)
        self.assertEqual(req.parameters.required, ["location", "units"])
        self.assertIn("location", req.parameters.properties)

    def test_defaults(self) -> None:
        req = ToolCallRequest(
            name="noop",
            description="Does nothing.",
            parameters=ToolFunctionParameters(),
        )
        self.assertEqual(req.type, "function")
        self.assertTrue(req.strict)
        self.assertEqual(req.parameters.type, "object")
        self.assertFalse(req.parameters.additionalProperties)


class TestToolCallResponse(unittest.TestCase):
    def test_final_answer_ok(self) -> None:
        r = ToolCallResponse(action="final_answer", answer="done")
        self.assertIsNone(r.tool_call)

    def test_tool_call_requires_payload(self) -> None:
        with self.assertRaises(ValidationError):
            ToolCallResponse.model_validate({"action": "tool_call"})

    def test_tool_call_with_invocation_ok(self) -> None:
        r = ToolCallResponse(
            action="tool_call",
            tool_call=ToolCallInvocation(
                name="get_current_time",
                arguments={"timezone": "Asia/Shanghai"},
            ),
        )
        self.assertIsNone(r.answer)
        assert r.tool_call is not None
        self.assertEqual(r.tool_call.name, "get_current_time")

    def test_final_answer_empty_string_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ToolCallResponse(action="final_answer", answer="   ")


class TestToolResult(unittest.TestCase):
    def test_ok_with_data(self) -> None:
        r = ToolResult(ok=True, tool_name="t", data={"x": 1})
        self.assertTrue(r.ok)

    def test_fail_requires_error_and_empty_data(self) -> None:
        with self.assertRaises(ValidationError):
            ToolResult(ok=False, tool_name="t", data={"x": 1}, error="e")
        with self.assertRaises(ValidationError):
            ToolResult(ok=False, tool_name="t", error="   ")
        r = ToolResult(ok=False, tool_name="t", error="boom", data={})
        self.assertFalse(r.ok)


if __name__ == "__main__":
    unittest.main()
