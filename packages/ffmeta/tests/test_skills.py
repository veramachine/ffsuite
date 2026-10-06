"""ffmeta's examples held to its formats' skills, word for word (the repository's .agents/skills).

The skills live at the repository's root, beside no package: this file is left out of ffmeta's
sdist (its own pyproject.toml), where they are not.
"""

from pathlib import Path
from typing import Final

import pytest
from ffmeta_support.examples import CUE, FFMETADATA, VORBIS

SKILLS: Final = Path(__file__).resolve().parents[3] / ".agents/skills"


@pytest.mark.parametrize(
    ("skill", "lead", "example"),
    [
        ("cue", "An album, one file:", CUE),
        ("ffmetadata", "A file with every feature, as ffmpeg reads it:", FFMETADATA),
        ("vorbiscomment", "A file in ffman's form:", VORBIS),
    ],
)
def test_the_copy_is_the_skills(skill: str, lead: str, example: str) -> None:
    text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
    assert text.split(f"{lead}\n\n```\n", 1)[1].split("```", 1)[0] == example
