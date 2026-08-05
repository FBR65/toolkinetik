"""Tests for SkillTool and SkillExecutor (P0.7).

SPEC: docs/SPEC-production-readiness.md P0.7
Tier 3 — SKILL.md-based skills must be callable, delegating to a Coding-Agent.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from toolkinetik.skill_executor import SkillExecutor, SkillTool
from toolkinetik.skill_loader import SkillInfo


def _make_skill_info(name: str = "docx", description: str = "Create Word docs", tmp_path: Path | None = None) -> SkillInfo:
    return SkillInfo(
        name=name,
        description=description,
        version="1.0.0",
        skill_dir=tmp_path or Path("/tmp/skills/docx"),
        has_scripts=True,
        scripts_dir=(tmp_path or Path("/tmp/skills/docx")) / "scripts",
        body="# DOCX Skill\n\nDoes things.",
    )


class TestSkillTool:
    def test_skill_tool_is_callable(self):
        """SkillTool implements __call__ so it can be registered as a tool."""
        tool = SkillTool(_make_skill_info())
        assert callable(tool)

    def test_skill_tool_has_name(self):
        """SkillTool.__name__ matches the skill name from frontmatter."""
        tool = SkillTool(_make_skill_info(name="my_skill"))
        assert tool.__name__ == "my_skill"

    def test_skill_tool_has_doc(self):
        """SkillTool.__doc__ matches the skill description."""
        info = _make_skill_info(description="Create Word documents")
        tool = SkillTool(info)
        assert tool.__doc__ == "Create Word documents"

    def test_skill_tool_has_skill_path(self):
        """SkillTool._skill_dir points to the SKILL.md directory."""
        info = _make_skill_info()
        tool = SkillTool(info)
        assert tool._skill_dir == info.skill_dir

    def test_skill_tool_call_delegates_to_executor(self):
        """Calling a SkillTool delegates to SkillExecutor.execute."""
        executor = MagicMock(spec=SkillExecutor)
        executor.execute.return_value = "skill result"
        tool = SkillTool(_make_skill_info(), executor=executor)

        result = tool("create a doc", title="Test")

        executor.execute.assert_called_once()
        assert result == "skill result"

    def test_skill_tool_call_passes_args_to_executor(self):
        """Args and kwargs are forwarded to the executor."""
        executor = MagicMock(spec=SkillExecutor)
        executor.execute.return_value = "ok"
        tool = SkillTool(_make_skill_info(), executor=executor)

        tool("arg1", key="value")

        call_args = executor.execute.call_args
        assert call_args[0][1] == "arg1"  # positional
        assert call_args[1] == {"key": "value"}  # kwargs


class TestSkillExecutor:
    def test_execute_returns_string(self):
        """SkillExecutor.execute returns a string result."""
        executor = SkillExecutor(coding_agent=MagicMock())
        info = _make_skill_info()
        with patch.object(executor, "_delegate_to_agent", return_value="done"):
            result = executor.execute(info, "create a document")
        assert isinstance(result, str)
        assert result == "done"

    def test_execute_includes_skill_md_context(self):
        """The executor passes the SKILL.md body as context to the agent."""
        mock_agent = MagicMock()
        mock_agent.revise_code.return_value = ""
        executor = SkillExecutor(coding_agent=mock_agent)
        info = _make_skill_info()

        with patch.object(executor, "_delegate_to_agent") as mock_delegate:
            executor.execute(info, "do something")

        # The skill body should be part of the prompt.
        call_args = mock_delegate.call_args[0]
        prompt = call_args[1]
        assert "DOCX Skill" in prompt or "docx" in prompt.lower()

    def test_execute_without_agent_returns_fallback_message(self):
        """Without a coding agent, execute returns a graceful fallback."""
        executor = SkillExecutor(coding_agent=None)
        info = _make_skill_info()
        result = executor.execute(info, "do something")
        assert isinstance(result, str)
        assert "docx" in result.lower() or "skill" in result.lower()

    def test_executor_discovers_scripts(self):
        """SkillExecutor knows about scripts in the skill directory."""
        info = _make_skill_info()
        executor = SkillExecutor(coding_agent=MagicMock())
        assert executor.get_scripts(info) is not None