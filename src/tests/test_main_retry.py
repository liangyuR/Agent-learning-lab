"""测试 call_model / call_chat_model 单次请求行为（失败不重试）。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from main import (  # noqa: E402
    DEFAULT_DEEPSEEK_MODEL,
    build_deepseek_chat_payload,
    call_chat_model,
    call_model,
    extract_deepseek_model_response,
)


def make_deepseek_response(content: str) -> MagicMock:
    response = MagicMock()
    response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": content,
                },
            },
        ],
    }
    return response


def make_deepseek_tool_call_response() -> MagicMock:
    response = MagicMock()
    response.json.return_value = {
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "get_current_time",
                                "arguments": '{"timezone":"UTC"}',
                            },
                        }
                    ],
                },
            },
        ],
    }
    return response


class TestCallModelSingleAttempt(unittest.TestCase):
    def test_success_on_first_post(self) -> None:
        client = MagicMock()
        client.post.return_value = make_deepseek_response("ok")
        result = call_model(client, "system", "user")
        self.assertEqual(result.text, "ok")
        self.assertEqual(client.post.call_count, 1)

    def test_raises_on_first_post_error_no_retry(self) -> None:
        client = MagicMock()
        client.post.side_effect = RuntimeError("network down")
        with self.assertRaises(RuntimeError) as ctx:
            call_model(client, "system", "user")
        self.assertEqual(str(ctx.exception), "network down")
        self.assertEqual(client.post.call_count, 1)

    @patch.dict("os.environ", {}, clear=True)
    def test_payload_uses_deepseek_thinking_mode(self) -> None:
        client = MagicMock()
        client.post.return_value = make_deepseek_response("ok")
        call_model(client, "system", "user", max_output_tokens=123)
        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], DEFAULT_DEEPSEEK_MODEL)
        self.assertEqual(payload["max_tokens"], 123)
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
        )

    @patch.dict("os.environ", {}, clear=True)
    def test_call_chat_model_sends_full_messages(self) -> None:
        client = MagicMock()
        client.post.return_value = make_deepseek_response("hi")
        msgs = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
        ]
        result = call_chat_model(client, msgs, max_output_tokens=99)
        self.assertEqual(result.text, "hi")
        self.assertEqual(result.content, "hi")
        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(payload["messages"], msgs)
        self.assertEqual(payload["max_tokens"], 99)
        self.assertEqual(payload["model"], DEFAULT_DEEPSEEK_MODEL)

    @patch.dict("os.environ", {}, clear=True)
    def test_call_chat_model_sends_tools_and_tool_choice(self) -> None:
        client = MagicMock()
        client.post.return_value = make_deepseek_response("ok")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_current_time",
                    "description": "获取当前时间",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]
        call_chat_model(
            client,
            [{"role": "user", "content": "现在几点？"}],
            tools=tools,
            tool_choice="auto",
            max_output_tokens=88,
        )
        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(payload["tools"], tools)
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertEqual(payload["max_tokens"], 88)

    def test_extract_deepseek_model_response_reads_tool_calls(self) -> None:
        data = make_deepseek_tool_call_response().json()
        result = extract_deepseek_model_response(data)
        self.assertEqual(result.finish_reason, "tool_calls")
        self.assertEqual(result.content, "")
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0].id, "call_1")
        self.assertEqual(result.tool_calls[0].name, "get_current_time")
        self.assertEqual(result.tool_calls[0].arguments["timezone"], "UTC")

    @patch.dict("os.environ", {}, clear=True)
    def test_build_deepseek_chat_payload_matches_call_shape(self) -> None:
        payload = build_deepseek_chat_payload(
            [{"role": "user", "content": "x"}],
            50,
            response_format={"type": "json_object"},
        )
        self.assertIn("model", payload)
        self.assertEqual(payload["messages"], [{"role": "user", "content": "x"}])
        self.assertEqual(payload["max_tokens"], 50)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertFalse(payload["stream"])


if __name__ == "__main__":
    unittest.main()
