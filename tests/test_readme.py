"""TDD: Tests für README.md Aktualisierung."""

from pathlib import Path

README_PATH = Path(__file__).parent.parent / "README.md"


def test_readme_contains_intent_engine():
    """README mentions IntentEngine as the new LLM-driven intent detection."""
    content = README_PATH.read_text()
    assert "IntentEngine" in content


def test_readme_contains_skill_writer():
    """README mentions SkillWriter (the meta-skill that creates skills)."""
    content = README_PATH.read_text()
    assert "SkillWriter" in content


def test_readme_contains_wigolo():
    """README mentions wigolo as the MCP research tool."""
    content = README_PATH.read_text()
    assert "wigolo" in content.lower()


def test_readme_contains_rag_support():
    """README documents RAG support with LanceDB + HuggingFace."""
    content = README_PATH.read_text()
    assert "RAG" in content or "LanceDB" in content
    assert "HuggingFace" in content or "sentence-transformers" in content


def test_readme_contains_updated_test_count():
    """README reflects updated test count (216 tests)."""
    content = README_PATH.read_text()
    assert "216" in content


def test_readme_contains_architecture_diagram_update():
    """Architecture diagram includes IntentEngine + SkillWriter + RagManager."""
    content = README_PATH.read_text()
    assert "IntentEngine" in content
    assert "RagManager" in content


def test_readme_contains_project_structure_update():
    """Project Structure lists new files (setup_mcp, rag_manager, skill_writer)."""
    content = README_PATH.read_text()
    assert "setup_mcp" in content
    assert "rag_manager" in content
    assert "skill_writer" in content
