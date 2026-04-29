from typing import TYPE_CHECKING, Type

from pydantic import BaseModel

if TYPE_CHECKING:
    from models import ToolCallRequest


class BaseTool:
    name: str
    description: str
    input_model: Type[BaseModel]

    def run(self, args: BaseModel) -> dict:
        raise NotImplementedError

    def to_definition(self) -> "ToolCallRequest":
        """转为放入 system prompt 的 function 定义（供模型选择工具与参数）。"""
        from models import ToolCallRequest, ToolFunctionParameters

        schema = self.input_model.model_json_schema()
        return ToolCallRequest(
            name=self.name,
            description=self.description,
            parameters=ToolFunctionParameters(
                type="object",
                properties=schema.get("properties", {}),
                required=list(schema.get("required", [])),
                additionalProperties=schema.get("additionalProperties", False),
            ),
        )