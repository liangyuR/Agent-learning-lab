'''
负责存储：

当前 session id
历史消息
已知用户意图
当前任务上下文
工具调用结果摘要
'''

from datetime import datetime
from uuid import uuid4
from pydantic import BaseModel, Field

from session.message import ChatMessage

class SessionState:
    session_id: str
    messages: list
    summary: str | None
    variables: dict