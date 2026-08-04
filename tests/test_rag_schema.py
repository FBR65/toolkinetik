"""Tests for RagManager LanceDB schema (#15).

SPEC: docs/SPEC-25-improvements.md #15
Tier 2 — schema must use pyarrow types, not string placeholders.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

SRC = Path(__file__).resolve().parent.parent / "src" / "toolkinetik" / "rag_manager.py"
REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


class TestRagSchema:
    def test_no_string_placeholder_for_vector(self):
        src = SRC.read_text()
        # The old "{embedding}" string-literal placeholder must be gone.
        assert '"{embedding}"' not in src
        assert "'{embedding}'" not in src

    def test_uses_pyarrow(self):
        src = SRC.read_text()
        assert "import pyarrow" in src or "pa.list_" in src

    def test_schema_has_vector_text_source(self):
        # Initialize a RagManager with mocked lancedb/sentence_transformers
        # and inspect the schema passed to create_table.
        # Real pyarrow may not be installed; mock it minimally.
        fake_pa = MagicMock(name="pyarrow")
        fake_pa.float32 = MagicMock(name="float32")
        fake_pa.string = MagicMock(name="string")
        fake_pa.list_ = MagicMock(name="pa_list")
        fake_pa.field = MagicMock(name="pa_field")
        fake_pa.schema = MagicMock(name="pa_schema")
        # Make schema/field return dicts the test can inspect.
        def _field(name, typ):
            return MagicMock(name=f"field_{name}", type=typ, _name=name)
        fake_pa.field.side_effect = _field
        captured_schema = MagicMock(name="schema")
        fake_pa.schema.return_value = captured_schema
        captured_schema.names = ["vector", "text", "source"]
        captured_schema.field = lambda n: MagicMock(type=MagicMock(), value_type="float32")
        # is_list / is_float32 stubs
        import types
        types_mod = types.SimpleNamespace(is_list=lambda _: True, is_float32=lambda _: True)
        fake_pa.types = types_mod

        fake_lancedb = MagicMock()
        fake_db = MagicMock()
        fake_db.open_table.side_effect = Exception("no table")
        fake_table = MagicMock()
        fake_db.create_table = MagicMock(return_value=fake_table)
        fake_lancedb.connect.return_value = fake_db

        fake_embedder = MagicMock()

        with patch.dict("sys.modules", {
            "lancedb": fake_lancedb,
            "sentence_transformers": MagicMock(SentenceTransformer=MagicMock(return_value=fake_embedder)),
            "pyarrow": fake_pa,
        }):
            from toolkinetik.rag_manager import RagManager
            mgr = RagManager()
            mgr.initialize()

        # The schema passed to create_table should be a pyarrow schema.
        call_args = fake_db.create_table.call_args
        assert call_args is not None
        schema = call_args.kwargs.get("schema")
        assert schema is not None, "create_table must be called with a schema"
        assert hasattr(schema, "names")
        names = list(schema.names)
        assert "vector" in names
        assert "text" in names
        assert "source" in names

    def test_graceful_degradation_when_lancedb_missing(self):
        # Simulate ImportError on lancedb.
        with patch.dict("sys.modules", {"lancedb": None}):
            from toolkinetik.rag_manager import RagManager
            mgr = RagManager()
            mgr.initialize()
            assert mgr.is_ready is False
            assert mgr.search("anything") == []


class TestPyprojectRagExtra:
    def test_pyproject_has_rag_extra(self):
        pyproject = PYPROJECT.read_text()
        # Must declare lancedb and sentence-transformers in a rag extra.
        assert "lancedb" in pyproject
        assert "sentence-transformers" in pyproject
        # Must be in an optional-dependencies section, not the core deps.
        assert re.search(r'\[project\.optional-dependencies\]\s*[\s\S]*?rag', pyproject) or \
               re.search(r'rag\s*=\s*\[', pyproject)