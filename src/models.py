from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Any

class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., min_length=1, description="工具名称")
    args: dict[str, Any] = Field(..., description="工具参数")

    @field_validator("tool_name")
    def validate_tool_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("工具名称不能为空")
        return v


class ToolCallResponse(BaseModel):

class ToolResult(BaseModel):