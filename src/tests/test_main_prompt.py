"""测试指令文案与 parse_output。"""

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from main import (  # noqa: E402
    ParseOutputError,
    build_system_instruction,
    parse_output,
)


class TestBuildSystemInstruction(unittest.TestCase):
    def test_contains_json_field_names(self) -> None:
        p = build_system_instruction()
        self.assertIn("summary", p)
        self.assertIn("key_points", p)
        self.assertIn("risks", p)
        self.assertIn("next_actions", p)


class TestParseOutput(unittest.TestCase):
    def test_returns_dict_when_valid(self) -> None:
        payload = {
            "summary": "s",
            "key_points": ["a"],
            "risks": [],
            "next_actions": ["b"],
        }
        resp = SimpleNamespace(text=json.dumps(payload, ensure_ascii=False))
        out = parse_output(resp)
        self.assertEqual(out, payload)

    def test_strips_json_fence(self) -> None:
        body = '{"summary":"x","key_points":[],"risks":[],"next_actions":[]}'
        resp = SimpleNamespace(text=f"```json\n{body}\n```")
        out = parse_output(resp)
        self.assertEqual(
            out,
            {"summary": "x", "key_points": [], "risks": [], "next_actions": []},
        )

    def test_empty_text_raises(self) -> None:
        resp = SimpleNamespace(text="")
        with self.assertRaises(ParseOutputError) as ctx:
            parse_output(resp)
        self.assertIn("未返回", ctx.exception.message)

    def test_invalid_json_raises(self) -> None:
        raw = "not json at all"
        resp = SimpleNamespace(text=raw)
        with self.assertRaises(ParseOutputError) as ctx:
            parse_output(resp)
        self.assertIn("合法 JSON", ctx.exception.message)
        self.assertEqual(ctx.exception.raw, raw)

    def test_schema_mismatch_raises(self) -> None:
        resp = SimpleNamespace(text='{"summary":1,"key_points":[],"risks":[],"next_actions":[]}')
        with self.assertRaises(ParseOutputError) as ctx:
            parse_output(resp)
        self.assertIn("不符合约定", ctx.exception.message)


if __name__ == "__main__":
    unittest.main()
