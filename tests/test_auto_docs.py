"""Tests for auto-documentation of promoted skills."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from toolkinetik.auto_docs import DocUpdater, SkillInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_skill(dir_path: str, filename: str, content: str) -> str:
    """Write a .py file into *dir_path* and return the full path."""
    p = Path(dir_path) / filename
    p.write_text(content)
    return str(p)


# ---------------------------------------------------------------------------
# _extract_skill_info
# ---------------------------------------------------------------------------


class TestExtractSkillInfo:
    def test_extract_skill_info(self):
        """Single function with docstring and type hints."""
        with TemporaryDirectory() as d:
            path = _write_skill(d, "mytool.py", (
                "def greet(name: str) -> str:\n"
                '    """Say hello to *name*."""\n'
                "    return f'Hello {name}'\n"
            ))
            updater = DocUpdater(skills_dir=d, docs_dir=str(Path(d) / "docs"))
            info = updater._extract_skill_info(path)

            assert isinstance(info, SkillInfo)
            assert info.module_name == "mytool"
            assert len(info.functions) == 1

            func = info.functions[0]
            assert func["name"] == "greet"
            assert "Say hello" in func["docstring"]
            assert func["args"] == "name"
            assert func["return_type"] == "str"

    def test_extract_skill_info_multiple_functions(self):
        """File with 2+ functions — all extracted."""
        with TemporaryDirectory() as d:
            path = _write_skill(d, "multi.py", (
                "def add(a: int, b: int) -> int:\n"
                '    """Add two numbers."""\n'
                "    return a + b\n\n"
                "def multiply(a: int, b: int) -> int:\n"
                '    """Multiply two numbers."""\n'
                "    return a * b\n"
            ))
            updater = DocUpdater(skills_dir=d, docs_dir=str(Path(d) / "docs"))
            info = updater._extract_skill_info(path)

            assert info.module_name == "multi"
            assert len(info.functions) == 2
            names = {f["name"] for f in info.functions}
            assert names == {"add", "multiply"}
            assert info.functions[0]["args"] == "a, b"

    def test_extract_skill_info_no_functions(self):
        """Empty file (or no public functions) → empty functions list."""
        with TemporaryDirectory() as d:
            path = _write_skill(d, "empty.py", "# just a comment\n")
            updater = DocUpdater(skills_dir=d, docs_dir=str(Path(d) / "docs"))
            info = updater._extract_skill_info(path)

            assert info.module_name == "empty"
            assert info.functions == []

    def test_extract_skill_info_skips_private(self):
        """Private functions (starting with _) are not documented."""
        with TemporaryDirectory() as d:
            path = _write_skill(d, "priv.py", (
                "def public_func():\n"
                '    """Public."""\n'
                "    pass\n\n"
                "def _private_func():\n"
                "    pass\n"
            ))
            updater = DocUpdater(skills_dir=d, docs_dir=str(Path(d) / "docs"))
            info = updater._extract_skill_info(path)

            assert len(info.functions) == 1
            assert info.functions[0]["name"] == "public_func"

    def test_extract_skill_info_varargs(self):
        """Function with *args and **kwargs is extracted correctly."""
        with TemporaryDirectory() as d:
            path = _write_skill(d, "varargs.py", (
                "def flexible(*args, **kwargs):\n"
                '    """Flexible function."""\n'
                "    pass\n"
            ))
            updater = DocUpdater(skills_dir=d, docs_dir=str(Path(d) / "docs"))
            info = updater._extract_skill_info(path)

            assert len(info.functions) == 1
            func = info.functions[0]
            assert "*args" in func["args"]
            assert "**kwargs" in func["args"]


# ---------------------------------------------------------------------------
# update_readme_table
# ---------------------------------------------------------------------------


class TestUpdateReadmeTable:
    def test_update_readme_table(self):
        """Verify table format with headers."""
        infos = [
            SkillInfo(
                module_name="weather",
                functions=[
                    {
                        "name": "get_weather",
                        "docstring": "Get the weather",
                        "args": "city",
                        "return_type": "dict",
                    }
                ],
            ),
            SkillInfo(module_name="empty", functions=[]),
        ]
        updater = DocUpdater(skills_dir="/tmp/nonexistent_skills", docs_dir="/tmp/docs_test")
        table = updater.update_readme_table(infos)

        assert "# Skill Documentation" in table
        assert "| Module | Function | Args | Return Type | Description |" in table
        assert "|--------|" in table
        assert "weather" in table
        assert "get_weather" in table
        assert "Get the weather" in table
        assert "empty" in table  # module with no functions still listed

    def test_update_readme_table_empty(self):
        """Empty skill list → still produces header table."""
        updater = DocUpdater(skills_dir="/tmp/nonexistent", docs_dir="/tmp/docs_test2")
        table = updater.update_readme_table([])
        assert "| Module | Function |" in table
        assert table.endswith("\n")


# ---------------------------------------------------------------------------
# update_skill_docs
# ---------------------------------------------------------------------------


class TestUpdateSkillDocs:
    def test_update_skill_docs(self):
        """Create a skills dir with test files, verify markdown output + file written."""
        with TemporaryDirectory() as d:
            skills_dir = Path(d) / "skills"
            docs_dir = Path(d) / "docs"
            skills_dir.mkdir()

            _write_skill(str(skills_dir), "adder.py", (
                "def add(a: int, b: int) -> int:\n"
                '    """Add two numbers."""\n'
                "    return a + b\n"
            ))
            _write_skill(str(skills_dir), "greeter.py", (
                "def greet(name: str) -> str:\n"
                '    """Greet someone."""\n'
                "    return f'Hi {name}'\n"
            ))

            updater = DocUpdater(
                skills_dir=str(skills_dir),
                docs_dir=str(docs_dir),
            )
            markdown = updater.update_skill_docs()

            # Content checks
            assert "# Skill Documentation" in markdown
            assert "adder" in markdown
            assert "add" in markdown
            assert "Add two numbers" in markdown
            assert "greeter" in markdown
            assert "greet" in markdown

            # File was written
            skills_md = docs_dir / "skills.md"
            assert skills_md.exists()
            assert skills_md.read_text() == markdown

    def test_update_skill_docs_empty_dir(self):
        """Empty skills dir → only the table header."""
        with TemporaryDirectory() as d:
            skills_dir = Path(d) / "skills"
            docs_dir = Path(d) / "docs"
            skills_dir.mkdir()

            updater = DocUpdater(
                skills_dir=str(skills_dir),
                docs_dir=str(docs_dir),
            )
            markdown = updater.update_skill_docs()

            assert "| Module | Function |" in markdown
            # File was still written.
            assert (docs_dir / "skills.md").exists()

    def test_update_skill_docs_skips_dunder(self):
        """__init__.py files are skipped."""
        with TemporaryDirectory() as d:
            skills_dir = Path(d) / "skills"
            docs_dir = Path(d) / "docs"
            skills_dir.mkdir()

            _write_skill(str(skills_dir), "__init__.py", "")
            _write_skill(str(skills_dir), "real.py", (
                "def real_func():\n"
                '    """Real."""\n'
                "    pass\n"
            ))

            updater = DocUpdater(
                skills_dir=str(skills_dir),
                docs_dir=str(docs_dir),
            )
            markdown = updater.update_skill_docs()

            assert "real" in markdown
            assert "__init__" not in markdown


# ---------------------------------------------------------------------------
# DocUpdater __init__
# ---------------------------------------------------------------------------


class TestDocUpdaterInit:
    def test_doc_updater_init(self):
        """Verify defaults are set correctly."""
        updater = DocUpdater()
        assert updater.skills_dir is not None
        assert updater.docs_dir == "docs"
        # db can be None by default.
        assert updater.db is None or updater.db is not None  # just verify attr exists

    def test_doc_updater_init_custom(self):
        """Custom args are respected."""
        with TemporaryDirectory() as d:
            skills_dir = str(Path(d) / "skills")
            docs_dir = str(Path(d) / "docs")
            updater = DocUpdater(skills_dir=skills_dir, docs_dir=docs_dir)
            assert updater.skills_dir == skills_dir
            assert updater.docs_dir == docs_dir