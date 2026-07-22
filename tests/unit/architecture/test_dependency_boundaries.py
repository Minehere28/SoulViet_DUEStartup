import ast
from pathlib import Path

PROHIBITED = {
    "fastapi",
    "langgraph",
    "neo4j",
    "openai",
    "qdrant_client",
    "services",
    "soulviet_cli",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_domain_packages_do_not_import_apps_services_or_infrastructure() -> None:
    sources = [
        *Path("packages/contracts/src").rglob("*.py"),
        *Path("packages/compiler/src").rglob("*.py"),
    ]
    for source in sources:
        assert not (_imports(source) & PROHIBITED), source


def test_contracts_use_only_the_standard_library() -> None:
    allowed = {
        "__future__",
        "collections",
        "dataclasses",
        "datetime",
        "soulviet_contracts",
        "types",
        "typing",
        "uuid",
    }
    for source in Path("packages/contracts/src").rglob("*.py"):
        assert _imports(source) <= allowed, source
