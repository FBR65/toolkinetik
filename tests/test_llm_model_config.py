"""Tests that LLM calls use settings.OPENAI_MODEL (#7).

SPEC: docs/SPEC-25-improvements.md #7
Tier 2 — intent.py and skill_writer.py must not hardcode model="gpt-4o".
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from toolkinetik.coding_agent import SkillSpec
from toolkinetik.config import get_settings
from toolkinetik.intent import IntentEngine
from toolkinetik.skill_writer import SkillWriter


@pytest.fixture
def custom_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_MODEL", "llama3-test")
    get_settings.cache_clear()
    yield "llama3-test"
    get_settings.cache_clear()


def _mock_llm_response(content: str = '{"intent": "chat"}') -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=content))]
    return resp


class TestIntentEngineModelConfig:
    def test_intent_engine_uses_settings_model(self, custom_model, tmp_path):
        llm = MagicMock()
        llm.chat.completions.create.return_value = _mock_llm_response()
        engine = IntentEngine(registry=None, llm=llm)
        engine.analyze("hello")
        kwargs = llm.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == custom_model

    def test_intent_engine_default_gpt4o(self, monkeypatch, tmp_path):
        # Clear env to use default
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        get_settings.cache_clear()
        llm = MagicMock()
        llm.chat.completions.create.return_value = _mock_llm_response()
        engine = IntentEngine(registry=None, llm=llm)
        engine.analyze("hello")
        kwargs = llm.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == "gpt-4o"
        get_settings.cache_clear()


class TestSkillWriterModelConfig:
    def test_generate_code_uses_settings_model(self, custom_model, tmp_path):
        llm = MagicMock()
        llm.chat.completions.create.return_value = _mock_llm_response(
            "```python\ndef t(): pass\n```\n```python\ndef x(): pass\n```"
        )
        writer = SkillWriter(llm=llm, registry=MagicMock(), db=MagicMock(),
                             skills_dir=str(tmp_path))
        spec = SkillSpec(name="x", description="d", signature="def x():")
        writer._generate_code(spec)
        kwargs = llm.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == custom_model

    def test_llm_classify_uses_settings_model(self, custom_model, tmp_path):
        llm = MagicMock()
        llm.chat.completions.create.return_value = _mock_llm_response(
            '{"name": "x", "description": "d", "signature": "def x()"}'
        )
        writer = SkillWriter(llm=llm, registry=MagicMock(), db=MagicMock(),
                             skills_dir=str(tmp_path))
        writer.generate_spec("create something")
        kwargs = llm.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == custom_model

    def test_revise_code_uses_settings_model(self, custom_model, tmp_path):
        llm = MagicMock()
        llm.chat.completions.create.return_value = _mock_llm_response(
            "```python\ndef fixed(): pass\n```"
        )
        writer = SkillWriter(llm=llm, registry=MagicMock(), db=MagicMock(),
                             skills_dir=str(tmp_path))
        writer._revise_code("old code", "some error")
        kwargs = llm.chat.completions.create.call_args.kwargs
        assert kwargs["model"] == custom_model