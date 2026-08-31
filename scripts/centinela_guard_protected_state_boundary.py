from __future__ import annotations

import ast
from pathlib import Path

APP_ROOT = Path("app")
RAW_STATE_MACHINE_MODULE = "app.services.centinela.orchestration.state_machine"
AUTHORIZED_RAW_IMPORTERS = {
    Path("app/services/centinela/orchestration/protected_state_machine.py"),
}
AUTHORIZED_PROTECTED_STATUS_WRITERS = {
    Path("app/services/centinela/orchestration/state_machine.py"),
}
PROTECTED_STATES = {"FINAL_APPROVED", "PUBLICATION_PACKAGE_READY"}


def _source_mentions_protected_state(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and child.value in PROTECTED_STATES:
            return True
        if isinstance(child, ast.Attribute) and child.attr in PROTECTED_STATES:
            return True
    return False


def _status_targets(node: ast.Assign | ast.AnnAssign) -> list[ast.AST]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    return [node.target]


def main() -> None:
    violations: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=path.as_posix())

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imports_raw_machine = any(
                    alias.name == "ProjectStateMachine" for alias in node.names
                ) and (
                    node.module == RAW_STATE_MACHINE_MODULE
                    or (
                        path.parent == Path("app/services/centinela/orchestration")
                        and node.level == 1
                        and node.module == "state_machine"
                    )
                )
                if imports_raw_machine and path not in AUTHORIZED_RAW_IMPORTERS:
                    violations.append(
                        f"{path}:{node.lineno}: raw ProjectStateMachine import is forbidden"
                    )

            if isinstance(node, ast.Import):
                if any(alias.name == RAW_STATE_MACHINE_MODULE for alias in node.names):
                    if path not in AUTHORIZED_RAW_IMPORTERS:
                        violations.append(
                            f"{path}:{node.lineno}: raw state_machine module import is forbidden"
                        )

            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                if value is None or not _source_mentions_protected_state(value):
                    continue
                for target in _status_targets(node):
                    if isinstance(target, ast.Attribute) and target.attr == "status":
                        if path not in AUTHORIZED_PROTECTED_STATUS_WRITERS:
                            violations.append(
                                f"{path}:{node.lineno}: direct protected project status mutation is forbidden"
                            )

    if violations:
        raise SystemExit("\n".join(["PROTECTED_STATE_BOUNDARY=FAIL", *violations]))

    print("RAW_STATE_MACHINE_IMPORT_BOUNDARY=PASS")
    print("DIRECT_PROTECTED_STATUS_MUTATION_GUARD=PASS")


if __name__ == "__main__":
    main()
