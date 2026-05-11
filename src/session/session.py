"""
会话状态：session_id、消息列表、摘要占位、会话级变量。

提供创建、加载、保存、追加消息、清空及 load_or_create 便捷方法。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from session.message import ChatMessage

# 仅允许安全文件名片段：字母数字、下划线、连字符、点（不含路径分隔符）
_SAFE_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


class SessionState(BaseModel):
    """可 JSON 序列化的会话状态，字段固定。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str
    messages: list[ChatMessage] = Field(default_factory=list)
    summary: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)


def assert_safe_session_id(session_id: str) -> None:
    """拒绝空串、路径分隔符、.. 及非安全字符，防止路径穿越。"""
    if not session_id or not session_id.strip():
        raise ValueError("session_id 不能为空")
    if ".." in session_id or "/" in session_id or "\\" in session_id:
        raise ValueError("session_id 不能包含路径片段 '..' 或分隔符")
    if not _SAFE_SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("session_id 仅允许字母、数字、_.-")


def session_file_path(session_id: str, sessions_dir: Path) -> Path:
    """返回会话 JSON 的绝对路径，并校验 session_id 与最终路径在 sessions_dir 下。"""
    assert_safe_session_id(session_id)
    root = sessions_dir.resolve()
    path = (root / f"{session_id}.json").resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("会话文件路径必须位于 sessions_dir 内") from exc
    return path


def create_session(session_id: str) -> SessionState:
    """在内存中创建新会话（不读写磁盘）。"""
    assert_safe_session_id(session_id)
    return SessionState(session_id=session_id)


def load_session(session_id: str, sessions_dir: Path) -> SessionState:
    """从磁盘加载会话；文件不存在时抛出 FileNotFoundError。"""
    path = session_file_path(session_id, sessions_dir)
    if not path.is_file():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    state = SessionState.model_validate_json(text)
    if state.session_id != session_id:
        raise ValueError("文件内 session_id 与请求的 session_id 不一致")
    return state


def save_session(state: SessionState, sessions_dir: Path) -> None:
    """将会话写入 UTF-8 JSON（ensure_ascii=False）。"""
    assert_safe_session_id(state.session_id)
    path = session_file_path(state.session_id, sessions_dir)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    payload = state.model_dump(mode="json")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def append_message(state: SessionState, message: ChatMessage) -> None:
    """向当前会话追加一条消息（原地修改）。"""
    state.messages.append(message)


def clear_session(state: SessionState, clear_variables: bool = False) -> None:
    """
    清空对话与摘要；默认保留 variables。

    clear_variables 为 True 时同时清空 variables。
    """
    state.messages.clear()
    state.summary = None
    if clear_variables:
        state.variables.clear()


def load_or_create_session(
    session_id: str,
    sessions_dir: Path,
    *,
    save_on_create: bool = False,
) -> SessionState:
    """
    存在则 load_session；不存在则 create_session。

    save_on_create 为 True 时，新建后立即 save_session（便于落盘占位）。
    """
    try:
        return load_session(session_id, sessions_dir)
    except FileNotFoundError:
        state = create_session(session_id)
        if save_on_create:
            save_session(state, sessions_dir)
        return state
