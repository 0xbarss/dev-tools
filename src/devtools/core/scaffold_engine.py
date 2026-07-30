"""`devtools new <template> <name>` — scaffold a new project from a small,
built-in set of templates (backlog #33, P2). Deliberately minimal: a few
opinionated, batteries-included starting points rather than a general
templating engine (no Cookiecutter-style variable substitution) -- that
keeps this predictable and dependency-free, in keeping with the rest of
the toolkit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_MIT_LICENSE = """MIT License

Copyright (c) {year} {author}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

_PY_GITIGNORE = """__pycache__/
*.pyc
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
.mypy_cache/
.ruff_cache/
"""

_NODE_GITIGNORE = """node_modules/
dist/
build/
*.log
.DS_Store
"""


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _scaffold_python_cli(target: Path, name: str) -> None:
    pkg = name.replace("-", "_")
    _write(
        target / "pyproject.toml",
        f"""[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "0.1.0"
description = "TODO: describe {name}."
readme = "README.md"
requires-python = ">=3.9"
license = {{ text = "MIT" }}
dependencies = [
    "typer>=0.12",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
{name} = "{pkg}.cli:app"

[tool.setuptools.packages.find]
where = ["src"]
""",
    )
    _write(
        target / "src" / pkg / "__init__.py",
        f'"""{name}."""\n\n__version__ = "0.1.0"\n',
    )
    _write(
        target / "src" / pkg / "cli.py",
        f'''"""{name} — command-line entry point."""

import typer

app = typer.Typer()


@app.command()
def main(name: str = typer.Argument("world", help="Who to greet.")) -> None:
    """A starting-point command -- replace me."""
    print(f"Hello, {{name}}!")


if __name__ == "__main__":
    app()
''',
    )
    _write(target / "tests" / f"test_{pkg}.py", f'"""Tests for {name}."""\n\n\ndef test_placeholder() -> None:\n    assert True\n')
    _write(target / "README.md", f"# {name}\n\nTODO: describe {name}.\n\n## Installation\n\n```bash\npip install -e .\n```\n\n## Usage\n\n```bash\n{name} world\n```\n")
    _write(target / ".gitignore", _PY_GITIGNORE)


def _scaffold_python_lib(target: Path, name: str) -> None:
    pkg = name.replace("-", "_")
    _write(
        target / "pyproject.toml",
        f"""[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "0.1.0"
description = "TODO: describe {name}."
readme = "README.md"
requires-python = ">=3.9"
license = {{ text = "MIT" }}
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.setuptools.packages.find]
where = ["src"]
""",
    )
    _write(target / "src" / pkg / "__init__.py", f'"""{name}."""\n\n__version__ = "0.1.0"\n')
    _write(target / "tests" / f"test_{pkg}.py", f'"""Tests for {name}."""\n\n\ndef test_placeholder() -> None:\n    assert True\n')
    _write(target / "README.md", f"# {name}\n\nTODO: describe {name}.\n\n## Installation\n\n```bash\npip install {name}\n```\n")
    _write(target / ".gitignore", _PY_GITIGNORE)


def _scaffold_node_lib(target: Path, name: str) -> None:
    _write(
        target / "package.json",
        f"""{{
  "name": "{name}",
  "version": "0.1.0",
  "description": "TODO: describe {name}.",
  "main": "src/index.js",
  "type": "module",
  "scripts": {{
    "test": "node --test"
  }},
  "license": "MIT"
}}
""",
    )
    _write(target / "src" / "index.js", f"// {name}\n\nexport function main() {{\n  console.log('Hello from {name}!');\n}}\n")
    _write(
        target / "test" / "index.test.js",
        "import test from 'node:test';\nimport assert from 'node:assert';\n\ntest('placeholder', () => {\n  assert.ok(true);\n});\n",
    )
    _write(target / "README.md", f"# {name}\n\nTODO: describe {name}.\n\n## Installation\n\n```bash\nnpm install\n```\n\n## Usage\n\n```bash\nnpm test\n```\n")
    _write(target / ".gitignore", _NODE_GITIGNORE)


@dataclass
class Template:
    name: str
    description: str
    scaffold: Callable[[Path, str], None]


TEMPLATES: dict[str, Template] = {
    "python-cli": Template("python-cli", "A Typer-based Python CLI (src layout, pyproject.toml, one test).", _scaffold_python_cli),
    "python-lib": Template("python-lib", "A minimal installable Python library (src layout, pyproject.toml, one test).", _scaffold_python_lib),
    "node-lib": Template("node-lib", "A minimal ESM Node library (package.json, node:test).", _scaffold_node_lib),
}


def scaffold(template_name: str, target: Path, name: str, license_: bool = True, author: str = "Your Name") -> list[str]:
    """Create `target/` (must not already exist or must be empty) from the
    named template. Returns the list of created file paths (relative)."""
    template = TEMPLATES.get(template_name)
    if template is None:
        raise ValueError(f"Unknown template '{template_name}'. Available: {', '.join(sorted(TEMPLATES))}")

    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"{target} already exists and is not empty.")

    template.scaffold(target, name)
    if license_:
        from datetime import date

        _write(target / "LICENSE", _MIT_LICENSE.format(year=date.today().year, author=author))

    return sorted(str(p.relative_to(target)) for p in target.rglob("*") if p.is_file())
