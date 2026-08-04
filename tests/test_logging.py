"""Tests for structured logging in defensive boundaries (#23).

SPEC: docs/SPEC-25-improvements.md #23
Tier 3 — defensive except blocks must log via logging, not silently pass.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from unittest.mock import MagicMock

SRC = Path(__file__).resolve().parent.parent / "src" / "toolkinetik"


def _source(module: str) -> str:
    return (SRC / f"{module}.py").read_text()


class TestLoggerSetup:
    def test_skill_writer_has_logger(self):
        src = _source("skill_writer")
        assert "import logging" in src
        assert re.search(r"logger\s*=\s*logging\.getLogger\(__name__\)", src), \
            "skill_writer.py must have a module-level logger"

    def test_setup_mcp_has_logger(self):
        src = _source("setup_mcp")
        assert "import logging" in src
        assert re.search(r"logger\s*=\s*logging\.getLogger\(__name__\)", src), \
            "setup_mcp.py must have a module-level logger"

    def test_promotion_has_logger(self):
        src = _source("promotion")
        assert "import logging" in src
        assert re.search(r"logger\s*=\s*logging\.getLogger\(__name__\)", src), \
            "promotion.py must have a module-level logger"

    def test_sandbox_has_logger(self):
        src = _source("sandbox")
        assert "import logging" in src
        assert re.search(r"logger\s*=\s*logging\.getLogger\(__name__\)", src), \
            "sandbox.py must have a module-level logger"

    def test_intent_has_logger(self):
        src = _source("intent")
        assert "import logging" in src
        assert re.search(r"logger\s*=\s*logging\.getLogger\(__name__\)", src), \
            "intent.py must have a module-level logger"


class TestDefensiveExceptLogs:
    def test_skill_writer_research_logs_exception(self, tmp_path, caplog):
        from toolkinetik.coding_agent import SkillSpec
        from toolkinetik.skill_writer import SkillWriter
        wigolo = MagicMock()
        wigolo.research.side_effect = RuntimeError("network down")
        writer = SkillWriter(wigolo=wigolo, registry=MagicMock(), db=MagicMock(),
                             skills_dir=str(tmp_path))
        spec = SkillSpec(name="x", description="d", signature="def x():")
        with caplog.at_level(logging.WARNING, logger="toolkinetik.skill_writer"):
            result = writer._research_dependencies(spec)
        assert result == ""  # graceful
        assert any("network down" in r.message or "research" in r.message.lower()
                   for r in caplog.records), "must log the exception"

    def test_setup_mcp_research_logs_fallback(self, caplog):
        from toolkinetik.setup_mcp import WigoloMCPToolkit, _StubClient
        client = MagicMock()
        client.research.side_effect = RuntimeError("server unavailable")
        client._stub = _StubClient()  # so the fallback uses a real stub
        toolkit = WigoloMCPToolkit(client=client)
        with caplog.at_level(logging.WARNING, logger="toolkinetik.setup_mcp"):
            result = toolkit.research("query")
        assert "error" in result or "unavailable" in str(result)
        assert len(caplog.records) > 0, "must log the fallback"

    def test_promotion_rollback_logs_db_error(self, tmp_path, caplog):
        from toolkinetik.promotion import SkillPromoter
        db = MagicMock()
        db.delete_skill.side_effect = RuntimeError("db locked")
        reg = MagicMock()
        reg.get_tools.return_value = []
        promoter = SkillPromoter(skills_dir=str(tmp_path), registry=reg, db=db)
        with caplog.at_level(logging.ERROR, logger="toolkinetik.promotion"):
            ok = promoter.rollback("missing_skill")
        assert ok is True  # rollback still succeeds for missing file
        assert len(caplog.records) > 0, "must log DB error"