"""读取 Markdown 文件内容（供 agent 工具调用）。"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from tools.base_tool import BaseTool

# src/tools/read_markdown_file.py -> 仓库根目录
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_markdown_path(user_path: str) -> Path:
    """
    相对路径依次尝试：当前工作目录、项目根目录。
    这样即使用户在 src/ 下启动进程，也能用 path=\"README.md\" 找到仓库根目录的 README。
    """
    raw = Path(user_path)
    if raw.is_absolute():
        p = raw.resolve()
        if not p.exists():
            raise ValueError(f"文件不存在: {user_path}")
        return p

    rel = raw.as_posix().lstrip("./")
    candidates = [
        (Path.cwd() / rel).resolve(),
        (_REPO_ROOT / rel).resolve(),
    ]
    for p in candidates:
        if p.exists():
            return p

    raise ValueError(
        f"文件不存在: {user_path}（已尝试当前目录 {Path.cwd()} 与项目根 {_REPO_ROOT}）"
    )


class ReadMarkdownFileInput(BaseModel):
    path: str = Field(..., description="Markdown 文件路径（相对路径相对 cwd 或项目根）")
    max_chars: int = Field(8000, description="最多返回字符数")


class ReadMarkdownFileTool(BaseTool):
    name = "read_markdown_file"
    description = "读取 Markdown 文件"
    input_model = ReadMarkdownFileInput

    def run(self, args: ReadMarkdownFileInput) -> dict[str, str | int | bool]:
        file_path = _resolve_markdown_path(args.path)

        if not file_path.is_file():
            raise ValueError(f"路径不是文件: {args.path}")

        if file_path.suffix.lower() not in (".md", ".markdown"):
            raise ValueError(f"仅允许 .md / .markdown 后缀: {args.path}")

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise ValueError("文件不是合法 UTF-8 文本") from e

        truncated = len(content) > args.max_chars
        if truncated:
            content = content[: args.max_chars]

        return {
            "path": str(file_path),
            "content": content,
            "chars": len(content),
            "truncated": truncated,
        }
