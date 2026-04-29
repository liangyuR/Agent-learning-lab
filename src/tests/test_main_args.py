"""测试 main 模块的命令行参数解析与读文件。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from main import main, parse_args, read_text_file  # noqa: E402


class TestParseArgs(unittest.TestCase):
    def test_input_long_flag(self) -> None:
        ns = parse_args(["--input", "什么是 Python"])
        self.assertEqual(ns.input, "什么是 Python")
        self.assertIsNone(ns.file)

    def test_input_short_flag(self) -> None:
        ns = parse_args(["-i", "hi"])
        self.assertEqual(ns.input, "hi")
        self.assertIsNone(ns.file)

    def test_no_input_uses_default(self) -> None:
        ns = parse_args([])
        self.assertIsNone(ns.input)
        self.assertIsNone(ns.file)

    def test_mode_defaults_to_analysis(self) -> None:
        ns = parse_args([])
        self.assertEqual(ns.mode, "analysis")

    def test_mode_agent(self) -> None:
        ns = parse_args(["--mode", "agent"])
        self.assertEqual(ns.mode, "agent")

    def test_file_long_flag(self) -> None:
        ns = parse_args(["--file", "input.txt"])
        self.assertEqual(ns.file, "input.txt")
        self.assertIsNone(ns.input)

    def test_file_short_flag(self) -> None:
        ns = parse_args(["-f", "notes.md"])
        self.assertEqual(ns.file, "notes.md")
        self.assertIsNone(ns.input)

    def test_input_and_file_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            parse_args(["--input", "a", "--file", "b"])
        self.assertEqual(ctx.exception.code, 2)

    def test_short_flags_input_file_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            parse_args(["-i", "a", "-f", "b"])
        self.assertEqual(ctx.exception.code, 2)

    def test_file_path_with_spaces(self) -> None:
        ns = parse_args(["--file", "my input file.txt"])
        self.assertEqual(ns.file, "my input file.txt")

    def test_file_empty_string_argument(self) -> None:
        ns = parse_args(["--file", ""])
        self.assertEqual(ns.file, "")


class TestReadTextFile(unittest.TestCase):
    def test_reads_utf8_content(self) -> None:
        text = "中文内容\nline2"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False
        ) as f:
            f.write(text)
            path = f.name
        try:
            self.assertEqual(read_text_file(path), text)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            read_text_file("__does_not_exist__.txt")

    def test_empty_file_returns_empty_string(self) -> None:
        path: str | None = None
        try:
            fd, path = tempfile.mkstemp(suffix=".txt")
            os.close(fd)
            self.assertEqual(read_text_file(path), "")
        finally:
            if path:
                Path(path).unlink(missing_ok=True)

    def test_utf8_bom_preserved_in_content(self) -> None:
        text = "\ufeff有 BOM 的行\n"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False
        ) as f:
            f.write(text)
            p = f.name
        try:
            self.assertEqual(read_text_file(p), text)
        finally:
            Path(p).unlink(missing_ok=True)

    def test_invalid_utf8_raises_unicode_decode_error(self) -> None:
        path: str | None = None
        try:
            fd, path = tempfile.mkstemp(suffix=".bin")
            os.write(fd, b"\xff\xfe\x00")
            os.close(fd)
            with self.assertRaises(UnicodeDecodeError):
                read_text_file(path)
        finally:
            if path:
                Path(path).unlink(missing_ok=True)

    def test_directory_path_raises(self) -> None:
        # Unix 常见 IsADirectoryError；Windows 上多为 PermissionError
        with self.assertRaises((IsADirectoryError, PermissionError)):
            read_text_file(str(_SRC))


class TestMainFileBranch(unittest.TestCase):
    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True)
    @patch("main.build_deepseek_client")
    @patch("main.call_model")
    @patch(
        "main.parse_output",
        return_value={
            "summary": "ok",
            "key_points": [],
            "risks": [],
            "next_actions": [],
        },
    )
    def test_file_nonempty_exits_zero(
        self,
        _parse_output: MagicMock,
        mock_call_model: MagicMock,
        _build_client: MagicMock,
    ) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("有效内容")
            p = f.name
        try:
            with patch.object(sys, "argv", ["main.py", "--file", p]):
                code = main()
            self.assertEqual(code, 0)
            mock_call_model.assert_called_once()
        finally:
            Path(p).unlink(missing_ok=True)

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True)
    @patch("main.build_deepseek_client")
    @patch("main.call_model")
    @patch("main.parse_output")
    def test_file_whitespace_only_exits_one_without_calling_model(
        self,
        _parse_output: MagicMock,
        mock_call_model: MagicMock,
        mock_build_client: MagicMock,
    ) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", delete=False
        ) as f:
            f.write("  \n\t\r\n  ")
            p = f.name
        try:
            with patch.object(sys, "argv", ["main.py", "--file", p]):
                code = main()
            self.assertEqual(code, 1)
            mock_build_client.assert_not_called()
            mock_call_model.assert_not_called()
        finally:
            Path(p).unlink(missing_ok=True)

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True)
    @patch("main.build_deepseek_client")
    @patch("main.call_model")
    @patch("main.parse_output")
    def test_file_missing_exits_one_without_calling_model(
        self,
        _parse_output: MagicMock,
        mock_call_model: MagicMock,
        mock_build_client: MagicMock,
    ) -> None:
        with patch.object(
            sys, "argv", ["main.py", "--file", "__no_such_file_for_main__.txt"]
        ):
            code = main()
        self.assertEqual(code, 1)
        mock_build_client.assert_not_called()
        mock_call_model.assert_not_called()

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True)
    @patch("main.build_deepseek_client")
    @patch("main.call_model")
    @patch("main.parse_output")
    def test_file_invalid_utf8_exits_one_without_calling_model(
        self,
        _parse_output: MagicMock,
        mock_call_model: MagicMock,
        mock_build_client: MagicMock,
    ) -> None:
        path: str | None = None
        try:
            fd, path = tempfile.mkstemp(suffix=".txt")
            os.write(fd, b"\xc3\x28")
            os.close(fd)
            with patch.object(sys, "argv", ["main.py", "--file", path]):
                code = main()
            self.assertEqual(code, 1)
            mock_build_client.assert_not_called()
            mock_call_model.assert_not_called()
        finally:
            if path:
                Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
