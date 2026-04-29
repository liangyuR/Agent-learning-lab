import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from pydantic import ValidationError

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from tools.http_tool import HttpRequestArgs, HttpRequestTool  # noqa: E402


def _response(
    *,
    status_code: int = 200,
    text: str = "hello",
    content_type: str = "text/html",
    url: str = "https://example.com/",
) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        text=text,
        headers={"Content-Type": content_type},
        request=httpx.Request("GET", url),
    )


class TestHttpRequestArgs(unittest.TestCase):
    def test_defaults(self) -> None:
        args = HttpRequestArgs(url="https://example.com/")

        self.assertEqual(args.method, "GET")
        self.assertEqual(args.headers, {})
        self.assertEqual(args.params, {})
        self.assertEqual(args.body, {})
        self.assertEqual(args.timeout, 10)
        self.assertEqual(args.max_chars, 8000)

    def test_method_is_normalized(self) -> None:
        args = HttpRequestArgs(url="https://example.com/", method="post")

        self.assertEqual(args.method, "POST")

    def test_rejects_non_http_url(self) -> None:
        with self.assertRaises(ValidationError):
            HttpRequestArgs(url="file:///etc/passwd")

    def test_rejects_private_or_localhost_url(self) -> None:
        blocked_urls = [
            "http://localhost/",
            "http://127.0.0.1/",
            "http://0.0.0.0/",
            "http://192.168.1.1/",
            "http://[::1]/",
        ]

        for url in blocked_urls:
            with self.subTest(url=url):
                with self.assertRaises(ValidationError):
                    HttpRequestArgs(url=url)

    def test_rejects_out_of_range_limits(self) -> None:
        with self.assertRaises(ValidationError):
            HttpRequestArgs(url="https://example.com/", timeout=31)

        with self.assertRaises(ValidationError):
            HttpRequestArgs(url="https://example.com/", max_chars=0)


class TestHttpRequestTool(unittest.TestCase):
    def test_returns_structured_html_response(self) -> None:
        with patch("tools.http_tool.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.request.return_value = _response(text="<html>ok</html>")

            out = HttpRequestTool().run(
                HttpRequestArgs(
                    url="https://example.com/",
                    headers={"Accept": "text/html"},
                    params={"q": "agent"},
                ),
            )

        client_cls.assert_called_once_with(follow_redirects=True, timeout=10)
        client.request.assert_called_once_with(
            "GET",
            "https://example.com/",
            headers={"Accept": "text/html"},
            params={"q": "agent"},
            json=None,
        )
        self.assertEqual(out["status_code"], 200)
        self.assertEqual(out["url"], "https://example.com/")
        self.assertEqual(out["content_type"], "text/html")
        self.assertEqual(out["body"], "<html>ok</html>")
        self.assertEqual(out["chars"], len("<html>ok</html>"))
        self.assertFalse(out["truncated"])
        self.assertFalse(out["is_json"])

    def test_passes_post_json_body(self) -> None:
        with patch("tools.http_tool.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.request.return_value = _response(text='{"ok": true}', content_type="application/json")

            HttpRequestTool().run(
                HttpRequestArgs(
                    url="https://example.com/api",
                    method="POST",
                    body={"name": "agent"},
                    timeout=15,
                ),
            )

        client_cls.assert_called_once_with(follow_redirects=True, timeout=15)
        client.request.assert_called_once_with(
            "POST",
            "https://example.com/api",
            headers={},
            params={},
            json={"name": "agent"},
        )

    def test_detects_json_content_type(self) -> None:
        with patch("tools.http_tool.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.request.return_value = _response(
                text='{"message": "ok"}',
                content_type="application/json; charset=utf-8",
            )

            out = HttpRequestTool().run(HttpRequestArgs(url="https://example.com/api"))

        self.assertTrue(out["is_json"])

    def test_returns_404_without_raising(self) -> None:
        with patch("tools.http_tool.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.request.return_value = _response(status_code=404, text="not found")

            out = HttpRequestTool().run(HttpRequestArgs(url="https://example.com/missing"))

        self.assertEqual(out["status_code"], 404)
        self.assertEqual(out["body"], "not found")

    def test_truncates_body_by_max_chars(self) -> None:
        with patch("tools.http_tool.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.request.return_value = _response(text="abcdef")

            out = HttpRequestTool().run(
                HttpRequestArgs(url="https://example.com/", max_chars=3),
            )

        self.assertEqual(out["body"], "abc")
        self.assertEqual(out["chars"], 3)
        self.assertTrue(out["truncated"])

    def test_timeout_becomes_value_error(self) -> None:
        with patch("tools.http_tool.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.request.side_effect = httpx.TimeoutException("slow")

            with self.assertRaisesRegex(ValueError, "HTTP 请求超时"):
                HttpRequestTool().run(HttpRequestArgs(url="https://example.com/"))

    def test_network_error_becomes_value_error(self) -> None:
        with patch("tools.http_tool.httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.request.side_effect = httpx.ConnectError("connection failed")

            with self.assertRaisesRegex(ValueError, "HTTP 请求失败"):
                HttpRequestTool().run(HttpRequestArgs(url="https://example.com/"))


if __name__ == "__main__":
    unittest.main()
