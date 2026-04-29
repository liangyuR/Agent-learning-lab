"""测试 call_model 在失败时的重试行为。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from main import call_model  # noqa: E402


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


class TestCallModelRetry(unittest.TestCase):
    @patch("time.sleep", MagicMock())
    def test_three_failures_then_success(self) -> None:
        client = MagicMock()
        client.post.side_effect = [
            RuntimeError("e1"),
            RuntimeError("e2"),
            RuntimeError("e3"),
            make_deepseek_response("ok"),
        ]
        result = call_model(client, "system", "user")
        self.assertEqual(result.text, "ok")
        self.assertEqual(client.post.call_count, 4)

    @patch("time.sleep", MagicMock())
    def test_all_attempts_fail_raises_last_error(self) -> None:
        client = MagicMock()
        client.post.side_effect = RuntimeError("always fail")
        with self.assertRaises(RuntimeError) as ctx:
            call_model(client, "system", "user")
        self.assertEqual(str(ctx.exception), "always fail")
        self.assertEqual(client.post.call_count, 4)

    @patch.dict("os.environ", {}, clear=True)
    def test_payload_uses_deepseek_thinking_mode(self) -> None:
        client = MagicMock()
        client.post.return_value = make_deepseek_response("ok")
        call_model(client, "system", "user", max_output_tokens=123)
        payload = client.post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "deepseek-v4-pro")
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


if __name__ == "__main__":
    unittest.main()
