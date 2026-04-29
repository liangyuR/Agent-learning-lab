"""测试 parser 模块的 JSON 抽取与 ToolCallResponse 解析。"""

import json
import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from parser import (  # noqa: E402
    ParserOutputError,
    extract_json_text,
    parse_tool_call_response,
)


class TestExtractJsonText(unittest.TestCase):
    def test_plain_json_object(self) -> None:
        s = '{"action": "final_answer", "answer": "ok"}'
        self.assertEqual(extract_json_text(s), s)

    def test_fenced_json(self) -> None:
        s = """```json
{"action": "final_answer", "answer": "hi"}
```"""
        obj = json.loads(extract_json_text(s))
        self.assertEqual(obj["action"], "final_answer")
        self.assertEqual(obj["answer"], "hi")

    def test_prose_before_and_after(self) -> None:
        s = '说明如下：{"action": "final_answer", "answer": "done"} 以上。'
        self.assertIn('"final_answer"', extract_json_text(s))

    def test_empty_raises(self) -> None:
        with self.assertRaises(ParserOutputError):
            extract_json_text("")
        with self.assertRaises(ParserOutputError):
            extract_json_text("   ")

    def test_no_brace_raises(self) -> None:
        with self.assertRaises(ParserOutputError):
            extract_json_text("只有文字没有 JSON")


class TestParseToolCallResponse(unittest.TestCase):
    def test_final_answer_plain(self) -> None:
        r = parse_tool_call_response('{"action": "final_answer", "answer": "hello"}')
        self.assertEqual(r.action, "final_answer")
        self.assertEqual(r.answer, "hello")
        self.assertIsNone(r.tool_call)

    def test_final_answer_fenced(self) -> None:
        text = """```json
{"action": "final_answer", "answer": "from fence"}
```"""
        r = parse_tool_call_response(text)
        self.assertEqual(r.answer, "from fence")

    def test_final_answer_with_prose(self) -> None:
        text = '好的。{"action": "final_answer", "answer": "x"} 结束。'
        r = parse_tool_call_response(text)
        self.assertEqual(r.answer, "x")

    def test_tool_call_invocation(self) -> None:
        payload = {
            "action": "tool_call",
            "tool_call": {
                "name": "get_current_time",
                "arguments": {"timezone": "UTC"},
            },
        }
        r = parse_tool_call_response(json.dumps(payload, ensure_ascii=False))
        self.assertEqual(r.action, "tool_call")
        assert r.tool_call is not None
        self.assertEqual(r.tool_call.name, "get_current_time")
        self.assertEqual(r.tool_call.arguments["timezone"], "UTC")

    def test_bad_json_raises(self) -> None:
        with self.assertRaises(ParserOutputError) as ctx:
            parse_tool_call_response('{"a": undefined}')
        self.assertIsInstance(ctx.exception.__cause__, json.JSONDecodeError)

    def test_inconsistent_action_raises(self) -> None:
        with self.assertRaises(ParserOutputError):
            parse_tool_call_response(
                '{"action": "final_answer", "answer": "", "tool_call": null}'
            )


if __name__ == "__main__":
    unittest.main()
