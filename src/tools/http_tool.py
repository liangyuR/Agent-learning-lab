from __future__ import annotations

from ipaddress import ip_address
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field, field_validator

from tools.base_tool import BaseTool

_BLOCKED_HOSTNAMES = {"localhost"}


def _is_blocked_host(host: str | None) -> bool:
    if host is None:
        return True

    normalized = host.rstrip(".").lower()
    if normalized in _BLOCKED_HOSTNAMES:
        return True

    try:
        parsed_ip = ip_address(normalized)
    except ValueError:
        return False

    return (
        parsed_ip.is_private
        or parsed_ip.is_loopback
        or parsed_ip.is_link_local
        or parsed_ip.is_multicast
        or parsed_ip.is_reserved
        or parsed_ip.is_unspecified
    )


def _is_json_content_type(content_type: str | None) -> bool:
    if content_type is None:
        return False

    media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    return media_type == "application/json" or media_type.endswith("+json")


class HttpRequestArgs(BaseModel):
    url: str = Field(..., description="只支持 http:// 或 https:// 开头的公开 URL")
    method: Literal["GET", "POST"] = Field(default="GET", description="HTTP 方法，支持 GET、POST")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP 请求头")
    params: dict[str, str | int | float | bool] = Field(default_factory=dict, description="HTTP 查询参数")
    body: dict[str, Any] = Field(default_factory=dict, description="JSON 请求体")
    timeout: int = Field(default=10, ge=1, le=30, description="HTTP 请求超时时间，单位：秒")
    max_chars: int = Field(default=8000, ge=1, le=20000, description="最多返回的响应字符数")

    @field_validator("method", mode="before")
    @classmethod
    def normalize_method(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.upper()
        return value

    @field_validator("url")
    @classmethod
    def validate_public_http_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("只支持 http:// 或 https:// URL")
        if not parsed.netloc:
            raise ValueError("URL 缺少主机名")
        if _is_blocked_host(parsed.hostname):
            raise ValueError("禁止访问 localhost、内网 IP 或保留地址")
        return value


class HttpRequestTool(BaseTool):
    name = "http_request"
    description = "读取公开网页或调用简单 HTTP API，返回状态码、响应头类型和截断后的正文"
    input_model = HttpRequestArgs

    def run(self, args: HttpRequestArgs) -> dict[str, Any]:
        try:
            with httpx.Client(follow_redirects=True, timeout=args.timeout) as client:
                response = client.request(
                    args.method,
                    args.url,
                    headers=args.headers,
                    params=args.params,
                    json=args.body if args.body else None,
                )
        except httpx.TimeoutException as e:
            raise ValueError(f"HTTP 请求超时: {args.url}") from e
        except httpx.RequestError as e:
            raise ValueError(f"HTTP 请求失败: {e}") from e

        raw_body = response.text
        truncated = len(raw_body) > args.max_chars
        body = raw_body[: args.max_chars] if truncated else raw_body
        content_type = response.headers.get("Content-Type")

        return {
            "status_code": response.status_code,
            "url": str(response.url),
            "content_type": content_type,
            "body": body,
            "chars": len(body),
            "truncated": truncated,
            "is_json": _is_json_content_type(content_type),
        }
