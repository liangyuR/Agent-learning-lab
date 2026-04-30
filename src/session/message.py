# src/agent/message.py

from typing import Literal, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


MessageRole = Literal["system", "user", "assistant", "tool"]


class ChatMessage(BaseModel):
    role: MessageRole
    content: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # 可选：如果是工具消息，可以记录工具名
    tool_name: Optional[str] = None

    # 可选：保存结构化数据
    metadata: dict[str, Any] = Field(default_factory=dict)