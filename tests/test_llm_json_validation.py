"""Tests for LLM JSON response validation (#25)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from toolkinetik.intent import IntentEngine
from toolkinetik.skill_writer import SkillWriter


def _llm_with_content(content: str) -> MagicMock:
    llm = MagicMock()
    llm.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=content))]
    )
    return llm


class TestIntentJsonValidation:
    def test_valid_execute_skill_json(self, tmp_path):
        llm = _llm_with_content('{"intent": "execute_skill", "skill_name": "foo"}')
        engine = IntentEngine(registry=None, llm=llm)
        result = engine.analyze("run foo")
        assert result.action == "execute_skill"
        assert result.skill_name == "foo"

    def test_valid_create_skill_json(self, tmp_path):
        llm = _llm_with_content(
            '{"intent": "create_skill", "skill_name": "new_skill", '
            '"description": "does thing", "signature": "def new_skill():"}'
        )
        engine = IntentEngine(registry=None, llm=llm)
        result = engine.analyze("make new skill")
        assert result.action == "create_skill"
        assert result.skill_spec is not None
        assert result.skill_spec.name == "new_skill"

    def test_malformed_json_falls_back_to_chat(self, caplog):
        llm = _llm_with_content("not json at all")
        engine = IntentEngine(registry=None, llm=llm)
        with caplog.at_level(logging.WARNING, logger="toolkinetik.intent"):
            result = engine.analyze("hello")
        assert result.action == "chat"
        assert len(caplog.records) > 0, "must log malformed JSON"

    def test_unknown_intent_falls_back_to_chat(self, caplog):
        llm = _llm_with_content('{"intent": "unknown_xyz"}')
        engine = IntentEngine(registry=None, llm=llm)
        with caplog.at_level(logging.WARNING, logger="toolkinetik.intent"):
            result = engine.analyze("hello")
        assert result.action == "chat"
        assert len(caplog.records) > 0

    def test_missing_intent_key_falls_back(self):
        llm = _llm_with_content('{"skill_name": "foo"}')
        engine = IntentEngine(registry=None, llm=llm)
        result = engine.analyze("foo")
        assert result.action == "chat"

    def test_execute_skill_missing_skill_name(self):
        llm = _llm_with_content('{"intent": "execute_skill"}')
        engine = IntentEngine(registry=None, llm=llm)
        result = engine.analyze("run")
        assert result.action == "execute_skill"
        assert result.skill_name == ""


class TestSkillWriterJsonValidation:
    def test_malformed_json_falls_back_to_heuristic(self, tmp_path, caplog):
        llm = _llm_with_content("{broken")
        writer = SkillWriter(llm=llm, registry=MagicMock(), db=MagicMock(),
                             skills_dir=str(tmp_path))
        with caplog.at_level(logging.WARNING, logger="toolkinetik.skill_writer"):
            spec = writer.generate_spec("create fibonacci calc")
        assert spec is not None
        assert spec.name  # heuristic name
        assert len(caplog.records) > 0

    def test_missing_name_uses_extract(self, tmp_path):
        llm = _llm_with_content('{"description": "does thing"}')
        writer = SkillWriter(llm=llm, registry=MagicMock(), db=MagicMock(),
                             skills_dir=str(tmp_path))
        spec = writer.generate_spec("calculate fibonacci")
        assert spec is not None
        assert "fibonacci" in spec.name or "calculate" in spec.name