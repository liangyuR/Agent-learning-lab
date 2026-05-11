# {
#   "type": "function",
#   "name": "get_weather",
#   "description": "Retrieves current weather for the given location.",
#   "parameters": {
#     "type": "object",
#     "properties": {
#       "location": {
#         "type": "string",
#         "description": "City and country e.g. Bogotá, Colombia"
#       },
#       "units": {
#         "type": "string",
#         "enum": ["celsius", "fahrenheit"],
#         "description": "Units the temperature will be returned in."
#       }
#     },
#     "required": ["location", "units"],
#     "additionalProperties": false
#   },
#   "strict": true
# }

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ToolFunctionParameters(BaseModel):
    """与 ChatGPT / OpenAI function.parameters 的 JSON Schema 子集对齐。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["object"] = Field(
        default="object",
        description="根类型，一般为 object",
    )
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="各参数的 JSON Schema 定义",
    )
    required: list[str] = Field(
        default_factory=list,
        description="必填参数名列表",
    )
    additionalProperties: bool = Field(
        default=False,
        description="是否允许未在 properties 中声明的额外字段",
    )


class ToolCallRequest(BaseModel):
    """与 OpenAI Chat Completions 中单个 function 工具定义对齐（非对话里的 tool_calls 执行项）。"""

    model_config = ConfigDict(extra="forbid")

    type: Literal["function"] = Field(
        default="function",
        description="固定为 function",
    )
    name: str = Field(..., min_length=1, description="工具名称，如 get_weather")
    description: str = Field(..., min_length=1, description="工具用途说明")
    parameters: ToolFunctionParameters = Field(..., description="参数的 JSON Schema")
    strict: bool = Field(default=True, description="是否启用严格模式")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("工具名称不能为空")
        return v.strip()


class ToolCallInvocation(BaseModel):
    """模型决定调用工具时给出的名称与参数（非工具 JSON Schema 定义）。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, description="已注册工具名，如 get_current_time")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="传给工具的参数，需符合该工具的 input_model",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("工具名称不能为空")
        return v.strip()


class NativeToolCall(BaseModel):
    """DeepSeek/OpenAI 原生 tool_calls 中的单个 function 调用。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, description="API 返回的 tool_call_id")
    name: str = Field(..., min_length=1, description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="工具参数")

    def to_invocation(self) -> ToolCallInvocation:
        """转为项目内部已有的 ToolCallInvocation。"""
        return ToolCallInvocation(name=self.name, arguments=self.arguments)


class ToolCallResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["final_answer", "tool_call"]
    answer: str | None = None
    tool_call: ToolCallInvocation | None = None

    @model_validator(mode="after")
    def validate_action_payload(self):
        if self.action == "final_answer":
            if not self.answer or not self.answer.strip():
                raise ValueError("answer 不能为空")
            if self.tool_call is not None:
                raise ValueError("tool_call 不能与 answer 同时存在")

        if self.action == "tool_call":
            if self.tool_call is None:
                raise ValueError("tool_call 不能为空")
            if self.answer is not None:
                raise ValueError("answer 不能与 tool_call 同时存在")

        return self


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    tool_name: str = Field(..., min_length=1, description="工具名称，如 get_weather")
    data: dict[str, Any] = Field(default_factory=dict, description="工具返回的数据")
    error: str | None = None

    @model_validator(mode="after")
    def validate_ok_payload(self):
        if not self.ok:
            if not self.error or not self.error.strip():
                raise ValueError("error 不能为空")
            if self.data:
                raise ValueError("失败时 data 应为空")
        return self
