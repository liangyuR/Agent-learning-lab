"""测试 call_model 在失败时的重试行为。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from main import call_model  # noqa: E402


class TestCallModelRetry(unittest.TestCase):
    @patch("time.sleep", MagicMock())
    def test_three_failures_then_success(self) -> None:
        client = MagicMock()
        ok = object()
        client.models.generate_content.side_effect = [
            RuntimeError("e1"),
            RuntimeError("e2"),
            RuntimeError("e3"),
            ok,
        ]
        result = call_model(client, "system", "user")
        self.assertIs(result, ok)
        self.assertEqual(client.models.generate_content.call_count, 4)

    @patch("time.sleep", MagicMock())
    def test_all_attempts_fail_raises_last_error(self) -> None:
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError("always fail")
        with self.assertRaises(RuntimeError) as ctx:
            call_model(client, "system", "user")
        self.assertEqual(str(ctx.exception), "always fail")
        self.assertEqual(client.models.generate_content.call_count, 4)


if __name__ == "__main__":
    unittest.main()
