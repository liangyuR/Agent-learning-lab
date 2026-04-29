"""根据 ToolCallInvocation 在注册表中执行工具并产出 ToolResult。"""

from pydantic import ValidationError

from models import ToolCallInvocation, ToolResult
from tool_registery import ToolRegistry

from loguru import logger


def run_tool_invocation(
    registry: ToolRegistry,
    inv: ToolCallInvocation,
) -> ToolResult:
    """查找工具、校验参数、调用 run；失败时返回 ok=False 的 ToolResult。"""
    logger.debug(f"[TOOL CALL] {inv.name} {inv.arguments}")

    result: ToolResult
    try:
        tool = registry.get(inv.name)
    except ValueError as e:
        result = ToolResult(ok=False, tool_name=inv.name, error=str(e))
    else:
        try:
            args = tool.input_model.model_validate(inv.arguments)
        except ValidationError as e:
            result = ToolResult(ok=False, tool_name=inv.name, error=str(e))
        else:
            try:
                data = tool.run(args)
                result = ToolResult(ok=True, tool_name=inv.name, data=data)
            except Exception as e:
                result = ToolResult(ok=False, tool_name=inv.name, error=str(e))

    if result.ok:
        logger.debug("[TOOL RESULT] ok=True")
    else:
        logger.debug(f"[TOOL RESULT] ok=False error={result.error}")
    return result
