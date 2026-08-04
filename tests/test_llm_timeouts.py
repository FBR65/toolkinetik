"""Tests for LLM call timeouts (#24)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from toolkinetik.coding_agent import SkillSpec
from toolkinetik.config import get_settings
from toolkinetik.intent import IntentEngine
from toolkinetik.skill_writer import SkillWriter


@pytest.fixture
def custom_timeout(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_TIMEOUT", "2")
    get_settings.cache_clear()
    yield 2
    get_settings.cache_clear()


def _slow_llm(sleep_s: float) -> MagicMock:
    """Mock LLM that sleeps <sleep_s> when no timeout kwarg is passed,
    and raises TimeoutError when timeout < sleep_s is passed."""
    llm = MagicMock()
    def _create(*args, **kwargs):
        t = kwargs.get("timeout", None)
        if t is not None and t < sleep_s:
            raise TimeoutError(f"LLM call timed out after {t}s")
        time.sleep(sleep_s)
        return MagicMock(choices=[MagicMock(message=MagicMock(content='{"intent": "chat"}'))])
    llm.chat.completions.create.side_effect = _create
    return llm


class TestLLMTimeoutConfig:
    def test_settings_has_llm_timeout_default(self, monkeypatch):
        monkeypatch.delenv("LLM_TIMEOUT", raising=False)
        get_settings.cache_clear()
        s = get_settings()
        assert s.LLM_TIMEOUT == 60
        get_settings.cache_clear()

    def test_settings_llm_timeout_env(self, custom_timeout):
        s = get_settings()
        assert s.LLM_TIMEOUT == 2

    def test_intent_engine_passes_timeout(self, custom_timeout, tmp_path):
        llm = MagicMock()
        llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content='{"intent": "chat"}'))]
        )
        engine = IntentEngine(registry=None, llm=llm)
        engine.analyze("hello")
        kwargs = llm.chat.completions.create.call_args.kwargs
        assert kwargs.get("timeout") == 2

    def test_skill_writer_generate_code_passes_timeout(self, custom_timeout, tmp_path):
        llm = MagicMock()
        llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content="```python\ndef t(): pass\n```\n```python\ndef x(): pass\n```"))]
        )
        writer = SkillWriter(llm=llm, registry=MagicMock(), db=MagicMock(),
                             skills_dir=str(tmp_path))
        writer._generate_code(SkillSpec(name="x", description="d", signature="def x():"))
        kwargs = llm.chat.completions.create.call_args.kwargs
        assert kwargs.get("timeout") == 2

    def test_skill_writer_llm_classify_passes_timeout(self, custom_timeout, tmp_path):
        llm = MagicMock()
        llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(
                content='{"name": "x", "description": "d", "signature": "def x()"}'))]
        )
        writer = SkillWriter(llm=llm, registry=MagicMock(), db=MagicMock(),
                             skills_dir=str(tmp_path))
        writer.generate_spec("create something")
        kwargs = llm.chat.completions.create.call_args.kwargs
        assert kwargs.get("timeout") == 2

    def test_skill_writer_revise_code_passes_timeout(self, custom_timeout, tmp_path):
        llm = MagicMock()
        llm.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="```python\ndef f(): pass\n```"))]
        )
        writer = SkillWriter(llm=llm, registry=MagicMock(), db=MagicMock(),
                             skills_dir=str(tmp_path))
        writer._revise_code("old", "err")
        kwargs = llm.chat.completions.create.call_args.kwargs
        assert kwargs.get("timeout") == 2

    def test_intent_engine_slow_llm_aborts(self, custom_timeout):
        # Timeout=2; sleep 5 → must abort within ~3s
        llm = _slow_llm(5)
        engine = IntentEngine(registry=None, llm=llm)
        start = time.monotonic()
        result = engine.analyze("hello")
        elapsed = time.monotonic() - start
        assert elapsed < 4, f"should abort within timeout, took {elapsed}"
        # Falls back to chat on exception
        assert result.action == "chat"