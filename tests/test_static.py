"""Static checks on the source (specs/003-dashboard-ui.md §6.1, §6.4, §6.6; plan 003 §4.3).

Files are parsed with ``ast``, never run. Covers AC-16, AC-38 and AC-46.
"""

import ast
import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
PACKAGE = SRC / "shopify_dashboard"
APP = PACKAGE / "app.py"

PURE_MODULES = ("filters.py", "display.py", "quality.py", "cache.py")
DATA_LAYER = ("loader", "sheets_client", "parsing", "validation", "calculations", "config")
ROOT_NAMES_ALLOWED = {"load_data", "DataSourceError", "cache", "display", "filters", "quality"}
DOTENV_NAME = re.compile(r"(?<![\w.-])\.env(?![\w.-])", re.IGNORECASE)


def _tree(source: str) -> ast.Module:
    return ast.parse(source)


def imported_modules(tree: ast.AST) -> set[str]:
    """Every module named by an ``import`` or ``from ... import`` anywhere in the tree."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def imports_top_level(tree: ast.AST, package: str) -> bool:
    """True if ``package`` or any of its submodules is imported."""
    return any(m == package or m.startswith(package + ".") for m in imported_modules(tree))


def data_layer_imports(tree: ast.AST) -> set[str]:
    """Data-layer modules imported by dotted path or ``from shopify_dashboard import x``."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "shopify_dashboard" and len(parts) > 1 and parts[1] in DATA_LAYER:
                    found.add(parts[1])
        elif isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if parts[0] != "shopify_dashboard":
                continue
            if len(parts) > 1 and parts[1] in DATA_LAYER:
                found.add(parts[1])
            elif len(parts) == 1:
                found.update(a.name for a in node.names if a.name in DATA_LAYER)
    return found


def package_root_names(tree: ast.AST) -> set[str]:
    """Names imported with ``from shopify_dashboard import ...``."""
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "shopify_dashboard"
        for alias in node.names
    }


def names_dotenv_file(tree: ast.AST) -> bool:
    """True if any string constant names the ``.env`` file on its own."""
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and DOTENV_NAME.search(node.value) is not None
        for node in ast.walk(tree)
    )


def _src_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


# --- The helpers catch what they should (seen failing on bad source) ---


@pytest.mark.parametrize(
    "source", ["import streamlit", "import streamlit as st", "from streamlit import cache_data"]
)
def test_helper_finds_streamlit_import(source: str) -> None:
    assert imports_top_level(_tree(source), "streamlit")


def test_helper_finds_nested_streamlit_import() -> None:
    assert imports_top_level(_tree("def f():\n    import streamlit.components.v1\n"), "streamlit")


def test_helper_ignores_similar_names() -> None:
    assert not imports_top_level(_tree("import streamlit_extras\nimport mystreamlit"), "streamlit")


@pytest.mark.parametrize(
    "source",
    [
        "from shopify_dashboard.loader import load_data",
        "from shopify_dashboard import sheets_client",
        "import shopify_dashboard.parsing",
        "from shopify_dashboard.validation import validate",
    ],
)
def test_helper_finds_data_layer_import(source: str) -> None:
    assert data_layer_imports(_tree(source))


@pytest.mark.parametrize(
    "source", ['x = ".env"', 'p = Path(root) / ".env"', "open('.env')", 'x = "load .ENV here"']
)
def test_helper_finds_dotenv_name(source: str) -> None:
    assert names_dotenv_file(_tree(source))


@pytest.mark.parametrize("source", ['x = ".env.example"', 'x = "my.env"', 'x = "environment"'])
def test_helper_allows_other_names(source: str) -> None:
    assert not names_dotenv_file(_tree(source))


# --- The real source ---


@pytest.mark.parametrize("module", PURE_MODULES)
def test_pure_modules_do_not_import_streamlit(module: str) -> None:
    """AC-38 (and plan §4.3 for the other pure modules)."""
    tree = _tree((PACKAGE / module).read_text(encoding="utf-8"))
    assert not imports_top_level(tree, "streamlit"), module


@pytest.mark.parametrize("path", _src_files(), ids=lambda p: p.name)
def test_src_does_not_import_dotenv(path: Path) -> None:
    """AC-46: no dotenv library under src/."""
    assert not imports_top_level(_tree(path.read_text(encoding="utf-8")), "dotenv")


@pytest.mark.parametrize("path", _src_files(), ids=lambda p: p.name)
def test_src_does_not_name_dotenv_file(path: Path) -> None:
    """AC-46: no file under src/ opens (or names) the .env file."""
    assert not names_dotenv_file(_tree(path.read_text(encoding="utf-8")))


def test_app_imports_nothing_from_data_layer() -> None:
    """AC-16: app.py reaches the data layer only through load_data (§6.1)."""
    assert data_layer_imports(_tree(APP.read_text(encoding="utf-8"))) == set()


def test_app_uses_only_load_data_from_package_root() -> None:
    """AC-16: from the package root, only load_data, DataSourceError and the UI helpers."""
    names = package_root_names(_tree(APP.read_text(encoding="utf-8")))
    assert "load_data" in names
    assert names <= ROOT_NAMES_ALLOWED
