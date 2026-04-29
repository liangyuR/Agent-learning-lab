from __future__ import annotations

from tools.base_tool import BaseTool
from tools.get_datatime import GetCurrentTimeTool
from tools.read_markdown_file import ReadMarkdownFileTool
from tools.query_db import QueryDbTool
from tools.http_tool import HttpRequestTool

from models import ToolCallRequest


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise ValueError(f"未知工具: {name}")
        return self._tools[name]

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def definitions(self) -> list[ToolCallRequest]:
        """供写入 system prompt 的工具列表（OpenAI function 形状）。"""
        return [t.to_definition() for t in self.list_tools()]


def build_default_registry() -> ToolRegistry:
    """项目默认注册表：在此集中注册所有内置工具。"""
    registry = ToolRegistry()
    registry.register(GetCurrentTimeTool())
    registry.register(ReadMarkdownFileTool())
    registry.register(QueryDbTool())
    registry.register(HttpRequestTool())
    return registry