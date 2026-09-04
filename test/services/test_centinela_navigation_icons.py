import re
from pathlib import Path

from streamlit.string_util import validate_material_icon


def test_centinela_navigation_material_icons_are_supported() -> None:
    source = Path("webui/Centinela.py").read_text(encoding="utf-8")
    icons = re.findall(r'icon="(:material/[a-z0-9_]+:)"', source)

    assert icons, "Centinela navigation should declare its Material icons explicitly"
    for icon in icons:
        assert validate_material_icon(icon) == icon
