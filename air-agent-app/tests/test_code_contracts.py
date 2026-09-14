"""Keep teaching code documented, annotated, and offline workflow entry points thin."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_all_functions_have_annotations_and_docstrings() -> None:
    """Inspect application and test functions, including nested callbacks."""
    problems: list[str] = []
    for directory in (PROJECT_ROOT / "src", PROJECT_ROOT / "tests"):
        for path in directory.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
                args += [arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None]
                missing = [
                    arg.arg
                    for arg in args
                    if arg.arg not in ("self", "cls") and arg.annotation is None
                ]
                if node.returns is None:
                    missing.append("return")
                if not ast.get_docstring(node):
                    missing.append("docstring")
                if missing:
                    problems.append(f"{path.name}:{node.lineno} {node.name}: {missing}")
    assert not problems, "\n".join(problems)


def test_core_packages_do_not_import_mock_adapters() -> None:
    """Keep scenario composition in CLI/mock packages instead of reusable runtime code."""
    for directory in ("agent", "context", "investigation"):
        for path in (PROJECT_ROOT / "src" / "air_agent_app" / directory).rglob("*.py"):
            if "cli" in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith("air_agent_app.tools.mock"), path
                elif isinstance(node, ast.Import):
                    assert not any(
                        alias.name.startswith("air_agent_app.tools.mock") for alias in node.names
                    ), path


def test_command_modules_are_thin_callers() -> None:
    """Reject functions, classes, loops, or multiple application calls in launchers."""
    for path in (PROJECT_ROOT / "src" / "air_agent_app" / "commands").glob("*.py"):
        tree = ast.parse(path.read_text())
        assert not any(
            isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.For, ast.While))
            for node in ast.walk(tree)
        )
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        application_calls = [
            node
            for node in calls
            if not isinstance(node.func, ast.Name) or node.func.id != "SystemExit"
        ]
        assert len(application_calls) <= 1
