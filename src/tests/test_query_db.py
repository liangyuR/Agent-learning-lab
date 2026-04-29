"""测试 query_db 工具：只读查询校验与返回结构。"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from tools.query_db import QueryDbArgs, QueryDbTool  # noqa: E402


class TestQueryDbTool(unittest.TestCase):
    def test_rejects_write_sql(self) -> None:
        tool = QueryDbTool()
        with self.assertRaises(ValueError) as ctx:
            tool.run(QueryDbArgs(sql="DELETE FROM users WHERE id=1"))
        self.assertIn("只读查询", str(ctx.exception))

    def test_rejects_empty_sql(self) -> None:
        tool = QueryDbTool()
        with self.assertRaises(ValueError):
            tool.run(QueryDbArgs(sql="   "))

    def _run_sql_with_mock_db(self, sql: str) -> dict:
        with (
            patch("tools.query_db._load_mysql_config") as mock_cfg,
            patch("tools.query_db.pymysql.connect") as mock_connect,
        ):
            mock_cfg.return_value = {
                "host": "h",
                "port": 3306,
                "user": "u",
                "password": "p",
                "database": "d",
            }
            mock_cursor = MagicMock()
            mock_cursor.description = (("id",), ("name",))
            mock_cursor.fetchall.return_value = ((1, "a"), (2, "b"))
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            tool = QueryDbTool()
            out = tool.run(QueryDbArgs(sql=sql))

            mock_cursor.execute.assert_called_once_with(sql)
            mock_cursor.close.assert_called_once()
            mock_conn.close.assert_called_once()
            return out

    @patch("tools.query_db._load_mysql_config")
    @patch("tools.query_db.pymysql.connect")
    def test_select_returns_dict_with_columns_and_rows(
        self,
        mock_connect: MagicMock,
        mock_cfg: MagicMock,
    ) -> None:
        mock_cfg.return_value = {
            "host": "h",
            "port": 3306,
            "user": "u",
            "password": "p",
            "database": "d",
        }
        mock_cursor = MagicMock()
        mock_cursor.description = (("id",), ("name",))
        mock_cursor.fetchall.return_value = ((1, "a"), (2, "b"))
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        tool = QueryDbTool()
        out = tool.run(QueryDbArgs(sql="SELECT id, name FROM t"))

        self.assertEqual(out["columns"], ["id", "name"])
        self.assertEqual(out["rows"], [[1, "a"], [2, "b"]])
        self.assertEqual(out["row_count"], 2)
        mock_cursor.execute.assert_called_once_with("SELECT id, name FROM t")
        mock_cursor.close.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_show_tables_is_allowed(self) -> None:
        out = self._run_sql_with_mock_db("SHOW TABLES")

        self.assertEqual(out["columns"], ["id", "name"])
        self.assertEqual(out["rows"], [[1, "a"], [2, "b"]])
        self.assertEqual(out["row_count"], 2)

    def test_describe_is_allowed(self) -> None:
        out = self._run_sql_with_mock_db("DESCRIBE users")

        self.assertEqual(out["row_count"], 2)

    def test_desc_is_allowed(self) -> None:
        out = self._run_sql_with_mock_db("DESC users")

        self.assertEqual(out["row_count"], 2)

    def test_explain_is_allowed(self) -> None:
        out = self._run_sql_with_mock_db("EXPLAIN SELECT * FROM users")

        self.assertEqual(out["row_count"], 2)


if __name__ == "__main__":
    unittest.main()
