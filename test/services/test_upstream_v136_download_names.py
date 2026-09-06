import ast
import re
from pathlib import Path


ROOT_DIR = Path(__file__).parent.parent.parent
WEBUI_MAIN = ROOT_DIR / "webui" / "Main.py"


def _load_download_name_helper():
    tree = ast.parse(WEBUI_MAIN.read_text(encoding="utf-8"))
    selected = []
    wanted = {
        "_DOWNLOAD_FILENAME_INVALID_PATTERN",
        "_WINDOWS_RESERVED_FILENAMES",
    }
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in wanted
            for target in node.targets
        ):
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "_build_video_download_name":
            selected.append(node)

    namespace = {"re": re, "frozenset": frozenset, "range": range}
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    exec(compile(module, str(WEBUI_MAIN), "exec"), namespace)
    return namespace["_build_video_download_name"]


def test_windows_reserved_download_names_are_prefixed():
    build_name = _load_download_name_helper()

    assert build_name("CON", 1, 1) == "_CON.mp4"
    assert build_name("aux.extra", 1, 1) == "_aux.extra.mp4"
    assert build_name("lpt1", 1, 1) == "_lpt1.mp4"


def test_normal_download_name_is_unchanged():
    build_name = _load_download_name_helper()
    assert build_name("Eclipse total", 1, 1) == "Eclipse total.mp4"
