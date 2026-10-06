"""ffman's README: what it states that the package decides."""

import re
from pathlib import Path
from typing import Final

from ffman import __version__

README: Final = Path(__file__).resolve().parents[1] / "README.md"


def test_the_images_tag_is_the_version() -> None:
    # nix/image.nix tags the image with ffman's version: docker load names it so
    tags = re.findall(r"\bffman:(\S+)", README.read_text(encoding="utf-8"))
    assert tags  # the image's command is there
    assert set(tags) == {__version__}
