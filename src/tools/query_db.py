"""只读查询 MySQL。配置见 tools/db/db.yaml，密码可用环境变量 MYSQL_PASSWORD 覆盖。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pymysql
import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from tools.base_tool import BaseTool

_DB_DIR = Path(__file__).resolve().parent / "db"
_DB_YAML = _DB_DIR / "db.yaml"


def _load_mysql_config() -> dict[str, Any]:
    if not _DB_YAML.is_file():
        raise ValueError(
            f"数据库配置不存在: {_DB_YAML}（可将 db.yaml.example 复制为 db.yaml）",
        )
    with _DB_YAML.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    mysql = raw.get("mysql")
    if not isinstance(mysql, dict):
        raise ValueError("db.yaml 中缺少 mysql: 配置段")
    password = os.getenv("MYSQL_PASSWORD") or mysql.get("password")
    if not password:
        raise ValueError("未配置数据库密码（db.yaml 或环境变量 MYSQL_PASSWORD）")
    return {
        "host": str(mysql["ip"]),
        "port": int(mysql.get("port", 3306)),
        "user": str(mysql["username"]),
        "password": str(password),
        "database": str(mysql["database"]),
    }


_READONLY_QUERY_KEYWORDS = {"select", "show", "describe", "desc", "explain"}


def _require_readonly_query_sql(sql: str) -> None:
    stripped = sql.strip()
    if not stripped:
        raise ValueError("SQL 不能为空")
    first = stripped.split()[0].lower()
    if first not in _READONLY_QUERY_KEYWORDS:
        raise ValueError("仅允许只读查询（禁止 DML/DDL）")


class QueryDbArgs(BaseModel):
    sql: str = Field(..., description="仅支持只读查询，如 SELECT、SHOW、DESCRIBE、EXPLAIN")


class QueryDbTool(BaseTool):
    name = "query_db"
    description = "对 MySQL 执行只读查询（SELECT/SHOW/DESCRIBE/EXPLAIN），可查看表结构，返回列名与行数据"
    input_model = QueryDbArgs

    def run(self, args: QueryDbArgs) -> dict[str, Any]:
        load_dotenv()
        _require_readonly_query_sql(args.sql)
        cfg = _load_mysql_config()

        conn: pymysql.connections.Connection | None = None
        cursor: pymysql.cursors.Cursor | None = None
        try:
            conn = pymysql.connect(
                host=cfg["host"],
                port=cfg["port"],
                user=cfg["user"],
                password=cfg["password"],
                database=cfg["database"],
                charset="utf8mb4",
            )
            cursor = conn.cursor()
            cursor.execute(args.sql)
            columns = [d[0] for d in (cursor.description or ())]
            rows = [list(row) for row in cursor.fetchall()]
            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            }
        finally:
            if cursor is not None:
                cursor.close()
            if conn is not None:
                conn.close()
