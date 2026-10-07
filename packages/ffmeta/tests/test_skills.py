"""ffmeta held to the repository's skills (.agents/skills), word for word.

Its examples are its formats' skills' own; the mappings skill's tables are its fields' and its
examples its conversions'. The skills live at the repository's root, beside no package: this
file is left out of ffmeta's sdist (its own pyproject.toml), where they are not.
"""

from fractions import Fraction
from pathlib import Path
from typing import Final

import ffmeta
import pytest
from ffmeta.fields import DISC, RENAMED, TRACK
from ffmeta_support.examples import CUE, FFMETADATA, VORBIS

SKILLS: Final = Path(__file__).resolve().parents[3] / ".agents/skills"
MAPPINGS: Final = SKILLS / "metadata-mappings/SKILL.md"


def _block(text: str, lead: str) -> str:
    """The code block after ``lead``."""
    return text.split(f"{lead}\n\n```\n", 1)[1].split("```", 1)[0]


def _rows(text: str, lead: str) -> list[tuple[str, ...]]:
    """The table after ``lead``: each row's cells, unquoted -- its header and rule left out."""
    table = text.split(f"{lead}\n\n", 1)[1].split("\n\n", 1)[0].splitlines()[2:]
    return [tuple(cell.strip().strip("`") for cell in row.strip("|").split("|")) for row in table]


@pytest.mark.parametrize(
    ("skill", "lead", "example"),
    [
        ("cue", "An album, one file:", CUE),
        ("ffmetadata", "A file with every feature, as ffmpeg reads it:", FFMETADATA),
        ("vorbiscomment", "A file in ffman's form:", VORBIS),
    ],
)
def test_the_copy_is_the_skills(skill: str, lead: str, example: str) -> None:
    assert _block((SKILLS / skill / "SKILL.md").read_text(encoding="utf-8"), lead) == example


def test_the_mappings_skills_tables_are_ffmetas() -> None:
    text = MAPPINGS.read_text(encoding="utf-8")
    fields = [("disc", field) for field in DISC.fields] + [("track", f) for f in TRACK.fields]
    assert _rows(text, "which its tests hold this one to:") == [
        (holds, field.ffmetadata, field.vorbis or "--", field.cue) for holds, field in fields
    ]
    assert _rows(text, "`ARTIST` upper case in ffmetadata.") == list(RENAMED)


@pytest.mark.parametrize(
    ("source", "lead", "target", "media", "result", "lost"),
    [
        ("cue", "A cue sheet, its media 600 s long:", "ffmetadata", "", "As ffmetadata:",
         ["REM COMMENT", "INDEX 00"]),
        ("cue", "A cue sheet, its media 600 s long:", "vorbis", "", "As Vorbis comments:",
         ["REM COMMENT", "PERFORMER", "ISRC", "INDEX 00", "257693 ms"]),
        ("ffmetadata", "Back the other way, ffmetadata with a first chapter at 30 s:", "cue",
         "album.flac", "As a cue sheet, its media `album.flac`:",
         ["'artist'", "'comment'", "chapter 2's end", "frame 19327"]),
    ],
)  # fmt: skip
def test_the_mappings_skills_examples_are_ffmetas_conversions(
    source: ffmeta.Format,
    lead: str,
    target: ffmeta.Format,
    media: str,
    result: str,
    lost: list[str],
) -> None:
    """Each example converted as the skill shows it, and each note the loss its prose names."""
    text = MAPPINGS.read_text(encoding="utf-8")
    converted = ffmeta.convert(
        ffmeta.read(_block(text, lead), source, "x"), source, target, media=media
    )
    written = ffmeta.write(converted.meta, target, Fraction(600))
    assert written.text == _block(text, result)
    notes = converted.notes + written.notes
    assert len(notes) == len(lost)
    assert all(word in note for word, note in zip(lost, notes, strict=True))
