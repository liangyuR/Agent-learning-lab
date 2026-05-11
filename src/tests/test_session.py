"""会话状态模型与磁盘读写。"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from session.message import ChatMessage
from session.session import (
    append_message,
    assert_safe_session_id,
    clear_session,
    create_session,
    load_or_create_session,
    load_session,
    save_session,
    session_file_path,
)


class TestCreateSession(unittest.TestCase):
    def test_default_fields(self) -> None:
        state = create_session("default")
        self.assertEqual(state.session_id, "default")
        self.assertEqual(state.messages, [])
        self.assertIsNone(state.summary)
        self.assertEqual(state.variables, {})


class TestSaveLoadRoundtrip(unittest.TestCase):
    def test_append_messages_datetime_roundtrip(self) -> None:
        fixed = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        u = ChatMessage(role="user", content="hi", created_at=fixed)
        a = ChatMessage(role="assistant", content="hello", created_at=fixed)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = create_session("abc")
            append_message(state, u)
            append_message(state, a)
            state.variables["k"] = 1
            save_session(state, root)
            loaded = load_session("abc", root)
            self.assertEqual(loaded.session_id, "abc")
            self.assertEqual(len(loaded.messages), 2)
            self.assertEqual(loaded.messages[0].role, "user")
            self.assertEqual(loaded.messages[0].content, "hi")
            self.assertEqual(loaded.messages[0].created_at, fixed)
            self.assertEqual(loaded.messages[1].content, "hello")
            self.assertEqual(loaded.variables, {"k": 1})


class TestClearSession(unittest.TestCase):
    def test_clear_keeps_variables_by_default(self) -> None:
        state = create_session("s1")
        append_message(state, ChatMessage(role="user", content="x"))
        state.summary = "old"
        state.variables["prefs"] = "y"
        clear_session(state)
        self.assertEqual(state.messages, [])
        self.assertIsNone(state.summary)
        self.assertEqual(state.variables, {"prefs": "y"})

    def test_clear_with_variables(self) -> None:
        state = create_session("s2")
        state.variables["a"] = 1
        clear_session(state, clear_variables=True)
        self.assertEqual(state.variables, {})


class TestSafeSessionId(unittest.TestCase):
    def test_rejects_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            assert_safe_session_id("../evil")
        with self.assertRaises(ValueError):
            assert_safe_session_id("a/b")
        with self.assertRaises(ValueError):
            assert_safe_session_id("x\\y")

    def test_rejects_empty(self) -> None:
        with self.assertRaises(ValueError):
            assert_safe_session_id("")
        with self.assertRaises(ValueError):
            assert_safe_session_id("   ")


class TestLoadOrCreate(unittest.TestCase):
    def test_creates_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = load_or_create_session("newid", root)
            self.assertEqual(state.session_id, "newid")
            self.assertFalse((root / "newid.json").exists())

    def test_save_on_create(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = load_or_create_session("x", root, save_on_create=True)
            self.assertTrue((root / "x.json").is_file())
            self.assertEqual(load_session("x", root).session_id, state.session_id)

    def test_loads_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            s = create_session("exist")
            append_message(s, ChatMessage(role="user", content="u"))
            save_session(s, root)
            loaded = load_or_create_session("exist", root)
            self.assertEqual(len(loaded.messages), 1)


class TestLoadSessionErrors(unittest.TestCase):
    def test_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                load_session("nope", Path(tmp))

    def test_session_id_mismatch_in_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.mkdir(exist_ok=True)
            bad = {"session_id": "other", "messages": [], "summary": None, "variables": {}}
            (root / "name.json").write_text(
                json.dumps(bad, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_session("name", root)


class TestSessionFilePath(unittest.TestCase):
    def test_resolves_under_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = session_file_path("my-session", root)
            self.assertEqual(p.name, "my-session.json")
            self.assertEqual(p.parent.resolve(), root.resolve())
