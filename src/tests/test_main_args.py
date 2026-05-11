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

from main import main, parse_args, read_text_file, run_chat_loop  # noqa: E402
from main import (  # noqa: E402
    ModelResponse,
    _chat_max_tool_calls,
    chat_messages_to_api_messages,
    complete_chat_turn,
    ensure_chat_system_message,
    native_tool_call_to_api_dict,
    truncate_text_for_model,
)
from models import NativeToolCall, ToolResult  # noqa: E402


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

    def test_chat_flag(self) -> None:
        ns = parse_args(["--chat"])
        self.assertTrue(ns.chat)

    def test_session_id_default(self) -> None:
        ns = parse_args([])
        self.assertEqual(ns.session_id, "default")

    def test_session_id_custom(self) -> None:
        ns = parse_args(["--session-id", "abc"])
        self.assertEqual(ns.session_id, "abc")

    def test_reset_session_flag(self) -> None:
        ns = parse_args(["--reset-session"])
        self.assertTrue(ns.reset_session)

    def test_reset_session_default_false(self) -> None:
        ns = parse_args([])
        self.assertFalse(ns.reset_session)


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


class TestMainChatBranch(unittest.TestCase):
    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True)
    @patch("main.build_deepseek_client")
    @patch("main.run_chat_loop", return_value=0)
    def test_chat_invokes_run_chat_loop(
        self,
        mock_run_chat: MagicMock,
        mock_build_client: MagicMock,
    ) -> None:
        fake_client = MagicMock()
        mock_build_client.return_value = fake_client
        with patch.object(sys, "argv", ["main.py", "--chat", "--session-id", "room1"]):
            code = main()
        self.assertEqual(code, 0)
        mock_run_chat.assert_called_once_with(fake_client, "room1", False)
        fake_client.close.assert_called_once()

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True)
    @patch("main.build_deepseek_client")
    @patch("main.run_chat_loop")
    def test_reset_session_passed_to_loop(
        self,
        mock_run_chat: MagicMock,
        mock_build_client: MagicMock,
    ) -> None:
        mock_build_client.return_value = MagicMock()
        mock_run_chat.return_value = 0
        with patch.object(
            sys, "argv", ["main.py", "--chat", "--reset-session"]
        ):
            code = main()
        self.assertEqual(code, 0)
        mock_run_chat.assert_called_once()
        self.assertEqual(mock_run_chat.call_args[0][2], True)

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True)
    @patch("main.build_deepseek_client")
    @patch("main.run_chat_loop")
    def test_chat_with_input_exits_one(
        self,
        _mock_run_chat: MagicMock,
        mock_build_client: MagicMock,
    ) -> None:
        with patch.object(sys, "argv", ["main.py", "--chat", "-i", "hi"]):
            code = main()
        self.assertEqual(code, 1)
        mock_build_client.assert_not_called()

    @patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True)
    @patch("main.build_deepseek_client")
    @patch("main.run_chat_loop")
    def test_chat_invalid_session_id_exits_one(
        self,
        _mock_run_chat: MagicMock,
        mock_build_client: MagicMock,
    ) -> None:
        with patch.object(sys, "argv", ["main.py", "--chat", "--session-id", "../x"]):
            code = main()
        self.assertEqual(code, 1)
        mock_build_client.assert_not_called()


class TestChatMaxToolCalls(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_default_is_ten(self) -> None:
        self.assertEqual(_chat_max_tool_calls(), 10)

    @patch.dict(os.environ, {"CHAT_MAX_TOOL_CALLS": "5"})
    def test_env_override(self) -> None:
        self.assertEqual(_chat_max_tool_calls(), 5)

    @patch.dict(os.environ, {"CHAT_MAX_TOOL_CALLS": "0"})
    def test_minimum_one(self) -> None:
        self.assertEqual(_chat_max_tool_calls(), 1)

    @patch.dict(os.environ, {"CHAT_MAX_TOOL_CALLS": "not-a-number"})
    def test_invalid_env_falls_back_to_default(self) -> None:
        self.assertEqual(_chat_max_tool_calls(), 10)


class TestRunChatLoop(unittest.TestCase):
    @patch("main.load_or_create_session")
    @patch("main.save_session")
    @patch("builtins.input", side_effect=["/exit"])
    def test_exit_command(
        self,
        _mock_input: MagicMock,
        _mock_save: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        from session.message import ChatMessage
        from session.session import SessionState

        state = SessionState(
            session_id="s",
            messages=[ChatMessage(role="system", content="sys")],
        )
        mock_load.return_value = state
        client = MagicMock()
        with tempfile.TemporaryDirectory() as tmp:
            with patch("main.default_sessions_dir", return_value=Path(tmp)):
                code = run_chat_loop(client, "s", reset_session=False)
        self.assertEqual(code, 0)
        client.post.assert_not_called()

    def test_tool_messages_are_sent_as_native_tool_context(self) -> None:
        from session.message import ChatMessage

        messages = [
            ChatMessage(role="system", content="sys"),
            ChatMessage(
                role="tool",
                content="tool body",
                tool_name="t",
                metadata={"tool_call_id": "call_1"},
            ),
        ]
        api_messages = chat_messages_to_api_messages(messages)
        self.assertEqual(api_messages[1]["role"], "tool")
        self.assertEqual(api_messages[1]["tool_call_id"], "call_1")

    def test_old_tool_messages_fallback_to_user_context(self) -> None:
        from session.message import ChatMessage

        messages = [
            ChatMessage(role="system", content="sys"),
            ChatMessage(role="tool", content="tool body", tool_name="t"),
        ]
        api_messages = chat_messages_to_api_messages(messages)
        self.assertEqual(api_messages[1]["role"], "user")
        self.assertIn("[历史工具结果: t]", api_messages[1]["content"])

    def test_assistant_tool_call_message_round_trips(self) -> None:
        from session.message import ChatMessage

        tool_call = NativeToolCall(
            id="call_1",
            name="get_current_time",
            arguments={"timezone": "UTC"},
        )
        messages = [
            ChatMessage(
                role="assistant",
                content="",
                metadata={
                    "tool_calls": [native_tool_call_to_api_dict(tool_call)],
                    "reasoning_content": "need tool",
                },
            )
        ]
        api_messages = chat_messages_to_api_messages(messages)
        self.assertEqual(api_messages[0]["role"], "assistant")
        self.assertEqual(api_messages[0]["content"], "")
        self.assertEqual(api_messages[0]["tool_calls"][0]["id"], "call_1")
        self.assertEqual(api_messages[0]["reasoning_content"], "need tool")

    def test_tool_message_content_is_truncated_for_model(self) -> None:
        from session.message import ChatMessage

        messages = [
            ChatMessage(
                role="tool",
                content="x" * 7000,
                metadata={"tool_call_id": "call_1"},
            )
        ]
        api_messages = chat_messages_to_api_messages(messages)
        self.assertLess(len(api_messages[0]["content"]), 6200)
        self.assertIn("内容已截断", api_messages[0]["content"])

    def test_truncate_text_for_model_keeps_short_text(self) -> None:
        self.assertEqual(truncate_text_for_model("abc", 10), "abc")

    def test_ensure_chat_system_message_includes_tool_protocol(self) -> None:
        from session.session import SessionState

        state = SessionState(session_id="s")
        ensure_chat_system_message(state)
        self.assertEqual(state.messages[0].role, "system")
        self.assertEqual(
            state.messages[0].metadata["managed_by"],
            "agent_learning_lab",
        )

    @patch("main.run_tool_invocation")
    @patch("main.call_chat_model")
    def test_complete_chat_turn_runs_tool_then_final_answer(
        self,
        mock_call_chat_model: MagicMock,
        mock_run_tool: MagicMock,
    ) -> None:
        from session.message import ChatMessage
        from session.session import SessionState

        mock_call_chat_model.side_effect = [
            ModelResponse(
                tool_calls=[
                    NativeToolCall(
                        id="call_1",
                        name="get_current_time",
                        arguments={"timezone": "UTC"},
                    )
                ],
                finish_reason="tool_calls",
                reasoning_content="need current time",
            ),
            ModelResponse(
                content="现在是 12:00。",
                finish_reason="stop",
                reasoning_content="answer from tool result",
            ),
        ]
        mock_run_tool.return_value = ToolResult(
            ok=True,
            tool_name="get_current_time",
            data={"time": "12:00:00", "timezone": "UTC"},
        )
        state = SessionState(
            session_id="s",
            messages=[
                ChatMessage(role="system", content="sys"),
                ChatMessage(role="user", content="现在几点？"),
            ],
        )

        answer = complete_chat_turn(MagicMock(), state, MagicMock())

        self.assertEqual(answer, "现在是 12:00。")
        self.assertEqual(mock_call_chat_model.call_count, 2)
        self.assertEqual(mock_call_chat_model.call_args_list[0].kwargs["tool_choice"], "auto")
        self.assertEqual(mock_run_tool.call_args[0][1].name, "get_current_time")
        self.assertEqual(state.messages[-3].role, "assistant")
        self.assertEqual(state.messages[-3].metadata["reasoning_content"], "need current time")
        self.assertEqual(state.messages[-2].role, "tool")
        self.assertEqual(state.messages[-2].metadata["tool_call_id"], "call_1")
        self.assertEqual(state.messages[-1].role, "assistant")
        self.assertEqual(
            state.messages[-1].metadata["reasoning_content"],
            "answer from tool result",
        )

    @patch("main.call_chat_model")
    def test_complete_chat_turn_without_tool_call_keeps_plain_chat(
        self,
        mock_call_chat_model: MagicMock,
    ) -> None:
        from session.message import ChatMessage
        from session.session import SessionState

        mock_call_chat_model.return_value = ModelResponse(
            content="普通回答",
            finish_reason="stop",
        )
        state = SessionState(
            session_id="s",
            messages=[
                ChatMessage(role="system", content="sys"),
                ChatMessage(role="user", content="你好"),
            ],
        )

        answer = complete_chat_turn(MagicMock(), state, MagicMock())

        self.assertEqual(answer, "普通回答")
        self.assertEqual(state.messages[-1].role, "assistant")


if __name__ == "__main__":
    unittest.main()
