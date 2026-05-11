"""测试工具注册表与 run_tool_invocation。"""

import sys
import unittest
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from models import ToolCallInvocation  # noqa: E402
from tool_registery import ToolRegistry, build_default_registry  # noqa: E402
from tool_runner import run_tool_invocation  # noqa: E402
from tools.get_datatime import GetCurrentTimeTool  # noqa: E402
from tools.http_tool import HttpRequestTool  # noqa: E402


class TestBaseToolDefinition(unittest.TestCase):
    def test_to_definition_shape(self) -> None:
        t = GetCurrentTimeTool()
        d = t.to_definition()
        self.assertEqual(d.name, "get_current_time")
        self.assertIn("timezone", d.parameters.properties)


class TestBuildDefaultRegistry(unittest.TestCase):
    def test_has_get_current_time(self) -> None:
        r = build_default_registry()
        t = r.get("get_current_time")
        self.assertIsInstance(t, GetCurrentTimeTool)

    def test_has_http_request(self) -> None:
        r = build_default_registry()
        t = r.get("http_request")
        self.assertIsInstance(t, HttpRequestTool)

    def test_definitions_non_empty(self) -> None:
        r = build_default_registry()
        defs = r.definitions()
        self.assertTrue(len(defs) >= 1)
        self.assertEqual(defs[0].name, "get_current_time")

    def test_api_tools_shape(self) -> None:
        r = build_default_registry()
        tools = r.api_tools()
        self.assertTrue(len(tools) >= 1)
        first = tools[0]
        self.assertEqual(first["type"], "function")
        self.assertEqual(first["function"]["name"], "get_current_time")
        self.assertIn("parameters", first["function"])
        self.assertNotIn("strict", first["function"])


class TestRunToolInvocation(unittest.TestCase):
    def test_ok(self) -> None:
        r = build_default_registry()
        out = run_tool_invocation(
            r,
            ToolCallInvocation(name="get_current_time", arguments={"timezone": "UTC"}),
        )
        self.assertTrue(out.ok)
        self.assertEqual(out.tool_name, "get_current_time")
        self.assertIn("datetime", out.data)

    def test_unknown_tool(self) -> None:
        r = ToolRegistry()
        r.register(GetCurrentTimeTool())
        out = run_tool_invocation(
            r,
            ToolCallInvocation(name="missing", arguments={}),
        )
        self.assertFalse(out.ok)
        self.assertIn("未知工具", out.error or "")


if __name__ == "__main__":
    unittest.main()
