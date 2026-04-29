"""测试 read_markdown_file 工具的路径解析与内容读取。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from models import ToolCallInvocation  # noqa: E402
from tool_registery import ToolRegistry  # noqa: E402
from tool_runner import run_tool_invocation  # noqa: E402
from tools.read_markdown_file import ReadMarkdownFileTool  # noqa: E402


class TestReadMarkdownFileTool(unittest.TestCase):
    def test_reads_temp_file(self) -> None:
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".md",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write("# Hi\n")
            path = f.name
        try:
            t = ReadMarkdownFileTool()
            out = t.run(t.input_model.model_validate({"path": path}))
            self.assertEqual(out["content"].strip(), "# Hi")
            self.assertFalse(out["truncated"])
        finally:
            os.unlink(path)

    def test_unknown_path_via_runner(self) -> None:
        missing = Path(tempfile.gettempdir()) / "__agent_lab_no_such__.md"
        self.assertFalse(missing.exists())
        r = ToolRegistry()
        r.register(ReadMarkdownFileTool())
        res = run_tool_invocation(
            r,
            ToolCallInvocation(
                name="read_markdown_file",
                arguments={"path": str(missing)},
            ),
        )
        self.assertFalse(res.ok)
        self.assertIn("文件不存在", res.error or "")

    @mock.patch("tools.read_markdown_file.Path.cwd")
    def test_relative_falls_back_to_repo_root(self, mock_cwd: mock.MagicMock) -> None:
        """cwd 下没有 README 时，应能在项目根找到 README.md（若存在）。"""
        repo = _SRC.parent
        readme = repo / "README.md"
        if not readme.is_file():
            self.skipTest("仓库无 README.md，跳过")

        # 模拟在 src/ 下启动，且当前目录没有 README.md
        mock_cwd.return_value = _SRC
        t = ReadMarkdownFileTool()
        out = t.run(t.input_model.model_validate({"path": "README.md"}))
        self.assertIn("Gemini", out["content"] or "")


if __name__ == "__main__":
    unittest.main()
